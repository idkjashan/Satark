"""SafeHttpClient: the only way a checker reaches the network (LLD §17, SSRF guard).

One shared httpx.AsyncClient for the process. Every request, and every redirect hop inside
`resolve_redirects`, is checked before it goes out: scheme, port, then a DNS resolve that
must not land on a private, loopback, link-local, CGNAT, multicast, reserved or unspecified
address. A failure never raises past a checker as a surprise exception: checkers catch
`BlockedURL` / `Offline` themselves and turn them into `unknown(...)` evidence.
"""

from __future__ import annotations

import asyncio
import ipaddress
from urllib.parse import urlsplit

import httpcore
import httpx

USER_AGENT = "SatarkBot/0.1 (investor-safety prototype)"

_ALLOWED_SCHEMES = frozenset({"http", "https"})
_ALLOWED_PORTS = frozenset({80, 443})
_CGNAT = ipaddress.ip_network("100.64.0.0/10")  # carrier-grade NAT; not covered by ip.is_private


class BlockedURL(Exception):
    """A URL (or a redirect hop) fails the SSRF guard: bad scheme/port, or resolves to a disallowed IP."""


class Offline(Exception):
    """Raised by every call when SafeHttpClient(network=False) (tests, offline demos)."""


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:  # ::ffff:127.0.0.1 must not slip through
        ip = ip.ipv4_mapped
    if isinstance(ip, ipaddress.IPv4Address) and ip in _CGNAT:
        return True
    # covers loopback (127/8, ::1), link-local incl. 169.254.169.254 (169.254/16, fe80::/10),
    # private incl. unique-local IPv6 (10/8, 172.16/12, 192.168/16, fc00::/7), multicast,
    # IETF-reserved and unspecified (0.0.0.0, ::).
    return (
        ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified
    )


class _GuardedBackend(httpcore.AsyncNetworkBackend):
    """Every TCP connection httpx opens goes through here: resolve the host once, refuse any blocked
    address, and connect to the vetted IP itself. The TLS layer still verifies the certificate against
    the hostname (httpcore passes the origin host as server_hostname), so pinning breaks nothing - and a
    DNS-rebinding answer between "check" and "connect" can no longer reach an internal address."""

    def __init__(self, resolve) -> None:
        self._resolve = resolve
        self._inner = httpcore.AnyIOBackend()

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):  # noqa: ASYNC109
        try:
            addrs = [host] if _is_ip(host) else await self._resolve(host)
        except OSError as e:
            raise BlockedURL(f"could not resolve {host}: {e}") from e
        if not addrs or any(_is_blocked_ip(ipaddress.ip_address(a)) for a in addrs):
            raise BlockedURL(f"{host} resolves to a disallowed address")
        return await self._inner.connect_tcp(
            addrs[0], port, timeout=timeout, local_address=local_address, socket_options=socket_options
        )

    async def connect_unix_socket(self, path, timeout=None, socket_options=None):  # noqa: ASYNC109  # pragma: no cover
        raise BlockedURL("unix sockets are not allowed")

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
        return True
    except ValueError:
        return False


