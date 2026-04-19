"""End-to-end PLANNING phase: APPROVED → outline → plan_submit with
architecture → authorize → READY → spec-context returns plan_md_content."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from unittest.mock import MagicMock

from requirement_workflow_v12.coordinator_service import CoordinatorService
from requirement_workflow_v12.models import Requirement, WorkflowStatus
from requirement_workflow_v12.plan_state_machine import (
    PlanStatus, PlanPhase,
)
from requirement_workflow_v12.project_config import ProjectConfig
from requirement_workflow_v12.project_repo import PlanCommitResult
from requirement_workflow_v12.spec_context import SpecContextBuilder


def test_planning_e2e_with_architecture_change():
    svc = CoordinatorService()

    svc.project_configs["P"] = ProjectConfig(
        category="web", template_version="v1",
        architecture_doc_id="a", architecture_doc_url="https://doc/a",
        tech_stack={"backend": "py"}, github_repo_url="owner/repo",
    )

    tools = MagicMock()
    tools.commit_plan_artifacts.return_value = PlanCommitResult(
        commit_sha="sha-final",
        branch="main",
        plan_md_path="docs/specs/REQ-P-1/plan.md",
        architecture_updated=True,
    )
    svc.configure_plan_hooks(tools=tools)

    r = Requirement(
        req_id="REQ-P-1", name="n", project="P", summary="s", creator="c",
    )
    r.status = WorkflowStatus.APPROVED
    svc.requirements[r.req_id] = r

    svc.plan_start(r.req_id)
    assert r.plan_status is PlanStatus.DRAFTING
    assert r.plan_phase is PlanPhase.OUTLINE_PENDING

    svc.set_plan_outline(
        r.req_id,
        [
            {"id": "D1", "title": "Storage", "problem": "..."},
            {"id": "D2", "title": "Auth", "problem": "..."},
        ],
    )
    assert r.plan_phase is PlanPhase.DECISIONS_IN_PROGRESS

    plan_md = """---
schema_version: "1.0"
req_id: "REQ-P-1"
decisions:
  - id: D1
    chosen: "A"
  - id: D2
    chosen: "B"
---
"""
    arch_change = {
        "summary": "add storage",
        "changes": [{
            "section_path": "## Storage",
            "before": "",
            "after": "## Storage\n\nRedis.",
            "rationale": "D1",
        }],
        "authorized": False,
    }
    svc.plan_submit(
        r.req_id, plan_md_content=plan_md, architecture_change=arch_change,
    )
    assert r.plan_status is PlanStatus.AUTH_PENDING

    svc.plan_authorize(r.req_id, authorized_by="ou-user")
    assert r.plan_status is PlanStatus.READY
    assert r.plan_pr_url == "sha-final"
    assert r.pending_plan_draft is None
    tools.commit_plan_artifacts.assert_called_once()

    svc._fetch_plan_md = MagicMock(return_value=plan_md)
    gw = MagicMock()
    gw.fetch_document_revision.return_value = "rev"
    builder = SpecContextBuilder(svc, gw)

    result = builder.build(r.req_id)

    assert result.context["plan_md_content"] == plan_md
    assert result.context["plan_decision_ids"] == ["D1", "D2"]


def test_planning_e2e_without_architecture_change():
    svc = CoordinatorService()
    svc.project_configs["P"] = ProjectConfig(
        category="web", template_version="v1",
        architecture_doc_id="a", architecture_doc_url="",
        tech_stack={}, github_repo_url="o/r",
    )
    tools = MagicMock()
    tools.commit_plan_artifacts.return_value = PlanCommitResult(
        commit_sha="sha", branch="main",
        plan_md_path="docs/specs/REQ-P-2/plan.md",
        architecture_updated=False,
    )
    svc.configure_plan_hooks(tools=tools)

    r = Requirement(
        req_id="REQ-P-2", name="n", project="P", summary="s", creator="c",
    )
    r.status = WorkflowStatus.APPROVED
    svc.requirements[r.req_id] = r

    svc.plan_start(r.req_id)
    svc.plan_submit(
        r.req_id, plan_md_content="---\nreq_id: REQ-P-2\n---\n",
        architecture_change=None,
    )

    assert r.plan_status is PlanStatus.READY
    tools.commit_plan_artifacts.assert_called_once()
