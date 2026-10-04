"""Named functions referenced by `normalise:` / `validate:` / `derive:` in config/entities.yaml.

Exposed as three dicts so the pipeline (and tests) can look functions up by name. A `normalise`
function takes the raw matched text and returns either the normalised value (str) or a
(value, attrs) tuple when it also derives attributes (e.g. return_rate). A `validate` function
takes the normalised value and returns bool. A `derive` function takes the normalised value and
returns a dict of attrs to merge into Entity.attrs. The special derive name "entity:domain" is
handled by the pipeline itself (it creates a new entity, not an attribute).
"""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from satark.infra import norm
from satark.infra import validators as _v

# ---------------------------------------------------------------------------------------- normalise


def _upper_nospace(v: str) -> str:
    return re.sub(r"\s+", "", v).upper()


def _digits(v: str) -> str:
    return re.sub(r"\D", "", v)


_TRACKING_PARAM = re.compile(r"(?i)^(utm_\w+|fbclid|gclid)$")
_SCHEME = re.compile(r"(?i)^[a-z][a-z0-9+.\-]*://")


def _url(v: str) -> str:
    s = v.strip()
    if not _SCHEME.match(s):
        s = "https://" + s
    p = urlsplit(s)
    netloc = p.netloc
    userinfo = ""
    if "@" in netloc:
        userinfo, netloc = netloc.rsplit("@", 1)
        userinfo += "@"
    host, _sep, port = netloc.partition(":")
    netloc = userinfo + norm.host_norm(host) + (":" + port if port else "")
    query = [(k, val) for k, val in parse_qsl(p.query, keep_blank_values=True) if not _TRACKING_PARAM.match(k)]
    return urlunsplit((p.scheme.lower(), netloc, p.path, urlencode(query), p.fragment))


_TG_HOST = re.compile(r"(?i)^https?://")
_TG_PREFIX = re.compile(r"(?i)^(t\.me|telegram\.me|telegram\.dog)/")


def _tg(v: str) -> str:
    path = _TG_PREFIX.sub("", _TG_HOST.sub("", v.strip()))
    if not (path.startswith("+") or path.lower().startswith("joinchat/")):
        path = path.lower()  # usernames (incl. s/<username>) are case-insensitive; invite hashes are not
    return f"t.me/{path}"


_SOCIAL_HOST = {
    "instagram.com": "instagram",
    "x.com": "x",
    "twitter.com": "x",
    "facebook.com": "facebook",
    "fb.com": "facebook",
    "youtube.com": "youtube",
}
_SOCIAL_WWW = re.compile(r"(?i)^(www\.|m\.)")


def _social(v: str) -> str:
    s = _TG_HOST.sub("", v.strip())
    s = _SOCIAL_WWW.sub("", s)
    host, _sep, rest = s.partition("/")
    platform = _SOCIAL_HOST.get(host.lower(), host.lower())
    return f"{platform}:{norm.handle_norm(rest)}"


_INR_MULT = {
    "k": 1e3,
    "l": 1e5,
    "lakh": 1e5,
    "lakhs": 1e5,
    "lac": 1e5,
    "cr": 1e7,
    "crore": 1e7,
    "crores": 1e7,
    "लाख": 1e5,
    "करोड़": 1e7,
}
_INR_RE = re.compile(r"(?i)(\d[\d,]*(?:\.\d+)?)\s*(k|l|lakh|lakhs|lac|cr|crore|crores|लाख|करोड़)?")


def _inr(v: str) -> str:
    m = _INR_RE.search(v)
    if not m:
        return "0"
    amount = float(m.group(1).replace(",", ""))
    mult = _INR_MULT.get((m.group(2) or "").lower(), 1)
    return str(int(round(amount * mult)))


_PCT_RE = re.compile(r"(\d{1,3}(?:\.\d{1,2})?)\s?%")
_MULTIPLIER_WORDS = {
    "double": 2, "doguna": 2, "dugna": 2,
    "triple": 3, "tiguna": 3,
    "डबल": 2, "दोगुना": 2, "दुगना": 2,
    "ट्रिपल": 3, "तिगुना": 3,
}
_PERIOD_WORDS = {
    "day": ("daily", "day", "din", "roz", "rozana", "दिन", "रोज़", "रोज", "रोजाना", "प्रतिदिन"),
    "week": ("weekly", "week", "hafta", "हफ्ते", "सप्ताह"),
    "month": ("monthly", "month", "mahina", "mahine", "महीने", "महीना"),
    "year": ("yearly", "year", "annum", "साल", "वर्ष"),
}
_PERIOD_ALTS = "|".join(
    re.escape(w) for w in sorted({w for words in _PERIOD_WORDS.values() for w in words}, key=len, reverse=True)
)
# "in 3 days" / "within a week" / "7 दिन में": an optional lead-in, an optional N, an optional
# bare "a", then the period word itself (N absent -> a single occurrence of that period, i.e. n=1).
_N_PERIODS_RE = re.compile(rf"(?:in|within|mein|में)?\s*(\d{{1,3}})?\s?(?:a\s+)?(?:{_PERIOD_ALTS})")


def _return_rate(v: str) -> tuple[str, dict]:
    """"5% daily" -> rate 0.05 (n=1, no compounding needed). "150% in 3 days" / "money double
    in 7 days": a total multiplier (1 + pct/100, or 2/3 for double/triple) reached over n
    periods, converted to the equivalent single-period rate: rate = total**(1/n) - 1 (e.g.
    150% over 3 days is a daily rate of 2.5**(1/3)-1; doubling over 7 days is 2**(1/7)-1/day)."""
    pct_m = _PCT_RE.search(v)
    low = v.lower()
    if pct_m:
        total = 1 + float(pct_m.group(1)) / 100
    else:
        total = next((mult for word, mult in _MULTIPLIER_WORDS.items() if word in low), 1.0)
    n_m = _N_PERIODS_RE.search(v)
    n = int(n_m.group(1)) if (n_m and n_m.group(1)) else 1
    period = next((p for p, words in _PERIOD_WORDS.items() if any(w in low for w in words)), "day")
    rate = round(total ** (1 / n) - 1, 4) if n > 0 else 0.0
    return f"{rate:g}/{period}", {"rate": rate, "period": period}


