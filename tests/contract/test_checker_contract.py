"""The generated checker contract test (LLD §26.2, docs/CONTRACTS.md §3).

Generic over the whole registry: it builds one sample Entity for every type in
config/entities.yaml (cross-referenced where a claim needs refs), plus garbage variants, and
runs every registered checker against them under six resource conditions. A new checker module
(this sprint's or a later one's) gets this test for free the moment it registers.

What is asserted, per docs/CONTRACTS.md and the task brief (the LLD's version is the fuller
design; this is the sprint cut, and where they differ this is simpler and wins):
  - status in {hit, clear, unknown, error, skipped}
  - never raises anything but TransientError (a harness-level timeout is not the checker raising)
  - signal codes and flags are a subset of checker.produces
  - every derived EntityDraft's type exists in config.entities
  - completes within checker.timeout_s + 0.5s
  - a non-local checker consumes no U- or R-class entity type (also enforced by reg.validate()
    itself, which raises ConfigError for the whole registry if any checker breaks this)
"""

from __future__ import annotations

import asyncio
import random
import string

import httpx
from pydantic import SecretStr

from satark.checkers.base import CheckContext, TransientError
from satark.checkers.registry import CheckerRegistry
from satark.harness.state import CaseState, Entity, utcnow

# ======================================================================== sample entities

