"""mask/unmask/brief/pii_leaks/check_output/is_advice_seeking (CONTRACTS §4, LLD §6.2, §6.4-6.5)."""

from __future__ import annotations

import json

from satark.harness import guards
from satark.harness.extract.fns import VALIDATORS
from satark.harness.extract.pipeline import ExtractorPipeline
from satark.harness.state import Evidence, Reason, Verdict

# ---------------------------------------------------------------------------------------- masking


def test_mask_replaces_every_u_and_c_value(config, make_case):
    pipe = ExtractorPipeline(config)
    case = make_case()
    pipe.regex(case, "pay scammer@ybl, otp is 482913, aadhaar 234123412346 shared")
    out = guards.mask("pay scammer@ybl, otp is 482913, aadhaar 234123412346 shared", case)
    assert "scammer@ybl" not in out
    assert "482913" not in out
    assert "234123412346" not in out
    assert "[UPI_1]" in out


def test_u_values_never_stored(config, make_case):
    pipe = ExtractorPipeline(config)
    case = make_case()
    pipe.regex(case, "aadhaar 234123412346 shared, otp 482913 too")
    for e in case.entities:
        if e.cls == "U":
            assert e.value.get_secret_value() == ""
            assert e.display == ""


def test_mask_catches_fresh_u_identifier_not_yet_in_case(config, make_case):
    """A chat message may carry a brand-new OTP the earlier regex() pass never saw."""
    case = make_case()
    out = guards.mask("my new otp is 773400 for this login", case)
    assert "773400" not in out
    assert any(e.type == "otp" for e in case.entities)  # mask() adds it so later refs dedupe


def test_mask_is_idempotent_and_reuses_placeholder(config, make_case):
    pipe = ExtractorPipeline(config)
    case = make_case()
    pipe.regex(case, "pay scammer@ybl now")
    once = guards.mask("pay scammer@ybl now", case)
    twice = guards.mask(once, case)
    assert once == twice  # already-masked text is left alone


def test_unmask_restores_c_and_hides_u(config, make_case):
    pipe = ExtractorPipeline(config)
    case = make_case()
    pipe.regex(case, "pay scammer@ybl, otp is 482913")
    masked = case.masked_text
    restored = guards.unmask(masked, case, lang="en")
    assert "scammer@ybl" in restored
    assert "(hidden)" in restored
    assert "482913" not in restored


def test_unmask_hindi_hidden_text(config, make_case):
    pipe = ExtractorPipeline(config)
    case = make_case()
    pipe.regex(case, "otp is 482913")
    restored = guards.unmask(case.masked_text, case, lang="hi")
    assert "छिपाया गया" in restored


def test_unmask_leaves_unknown_placeholder_as_is(config, make_case):
    case = make_case()
    assert guards.unmask("see [UPI_99] here", case) == "see [UPI_99] here"


# ------------------------------------------------------------------------------------------ brief


def test_brief_never_contains_raw_value_or_display(config, make_case):
    pipe = ExtractorPipeline(config)
    case = make_case()
    pipe.regex(case, "pay scammer@ybl now, call 9876543210")
    out = guards.brief(case, "extract", config)
    assert "scammer@ybl" not in out
    assert "9876543210" not in out
    data = json.loads(out)
    assert "<untrusted_message>" in data["masked_text"]
    assert all("value" not in e and "display" not in e for e in data["entities"])


def test_brief_drops_raw_suffixed_facts_and_masks_remaining_strings(config, make_case):
    pipe = ExtractorPipeline(config)
    case = make_case()
    pipe.regex(case, "pay scammer@ybl now")
    vpa = next(e for e in case.entities if e.type == "upi.vpa")
    case.ledger.append(
        Evidence(
            id="ev1", step_id="s1", checker_id="upi.valid_handle", family="payment",
            entity_ids=[vpa.id], status="hit",
            facts={"bank_raw": "Yes Bank internal note", "note": "seen as scammer@ybl before"},
        )
    )
    out = json.loads(guards.brief(case, "explain", config))
    fact_keys = out["evidence"][0]["facts"]
    assert "bank_raw" not in fact_keys
    assert "scammer@ybl" not in out["evidence"][0]["facts"]["note"]


def test_brief_includes_verdict_titles_in_case_lang(config, make_case):
    case = make_case(lang="hi")
    case.verdict = Verdict(level="HIGH_RISK", confidence="SURE", reasons=[Reason(code="REG_NOT_FOUND", weight="high", basis="registry")])
    out = json.loads(guards.brief(case, "explain", config))
    assert out["verdict"]["level"] == "HIGH_RISK"
    assert out["verdict"]["reasons"][0]["code"] == "REG_NOT_FOUND"
    assert out["verdict"]["reasons"][0]["title"]  # a real sentence, not the bare code


