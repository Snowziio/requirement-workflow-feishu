import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.coordinator_service import CoordinatorService
from requirement_workflow_v12.models import Requirement, WorkflowStatus
from requirement_workflow_v12.spec_state_machine import SpecStatus


def _req(req_id: str, project: str, spec_status: SpecStatus | None) -> Requirement:
    r = Requirement(req_id=req_id, name="n", project=project, summary="s", creator="c")
    r.status = WorkflowStatus.APPROVED
    r.spec_status = spec_status
    return r


def test_has_concurrent_spec_false_when_alone():
    svc = CoordinatorService()
    svc.requirements["R1"] = _req("R1", "ProjA", SpecStatus.DRAFTING)
    assert svc._has_concurrent_spec("ProjA", exclude_req_id="R1") is False


def test_has_concurrent_spec_true_when_sibling_drafting():
    svc = CoordinatorService()
    svc.requirements["R1"] = _req("R1", "ProjA", SpecStatus.DRAFTING)
    svc.requirements["R2"] = _req("R2", "ProjA", None)
    assert svc._has_concurrent_spec("ProjA", exclude_req_id="R2") is True


def test_has_concurrent_spec_ignores_other_projects():
    svc = CoordinatorService()
    svc.requirements["R1"] = _req("R1", "ProjA", SpecStatus.DRAFTING)
    svc.requirements["R2"] = _req("R2", "ProjB", None)
    assert svc._has_concurrent_spec("ProjB", exclude_req_id="R2") is False


def test_has_concurrent_spec_ignores_locked_siblings():
    svc = CoordinatorService()
    svc.requirements["R1"] = _req("R1", "ProjA", SpecStatus.LOCKED)
    assert svc._has_concurrent_spec("ProjA", exclude_req_id="R2") is False
