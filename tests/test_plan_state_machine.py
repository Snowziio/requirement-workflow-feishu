import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.plan_state_machine import (
    PlanStatus, PlanEvent, PlanPhase,
    DesignStatus, DesignEvent,
    apply_plan_event, apply_design_event,
)


def test_plan_start_from_none_goes_drafting():
    d = apply_plan_event(None, PlanEvent.PLAN_START)
    assert d.allowed is True
    assert d.next_status is PlanStatus.DRAFTING


def test_plan_start_from_drafting_rejected():
    d = apply_plan_event(PlanStatus.DRAFTING, PlanEvent.PLAN_START)
    assert d.allowed is False


def test_plan_submit_with_architecture_change_goes_auth_pending():
    d = apply_plan_event(
        PlanStatus.DRAFTING, PlanEvent.PLAN_SUBMIT,
        has_architecture_change=True,
    )
    assert d.allowed is True
    assert d.next_status is PlanStatus.AUTH_PENDING


def test_plan_submit_without_architecture_change_goes_ready():
    d = apply_plan_event(
        PlanStatus.DRAFTING, PlanEvent.PLAN_SUBMIT,
        has_architecture_change=False,
    )
    assert d.allowed is True
    assert d.next_status is PlanStatus.READY


def test_plan_authorize_from_auth_pending_goes_ready():
    d = apply_plan_event(PlanStatus.AUTH_PENDING, PlanEvent.PLAN_AUTHORIZE)
    assert d.allowed is True
    assert d.next_status is PlanStatus.READY


def test_plan_authorization_reject_returns_to_drafting():
    d = apply_plan_event(
        PlanStatus.AUTH_PENDING, PlanEvent.PLAN_AUTHORIZATION_REJECT,
    )
    assert d.allowed is True
    assert d.next_status is PlanStatus.DRAFTING


def test_plan_authorize_from_drafting_rejected():
    d = apply_plan_event(PlanStatus.DRAFTING, PlanEvent.PLAN_AUTHORIZE)
    assert d.allowed is False


def test_plan_restart_from_any_allowed_state_returns_none():
    for status in (PlanStatus.DRAFTING, PlanStatus.AUTH_PENDING, PlanStatus.READY):
        d = apply_plan_event(status, PlanEvent.PLAN_RESTART)
        assert d.allowed is True
        assert d.next_status is None


def test_plan_restart_before_start_rejected():
    d = apply_plan_event(None, PlanEvent.PLAN_RESTART)
    assert d.allowed is False


def test_design_start_from_none_goes_drafting():
    d = apply_design_event(None, DesignEvent.DESIGN_START)
    assert d.allowed is True
    assert d.next_status is DesignStatus.DRAFTING


def test_design_submit_goes_ready():
    d = apply_design_event(DesignStatus.DRAFTING, DesignEvent.DESIGN_SUBMIT)
    assert d.allowed is True
    assert d.next_status is DesignStatus.READY


def test_design_restart_from_any_allowed_returns_none():
    for status in (DesignStatus.DRAFTING, DesignStatus.READY):
        d = apply_design_event(status, DesignEvent.DESIGN_RESTART)
        assert d.allowed is True
        assert d.next_status is None


def test_plan_phase_enum_values():
    assert PlanPhase.OUTLINE_PENDING.value == "outline_pending"
    assert PlanPhase.OUTLINE_CONFIRMED.value == "outline_confirmed"
    assert PlanPhase.DECISIONS_IN_PROGRESS.value == "decisions_in_progress"
    assert PlanPhase.FINAL_REVIEW_PENDING.value == "final_review_pending"
