"""Tests for the unified project_context_change dispatcher."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.project_context_apply import (  # noqa: E402
    ProjectContextApplyError,
    apply_project_context_change,
)


def test_dispatch_architecture_executor_returns_updated_files():
    original = {"docs/ARCHITECTURE.md": "## Storage\n\nTBD\n"}
    change = {
        "summary": "Add Redis storage",
        "changes": [
            {
                "artifact": "architecture",
                "section_path": "## Storage",
                "before": "## Storage\n\nTBD\n",
                "after": "## Storage\n\nRedis 24h TTL\n",
                "rationale": "D1",
            },
        ],
    }
    updated = apply_project_context_change(original_files=original, change=change)
    assert "Redis 24h TTL" in updated["docs/ARCHITECTURE.md"]


def test_environments_and_skill_md_executors_are_noop_stubs_that_log(caplog):
    original = {
        "project/environments.yaml": "environments:\n  dev: {}\n",
        "SKILL.md": "# x\n",
    }
    change = {
        "summary": "Add staging env + update SKILL",
        "changes": [
            {"artifact": "environments", "section_path": "staging", "before": "", "after": "...", "rationale": "D2"},
            {"artifact": "skill_md", "section_path": "## Testing", "before": "", "after": "...", "rationale": "D3"},
        ],
    }
    with caplog.at_level("WARNING"):
        updated = apply_project_context_change(original_files=original, change=change)
    assert updated["project/environments.yaml"] == "environments:\n  dev: {}\n"
    assert updated["SKILL.md"] == "# x\n"
    warnings = " ".join(r.message for r in caplog.records)
    assert "environments" in warnings
    assert "skill_md" in warnings


def test_dispatch_rejects_unknown_artifact():
    with pytest.raises(ProjectContextApplyError, match="unknown artifact"):
        apply_project_context_change(
            original_files={},
            change={
                "summary": "x",
                "changes": [
                    {
                        "artifact": "mystery",
                        "section_path": "",
                        "before": "",
                        "after": "",
                        "rationale": "D",
                    }
                ],
            },
        )
