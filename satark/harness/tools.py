"""Tool layer of the agent loop: Satark's own checks and any MCP server, behind one interface.

The loop (agent.py) never calls a checker or a server directly. It sees a menu of suggested calls and the
tool specs (name, description, JSON input schema, policy), and asks the registry to run calls:

- Toolsets come from config/tools.yaml. `builtin` is Satark's own checks (in-process); `mcp_stdio` is any MCP
  (Model Context Protocol) server, spawned once at startup, its tools discovered with tools/list. Plug-and-play:
  add a server entry, restart, and its tools appear in the menu. A tool whose only required parameter is a
  string named like `query`, `url`, `domain` or `name` gets menu entries automatically from the case's
  identifiers.
- Every call passes the same policy: the tool is allowed in this mode, under its per-run cap and the run's
  total cap, within its timeout. For toolsets marked `privacy: external`, placeholders of public identifier
  types (a site, an app, a firm's name) are filled in, every other placeholder is removed, and the PII
  tripwire must pass: the user's own data never leaves the server.
- Every result becomes short masked text, stored on the case as an observation (obs1, obs2...): the loop's
  memory across steps and chat turns, and proof the judge step may cite.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
from collections import Counter
from collections.abc import Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any

from satark.harness.budget import Budget
from satark.harness.state import CaseState, EntityDraft, Observation, PlanStep

log = logging.getLogger(__name__)

ADDABLE = ("party.name", "social.handle", "url", "phone", "upi.vpa", "app.package", "email", "tg.link")
_PLACEHOLDER = re.compile(r"\[[A-Z]+_\d+\]")
_DEFAULT_SOURCES = {  # parameter name -> identifier types that can fill it, for any MCP tool
    "query": ("domain", "app.package", "social.handle", "tg.link", "party.name"), "q": ("domain", "party.name"),
    "url": ("url",), "link": ("url",), "domain": ("domain",), "name": ("party.name",),
}


@dataclass(frozen=True)
class ToolSpec:
    name: str  # namespaced: "satark.check_identifiers", "web.search"
    description: str
    params: dict  # JSON schema of the arguments (an MCP tool's inputSchema)
    toolset: str
    privacy: str = "local"
    modes: frozenset[str] = frozenset({"check", "chat"})
    max_calls: int = 2
    timeout_s: float = 10.0


@dataclass
class Call:
    tool: str
    args: dict

    @property
    def key(self) -> str:
        return f"{self.tool}:{json.dumps(self.args, sort_keys=True, ensure_ascii=False)}"


@dataclass
class ToolRun:
    """Per-run state: the case, the mode, a budget for Satark's checkers, and the event callbacks."""

    case: CaseState
    mode: str
    budget: Budget
    emit: Callable[[str, dict], None]
    on_evidence: Callable[[Any], None]
    lang: str = "en"
    on_plan: Callable[[], None] = lambda: None  # the plan grew (new checker steps): tell the UI
    step: int = 0
    counts: Counter = field(default_factory=Counter)

    def done_keys(self) -> set[str]:
        return {o.key for o in self.case.observations}


class Toolset:
    name = ""
    privacy = "local"
    public_types: tuple[str, ...] = ()
    error: str | None = None

    def specs(self) -> list[ToolSpec]:
        return []

    def suggest(self, run: ToolRun) -> list[Call]:
        return []

    async def call(self, spec: ToolSpec, args: dict, run: ToolRun) -> tuple[bool, str]:
        raise NotImplementedError

    async def start(self) -> None:
        return None

    async def close(self) -> None:
        return None


