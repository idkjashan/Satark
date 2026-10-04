"""App family checkers (LLD §9.5): Play Store listing, NSE broker-app registry, remote access."""

from __future__ import annotations

import html
import json
import re
import time
from urllib.parse import quote

from rapidfuzz import fuzz

from satark.checkers.base import (
    BaseChecker,
    CheckContext,
    TransientError,
    clear,
    hit,
    register_checker,
    unknown,
)
from satark.harness.state import Basis, Entity, SourceRef
from satark.infra.norm import name_norm

_BRAND_KINDS = ("broker", "amc", "exchange")


def _basis(entity: Entity, default: Basis) -> Basis:
    return "llm_claim" if entity.origin == "llm" else default


def _claims_broker(ctx: CheckContext) -> bool:
    """Facts/claims only, never message wording: an impersonation claim, or a registered_as claim
    with category BROKER (product decision: no keyword-context gating for this signal)."""
    for c in ctx.case.by_type("claim.impersonates"):
        if c.attrs.get("kind") in ("broker", "exchange"):
            return True
    return any(c.attrs.get("category") == "BROKER" for c in ctx.case.by_type("claim.registered_as"))


def _claimed_brand_names(ctx: CheckContext) -> list[str]:
    """Names the claimed brand could legitimately be known by (claim + config/brands.yaml)."""
    names: list[str] = []
    for c in ctx.case.by_type("claim.impersonates"):
        if c.attrs.get("kind") not in _BRAND_KINDS:
            continue
        org = c.attrs.get("org")
        if org:
            names.append(org)
        brand_id = c.attrs.get("brand_id")
        for b in ctx.config.brands:
            if b.get("id") == brand_id or (org and b.get("name", "").lower() == str(org).lower()):
                names.append(b["name"])
                names.extend(b.get("aliases", []))
    return names


def _fuzzy_contains(developer: str, candidates: list[str]) -> bool:
    if not developer or not candidates:
        return False
    dn = name_norm(developer)
    # ponytail: 0.6 is a seed threshold (same band as the QR payee-name check); tune on the golden set.
    return any(fuzz.token_set_ratio(dn, name_norm(c)) / 100 >= 0.6 for c in candidates)