NORMALISERS: dict[str, object] = {
    "lower": str.lower,
    "strip": str.strip,
    "upper_nospace": _upper_nospace,
    "digits": _digits,
    "e164": norm.phone_norm,
    "url": _url,
    "domain": norm.registrable_domain,
    "tg": _tg,
    "social": _social,
    "inr": _inr,
    "return_rate": _return_rate,
    "name": norm.name_norm,
}

# ----------------------------------------------------------------------------------------- validate


def _upi_vpa_ok(v: str) -> bool:
    return bool(re.match(r"^[a-z0-9](?:[a-z0-9._-]*[a-z0-9])?@[a-z][a-z0-9]*$", v))


def _btc_ok(v: str) -> bool:
    return _v.bech32_ok(v) if v.lower().startswith("bc1") else _v.btc_base58_ok(v)


VALIDATORS: dict[str, object] = {
    "upi_vpa": _upi_vpa_ok,
    "verhoeff": _v.verhoeff_ok,
    "luhn": _v.luhn_ok,
    "btc": _btc_ok,
    "tron": _v.tron_ok,
}

# ------------------------------------------------------------------------------------------ derive


def psp_handle(value: str) -> dict:
    return {"psp_handle": value.rsplit("@", 1)[-1]} if "@" in value else {}


_SEBI_VALID = re.compile(r"^[a-z0-9]+(?:\.[a-z0-9]+)*\.(brk|bti|dp|ra|ia|invit|mf|pms|sreit|reit)@valid([a-z]+)$")


def sebi_valid(value: str) -> dict:
    m = _SEBI_VALID.match(value)
    if not m:
        return {"sebi_valid": False}
    return {"sebi_valid": True, "valid_category": m.group(1), "valid_bank": m.group(2)}


def reg_category(value: str) -> dict:
    v = value.upper()
    if v.startswith("IN-DP"):
        cat = "DP"
    elif v.startswith("MF/"):
        cat = "MF"
    elif v.startswith("IN/AIF"):
        cat = "AIF"
    elif v.startswith("IN/") or v.startswith("INBI") or v.startswith("IND"):
        cat = "OTHER"
    elif v[:3] == "INA":
        cat = "IA"
    elif v[:3] == "INH":
        cat = "RA"
    elif v[:3] in ("INZ", "INB", "INF", "INE"):
        cat = "BROKER"
    elif v[:3] == "INP":
        cat = "PMS"
    elif v[:3] == "INM":
        cat = "MB"
    elif v[:3] == "INR":
        cat = "RTA"
    else:
        cat = "OTHER"
    return {"category": cat}


_PAN_HOLDER = {
    "P": "individual",
    "C": "company",
    "H": "huf",
    "F": "firm",
    "A": "aop",
    "T": "trust",
    "B": "boi",
    "L": "local_authority",
    "J": "ajp",
    "G": "government",
}


def pan_holder_type(value: str) -> dict:
    return {"holder_type": _PAN_HOLDER.get(value[3:4], "unknown")}


_PROMO_140 = re.compile(r"^140\d{7}$")
_SERVICE_1600 = re.compile(r"^160[01]\d{6}$")
_TOLLFREE = re.compile(r"^1800\d{6,7}$")
_UAN_1860 = re.compile(r"^1860\d{6,7}$")


def phone_series(value: str) -> dict:
    digits = re.sub(r"\D", "", value)
    core = digits[2:] if digits.startswith("91") and len(digits) > 10 else digits
    if value.startswith("+") and not value.startswith("+91"):
        import phonenumbers

        try:
            cc = phonenumbers.parse(value).country_code
        except phonenumbers.NumberParseException:
            cc = None
        return {"series": "foreign", "country_code": cc}
    if len(digits) <= 6:
        return {"series": "short", "country_code": 91}
    if _PROMO_140.match(core):
        return {"series": "promo_140", "country_code": 91}
    if _SERVICE_1600.match(core):
        return {"series": "service_1600", "country_code": 91}
    if _TOLLFREE.match(core):
        return {"series": "tollfree", "country_code": 91}
    if _UAN_1860.match(core):
        return {"series": "uan_1860", "country_code": 91}
    series = "mobile" if re.match(r"^[6-9]\d{9}$", core) else "fixed"
    return {"series": series, "country_code": 91}


def tg_kind(value: str) -> dict:
    path = value.split("t.me/", 1)[-1]
    if path.lower().startswith("joinchat/"):
        kind = "invite"
    elif path.startswith("+"):
        kind = "phone" if path[1:].isdigit() else "invite"
    else:
        kind = "username"
    return {"kind": kind}


def platform(value: str) -> dict:
    return {"platform": value.split(":", 1)[0]}


def host(value: str) -> dict:
    return {"host": urlsplit(value).netloc.split("@")[-1].split(":")[0]}


DERIVERS: dict[str, object] = {
    "psp_handle": psp_handle,
    "sebi_valid": sebi_valid,
    "reg_category": reg_category,
    "pan_holder_type": pan_holder_type,
    "phone_series": phone_series,
    "tg_kind": tg_kind,
    "platform": platform,
    "host": host,
}