# ------------------------------------------------------------------------------------ pii tripwire

RAW_IDENTIFIERS = [
    ("aadhaar", "mera aadhaar {v} hai", "234123412346"),
    ("aadhaar2", "aadhaar number {v} verify karo", "345123678916"),
    ("card", "card number {v} charged", "4111111111111111"),
    ("card2", "card {v} was used today", "4532015112830366"),
    ("card3", "visa test card {v} here", "4916338506082832"),
    ("otp1", "your otp is {v} valid 10 min", "482913"),
    ("otp2", "OTP: {v} for login", "773400"),
    ("otp3", "ओटीपी {v} है", "556611"),
    ("pan1", "pan is {v} for kyc", "ABCPE1234F"),
    ("pan2", "PAN: {v} filed", "AAACP1234Q"),
    ("phone1", "call {v} now", "9876543210"),
    ("phone2", "contact +91 {v}", "9988776655"),
    ("phone3", "whatsapp {v} for help", "9123456780"),
    ("upi1", "pay {v} now", "scammer.vip@ybl"),
    ("upi2", "send to {v} today", "fraud123@paytm"),
    ("upi3", "upi id {v} confirmed", "ramesh.kumar@okaxis"),
    ("account1", "a/c {v} for neft", "123456789012"),
    ("account2", "account no {v} linked", "987654321098"),
    ("ifsc1", "ifsc {v} branch", "SBIN0001234"),
    ("ifsc2", "ifsc: {v} transfer", "HDFC0000123"),
    ("boid1", "demat boid {v} linked", "1234567890123456"),
    ("boid2", "client id {v} for demat", "IN30012345678901"),
    ("email1", "mail {v} now", "rajesh.sharma@gmail.com"),
    ("email2", "contact {v} today", "support.help@outlook.com"),
    ("reg1", "adviser INA000099999 reg {v} check", "INA000099999"),
    ("reg2", "broker code {v} verified", "INZ000099999"),
    ("url1", "visit {v} now", "fakebroker-example.xyz/login"),
    ("btc1", "send to {v} wallet", "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"),
    ("tron1", "usdt to {v} address", "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"),
    ("name1", "Dear Suresh ji, your KYC is due", "Suresh"),
]


def test_pii_tripwire_30_identifiers_never_leak(config, make_case):
    assert len(RAW_IDENTIFIERS) >= 30
    pipe = ExtractorPipeline(config)
    case = make_case()
    for _key, template, value in RAW_IDENTIFIERS:
        pipe.regex(case, template.format(v=value))
    brief_text = guards.brief(case, "explain", config)
    for _key, _template, value in RAW_IDENTIFIERS:
        assert value not in brief_text, f"{_key} leaked into the brief: {value!r}"
    assert guards.pii_leaks(brief_text, case) == []


def test_pii_leaks_detects_fresh_regex_identifier_in_a_prompt(config, make_case):
    case = make_case()
    leaks = guards.pii_leaks("please confirm aadhaar 234123412346 now", case)
    assert "aadhaar" in leaks


def test_pii_leaks_returns_type_names_never_values(config, make_case):
    pipe = ExtractorPipeline(config)
    case = make_case()
    pipe.regex(case, "pay scammer@ybl now")
    vpa_value = case.entities[0].value.get_secret_value()
    leaks = guards.pii_leaks(f"the prompt accidentally includes {vpa_value}", case)
    assert leaks == ["upi.vpa"]
    assert vpa_value not in leaks


def test_pii_leaks_does_not_flag_p_class_values(config, make_case):
    """Regression (integration bug report): "Guaranteed 5% daily profit" tripped the tripwire
    on money.return_rate and blocked every extract call. P-class (amounts, rates, IFSC) is
    never masked for LLMs in the first place (CONTRACTS §4) and must never count as a leak."""
    pipe = ExtractorPipeline(config)
    case = make_case()
    pipe.regex(case, "Guaranteed 5% daily profit, pay Rs 10,000 to IFSC SBIN0001234")
    assert {e.type for e in case.entities} >= {"money.return_rate", "money.inr", "bank.ifsc"}
    prompt = guards.brief(case, "extract", config)
    assert guards.pii_leaks(prompt, case) == []