class SafeHttpClient:
    """Pre-request SSRF guard + one no-cookie, no-redirect httpx.AsyncClient.

    `resolver` is injectable for tests (`monkeypatch` the resolver rather than the real DNS).
    """

    def __init__(self, network: bool = True, resolver=None) -> None:
        self.network = network
        self._resolve = resolver or self._getaddrinfo
        transport = httpx.AsyncHTTPTransport()
        # swap in a pool whose connections are resolved, vetted and pinned by _GuardedBackend
        transport._pool = httpcore.AsyncConnectionPool(
            ssl_context=transport._pool._ssl_context,
            max_connections=100,
            max_keepalive_connections=20,
            keepalive_expiry=5.0,
            network_backend=_GuardedBackend(self._resolve),
        )
        self._client = httpx.AsyncClient(
            transport=transport,
            follow_redirects=False,
            headers={"User-Agent": USER_AGENT},
            timeout=httpx.Timeout(2.5),
        )

    @staticmethod
    async def _getaddrinfo(host: str) -> list[str]:
        loop = asyncio.get_running_loop()
        infos = await loop.getaddrinfo(host, None)
        return [info[4][0] for info in infos]

    async def _guard(self, url: str) -> None:
        """Raise BlockedURL unless `url` is http(s), port 80/443, and resolves only to public IPs."""
        parts = urlsplit(url)
        if parts.scheme not in _ALLOWED_SCHEMES:
            raise BlockedURL(f"scheme not allowed: {url}")
        port = parts.port or (443 if parts.scheme == "https" else 80)
        if port not in _ALLOWED_PORTS:
            raise BlockedURL(f"port not allowed: {url}")
        host = parts.hostname
        if not host:
            raise BlockedURL(f"no host: {url}")
        try:
            addrs = await self._resolve(host)
        except OSError as e:  # socket.gaierror and friends
            raise BlockedURL(f"could not resolve {host}: {e}") from e
        if not addrs:
            raise BlockedURL(f"could not resolve {host}")
        for addr in addrs:
            if _is_blocked_ip(ipaddress.ip_address(addr)):
                raise BlockedURL(f"{host} resolves to a disallowed address")
        # This early check fails fast with a clear reason; the authoritative check is at connect time
        # in _GuardedBackend, which also pins the vetted IP (no DNS-rebinding window).

    # noqa plain `timeout` kwargs below match httpx's own convention (the contract fixes these signatures).
    async def get(self, url: str, timeout: float = 2.5, headers: dict[str, str] | None = None, max_bytes: int = 512_000) -> httpx.Response:  # noqa: ASYNC109
        if not self.network:
            raise Offline(url)
        await self._guard(url)
        request = self._client.build_request("GET", url, headers=headers, timeout=timeout)
        response = await self._client.send(request, stream=True)
        try:
            chunks: list[bytes] = []
            total = 0
            async for chunk in response.aiter_bytes():
                chunks.append(chunk)
                total += len(chunk)
                if total >= max_bytes:
                    break
            response._content = b"".join(chunks)[:max_bytes]
        finally:
            await response.aclose()
        return response

    async def post_json(self, url: str, payload: dict, timeout: float = 2.5) -> httpx.Response:  # noqa: ASYNC109
        if not self.network:
            raise Offline(url)
        await self._guard(url)
        return await self._client.post(url, json=payload, timeout=timeout)

    async def head(self, url: str, timeout: float = 1.5) -> httpx.Response:  # noqa: ASYNC109
        if not self.network:
            raise Offline(url)
        await self._guard(url)
        request = self._client.build_request("HEAD", url, timeout=timeout)
        return await self._client.send(request)

    async def resolve_redirects(self, url: str, max_hops: int = 3, timeout: float = 1.5) -> list[str]:  # noqa: ASYNC109
        """Follow up to `max_hops` redirects (HEAD, falling back to a 1-byte ranged GET).

        Returns the URL chain starting with `url`. Every hop is re-checked by the SSRF guard
        (inside `head`/`get`), so a redirect to a private address raises BlockedURL immediately.
        """
        if not self.network:
            raise Offline(url)
        chain = [url]
        current = url
        for _ in range(max_hops):
            try:
                resp = await self.head(current, timeout=timeout)
                if resp.status_code in (405, 501):
                    raise httpx.HTTPError("HEAD not allowed")
            except httpx.HTTPError:
                resp = await self.get(current, timeout=timeout, headers={"Range": "bytes=0-0"}, max_bytes=1)
            if not resp.has_redirect_location:
                break
            current = str(httpx.URL(current).join(resp.headers["location"]))
            chain.append(current)
        return chain

    async def aclose(self) -> None:
        await self._client.aclose()
