"""Validates all engineer-G content against docs/CONTRACTS.md SS7 (schema) and SS8 (golden set).

Run: uv run pytest -q tests/unit/test_content.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from satark.config import ROOT

CONTENT = ROOT / "content"
SKILLS_DIR = ROOT / "skills"
LANGS = ("en", "hi")
LEVELS = {"HIGH_RISK", "SUSPICIOUS", "NO_SIGNS", "UNKNOWN"}


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


# Loaded once directly from the files this task owns, independent of the merged `config` fixture
# (which also picks up content/i18n/ui.*.json, owned by F) so this suite only judges G's own content.
I18N = {lang: _json(CONTENT / "i18n" / f"content.{lang}.json") for lang in LANGS}

# ---------------------------------------------------------------------------
# Cheap Hindi-script check: the share of Devanagari letters among the letters that remain once
# {placeholders} and common Latin loanwords (brand names, acronyms, official programme names a
# Hindi speaker says as-is: UPI, OTP, SEBI, SCORES, Sachet...) are stripped out. None means nothing
# was left to judge (a loanword/placeholder-only string, e.g. "UPI ID") -- treated as a pass.
LOANWORDS = {
    "upi", "otp", "sebi", "pin", "apk", "ipo", "kyc", "pan", "ifsc", "qr", "nav", "sip", "vip",
    "cas", "nse", "bse", "rbi", "amfi", "npci", "id", "play", "store", "verified", "app", "google",
    "ok", "dp", "ia", "ra", "pms", "anydesk", "teamviewer", "dnvs", "url", "sms", "telegram",
    "whatsapp", "cbi", "fpi", "qib", "otc", "scores", "faq", "tds", "stt", "cams", "check",
    "sachet", "odr", "smart", "cms", "tafcop", "mrm", "iepf", "pib", "nsdl", "cdsl", "arn", "mi",
    "f&o", "groww", "zerodha", "hdfc", "tradeking", "pro", "ekyc",
}
_PLACEHOLDER = re.compile(r"\{[^}]*\}")


def devanagari_ratio(text: str) -> float | None:
    text = _PLACEHOLDER.sub(" ", text)
    for word in sorted(LOANWORDS, key=len, reverse=True):
        text = re.sub(rf"(?i)\b{re.escape(word)}\b", " ", text)
    deva = sum(1 for ch in text if "ऀ" <= ch <= "ॿ")
    latin = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    total = deva + latin
    return None if total == 0 else deva / total


def _assert_bilingual(d: dict, label: str = "") -> None:
    assert isinstance(d, dict), f"{label}: not an object"
    for lang in LANGS:
        assert lang in d and isinstance(d[lang], str) and d[lang].strip(), f"{label}: missing {lang}"
    ratio = devanagari_ratio(d["hi"])
    assert ratio is None or ratio >= 0.6, f"{label}: hi text not natural Devanagari ({ratio:.0%}): {d['hi']!r}"


# ---------------------------------------------------------------------------
# i18n content (content/i18n/content.{en,hi}.json)

def test_i18n_json_parses_and_is_flat():
    for lang in LANGS:
        data = I18N[lang]
        assert isinstance(data, dict) and data
        assert all(isinstance(k, str) and isinstance(v, str) and v.strip() for k, v in data.items())


def test_i18n_same_keys_in_both_languages():
    assert set(I18N["en"]) == set(I18N["hi"])


def test_i18n_hindi_is_natural_devanagari():
    bad = []
    for key, text in I18N["hi"].items():
        ratio = devanagari_ratio(text)
        if ratio is not None and ratio < 0.6:
            bad.append(f"{key}: {ratio:.0%} -- {text!r}")
    assert not bad, "\n".join(bad)


def test_signal_titles_complete(config):
    for code, spec in config.signals.items():
        if spec.get("polarity") in ("risk", "assurance", "info"):
            for lang in LANGS:
                assert f"signal.{code}" in I18N[lang], f"signal.{code} missing for {lang}"


def test_action_and_portal_labels_complete(config):
    for aid in config.portals["actions"]:
        for lang in LANGS:
            assert f"action.{aid}" in I18N[lang], f"action.{aid} missing for {lang}"
    for pid in config.portals["portals"]:
        for lang in LANGS:
            assert f"portal.{pid}" in I18N[lang], f"portal.{pid} missing for {lang}"


def test_entity_labels_complete(config):
    for etype in config.entities:
        for lang in LANGS:
            assert f"entity.{etype}" in I18N[lang], f"entity.{etype} missing for {lang}"


def test_scam_type_and_confidence_and_level_keys_present():
    for t in range(1, 12):
        for lang in LANGS:
            assert f"scam_type.T{t}" in I18N[lang]
    for c in ("SURE", "FAIRLY_SURE", "NOT_SURE"):
        for lang in LANGS:
            assert f"confidence.{c}" in I18N[lang]
    for lvl in LEVELS:
        for part in ("headline", "say"):
            for lang in LANGS:
                assert f"level.{lvl}.{part}" in I18N[lang]


# ---------------------------------------------------------------------------
# Lessons (content/lessons/<id>.json)

LESSON_IDS = {
    "compounding", "leverage", "sebi-registration", "fake-apps", "tips-and-pumps",
    "digital-arrest", "job-scam", "withdrawal-fee-app", "pig-butchering",
    "kyc-otp-remote-access", "deepfake-ads", "ipo-allotment",
    "bonus-and-split", "buyback-and-delisting", "agm-and-voting",
}

FSM_SIM_IDS = {"S1", "S4", "S5", "S6"}  # content/sims/*.json with kind "fsm" (shared reachability rules)


def _quiz_questions(quiz: Any) -> list[dict]:
    """A lesson/sim `quiz` is either one question object (older content) or a list of 2-3
    (CONTRACTS SS7.2/7.3 extension for Track C's immediate-retrieval quizzes) - normalise to a list."""
    return quiz if isinstance(quiz, list) else [quiz]


def _assert_quiz_question(q: dict, label: str) -> None:
    _assert_bilingual(q["question"], f"{label}.question")
    _assert_bilingual(q["explain"], f"{label}.explain")
    options = q["options"]
    assert len(options) >= 2, f"{label}: quiz needs >=2 options"
    assert sum(1 for o in options if o.get("correct")) == 1, f"{label}: quiz needs exactly one correct option"
    for i, opt in enumerate(options):
        _assert_bilingual(opt["text"], f"{label}.options[{i}]")
    if "tactic" in q:
        assert isinstance(q["tactic"], str) and q["tactic"], f"{label}: tactic must be a non-empty string"


def test_lesson_ids_match_spec_and_scoring(config):
    files = {p.stem for p in (CONTENT / "lessons").glob("*.json")}
    assert files == LESSON_IDS
    referenced = set(config.scoring["lesson_by_scam_type"].values())
    assert referenced <= files, f"scoring.yaml references lessons that don't exist: {referenced - files}"


def test_lesson_schema():
    for path in sorted((CONTENT / "lessons").glob("*.json")):
        data = _json(path)
        label = f"lesson {path.stem}"
        assert data["id"] == path.stem
        assert isinstance(data.get("icon"), str) and data["icon"]
        assert isinstance(data.get("minutes"), int) and data["minutes"] > 0
        _assert_bilingual(data["title"], f"{label}.title")
        # Prebunking (task technique #2): every lesson opens by naming its manipulation tactic.
        _assert_bilingual(data["tactic"], f"{label}.tactic")
        assert isinstance(data.get("tacticKey"), str) and data["tacticKey"], f"{label}: missing tacticKey"
        steps = data["steps"]
        assert 3 <= len(steps) <= 5, f"{label}: {len(steps)} steps, want 3-5"
        for i, step in enumerate(steps):
            _assert_bilingual(step["text"], f"{label}.steps[{i}].text")
            if "visual" in step:
                assert isinstance(step["visual"], str) and step["visual"]
        _assert_bilingual(data["analogy"], f"{label}.analogy")
        if "source" in data:
            assert data["source"].startswith("https://"), f"{label}: source must be an https:// URL"
        if "sim" in data:
            assert isinstance(data["sim"], str) and data["sim"], f"{label}: sim must be a non-empty sim id"
        questions = _quiz_questions(data["quiz"])
        assert 1 <= len(questions) <= 3, f"{label}: {len(questions)} quiz questions, want 1-3"
        for i, q in enumerate(questions):
            _assert_quiz_question(q, f"{label}.quiz[{i}]")


# ---------------------------------------------------------------------------
# Simulators (content/sims/S1.json, S2.json, S3.json)

_SET_OP = re.compile(r"^[+\-=*]\d+(\.\d+)?$")


def test_sim_fsm_structure_and_reachability():
    files = {p.stem for p in (CONTENT / "sims").glob("*.json") if _json(p).get("kind") == "fsm"}
    assert files == FSM_SIM_IDS, f"fsm sim files {files} != expected {FSM_SIM_IDS}"

    for sim_id in sorted(FSM_SIM_IDS):
        data = _json(CONTENT / "sims" / f"{sim_id}.json")
        assert data["id"] == sim_id and data["kind"] == "fsm"
        states = data["states"]
        assert data["start"] in states
        assert isinstance(data["vars"], dict)

        for sid, st in states.items():
            for choice in st.get("choices", []):
                assert choice["to"] in states, f"{sim_id}.{sid}: choice {choice['id']} targets unknown state {choice['to']!r}"
                _assert_bilingual(choice["label"], f"{sim_id}.{sid}.choices.{choice['id']}.label")
                for var, op in (choice.get("set") or {}).items():
                    assert var in data["vars"], f"{sim_id}.{sid}: unknown var {var!r} in set"
                    assert _SET_OP.match(op), f"{sim_id}.{sid}: bad set op {op!r} (only +N, -N, =N, *F allowed)"
            if "say" in st:
                _assert_bilingual(st["say"], f"{sim_id}.{sid}.say")
            if "end" in st:
                assert st["end"] in ("safe", "lost"), f"{sim_id}.{sid}: bad end {st['end']!r}"
                _assert_bilingual(st["reveal"], f"{sim_id}.{sid}.reveal")
            else:
                assert st.get("choices"), f"{sim_id}.{sid}: non-end state has no choices"

        # Every state must be able to reach an end state: reverse-BFS from the ends over the choice graph.
        ends = {sid for sid, st in states.items() if "end" in st}
        assert ends, f"{sim_id}: no end states at all"
        preds: dict[str, set[str]] = {sid: set() for sid in states}
        for sid, st in states.items():
            for choice in st.get("choices", []):
                preds[choice["to"]].add(sid)
        can_reach_end = set(ends)
        frontier = list(ends)
        while frontier:
            s = frontier.pop()
            for p in preds[s]:
                if p not in can_reach_end:
                    can_reach_end.add(p)
                    frontier.append(p)
        stuck = set(states) - can_reach_end
        assert not stuck, f"{sim_id}: states that can never reach an end: {stuck}"
        assert data["start"] in can_reach_end

        for i, q in enumerate(_quiz_questions(data["quiz"])):
            _assert_quiz_question(q, f"{sim_id}.quiz[{i}]")


def test_sim_s2_and_s3_required_fields():
    s2 = _json(CONTENT / "sims" / "S2.json")
    assert s2["id"] == "S2" and s2["kind"] == "returns"
    _assert_bilingual(s2["title"], "S2.title")
    assert s2["texts"], "S2: no texts"
    for key, text in s2["texts"].items():
        _assert_bilingual(text, f"S2.texts.{key}")
    assert set(s2["defaults"]) == {"rate", "period", "amount"}
    for i, q in enumerate(_quiz_questions(s2["quiz"])):
        _assert_quiz_question(q, f"S2.quiz[{i}]")

    s3 = _json(CONTENT / "sims" / "S3.json")
    assert s3["id"] == "S3" and s3["kind"] == "leverage"
    _assert_bilingual(s3["title"], "S3.title")
    assert s3["texts"], "S3: no texts"
    for key, text in s3["texts"].items():
        _assert_bilingual(text, f"S3.texts.{key}")
    assert set(s3["defaults"]) == {"margin", "leverage", "seed", "steps"}
    for i, q in enumerate(_quiz_questions(s3["quiz"])):
        _assert_quiz_question(q, f"S3.quiz[{i}]")


def test_lesson_sim_links_point_to_real_sims():
    sim_ids = {p.stem for p in (CONTENT / "sims").glob("*.json")}
    for path in sorted((CONTENT / "lessons").glob("*.json")):
        data = _json(path)
        if "sim" in data:
            assert data["sim"] in sim_ids, f"lesson {path.stem}: sim {data['sim']!r} does not exist"


# ---------------------------------------------------------------------------
# Offline chat FAQ (content/faq.json)

def test_faq_schema():
    data = _json(CONTENT / "faq.json")
    intents = data["intents"]
    assert len(intents) >= 15, f"faq.json: only {len(intents)} intents, want >= 15"
    seen = set()
    for intent in intents:
        iid = intent["id"]
        assert iid not in seen, f"duplicate faq intent id {iid}"
        seen.add(iid)
        patterns = intent["patterns"]
        assert patterns, f"{iid}: no patterns"
        assert all(p == p.lower() for p in patterns), f"{iid}: patterns must be lower-case"
        _assert_bilingual(intent["answer"], f"faq.{iid}.answer")
        chips = intent["chips"]
        for lang in LANGS:
            assert chips.get(lang), f"{iid}: no {lang} chips"
    fallback = data["fallback"]
    _assert_bilingual(fallback["answer"], "faq.fallback.answer")
    for lang in LANGS:
        assert fallback["chips"].get(lang), f"faq fallback: no {lang} chips"


# ---------------------------------------------------------------------------
# Skills (skills/<area>/<name>/SKILL.md)

_FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.S)
_REQUIRED_SKILL_FIELDS = ("name", "description", "languages", "reviewer", "reviewed_on", "sources", "reason_codes")
_ALWAYS_LOADED_SKILLS = ("policy/no-tips", "policy/tone-for-seniors", "policy/uncertainty")

