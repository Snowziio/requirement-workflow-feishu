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
