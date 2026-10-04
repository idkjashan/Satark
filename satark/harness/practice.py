"""POST /v1/practice: a 3-question "spot the trick" quiz on one scam topic.

The model (role `practice`) writes the quiz from the matching lesson chunks of the knowledge base. Its output is
sanitised (placeholders for phone/UPI/link values) and rejected when it says "safe" or gives buy/sell advice; on no
model, failure or a rejected quiz the quiz is built from the lesson's own static questions (content/lessons/*.json).
Questions use the PWA's QuizQuestion shape, so QuizFlow renders either source unchanged.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

N_QUESTIONS = 3
_PHONE = re.compile(r"(?:\+?91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}")
_UPI = re.compile(r"[\w.-]{2,}@[a-z]{2,}", re.I)
_LINK = re.compile(r"(?:https?://|www\.)\S+|\b[\w-]+\.(?:com|in|co|net|org|app|xyz|top|link|info)\b\S*", re.I)
_SAFE = re.compile(r"\bsafe\b|सुरक्षित", re.I)
_ADVICE = re.compile(r"\b(?:should|must|recommend|advise)\b.{0,30}\b(?:buy|sell|invest)|\btarget price\b", re.I)


class _Q(BaseModel):
    message: str = Field(description="A short, realistic scam message or situation (at most 40 words)")
    options: list[str] = Field(description="Exactly 3 short answers the user may pick")
    correct: int = Field(description="Index 0-2 of the best answer")
    explain: str = Field(description="One line naming the manipulation tactic")


class _Quiz(BaseModel):
    questions: list[_Q] = Field(description="Exactly 3 questions")


def clean(text: str) -> str:
    """Swap anything that looks like a real phone number, UPI id or link for a placeholder."""
    return _LINK.sub("example.com/link", _UPI.sub("example-upi@bank", _PHONE.sub("98XXXXXX10", text)))


def _lessons(root: Path) -> dict[str, dict[str, Any]]:
    out = {}
    for p in sorted((root / "content" / "lessons").glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        out[d.get("id", p.stem)] = d
    return out


def _resolve(lessons: dict[str, dict], scoring: dict, topic: str | None, scam_type: str | None, knowledge: Any, lang: str) -> str | None:
    if topic in lessons:
        return topic
    if scam_type and (lid := (scoring.get("lesson_by_scam_type") or {}).get(scam_type)) in lessons:
        return lid
    if topic and knowledge is not None:
        for c in knowledge.search(topic, k=4):
            if c.source == "lesson" and c.ref in lessons:
                return c.ref
    return None


def _quiz_qs(lesson: dict) -> list[dict]:
    q = lesson.get("quiz") or []
    return q if isinstance(q, list) else [q]


def _fallback(lessons: dict[str, dict], lid: str | None) -> list[dict]:
    """Static questions: the lesson's own, topped up from the others' (tagged ones first)."""
    order = ([lid] if lid else []) + [k for k in lessons if k != lid]
    pool = [q for k in order for q in _quiz_qs(lessons[k])]
    return pool[:N_QUESTIONS]


def _convert(quiz: _Quiz, lang: str, tactic: str | None) -> list[dict] | None:
    if len(quiz.questions) < N_QUESTIONS:
        return None
    out = []
    for q in quiz.questions[:N_QUESTIONS]:
        opts = [clean(o.strip()) for o in q.options]
        message, explain = clean(q.message.strip()), clean(q.explain.strip())
        if len(opts) != 3 or not 0 <= q.correct < 3 or not message or not explain:
            return None
        if any(_SAFE.search(x) for x in [message, explain, *opts]) or any(_ADVICE.search(x) for x in [message, explain, *opts]):
            return None
        item = {"question": {lang: message},
                "options": [{"id": "abc"[i], "text": {lang: o}, "correct": i == q.correct} for i, o in enumerate(opts)],
                "explain": {lang: explain}}
        if tactic:
            item["tactic"] = tactic
        out.append(item)
    return out


async def make_quiz(router: Any, knowledge: Any, config: Any, topic: str | None, scam_type: str | None, lang: str) -> dict[str, Any]:
    lessons = await asyncio.to_thread(_lessons, config.root)
    lid = _resolve(lessons, config.scoring, topic, scam_type, knowledge, lang)
    questions: list[dict] | None = None
    try:
        agent = router.agent("practice", _Quiz, (
            "Write a 3-question 'spot the trick' quiz that teaches people to recognise one scam tactic. Each question is a "
            "short realistic message a scammer might send, 3 answer options, the index of the best one, and a one-line "
            f"explanation naming the tactic. Write everything in language \"{lang}\". Never call anything 'safe'. Give no "
            "investment advice. Use only placeholders for contact details: 98XXXXXX10, example-upi@bank, example.com/link."))
    except Exception:
        agent = None
    if agent is not None:
        chunks = [c for c in (getattr(knowledge, "chunks", None) or []) if c.source == "lesson" and c.ref == lid] if lid else []
        if not chunks and knowledge is not None and (topic or scam_type):
            chunks = await knowledge.search_async(topic or scam_type or "", k=4)
        material = "\n".join(c.rendered(lang) for c in chunks)[:2500]
        try:
            result = await asyncio.wait_for(agent.run(f"Topic: {topic or scam_type or 'common scams'}\nLesson material:\n{material}"),
                                            timeout=router.timeout("practice"))
            router.record("practice", ok=True)
            questions = _convert(result.output, lang, (lessons.get(lid) or {}).get("tacticKey"))
        except Exception as e:
            log.warning("practice quiz failed: %s", type(e).__name__)
            router.record("practice", ok=False)
    if questions:
        return {"questions": questions, "source": "model", "lesson": lid}
    return {"questions": _fallback(lessons, lid), "source": "lessons", "lesson": lid}
