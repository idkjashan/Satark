"""Tests for SafeHttpClient (LLD §17 SSRF guard). No test touches the real network:
HTTP is mocked with respx; DNS is mocked by injecting a fake resolver."""

from __future__ import annotations

import httpx
import pytest
import respx

from satark.infra.http import BlockedURL, Offline, SafeHttpClient

PUBLIC_IP = "93.184.216.34"  # a public, non-reserved address


def _resolver(table: dict[str, list[str]]):
    async def resolve(host: str) -> list[str]:
        return table.get(host, [PUBLIC_IP])

    return resolve


@pytest.fixture
async def client():
    c = SafeHttpClient(resolver=_resolver({}))
    yield c
    await c.aclose()


# ---- scheme / port --------------------------------------------------------------------


async def test_blocked_scheme(client):
    with pytest.raises(BlockedURL):
        await client.get("ftp://example.com/file")


@pytest.mark.parametrize("url", ["http://example.com:8080/", "https://example.com:8443/"])
async def test_blocked_port(client, url):
    with pytest.raises(BlockedURL):
        await client.get(url)


async def test_allowed_default_ports_pass_the_guard():
    client = SafeHttpClient(resolver=_resolver({}))
    with respx.mock:
        respx.get("https://example.com/").mock(return_value=httpx.Response(200, text="ok"))
        resp = await client.get("https://example.com/")
    assert resp.status_code == 200
    await client.aclose()


# ---- blocked addresses -----------------------------------------------------------------


@pytest.mark.parametrize(
    "addr",
    [
        "10.0.0.1",  # private
        "172.16.0.5",  # private
        "192.168.1.1",  # private
        "127.0.0.1",  # loopback
        "169.254.169.254",  # cloud metadata
        "169.254.1.1",  # link-local
        "100.64.0.1",  # CGNAT
        "0.0.0.0",  # unspecified
        "224.0.0.1",  # multicast
        "::1",  # IPv6 loopback
        "fc00::1",  # IPv6 unique-local
        "fe80::1",  # IPv6 link-local
    ],
)
async def test_blocked_addresses(addr):
    client = SafeHttpClient(resolver=_resolver({"evil.example": [addr]}))
    with pytest.raises(BlockedURL):
        await client.get("http://evil.example/")
    await client.aclose()


async def test_unresolvable_host_is_blocked():
    async def resolve(host: str) -> list[str]:
        return []

    client = SafeHttpClient(resolver=resolve)
    with pytest.raises(BlockedURL):
        await client.get("http://nowhere.example/")
    await client.aclose()


# ---- redirects --------------------------------------------------------------------------


async def test_redirect_to_private_ip_is_refused():
    client = SafeHttpClient(resolver=_resolver({"safe.example": [PUBLIC_IP], "internal.local": ["127.0.0.1"]}))
    with respx.mock:
        respx.head("http://safe.example/go").mock(
            return_value=httpx.Response(302, headers={"Location": "http://internal.local/secret"})
        )
        with pytest.raises(BlockedURL):
            await client.resolve_redirects("http://safe.example/go")
    await client.aclose()


async def test_resolve_redirects_follows_chain_to_final_url():
    client = SafeHttpClient(resolver=_resolver({}))
    with respx.mock:
        respx.head("http://hop1.example/a").mock(
            return_value=httpx.Response(301, headers={"Location": "http://hop2.example/b"})
        )
        respx.head("http://hop2.example/b").mock(return_value=httpx.Response(200))
        chain = await client.resolve_redirects("http://hop1.example/a")
    assert chain == ["http://hop1.example/a", "http://hop2.example/b"]
    await client.aclose()


async def test_resolve_redirects_falls_back_to_ranged_get_when_head_not_allowed():
    client = SafeHttpClient(resolver=_resolver({}))
    with respx.mock:
        respx.head("http://nohead.example/x").mock(return_value=httpx.Response(405))
        get_route = respx.get("http://nohead.example/x").mock(
            return_value=httpx.Response(302, headers={"Location": "http://final.example/"})
        )
        respx.head("http://final.example/").mock(return_value=httpx.Response(200))
        chain = await client.resolve_redirects("http://nohead.example/x")
    assert chain == ["http://nohead.example/x", "http://final.example/"]
    assert get_route.calls.last.request.headers["range"] == "bytes=0-0"
    await client.aclose()


async def test_resolve_redirects_stops_at_max_hops():
    client = SafeHttpClient(resolver=_resolver({}))
    with respx.mock:
        for i in range(1, 6):
            respx.head(f"http://chain.example/{i}").mock(
                return_value=httpx.Response(302, headers={"Location": f"http://chain.example/{i + 1}"})
            )
        chain = await client.resolve_redirects("http://chain.example/1", max_hops=3)
    assert chain == [f"http://chain.example/{i}" for i in (1, 2, 3, 4)]
    await client.aclose()


# ---- body size cap ------------------------------------------------------------------------


async def test_get_truncates_body_at_max_bytes():
    client = SafeHttpClient(resolver=_resolver({}))
    with respx.mock:
        respx.get("http://big.example/").mock(return_value=httpx.Response(200, content=b"x" * 10_000))
        resp = await client.get("http://big.example/", max_bytes=100)
    assert len(resp.content) == 100
    await client.aclose()


# ---- offline mode -------------------------------------------------------------------------


async def test_offline_mode_blocks_every_call():
    client = SafeHttpClient(network=False)
    with pytest.raises(Offline):
        await client.get("http://example.com/")
    with pytest.raises(Offline):
        await client.head("http://example.com/")
    with pytest.raises(Offline):
        await client.resolve_redirects("http://example.com/")
    await client.aclose()


async def test_dns_rebinding_is_blocked_at_connect_time():
    """The early guard sees a public IP; the connection-time lookup returns loopback: must be refused."""
    from satark.infra.http import BlockedURL, SafeHttpClient

    answers = iter([["93.184.216.34"], ["127.0.0.1"]])

    async def flip(host):
        return next(answers, ["127.0.0.1"])

    client = SafeHttpClient(resolver=flip)
    with pytest.raises(BlockedURL):
        await client.get("http://rebind.example/", timeout=1)
    await client.aclose()


@pytest.mark.parametrize("addr", ["::ffff:127.0.0.1", "::ffff:10.1.2.3", "100.64.0.1", "169.254.169.254"])
def test_mapped_and_special_addresses_are_blocked(addr):
    import ipaddress

    from satark.infra.http import _is_blocked_ip

    assert _is_blocked_ip(ipaddress.ip_address(addr))
