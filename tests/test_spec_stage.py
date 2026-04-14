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


# ── Task 5: service_app spec-turn Endpoint + Notifications ───────────────────

import json
import tempfile
from requirement_workflow_v12.service_app import CoordinatorRuntimeApp
from requirement_workflow_v12 import Settings


class FakeGateway:
    """Minimal gateway stub for unit tests."""
    def __init__(self):
        self.sent_texts: list[tuple[str, str, str]] = []
        self.sent_cards: list[tuple[str, dict, str]] = []
        self.spec_doc_created: list[str] = []

    def update_requirement_record(self, req) -> None:
        pass

    def bitable_url(self) -> str:
        return ""

    def send_text(self, receive_id, text, receive_id_type="chat_id"):
        self.sent_texts.append((receive_id, text, receive_id_type))

    def send_card(self, receive_id, card, receive_id_type="chat_id"):
        self.sent_cards.append((receive_id, card, receive_id_type))

    def create_spec_document(self, requirement):
        self.spec_doc_created.append(requirement.req_id)
        from requirement_workflow_v12.feishu_gateway import CreatedDocument
        return CreatedDocument(
            document_id=f"spec_doc_{requirement.req_id}",
            document_url=f"https://feishu.cn/docx/spec_doc_{requirement.req_id}",
        )


def _make_app_with_approved_req():
    tmpdir = tempfile.mkdtemp()
    svc = CoordinatorService()
    resp = svc.create_requirement_from_group(CreationRequest(
        project="SPEC3", name="端到端测试", summary="s", creator="c",
        creator_user_id="u1", creation_chat_id="c1",
    ))
    req = svc.get_requirement(resp.req_id)
    assert req is not None
    from requirement_workflow_v12.protocols import AgentAuthorEventPayload
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

    gateway = FakeGateway()
    app = CoordinatorRuntimeApp(
        Settings(feishu_app_id="x", feishu_app_secret="y",
                 state_store_path=f"{tmpdir}/state.json"),
        service=svc,
        gateway=gateway,
    )
    return app, resp.req_id, gateway


def test_spec_start_callback_creates_doc_and_transitions_state():
    app, req_id, gateway = _make_app_with_approved_req()
    body = json.dumps({"req_id": req_id, "event": "spec_start", "summary": "开始 Spec 撰写"}).encode()
    status, payload = app.handle_openclaw_spec_turn_callback(body)
    assert status == 200
    assert payload["ok"] is True
    assert payload["status"] == "SPEC_DRAFTING"
    assert "spec_document_id" in payload
    assert "spec_document_url" in payload
    assert "requirement_document_url" in payload
    req = app.service.get_requirement(req_id)
    assert req is not None
    assert req.status == WorkflowStatus.SPEC_DRAFTING
    assert req.spec_document_id == f"spec_doc_{req_id}"


def test_spec_start_blocked_if_not_approved():
    app, req_id, gateway = _make_app_with_approved_req()
    body = json.dumps({"req_id": req_id, "event": "spec_start", "summary": "start"}).encode()
    app.handle_openclaw_spec_turn_callback(body)
    # Try to start again (now SPEC_DRAFTING, not APPROVED)
    status, payload = app.handle_openclaw_spec_turn_callback(body)
    assert status == 400


def test_spec_submit_notifies_reviewer():
    app, req_id, gateway = _make_app_with_approved_req()
    start_body = json.dumps({"req_id": req_id, "event": "spec_start", "summary": "start"}).encode()
    app.handle_openclaw_spec_turn_callback(start_body)
    app.settings.spec_reviewer_feishu_id = "ou_reviewer_123"
    submit_body = json.dumps({
        "req_id": req_id,
        "event": "spec_submit",
        "summary": "9节已完成",
        "spec_document_url": "https://feishu.cn/docx/spec_doc",
    }).encode()
    status, payload = app.handle_openclaw_spec_turn_callback(submit_body)
    assert status == 200
    assert payload["ok"] is True
    reviewer_texts = [t for t in gateway.sent_texts if t[0] == "ou_reviewer_123"]
    assert len(reviewer_texts) == 1
    assert req_id in reviewer_texts[0][1]


def test_review_result_on_spec_drafting_transitions_to_spec_locked():
    app, req_id, gateway = _make_app_with_approved_req()
    start_body = json.dumps({"req_id": req_id, "event": "spec_start", "summary": "start"}).encode()
    app.handle_openclaw_spec_turn_callback(start_body)
    review_body = json.dumps({
        "req_id": req_id,
        "event": "ai_review_pass",
        "review_summary": "Spec 质量达标",
    }).encode()
    status, payload = app.handle_openclaw_review_result_callback(review_body)
    assert status == 200
    req = app.service.get_requirement(req_id)
    assert req is not None
    assert req.status == WorkflowStatus.SPEC_LOCKED


def test_spec_locked_sends_notification_card_to_project_group():
    app, req_id, gateway = _make_app_with_approved_req()
    req = app.service.get_requirement(req_id)
    assert req is not None
    req.project_group_id = "oc_testgroup123"
    start_body = json.dumps({"req_id": req_id, "event": "spec_start", "summary": "start"}).encode()
    app.handle_openclaw_spec_turn_callback(start_body)
    review_body = json.dumps({
        "req_id": req_id,
        "event": "ai_review_pass",
        "review_summary": "Spec 质量达标",
    }).encode()
    app.handle_openclaw_review_result_callback(review_body)
    group_cards = [c for c in gateway.sent_cards if c[0] == "oc_testgroup123"]
    assert len(group_cards) >= 1
    card_str = json.dumps(group_cards[-1][1])
    assert req_id in card_str
