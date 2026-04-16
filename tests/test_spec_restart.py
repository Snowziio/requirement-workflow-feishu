import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest
from requirement_workflow_v12.coordinator_service import CoordinatorService
from requirement_workflow_v12.models import Requirement, WorkflowStatus
from requirement_workflow_v12.spec_state_machine import SpecStatus


def _drafting_req(svc: CoordinatorService) -> Requirement:
    r = Requirement(req_id="R1", name="n", project="P", summary="s", creator="c")
    r.status = WorkflowStatus.APPROVED
    r.spec_status = SpecStatus.DRAFTING
    r.spec_document_url = "https://feishu/doc"
    r.spec_document_id = "doc-1"
    svc.requirements["R1"] = r
    return r


def test_spec_restart_from_drafting_resets_state():
    svc = CoordinatorService()
    _drafting_req(svc)
    result = svc.spec_restart("R1")
    r = svc.requirements["R1"]
    assert r.spec_status is None
    assert r.spec_document_url == ""
    assert r.spec_document_id == ""
    assert r.spec_deadlocked is False
    assert result.spec_status is None


def test_spec_restart_from_locked_raises():
    svc = CoordinatorService()
    r = _drafting_req(svc)
    r.spec_status = SpecStatus.LOCKED
    with pytest.raises(ValueError, match="不能 restart"):
        svc.spec_restart("R1")


def test_spec_restart_from_transforming_without_deadlock_raises():
    svc = CoordinatorService()
    r = _drafting_req(svc)
    r.spec_status = SpecStatus.TRANSFORMING
    with pytest.raises(ValueError, match="不能 restart"):
        svc.spec_restart("R1")


def test_spec_restart_from_deadlocked_transforming_resets():
    svc = CoordinatorService()
    r = _drafting_req(svc)
    r.spec_status = SpecStatus.TRANSFORMING
    r.spec_deadlocked = True
    result = svc.spec_restart("R1")
    assert result.spec_status is None
    assert result.spec_deadlocked is False