_TITLE_RE = re.compile(r'itemprop="name">([^<]+)</span>', re.I)
_DEV_RE = re.compile(r'/store/apps/(?:dev|developer)\?id=[^"]*"[^>]*>\s*<span>([^<]+)</span>', re.I)
_LDJSON_RE = re.compile(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', re.I | re.S)
_SEBI_VERIFIED_MARK = 'aria-label="SEBI verified"'


def _ldjson_name(page_text: str) -> str | None:
    m = _LDJSON_RE.search(page_text)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except ValueError:
        return None
    return data.get("name") if isinstance(data, dict) else None


def _parse_listing(page_text: str) -> tuple[str, str]:
    title_m = _TITLE_RE.search(page_text)
    title = html.unescape(title_m.group(1)) if title_m else (_ldjson_name(page_text) or "")
    dev_m = _DEV_RE.search(page_text)
    developer = html.unescape(dev_m.group(1)) if dev_m else ""
    return title, developer


_PAGE_CACHE: dict[str, tuple[float, tuple[int, str]]] = {}  # package -> (fetched at, (status, html))


@register_checker
class AppPlayListing(BaseChecker):
    id, family = "app.play_listing", "app"
    description = "Fetch the Google Play details page: title, developer, SEBI-verified badge."
    consumes = frozenset({"app.package"})
    produces = frozenset({"APP_NOT_ON_PLAY", "APP_DEVELOPER_MISMATCH", "APP_SEBI_VERIFIED"})
    needs = ("http",)
    source = "play"
    privacy = "public_only"
    cost = 2
    timeout_s = 2.5
    # The verdict depends on the case's claims (developer mismatch), so the executor must not cache it;
    # the fetched page itself is cached here per package for a day.
    cache_ttl_s = 0

    async def check(self, entity, ctx):
        pkg = ctx.raw(entity)
        page = _PAGE_CACHE.get(pkg)
        if page is None or time.monotonic() - page[0] > 86400:
            fetched = await self._fetch(pkg, ctx)
            if not isinstance(fetched, tuple):
                return fetched  # unknown(...)
            page = _PAGE_CACHE[pkg] = (time.monotonic(), fetched)
        status, text = page[1]
        return self._judge(entity, ctx, status, text)

    async def _fetch(self, pkg, ctx):
        url = f"https://play.google.com/store/apps/details?id={quote(pkg)}&hl=en_IN&gl=IN"
        try:
            # the details page is ~1.3 MB and the developer/verified markers sit past the 512 KB default cap
            resp = await ctx.http.get(url, timeout=self.timeout_s, max_bytes=3_000_000)
        except Exception as e:  # satark.infra.http may not be importable yet: match by class name
            name = type(e).__name__
            if name == "Offline":
                return unknown("offline")
            if name == "BlockedURL":
                return unknown("blocked")
            if isinstance(e, TransientError):
                raise
            raise TransientError(str(e)) from e

        if resp.status_code == 429 or resp.status_code >= 500:
            raise TransientError(f"play store returned {resp.status_code}")
        if resp.status_code not in (200, 404):
            return unknown(f"http_{resp.status_code}")
        return resp.status_code, (resp.text if resp.status_code == 200 else "")

    def _judge(self, entity, ctx, status: int, text: str):
        basis = _basis(entity, "rule")
        if status == 404:
            # product decision: a dead Play link is suspicious in any message, not only a "trading" one.
            return hit("APP_NOT_ON_PLAY", basis=basis, source=SourceRef(id=self.source))

        title, developer = _parse_listing(text)
        if not title and not developer:
            return unknown("unparseable")  # the page changed shape; never guess (daily canary, LLD §26.1)

        assure = ["APP_SEBI_VERIFIED"] if _SEBI_VERIFIED_MARK in text else []
        codes: list[str] = []
        brand_names = _claimed_brand_names(ctx)
        if brand_names and not _fuzzy_contains(developer, brand_names):
            codes.append("APP_DEVELOPER_MISMATCH")

        facts = {"title": title, "developer": developer}
        src = SourceRef(id=self.source)
        if codes:
            return hit(*codes, basis=basis, assure=assure, facts=facts, source=src)
        return clear(*assure, basis=basis, facts=facts, source=src)


@register_checker
class AppBrokerRegistry(BaseChecker):
    id, family = "app.broker_registry", "app"
    description = "Is this Android package id in NSE's broker-apps list?"
    consumes = frozenset({"app.package"})
    produces = frozenset({"APP_IN_BROKER_REGISTRY", "APP_CLAIMS_BROKER_NOT_LISTED"})
    needs = ("db",)
    source = "nse_broker_apps"
    decisive = True

    async def check(self, entity, ctx):
        pkg = ctx.raw(entity)
        if ctx.db is None or not ctx.db.one("SELECT 1 FROM app_registry LIMIT 1"):
            return unknown("source_missing")
        row = ctx.db.one("SELECT app_name, member_name FROM app_registry WHERE package_id = ?", (pkg,))
        src = SourceRef(id=self.source, as_on=ctx.db.source_as_on(self.source))
        basis = _basis(entity, "official_list")
        if row:
            return clear(
                "APP_IN_BROKER_REGISTRY",
                basis=basis,
                source=src,
                facts={"member_name": row["member_name"], "app_name": row["app_name"]},
            )
        if _claims_broker(ctx):
            return hit("APP_CLAIMS_BROKER_NOT_LISTED", basis=basis, source=src)
        return clear(source=src)


# Well-documented package ids for these four; not independently re-fetched from Play here
# (no network access in this task) -- recheck against each vendor's current listing before relying
# on this list in production.
_REMOTE_ACCESS_PACKAGES = {
    "com.anydesk.anydeskandroid": "AnyDesk",
    "com.teamviewer.quicksupport.market": "TeamViewer QuickSupport",
    "com.teamviewer.teamviewer.market.mobile": "TeamViewer Remote Control",
    "com.carriez.flutter_hbb": "RustDesk",
    # AirDroid's package id varies by edition (airdroid / airmirror / business); left out until
    # confirmed against a real listing rather than risk a wrong id.
}


@register_checker
class AppRemoteAccess(BaseChecker):
    id, family = "app.remote_access", "app"
    description = "A known remote-access app package, or an explicit request to install one."
    consumes = frozenset({"app.package", "request.remote_access"})
    produces = frozenset({"REMOTE_ACCESS_REQUEST"})
    decisive = True

    async def check(self, entity, ctx):
        basis = _basis(entity, "rule")
        if entity.type == "app.package":
            if ctx.raw(entity) in _REMOTE_ACCESS_PACKAGES:
                return hit("REMOTE_ACCESS_REQUEST", basis=basis)
            return clear()
        return hit("REMOTE_ACCESS_REQUEST", basis=basis)  # the claim's mere presence is the signal