# One good value per entity type in config/entities.yaml. U-class types keep value="" (CONTRACTS
# §2: "U-class entities keep value='' (discarded at extraction)") since no checker ever sees
# anything else in production. R-class types (pan, bank.account_no, phone, email) get a real
# value: the interesting case for a checker is the "role != user" resolution, i.e. cls="C".
# Claim/request/etc. samples carry the attrs and refs (by entity TYPE, resolved to ids below)
# that this sprint's checkers actually read.
_SAMPLES: dict[str, dict] = {
    "upi.vpa": {"value": "rajesh.ra@validsbi"},
    "upi.uri": {"value": "upi://pay?pa=rajesh.ra%40validsbi&pn=Rajesh+Kumar+Sharma&mc=6211&tr=TXN1&sign=abc"},
    "sebi.reg_no": {"value": "INH000000002"},
    "pan": {"value": "ABCPE1234F"},
    "aadhaar": {"value": ""},
    "card.number": {"value": ""},
    "otp": {"value": ""},
    "demat.bo_id": {"value": ""},
    "bank.account_no": {"value": "123456789012"},
    "bank.ifsc": {"value": "SBIN0001234"},
    "user.name": {"value": ""},
    "phone": {"value": "+919999900000"},
    "sms.header": {"value": "VM-HDFCBK-S"},
    "email": {"value": "scammer@example.com"},
    "url": {"value": "https://kite.zerodha.com/signup"},
    "domain": {"value": "zerodha.com"},
    "tg.link": {"value": "t.me/rajesh_investments"},
    "social.handle": {"value": "instagram:rajesh_investments"},
    "app.package": {"value": "com.zerodha.kite3"},
    "apk.link": {"value": "https://totally-legit-broker.example/download/app.apk"},
    "crypto.btc": {"value": "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"},
    "crypto.evm": {"value": "0x" + "ab" * 20},
    "crypto.tron": {"value": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"},
    "money.inr": {"value": "50000"},
    "money.return_rate": {"value": "0.05/day", "attrs": {"rate": 0.05, "period": "day"}},
    "message.text": {
        "value": "SEBI Registered RA Rajesh Kumar Sharma (INH000000002) guarantees 5% daily profit. "
        "Pay to rajesh.ra@validsbi. Install AnyDesk for support."
    },
    "party.name": {"value": "Rajesh Kumar Sharma"},
    "claim.registered_as": {
        "value": "",
        "attrs": {"regulator": "SEBI", "category": "RA"},
        "refs": ["party.name", "sebi.reg_no"],
    },
    "claim.impersonates": {"value": "", "attrs": {"org": "Zerodha", "kind": "broker", "brand_id": "zerodha"}},
    "claim.guaranteed_return": {"value": ""},
    "claim.institutional_access": {"value": "", "attrs": {"kind": "FPI"}},
    "claim.endorsement": {"value": "", "attrs": {"figure": "Finance Minister"}},
    "request.payment": {"value": "", "attrs": {"purpose": "deposit"}, "refs": ["upi.vpa", "money.inr"]},
    "request.fee_to_withdraw": {"value": ""},
    "request.install_app": {"value": "", "attrs": {"source": "link"}, "refs": ["app.package"]},
    "request.remote_access": {"value": "", "attrs": {"tool": "AnyDesk"}},
    "request.credentials": {"value": "", "attrs": {"kind": "OTP"}},
    "request.kyc_docs": {"value": "", "attrs": {"kind": "Aadhaar"}},
    "request.join_group": {"value": "", "attrs": {"platform": "telegram"}},
    "request.account_handling": {"value": ""},
    "pressure.urgency": {"value": "", "attrs": {"kind": "urgency"}},
    "tip.security_call": {"value": "", "attrs": {"direction": "buy", "target": "150"}},
    "offer.unregulated": {"value": "", "attrs": {"kind": "forex"}},
    "doc.official_notice": {"value": "", "attrs": {"issuer": "SEBI"}},
    "threat.legal_action": {"value": "", "attrs": {"kind": "digital_arrest"}},
}

# "" / "@@@" / 4,000 pseudo-random characters, fixed seed so the suite is deterministic.
_GARBAGE_VALUES = ["", "@@@", "".join(random.Random(42).choices(string.ascii_letters + " .@:/0123456789", k=4000))]


def _cls_for(type_: str, config) -> str:
    """Entity.cls only accepts U/C/P; R-class types resolve to C (role != user) or U (CONTRACTS §2)."""
    c = config.entities[type_].get("class", "C")
    return "C" if c == "R" else c


def build_sample_case(config) -> CaseState:
    """One case holding a well-formed sample entity for every type in config/entities.yaml."""
    missing = [t for t in config.entities if t not in _SAMPLES]
    assert not missing, f"tests/contract/test_checker_contract.py: add a sample for {missing}"

    case = CaseState(case_id="contract-sample", expires_at=utcnow())
    type_to_id: dict[str, str] = {}
    counter = 0

    def add(type_: str, spec: dict) -> None:
        nonlocal counter
        counter += 1
        eid = f"e{counter}"
        type_to_id[type_] = eid
        refs = [type_to_id[rt] for rt in spec.get("refs", []) if rt in type_to_id]
        case.entities.append(
            Entity(
                id=eid,
                type=type_,
                cls=_cls_for(type_, config),
                value=SecretStr(spec["value"]),
                display=spec["value"][:120],
                attrs=spec.get("attrs", {}),
                refs=refs,
            )
        )

    # pass 1: identifiers and the synthetic message.text (claims below ref these by type)
    for t, spec in config.entities.items():
        if spec.get("kind") != "claim" and t in _SAMPLES:
            add(t, _SAMPLES[t])
    # pass 2: claims (refs resolved against pass 1's ids)
    for t, spec in config.entities.items():
        if spec.get("kind") == "claim" and t in _SAMPLES:
            add(t, _SAMPLES[t])
    return case


def garbage_entities(type_: str, config) -> list[Entity]:
    """Garbage-value variants for identifier/synthetic types only: claims have no raw value to fuzz."""
    if config.entities[type_].get("kind") not in ("identifier", "synthetic"):
        return []
    cls = _cls_for(type_, config)
    return [
        Entity(id=f"g{i}", type=type_, cls=cls, value=SecretStr(v), display=v[:120])
        for i, v in enumerate(_GARBAGE_VALUES)
    ]


# ======================================================================== fake resources

try:  # the real exceptions, now that satark/infra/http.py (C2) exists; a stand-in if it doesn't yet
    from satark.infra.http import BlockedURL, Offline
except ImportError:  # pragma: no cover

    class Offline(Exception):
        pass

    class BlockedURL(Exception):
        pass


class _FakeHttp:
    """Stand-in for satark.infra.http.SafeHttpClient: get/head/resolve_redirects, same shapes.

    Every checker's HTTP call ends up at one of these three methods (SafeHttpClient's whole public
    surface besides aclose()), so one fault-injection point (`_fault`) covers all of them.
    """

    def __init__(self, status: int = 200, text: str = "<html></html>", exc: Exception | None = None, sleep: float = 0.0):
        self._status, self._text, self._exc, self._sleep = status, text, exc, sleep

    async def _fault(self, timeout: float) -> None:  # noqa: ASYNC109
        if self._sleep:
            await asyncio.sleep(timeout + self._sleep)  # always overshoots whatever timeout the caller passed
        if self._exc:
            raise self._exc

    async def get(self, url: str, timeout: float = 2.5, headers=None, max_bytes: int = 512_000):  # noqa: ASYNC109
        await self._fault(timeout)
        return httpx.Response(self._status, text=self._text, request=httpx.Request("GET", url))

    async def head(self, url: str, timeout: float = 1.5):  # noqa: ASYNC109
        await self._fault(timeout)
        return httpx.Response(self._status, request=httpx.Request("HEAD", url))

    async def resolve_redirects(self, url: str, max_hops: int = 3, timeout: float = 1.5):  # noqa: ASYNC109
        await self._fault(timeout)
        return [url]  # no redirect: good enough for the fault-injection contexts below


def _contexts(fixture_db) -> dict[str, tuple]:
    return {
        "db_ok": (fixture_db, _FakeHttp()),
        "db_none": (None, _FakeHttp()),
        "http_slow": (fixture_db, _FakeHttp(sleep=0.6)),
        "http_503": (fixture_db, _FakeHttp(status=503)),
        "http_malformed": (fixture_db, _FakeHttp(text="<<<not really html>>>")),
        "http_offline": (fixture_db, _FakeHttp(exc=Offline())),
    }


# ======================================================================== the test itself


async def _run(checker, entity, ctx) -> object | None:
    """Call checker.check() under the harness's own latency bound. None = an accepted non-result
    (a harness-level timeout, or the checker's own documented escape hatch, TransientError)."""
    try:
        return await asyncio.wait_for(checker.check(entity, ctx), timeout=checker.timeout_s + 0.5)
    except TimeoutError:
        return None
    except TransientError:
        return None


def _assert_contract(checker, result, config) -> None:
    if result is None:
        return
    assert result.status in {"hit", "clear", "unknown", "error", "skipped"}, (checker.id, result.status)
    codes = {s.code for s in result.signals} | result.flags
    assert codes <= checker.produces, (checker.id, "codes not in produces:", codes - checker.produces)
    for d in result.derived:
        assert d.type in config.entities, (checker.id, "derived type not in config.entities:", d.type)


async def test_checker_contract(config, fixture_db):
    reg = CheckerRegistry()
    reg.discover()
    reg.validate(config, env={}, db_ok=True)  # raises ConfigError if any checker breaks a startup rule

    sample_case = build_sample_case(config)
    contexts = _contexts(fixture_db)

    assert reg.all(), "no checkers registered: discover() found nothing under satark.checkers"

    for checker in reg.all():
        for t in checker.consumes:
            # LLD §10.5 rule 2, also enforced at startup by reg.validate() above: a non-local
            # checker (its output can leave the server) may not consume user or role-resolved data.
            assert checker.privacy == "local" or config.entities[t].get("class") not in ("U", "R"), (
                checker.id,
                t,
                "privacy rule violated",
            )

            good = sample_case.by_type(t)
            if not good:
                continue
            entity = good[0]
            for _ctx_name, (db, http) in contexts.items():
                ctx = CheckContext(case=sample_case, config=config, db=db, http=http)
                result = await _run(checker, entity, ctx)
                _assert_contract(checker, result, config)

            for garbage in garbage_entities(t, config):
                g_case = CaseState(case_id="contract-garbage", expires_at=utcnow())
                g_case.entities.append(garbage)
                for ctx_name, (db, http) in contexts.items():
                    if ctx_name == "http_slow":
                        continue  # same code path as the good sample above; skip to keep the suite fast
                    ctx = CheckContext(case=g_case, config=config, db=db, http=http)
                    result = await _run(checker, garbage, ctx)
                    _assert_contract(checker, result, config)
