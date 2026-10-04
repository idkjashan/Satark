"""Runtime: builds every shared object once at startup (CONTRACTS §5).

Fails closed on a broken config (`ConfigError` from `load_config` or `registry.validate`
propagates - LLD §10.5): never serve from a half-loaded config. A missing registry database is
different - it disables db-needing checkers and sets `ready=False` with a reason, but the process
still starts, so `/healthz` and `/v1/meta` work while an operator fixes it.
"""

from __future__ import annotations

import asyncio
import functools
import logging
from dataclasses import dataclass

from satark.checkers.registry import CheckerRegistry
from satark.config import Config, Settings, load_config
from satark.harness.cases import CaseStore
from satark.harness.events import EventBus
from satark.harness.execute import DagExecutor
from satark.harness.explain import Explainer
from satark.harness.join import Joiner
from satark.harness.knowledge import KnowledgeBase
from satark.harness.models import ModelRouter
from satark.harness.orchestrator import Orchestrator
from satark.harness.plan import RulePlanner
from satark.harness.respond import Responder
from satark.harness.score import Scorer
from satark.harness.scope_router import ScopeRouter, load_encoder
from satark.harness.skills import SkillStore
from satark.infra.db import RegistryDB

log = logging.getLogger(__name__)


@dataclass
class Runtime:
    settings: Settings
    config: Config
    registry: CheckerRegistry
    db: RegistryDB | None
    http: object
    router: ModelRouter
    bus: EventBus
    cases: CaseStore
    orchestrator: Orchestrator
    ready: bool
    not_ready_reason: str | None
    tools: object = None  # tools.ToolRegistry: the agent loop's toolsets (MCP servers live as long as the runtime)


# Built once per process (read-only after build): embedding the examples and the content takes ~3 s.
_router = functools.cache(ScopeRouter.build)
_knowledge = functools.cache(KnowledgeBase.build)


async def build_runtime(settings: Settings) -> Runtime:
    config = load_config(settings.root, validate=True)  # ConfigError propagates: fail closed

    registry = CheckerRegistry()
    registry.discover()

    db: RegistryDB | None = None
    ready, reason = True, None
    try:
        db = RegistryDB(settings.db_path)
    except FileNotFoundError:
        ready, reason = False, "registry database missing"

    registry.validate(config, env=settings.env, db_ok=db is not None)  # ConfigError propagates too

    http = _build_http(settings.network)
    router = ModelRouter(config.models, settings.env)
    pipeline = _build_pipeline(config, router, db)
    skills = SkillStore(settings.root / "skills")
    bus = EventBus()
    cases = CaseStore()

    planner = RulePlanner(registry, config)
    executor = DagExecutor(registry, config, pipeline, db=db, http=http, secrets=settings.env, network=settings.network)
    scorer = Scorer(config, registry)
    joiner = Joiner(registry, scorer, config)
    explain_timeout = float(((config.modes.get("check") or {}).get("limits") or {}).get("explain_timeout_s", 3))
    explainer = Explainer(router, config, skills, explain_timeout_s=explain_timeout)

    # The scope router and the knowledge base (chat RAG) share one fastembed encoder, loaded
    # once here and run off the event loop thread from then on (it's synchronous CPU work).
    encoder = await asyncio.to_thread(load_encoder)
    scope_router = await asyncio.to_thread(_router, config.root / "config" / "routes.yaml", encoder)
    knowledge = await asyncio.to_thread(_knowledge, config.root, encoder)
    responder = Responder(router, config, registry, db, planner, executor, pipeline, skills, scorer, config.faq,
                          scope_router=scope_router, knowledge=knowledge)

    from satark.harness.agent import AgentLoop
    from satark.harness.assess import Assessor
    from satark.harness.tools import SatarkTools, ToolRegistry
    from satark.harness.vision import ImageReader

    satark_cfg = ((config.tools or {}).get("toolsets") or {}).get("satark") or {}
    satark_tools = SatarkTools(satark_cfg, config, registry, executor, pipeline, skills, responder._search_registry)
    tools = ToolRegistry.build(config, settings.network, satark_tools)
    await tools.start()  # spawns the MCP servers once; a broken server only removes its own tools
    responder.agent = AgentLoop(router, config, tools, role="respond")
    responder.tools = tools
    orchestrator = Orchestrator(
        config, registry, pipeline, router, bus, cases, planner, executor, joiner, scorer, explainer, responder,
        assessor=Assessor(router, config, registry), agent=AgentLoop(router, config, tools, role="assess"),
        vision=ImageReader(router, config),
        vision_allowed=settings.env.get("SATARK_LLM_VISION", "") in ("1", "true", "yes"),
    )

    return Runtime(
        settings=settings, config=config, registry=registry, db=db, http=http, router=router, bus=bus, cases=cases,
        orchestrator=orchestrator, ready=ready, not_ready_reason=reason, tools=tools,
    )


async def close_runtime(rt: Runtime) -> None:
    if rt.tools is not None:
        await rt.tools.close()
    if rt.http is not None:
        await _close_http(rt.http)
    if rt.db is not None:
        rt.db.close()


def _build_http(network: bool):
    try:
        from satark.infra.http import SafeHttpClient
    except ImportError:  # pragma: no cover - C's module
        return None
    return SafeHttpClient(network=network)


async def _close_http(http) -> None:
    # note: SafeHttpClient has no public close/aclose today, so fall back to its private
    # httpx client; add a public aclose() there and drop this fallback.
    for name in ("aclose", "close"):
        fn = getattr(http, name, None)
        if fn is not None:
            result = fn()
            if asyncio.iscoroutine(result):
                await result
            return
    client = getattr(http, "_client", None)
    if client is not None and hasattr(client, "aclose"):
        await client.aclose()


def _build_pipeline(config, router, db):
    try:
        from satark.harness.extract import ExtractorPipeline
    except ImportError:  # pragma: no cover - A's module
        return None
    return ExtractorPipeline(config, router, db)