# ---- Satark's own checks (in-process) ----------------------------------------------------------------
_SATARK_TOOLS = {
    "check_identifiers": ("Run Satark's checks (registers, lists, links, apps, phone rules) on identifiers the "
                          "message contains", {"type": "object", "properties": {"entity_ids": {
                              "type": "array", "items": {"type": "string"}}}, "required": ["entity_ids"]}),
    "add_and_check": ("Add a name, app, handle, link, phone or UPI ID the message mentions but the identifier list "
                      "missed (exact words from the message), then check it",
                      {"type": "object", "properties": {"entity_type": {"enum": list(ADDABLE)},
                                                        "value": {"type": "string"}},
                       "required": ["entity_type", "value"]}),
    "search_sebi_register": ("Look a person or firm up in SEBI's register of advisers, analysts and brokers",
                             {"type": "object", "properties": {"name": {"type": "string"},
                                                               "category": {"type": "string"}}, "required": ["name"]}),
    "read_safety_note": ("Read one of Satark's reviewed safety notes (how a scam works, how to verify, what to do)",
                         {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}),
}


class SatarkTools(Toolset):
    def __init__(self, cfg: dict, config, checkers, executor, pipeline, skills, search_registry) -> None:
        self.name, self.privacy = "satark", "local"
        self.config, self.checkers, self.executor, self.pipeline = config, checkers, executor, pipeline
        self.skills, self._search_registry = skills, search_registry
        tools_cfg = cfg.get("tools") or {k: {} for k in _SATARK_TOOLS}
        self._specs = [
            ToolSpec(name=f"satark.{t}", description=_SATARK_TOOLS[t][0], params=_SATARK_TOOLS[t][1], toolset="satark",
                     modes=frozenset(c.get("modes", ["check", "chat"])), max_calls=int(c.get("max_calls", 2)),
                     timeout_s=float(c.get("timeout_s", 15)))
            for t, c in tools_cfg.items() if t in _SATARK_TOOLS
        ]

    def specs(self) -> list[ToolSpec]:
        return self._specs

    def suggest(self, run: ToolRun) -> list[Call]:
        case, calls = run.case, []
        unchecked = [e.id for e in case.entities if _checkable(e) and not e.planned]
        if unchecked:
            calls.append(Call("satark.check_identifiers", {"entity_ids": unchecked[:4]}))
        for e in case.by_type("party.name"):
            calls.append(Call("satark.search_sebi_register", {"name": e.placeholder or e.display}))
        if run.mode == "chat" and self.skills:
            calls += [Call("satark.read_safety_note", {"name": n}) for n in self._notes_for(case)]
        return calls

    def _notes_for(self, case: CaseState) -> list[str]:
        """Notes for the verdict's reasons, then the notes whose description shares the most words with the last
        thing the user said (a ranking for the menu, never a gate)."""
        names = []
        if case.verdict:
            names += [self.config.signal(r.code).get("skill") for r in case.verdict.reasons]
        last = next((t.text for t in reversed(case.turns) if t.role == "user"), "")
        words = {w for w in re.findall(r"[\wऀ-ॿ]{3,}", last.lower())}
        ranked = sorted(self.skills.index(), key=lambda s: -len(words & set(re.findall(r"\w{3,}", (
            s["name"] + " " + s.get("description", "")).lower()))))
        names += [s["name"] for s in ranked[:2] if words & set(re.findall(r"\w{3,}", (s["name"] + " " + s.get(
            "description", "")).lower()))]
        return [n for n in dict.fromkeys(names) if n][:2]

    async def call(self, spec: ToolSpec, args: dict, run: ToolRun) -> tuple[bool, str]:
        tool = spec.name.split(".", 1)[1]
        if tool == "check_identifiers":
            ids = [i for i in args.get("entity_ids", []) if isinstance(i, str) and run.case.entity(i)]
            return await self._check(run, ids)
        if tool == "add_and_check":
            return await self._add(run, str(args.get("entity_type", "")), str(args.get("value", "")))
        if tool == "search_sebi_register":
            return await self._register(run, str(args.get("name", "")), args.get("category"))
        if tool == "read_safety_note":
            body = self.skills.get(str(args.get("name", ""))) if self.skills else None
            return (True, body[:900]) if body else (False, "no such note")
        return False, f"unknown tool {spec.name}"

    async def _check(self, run: ToolRun, entity_ids: list[str]) -> tuple[bool, str]:
        steps = self._steps_for(run, entity_ids)
        if steps:
            run.on_plan()
        lines = []
        async for ev in self.executor.run(steps, run.case, run.budget):
            run.on_evidence(ev)
            codes = ", ".join(f"{s.code} ({self.config.t('en', f'signal.{s.code}')})" for s in ev.signals)
            who = ", ".join(e.placeholder or e.type for i in ev.entity_ids if (e := run.case.entity(i)))
            lines.append(f"{who} {ev.checker_id}: {ev.status}{' - ' + codes if codes else ''}")
        return True, "\n".join(lines) or "nothing new to check"

    def _steps_for(self, run: ToolRun, entity_ids: list[str]) -> list[PlanStep]:
        case = run.case
        allow = frozenset((self.config.modes.get(run.mode) or {}).get("allow_privacy", []))
        done, steps = case.ledger_keys(), []
        for eid in dict.fromkeys(entity_ids):
            entity = case.entity(eid)
            if entity is None:
                continue
            for checker in self.checkers.consumers_of(entity.type, run.mode, allow):
                if (checker.id, entity.norm_hash or entity.id) in done or not checker.should_run(entity, case):
                    continue
                steps.append(PlanStep(id=case.next_id("s"), checker_id=checker.id, entity_ids=[eid], family=checker.family))
            entity.planned = True
        case.plan.steps.extend(steps)
        if steps:
            case.plan.revision += 1
        return steps

    async def _add(self, run: ToolRun, entity_type: str, value: str) -> tuple[bool, str]:
        from satark.harness import guards

        case, value = run.case, value.strip()
        if known := [e.id for e in case.entities if e.placeholder and e.placeholder in value]:
            return await self._check(run, known)  # it pointed at a placeholder: that entity exists, check it
        said = case.masked_text + " " + next((t.text for t in reversed(case.turns) if t.role == "user"), "")
        if entity_type not in ADDABLE or len(value) < 3 or _norm(value) not in _norm(said):
            return False, "not added: copy the exact words from the message"
        new = self.pipeline.add_drafts(case, [EntityDraft(type=entity_type, value=value)], origin="llm")
        case.masked_text = guards.mask(case.masked_text, case)  # later prompts see a placeholder
        if not new:
            return False, "not added: already known or not a valid identifier"
        ok, checks = await self._check(run, [e.id for e in new])
        if entity_type == "party.name":  # a named firm or adviser: the register is the first thing to know
            checks += "\n" + (await self._register(run, value, None))[1]
        return ok, f"added {', '.join(e.placeholder or e.type for e in new)} ({entity_type})\n{checks}"

    async def _register(self, run: ToolRun, name: str, category: Any) -> tuple[bool, str]:
        from satark.harness import guards

        name = guards.unmask(name, run.case, "en")[:80].strip()  # the model sees [NAME_1]; the register needs the name
        if len(name) < 3:
            return False, "no name to search"
        rows = await asyncio.to_thread(self._search_registry, name, category if isinstance(category, str) else None)
        close = [r for r in rows if r.get("similarity", 0) >= 0.92]
        shown = "; ".join(f"{r['name']} ({r['reg_no']}, {r['category']}, {'valid' if r.get('valid') else 'expired'}, "
                          f"match {r.get('similarity')})" for r in (close or rows)[:2])
        return True, f"found in SEBI register: {'yes' if close else 'no'}{'; closest: ' + shown if shown else ''}"


