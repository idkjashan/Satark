"""ExtractorPipeline.regex/qr/add_drafts: dedupe, placeholders, masking, overlaps, claims
(CONTRACTS §4, LLD §6.5, §8.6, build step 2)."""

from __future__ import annotations

import time
from datetime import timedelta

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from satark.harness.extract.pipeline import ExtractorPipeline
from satark.harness.state import CaseState, EntityDraft, utcnow

VALID_AADHAAR = "234123412346"  # passes Verhoeff
VALID_UPI = "rajesh.vip@okaxis"


def test_dedupe_repeated_value_reuses_one_entity(config, make_case):
    pipe = ExtractorPipeline(config)
    case = make_case()
    pipe.regex(case, f"pay {VALID_UPI} or {VALID_UPI} again, same id")
    hits = [e for e in case.entities if e.type == "upi.vpa"]
    assert len(hits) == 1
    assert case.masked_text.count(hits[0].placeholder) == 2


def test_placeholders_numbered_per_prefix_in_order(config, make_case):
    pipe = ExtractorPipeline(config)
    case = make_case()
    pipe.regex(case, "pay a@okaxis then b@okaxis then c@okaxis")
    vpas = [e for e in case.entities if e.type == "upi.vpa"]
    assert [e.placeholder for e in vpas] == ["[UPI_1]", "[UPI_2]", "[UPI_3]"]


def test_u_class_value_and_display_discarded(config, make_case):
    pipe = ExtractorPipeline(config)
    case = make_case()
    pipe.regex(case, f"aadhaar {VALID_AADHAAR} shared")
    ent = next(e for e in case.entities if e.type == "aadhaar")
    assert ent.value.get_secret_value() == ""
    assert ent.display == ""
    assert ent.placeholder
    assert ent.norm_hash  # still set, so later repeats dedupe


def test_message_text_masks_u_but_keeps_c_raw(config, make_case):
    pipe = ExtractorPipeline(config)
    case = make_case()
    pipe.regex(case, f"Zerodha support: your otp is 482913, aadhaar {VALID_AADHAAR} needed")
    msg = next(e for e in case.entities if e.type == "message.text")
    text = msg.value.get_secret_value()
    assert "482913" not in text  # otp: U, masked
    assert VALID_AADHAAR not in text  # aadhaar: U, masked
    assert "Zerodha" in text  # ordinary words: kept raw for local text checkers


def test_masked_text_masks_both_u_and_c(config, make_case):
    pipe = ExtractorPipeline(config)
    case = make_case()
    pipe.regex(case, f"pay {VALID_UPI} otp is 482913")
    assert VALID_UPI not in case.masked_text
    assert "482913" not in case.masked_text
    assert "[UPI_1]" in case.masked_text
    assert "[OTP_1]" in case.masked_text


def test_overlap_u_class_wins_over_context_gated_r_class(config, make_case):
    """a/c 234123412346 looks like both a bank.account_no (context "a/c") and an aadhaar
    number; the aadhaar (U, mask more never less) must win, per CONTRACTS overlap rules."""
    pipe = ExtractorPipeline(config)
    case = make_case()
    pipe.regex(case, f"a/c {VALID_AADHAAR} for neft transfer")
    assert any(e.type == "aadhaar" for e in case.entities)
    assert not any(e.type == "bank.account_no" for e in case.entities)


def test_overlap_url_and_embedded_tg_link_both_kept(config, make_case):
    pipe = ExtractorPipeline(config)
    case = make_case()
    pipe.regex(case, "visit https://t.me/bullrun_vip for tips")
    assert any(e.type == "url" for e in case.entities)
    assert any(e.type == "tg.link" for e in case.entities)


def test_max_per_case_never_leaves_a_value_unmasked(config, make_case):
    pipe = ExtractorPipeline(config)
    case = make_case()
    nums = [VALID_AADHAAR, "456789123451", "298765432117", "567812345678"]  # all pass Verhoeff
    text = " and ".join(f"aadhaar {n}" for n in nums)
    pipe.regex(case, text)
    hits = [e for e in case.entities if e.type == "aadhaar"]
    # every user-owned value is masked, even past max_per_case (the planner caps checks, not masking)
    assert len(hits) == 4
    assert not any(n in case.masked_text for n in nums)


def test_entity_domain_derived_and_deduped_across_url_and_email(config, make_case):
    pipe = ExtractorPipeline(config)
    case = make_case()
    pipe.regex(case, "visit https://scam.zerodha-pro.in/login or mail admin@scam.zerodha-pro.in")
    domains = [e for e in case.entities if e.type == "domain"]
    assert len(domains) == 1
    assert domains[0].display == "zerodha-pro.in"


def test_claims_false_skips_deterministic_claims_but_not_identifiers(config, make_case):
    pipe = ExtractorPipeline(config)
    case = make_case()
    pipe.regex(case, "from SEBI: Rajesh Sharma INA000012345 is registered", claims=False)
    assert not any(e.type in ("claim.impersonates", "claim.registered_as", "party.name") for e in case.entities)
    assert any(e.type == "sebi.reg_no" for e in case.entities)


def test_qr_upi_payload_creates_upi_uri(config, make_case):
    pipe = ExtractorPipeline(config)
    case = make_case()
    ents = pipe.qr(case, "upi://pay?pa=scammer@ybl&pn=Scammer&am=5000")
    assert len(ents) == 1
    assert ents[0].type == "upi.uri"


def test_qr_non_upi_payload_falls_back_to_regex(config, make_case):
    pipe = ExtractorPipeline(config)
    case = make_case()
    pipe.qr(case, "https://fakebroker.xyz/pay")
    assert any(e.type == "url" for e in case.entities)


