"""ModelRouter: role -> PydanticAI model chain (LLD §6.6).

Models are chosen by environment variables so no key or project id lives in YAML:

    SATARK_LLM="anthropic:claude-haiku-4-5"                    # every role
    SATARK_LLM_RESPOND="anthropic:claude-sonnet-5,google-gla:gemini-2.5-flash"   # a fallback chain for one role
    SATARK_LLM="vertex-claude:claude-haiku-4-5"               # Claude on Vertex AI (needs GOOGLE_CLOUD_PROJECT, CLAUDE_REGION)
    SATARK_LLM="local:qwen2.5:7b"                              # any OpenAI-compatible server: Ollama, LM Studio,
    SATARK_LLM_BASE_URL="http://127.0.0.1:11434/v1"            #   vLLM, llama.cpp (default: Ollama's URL)
    SATARK_LLM_OUTPUT_MODE="native"                            # tool (hosted default) | native (local default) | prompted

With nothing set, every role is disabled and the harness runs fully deterministic
(regex extraction, template explanations, FAQ chat answers). Tests inject models with
`router.override(role, FunctionModel(...))`.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, get_args

from pydantic import BaseModel
from pydantic_ai import Agent, NativeOutput, PromptedOutput
from pydantic_ai.models import Model, infer_model
from pydantic_ai.models.fallback import FallbackModel

log = logging.getLogger(__name__)
os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")  # no promotional banner in server logs

ROLES = ("extract", "assess", "explain", "respond", "image")
_EXPLICIT_ONLY = {"image"}  # screenshots may hold the user's own data: only a model named for this role sees them


def field_guide(model: Any) -> str:
    """'- field: description' lines for a Pydantic model and the models nested in it."""
    lines: list[str] = []

    def walk(m: Any, prefix: str) -> None:
        for name, f in getattr(m, "model_fields", {}).items():
            if f.description:
                lines.append(f"- {prefix}{name}: {f.description}")
            for t in (f.annotation, *get_args(f.annotation)):
                if isinstance(t, type) and issubclass(t, BaseModel):
                    walk(t, f"{prefix}{name}[].")

    walk(model, "")
    return "\n".join(lines)


def _build_one(model_id: str, env: Mapping[str, str]) -> Model:
    if model_id.startswith("vertex-claude:"):
        from anthropic import AsyncAnthropicVertex
        from pydantic_ai.models.anthropic import AnthropicModel
        from pydantic_ai.providers.anthropic import AnthropicProvider

        client = AsyncAnthropicVertex(
            project_id=env.get("GOOGLE_CLOUD_PROJECT") or env.get("GCP_PROJECT"),
            region=env.get("CLAUDE_REGION", "us-east5"),
        )
        return AnthropicModel(model_id.split(":", 1)[1], provider=AnthropicProvider(anthropic_client=client))
    if model_id.startswith("local:"):  # OpenAI-compatible server (Ollama, LM Studio, vLLM, llama.cpp, test doubles)
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider

        provider = OpenAIProvider(
            base_url=env.get("SATARK_LLM_BASE_URL", "http://127.0.0.1:11434/v1"),
            api_key=env.get("SATARK_LLM_API_KEY", "local"),
        )
        return OpenAIChatModel(model_id.split(":", 1)[1], provider=provider)
    return infer_model(model_id)


class ModelRouter:
    def __init__(self, models_cfg: Mapping[str, Any], env: Mapping[str, str]):
        self.cfg = dict(models_cfg or {})
        self.env = env
        self._models: dict[str, Model | None] = {}
        self._override: dict[str, Model] = {}
        self.disabled_reason: dict[str, str] = {}
        self._spent: dict[str, float] = {}  # UTC date -> USD
        self._failures: dict[str, int] = {}  # role -> failures in a row
        self._paused_until: dict[str, float] = {}  # role -> monotonic time the breaker closes again
        for role in ROLES:
            named = env.get(f"SATARK_LLM_{role.upper()}") or ("" if role in _EXPLICIT_ONLY else env.get("SATARK_LLM")) or ""
            chain = [m.strip() for m in named.split(",") if m.strip()]
            if not chain:
                self._models[role] = None
                self.disabled_reason[role] = f"no model configured (set SATARK_LLM{'_' + role.upper() if role in _EXPLICIT_ONLY else ''})"
                continue
            try:
                built = [_build_one(m, env) for m in chain]
                self._models[role] = built[0] if len(built) == 1 else FallbackModel(*built)
            except Exception as e:  # missing key, unknown provider: disable the role, never crash
                self._models[role] = None
                self.disabled_reason[role] = f"model setup failed: {type(e).__name__}"
                log.warning("LLM role %s disabled: %s", role, e)

    # ---- configuration --------------------------------------------------------------------
    def role_cfg(self, role: str) -> dict[str, Any]:
        return dict((self.cfg.get("roles") or {}).get(role) or {})

    def timeout(self, role: str) -> float:
        return float(self.role_cfg(role).get("timeout_s", 6))

    def settings(self, role: str) -> dict[str, Any]:
        rc = self.role_cfg(role)
        s: dict[str, Any] = {"timeout": self.timeout(role)}
        if "max_tokens" in rc:
            s["max_tokens"] = int(rc["max_tokens"])
        if "temperature" in rc:
            s["temperature"] = float(rc["temperature"])
        return s

    # ---- models -----------------------------------------------------------------------------
    def override(self, role: str, model: Model | None) -> None:
        """Tests: force a model (FunctionModel/TestModel) for a role; None removes the override."""
        if model is None:
            self._override.pop(role, None)
        else:
            self._override[role] = model

    def model(self, role: str) -> Model | None:
        if role in self._override:
            return self._override[role]
        if self.over_cap() or self.paused(role):
            return None
        return self._models.get(role)

    # ---- circuit breaker: a model server that keeps failing is skipped for a while -------------------
    # Without it every request in an outage waits for the full model timeouts (20-40 s) before the rule answer;
    # with it, after `breaker_failures` failures in a row the role is off for `breaker_pause_s`, so users get the
    # rule verdict at once, and one success closes the breaker again.
    def record(self, role: str, ok: bool) -> None:
        if ok:
            self._failures[role] = 0
            return
        self._failures[role] = self._failures.get(role, 0) + 1
        if self._failures[role] >= int(self.cfg.get("breaker_failures", 3)):
            self._paused_until[role] = time.monotonic() + float(self.cfg.get("breaker_pause_s", 60))
            self._failures[role] = 0
            log.warning("LLM role %s paused for %ss after repeated failures", role, self.cfg.get("breaker_pause_s", 60))

    def paused(self, role: str) -> bool:
        return self._paused_until.get(role, 0.0) > time.monotonic()

    def enabled(self, role: str) -> bool:
        return self.model(role) is not None

    def output_mode(self, role: str) -> str:
        """How structured output is requested: tool, native (JSON schema) or prompted (schema in the prompt).
        Local servers (Ollama, llama.cpp, vLLM) enforce a native JSON schema while decoding, so a small model
        cannot return the wrong shape (in prompted mode a 3B model often echoes the schema back); hosted
        models default to a final-answer tool call."""
        explicit = self.env.get("SATARK_LLM_OUTPUT_MODE") or self.role_cfg(role).get("output_mode")
        if explicit:
            return str(explicit)
        chain = self.env.get(f"SATARK_LLM_{role.upper()}") or self.env.get("SATARK_LLM") or ""
        return "native" if chain.strip().startswith("local:") else "tool"

    def agent(self, role: str, output_type: Any, instructions: str, **kw: Any) -> Agent | None:
        """A fresh Agent for the role, or None when the role is off (caller uses its fallback)."""
        model = self.model(role)
        if model is None:
            return None
        mode = self.output_mode(role)
        if mode == "native":
            # The schema constrains decoding but the model never sees it, so say what each field means.
            instructions += "\n\nOutput fields, in order:\n" + field_guide(output_type)
            output_type = NativeOutput(output_type)
        elif mode == "prompted":
            output_type = PromptedOutput(output_type)
        return Agent(
            model,
            output_type=output_type,
            instructions=instructions,
            model_settings=self.settings(role),
            retries=kw.pop("retries", 1),
            defer_model_check=True,
            **kw,
        )

    # ---- daily cost cap (LLD §6.6) ----------------------------------------------------------
    def add_usage(self, model_name: str, input_tokens: int, output_tokens: int) -> None:
        prices = (self.cfg.get("prices_usd_per_mtok") or {}).get(model_name)
        if not prices:
            return
        day = datetime.now(UTC).date().isoformat()
        cost = (input_tokens * prices[0] + output_tokens * prices[1]) / 1_000_000
        self._spent[day] = self._spent.get(day, 0.0) + cost

    def over_cap(self) -> bool:
        cap = float(self.cfg.get("daily_cost_cap_usd") or 0)
        return cap > 0 and self._spent.get(datetime.now(UTC).date().isoformat(), 0.0) >= cap

    def status(self) -> dict[str, str]:
        """For /v1/meta and /readyz: role -> "on" or the reason it is off."""
        return {r: ("on" if self.enabled(r) else "paused after repeated failures" if self.paused(r)
                    else self.disabled_reason.get(r, "off")) for r in ROLES}
