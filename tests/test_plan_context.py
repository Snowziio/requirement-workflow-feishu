import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest
from unittest.mock import MagicMock

from requirement_workflow_v12.coordinator_service import CoordinatorService
from requirement_workflow_v12.models import Requirement, WorkflowStatus
from requirement_workflow_v12.plan_context import (
    PlanContextBuilder, PlanContextGateError,
)
from requirement_workflow_v12.plan_state_machine import PlanStatus
from requirement_workflow_v12.project_config import ProjectConfig


def _req(svc, req_id="REQ-P-1"):
    r = Requirement(
        req_id=req_id, name="n", project="P", summary="s", creator="c",
    )
    r.status = WorkflowStatus.APPROVED
    svc.requirements[req_id] = r
    svc.project_configs["P"] = ProjectConfig(
        category="web", template_version="v1",
        architecture_doc_id="doc-a", architecture_doc_url="https://x",
        tech_stack={"backend": "python"}, github_repo_url="owner/repo",
    )
    return r


def test_plan_context_returns_expected_fields_when_plan_none():
    svc = CoordinatorService()
    r = _req(svc)
    builder = PlanContextBuilder(service=svc)

    ctx = builder.build(r.req_id)

    assert ctx["req_id"] == "REQ-P-1"
    assert ctx["project"] == "P"
    assert ctx["needs_ui"] is False
    assert ctx["tech_stack"] == {"backend": "python"}
    assert ctx["project_repo"] == "owner/repo"
    assert ctx["architecture_doc_url"] == "https://x"


def test_plan_context_rejected_when_not_approved():
    svc = CoordinatorService()
    r = _req(svc)
    r.status = WorkflowStatus.DRAFTING
    builder = PlanContextBuilder(service=svc)
    with pytest.raises(PlanContextGateError):
        builder.build(r.req_id)


def test_plan_context_rejected_when_already_ready():
    svc = CoordinatorService()
    r = _req(svc)
    r.plan_status = PlanStatus.READY
    builder = PlanContextBuilder(service=svc)
    with pytest.raises(PlanContextGateError):
        builder.build(r.req_id)


def test_plan_context_allowed_when_drafting():
    svc = CoordinatorService()
    r = _req(svc)
    r.plan_status = PlanStatus.DRAFTING
    builder = PlanContextBuilder(service=svc)
    ctx = builder.build(r.req_id)
    assert ctx["req_id"] == "REQ-P-1"


def test_plan_context_allowed_when_needs_ui_true_and_no_design():
    """MVP (2026-04-21): plan_start no longer couples to needs_ui/design_status;
    plan_context must stay consistent with that — it should NOT gate on design."""
    svc = CoordinatorService()
    r = _req(svc)
    r.needs_ui = True
    # design_status stays None
    builder = PlanContextBuilder(service=svc)
    ctx = builder.build(r.req_id)
    assert ctx["req_id"] == "REQ-P-1"
    assert ctx["needs_ui"] is True
