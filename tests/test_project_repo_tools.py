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
        def commit_spec_md(self, artifacts): ...
        def cleanup_failed_branch(self, project_repo, branch): ...
        def bootstrap_project_repo(
            self,
            *,
            template_owner,
            template_repo,
            new_owner,
            new_name,
            populate_files,
            populate_commit_message,
            collaborator_username,
        ): ...
        def project_repo_commit(self, *, project_repo, message, files): ...

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


def test_fetch_project_context_wraps_non_404_gateway_error():
    """Non-404 gateway errors (5xx, auth, etc.) still bubble up as ProjectRepoError.

    Only the 404 case has graceful fallback (see fallback tests below); other
    HTTP failures must surface so transform halts and operators investigate.
    """
    gw = MagicMock()
    gw.fetch_file_sha = MagicMock(
        side_effect=GitHubGatewayError(500, "server error"),
    )
    tools = GitHubProjectRepoTools(gw)

    with pytest.raises(ProjectRepoError) as exc_info:
        tools.fetch_project_context("acme/repo")
    assert "fetch_project_context" in str(exc_info.value)
    assert exc_info.value.__cause__ is not None
    assert exc_info.value.recoverable is False


def _mock_gateway_with_md_fallback(*, has_registry: bool):
    """Bootstrap-style repo: only docs/ARCHITECTURE.md exists; root yamls 404.

    If ``has_registry`` is False, acm-registry.yaml is also missing — the
    common state for a freshly bootstrapped project that has no ACs yet.
    """
    files: dict[str, tuple[str, str]] = {
        "docs/ARCHITECTURE.md": ("md-sha", "# Architecture\n\nProject overview.\n"),
    }
    if has_registry:
        files["acm-registry.yaml"] = ("reg-sha", "version: 3\nentries: []\n")

    def _side_effect(repo, ref, path):
        if path in files:
            return files[path]
        raise GitHubGatewayError(404, f"{path} not found")

    gw = MagicMock()
    gw.fetch_file_sha = MagicMock(side_effect=_side_effect)
    return gw


def test_fetch_project_context_falls_back_to_architecture_md_on_yaml_404():
    """Bug 3 option A: when ARCHITECTURE.yaml is missing, read docs/ARCHITECTURE.md.

    Bootstrap produces docs/ARCHITECTURE.md (the v3.0 SOT) and never writes
    ARCHITECTURE.yaml. Spec-transformer was hard-failing on this drift.
    """
    gw = _mock_gateway_with_md_fallback(has_registry=True)
    tools = GitHubProjectRepoTools(gw)

    ctx = tools.fetch_project_context("acme/repo")

    assert ctx.arch_sha == "md-sha"
    assert ctx.arch_text == "# Architecture\n\nProject overview.\n"
    assert ctx.registry_sha == "reg-sha"
    assert ctx.registry_text == "version: 3\nentries: []\n"


def test_fetch_project_context_empty_registry_when_acm_registry_404():
    """Bug 3 option A: when acm-registry.yaml is missing, return empty registry.

    Fresh-bootstrapped projects have no ACs yet — no registry file is
    expected. ``parse_active_slice`` and ``parse`` already handle empty
    text gracefully, so empty strings are a safe sentinel.
    """
    gw = _mock_gateway_with_md_fallback(has_registry=False)
    tools = GitHubProjectRepoTools(gw)

    ctx = tools.fetch_project_context("acme/repo")

    assert ctx.arch_sha == "md-sha"
    assert ctx.registry_sha == ""
    assert ctx.registry_text == ""


def test_fetch_project_context_raises_when_both_architecture_paths_missing():
    """If neither ARCHITECTURE.yaml nor docs/ARCHITECTURE.md exists, fail loud.

    A repo with no architecture artifact at all is not a valid project —
    Bootstrap was never completed. Callers (spec-transformer) should halt.
    """
    gw = MagicMock()
    gw.fetch_file_sha = MagicMock(
        side_effect=GitHubGatewayError(404, "not found"),
    )
    tools = GitHubProjectRepoTools(gw)

    with pytest.raises(ProjectRepoError) as exc_info:
        tools.fetch_project_context("acme/repo")
    assert "fetch_project_context" in str(exc_info.value)
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


# ── _parse_repo normalization (Bitable may store full URL) ──────────────
#
# Bitable's project_repo column historically stored shorthand "owner/repo",
# but Bootstrap writes it as "https://github.com/owner/repo". Without
# normalization every facade method splitting on "/" breaks silently into
# a nonsensical GitHub API path (owner="https:", repo="/github.com/...").
# These tests lock the helper's contract and the three facade call sites.

from requirement_workflow_v12.project_repo.tools import _parse_repo


def test_parse_repo_accepts_shorthand():
    assert _parse_repo("acme/repo") == ("acme", "repo")


