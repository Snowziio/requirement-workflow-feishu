import sys
from pathlib import Path
from unittest.mock import MagicMock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.models import Requirement, WorkflowStatus
from requirement_workflow_v12.plan_state_machine import DesignStatus
from requirement_workflow_v12.coordinator_service import CoordinatorService


def _make_svc() -> CoordinatorService:
    svc = CoordinatorService.__new__(CoordinatorService)
    svc.requirements = {}
    svc._hooks = MagicMock()
    return svc


def test_design_start_from_approved_needs_ui_true_goes_drafting():
    svc = _make_svc()
    r = Requirement(
        req_id="REQ-X-001", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
    )
    svc.requirements[r.req_id] = r
    result = svc.design_start(
        r.req_id,
        design_doc_id="d-1",
        design_doc_url="https://feishu/d/1",
    )
    assert result.design_status is DesignStatus.DRAFTING
    assert result.design_doc_id == "d-1"
    assert result.design_doc_url == "https://feishu/d/1"
    svc._hooks.fire_enter.assert_called_once()


def test_design_start_rejects_not_approved():
    svc = _make_svc()
    r = Requirement(
        req_id="REQ-X-002", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.CREATED, needs_ui=True,
    )
    svc.requirements[r.req_id] = r
    import pytest
    with pytest.raises(ValueError, match="APPROVED"):
        svc.design_start(r.req_id, design_doc_id="d", design_doc_url="u")


def test_design_start_rejects_needs_ui_false():
    svc = _make_svc()
    r = Requirement(
        req_id="REQ-X-003", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=False,
    )
    svc.requirements[r.req_id] = r
    import pytest
    with pytest.raises(ValueError, match="needs_ui"):
        svc.design_start(r.req_id, design_doc_id="d", design_doc_url="u")


def test_design_start_fires_exit_hook_for_prev_status():
    """Even though entry status is typically None, hook contract is
    fire_exit(prev) then fire_enter(next). Verify the contract."""
    svc = _make_svc()
    r = Requirement(
        req_id="REQ-X-004", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
    )
    svc.requirements[r.req_id] = r
    svc.design_start(r.req_id, design_doc_id="d", design_doc_url="u")
    svc._hooks.fire_exit.assert_called_once()
    svc._hooks.fire_enter.assert_called_once()
