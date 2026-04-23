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
    svc.project_configs = {}
    svc._hooks = MagicMock()
    return svc


def test_plan_start_refused_when_needs_ui_and_design_not_ready():
    """Critical guard: needs_ui=True requires design_precondition_met=True."""
    svc = _make_svc()
    r = Requirement(
        req_id="REQ-X-001", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED,
        needs_ui=True,
        design_precondition_met=False,  # design phase hasn't completed
    )
    svc.requirements[r.req_id] = r

    import pytest
    with pytest.raises(ValueError, match="design"):
        svc.plan_start(r.req_id, plan_doc_id="d", plan_doc_url="u")


def test_plan_start_allowed_when_needs_ui_and_design_ready():
    """Happy path: design completed -> plan can start."""
    svc = _make_svc()
    r = Requirement(
        req_id="REQ-X-002", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED,
        needs_ui=True,
        design_precondition_met=True,  # design phase completed
        design_status=DesignStatus.READY,
    )
    svc.requirements[r.req_id] = r

    # Should not raise
    result = svc.plan_start(r.req_id, plan_doc_id="d", plan_doc_url="u")
    # The plan state should have advanced (returns the Requirement)
    assert result is r


def test_plan_start_allowed_when_needs_ui_false():
    """Non-UI REQ: guard doesn't apply; plan can start regardless of design flag."""
    svc = _make_svc()
    r = Requirement(
        req_id="REQ-X-003", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED,
        needs_ui=False,
        design_precondition_met=False,
    )
    svc.requirements[r.req_id] = r

    # Should not raise
    svc.plan_start(r.req_id, plan_doc_id="d", plan_doc_url="u")


def test_card_handler_send_plan_author_start_blocks_when_design_not_ready():
    """UI-layer guard: the card 'send_plan_author_start' action must refuse
    when needs_ui=True and design_precondition_met=False."""
    from requirement_workflow_v12.service_app import CoordinatorRuntimeApp

    r = Requirement(
        req_id="REQ-X-004", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED,
        needs_ui=True,
        design_precondition_met=False,
    )
    app = CoordinatorRuntimeApp.__new__(CoordinatorRuntimeApp)
    app.service = MagicMock()
    app.service.get_requirement = MagicMock(return_value=r)
    app.gateway = MagicMock()

    status, resp = app._handle_card_action_payload({
        "action": {"value": {"action": "send_plan_author_start", "req_id": "REQ-X-004"}},
        "operator": {"operator_id": {"user_id": "u1"}},
    })
    assert status == 200
    toast = resp.get("toast", {})
    assert toast.get("type") == "error"
    # The error message should mention design (not just generic "wrong status")
    assert "设计" in toast.get("content", "") or "design" in toast.get("content", "").lower()

    # Gateway should not have been called to create plan doc
    app.gateway.create_plan_document.assert_not_called()


def test_card_handler_send_plan_author_start_allowed_when_needs_ui_false():
    """Non-UI REQ: card handler proceeds normally."""
    from requirement_workflow_v12.service_app import CoordinatorRuntimeApp

    r = Requirement(
        req_id="REQ-X-005", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED,
        needs_ui=False,
    )
    app = CoordinatorRuntimeApp.__new__(CoordinatorRuntimeApp)
    app.service = MagicMock()
    app.service.get_requirement = MagicMock(return_value=r)
    app.service.plan_start = MagicMock()
    app.gateway = MagicMock()
    created_doc = MagicMock(document_id="d", document_url="u")
    app.gateway.create_plan_document.return_value = created_doc
    app._save_state = MagicMock()
    app._resolve_operator_receive_target = MagicMock(return_value=("u", "user_id"))
    app._build_plan_author_handoff_text = MagicMock(return_value="text")

    status, resp = app._handle_card_action_payload({
        "action": {"value": {"action": "send_plan_author_start", "req_id": "REQ-X-005"}},
        "operator": {"operator_id": {"user_id": "u1"}},
    })
    # Allowed (not blocked by design guard); may still have other validation
    # so we check only that the design-specific rejection message is NOT present
    content = resp.get("toast", {}).get("content", "")
    assert "设计" not in content


def test_plan_start_guard_error_message_is_clear():
    """Error message should help the user understand what to do."""
    svc = _make_svc()
    r = Requirement(
        req_id="REQ-X-006", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED,
        needs_ui=True,
        design_precondition_met=False,
    )
    svc.requirements[r.req_id] = r

    import pytest
    with pytest.raises(ValueError) as exc_info:
        svc.plan_start(r.req_id, plan_doc_id="d", plan_doc_url="u")
    msg = str(exc_info.value)
    # Message should mention design (in either Chinese or English)
    assert "设计" in msg or "design" in msg.lower()
    # Should mention readiness / precondition concept
    assert any(keyword in msg for keyword in ["READY", "完成", "precondition"])
