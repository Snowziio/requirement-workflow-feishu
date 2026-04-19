import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from requirement_workflow_v12.coordinator_service import CoordinatorService
from requirement_workflow_v12.models import Requirement, WorkflowStatus
from requirement_workflow_v12.plan_state_machine import (
    PlanStatus, PlanPhase, DesignStatus,
)
from requirement_workflow_v12.spec_state_machine import SpecStatus


def _req_with_both(svc, req_id="REQ-P-1"):
    r = Requirement(
        req_id=req_id, name="n", project="P", summary="s", creator="c",
    )
    r.status = WorkflowStatus.APPROVED
    r.plan_status = PlanStatus.READY
    r.plan_phase = PlanPhase.FINAL_REVIEW_PENDING
    r.plan_pr_url = "commit-sha"
    r.spec_status = SpecStatus.DRAFTING
    r.spec_document_id = "spec-doc"
    r.spec_pr_url = "pr-url"
    svc.requirements[req_id] = r
    return r


def test_plan_restart_clears_plan_and_spec_state():
    svc = CoordinatorService()
    r = _req_with_both(svc)

    svc.plan_restart(r.req_id)

    assert r.plan_status is None
    assert r.plan_phase is None
    assert r.plan_pr_url == ""
    assert r.pending_plan_draft is None
    assert r.spec_status is None
    assert r.spec_document_id == ""
    assert r.spec_pr_url == ""


def test_plan_restart_rejected_when_never_started():
    svc = CoordinatorService()
    r = Requirement(
        req_id="R", name="n", project="P", summary="s", creator="c",
    )
    r.status = WorkflowStatus.APPROVED
    svc.requirements[r.req_id] = r
    with pytest.raises(ValueError):
        svc.plan_restart(r.req_id)


def test_design_restart_clears_design_plan_and_spec():
    svc = CoordinatorService()
    r = _req_with_both(svc)
    r.design_status = DesignStatus.READY

    svc.design_restart(r.req_id)

    assert r.design_status is None
    assert r.plan_status is None
    assert r.spec_status is None


def test_design_restart_rejected_when_never_started():
    svc = CoordinatorService()
    r = Requirement(
        req_id="R", name="n", project="P", summary="s", creator="c",
    )
    r.status = WorkflowStatus.APPROVED
    svc.requirements[r.req_id] = r
    with pytest.raises(ValueError):
        svc.design_restart(r.req_id)
