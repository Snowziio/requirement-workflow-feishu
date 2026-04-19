import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.project_repo import PlanArtifacts, PlanCommitResult


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