def _checkable(e) -> bool:
    return e.type != "message.text" and not e.type.startswith("claim.") and e.cls != "P" and bool(e.placeholder)


def _norm(text: str) -> str:
    import unicodedata

    return " ".join(unicodedata.normalize("NFKC", text or "").replace("़", "").casefold().split())


# ---- any MCP server over stdio (plug-and-play) ------------------------------------------------------------------
class MCPToolset(Toolset):
    def __init__(self, name: str, cfg: dict) -> None:
        self.name = name
        self.command = [sys.executable if c == "{python}" else c for c in cfg.get("command", [])]
        passthrough = {k: v for k, v in os.environ.items() if k.startswith("SATARK_")}
        self.env = {**os.environ, **{k: str(v) for k, v in (cfg.get("env") or {}).items()}, **passthrough}
        self.privacy = cfg.get("privacy", "external")
        self.public_types = tuple(cfg.get("public_types") or ())
        # chat only (CONTRACTS Track C): a check may need any web result to spot a scam site; a
        # chat reply should only ever point the user at an official source. Empty = no filter.
        self.chat_domains = frozenset(d.lower() for d in (cfg.get("chat_domains") or ()))
        self.timeout_s = float(cfg.get("timeout_s", 10))
        self.tool_cfg: dict = cfg.get("tools") or {}
        self.session = None
        self._specs: list[ToolSpec] = []
        self._stack: AsyncExitStack | None = None

    def specs(self) -> list[ToolSpec]:
        return self._specs

    async def start(self) -> None:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        self._stack = AsyncExitStack()
        try:
            params = StdioServerParameters(command=self.command[0], args=self.command[1:], env=self.env)
            read, write = await self._stack.enter_async_context(stdio_client(params))
            self.session = await self._stack.enter_async_context(ClientSession(read, write))
            await asyncio.wait_for(self.session.initialize(), 20)
            listed = await asyncio.wait_for(self.session.list_tools(), 10)
            for t in listed.tools:
                if self.tool_cfg and t.name not in self.tool_cfg:
                    continue  # an allowlist: only the tools the config names
                c = self.tool_cfg.get(t.name) or {}
                self._specs.append(ToolSpec(
                    name=f"{self.name}.{t.name}", description=(t.description or "")[:300],
                    params=_attr(t, "input_schema", "inputSchema") or {}, toolset=self.name, privacy=self.privacy,
                    modes=frozenset(c.get("modes", ["check", "chat"])), max_calls=int(c.get("max_calls", 2)),
                    timeout_s=float(c.get("timeout_s", self.timeout_s))))
        except Exception as e:  # a broken server only removes its own tools
            self.error = f"{type(e).__name__}: {e}"[:200]
            self._specs = []
            log.warning("MCP toolset %s unavailable: %s", self.name, self.error)
            await self.close()
            return
        log.info("MCP toolset %s: %s", self.name, [s.name for s in self._specs])

    async def close(self) -> None:
        if self._stack is not None:
            stack, self._stack, self.session = self._stack, None, None
            try:
                await stack.aclose()
            except Exception as e:  # a server that died first must not break shutdown
                log.debug("MCP toolset %s close: %s", self.name, e)

    def suggest(self, run: ToolRun) -> list[Call]:
        calls = []
        for spec in self._specs:
            props, required = spec.params.get("properties", {}), spec.params.get("required", [])
            strings = [p for p in required if props.get(p, {}).get("type") == "string"]
            if len(strings) != 1:
                continue
            param = strings[0]
            short = spec.name.split(".", 1)[1]
            sources = ((self.tool_cfg.get(short) or {}).get("suggest") or {}).get(param) or _DEFAULT_SOURCES.get(param.lower(), ())
            for e in run.case.entities:
                if e.type in sources and e.placeholder and self._public(e):
                    calls.append(Call(spec.name, {param: e.placeholder}))
        return calls

    def _public(self, e) -> bool:
        return e.type in self.public_types and not (e.type == "party.name" and e.attrs.get("kind") == "person")

    def outgoing(self, args: dict, case: CaseState) -> dict | None:
        """Fill in placeholders of public identifiers, drop every other placeholder, then the PII tripwire."""
        from satark.harness import guards

        public = {e.placeholder: e.display for e in case.entities if e.placeholder and e.display and self._public(e)}

        def fill(v: Any) -> Any:
            if isinstance(v, str):
                v = _PLACEHOLDER.sub(lambda m: public.get(m.group(0), ""), v)
                return " ".join(v.split())
            if isinstance(v, list):
                return [fill(x) for x in v]
            if isinstance(v, dict):
                return {k: fill(x) for k, x in v.items()}
            return v

        out = fill(args)
        others = case.model_copy(update={"entities": [e for e in case.entities if e.placeholder not in public]})
        if guards.pii_leaks(json.dumps(out, ensure_ascii=False), others):
            return None
        return out

    async def call(self, spec: ToolSpec, args: dict, run: ToolRun) -> tuple[bool, str]:
        if self.session is None:
            return False, "tool server unavailable"
        sent = self.outgoing(args, run.case) if self.privacy == "external" else args
        if sent is None:
            return False, "blocked: the call would send personal data"
        if not any(isinstance(v, str) and v.strip() for v in sent.values()):
            return False, "nothing public to send"
        result = await self.session.call_tool(spec.name.split(".", 1)[1], sent)
        allowed = self.chat_domains if (run.mode == "chat" and self.chat_domains) else None
        return not _attr(result, "is_error", "isError"), _result_text(result, allowed)


