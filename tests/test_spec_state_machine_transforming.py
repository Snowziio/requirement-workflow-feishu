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


from requirement_workflow_v12.models import Requirement, WorkflowStatus


def test_requirement_default_spec_deadlocked_is_false():
    r = Requirement(req_id="R", name="n", project="p", summary="s", creator="c")
    assert r.spec_deadlocked is False
    assert r.spec_transform_snapshot is None


from unittest.mock import MagicMock

from requirement_workflow_v12.coordinator_service import CoordinatorService


def test_submit_checkpoint_1a_pass_transitions_to_transforming():
    svc = CoordinatorService()
    r = Requirement(req_id="R1", name="n", project="P", summary="s", creator="c")
    r.status = WorkflowStatus.APPROVED
    r.spec_status = SpecStatus.DRAFTING
    r.spec_document_id = "doc-1"
    svc.requirements["R1"] = r

    svc.spec_orchestrator = MagicMock()
    svc.spec_orchestrator.on_enter_transforming = MagicMock(return_value=None)
    svc.project_configs = MagicMock()
    cfg = MagicMock(); cfg.scaffold_repo = "owner/repo"
    svc.project_configs.get.return_value = cfg

    svc.submit_checkpoint_1a_pass("R1")
    assert svc.requirements["R1"].spec_status is SpecStatus.TRANSFORMING
    svc.spec_orchestrator.on_enter_transforming.assert_called_once()


def test_on_spec_deadlock_sets_spec_deadlocked_flag_in_transforming():
    svc = CoordinatorService()
    r = Requirement(req_id="REQ-T-1", name="n", project="T", summary="s", creator="c")
    r.status = WorkflowStatus.APPROVED
    r.spec_status = SpecStatus.TRANSFORMING
    svc.requirements[r.req_id] = r
    svc._on_spec_deadlock("REQ-T-1", "max_rounds")
    assert r.spec_deadlocked is True


def test_on_spec_deadlock_noop_when_req_missing():
    svc = CoordinatorService()
    svc._on_spec_deadlock("DOES-NOT-EXIST", "max_rounds")


def test_on_spec_deadlock_does_not_set_flag_when_not_in_transforming():
    svc = CoordinatorService()
    r = Requirement(req_id="REQ-T-2", name="n", project="T", summary="s", creator="c")
    r.status = WorkflowStatus.APPROVED
    r.spec_status = SpecStatus.DRAFTING
    svc.requirements[r.req_id] = r
    svc._on_spec_deadlock("REQ-T-2", "max_rounds")
    assert r.spec_deadlocked is False
