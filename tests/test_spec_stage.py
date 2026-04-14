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


# ── Task 3: CoordinatorService Spec Methods ───────────────────────────────────

from requirement_workflow_v12.coordinator_service import CoordinatorService
from requirement_workflow_v12 import CreationRequest
from requirement_workflow_v12.protocols import AgentReviewEventPayload


def _make_approved_requirement():
    """Create a requirement and advance it all the way to APPROVED."""
    from requirement_workflow_v12.protocols import AgentAuthorEventPayload
    svc = CoordinatorService()
    resp = svc.create_requirement_from_group(CreationRequest(
        project="SPEC", name="Spec测试需求", summary="s", creator="c",
        creator_user_id="u1", creation_chat_id="chat1",
    ))
    req = svc.get_requirement(resp.req_id)
    assert req is not None
    svc.submit_author_event_payload(AgentAuthorEventPayload(
        req_id=resp.req_id, event="author_submit", summary="done",
        completed_fields=list(req.pending_fields),
    ))
    svc.submit_review_event_payload(AgentReviewEventPayload(
        req_id=resp.req_id, event="ai_review_pass", review_summary="pass",
    ))
    req = svc.get_requirement(resp.req_id)
    assert req is not None
    svc.handle_human_confirmation(req, approved=True)
    req = svc.get_requirement(resp.req_id)
    assert req is not None
    svc.approve_requirement(req)
    req = svc.get_requirement(resp.req_id)
    assert req is not None
    assert req.status == WorkflowStatus.APPROVED
    return svc, resp.req_id


def test_submit_spec_start_transitions_to_spec_drafting():
    svc, req_id = _make_approved_requirement()
    req = svc.submit_spec_start(req_id, spec_document_id="docabc", spec_document_url="https://feishu.cn/docx/docabc")
    assert req.status == WorkflowStatus.SPEC_DRAFTING
    assert req.spec_document_id == "docabc"
    assert req.spec_document_url == "https://feishu.cn/docx/docabc"
    assert req.current_phase == "Spec 撰写"
    assert req.current_owner == "spec-agent"


def test_submit_spec_start_blocked_if_not_approved():
    svc = CoordinatorService()
    resp = svc.create_requirement_from_group(CreationRequest(
        project="SPEC2", name="n", summary="s", creator="c",
        creator_user_id="u1", creation_chat_id="c1",
    ))
    import pytest
    with pytest.raises(ValueError, match="spec_start"):
        svc.submit_spec_start(resp.req_id, spec_document_id="x", spec_document_url="y")


def test_submit_spec_submit_stores_summary():
    svc, req_id = _make_approved_requirement()
    svc.submit_spec_start(req_id, spec_document_id="doc1", spec_document_url="https://feishu.cn/docx/doc1")
    req = svc.submit_spec_submit(req_id, summary="Spec 初稿完成，9节均已填写")
    assert req.status == WorkflowStatus.SPEC_DRAFTING  # no state change
    assert req.spec_review_summary == "Spec 初稿完成，9节均已填写"


def test_spec_review_pass_transitions_to_spec_locked():
    svc, req_id = _make_approved_requirement()
    svc.submit_spec_start(req_id, spec_document_id="doc1", spec_document_url="https://feishu.cn/docx/doc1")
    req = svc.submit_review_event_payload(AgentReviewEventPayload(
        req_id=req_id, event="ai_review_pass", review_summary="Spec 质量达标",
    ))
    assert req.status == WorkflowStatus.SPEC_LOCKED
    assert req.spec_review_summary == "Spec 质量达标"


def test_spec_review_reject_stays_spec_drafting():
    svc, req_id = _make_approved_requirement()
    svc.submit_spec_start(req_id, spec_document_id="doc1", spec_document_url="https://feishu.cn/docx/doc1")
    req = svc.submit_review_event_payload(AgentReviewEventPayload(
        req_id=req_id, event="ai_review_reject", review_summary="API 入参缺少字段名",
    ))
    assert req.status == WorkflowStatus.SPEC_DRAFTING
    assert req.spec_review_summary == "API 入参缺少字段名"


def test_context_query_returns_spec_fields():
    from requirement_workflow_v12.protocols import AgentRequirementContextQuery
    svc, req_id = _make_approved_requirement()
    svc.submit_spec_start(req_id, spec_document_id="docXYZ", spec_document_url="https://feishu.cn/docx/docXYZ")
    ctx = svc.get_agent_requirement_context(AgentRequirementContextQuery(req_id=req_id))
    assert ctx["spec_document_id"] == "docXYZ"
    assert ctx["spec_document_url"] == "https://feishu.cn/docx/docXYZ"
    assert "spec_review_summary" in ctx
