"""Unit tests for the layer-3 ProjectRepoTools facade.

Verifies translation correctness from domain verbs to the underlying
GitHubGateway primitives, plus error-wrapping semantics.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest
from dataclasses import FrozenInstanceError

from requirement_workflow_v12.project_repo.tools import (
    ProjectRepoError, ProjectRepoTools,
)
from requirement_workflow_v12.project_repo.types import (
    ProjectContext, SpecArtifacts, CommitRef, PrRef, RepoRef,
)


def test_domain_types_are_frozen_dataclasses():
    ctx = ProjectContext(
        project_repo="o/r", arch_sha="a", arch_text="kind: x\n",
        registry_sha="b", registry_text="version: 3\n",
    )
    with pytest.raises(FrozenInstanceError):
        ctx.arch_sha = "mutated"  # type: ignore[misc]

    art = SpecArtifacts(
        project_repo="o/r", branch="spec/REQ-P-1", base_branch="main",
        files={"a.md": "x"}, commit_message="m", pr_title="t", pr_body="b",
    )
    assert art.files["a.md"] == "x"

    assert CommitRef(sha="s", branch="b").sha == "s"
    assert PrRef(number=1, html_url="u", head_sha="s", branch="b").number == 1
    assert RepoRef(
        owner="o", name="r", html_url="u",
        default_branch="main", initial_commit_sha="s",
    ).owner == "o"


def test_project_repo_error_carries_recoverable_flag():
    err = ProjectRepoError("boom", recoverable=True)
    assert err.recoverable is True
    assert "boom" in str(err)

    default = ProjectRepoError("x")
    assert default.recoverable is False


def test_project_repo_tools_is_protocol():
    class Dummy:
        def fetch_project_context(self, project_repo): ...
        def commit_spec_artifacts(self, req_id, artifacts): ...
        def cleanup_failed_branch(self, project_repo, branch): ...

    assert isinstance(Dummy(), ProjectRepoTools)
