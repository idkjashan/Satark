"""POST /v1/report-draft (CONTRACTS §6)."""

from __future__ import annotations

from datetime import timedelta

from satark.harness.state import CaseState, Entity, Reason, Verdict, utcnow


def _case_with_entities(case_id: str = "case-report-1") -> CaseState:
    case = CaseState(case_id=case_id, lang="hi", expires_at=utcnow() + timedelta(minutes=30))
    case.entities = [
        Entity(id="e1", type="upi.vpa", cls="C", placeholder="[UPI_1]", norm_hash="h1", display="scammer@ybl"),
        Entity(id="e2", type="url", cls="C", placeholder="[URL_1]", norm_hash="h2", display="http://fake-sebi-refund.in"),
        Entity(id="e3", type="aadhaar", cls="U", placeholder="[AADHAAR_1]", norm_hash="h3", display=""),
        Entity(id="e4", type="message.text", cls="C", norm_hash="h4", display="the whole masked message"),
    ]
    case.verdict = Verdict(
        revision=1,
        level="HIGH_RISK",
        confidence="SURE",
        reasons=[Reason(code="UPI_COLLECT_TO_RECEIVE", weight="critical", basis="rule")],
        assurances=["REG_FOUND"],
        scam_type="T5",
    )
    return case


async def test_happy_path_contains_everything_required(client, rt, config):
    case = _case_with_entities()
    rt.cases.put(case)

    resp = await client.post("/v1/report-draft", json={"case_id": case.case_id, "lang": "hi", "answers": {"when": "yesterday", "how_paid": "UPI", "amount_band": "5000-20000"}})
    assert resp.status_code == 200
    body = resp.json()

    assert "text_en" in body and "text_lang" in body
    # the identifiers (C-class only) must appear
    assert "scammer@ybl" in body["text_en"]
    assert "http://fake-sebi-refund.in" in body["text_en"]
    # the whole masked message (synthetic entity) must NOT be dumped in
    assert "the whole masked message" not in body["text_en"]
    # the answers must appear
    assert "yesterday" in body["text_en"]
    assert "UPI" in body["text_en"]
    assert "5000-20000" in body["text_en"]
    # the verdict reason's title: whatever config.t resolves it to (real content, once
    # content/i18n has it, else the bare key) — computed the same way the code does, so this
    # does not hardcode a guess at either state.
    assert config.t("en", "signal.UPI_COLLECT_TO_RECEIVE") in body["text_en"]
    assert config.t("hi", "signal.UPI_COLLECT_TO_RECEIVE") in body["text_lang"]

    # exactly the two C-class identifiers: never the U-class aadhaar, never the synthetic message.text
    evidence_values = {row["value"] for row in body["evidence"]}
    assert evidence_values == {"scammer@ybl", "http://fake-sebi-refund.in"}

    portal_ids = [p["id"] for p in body["portals"]]
    assert portal_ids[0] == "ncrp_1930"
    assert "sebi_scores" in portal_ids  # REG_FOUND among assurances
    assert "sebi_mi" in portal_ids  # scam_type T5


async def test_no_u_class_value_ever_leaks(client, rt):
    """Defense in depth: even if a U-class entity somehow carried a non-empty `display` (it
    never should — masking discards it at extraction, CONTRACTS §2), draft_report must still
    filter it out by `cls`, not merely by whether `display` happens to be truthy."""
    case = _case_with_entities()
    case.entities.append(
        Entity(id="e9", type="aadhaar", cls="U", placeholder="[AADHAAR_2]", norm_hash="h9", display="999988887777")
    )
    rt.cases.put(case)
    resp = await client.post("/v1/report-draft", json={"case_id": case.case_id, "lang": "en", "answers": {}})
    body = resp.json()
    full_text = body["text_en"] + body["text_lang"]
    assert "999988887777" not in full_text
    assert all(row["value"] != "999988887777" for row in body["evidence"])
    assert all(row["value"] for row in body["evidence"])  # no empty rows either


async def test_rbi_sachet_for_ponzi_scam_type(client, rt):
    case = _case_with_entities(case_id="case-ponzi")
    case.verdict.scam_type = "T11"
    case.verdict.assurances = []
    rt.cases.put(case)
    resp = await client.post("/v1/report-draft", json={"case_id": case.case_id, "lang": "en", "answers": {}})
    portal_ids = [p["id"] for p in resp.json()["portals"]]
    assert "rbi_sachet" in portal_ids
    assert "sebi_mi" not in portal_ids


async def test_chakshu_for_phone_sms_case(client, rt):
    case = _case_with_entities(case_id="case-phone")
    case.verdict = None
    case.entities.append(Entity(id="e5", type="phone", cls="C", placeholder="[PHONE_1]", norm_hash="h5", display="+919999900000"))
    rt.cases.put(case)
    resp = await client.post("/v1/report-draft", json={"case_id": case.case_id, "lang": "en", "answers": {}})
    body = resp.json()
    portal_ids = [p["id"] for p in body["portals"]]
    assert portal_ids == ["ncrp_1930", "chakshu"]
    assert "+919999900000" in body["text_en"]


async def test_case_expired(client):
    resp = await client.post("/v1/report-draft", json={"case_id": "no-such-case", "lang": "en", "answers": {}})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "case_expired"


async def test_missing_required_field_is_422(client):
    resp = await client.post("/v1/report-draft", json={"lang": "en"})
    assert resp.status_code == 422