def _attr(obj: Any, *names: str) -> Any:
    """MCP SDK 2.x uses snake_case fields (input_schema, is_error); 1.x used camelCase."""
    return next((getattr(obj, n) for n in names if hasattr(obj, n)), None)


def _domain_ok(url: str, allowed: frozenset[str]) -> bool:
    from satark.infra.norm import registrable_domain

    dom = (registrable_domain(url) or "").lower()
    return any(dom == a or dom.endswith(f".{a}") for a in allowed)


def _result_text(result, allowed_domains: frozenset[str] | None = None) -> str:
    data = _attr(result, "structured_content", "structuredContent")
    if data is None:  # many servers return JSON as text content instead of structured content
        texts = [getattr(c, "text", "") for c in result.content or []]
        try:
            data = json.loads(texts[0]) if len(texts) == 1 else None
        except (ValueError, TypeError):
            data = None
    if isinstance(data, dict) and set(data) == {"result"}:
        data = data["result"]
    if isinstance(data, dict) and isinstance(data.get("results"), list):
        if data.get("error"):
            return f"error: {data['error']}"
        rows = data["results"]
        if allowed_domains:
            rows = [r for r in rows if _domain_ok(r.get("url", ""), allowed_domains)]
        rows = rows[:5]
        if not rows:
            return "no results" if not allowed_domains else "no results from an official source"
        return "\n".join(f"{i}. {r.get('title', '')[:100]} - {r.get('snippet', '')[:220]} ({r.get('url', '')[:200]})"
                         for i, r in enumerate(rows, 1))
    if data is not None:
        return json.dumps(data, ensure_ascii=False)[:900]
    texts = [getattr(c, "text", "") for c in result.content or []]
    return "\n".join(t for t in texts if t)[:900] or "no result"


