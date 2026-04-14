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


def test_store_round_trips_spec_fields():
    import tempfile, json
    from requirement_workflow_v12.store import JsonStateStore
    from requirement_workflow_v12.models import Requirement, WorkflowStatus

    req = Requirement(req_id="REQ-S-001", name="Spec 测试", project="S", summary="s", creator="c")
    req.status = WorkflowStatus.SPEC_DRAFTING
    req.spec_document_id = "doctoken123"
    req.spec_document_url = "https://feishu.cn/docx/doctoken123"
    req.spec_review_summary = "Spec 审查通过"

    with tempfile.TemporaryDirectory() as tmpdir:
        store = JsonStateStore(f"{tmpdir}/state.json")
        store.save_snapshot({"REQ-S-001": req}, {}, {})
        reqs, _, _, _ = store.load_snapshot()
        loaded = reqs["REQ-S-001"]
        assert loaded.status == WorkflowStatus.SPEC_DRAFTING
        assert loaded.spec_document_id == "doctoken123"
        assert loaded.spec_document_url == "https://feishu.cn/docx/doctoken123"
        assert loaded.spec_review_summary == "Spec 审查通过"


def test_config_has_spec_agent_settings():
    from requirement_workflow_v12.config import Settings
    s = Settings(
        spec_agent_feishu_id="ou_spec_agent_1",
        spec_reviewer_feishu_id="ou_spec_reviewer_1",
        openclaw_spec_agent_name="我的Spec助手",
    )
    assert s.spec_agent_feishu_id == "ou_spec_agent_1"
    assert s.spec_reviewer_feishu_id == "ou_spec_reviewer_1"
    assert s.openclaw_spec_agent_name == "我的Spec助手"
