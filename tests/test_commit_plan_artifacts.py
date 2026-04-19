import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from unittest.mock import MagicMock
from requirement_workflow_v12.project_repo import (
    GitHubProjectRepoTools, ProjectRepoError,
    PlanArtifacts, PlanCommitResult,
)


def test_commit_plan_artifacts_without_architecture_commits_plan_md_to_main():
    gw = MagicMock()
    gw.commit_files.return_value = "sha-commit-1"
    tools = GitHubProjectRepoTools(gateway=gw)
    artifacts = PlanArtifacts(
        project_repo="owner/repo",
        req_id="REQ-P-1",
        plan_md_content="---\nreq_id: REQ-P-1\n---\n# Plan\n",
        architecture_change=None,
        commit_message="plan(REQ-P-1): initial plan",
    )
    result = tools.commit_plan_artifacts(artifacts)

    assert isinstance(result, PlanCommitResult)
    assert result.commit_sha == "sha-commit-1"
    assert result.branch == "main"
    assert result.plan_md_path == "docs/specs/REQ-P-1/plan.md"
    assert result.architecture_updated is False

    gw.commit_files.assert_called_once()
    kwargs = gw.commit_files.call_args.kwargs
    assert kwargs["owner"] == "owner"
    assert kwargs["repo"] == "repo"
    assert kwargs["branch"] == "main"
    files = list(kwargs["files"])
    assert len(files) == 1
    assert files[0].path == "docs/specs/REQ-P-1/plan.md"
    assert "req_id: REQ-P-1" in files[0].content
    gw.fetch_file_sha.assert_not_called()


def test_commit_plan_artifacts_with_architecture_commits_both_files_atomically():
    gw = MagicMock()
    gw.fetch_file_sha.return_value = (
        "arch-sha-before",
        "# Architecture\n\n## 会话存储\n\n旧方案。\n",
    )
    gw.commit_files.return_value = "sha-commit-2"

    tools = GitHubProjectRepoTools(gateway=gw)
    arch_change = {
        "summary": "Add Redis",
        "changes": [{
            "section_path": "## 会话存储",
            "before": "## 会话存储\n\n旧方案。",
            "after": "## 会话存储\n\n新方案：Redis。",
            "rationale": "D1",
        }],
        "authorized": True,
        "authorized_by": "u-1",
        "authorized_at": "2026-04-19T10:00:00Z",
    }
    artifacts = PlanArtifacts(
        project_repo="owner/repo",
        req_id="REQ-P-2",
        plan_md_content="---\nreq_id: REQ-P-2\n---\n",
        architecture_change=arch_change,
        commit_message="plan(REQ-P-2): add Redis",
    )

    result = tools.commit_plan_artifacts(artifacts)

    assert result.architecture_updated is True
    gw.fetch_file_sha.assert_called_once_with("owner/repo", "main", "ARCHITECTURE.md")
    kwargs = gw.commit_files.call_args.kwargs
    files = list(kwargs["files"])
    paths = sorted(fc.path for fc in files)
    assert paths == ["ARCHITECTURE.md", "docs/specs/REQ-P-2/plan.md"]
    arch_content = next(fc.content for fc in files if fc.path == "ARCHITECTURE.md")
    assert "Redis" in arch_content
    assert "旧方案" not in arch_content


def test_commit_plan_artifacts_raises_recoverable_on_architecture_conflict():
    gw = MagicMock()
    gw.fetch_file_sha.return_value = (
        "arch-sha",
        "# Architecture\n\n## 会话存储\n\n实际内容不同。\n",
    )
    tools = GitHubProjectRepoTools(gateway=gw)
    arch_change = {
        "changes": [{
            "section_path": "## 会话存储",
            "before": "## 会话存储\n\n期望的旧内容。",
            "after": "## 会话存储\n\nRedis。",
            "rationale": "D1",
        }],
    }
    artifacts = PlanArtifacts(
        project_repo="owner/repo", req_id="REQ-P-3",
        plan_md_content="---\n---\n",
        architecture_change=arch_change,
        commit_message="m",
    )
    import pytest
    with pytest.raises(ProjectRepoError) as exc_info:
        tools.commit_plan_artifacts(artifacts)
    assert exc_info.value.recoverable is True
    gw.commit_files.assert_not_called()


def test_commit_plan_artifacts_raises_nonrecoverable_on_commit_failure():
    from requirement_workflow_v12.github_gateway import GitHubGatewayError
    gw = MagicMock()
    gw.commit_files.side_effect = GitHubGatewayError(500, "boom")
    tools = GitHubProjectRepoTools(gateway=gw)
    artifacts = PlanArtifacts(
        project_repo="o/r", req_id="REQ-P-4",
        plan_md_content="---\n---\n",
        architecture_change=None,
        commit_message="m",
    )
    import pytest
    with pytest.raises(ProjectRepoError) as exc_info:
        tools.commit_plan_artifacts(artifacts)
    assert exc_info.value.recoverable is False


def test_plan_artifacts_is_frozen():
    a = PlanArtifacts(
        project_repo="o/r",
        req_id="REQ-P-1",
        plan_md_content="---\nreq_id: REQ-P-1\n---\n",
        architecture_change=None,
        commit_message="plan: REQ-P-1",
    )
    import pytest
    with pytest.raises(Exception):
        a.plan_md_content = "changed"  # type: ignore[misc]


def test_plan_commit_result_fields():
    r = PlanCommitResult(
        commit_sha="abc123",
        branch="main",
        plan_md_path="docs/specs/REQ-P-1/plan.md",
        architecture_updated=False,
    )
    assert r.commit_sha == "abc123"
    assert r.branch == "main"
    assert r.plan_md_path.endswith("plan.md")
    assert r.architecture_updated is False