# Education skills (CONTRACTS SS7.5 "Add freely"): loaded on demand by topic in chat, not tied to a
# risk signal, so config/signals.yaml never names them. docs/reference/hld.txt Appendix C.6 concept
# list, plus SIP and IPO basics.
EDUCATION_SKILLS = (
    "education/sip", "education/nav", "education/compounding", "education/leverage",
    "education/diversification", "education/volatility", "education/kyc-and-demat",
    "education/nomination", "education/ipo-basics", "education/fees-and-expense-ratio",
)


def _check_skill_frontmatter(name: str) -> None:
    path = SKILLS_DIR / name / "SKILL.md"
    assert path.exists(), f"missing {path}"
    text = path.read_text(encoding="utf-8")
    m = _FRONTMATTER.match(text)
    assert m, f"{name}: SKILL.md has no '---' YAML front matter"
    front = yaml.safe_load(m.group(1))
    for field in _REQUIRED_SKILL_FIELDS:
        assert field in front, f"{name}: front matter missing {field!r}"
    assert front["languages"] == ["en", "hi"], f"{name}: languages should be [en, hi]"
    body_words = len(m.group(2).split())
    assert body_words <= 400, f"{name}: body is {body_words} words, want <= 400"


def test_every_signal_skill_exists_with_complete_frontmatter(config):
    names = {spec["skill"] for spec in config.signals.values() if spec.get("skill")}
    names |= set(_ALWAYS_LOADED_SKILLS)
    assert names, "no skills referenced by config/signals.yaml -- is the fixture stale?"
    for name in sorted(names):
        _check_skill_frontmatter(name)


