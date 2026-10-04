"""fns.py: NORMALISERS/VALIDATORS/DERIVERS used by config/entities.yaml (CONTRACTS §4)."""

from __future__ import annotations

import yaml

from satark.config import ROOT
from satark.harness.extract.fns import DERIVERS, NORMALISERS, VALIDATORS

ENTITIES = yaml.safe_load((ROOT / "config" / "entities.yaml").read_text())


def test_every_normalise_name_in_entities_yaml_exists():
    for type_, spec in ENTITIES.items():
        name = spec.get("normalise")
        if name:
            assert name in NORMALISERS, f"{type_}: normalise {name!r} is not in fns.NORMALISERS"


def test_every_validate_name_in_entities_yaml_exists():
    for type_, spec in ENTITIES.items():
        name = spec.get("validate")
        if name:
            assert name in VALIDATORS, f"{type_}: validate {name!r} is not in fns.VALIDATORS"


def test_every_derive_name_in_entities_yaml_exists():
    for type_, spec in ENTITIES.items():
        for name in spec.get("derive") or []:
            if name.startswith("entity:"):
                continue  # handled by the pipeline itself, not a fns.DERIVERS function
            assert name in DERIVERS, f"{type_}: derive {name!r} is not in fns.DERIVERS"


# ------------------------------------------------------------------------------------- normalise


def test_inr_handles_grouping_and_multipliers():
    assert NORMALISERS["inr"]("₹1,00,000") == "100000"
    assert NORMALISERS["inr"]("Rs 5 lakh") == "500000"
    assert NORMALISERS["inr"]("INR 2 crore") == "20000000"
    assert NORMALISERS["inr"]("रु 50000") == "50000"
    assert NORMALISERS["inr"]("Rs 3k") == "3000"


def test_return_rate_value_and_attrs():
    value, attrs = NORMALISERS["return_rate"]("5% daily")
    assert value == "0.05/day"
    assert attrs == {"rate": 0.05, "period": "day"}
    value, attrs = NORMALISERS["return_rate"]("10% per month")
    assert attrs["period"] == "month"
    value, attrs = NORMALISERS["return_rate"]("रोज़ 3%")
    assert attrs["period"] == "day"


def test_return_rate_n_periods_compounds_to_an_equivalent_single_period_rate():
    """"150% in 3 days" / "double in 7 days": a total multiplier reached over n periods,
    converted to the single-period rate total**(1/n) - 1 (golden-set triage examples)."""
    _, attrs = NORMALISERS["return_rate"]("150% in 3 days")
    assert attrs["period"] == "day"
    assert attrs["rate"] == round(2.5 ** (1 / 3) - 1, 4)

    _, attrs = NORMALISERS["return_rate"]("90% returns are guaranteed within a week")
    assert attrs == {"rate": 0.9, "period": "week"}  # n=1 (no "N weeks" given): no root needed

    _, attrs = NORMALISERS["return_rate"]("money double in 7 days")
    assert attrs["period"] == "day"
    assert attrs["rate"] == round(2 ** (1 / 7) - 1, 4)

    _, attrs = NORMALISERS["return_rate"]("paisa double 30 din mein")
    assert attrs["rate"] == round(2 ** (1 / 30) - 1, 4)

    _, attrs = NORMALISERS["return_rate"]("7 दिन में पैसा डबल")
    assert attrs["period"] == "day"
    assert attrs["rate"] == round(2 ** (1 / 7) - 1, 4)  # same claim as "double in 7 days", Hindi word order


def test_url_lowercases_host_and_strips_tracking_params():
    out = NORMALISERS["url"]("HTTP://Tracker.EXAMPLE.com/x?utm_source=fb&fbclid=1&id=7")
    assert out == "http://tracker.example.com/x?id=7"


def test_url_adds_scheme_when_missing():
    assert NORMALISERS["url"]("www.Fake-Broker.XYZ/login").startswith("https://")


