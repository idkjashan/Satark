"""CheckerRegistry: discovers checker plugins and validates them against config (LLD §10.5, §10.6)."""

from __future__ import annotations

import importlib
import logging
import os
import pkgutil
from importlib.metadata import entry_points
from typing import TYPE_CHECKING

from satark.checkers.base import FAMILIES, BaseChecker, registered_classes

if TYPE_CHECKING:
    from satark.config import Config

log = logging.getLogger(__name__)

_SKIP_MODULES = {"base", "registry"}


class ConfigError(Exception):
    """Startup validation failed: the app must not start (fail closed)."""


class CheckerRegistry:
    def __init__(self) -> None:
        self.checkers: dict[str, BaseChecker] = {}
        self.disabled: dict[str, str] = {}  # checker id -> reason (e.g. "missing secret ABUSECH_AUTH_KEY")
        self._by_type: dict[str, list[BaseChecker]] = {}

    # ---- discovery -------------------------------------------------------------------
    def discover(self, package: str = "satark.checkers", entry_point_group: str = "satark.checkers") -> None:
        """Import every module under `package` (the decorator registers classes), then entry points."""
        pkg = importlib.import_module(package)
        for mod in pkgutil.walk_packages(pkg.__path__, prefix=f"{package}."):
            if mod.name.rsplit(".", 1)[-1] not in _SKIP_MODULES:
                importlib.import_module(mod.name)
        for ep in entry_points(group=entry_point_group):
            ep.load()
        for cls in registered_classes():
            self.add(cls())

    def add(self, checker: BaseChecker) -> None:
        if checker.id in self.checkers:
            if type(self.checkers[checker.id]) is type(checker):
                return  # the same class imported twice
            raise ConfigError(f"duplicate checker id {checker.id!r}")
        self.checkers[checker.id] = checker

    # ---- validation (fail closed) -------------------------------------------------------
    def validate(self, config: Config, env: dict[str, str] | None = None, db_ok: bool = True) -> None:
        """Cross-check every checker against entities.yaml and signals.yaml.

        Contract errors raise ConfigError. A missing secret or a missing DB only disables
        the checker (it never stops the app)."""
        env = dict(os.environ) if env is None else env
        errors: list[str] = []
        for c in self.checkers.values():
            if not c.id or c.family not in FAMILIES:
                errors.append(f"{c.id or type(c).__name__}: bad id or family {c.family!r}")
            for t in c.consumes:
                if t not in config.entities:
                    errors.append(f"{c.id}: consumes unknown entity type {t!r}")
                elif c.privacy != "local" and config.entities[t].get("class") in ("U", "R"):
                    # LLD §10.5 rule 2: user data and role-dependent types never leave the server
                    errors.append(f"{c.id}: privacy {c.privacy} may not consume {config.entities[t]['class']}-class {t!r}")
            for code in c.produces:
                if code not in config.signals:
                    errors.append(f"{c.id}: produces unknown signal {code!r}")
            if c.privacy not in ("local", "public_only", "identifier"):
                errors.append(f"{c.id}: bad privacy {c.privacy!r}")
            for need in c.needs:
                if need.startswith("secret:") and not env.get(need.split(":", 1)[1]):
                    self.disabled[c.id] = f"missing secret {need.split(':', 1)[1]}"
                elif need == "db" and not db_ok:
                    self.disabled[c.id] = "registry database missing"
        if errors:
            raise ConfigError("checker validation failed:\n  " + "\n  ".join(errors))
        for cid, why in self.disabled.items():
            log.warning("checker disabled: %s (%s)", cid, why)
        self._build_index()

    def _build_index(self) -> None:
        self._by_type = {}
        for c in self.checkers.values():
            if c.id in self.disabled:
                continue
            for t in c.consumes:
                self._by_type.setdefault(t, []).append(c)
        for lst in self._by_type.values():
            lst.sort(key=lambda c: (not c.decisive, c.cost, c.id))  # decisive first, then cheap

    # ---- queries --------------------------------------------------------------------------
    def get(self, checker_id: str) -> BaseChecker | None:
        return self.checkers.get(checker_id)

    def all(self) -> list[BaseChecker]:
        return list(self.checkers.values())

    def consumers_of(self, entity_type: str, mode: str, allow_privacy: frozenset[str] | set[str]) -> list[BaseChecker]:
        """Enabled checkers for an entity type, allowed in `mode` and its privacy levels; decisive first."""
        return [
            c
            for c in self._by_type.get(entity_type, [])
            if mode in c.modes and c.privacy in allow_privacy
        ]