def test_add_drafts_creates_and_dedupes_derived_entities(config, make_case):
    pipe = ExtractorPipeline(config)
    case = make_case()
    drafts = [
        EntityDraft(type="url", value="https://final-destination.example.com/landing"),
        EntityDraft(type="url", value="https://final-destination.example.com/landing"),  # duplicate
    ]
    new = pipe.add_drafts(case, drafts, origin="derived")
    urls = [e for e in case.entities if e.type == "url"]
    assert len(urls) == 1
    assert urls[0].origin == "derived"
    assert len(new) == 2  # the url + its derived domain, once (the 2nd draft deduped away)
    assert any(e.type == "domain" for e in case.entities)


# ------------------------------------------------------------------ golden-set triage regressions


def test_role_hint_matches_devanagari_word_ending_in_a_matra(config, make_case):
    """Regression: Python's \\b breaks right after a Devanagari dependent vowel sign (a matra
    is not \\w), so "\\bमेरा\\b" never matched "मेरा" at all - role_hints must use the Devanagari-
    aware lookaround instead, or every "mera/meri/apna" role hint silently never fires."""
    pipe = ExtractorPipeline(config)
    case = make_case()
    pipe.regex(case, "yeh मेरा phone number hai 9876543210")
    phone = next(e for e in case.entities if e.type == "phone")
    assert phone.role == "user"
    assert phone.cls == "U"  # R + role=user -> U: masked and discarded, not shown to anyone


def test_self_introduction_name_anywhere_in_sentence_with_number(config, make_case):
    pipe = ExtractorPipeline(config)
    case = make_case()
    pipe.regex(case, "Hi, I'm Suresh Mehta, SEBI Registered Research Analyst, registration number INH000000002")
    party = next(e for e in case.entities if e.type == "party.name")
    assert party.display == "Suresh Mehta"
    claim = next(e for e in case.entities if e.type == "claim.registered_as")
    assert claim.attrs["category"] == "RA"
    reg = next(e for e in case.entities if e.type == "sebi.reg_no")
    assert set(claim.refs) == {party.id, reg.id}


def test_registration_claim_without_name_or_number_still_fires(config, make_case):
    """A registration claim without a number is itself the signal; it must not be dropped
    just because no name could be found nearby either."""
    pipe = ExtractorPipeline(config)
    case = make_case()
    pipe.regex(case, "I am a SEBI Registered Investment Adviser with 10 years of experience")
    assert not any(e.type == "party.name" for e in case.entities)
    claim = next(e for e in case.entities if e.type == "claim.registered_as")
    assert claim.attrs == {"regulator": "SEBI", "category": "IA"}
    assert claim.refs == []


@pytest.mark.parametrize(
    "text",
    [
        "Official SEBI Compliance Notice: your account is flagged",
        "This is an official SEBI notice regarding your account",
        "official SEBI communication about your KYC",
        "This is a SEBI officer calling you",
    ],
)
def test_impersonation_triggers_sebi_notice_variants(config, make_case, text):
    pipe = ExtractorPipeline(config)
    case = make_case()
    pipe.regex(case, text)
    claim = next(e for e in case.entities if e.type == "claim.impersonates")
    assert claim.attrs["brand_id"] == "sebi"


def test_impersonation_mention_without_self_presenting_is_not_flagged(config, make_case):
    pipe = ExtractorPipeline(config)
    case = make_case()
    pipe.regex(case, "Zerodha is SEBI registered broker, check on SEBI website")
    assert not any(e.type == "claim.impersonates" for e in case.entities)


def test_impersonation_check_stays_fast(config, make_case):
    """Regression: folding + escaping + compiling ~120 aliases x 9 triggers on every call
    measured at ~60ms before the patterns were precompiled in __init__ - well over the
    <10ms-typical budget (LLD §3.6). Generous margin here since CI machines vary."""
    pipe = ExtractorPipeline(config)
    text = "Guaranteed 10% daily returns, SEBI registered adviser Rajesh Sharma INA000012345 can help " * 3
    t0 = time.perf_counter()
    for _ in range(20):
        case = make_case()
        pipe.regex(case, text)
    elapsed_ms = (time.perf_counter() - t0) / 20 * 1000
    assert elapsed_ms < 25, f"regex() averaged {elapsed_ms:.1f} ms/call, expected well under 10ms typical"


# --------------------------------------------------------------------------------------- fuzzing


@given(
    prefix=st.text(max_size=30),
    middle=st.text(max_size=30),
    suffix=st.text(max_size=30),
)
@settings(max_examples=150, deadline=None)
def test_fuzz_regex_never_raises_and_never_leaks_u_value(config, prefix, middle, suffix):
    # Random digits landing right next to the aadhaar number can make a *longer* U-class
    # match win the overlap (e.g. card.number's loose per-digit separators swallowing a
    # trailing stray digit) - that is still safe (still U, still masked), so the invariants
    # below are type-agnostic: never raise, never leak the raw value, ids unique, no entity
    # duplicated for the same normalised value.
    pipe = ExtractorPipeline(config)
    case = CaseState(case_id="fuzz-case", lang="en", expires_at=utcnow() + timedelta(minutes=30))
    text = f"{prefix} aadhaar {VALID_AADHAAR} {middle} pay {VALID_UPI} {suffix}"
    pipe.regex(case, text)  # must never raise, regardless of the random unicode around it
    assert VALID_AADHAAR not in case.masked_text
    ids = [e.id for e in case.entities]
    assert len(ids) == len(set(ids))
    for e in case.entities:
        if e.cls == "U":
            assert e.value.get_secret_value() == ""
            assert e.display == ""
    seen: set[tuple[str, str]] = set()
    for e in case.entities:
        if e.norm_hash:
            key = (e.type, e.norm_hash)
            assert key not in seen, f"duplicate entity for {key}"
            seen.add(key)
