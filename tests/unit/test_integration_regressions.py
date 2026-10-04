"""Regression tests for bugs found while integrating the workstreams."""

import pytest

from satark.config import Settings
from satark.harness.orchestrator import CheckInput


async def _run(rt, text: str, lang: str = "en") -> tuple[set[str], dict]:
    h = await rt.orchestrator.start_check(CheckInput(text=text, lang=lang, client="test"))
    codes, verdict = set(), {}
    async for ev in rt.bus.subscribe(h.run_id):
        if ev.type == "check_result":
            codes.update(ev.data["signals"])
        elif ev.type == "verdict":
            verdict = ev.data
    return codes, verdict


@pytest.fixture()
async def rt(fixture_db_path):
    from satark.harness.runtime import build_runtime, close_runtime

    runtime = await build_runtime(Settings.from_env(db_path=fixture_db_path, network=False, env={}))
    yield runtime
    await close_runtime(runtime)


async def test_cached_checker_does_not_leak_between_cases(rt):
    """message.text has no content hash; a result cached under its per-case id leaked into the next case."""
    clean, _ = await _run(rt, "Your SIP of Rs 5,000 is due on 5 Oct.")
    assert "DEBARRED_ENTITY" not in clean
    debarred, verdict = await _run(rt, "Pump Masters Private Limited ka tip: operator wala stock, upper circuit lagega")
    assert "DEBARRED_ENTITY" in debarred and verdict["level"] == "HIGH_RISK"


async def test_hindi_with_and_without_nukta_match_the_same(rt):
    with_nukta, _ = await _run(rt, "रोज़ाना 3% मुनाफ़ा पक्का। आज ही जुड़ें।", "hi")
    without, _ = await _run(rt, "रोजाना 3% मुनाफा पक्का। आज ही जुड़ें।", "hi")
    assert {"GUARANTEED_RETURN", "URGENCY"} <= with_nukta
    assert with_nukta == without


async def test_lexicon_pattern_with_its_own_negator_still_fires(rt):
    codes, _ = await _run(rt, "Humari scheme mein paisa daaliye, loss nahi hoga, fixed return milega", "hi")
    assert "GUARANTEED_RETURN" in codes


async def test_bank_warning_with_negation_does_not_fire(rt):
    codes, verdict = await _run(rt, "Never share your OTP or PIN with anyone. OTP kisi ko mat batao. - Example Bank")
    assert "OTP_REQUEST" not in codes and verdict["level"] == "NO_SIGNS"


async def test_verdict_prefills_simulator_s2_with_the_promised_rate(rt):
    _, verdict = await _run(rt, "Guaranteed 5% daily profit, join our VIP group today")
    assert verdict["simulator"] == "S2"
    assert verdict["sim_params"] == {"rate": 5.0, "period": "day"}


async def test_real_registry_number_under_another_name_is_caught(rt):
    """'Reg. No.' used to split the sentence, so the self-introduced name was never linked to the number."""
    text = ("Hello, I am Suresh Mehta, SEBI Registered Research Analyst (Reg. No. INH000000002). "
            "Join my VIP group for sure-shot calls.")
    codes, verdict = await _run(rt, text)
    assert "REG_NAME_MISMATCH" in codes
    assert verdict["level"] == "HIGH_RISK" and verdict["confidence"] == "SURE"


def test_faq_matches_questions_by_content_words():
    """'What is a SIP?' missed the FAQ phrase 'what is sip' (QA journey 6)."""
    import json

    from satark.config import ROOT
    from satark.harness.respond import _faq_intent

    faq = json.loads((ROOT / "content" / "faq.json").read_text(encoding="utf-8"))
    assert _faq_intent(faq, "What is a SIP?")["id"] == "learn_sip"
    assert _faq_intent(faq, "एसआईपी क्या होता है?")["id"] == "learn_sip"
    assert _faq_intent(faq, "gossip about the market") is None  # whole words only


async def test_screenshot_is_not_sent_to_the_model_unless_vision_is_allowed(fixture_db_path):
    """Security review: a screenshot can show the user's own Aadhaar or bank app; by default only masked OCR
    text may reach a model. SATARK_LLM_VISION=1 opts in (for a local model)."""
    from pydantic_ai.models.function import AgentInfo, FunctionModel

    from satark.harness.runtime import build_runtime, close_runtime

    seen_images = []

    def model(messages, info: AgentInfo):
        for m in messages:
            for part in getattr(m, "parts", []):
                content = getattr(part, "content", None)
                if isinstance(content, list) and any(type(c).__name__ == "BinaryContent" for c in content):
                    seen_images.append(True)
        raise RuntimeError("stop here: the test only records what was sent")

    for vision, expect_image in (("", False), ("1", True)):
        seen_images.clear()
        rt = await build_runtime(Settings.from_env(db_path=fixture_db_path, network=False, env={"SATARK_LLM_VISION": vision}))
        rt.router.override("extract", FunctionModel(model))
        h = await rt.orchestrator.start_check(CheckInput(image=b"\x89PNG\r\n\x1a\n" + b"0" * 64, image_mime="image/png", lang="en"))
        async for _ in rt.bus.subscribe(h.run_id):
            pass
        await close_runtime(rt)
        assert bool(seen_images) is expect_image


