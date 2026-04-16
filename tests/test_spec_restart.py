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


def test_spec_restart_clears_audit_fields():
    svc = CoordinatorService()
    r = _drafting_req(svc)
    r.spec_status = SpecStatus.TRANSFORMING
    r.spec_deadlocked = True
    r.spec_source_revision = "rev-old"
    r.transform_trace_digest = "abcdef012345"
    r.spec_pr_url = "https://gh/pr/old"
    svc.spec_restart("R1")
    assert r.spec_source_revision == ""
    assert r.transform_trace_digest == ""
    assert r.spec_pr_url == ""


def test_spec_restart_archives_trace_when_orchestrator_wired(tmp_path):
    from unittest.mock import MagicMock
    svc = CoordinatorService()
    r = _drafting_req(svc)
    r.spec_status = SpecStatus.TRANSFORMING
    r.spec_deadlocked = True
    svc.configure_spec_orchestrator(
        github_gateway=MagicMock(), trace_dir=tmp_path, feishu=MagicMock(),
    )
    # Pre-existing trace from the deadlocked attempt
    svc.spec_orchestrator._trace.append("R1", {"event": "transform_started"})
    svc.spec_orchestrator._trace.append("R1", {"event": "deadlock"})

    svc.spec_restart("R1")

    assert not (tmp_path / "R1.jsonl").exists()
    archived = list((tmp_path / "archive").glob("R1.*.restart.jsonl"))
    assert len(archived) == 1
    assert "transform_started" in archived[0].read_text()


def test_spec_restart_works_without_orchestrator_wired():
    """Coordinators that never called configure_spec_orchestrator (e.g.,
    test-only) must still be able to restart without raising."""
    svc = CoordinatorService()
    r = _drafting_req(svc)
    r.spec_status = SpecStatus.TRANSFORMING
    r.spec_deadlocked = True
    assert svc.spec_orchestrator is None
    svc.spec_restart("R1")  # must not raise
    assert r.spec_status is None
