import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.coordinator_service import CoordinatorService
from requirement_workflow_v12.protocols import AgentAuthorEventPayload
from requirement_workflow_v12 import CreationRequest, WorkflowStatus


def _make_service_with_drafting_req():
    svc = CoordinatorService()
    resp = svc.create_requirement_from_group(
        CreationRequest(
            project="PROTO",
            name="协议测试",
            summary="验证 completed_fields 协议",
            creator="tester",
            creator_user_id="u1",
            creation_chat_id="c1",
        )
    )
    req = svc.get_requirement(resp.req_id)
    assert req is not None
    svc.handoff_to_author(req)
    return svc, resp.req_id


def test_author_callback_uses_completed_fields():
    svc, req_id = _make_service_with_drafting_req()
    svc.submit_author_event_payload(
        AgentAuthorEventPayload(
            req_id=req_id,
            event="author_submit",
            summary="完成了问题描述和使用场景",
            completed_fields=["问题描述", "使用场景"],
            iteration_round=1,
        )
    )
    req = svc.get_requirement(req_id)
    assert req is not None
    assert req.status == WorkflowStatus.AI_REVIEWING
    assert "问题描述" in req.completed_fields
    assert "使用场景" in req.completed_fields
    assert "输入" not in req.completed_fields


def test_author_callback_without_completed_fields_is_accepted():
    """Backward compat: completed_fields 为空列表时不报错."""
    svc, req_id = _make_service_with_drafting_req()
    svc.submit_author_event_payload(
        AgentAuthorEventPayload(
            req_id=req_id,
            event="author_submit",
            summary="完成了全部字段",
            completed_fields=[],
            iteration_round=2,
        )
    )
    req = svc.get_requirement(req_id)
    assert req is not None
    assert req.status == WorkflowStatus.AI_REVIEWING


def test_context_query_returns_field_hints():
    svc, req_id = _make_service_with_drafting_req()
    from requirement_workflow_v12.protocols import AgentRequirementContextQuery
    context = svc.get_agent_requirement_context(
        AgentRequirementContextQuery(req_id=req_id)
    )
    assert "field_hints" in context
    hints = context["field_hints"]
    assert "输入" in hints
    assert "输出" in hints
    assert "验收标准" in hints
    assert "技术范围声明" in hints
    assert len(hints["输入"]) > 10
    assert len(hints["验收标准"]) > 10


def test_requirement_has_no_document_field():
    """Requirement 不再持有文档内容副本。"""
    svc, req_id = _make_service_with_drafting_req()
    req = svc.get_requirement(req_id)
    assert req is not None
    assert not hasattr(req, "document") or req.document is None


def test_discussion_turn_has_no_normalized_updates():
    """DiscussionTurn 不再存储字段值。"""
    from requirement_workflow_v12.models import DiscussionTurn
    turn = DiscussionTurn(round_number=1, focused_field="问题描述", user_input="test")
    assert not hasattr(turn, "normalized_updates")


def test_dm_handler_redirects_to_author_agent():
    """直接私聊 Coordinator 时应提示使用 Author Agent，不处理需求内容。"""
    from requirement_workflow_v12.service_app import CoordinatorRuntimeApp, MessageContext
    from requirement_workflow_v12.config import Settings

    svc, req_id = _make_service_with_drafting_req()
    req = svc.get_requirement(req_id)
    assert req is not None

    class _FakeGateway:
        def update_requirement_record(self, r): pass
        def sync_requirement_document(self, r): pass

    import tempfile, os
    with tempfile.TemporaryDirectory() as tmp:
        app = CoordinatorRuntimeApp(
            Settings(
                feishu_app_id="app",
                feishu_app_secret="secret",
                state_store_path=os.path.join(tmp, "state.json"),
            ),
            service=svc,
            gateway=_FakeGateway(),
        )

        ctx = MessageContext(
            chat_id="dm_chat",
            chat_type="p2p",
            user_id="u1",
            text="这个需求的输入是用户ID和密码",
            sender_name="Test",
        )
        responses = app._handle_author_turn(ctx, req)
        texts = [r.text for r in responses if hasattr(r, "text")]
        assert len(texts) > 0
        assert any("请前往" in t for t in texts), f"Expected redirect message, got: {texts}"
