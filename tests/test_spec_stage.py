import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.models import WorkflowStatus, Requirement
from requirement_workflow_v12.state_machine import Event, apply_event


def test_spec_start_transitions_approved_to_spec_drafting():
    decision = apply_event(WorkflowStatus.APPROVED, Event.SPEC_START)
    assert decision.allowed
    assert decision.next_status == WorkflowStatus.SPEC_DRAFTING


def test_ai_review_pass_in_spec_drafting_transitions_to_spec_locked():
    decision = apply_event(WorkflowStatus.SPEC_DRAFTING, Event.AI_REVIEW_PASS)
    assert decision.allowed
    assert decision.next_status == WorkflowStatus.SPEC_LOCKED


def test_ai_review_reject_in_spec_drafting_stays_spec_drafting():
    decision = apply_event(WorkflowStatus.SPEC_DRAFTING, Event.AI_REVIEW_REJECT)
    assert decision.allowed
    assert decision.next_status == WorkflowStatus.SPEC_DRAFTING


def test_spec_start_blocked_in_non_approved_status():
    decision = apply_event(WorkflowStatus.DRAFTING, Event.SPEC_START)
    assert not decision.allowed


def test_requirement_has_spec_fields():
    req = Requirement(req_id="REQ-X-001", name="test", project="X", summary="s", creator="c")
    assert hasattr(req, "spec_document_id")
    assert hasattr(req, "spec_document_url")
    assert hasattr(req, "spec_review_summary")
    assert req.spec_document_id == ""
    assert req.spec_document_url == ""
    assert req.spec_review_summary == ""
