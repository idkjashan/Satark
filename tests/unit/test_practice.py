"""/v1/practice quiz maker: model path (sanitised, guarded) and the static-lesson fallback."""

from __future__ import annotations

from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from satark.harness.models import ModelRouter
from satark.harness.practice import make_quiz


def _model(message: str, explain: str = "Urgency is the pressure tactic."):
    q = {"message": message, "options": ["Pay", "Report it", "Share OTP"], "correct": 1, "explain": explain}

    def fn(messages, info: AgentInfo):
        return ModelResponse(parts=[ToolCallPart(tool_name=info.output_tools[0].name, args={"questions": [q, q, q]})])

    return FunctionModel(fn)


async def test_model_path_uses_placeholders(config):
    router = ModelRouter({}, {})
    router.override("practice", _model("Pay Rs 500 to realname@oksbi or call 9876543210 via http://scam.in/x"))
    out = await make_quiz(router, None, config, None, "T15", "en")
    assert out["source"] == "model" and out["lesson"] == "pig-butchering" and len(out["questions"]) == 3
    q = out["questions"][0]
    text = q["question"]["en"]
    assert "98XXXXXX10" in text and "example-upi@bank" in text and "example.com/link" in text
    assert [o["correct"] for o in q["options"]] == [False, True, False] and q["tactic"]


async def test_fallback_without_model_or_on_unsafe_output(config):
    out = await make_quiz(ModelRouter({}, {}), None, config, "fake-apps", None, "hi")
    assert out["source"] == "lessons" and len(out["questions"]) == 3 and "hi" in out["questions"][0]["question"]
    router = ModelRouter({}, {})
    router.override("practice", _model("This app is safe, trust it"))
    assert (await make_quiz(router, None, config, "fake-apps", None, "en"))["source"] == "lessons"
