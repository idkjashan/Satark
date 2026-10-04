"""Explainer: verdict -> short, grounded explanation (LLD §6.2).

LLM role `explain`, no tools, with policy skills in the instructions and the top reasons' skill
bodies in the prompt. Template fallback when the role is off, the output keeps failing validation,
or the timeout hits — every signal in `signals.yaml` has a pre-translated title, so the template
never has nothing to say.
"""

from __future__ import annotations

import asyncio
import logging

from pydantic_ai import ModelRetry, RunContext

from satark.harness.state import CaseState, Explanation, ReasonText

log = logging.getLogger(__name__)

_POLICY_SKILLS = ("policy/no-tips", "policy/tone-for-seniors", "policy/uncertainty")
_ROLE_TEXT = (
    "You write a short, plain-language explanation of a scam-risk verdict for a first-time Indian "
    "investor, often a senior citizen in a Tier-2/3 city. Use only the facts given below; never "
    "invent a registration number, a name or a fact not present in the evidence. Never give "
    "investment advice, and never say something 'is safe' or 'is genuine' - only what was checked "
    "and what is still unknown."
)

_LEVEL_CHIPS: dict[str, tuple[str, ...]] = {
    "HIGH_RISK": ("chip.what_now", "chip.report_where"),
    "SUSPICIOUS": ("chip.how_verify_adviser", "chip.what_now"),
    "NO_SIGNS": ("chip.how_verify_adviser",),
    "UNKNOWN": ("chip.what_now",),
}


def _guards():
    try:
        from satark.harness import guards

        return guards
    except ImportError:
        return None


class Explainer:
    def __init__(self, router, config, skills, explain_timeout_s: float = 3.0) -> None:
        self.router = router
        self.config = config
        self.skills = skills
        self.explain_timeout_s = explain_timeout_s

    async def explain(self, case: CaseState) -> Explanation:
        llm_enabled = self.router is not None and self.router.enabled("explain")
        explanation = await self._llm_explain(case) if llm_enabled else None
        if explanation is None:
            explanation = self._template(case, fallback_used=llm_enabled)

        g = _guards()
        if g is not None:
            explanation.summary = g.unmask(explanation.summary, case, case.lang)
            for r in explanation.reasons:
                r.text = g.unmask(r.text, case, case.lang)
        explanation.lang = case.lang
        return explanation

    # ---- LLM path -----------------------------------------------------------------------------
    async def _llm_explain(self, case: CaseState) -> Explanation | None:
        g = _guards()
        agent = self.router.agent("explain", Explanation, self._instructions())
        if agent is None:
            return None

        expected = [r.code for r in case.verdict.reasons] if case.verdict else []

        @agent.output_validator
        async def _validate(ctx: RunContext[None], output: Explanation) -> Explanation:
            if g is None:
                return output
            text = output.summary + " " + " ".join(r.text for r in output.reasons)
            problems = g.check_output(text, case, self.config, case.lang, expected_codes=expected)
            if problems:
                raise ModelRetry("; ".join(problems))
            return output

        prompt = self._user_prompt(case, g)
        if g is not None and (leaks := g.pii_leaks(prompt, case)):
            log.warning("PII_TRIPWIRE: explain prompt would have leaked %s", leaks)
            return None  # the template explains instead; nothing reaches the model
        try:
            result = await asyncio.wait_for(agent.run(prompt), timeout=self.explain_timeout_s)
            return result.output
        except Exception as e:  # timeout, retry exhausted, provider error, bad JSON, ...
            log.warning("explain LLM failed: %s", type(e).__name__)
            return None

    def _instructions(self) -> str:
        parts = [_ROLE_TEXT]
        for name in _POLICY_SKILLS:
            body = self.skills.get(name)
            if body:
                parts.append(body)
        return "\n\n".join(parts)

    def _user_prompt(self, case: CaseState, g) -> str:
        brief = g.brief(case, "explain", self.config) if g is not None else "{}"
        skill_bodies = []
        if case.verdict:
            for r in case.verdict.reasons[:3]:
                name = self.config.signal(r.code).get("skill")
                body = self.skills.get(name) if name else None
                if body:
                    skill_bodies.append(body)
        return brief + ("\n\n" + "\n\n".join(skill_bodies) if skill_bodies else "")

    # ---- template fallback ----------------------------------------------------------------
    def _template(self, case: CaseState, fallback_used: bool) -> Explanation:
        lang = case.lang
        v = case.verdict
        level = v.level if v else "UNKNOWN"
        reason_texts = [ReasonText(code=r.code, text=self.config.t(lang, f"signal.{r.code}")) for r in (v.reasons if v else [])]
        parts = [self.config.t(lang, f"level.{level}.headline"), *[rt.text for rt in reason_texts]]
        unknown_families = [c.family for c in (v.checked if v else []) if c.status == "unknown"]
        if unknown_families:
            labels = ", ".join(self.config.t(lang, f"family.{f}") for f in unknown_families)
            parts.append(self.config.t(lang, "explain.could_not_check", families=labels))
        parts.append(self.config.t(lang, "explain.uncertainty"))
        return Explanation(
            summary=_sentences(parts, lang),
            reasons=reason_texts,
            chips=[self.config.t(lang, key) for key in _LEVEL_CHIPS.get(level, _LEVEL_CHIPS["UNKNOWN"])],
            fallback_used=fallback_used,
            lang=lang,
        )


def _sentences(parts: list[str], lang: str) -> str:
    """Join template fragments as sentences: titles and headlines carry no final stop of their own."""
    stop = "।" if lang in ("hi", "mr") else "."
    out = []
    for p in (x.strip() for x in parts if x and x.strip()):
        out.append(p if p[-1] in ".!?।" else p + stop)
    return " ".join(out)
