"""Link family checkers (LLD §9.4): unshortening, blocklists, RDAP age, look-alike domains,
official domains, bank/government domain rules, sideloaded APKs, free-hosted landing pages
and brand popularity. See satark/checkers/base.py for the plugin contract.
"""

from __future__ import annotations

import functools
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
import idna
import tldextract
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
from satark.config import ROOT
from satark.harness.state import CaseState, CheckResult, Entity, EntityDraft, SourceRef
from satark.infra import norm
from satark.infra.http import BlockedURL, Offline

# tldextract config mirrors satark/infra/norm.py (a fixed file, so not imported from there):
# .bank.in and .fin.in are RBI-mandated suffixes newer than some public-suffix-list snapshots.
_tld = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None, extra_suffixes=("bank.in", "fin.in"))

_CONFUSABLE_MAP = str.maketrans(
    {
        "0": "o", "1": "l", "3": "e", "4": "a", "5": "s", "6": "g", "7": "t", "8": "b",
        # Cyrillic look-alikes
        "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "х": "x", "у": "y", "к": "k",
        "м": "m", "н": "h", "т": "t", "в": "b", "і": "i", "ѕ": "s", "ԍ": "g", "ⅰ": "i",
        # Greek look-alikes
        "α": "a", "ο": "o", "ρ": "p", "υ": "u", "κ": "k", "ν": "v", "ι": "i", "τ": "t",
    }
)

_RDAP_IN_FAMILY = (
    "in", "bank.in", "fin.in", "gov.in", "nic.in", "co.in", "org.in", "net.in", "res.in",
    "firm.in", "ind.in", "gen.in", "ac.in",
)
_RDAP_IN_BASE = "https://rdap.nixiregistry.in/rdap/"
# ponytail: used only if data/manual/misc/iana_rdap_dns.json (B's job) is missing or not yet in
# IANA bootstrap shape; extend when more TLDs matter for the demo set.
_RDAP_FALLBACK = {
    "com": "https://rdap.verisign.com/com/v1/",
    "net": "https://rdap.verisign.com/net/v1/",
    "org": "https://rdap.publicinterestregistry.org/rdap/",
}

_OFFICIAL_CACHE: dict[tuple[int, int], list[Any]] = {}  # (id(db), db.data_version) -> rows


# ---- small shared helpers ---------------------------------------------------------------


@functools.lru_cache(maxsize=4)
def _link_rules(root: Path = ROOT) -> dict[str, Any]:
    """Cached yaml.safe_load of config/link_rules.yaml (satark/config.py does not load this one)."""
    import yaml

    with (root / "config" / "link_rules.yaml").open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    data["shorteners"] = set(data.get("shorteners") or ())
    data["known_spoofs"] = set(data.get("known_spoofs") or ())
    data["free_hosting"] = list(data.get("free_hosting") or ())
    return data


def _domain_of(entity: Entity, ctx: CheckContext) -> str:
    """The registrable domain: `domain` entities already hold it; `url` entities need deriving."""
    raw = ctx.raw(entity)
    return raw if entity.type == "domain" else norm.registrable_domain(raw)


def _url_host_path(raw: str) -> tuple[str, str]:
    s = raw if "://" in raw else f"//{raw}"
    parts = urlsplit(s, scheme="http")
    return norm.host_norm(parts.hostname or ""), parts.path or ""


def _label(domain: str) -> str:
    return _tld(domain).domain or domain


def _table_empty(db: Any, table: str) -> bool:
    return db.one(f"SELECT 1 FROM {table} LIMIT 1") is None  # noqa: S608 (table name is our own literal)


def _is_official(db: Any, domain: str) -> bool:
    return db is not None and db.one("SELECT 1 FROM official_domain WHERE domain = ?", (domain,)) is not None


def _official_rows(db: Any) -> list[Any]:
    key = (id(db), db.data_version)
    rows = _OFFICIAL_CACHE.get(key)
    if rows is None:
        rows = db.query("SELECT domain, entity_name, category, brand_id FROM official_domain")
        _OFFICIAL_CACHE.clear()  # ponytail: one entry is enough for a single-process hackathon demo
        _OFFICIAL_CACHE[key] = rows
    return rows