def test_tg_lowercases_username_not_invite_hash():
    assert NORMALISERS["tg"]("https://t.me/BullRun_VIP") == "t.me/bullrun_vip"
    assert NORMALISERS["tg"]("t.me/+AbCdEf") == "t.me/+AbCdEf"  # invite hash: case preserved


def test_social_maps_host_to_platform_and_lowercases_handle():
    assert NORMALISERS["social"]("https://twitter.com/KediaCapital") == "x:kediacapital"
    assert NORMALISERS["social"]("facebook.com/Some.Page") == "facebook:some.page"


def test_name_strips_legal_suffixes():
    assert NORMALISERS["name"]("M/s. ABC Research Pvt. Ltd.") == "abc research"


# --------------------------------------------------------------------------------------- validate


def test_upi_vpa_validator():
    assert VALIDATORS["upi_vpa"]("rajesh.vip@okaxis") is True
    assert VALIDATORS["upi_vpa"]("not a vpa at all") is False


def test_verhoeff_and_luhn():
    assert VALIDATORS["verhoeff"]("234123412346") is True
    assert VALIDATORS["verhoeff"]("234123412340") is False
    assert VALIDATORS["luhn"]("4111111111111111") is True
    assert VALIDATORS["luhn"]("4111111111111112") is False


def test_btc_validator_covers_base58_and_bech32():
    assert VALIDATORS["btc"]("1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa") is True
    assert VALIDATORS["btc"]("bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4") is True
    assert VALIDATORS["btc"]("bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t5") is False


def test_tron_validator():
    assert VALIDATORS["tron"]("TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t") is True
    assert VALIDATORS["tron"]("TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6u") is False


# ----------------------------------------------------------------------------------------- derive


def test_psp_handle_and_sebi_valid():
    assert DERIVERS["psp_handle"]("rajesh.vip@okaxis") == {"psp_handle": "okaxis"}
    valid = DERIVERS["sebi_valid"]("rajesh.brk@validhdfc")
    assert valid == {"sebi_valid": True, "valid_category": "brk", "valid_bank": "hdfc"}
    assert DERIVERS["sebi_valid"]("rajesh.vip@okaxis") == {"sebi_valid": False}


def test_reg_category_mapping():
    assert DERIVERS["reg_category"]("INA000012345") == {"category": "IA"}
    assert DERIVERS["reg_category"]("INH000012345") == {"category": "RA"}
    assert DERIVERS["reg_category"]("INZ000012345") == {"category": "BROKER"}
    assert DERIVERS["reg_category"]("INP000012345") == {"category": "PMS"}
    assert DERIVERS["reg_category"]("IN-DP-CDSL-123") == {"category": "DP"}
    assert DERIVERS["reg_category"]("MF/001/02/3") == {"category": "MF"}
    assert DERIVERS["reg_category"]("IN/AIF1/22-23/123") == {"category": "AIF"}


def test_pan_holder_type():
    assert DERIVERS["pan_holder_type"]("ABCPE1234F") == {"holder_type": "individual"}
    assert DERIVERS["pan_holder_type"]("AAACP1234Q") == {"holder_type": "company"}


def test_phone_series():
    assert DERIVERS["phone_series"]("+919876543210") == {"series": "mobile", "country_code": 91}
    assert DERIVERS["phone_series"]("+14155552671")["series"] == "foreign"
    assert DERIVERS["phone_series"]("1930") == {"series": "short", "country_code": 91}


def test_tg_kind():
    assert DERIVERS["tg_kind"]("t.me/bullrun_vip") == {"kind": "username"}
    assert DERIVERS["tg_kind"]("t.me/joinchat/abcDEF") == {"kind": "invite"}
    assert DERIVERS["tg_kind"]("t.me/+919876543210") == {"kind": "phone"}
    assert DERIVERS["tg_kind"]("t.me/+AbCdEf") == {"kind": "invite"}


def test_host_and_platform():
    assert DERIVERS["host"]("https://tradeking-pro.in/offer") == {"host": "tradeking-pro.in"}
    assert DERIVERS["platform"]("x:kediacapital") == {"platform": "x"}