def test_education_skills_exist_with_complete_frontmatter():
    for name in EDUCATION_SKILLS:
        _check_skill_frontmatter(name)


# ---------------------------------------------------------------------------
# Golden cases (tests/golden/cases.yaml)

def test_golden_cases_schema(config):
    cases = _yaml(ROOT / "tests" / "golden" / "cases.yaml")
    assert len(cases) >= 45, f"only {len(cases)} golden cases, want >= 45 (30 scam + 15 legit)"
    known_codes = set(config.signals)
    seen_ids = set()
    for case in cases:
        cid = case["id"]
        assert cid not in seen_ids, f"duplicate golden case id {cid}"
        seen_ids.add(cid)
        assert case["lang"] in LANGS, f"{cid}: unsupported lang {case['lang']!r}"
        assert case["text"].strip(), f"{cid}: empty text"
        assert case.get("note"), f"{cid}: missing note"
        if "requires_llm" in case:  # optional: case only runs when an AI model is configured (e.g. off-topic)
            assert isinstance(case["requires_llm"], bool), f"{cid}: requires_llm must be true/false"
        exp = case["expect"]
        assert exp["level"] in LEVELS, f"{cid}: unknown level {exp['level']!r}"
        for field in ("codes_any", "codes_none"):
            for code in exp.get(field) or []:
                assert code in known_codes, f"{cid}: unknown code {code!r} in {field}"


def test_golden_cases_cover_scam_and_legit_and_off_topic():
    cases = _yaml(ROOT / "tests" / "golden" / "cases.yaml")
    no_signs = [c for c in cases if c["expect"]["level"] == "NO_SIGNS"]
    flagged = [c for c in cases if c["expect"]["level"] in ("HIGH_RISK", "SUSPICIOUS")]
    unknown = [c for c in cases if c["expect"]["level"] == "UNKNOWN"]
    assert len(no_signs) >= 15, "want at least 15 legitimate (NO_SIGNS) golden cases"
    assert len(flagged) >= 30, "want at least 30 scam (HIGH_RISK/SUSPICIOUS) golden cases"
    assert unknown, "want at least one UNKNOWN (off-topic / nothing-checkable) golden case"