def test_parse_repo_accepts_https_github_url():
    assert _parse_repo("https://github.com/acme/repo") == ("acme", "repo")


def test_parse_repo_strips_trailing_git_suffix():
    assert _parse_repo("https://github.com/acme/repo.git") == ("acme", "repo")


def test_parse_repo_accepts_ssh_url():
    assert _parse_repo("git@github.com:acme/repo.git") == ("acme", "repo")


def test_parse_repo_rejects_invalid_input():
    with pytest.raises(ValueError):
        _parse_repo("not-a-repo")
    with pytest.raises(ValueError):
        _parse_repo("")
    with pytest.raises(ValueError):
        _parse_repo("a/b/c")


def _url_artifacts():
    return SpecArtifacts(
        project_repo="https://github.com/acme/repo",
        branch="spec/REQ-P-1",
        base_branch="main",
        files={"docs/specs/REQ-P-1/design.md": "# Design\n"},
        commit_message="feat(spec): REQ-P-1",
        pr_title="Spec: REQ-P-1",
        pr_body="body",
    )


def test_commit_spec_artifacts_normalizes_full_url_project_repo():
    gw = MagicMock()
    gw.create_branch = MagicMock(return_value="head-sha")
    gw.commit_spec_pr_files = MagicMock(return_value="commit-sha")
    gw.open_pull_request = MagicMock(
        return_value={"number": 42, "html_url": "https://gh/pr/42"},
    )
    tools = GitHubProjectRepoTools(gw)

    tools.commit_spec_artifacts("REQ-P-1", _url_artifacts())

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


def test_commit_spec_artifacts_url_failure_cleans_branch_with_shorthand():
    gw = MagicMock()
    gw.create_branch = MagicMock(return_value="head-sha")
    gw.commit_spec_pr_files = MagicMock(
        side_effect=GitHubGatewayError(409, "conflict"),
    )
    gw.delete_branch = MagicMock(return_value=None)
    tools = GitHubProjectRepoTools(gw)

    with pytest.raises(ProjectRepoError):
        tools.commit_spec_artifacts("REQ-P-1", _url_artifacts())

    gw.delete_branch.assert_called_once_with("acme/repo", "spec/REQ-P-1")


def test_cleanup_failed_branch_normalizes_url():
    gw = MagicMock()
    gw.delete_branch = MagicMock(return_value=None)
    tools = GitHubProjectRepoTools(gw)

    tools.cleanup_failed_branch("https://github.com/acme/repo", "spec/REQ-P-1")

    gw.delete_branch.assert_called_once_with("acme/repo", "spec/REQ-P-1")


def test_fetch_project_context_normalizes_url():
    gw = _mock_gateway()
    tools = GitHubProjectRepoTools(gw)

    ctx = tools.fetch_project_context("https://github.com/acme/repo")

    # The stored project_repo on the returned context is the caller's string
    # (we don't rewrite it); but gateway calls must see shorthand.
    for call in gw.fetch_file_sha.call_args_list:
        args, _kwargs = call
        assert args[0] == "acme/repo", f"unexpected repo arg: {args[0]!r}"
    assert ctx.arch_sha == "arch-sha"


def test_commit_plan_artifacts_normalizes_url_project_repo():
    from requirement_workflow_v12.project_repo.types import PlanArtifacts

    gw = MagicMock()
    gw.commit_files = MagicMock(return_value="plan-commit-sha")
    tools = GitHubProjectRepoTools(gw)

    result = tools.commit_plan_artifacts(PlanArtifacts(
        project_repo="https://github.com/acme/repo",
        req_id="REQ-P-1",
        plan_md_content="# Plan\n",
        project_context_change=None,
        commit_message="docs(plan): REQ-P-1",
    ))

    assert result.commit_sha == "plan-commit-sha"
    gw.commit_files.assert_called_once()
    kwargs = gw.commit_files.call_args.kwargs
    assert kwargs["owner"] == "acme"
    assert kwargs["repo"] == "repo"
    assert kwargs["branch"] == "main"


def test_commit_spec_md_normalizes_url_project_repo():
    from requirement_workflow_v12.project_repo.types import SpecMdArtifacts

    gw = MagicMock()
    gw.commit_files = MagicMock(return_value="spec-commit-sha")
    tools = GitHubProjectRepoTools(gw)

    result = tools.commit_spec_md(SpecMdArtifacts(
        project_repo="https://github.com/acme/repo",
        req_id="REQ-P-1",
        spec_md_content="# Spec\n",
        commit_message="docs(spec): REQ-P-1",
    ))

    assert result.commit_sha == "spec-commit-sha"
    kwargs = gw.commit_files.call_args.kwargs
    assert kwargs["owner"] == "acme"
    assert kwargs["repo"] == "repo"