def test_pii_leaks_message_text_value_is_not_a_leak_source(config, make_case):
    """message.text's own (mostly-raw) value must never itself be treated as a leak: its
    content is already represented by masked_text, which is what actually goes in prompts."""
    pipe = ExtractorPipeline(config)
    case = make_case()
    pipe.regex(case, "Guaranteed 5% daily profit, totally safe scheme")
    msg_value = next(e for e in case.entities if e.type == "message.text").value.get_secret_value()
    assert guards.pii_leaks(msg_value, case) == []


# --------------------------------------------------------------------------------- check_output


def test_check_output_catches_tips_english_hindi_hinglish(config, make_case):
    case = make_case()
    assert "no_tips" in guards.check_output("You should buy this stock now", case, config, "en")
    assert "no_tips" in guards.check_output("Target price is ₹500, book profit", case, config, "en")
    assert "no_tips" in guards.check_output("खरीद लो यह शेयर अभी", case, config, "hi")
    assert "no_tips" in guards.check_output("stock mein le lo, target bhi set hai", case, config, "en")


def test_check_output_bare_buy_sell_invest_passes(config, make_case):
    case = make_case()
    problems = guards.check_output("Never buy shares because of a tip from a stranger.", case, config, "en")
    assert "no_tips" not in problems


def test_check_output_rejects_code_markup(config, make_case):
    case = make_case()
    problems = guards.check_output("Here is code: ```print(1)```", case, config, "en")
    assert "code_markup" in problems


def test_check_output_grounding_catches_ungrounded_reg_number(config, make_case):
    case = make_case()
    problems = guards.check_output("This adviser's number INA000099999 was not found.", case, config, "en")
    assert "grounding" in problems


def test_check_output_grounding_passes_for_known_reg_number(config, make_case):
    pipe = ExtractorPipeline(config)
    case = make_case()
    pipe.regex(case, "adviser INA000012345 claims registration")
    problems = guards.check_output("The number INA000012345 was not found on the register.", case, config, "en")
    assert "grounding" not in problems


def test_check_output_grounding_catches_invented_placeholder(config, make_case):
    case = make_case()
    problems = guards.check_output("We checked [REG_7] and it is clean.", case, config, "en")
    assert "grounding" in problems


def test_check_output_forbidden_affirmations(config, make_case):
    case = make_case()
    assert "affirmation" in guards.check_output("Yeh safe hai, you can proceed.", case, config, "en")
    assert "affirmation" in guards.check_output("This is safe to use.", case, config, "en")
    assert "affirmation" in guards.check_output("यह असली है, भरोसा करें।", case, config, "hi")


def test_check_output_script_check(config, make_case):
    case = make_case()
    clean_hindi = "हमें कोई मजबूत खतरे का संकेत नहीं मिला। सावधानी बरतें।"
    assert guards.check_output(clean_hindi, case, config, "hi") == []
    latin_for_hindi = "We found no strong risk signs. Please stay careful."
    assert "script" in guards.check_output(latin_for_hindi, case, config, "hi")


def test_check_output_length(config, make_case):
    case = make_case()
    long_text = " ".join(["word"] * 91)
    assert "length" in guards.check_output(long_text, case, config, "en", max_words=90)


def test_check_output_codes_mismatch(config, make_case):
    case = make_case()
    text = "We found REG_NOT_FOUND as the reason."
    assert "codes_mismatch" in guards.check_output(text, case, config, "en", expected_codes=["DOMAIN_YOUNG"])
    assert "codes_mismatch" not in guards.check_output(text, case, config, "en", expected_codes=["REG_NOT_FOUND"])
    assert "codes_mismatch" not in guards.check_output(text, case, config, "en", expected_codes=None)


# ------------------------------------------------------------------------------- is_advice_seeking


def test_is_advice_seeking_true_cases():
    assert guards.is_advice_seeking("which stock should I buy today?")
    assert guards.is_advice_seeking("kaunsa share lu abhi?") or guards.is_advice_seeking("konsa share lu abhi?")
    assert guards.is_advice_seeking("कौन सा शेयर खरीदूं?")
    assert guards.is_advice_seeking("what is the target price for this?")


def test_is_advice_seeking_false_for_verification_questions():
    assert not guards.is_advice_seeking("is this adviser genuine?")
    assert not guards.is_advice_seeking("how do I check if this is registered with SEBI?")
    assert not guards.is_advice_seeking("यह असली है या नकली?")


def test_verhoeff_sanity_for_pii_fixtures():
    # guards against the golden fixtures silently drifting onto an invalid checksum
    assert VALIDATORS["verhoeff"]("234123412346") is True
    assert VALIDATORS["verhoeff"]("345123678916") is True
