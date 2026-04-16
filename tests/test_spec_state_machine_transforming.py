import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.spec_state_machine import (
    SpecStatus, SpecEvent, apply_spec_event,
)


def test_spec_restart_from_drafting_returns_null():
    decision = apply_spec_event(SpecStatus.DRAFTING, SpecEvent.SPEC_RESTART)
    assert decision.allowed is True
    assert decision.next_status is None


def test_spec_restart_from_transforming_without_deadlock_rejected():
    decision = apply_spec_event(SpecStatus.TRANSFORMING, SpecEvent.SPEC_RESTART)
    assert decision.allowed is False


def test_spec_restart_from_transforming_with_deadlock_allowed():
    decision = apply_spec_event(
        SpecStatus.TRANSFORMING, SpecEvent.SPEC_RESTART, deadlocked=True,
    )
    assert decision.allowed is True
    assert decision.next_status is None


def test_spec_restart_from_locked_rejected():
    decision = apply_spec_event(SpecStatus.LOCKED, SpecEvent.SPEC_RESTART)
    assert decision.allowed is False


def test_spec_restart_before_spec_start_rejected():
    decision = apply_spec_event(None, SpecEvent.SPEC_RESTART)
    assert decision.allowed is False
