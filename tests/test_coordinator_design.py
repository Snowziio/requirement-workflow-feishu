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


def test_design_submit_requires_drafting():
    svc = _make_svc()
    r = Requirement(
        req_id="REQ-X-010", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
        design_status=None,
    )
    svc.requirements[r.req_id] = r
    import pytest
    with pytest.raises(ValueError):
        svc.design_submit(r.req_id, archive_path="design/archive/REQ-X-010_x/",
                          pages_touched=[])


def test_design_submit_transitions_to_submit_pending_review():
    svc = _make_svc()
    r = Requirement(
        req_id="REQ-X-011", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
        design_status=DesignStatus.DRAFTING,
    )
    svc.requirements[r.req_id] = r
    out = svc.design_submit(
        r.req_id,
        archive_path="design/archive/REQ-X-011_foo/",
        pages_touched=[{"display_name": "Upload", "action": "new"}],
    )
    assert out.design_status is DesignStatus.SUBMIT_PENDING_REVIEW
    assert out.pending_design_handoff is not None
    assert out.pending_design_handoff["archive_path"] == "design/archive/REQ-X-011_foo/"
    assert out.pending_design_handoff["pages_touched"] == [
        {"display_name": "Upload", "action": "new"}
    ]


def test_design_submit_records_timestamp():
    svc = _make_svc()
    r = Requirement(
        req_id="REQ-X-012", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
        design_status=DesignStatus.DRAFTING,
    )
    svc.requirements[r.req_id] = r
    svc.design_submit(
        r.req_id, archive_path="design/archive/REQ-X-012_foo/", pages_touched=[],
    )
    assert "submitted_at" in r.pending_design_handoff
    assert r.pending_design_handoff["submitted_at"]


def test_design_submit_fires_hooks_in_order():
    svc = _make_svc()
    r = Requirement(
        req_id="REQ-X-013", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
        design_status=DesignStatus.DRAFTING,
    )
    svc.requirements[r.req_id] = r
    svc.design_submit(r.req_id, archive_path="x", pages_touched=[])
    # Exit called first with DRAFTING, enter called with SUBMIT_PENDING_REVIEW
    svc._hooks.fire_exit.assert_called_once()
    svc._hooks.fire_enter.assert_called_once()
    # Call order: exit.call_args[0][0] should be DRAFTING; enter.call_args[0][0] should be SUBMIT_PENDING_REVIEW
    assert svc._hooks.fire_exit.call_args[0][0] is DesignStatus.DRAFTING
    assert svc._hooks.fire_enter.call_args[0][0] is DesignStatus.SUBMIT_PENDING_REVIEW


def test_design_final_approve_transitions_to_ready_and_unlocks_plan():
    svc = _make_svc()
    r = Requirement(
        req_id="REQ-X-020", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
        design_status=DesignStatus.SUBMIT_PENDING_REVIEW,
        pending_design_handoff={
            "archive_path": "design/archive/REQ-X-020_x/",
            "pages_touched": [],
            "submitted_at": "2026-04-23T00:00:00+00:00",
        },
    )
    svc.requirements[r.req_id] = r
    out = svc.design_final_approve(r.req_id, approved_by="tech-lead-1")
    assert out.design_status is DesignStatus.READY
    assert out.design_precondition_met is True
    assert out.pending_design_handoff is None     # cleared after approval
    assert out.design_archive_path == "design/archive/REQ-X-020_x/"


def test_design_final_approve_rejects_non_submit_pending_review():
    svc = _make_svc()
    r = Requirement(
        req_id="REQ-X-021", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
        design_status=DesignStatus.DRAFTING,
    )
    svc.requirements[r.req_id] = r
    import pytest
    with pytest.raises(ValueError):
        svc.design_final_approve(r.req_id, approved_by="x")


def test_design_final_reject_returns_to_drafting():
    svc = _make_svc()
    r = Requirement(
        req_id="REQ-X-022", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
        design_status=DesignStatus.SUBMIT_PENDING_REVIEW,
        pending_design_handoff={
            "archive_path": "design/archive/REQ-X-022_x/",
            "pages_touched": [],
            "submitted_at": "2026-04-23T00:00:00+00:00",
        },
    )
    svc.requirements[r.req_id] = r
    out = svc.design_final_reject(r.req_id, reason="配色偏差")
    assert out.design_status is DesignStatus.DRAFTING
    assert out.design_precondition_met is False
    # handoff kept for reference; reason recorded
    assert out.pending_design_handoff is not None
    assert out.pending_design_handoff["reject_reason"] == "配色偏差"


def test_design_final_reject_rejects_non_submit_pending_review():
    svc = _make_svc()
    r = Requirement(
        req_id="REQ-X-023", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
        design_status=DesignStatus.DRAFTING,
    )
    svc.requirements[r.req_id] = r
    import pytest
    with pytest.raises(ValueError):
        svc.design_final_reject(r.req_id, reason="x")


def test_design_final_approve_without_pending_handoff_still_transitions():
    """Edge case: if pending_design_handoff is None for some reason, the transition
    should still succeed; design_archive_path just stays empty."""
    svc = _make_svc()
    r = Requirement(
        req_id="REQ-X-024", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
        design_status=DesignStatus.SUBMIT_PENDING_REVIEW,
        pending_design_handoff=None,
    )
    svc.requirements[r.req_id] = r
    out = svc.design_final_approve(r.req_id, approved_by="x")
    assert out.design_status is DesignStatus.READY
    assert out.design_archive_path == ""
