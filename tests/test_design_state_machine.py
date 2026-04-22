import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.plan_state_machine import (
    DesignStatus, DesignEvent, apply_design_event,
)


def test_design_start_from_none_goes_drafting():
    d = apply_design_event(None, DesignEvent.DESIGN_START)
    assert d.allowed is True
    assert d.next_status is DesignStatus.DRAFTING


def test_design_submit_from_drafting_goes_submit_pending_review():
    d = apply_design_event(DesignStatus.DRAFTING, DesignEvent.DESIGN_SUBMIT)
    assert d.allowed is True
    assert d.next_status is DesignStatus.SUBMIT_PENDING_REVIEW


def test_design_final_approve_from_submit_pending_review_goes_ready():
    d = apply_design_event(
        DesignStatus.SUBMIT_PENDING_REVIEW, DesignEvent.DESIGN_FINAL_APPROVE,
    )
    assert d.allowed is True
    assert d.next_status is DesignStatus.READY


def test_design_final_reject_from_submit_pending_review_goes_drafting():
    d = apply_design_event(
        DesignStatus.SUBMIT_PENDING_REVIEW, DesignEvent.DESIGN_FINAL_REJECT,
    )
    assert d.allowed is True
    assert d.next_status is DesignStatus.DRAFTING


def test_design_submit_from_none_rejected():
    d = apply_design_event(None, DesignEvent.DESIGN_SUBMIT)
    assert d.allowed is False


def test_design_final_approve_from_drafting_rejected():
    d = apply_design_event(DesignStatus.DRAFTING, DesignEvent.DESIGN_FINAL_APPROVE)
    assert d.allowed is False


def test_design_restart_from_any_state_goes_none():
    for st in [DesignStatus.DRAFTING, DesignStatus.SUBMIT_PENDING_REVIEW, DesignStatus.READY]:
        d = apply_design_event(st, DesignEvent.DESIGN_RESTART)
        assert d.allowed is True
        assert d.next_status is None


def test_design_restart_from_none_rejected():
    d = apply_design_event(None, DesignEvent.DESIGN_RESTART)
    assert d.allowed is False
