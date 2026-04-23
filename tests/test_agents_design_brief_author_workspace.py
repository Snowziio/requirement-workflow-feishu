"""Verify the deploy workspace for design-brief-author agent."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = REPO_ROOT / "deploy" / "openclaw" / "workspace" / "agents" / "design-brief-author"


def test_workspace_directory_exists():
    assert WORKSPACE.is_dir()


def test_skill_md_is_symlink_to_docs_agents():
    skill_path = WORKSPACE / "SKILL.md"
    assert skill_path.is_symlink(), "SKILL.md in workspace must be a symlink"
    target = os.readlink(skill_path)
    assert "docs/agents/design-brief-author/SKILL.md" in target


def test_identity_md_exists_and_has_skill_name():
    identity = WORKSPACE / "IDENTITY.md"
    assert identity.is_file()
    text = identity.read_text(encoding="utf-8")
    assert "design-brief-author" in text
    assert "单轮" in text or "single-turn" in text.lower()


def test_boilerplate_files_exist():
    for name in ["SOUL.md", "AGENTS.md", "TOOLS.md", "USER.md"]:
        path = WORKSPACE / name
        assert path.is_file(), f"{name} missing from workspace"
        assert len(path.read_text(encoding="utf-8")) > 100, f"{name} too small"
