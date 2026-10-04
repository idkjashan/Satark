"""SkillStore: front matter + body parsing, missing folder (LLD §6.7)."""

from __future__ import annotations

from satark.harness.skills import SkillStore


def _write_skill(root, rel_path: str, description: str, body: str) -> None:
    path = root / rel_path / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\nname: {rel_path}\ndescription: {description}\n---\n{body}\n", encoding="utf-8")


def test_index_and_get_a_skill(tmp_path):
    _write_skill(tmp_path, "policy/no-tips", "Never give stock tips", "Body text with --- inside it too.")
    store = SkillStore(tmp_path)

    assert store.index() == [{"name": "policy/no-tips", "description": "Never give stock tips"}]
    assert store.get("policy/no-tips") == "Body text with --- inside it too."


def test_get_missing_skill_is_none(tmp_path):
    store = SkillStore(tmp_path)
    assert store.get("scams/does-not-exist") is None
    assert store.index() == []


def test_missing_root_folder_is_empty(tmp_path):
    store = SkillStore(tmp_path / "no-such-dir")
    assert store.index() == []
    assert store.get("anything") is None