# ---- the registry -------------------------------------------------------------------------------------------
class ToolRegistry:
    def __init__(self, config, toolsets: list[Toolset]) -> None:
        self.config = config
        self.toolsets = toolsets
        cfg = config.tools or {}
        self.max_calls_per_run = int(cfg.get("max_calls_per_run", 6))
        self.menu_size = int(cfg.get("menu_size", 6))

    @classmethod
    def build(cls, config, network: bool, satark: Toolset | None) -> ToolRegistry:
        toolsets: list[Toolset] = []
        for name, cfg in ((config.tools or {}).get("toolsets") or {}).items():
            kind = cfg.get("kind")
            if kind == "builtin":
                if satark is not None:
                    toolsets.append(satark)
            elif kind == "mcp_stdio":
                if cfg.get("needs_network") and not network:
                    continue
                toolsets.append(MCPToolset(name, cfg))
            else:
                log.warning("toolset %s: unknown kind %r", name, kind)
        return cls(config, toolsets)

    async def start(self) -> None:
        await asyncio.gather(*(ts.start() for ts in self.toolsets))

    async def close(self) -> None:
        for ts in reversed(self.toolsets):
            await ts.close()

    def status(self) -> dict[str, str]:
        return {ts.name: (ts.error or ("on" if ts.specs() else "no tools")) for ts in self.toolsets}

    def _index(self) -> dict[str, tuple[ToolSpec, Toolset]]:
        return {spec.name: (spec, ts) for ts in self.toolsets for spec in ts.specs()}

    def specs(self, mode: str) -> list[ToolSpec]:
        return [spec for spec, _ in self._index().values() if mode in spec.modes]

    def refusal(self, call: Call, run: ToolRun) -> str | None:
        found = self._index().get(call.tool)
        if found is None:
            return "no such tool"
        spec = found[0]
        if run.mode not in spec.modes:
            return "not allowed here"
        if run.counts[call.tool] >= spec.max_calls or sum(run.counts.values()) >= self.max_calls_per_run:
            return "call budget used up"
        if call.key in run.done_keys():
            return "already done"
        return None

    def menu(self, run: ToolRun) -> list[Call]:
        """Suggested next lookups: what the toolsets propose for this case, minus anything not allowed or done."""
        seen, out = set(), []
        for ts in self.toolsets:
            for call in ts.suggest(run):
                if call.key not in seen and self.refusal(call, run) is None:
                    seen.add(call.key)
                    out.append(call)
        return out[: self.menu_size]

    def label(self, call: Call, case: CaseState, lang: str) -> str:
        from satark.harness import guards

        arg = next((v for v in call.args.values() if isinstance(v, str) and v.strip()), "")
        if not arg and isinstance(call.args.get("entity_ids"), list):
            arg = ", ".join(e.placeholder for i in call.args["entity_ids"] if (e := case.entity(i)) and e.placeholder)
        arg = guards.unmask(arg, case, lang)[:60]
        text = self.config.t(lang, f"tool.{call.tool}", arg=arg)
        return text if text != f"tool.{call.tool}" else f"{call.tool}: {arg}"

    async def run(self, calls: list[Call], run: ToolRun) -> list[Observation]:
        """Run calls in parallel under policy; every result is stored on the case as an observation."""
        from satark.harness import guards

        accepted, keys = [], set()
        for call in calls:
            if call.key not in keys and self.refusal(call, run) is None:
                keys.add(call.key)
                run.counts[call.tool] += 1
                accepted.append(call)

        async def one(call: Call) -> Observation:
            spec, ts = self._index()[call.tool]
            call_id = run.case.next_id("c")
            label = self.label(call, run.case, run.lang)
            run.emit("tool_status", {"tool": call.tool, "status": "start", "label": label, "call_id": call_id})
            try:
                ok, text = await asyncio.wait_for(ts.call(spec, call.args, run), spec.timeout_s)
            except TimeoutError:
                ok, text = False, "timed out"
            except Exception as e:  # a tool error is an observation, never a crash
                log.warning("tool %s failed: %s", call.tool, type(e).__name__)
                ok, text = False, f"error: {type(e).__name__}"
            from satark.harness.proof import tool_proof

            proof = tool_proof(call.tool, label, ok, guards.unmask(text, run.case, run.lang), self.config, run.lang)
            run.emit("tool_status", {"tool": call.tool, "status": "end", "label": label, "call_id": call_id, "ok": ok,
                                     "proof": proof})
            return Observation(id=run.case.next_id("obs"), tool=call.tool, label=label, ok=ok, step=run.step,
                               key=call.key, text=guards.mask(text, run.case)[:900])

        observations = list(await asyncio.gather(*(one(c) for c in accepted)))
        run.case.observations.extend(observations)
        return observations
