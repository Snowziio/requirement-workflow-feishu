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
        def commit_plan_artifacts(self, artifacts): ...
        def cleanup_failed_branch(self, project_repo, branch): ...

    assert isinstance(Dummy(), ProjectRepoTools)


# ── GitHubProjectRepoTools.fetch_project_context ────────────────────────
from unittest.mock import MagicMock

from requirement_workflow_v12.github_gateway import GitHubGatewayError
from requirement_workflow_v12.project_repo.tools import GitHubProjectRepoTools


def _mock_gateway():
    gw = MagicMock()
    gw.fetch_file_sha = MagicMock(side_effect=lambda repo, ref, path: {
        "ARCHITECTURE.yaml": ("arch-sha", "kind: Architecture\n"),
        "acm-registry.yaml": ("reg-sha", "version: 3\n"),
    }[path])
    return gw


def test_fetch_project_context_combines_two_files():
    tools = GitHubProjectRepoTools(_mock_gateway())

    ctx = tools.fetch_project_context("acme/repo")

    assert ctx.project_repo == "acme/repo"
    assert ctx.arch_sha == "arch-sha"
    assert ctx.arch_text == "kind: Architecture\n"
    assert ctx.registry_sha == "reg-sha"
    assert ctx.registry_text == "version: 3\n"


import logging


def test_cleanup_failed_branch_delegates_to_gateway():
    gw = MagicMock()
    gw.delete_branch = MagicMock(return_value=None)
    tools = GitHubProjectRepoTools(gw)

    tools.cleanup_failed_branch("acme/repo", "spec/REQ-P-1")

    gw.delete_branch.assert_called_once_with("acme/repo", "spec/REQ-P-1")


def test_cleanup_failed_branch_swallows_gateway_error(caplog):
    gw = MagicMock()
    gw.delete_branch = MagicMock(
        side_effect=GitHubGatewayError(500, "server err"),
    )
    tools = GitHubProjectRepoTools(gw)

    with caplog.at_level(logging.WARNING):
        tools.cleanup_failed_branch("acme/repo", "spec/REQ-P-1")

    assert "cleanup_failed_branch" in caplog.text
    assert "spec/REQ-P-1" in caplog.text


def test_fetch_project_context_wraps_gateway_error():
    gw = MagicMock()
    gw.fetch_file_sha = MagicMock(
        side_effect=GitHubGatewayError(404, "not found"),
    )
    tools = GitHubProjectRepoTools(gw)

    with pytest.raises(ProjectRepoError) as exc_info:
        tools.fetch_project_context("acme/repo")
    assert "fetch_project_context" in str(exc_info.value)
    assert exc_info.value.__cause__ is not None
    assert exc_info.value.recoverable is False


# ── GitHubProjectRepoTools.commit_spec_artifacts ────────────────────────

def _happy_artifacts():
    return SpecArtifacts(
        project_repo="acme/repo",
        branch="spec/REQ-P-1",
        base_branch="main",
        files={"docs/specs/REQ-P-1/design.md": "# Design\n"},
        commit_message="feat(spec): REQ-P-1",
        pr_title="Spec: REQ-P-1",
        pr_body="body",
    )


def test_commit_spec_artifacts_happy_path_returns_pr_ref():
    gw = MagicMock()
    gw.create_branch = MagicMock(return_value="head-sha-of-main")
    gw.commit_spec_pr_files = MagicMock(return_value="commit-sha")
    gw.open_pull_request = MagicMock(
        return_value={"number": 42, "html_url": "https://gh/pr/42"},
    )
    tools = GitHubProjectRepoTools(gw)

    pr = tools.commit_spec_artifacts("REQ-P-1", _happy_artifacts())

    assert pr.number == 42
    assert pr.html_url == "https://gh/pr/42"
    assert pr.head_sha == "commit-sha"
    assert pr.branch == "spec/REQ-P-1"
    gw.create_branch.assert_called_once_with(
        owner="acme", repo="repo",
        branch="spec/REQ-P-1", from_branch="main",
    )
    gw.commit_spec_pr_files.assert_called_once_with(
        "acme/repo", "spec/REQ-P-1",
        {"docs/specs/REQ-P-1/design.md": "# Design\n"},
        "feat(spec): REQ-P-1",
    )
    gw.open_pull_request.assert_called_once_with(
        owner="acme", repo="repo",
        head_branch="spec/REQ-P-1", base_branch="main",
        title="Spec: REQ-P-1", body="body",
    )


def test_commit_spec_artifacts_on_pr_failure_cleans_branch_and_raises():
    gw = MagicMock()
    gw.create_branch = MagicMock(return_value="head-sha")
    gw.commit_spec_pr_files = MagicMock(return_value="commit-sha")
    gw.open_pull_request = MagicMock(
        side_effect=GitHubGatewayError(422, "validation failed"),
    )
    gw.delete_branch = MagicMock(return_value=None)
    tools = GitHubProjectRepoTools(gw)

    with pytest.raises(ProjectRepoError) as exc_info:
        tools.commit_spec_artifacts("REQ-P-1", _happy_artifacts())

    assert "REQ-P-1" in str(exc_info.value)
    assert exc_info.value.__cause__ is not None
    assert exc_info.value.recoverable is False
    gw.delete_branch.assert_called_once_with("acme/repo", "spec/REQ-P-1")


def test_commit_spec_artifacts_on_commit_failure_cleans_branch():
    gw = MagicMock()
    gw.create_branch = MagicMock(return_value="head-sha")
    gw.commit_spec_pr_files = MagicMock(
        side_effect=GitHubGatewayError(409, "conflict"),
    )
    gw.delete_branch = MagicMock(return_value=None)
    tools = GitHubProjectRepoTools(gw)

    with pytest.raises(ProjectRepoError):
        tools.commit_spec_artifacts("REQ-P-1", _happy_artifacts())

    gw.delete_branch.assert_called_once()