def _matches_free_hosting(host: str, path: str, rules: list[str]) -> bool:
    for rule in rules:
        if "/" in rule:
            rhost, rpath = rule.split("/", 1)
            if host == rhost and path.lstrip("/").startswith(rpath):
                return True
        elif rule.startswith("*."):
            suffix = rule[2:]
            if host == suffix or host.endswith("." + suffix):
                return True
        elif host == rule:
            return True
    return False


def _confusable_skeleton(label: str) -> str:
    if label.startswith("xn--"):
        try:
            label = idna.decode(label)
        except idna.IDNAError:
            pass
    s = label.lower().translate(_CONFUSABLE_MAP)
    s = s.replace("rn", "m").replace("vv", "w")
    return re.sub(r"[-_]", "", s)


def _tokens(label: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", label.lower()) if t}


def _brand_tokens(brands: list[dict[str, Any]]) -> set[str]:
    tokens: set[str] = set()
    for b in brands:
        for alias in b.get("aliases", ()):
            a = str(alias).lower()
            if re.fullmatch(r"[a-z0-9]+", a):  # single-word aliases only ("sebi", "zerodha"...)
                tokens.add(a)
    return tokens


# ---- link.unshorten -----------------------------------------------------------------------


@register_checker
class LinkUnshorten(BaseChecker):
    id, family = "link.unshorten", "link"
    description = "Resolves redirects for a link and reveals its final destination."
    consumes = frozenset({"url"})
    produces = frozenset({"URL_SHORTENED"})
    needs = ("http",)
    source = "unshorten"
    privacy = "public_only"
    cost = 2
    timeout_s = 1.5

    async def check(self, entity: Entity, ctx: CheckContext) -> CheckResult:
        # No shortener allow-list gate: every url is resolved, so a redirect is caught even
        # when the first hop's host isn't on our seed list of known shorteners.
        raw = ctx.raw(entity)
        try:
            chain = await ctx.http.resolve_redirects(raw, max_hops=3, timeout=1.5)
        except Offline:
            return unknown("offline")
        except BlockedURL:
            return unknown("blocked")
        except httpx.RequestError as e:
            raise TransientError(f"unshorten connection error: {e}") from e
        final = chain[-1]
        orig_domain = norm.registrable_domain(raw)
        final_domain = norm.registrable_domain(final)
        derived = []
        if final != raw:
            derived.append(EntityDraft(type="url", value=final))
        if urlsplit(final).path.lower().endswith(".apk"):
            derived.append(EntityDraft(type="apk.link", value=final))
        is_shortener = orig_domain in _link_rules(ctx.config.root).get("shorteners", ())
        if is_shortener or final_domain != orig_domain:
            return hit(
                "URL_SHORTENED",
                basis="rule",
                facts={"hops": len(chain) - 1, "final_domain_raw": final_domain},
                derived=derived,
            )
        return clear(derived=derived)


# ---- link.blocklist -----------------------------------------------------------------------


@register_checker
class LinkBlocklist(BaseChecker):
    id, family = "link.blocklist", "link"
    description = "Is this domain on a phishing / threat-intelligence blocklist?"
    consumes = frozenset({"domain", "url"})
    produces = frozenset({"URL_KNOWN_PHISHING"})
    needs = ("db",)
    source = "blocklists"
    privacy = "local"
    decisive = True

    async def check(self, entity: Entity, ctx: CheckContext) -> CheckResult:
        if ctx.db is None or _table_empty(ctx.db, "blocklist_domain"):
            return unknown("source_missing")
        domain = _domain_of(entity, ctx)
        host = domain if entity.type == "domain" else _url_host_path(ctx.raw(entity))[0]
        src = SourceRef(id="blocklists", as_on=ctx.db.source_as_on("blocklists"))
        row = ctx.db.one("SELECT domain, feeds FROM blocklist_domain WHERE domain IN (?, ?)", (host, domain))
        if row:
            return hit(
                "URL_KNOWN_PHISHING",
                basis="threat_feed",
                facts={"matched_raw": row["domain"], "feeds": row["feeds"]},
                source=src,
            )
        return clear(source=src)


# ---- link.safe_browsing (optional: free key) ----------------------------------------------

_SB_URL = "https://safebrowsing.googleapis.com/v4/threatMatches:find"


@register_checker
class LinkSafeBrowsing(BaseChecker):
    id, family = "link.safe_browsing", "link"
    description = "Does Google Safe Browsing list this link as phishing, malware or unwanted software?"
    consumes = frozenset({"url"})
    produces = frozenset({"URL_KNOWN_PHISHING"})
    needs = ("http", "secret:SATARK_SAFE_BROWSING_KEY")  # disabled (and listed in /v1/meta) without the free key
    source = "safe_browsing"
    privacy = "public_only"
    cost = 2
    cache_ttl_s = 3600

    async def check(self, entity: Entity, ctx: CheckContext) -> CheckResult:
        key = ctx.secrets.get("SATARK_SAFE_BROWSING_KEY")
        if not key:
            return unknown("source_missing")
        src = SourceRef(id="safe_browsing", as_on=ctx.now.date().isoformat())
        body = {
            "client": {"clientId": "satark", "clientVersion": "0.1"},
            "threatInfo": {
                "threatTypes": ["MALWARE", "SOCIAL_ENGINEERING", "UNWANTED_SOFTWARE"],
                "platformTypes": ["ANY_PLATFORM"], "threatEntryTypes": ["URL"],
                "threatEntries": [{"url": ctx.raw(entity)}],
            },
        }
        try:
            resp = await ctx.http.post_json(f"{_SB_URL}?key={key}", body, timeout=2.5)
        except Offline:
            return unknown("offline")
        except BlockedURL:
            return unknown("blocked")
        except httpx.RequestError as e:
            raise TransientError(f"safe browsing connection error: {type(e).__name__}") from e
        if resp.status_code == 429 or resp.status_code >= 500:
            raise TransientError(f"safe browsing http {resp.status_code}")
        if resp.status_code != 200:
            return unknown("safe_browsing_error", source=src)  # 400/403: bad or unauthorised key
        try:
            matches = resp.json().get("matches")
        except ValueError:
            return unknown("safe_browsing_error", source=src)
        if matches:
            return hit("URL_KNOWN_PHISHING", basis="threat_feed", source=src,
                       facts={"threats": sorted({m.get("threatType", "") for m in matches})})
        return clear(source=src)


# ---- link.rdap_age ------------------------------------------------------------------------


@functools.lru_cache(maxsize=1)
def _rdap_bootstrap(root: Path = ROOT) -> dict[str, str]:
    """tld -> base RDAP URL. `.in` and its second-level suffixes always use NIXI's server."""
    table = dict(_RDAP_FALLBACK)
    path = root / "data" / "manual" / "misc" / "iana_rdap_dns.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        for tlds, urls in data.get("services", []):
            if tlds and urls:
                base = urls[0].rstrip("/") + "/"
                table.update({t.lower(): base for t in tlds})
    except Exception:
        pass  # ponytail: a missing/malformed bootstrap snapshot falls back to the table above
    table.update({tld: _RDAP_IN_BASE for tld in _RDAP_IN_FAMILY})
    return table


def _rdap_base_for(domain: str, root: Path = ROOT) -> str | None:
    table = _rdap_bootstrap(root)
    labels = domain.split(".")
    for i in range(1, len(labels)):
        suffix = ".".join(labels[i:])
        if suffix in table:
            return table[suffix]
    return None


@register_checker
class LinkRdapAge(BaseChecker):
    id, family = "link.rdap_age", "link"
    description = "How old is this domain's registration? A brand-new domain is a red flag."
    consumes = frozenset({"domain"})
    produces = frozenset({"DOMAIN_YOUNG", "DOMAIN_OLD"})
    needs = ("http",)
    source = "rdap"
    privacy = "public_only"
    cost = 2
    cache_ttl_s = 86400

    async def check(self, entity: Entity, ctx: CheckContext) -> CheckResult:
        domain = _domain_of(entity, ctx)
        base = _rdap_base_for(domain, ctx.config.root)
        if not base:
            return unknown("source_missing")
        src = SourceRef(id="rdap", as_on=ctx.now.date().isoformat())
        try:
            resp = await ctx.http.get(f"{base}domain/{domain}", timeout=2.5)
        except Offline:
            return unknown("offline")
        except BlockedURL:
            return unknown("blocked")
        except httpx.RequestError as e:
            raise TransientError(f"rdap connection error: {e}") from e
        if resp.status_code == 404:
            return clear(facts={"rdap_not_found": True}, source=src)
        if resp.status_code == 429 or resp.status_code >= 500:
            raise TransientError(f"rdap http {resp.status_code}")
        if resp.status_code != 200:
            return unknown("rdap_error", source=src)
        try:
            data = resp.json()
        except ValueError:
            return unknown("rdap_error", source=src)
        reg_date = next(
            (e.get("eventDate") for e in data.get("events", []) if e.get("eventAction") == "registration"), None
        )
        if not reg_date:
            return unknown("rdap_error", source=src)
        try:
            age_days = (ctx.now - datetime.fromisoformat(reg_date)).days
        except ValueError:
            return unknown("rdap_error", source=src)
        facts = {"registered_on": reg_date, "age_days": age_days}
        if age_days < 90:
            return hit("DOMAIN_YOUNG", basis="registry", facts=facts, source=src)
        if age_days > 3 * 365:
            return clear("DOMAIN_OLD", basis="registry", facts=facts, source=src)
        return clear(facts=facts, source=src)


# ---- link.lookalike -----------------------------------------------------------------------


@register_checker
class LinkLookalike(BaseChecker):
    id, family = "link.lookalike", "link"
    description = "Does this domain's name imitate a known brand (confusable letters, a near-miss spelling, or 'brand-support.xyz')?"
    consumes = frozenset({"domain"})
    produces = frozenset({"DOMAIN_LOOKALIKE"})
    needs = ("db",)
    privacy = "local"

    async def check(self, entity: Entity, ctx: CheckContext) -> CheckResult:
        if ctx.db is None or _table_empty(ctx.db, "official_domain"):
            return unknown("source_missing")
        domain = _domain_of(entity, ctx)
        rows = _official_rows(ctx.db)
        if any(r["domain"] == domain for r in rows):
            return clear()  # the official domain itself (or one of its own rows): never flag it
        label = _label(domain)
        skeleton = _confusable_skeleton(label)
        tokens = _tokens(label)
        official_labels = {_label(r["domain"]): r["domain"] for r in rows}
        if label in official_labels:
            # The brand's exact name under another suffix (zerodha.in, groww.com) is often the brand's own
            # domain: not enough evidence to call it an imitation. Domain age and the message's other
            # signals still apply; confusable spellings and "brand-support" names below are still flagged.
            return clear(facts={"same_name_as_raw": official_labels[label]})
        for off_label, off_domain in official_labels.items():
            if skeleton and off_label and skeleton == _confusable_skeleton(off_label):
                return hit("DOMAIN_LOOKALIKE", basis="rule", facts={"looks_like_raw": off_domain})
            if off_label and fuzz.ratio(label, off_label) >= 85:
                return hit("DOMAIN_LOOKALIKE", basis="rule", facts={"looks_like_raw": off_domain})
        brand_tokens = _brand_tokens(ctx.config.brands)
        hits = tokens & (brand_tokens | official_labels.keys())
        if hits:
            token = next(iter(hits))
            return hit("DOMAIN_LOOKALIKE", basis="rule", facts={"looks_like_raw": official_labels.get(token, token)})
        return clear()


# ---- link.official ------------------------------------------------------------------------


@register_checker
class LinkOfficial(BaseChecker):
    id, family = "link.official", "link"
    description = "Is this domain one of our known brands' official domains?"
    consumes = frozenset({"domain"})
    produces = frozenset({"DOMAIN_OFFICIAL"})
    needs = ("db",)
    source = "official_domains"
    privacy = "local"

    async def check(self, entity: Entity, ctx: CheckContext) -> CheckResult:
        if ctx.db is None or _table_empty(ctx.db, "official_domain"):
            return unknown("source_missing")
        domain = _domain_of(entity, ctx)
        src = SourceRef(id="official_domains", as_on=ctx.db.source_as_on("official_domains"))
        row = ctx.db.one("SELECT entity_name, category FROM official_domain WHERE domain = ?", (domain,))
        if row:
            facts = {"entity_name": row["entity_name"], "category": row["category"]}
            return clear("DOMAIN_OFFICIAL", basis="official_list", facts=facts, source=src)
        return clear(source=src)


# ---- link.domain_rules --------------------------------------------------------------------


@register_checker
class LinkDomainRules(BaseChecker):
    id, family = "link.domain_rules", "link"
    description = "Banks only on .bank.in, government only on .gov.in/.nic.in, and known spoof domains."
    consumes = frozenset({"domain"})
    produces = frozenset({"BANK_NOT_BANK_IN", "GOVT_NOT_GOV_IN", "OFFICIAL_DOMAIN_SPOOF"})
    needs = ("db",)
    privacy = "local"

    async def check(self, entity: Entity, ctx: CheckContext) -> CheckResult:
        domain = _domain_of(entity, ctx)
        rules = _link_rules(ctx.config.root)
        codes: list[str] = []
        if domain in rules.get("known_spoofs", ()):
            codes.append("OFFICIAL_DOMAIN_SPOOF")
        official = _is_official(ctx.db, domain)
        for claim in ctx.case.by_type("claim.impersonates"):
            kind = claim.attrs.get("kind")
            brand_id = claim.attrs.get("brand_id")
            if kind == "bank" and not domain.endswith(".bank.in") and not official:
                if "BANK_NOT_BANK_IN" not in codes:
                    codes.append("BANK_NOT_BANK_IN")
            elif kind in ("government", "regulator"):
                if not (domain.endswith(".gov.in") or domain.endswith(".nic.in")) and not official:
                    if "GOVT_NOT_GOV_IN" not in codes:
                        codes.append("GOVT_NOT_GOV_IN")
            if brand_id in ("sebi", "rbi") and "OFFICIAL_DOMAIN_SPOOF" not in codes:
                email_domains = {norm.registrable_domain(ctx.raw(e)) for e in ctx.case.by_type("email")}
                if domain in email_domains and domain not in {"sebi.gov.in", "rbi.org.in"}:
                    codes.append("OFFICIAL_DOMAIN_SPOOF")
        if codes:
            return hit(*codes, basis="rule")
        return clear()


# ---- link.apk -----------------------------------------------------------------------------


@register_checker
class LinkApk(BaseChecker):
    id, family = "link.apk", "link"
    description = "A direct .apk download link, not an app store."
    consumes = frozenset({"apk.link"})
    produces = frozenset({"SIDELOAD_APK"})
    privacy = "local"
    decisive = True

    async def check(self, entity: Entity, ctx: CheckContext) -> CheckResult:
        return hit("SIDELOAD_APK", basis="rule")


# ---- link.google_hosted -------------------------------------------------------------------


@register_checker
class LinkGoogleHosted(BaseChecker):
    id, family = "link.google_hosted", "link"
    description = "A landing page on free hosting (Google Forms/Sites, Firebase, Netlify...), not a company's own site."
    consumes = frozenset({"url"})
    produces = frozenset({"FREE_HOSTED_LANDING"})
    privacy = "local"

    async def check(self, entity: Entity, ctx: CheckContext) -> CheckResult:
        host, path = _url_host_path(ctx.raw(entity))
        rules = _link_rules(ctx.config.root)
        if _matches_free_hosting(host, path, rules.get("free_hosting", ())):
            return hit("FREE_HOSTED_LANDING", basis="rule", facts={"host_raw": host})
        return clear()


# ---- link.popularity ----------------------------------------------------------------------


@register_checker
class LinkPopularity(BaseChecker):
    id, family = "link.popularity", "link"
    description = "A domain claiming to be a well-known brand should show up in India's popular-sites list."
    consumes = frozenset({"domain"})
    produces = frozenset({"DOMAIN_UNPOPULAR_FOR_BRAND"})
    needs = ("db",)
    source = "crux_india"
    privacy = "local"

    def should_run(self, entity: Entity, case: CaseState) -> bool:
        return bool(case.by_type("claim.impersonates"))

    async def check(self, entity: Entity, ctx: CheckContext) -> CheckResult:
        if ctx.db is None or _table_empty(ctx.db, "popularity"):
            return unknown("source_missing")
        domain = _domain_of(entity, ctx)
        src = SourceRef(id="crux_india", as_on=ctx.db.source_as_on("crux_india"))
        popular = ctx.db.one("SELECT 1 FROM popularity WHERE domain = ?", (domain,)) is not None
        if not popular and not _is_official(ctx.db, domain):
            return hit("DOMAIN_UNPOPULAR_FOR_BRAND", basis="rule", source=src)
        return clear(source=src)