async def test_brand_name_under_another_suffix_is_not_called_a_lookalike(rt):
    """Code review: zerodha.in / groww.com were flagged DOMAIN_LOOKALIKE only for a different suffix."""
    same_name, _ = await _run(rt, "Visit https://groww.com/markets for the latest NAVs.")
    assert "DOMAIN_LOOKALIKE" not in same_name
    imitation, _ = await _run(rt, "Download the update from https://zerodha-support.in/app.apk now")
    assert "DOMAIN_LOOKALIKE" in imitation


def test_values_beyond_the_per_type_cap_are_still_masked(config):
    """Code review: max_per_case dropped the 4th OTP before masking, leaving it in masked_text."""
    from satark.harness.extract import ExtractorPipeline
    from satark.harness.state import CaseState

    case = CaseState(case_id="cap")
    otps = ["482913", "591024", "773311", "990088", "123987"]
    ExtractorPipeline(config).regex(case, " ".join(f"OTP {o}." for o in otps))
    assert not any(o in case.masked_text for o in otps)
    msg = case.by_type("message.text")[0].value.get_secret_value()
    assert not any(o in msg for o in otps)


async def test_planner_checks_only_the_first_n_of_a_type(rt):
    """Masking covers everything; the planner still caps how many links are checked (max_per_case)."""
    links = " ".join(f"https://site{i}-example.com/x" for i in range(9))
    h = await rt.orchestrator.start_check(CheckInput(text=f"Invest here: {links}", lang="en"))
    url_steps = set()
    async for ev in rt.bus.subscribe(h.run_id):
        if ev.type == "plan":
            url_steps = {s["id"] for s in ev.data["steps"] if s["checker_id"] == "link.google_hosted"}
    assert 0 < len(url_steps) <= 5


@pytest.mark.parametrize("text, lang", [
    ("SEBI Investor Awareness: Beware of unregistered advisors promising 'guaranteed returns' or 'double your money "
     "in 30 days'. Verify any advisor's registration on sebi.gov.in before investing.", "en"),
    ("निवेशक सावधानी: जो लोग कहें कि \"गारंटीड रिटर्न\" मिलेगा, उनसे सावधान रहें। - सेबी निवेशक जागरूकता", "hi"),
    ("Allotment is as per SEBI's standard lottery process for retail investors, not guaranteed.", "en"),
    ("याद रखें, असली रिटर्न मार्केट पर निर्भर करता है, कोई गारंटी नहीं होती।", "hi"),
    ("पोस्ट ऑफिस की टाइम डिपॉजिट स्कीम पूरी तरह से सरकार द्वारा गारंटीड है।", "hi"),
    ("Market Update: Nifty falls 3% today amid global sell-off.", "en"),
])
async def test_warnings_negations_and_genuine_guarantees_are_not_flagged(rt, text, lang):
    """Blind sets 1-2: awareness posts, 'not guaranteed', government-backed deposits and market news."""
    _, verdict = await _run(rt, text, lang)
    assert verdict["level"] in ("NO_SIGNS", "UNKNOWN"), verdict


@pytest.mark.parametrize("text, code", [
    ("To avoid any data loss please install AnyDesk from the Play Store and share the 9-digit code.", "REMOTE_ACCESS_REQUEST"),
    ("Stake USDT and earn 1.5% DAILY garunteed. Register now: cryptovault-stake.xyz", "GUARANTEED_RETURN"),
    ("A parcel booked under your Aadhaar with illegal drugs was seized by customs. Press 1 to speak to an officer.", "DIGITAL_ARREST"),
    ("हमारी साइबर रिकवरी टीम आपका पैसा वापस दिला सकती है, केस शुरू करने के लिए ₹५,000 एडवांस फीस लगेगी।", "ADVANCE_FEE"),
])
async def test_blind_set_misses_are_caught(rt, text, code):
    codes, verdict = await _run(rt, text, "hi" if any("ऀ" <= ch <= "ॿ" for ch in text) else "en")
    assert code in codes and verdict["level"] in ("HIGH_RISK", "SUSPICIOUS"), (codes, verdict["level"])
