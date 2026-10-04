"""Normalisers shared by the ingest job and the checkers, so stored and looked-up values match."""

from __future__ import annotations

import hashlib
import re
import unicodedata

import tldextract

# tldextract must not fetch the public suffix list at runtime: use the snapshot bundled with the package.
# .bank.in (banks) and .fin.in (other financial entities) are RBI-mandated suffixes newer than some snapshots.
_tld = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None, extra_suffixes=("bank.in", "fin.in"))

_LEGAL_SUFFIXES = re.compile(
    r"\b(private|pvt|limited|ltd|llp|inc|co|company|corp|corporation|the|and|m/s|ms|mr|mrs|shri|smt|dr)\b\.?"
)
_NON_WORD = re.compile(r"[^0-9a-zऀ-ॿ]+")


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def name_norm(name: str) -> str:
    """'M/s. ABC Research Pvt. Ltd.' -> 'abc research'. Lower case, legal suffixes and punctuation removed."""
    s = unicodedata.normalize("NFKC", name or "").lower()
    s = s.replace("&", " ")
    s = _LEGAL_SUFFIXES.sub(" ", s)
    s = _NON_WORD.sub(" ", s)
    return " ".join(s.split())


def reg_norm(reg_no: str) -> str:
    """'ina 000 012345' -> 'INA000012345'; keeps the slashes and dashes of DP/MF/AIF numbers."""
    return re.sub(r"\s+", "", (reg_no or "").upper())


def host_norm(host: str) -> str:
    """Lower case, no trailing dot, no 'www.', IDN to punycode (IDNA 2008 / UTS #46)."""
    h = (host or "").strip().strip(".").lower()
    if h.startswith("www."):
        h = h[4:]
    try:
        import idna

        h = idna.encode(h, uts46=True).decode("ascii")
    except Exception:
        pass
    return h


def registrable_domain(host_or_url: str) -> str:
    """eTLD+1: 'https://kite.zerodha.com/x' -> 'zerodha.com'; 'sbi.bank.in' -> 'sbi.bank.in';
    'evil.github.io' -> 'evil.github.io'."""
    s = host_or_url.strip()
    if "://" in s:
        s = s.split("://", 1)[1]
    s = s.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0].split("@")[-1].split(":", 1)[0]
    # shared-hosting suffixes (PSL private section: github.io, blogspot.com, web.app...) count, so one site on
    # a platform is judged on its own, never as the whole platform ("evil.github.io", not "github.io")
    ext = _tld(host_norm(s), include_psl_private_domains=True)
    if ext.domain and ext.suffix:
        return f"{ext.domain}.{ext.suffix}"
    return host_norm(s)


def site_domain(host_or_url: str) -> str:
    """Like registrable_domain, but shared-hosting suffixes count (PSL private section): 'evil.github.io' stays
    'evil.github.io' instead of collapsing to 'github.io' — one site, not the whole platform."""
    s = host_or_url.strip()
    if "://" in s:
        s = s.split("://", 1)[1]
    s = s.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0].split("@")[-1].split(":", 1)[0]
    ext = _tld(host_norm(s), include_psl_private_domains=True)
    if ext.domain and ext.suffix:
        return f"{ext.domain}.{ext.suffix}"
    return host_norm(s)


def phone_norm(number: str) -> str:
    """E.164 for Indian and international numbers ('+919876543210'); digits only for short codes."""
    import phonenumbers

    raw = (number or "").strip()
    digits = re.sub(r"\D", "", raw)
    if len(digits) <= 6:  # short codes, helplines such as 1930, 14448
        return digits
    try:
        p = phonenumbers.parse(raw, "IN")
        return phonenumbers.format_number(p, phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        return digits


def handle_norm(handle: str) -> str:
    """'@KediaCapital' / 'https://x.com/KediaCapital?mx=2' -> 'kediacapital'."""
    h = (handle or "").strip()
    h = re.sub(r"^https?://", "", h, flags=re.I)
    h = h.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    if "/" in h:
        h = h.rsplit("/", 1)[-1]
    return h.lstrip("@").lower()


def upi_norm(vpa: str) -> str:
    return (vpa or "").strip().lower()


_ORG_MARKERS = re.compile(
    r"\b(limited|ltd|llp|pvt|private|fund|trust|inc|corporation|corp|company|ventures|capital|securities|"
    r"advisors?|advisers?|advisory|research|investments?|finance|fincorp|finvest|traders|trading|consultants?|"
    r"consultancy|services|associates|enterprises|industries|holdings|partners|group|global|broking|brokers?|"
    r"wealth|infra|developers|builders|exports|impex|agro|solutions|realty|estates?|fze|plc|gmbh|bank|"
    r"exchange|markets?|academy|institute)\b",
    re.I,
)


def looks_like_org(name: str) -> bool:
    """True for firm/fund names ("Pump Masters Pvt Ltd", "XYZ Capital"). Name-only matches against official
    lists are trusted for organisations only: Indian personal names repeat too often ("Rahul Meena") for a
    name match to identify a person — individuals are matched by PAN instead."""
    return bool(_ORG_MARKERS.search(name or ""))
