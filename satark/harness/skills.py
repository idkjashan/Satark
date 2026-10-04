"""SkillStore: loads skills/<area>/<name>/SKILL.md (YAML front matter + Markdown body), LLD §6.7."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_DELIM = "---"


def _parse(text: str) -> tuple[dict[str, Any], str]:
    if text.startswith(_DELIM):
        parts = text.split(_DELIM, 2)
        if len(parts) == 3:
            return (yaml.safe_load(parts[1]) or {}), parts[2].strip()
    return {}, text.strip()


class SkillStore:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self._skills: dict[str, tuple[dict[str, Any], str]] = {}
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self.root.is_dir():
            return
        for path in sorted(self.root.glob("*/*/SKILL.md")):
            name = path.relative_to(self.root).parent.as_posix()
            self._skills[name] = _parse(path.read_text(encoding="utf-8"))

    def index(self) -> list[dict[str, str]]:
        self._load()
        return [{"name": name, "description": meta.get("description", "")} for name, (meta, _) in sorted(self._skills.items())]

    def get(self, name: str) -> str | None:
        self._load()
        entry = self._skills.get(name)
        return entry[1] if entry else None
