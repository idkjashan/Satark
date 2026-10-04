"""Settings (environment) and Config (YAML/JSON registries), loaded once at startup.

Config validation fails closed (ConfigError): the app refuses to start on a broken
config rather than answering from a half-loaded one (LLD §10.5).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from satark.checkers.registry import ConfigError

ROOT = Path(__file__).resolve().parent.parent  # the repository root


@dataclass(frozen=True)
class Settings:
    """Everything that comes from the environment. Secrets never live in YAML."""

    root: Path = ROOT
    db_path: Path = ROOT / "data" / "registry.db"
    web_dist: Path = ROOT / "web" / "dist"
    env: dict[str, str] = field(default_factory=dict)  # a copy of os.environ (secrets, model ids)
    network: bool = True  # False = live-network checkers return unknown("offline") (tests, demos)

    @classmethod
    def from_env(cls, **overrides: Any) -> Settings:
        env = dict(os.environ)
        root = Path(env.get("SATARK_ROOT", ROOT))
        kw: dict[str, Any] = {
            "root": root,
            "db_path": Path(env.get("SATARK_DB", root / "data" / "registry.db")),
            "web_dist": Path(env.get("SATARK_WEB_DIST", root / "web" / "dist")),
            "env": env,
            "network": env.get("SATARK_OFFLINE", "") not in ("1", "true", "yes"),
        }
        kw.update(overrides)
        return cls(**kw)


def _yaml(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _json(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


@dataclass
class Config:
    """All registries. Plain dicts on purpose: the YAML shape is the contract (docs/CONTRACTS.md)."""

    root: Path
    entities: dict[str, dict[str, Any]]
    signals: dict[str, dict[str, Any]]
    scoring: dict[str, Any]
    modes: dict[str, dict[str, Any]]
    models: dict[str, Any]
    languages: dict[str, Any]
    sources: dict[str, dict[str, Any]]
    brands: list[dict[str, Any]]
    phone_rules: dict[str, Any]
    claim_rules: dict[str, Any]
    lexicons: dict[str, Any]  # file stem -> parsed YAML (redflags, guards, ...)
    portals: dict[str, Any]  # content/portals.json: {"portals": {...}, "actions": {...}}
    i18n: dict[str, dict[str, str]]  # lang -> flat key -> text (content/i18n/<lang>.json)
    faq: dict[str, Any] = field(default_factory=dict)  # content/faq.json (offline chat answers)
    tools: dict[str, Any] = field(default_factory=dict)  # config/tools.yaml (agent-loop toolsets, MCP servers)

    @property
    def enabled_langs(self) -> list[str]:
        return [code for code, spec in self.languages.get("languages", {}).items() if spec.get("enabled", True)]

    def t(self, lang: str, key: str, **fmt: Any) -> str:
        """Translate a content key; fall back to English, then to the key itself."""
        text = self.i18n.get(lang, {}).get(key) or self.i18n.get("en", {}).get(key) or key
        return text.format(**fmt) if fmt else text

    def signal(self, code: str) -> dict[str, Any]:
        return self.signals.get(code, {})


def load_config(root: Path = ROOT, validate: bool = True) -> Config:
    cfg_dir, content = root / "config", root / "content"
    opt = lambda p, d: _yaml(p) if p.exists() else d  # noqa: E731
    i18n: dict[str, dict[str, str]] = {}
    for p in sorted((content / "i18n").glob("*.json")):
        # files are <lang>.json or <part>.<lang>.json (e.g. ui.hi.json, content.hi.json); merged per language
        lang = p.stem.split(".")[-1]
        i18n.setdefault(lang, {}).update(_json(p))
    lexicons = {p.stem: _yaml(p) for p in sorted((cfg_dir / "lexicons").glob("*.yaml"))}
    cfg = Config(
        root=root,
        entities=_yaml(cfg_dir / "entities.yaml"),
        signals=_yaml(cfg_dir / "signals.yaml"),
        scoring=_yaml(cfg_dir / "scoring.yaml"),
        modes=_yaml(cfg_dir / "modes.yaml"),
        models=opt(cfg_dir / "models.yaml", {}),
        languages=_yaml(cfg_dir / "languages.yaml"),
        sources=opt(cfg_dir / "sources.yaml", {}),
        brands=opt(cfg_dir / "brands.yaml", {}).get("brands", []),
        phone_rules=opt(cfg_dir / "phone_rules.yaml", {}),
        claim_rules=opt(cfg_dir / "claim_rules.yaml", {}),
        lexicons=lexicons,
        portals=_json(content / "portals.json") if (content / "portals.json").exists() else {"portals": {}, "actions": {}},
        i18n=i18n,
        faq=_json(content / "faq.json") if (content / "faq.json").exists() else {},
        tools=opt(cfg_dir / "tools.yaml", {}),
    )
    if validate:
        validate_config(cfg)
    return cfg


_WEIGHTS = {"critical", "high", "medium", "low"}
_POLARITIES = {"risk", "assurance", "info", "flag"}


def validate_config(cfg: Config) -> None:
    """Cross-reference checks that need no code (LLD §10.5 rules 3-4). Checker checks live in the registry."""
    errors: list[str] = []
    placeholders: set[str] = set()
    for t, spec in cfg.entities.items():
        if spec.get("class") not in ("U", "C", "P", "R"):
            errors.append(f"entity {t}: class must be U, C, P or R")
        ph = spec.get("placeholder")
        if ph:
            if ph in placeholders:
                errors.append(f"entity {t}: duplicate placeholder {ph}")
            placeholders.add(ph)
        for pat in spec.get("patterns", []) or []:
            rx = pat.get("re", "") if isinstance(pat, dict) else pat  # plain string or {re, context, window}
            try:
                re.compile(rx)
                if isinstance(pat, dict) and pat.get("context"):
                    re.compile(pat["context"])
            except re.error as e:
                errors.append(f"entity {t}: bad pattern {rx!r}: {e}")
    actions = cfg.portals.get("actions", {})
    sims = {"S1", "S2", "S3"}
    for code, spec in cfg.signals.items():
        pol = spec.get("polarity")
        if pol not in _POLARITIES:
            errors.append(f"signal {code}: polarity must be one of {_POLARITIES}")
        if pol == "risk" and spec.get("weight") not in _WEIGHTS:
            errors.append(f"signal {code}: risk signals need a weight in {_WEIGHTS}")
        for a in spec.get("actions", []) or []:
            if actions and a not in actions:
                errors.append(f"signal {code}: unknown action {a!r}")
        if spec.get("simulator") and spec["simulator"] not in sims:
            errors.append(f"signal {code}: unknown simulator {spec['simulator']!r}")
        for s in spec.get("suppressed_by", []) or []:
            if s not in cfg.signals:
                errors.append(f"signal {code}: suppressed_by unknown code {s!r}")
        if pol in ("risk", "assurance", "info") and cfg.i18n:
            for lang in cfg.enabled_langs:
                if f"signal.{code}" not in cfg.i18n.get(lang, {}):
                    errors.append(f"signal {code}: no title 'signal.{code}' in content/i18n for {lang!r}")
    for lvl, acts in (cfg.scoring.get("default_actions") or {}).items():
        for a in acts:
            if actions and a not in actions:
                errors.append(f"scoring default_actions {lvl}: unknown action {a!r}")
    for name, mode in cfg.modes.items():
        for p in mode.get("allow_privacy", []):
            if p not in ("local", "public_only", "identifier"):
                errors.append(f"mode {name}: bad privacy level {p!r}")
    if errors:
        raise ConfigError("config validation failed:\n  " + "\n  ".join(errors))
