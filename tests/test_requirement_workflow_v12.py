import json
import hashlib
import hmac
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12 import (
    AgentAuthorEventPayload,
    AuthorTurnResult,
    CoordinatorService,
    CreationRequest,
    ReviewResult,
    Settings,
    WorkflowStatus,
)
from requirement_workflow_v12.service_app import CoordinatorRuntimeApp, MessageContext


class RequirementWorkflowV12Test(unittest.TestCase):
    def setUp(self) -> None:
        self.service = CoordinatorService()
        response = self.service.create_requirement_from_group(
            CreationRequest(
                project="HARNESS",
                name="多轮讨论测试",
                summary="验证需求构造与双 review 输出",
                creator="tester",
                creator_user_id="user-1",
                creation_chat_id="chat-1",
            )
        )
        self.req_id = response.req_id
        self.requirement = self.service.get_requirement(self.req_id)
        assert self.requirement is not None
        self.service.handoff_to_author(self.requirement)

    def test_discussion_history_is_written_to_document(self) -> None:
        requirement = self.service.handle_author_turn(
            self.requirement,
            AuthorTurnResult(
                updates={"问题描述": "目前创建完需求后，后续多轮讨论产物不会沉淀到正式文档，导致 review 难以追踪。"},
                next_question="请补充使用场景。",
                next_field="使用场景",
            ),
        )
        requirement = self.service.handle_review_result(
            requirement,
            ReviewResult(
                ready_for_human_confirmation=False,
                summary="问题描述已明确，但仍需补充使用场景。",
                next_focus="请补充谁会在什么情况下使用它。",
            ),
        )

        self.assertEqual(requirement.current_round, 1)
        self.assertEqual(len(requirement.discussion_history), 1)
        self.assertIn("第1轮", requirement.document.sections["多轮讨论纪要"])
        self.assertIn("问题描述", requirement.document.sections["多轮讨论纪要"])
        self.assertIn("问题描述已明确", requirement.document.sections["AI Review结论"])

    def test_human_review_history_records_dual_review(self) -> None:
        requirement = self.requirement
        fields = {
            "问题描述": "需求创建后，需要把多轮讨论沉淀为正式需求文档，并让后续评审可追踪。",
            "使用场景": "产品经理在飞书私聊中逐轮回答 author agent 的问题，协调服务持续写回正式文档。",
            "输入": "输入包括需求简述、每轮用户补充、历史 review 结论和当前文档草稿。",
            "输出": "输出包括结构化需求文档、AI review 结论、人工 review 决策和最终批准状态。",
            "边界": "本次不包含规格层转化、不做 GitHub PR 自动生成，也不覆盖部署流水线。",
            "验收标准": "系统必须保留每轮讨论摘要；AI review 必须给出明确结论；人工确认通过后状态应进入 FINAL_REVIEW。",
            "非功能要求": "单轮状态写回应保持幂等，服务重启后仍可恢复会话状态。",
        }
        ordered_fields = list(fields.items())
        for index, (field, content) in enumerate(ordered_fields):
            remaining_fields = [name for name, _ in ordered_fields[index + 1 :]]
            requirement = self.service.handle_author_turn(
                requirement,
                AuthorTurnResult(
                    updates={field: content},
                    next_question="done" if not remaining_fields else f"请补充{remaining_fields[0]}。",
                    next_field=remaining_fields[0] if remaining_fields else None,
                ),
            )
            requirement = self.service.handle_review_result(
                requirement,
                ReviewResult(
                    ready_for_human_confirmation=not remaining_fields,
                    summary="当前草稿可继续推进。" if remaining_fields else "AI review 通过，可以进入人工确认。",
                    next_focus=None if not remaining_fields else f"请补充{remaining_fields[0]}。",
                ),
            )

        self.assertEqual(requirement.status, WorkflowStatus.HUMAN_CONFIRM)

        requirement = self.service.handle_human_confirmation(requirement, approved=True)
        self.assertEqual(requirement.status, WorkflowStatus.FINAL_REVIEW)
        self.assertEqual(len(requirement.human_review_history), 1)
        self.assertIn("人工确认通过", requirement.document.sections["人工Review结论"])

    def test_formal_review_is_not_skipped_after_human_confirmation(self) -> None:
        requirement = self.requirement
        for index, field in enumerate(["问题描述", "使用场景", "输入", "输出", "边界", "验收标准", "非功能要求"]):
            next_field = ["问题描述", "使用场景", "输入", "输出", "边界", "验收标准", "非功能要求"][index + 1] if index < 6 else None
            requirement = self.service.handle_author_turn(
                requirement,
                AuthorTurnResult(
                    updates={field: f"{field} 的内容足够详细，满足当前轮需求构造与后续审查的基本要求。"},
                    next_question="done" if next_field is None else f"请补充{next_field}",
                    next_field=next_field,
                ),
            )
            requirement = self.service.handle_review_result(
                requirement,
                ReviewResult(
                    ready_for_human_confirmation=next_field is None,
                    summary="继续完善。" if next_field else "AI review 通过，可以进入人工确认。",
                    next_focus=None if next_field is None else f"请补充{next_field}",
                ),
            )

        requirement = self.service.handle_human_confirmation(requirement, approved=True)
        self.assertEqual(requirement.status, WorkflowStatus.FINAL_REVIEW)

        requirement = self.service.approve_requirement(requirement)
        self.assertEqual(requirement.status, WorkflowStatus.APPROVED)

    def test_openclaw_author_turn_callback_updates_requirement(self) -> None:
        class FakeGateway:
            def sync_requirement_document(self, requirement) -> None:
                return None

            def update_requirement_record(self, requirement) -> None:
                return None

        with TemporaryDirectory() as temp_dir:
            runtime_service = CoordinatorService()
            response = runtime_service.create_requirement_from_group(
                CreationRequest(
                    project="HARNESS",
                    name="author callback 测试",
                    summary="验证 agent skill 可直接上报构造结果。",
                    creator="tester",
                    creator_user_id="user-1",
                    creation_chat_id="chat-1",
                )
            )
            requirement = runtime_service.get_requirement(response.req_id)
            assert requirement is not None
            runtime_service.handoff_to_author(requirement)

            app = CoordinatorRuntimeApp(
                Settings(
                    feishu_app_id="app-id",
                    feishu_app_secret="app-secret",
                    state_store_path=str(Path(temp_dir) / "state.json"),
                ),
                service=runtime_service,
                gateway=FakeGateway(),
            )

            status, payload = app.handle_openclaw_author_turn_callback(
                json.dumps(
                    {
                        "req_id": response.req_id,
                        "event": "author_ready_for_ai_review",
                        "summary": "author 已完成本轮需求文档撰写，可进入 AI review。",
                        "document_url": "https://example.com/doc/REQ-HARNESS-001",
                        "iteration_round": 3,
                    },
                    ensure_ascii=False,
                ).encode()
            )

            refreshed = runtime_service.get_requirement(response.req_id)
            assert refreshed is not None
            self.assertEqual(status, 200)
            self.assertTrue(payload["ok"])
            self.assertEqual(refreshed.current_round, 3)
            self.assertEqual(refreshed.status, WorkflowStatus.AI_REVIEWING)
            self.assertEqual(refreshed.document_url, "https://example.com/doc/REQ-HARNESS-001")

    def test_author_private_message_accepts_forwarded_handoff_package(self) -> None:
        class FakeGateway:
            def sync_requirement_document(self, requirement) -> None:
                return None

            def update_requirement_record(self, requirement) -> None:
                return None

            def bitable_url(self) -> str:
                return "https://example.com/bitable"

        with TemporaryDirectory() as temp_dir:
            runtime_service = CoordinatorService()
            response = runtime_service.create_requirement_from_group(
                CreationRequest(
                    project="HARNESS",
                    name="启动包转发测试",
                    summary="验证私发启动指令整段转发也能被识别。",
                    creator="tester",
                    creator_user_id="user-1",
                    creation_chat_id="chat-1",
                )
            )
            requirement = runtime_service.get_requirement(response.req_id)
            assert requirement is not None
            requirement.document_url = "https://example.com/doc/REQ-HARNESS-001"

            app = CoordinatorRuntimeApp(
                Settings(
                    feishu_app_id="app-id",
                    feishu_app_secret="app-secret",
                    state_store_path=str(Path(temp_dir) / "state.json"),
                ),
                service=runtime_service,
                gateway=FakeGateway(),
            )

            forwarded_text = (
                "请私聊需求构造助手，并发送以下完整上下文：\n\n"
                f"开始需求构造 {response.req_id}\n"
                "需求名称：启动包转发测试\n"
                "需求简述：验证私发启动指令整段转发也能被识别。\n"
                "需求文档：https://example.com/doc/REQ-HARNESS-001\n"
                "多维表格：https://example.com/bitable\n"
            )
            outbound = app.handle_text_message(
                MessageContext(
                    chat_id="p2p-chat-1",
                    chat_type="p2p",
                    user_id="user-1",
                    text=forwarded_text,
                    message_id="msg-1",
                )
            )

            self.assertEqual(len(outbound), 1)
            self.assertIn("确认开始", outbound[0].text)
            refreshed = runtime_service.get_requirement(response.req_id)
            assert refreshed is not None
            self.assertEqual(refreshed.author_dm_chat_id, "p2p-chat-1")

    def test_send_author_start_card_uses_configured_user_id_type(self) -> None:
        class FakeGateway:
            def __init__(self) -> None:
                self.sent_texts = []

            def sync_requirement_document(self, requirement) -> None:
                return None

            def update_requirement_record(self, requirement) -> None:
                return None

            def send_text(self, receive_id, text, receive_id_type="chat_id") -> None:
                self.sent_texts.append((receive_id, receive_id_type, text))

            def bitable_url(self) -> str:
                return "https://example.com/bitable"

        with TemporaryDirectory() as temp_dir:
            runtime_service = CoordinatorService()
            response = runtime_service.create_requirement_from_group(
                CreationRequest(
                    project="HARNESS",
                    name="私发启动指令测试",
                    summary="验证卡片按钮会按配置的 user id type 私发。",
                    creator="tester",
                    creator_user_id="user-open-1",
                    creation_chat_id="chat-1",
                )
            )
            requirement = runtime_service.get_requirement(response.req_id)
            assert requirement is not None
            requirement.document_url = "https://example.com/doc/start"

            gateway = FakeGateway()
            app = CoordinatorRuntimeApp(
                Settings(
                    feishu_app_id="app-id",
                    feishu_app_secret="app-secret",
                    feishu_user_id_type="user_id",
                    state_store_path=str(Path(temp_dir) / "state.json"),
                ),
                service=runtime_service,
                gateway=gateway,
            )

            status, payload = app.handle_card_callback(
                json.dumps(
                    {
                        "operator": {
                            "open_id": "user-open-1",
                            "user_id": "user-id-1",
                            "name": "tester",
                        },
                        "action": {
                            "value": {
                                "action": "send_author_start",
                                "req_id": response.req_id,
                            }
                        },
                    },
                    ensure_ascii=False,
                ).encode()
            )

            self.assertEqual(status, 200)
            self.assertEqual(payload["toast"]["type"], "success")
            self.assertEqual(len(gateway.sent_texts), 1)
            receive_id, receive_id_type, text = gateway.sent_texts[0]
            self.assertEqual(receive_id, "user-id-1")
            self.assertEqual(receive_id_type, "user_id")
            self.assertIn(f"开始需求构造 {response.req_id}", text)

    def test_openclaw_author_turn_callback_rejects_missing_signature(self) -> None:
        class FakeGateway:
            def sync_requirement_document(self, requirement) -> None:
                return None

            def update_requirement_record(self, requirement) -> None:
                return None

        with TemporaryDirectory() as temp_dir:
            runtime_service = CoordinatorService()
            response = runtime_service.create_requirement_from_group(
                CreationRequest(
                    project="HARNESS",
                    name="author callback 鉴权测试",
                    summary="验证缺少签名会被拒绝。",
                    creator="tester",
                    creator_user_id="user-1",
                    creation_chat_id="chat-1",
                )
            )
            requirement = runtime_service.get_requirement(response.req_id)
            assert requirement is not None
            runtime_service.handoff_to_author(requirement)

            app = CoordinatorRuntimeApp(
                Settings(
                    feishu_app_id="app-id",
                    feishu_app_secret="app-secret",
                    openclaw_callback_secret="shared-secret",
                    state_store_path=str(Path(temp_dir) / "state.json"),
                ),
                service=runtime_service,
                gateway=FakeGateway(),
            )

            status, payload = app.handle_openclaw_author_turn_callback(
                json.dumps(
                    {
                        "req_id": response.req_id,
                        "event": "author_ready_for_ai_review",
                        "summary": "未签名请求。",
                    },
                    ensure_ascii=False,
                ).encode()
            )

            self.assertEqual(status, 401)
            self.assertEqual(payload["error"], "unauthorized")

    def test_openclaw_author_turn_callback_rejects_unknown_event(self) -> None:
        class FakeGateway:
            def sync_requirement_document(self, requirement) -> None:
                return None

            def update_requirement_record(self, requirement) -> None:
                return None

        with TemporaryDirectory() as temp_dir:
            runtime_service = CoordinatorService()
            response = runtime_service.create_requirement_from_group(
                CreationRequest(
                    project="HARNESS",
                    name="author callback 字段校验测试",
                    summary="验证未知字段会被拒绝。",
                    creator="tester",
                    creator_user_id="user-1",
                    creation_chat_id="chat-1",
                )
            )
            requirement = runtime_service.get_requirement(response.req_id)
            assert requirement is not None
            runtime_service.handoff_to_author(requirement)

            app = CoordinatorRuntimeApp(
                Settings(
                    feishu_app_id="app-id",
                    feishu_app_secret="app-secret",
                    state_store_path=str(Path(temp_dir) / "state.json"),
                ),
                service=runtime_service,
                gateway=FakeGateway(),
            )

            status, payload = app.handle_openclaw_author_turn_callback(
                json.dumps(
                    {
                        "req_id": response.req_id,
                        "event": "author_unknown_event",
                        "summary": "错误事件名。",
                    },
                    ensure_ascii=False,
                ).encode()
            )

            self.assertEqual(status, 400)
            self.assertEqual(payload["error"], "invalid_payload")

    def test_openclaw_review_result_callback_advances_state(self) -> None:
        class FakeGateway:
            def __init__(self) -> None:
                self.text_messages = []
                self.card_messages = []

            def sync_requirement_document(self, requirement) -> None:
                return None

            def update_requirement_record(self, requirement) -> None:
                return None

            def send_text(self, receive_id, text, receive_id_type="chat_id") -> None:
                self.text_messages.append((receive_id, receive_id_type, text))

            def send_card(self, receive_id, card, receive_id_type="chat_id") -> None:
                self.card_messages.append((receive_id, receive_id_type, card))

        with TemporaryDirectory() as temp_dir:
            runtime_service = CoordinatorService()
            response = runtime_service.create_requirement_from_group(
                CreationRequest(
                    project="HARNESS",
                    name="review callback 测试",
                    summary="验证 reviewer 结果可直接推动状态。",
                    creator="tester",
                    creator_user_id="user-1",
                    creation_chat_id="chat-1",
                )
            )
            requirement = runtime_service.get_requirement(response.req_id)
            assert requirement is not None
            requirement.project_group_id = "oc_group_1"
            runtime_service.handoff_to_author(requirement)
            runtime_service.submit_author_event_payload(
                AgentAuthorEventPayload(
                    req_id=response.req_id,
                    event="author_ready_for_ai_review",
                    summary="author 已完成需求文档撰写。",
                    document_url="https://example.com/doc/review-callback",
                    iteration_round=2,
                )
            )

            gateway = FakeGateway()
            app = CoordinatorRuntimeApp(
                Settings(
                    feishu_app_id="app-id",
                    feishu_app_secret="app-secret",
                    state_store_path=str(Path(temp_dir) / "state.json"),
                ),
                service=runtime_service,
                gateway=gateway,
            )

            status, payload = app.handle_openclaw_review_result_callback(
                json.dumps(
                    {
                        "req_id": response.req_id,
                        "event": "review_returned_for_revision",
                        "review_summary": "AI review 认为仍需继续修改需求文档。",
                        "review_notes_url": "https://example.com/review-notes/1",
                    },
                    ensure_ascii=False,
                ).encode()
            )

            refreshed = runtime_service.get_requirement(response.req_id)
            assert refreshed is not None
            self.assertEqual(status, 200)
            self.assertTrue(payload["ok"])
            self.assertEqual(refreshed.status, WorkflowStatus.DISCUSSING)
            self.assertEqual(refreshed.latest_question, "AI review 认为仍需继续修改需求文档。")
            self.assertEqual(refreshed.latest_review_summary, "AI review 认为仍需继续修改需求文档。")
            self.assertTrue(
                any("AI Review 未通过" in card["header"]["title"]["content"] for _, _, card in gateway.card_messages)
            )

    def test_author_callback_sends_follow_up_for_reviewer_handoff(self) -> None:
        class FakeGateway:
            def __init__(self) -> None:
                self.text_messages = []
                self.card_messages = []

            def sync_requirement_document(self, requirement) -> None:
                return None

            def update_requirement_record(self, requirement) -> None:
                return None

            def send_text(self, receive_id, text, receive_id_type="chat_id") -> None:
                self.text_messages.append((receive_id, receive_id_type, text))

            def send_card(self, receive_id, card, receive_id_type="chat_id") -> None:
                self.card_messages.append((receive_id, receive_id_type, card))

        with TemporaryDirectory() as temp_dir:
            runtime_service = CoordinatorService()
            response = runtime_service.create_requirement_from_group(
                CreationRequest(
                    project="HARNESS",
                    name="author callback follow-up 测试",
                    summary="验证进入 AI Review 时会发 reviewer 接手通知。",
                    creator="tester",
                    creator_user_id="user-1",
                    creation_chat_id="chat-1",
                )
            )
            requirement = runtime_service.get_requirement(response.req_id)
            assert requirement is not None
            requirement.project_group_id = "oc_group_1"

            gateway = FakeGateway()
            app = CoordinatorRuntimeApp(
                Settings(
                    feishu_app_id="app-id",
                    feishu_app_secret="app-secret",
                    openclaw_reviewer_agent_name="需求审查助手",
                    state_store_path=str(Path(temp_dir) / "state.json"),
                ),
                service=runtime_service,
                gateway=gateway,
            )

            status, payload = app.handle_openclaw_author_turn_callback(
                json.dumps(
                    {
                        "req_id": response.req_id,
                        "event": "author_ready_for_ai_review",
                        "summary": "需求文档已完成当前轮撰写。",
                        "document_url": "https://example.com/doc/reviewer-handoff",
                        "iteration_round": 1,
                    },
                    ensure_ascii=False,
                ).encode()
            )

            self.assertEqual(status, 200)
            self.assertTrue(payload["ok"])
            self.assertTrue(
                any("已进入 AI Review" in card["header"]["title"]["content"] for _, _, card in gateway.card_messages)
            )
            self.assertTrue(
                any("需求审查助手" in json.dumps(card, ensure_ascii=False) for _, _, card in gateway.card_messages)
            )

    def test_openclaw_review_result_callback_accepts_valid_signature(self) -> None:
        class FakeGateway:
            def sync_requirement_document(self, requirement) -> None:
                return None

            def update_requirement_record(self, requirement) -> None:
                return None

        with TemporaryDirectory() as temp_dir:
            runtime_service = CoordinatorService()
            response = runtime_service.create_requirement_from_group(
                CreationRequest(
                    project="HARNESS",
                    name="review callback 鉴权测试",
                    summary="验证合法签名可通过。",
                    creator="tester",
                    creator_user_id="user-1",
                    creation_chat_id="chat-1",
                )
            )
            requirement = runtime_service.get_requirement(response.req_id)
            assert requirement is not None
            runtime_service.handoff_to_author(requirement)
            runtime_service.submit_author_event_payload(
                AgentAuthorEventPayload(
                    req_id=response.req_id,
                    event="author_ready_for_ai_review",
                    summary="author 已完成需求文档撰写。",
                    document_url="https://example.com/doc/signed-review",
                    iteration_round=1,
                )
            )

            secret = "shared-secret"
            app = CoordinatorRuntimeApp(
                Settings(
                    feishu_app_id="app-id",
                    feishu_app_secret="app-secret",
                    openclaw_callback_secret=secret,
                    state_store_path=str(Path(temp_dir) / "state.json"),
                ),
                service=runtime_service,
                gateway=FakeGateway(),
            )

            raw_body = json.dumps(
                {
                    "req_id": response.req_id,
                    "event": "review_returned_for_revision",
                    "review_summary": "当前 review 已完成，需继续修改。",
                    "review_notes_url": "https://example.com/review-notes/2",
                },
                ensure_ascii=False,
            ).encode()
            timestamp = str(int(time.time()))
            signature = hmac.new(
                secret.encode("utf-8"),
                timestamp.encode("utf-8") + b"." + raw_body,
                hashlib.sha256,
            ).hexdigest()

            status, payload = app.handle_openclaw_review_result_callback(
                raw_body,
                headers={
                    "X-OpenClaw-Timestamp": timestamp,
                    "X-OpenClaw-Signature": signature,
                },
            )

            refreshed = runtime_service.get_requirement(response.req_id)
            assert refreshed is not None
            self.assertEqual(status, 200)
            self.assertTrue(payload["ok"])
            self.assertEqual(refreshed.status, WorkflowStatus.DISCUSSING)

    def test_openclaw_review_result_callback_rejects_human_confirmation_event(self) -> None:
        class FakeGateway:
            def sync_requirement_document(self, requirement) -> None:
                return None

            def update_requirement_record(self, requirement) -> None:
                return None

        with TemporaryDirectory() as temp_dir:
            runtime_service = CoordinatorService()
            response = runtime_service.create_requirement_from_group(
                CreationRequest(
                    project="HARNESS",
                    name="review callback 权限边界测试",
                    summary="验证 reviewer 不能代替人工确认推进状态。",
                    creator="tester",
                    creator_user_id="user-1",
                    creation_chat_id="chat-1",
                )
            )
            requirement = runtime_service.get_requirement(response.req_id)
            assert requirement is not None
            runtime_service.handoff_to_author(requirement)
            runtime_service.submit_author_event_payload(
                AgentAuthorEventPayload(
                    req_id=response.req_id,
                    event="author_ready_for_ai_review",
                    summary="author 已完成需求文档撰写。",
                    document_url="https://example.com/doc/reviewer-boundary",
                    iteration_round=1,
                )
            )

            app = CoordinatorRuntimeApp(
                Settings(
                    feishu_app_id="app-id",
                    feishu_app_secret="app-secret",
                    state_store_path=str(Path(temp_dir) / "state.json"),
                ),
                service=runtime_service,
                gateway=FakeGateway(),
            )

            status, payload = app.handle_openclaw_review_result_callback(
                json.dumps(
                    {
                        "req_id": response.req_id,
                        "event": "human_confirmed",
                        "review_summary": "reviewer 误将人工确认也作为 callback 上报。",
                        "review_notes_url": "https://example.com/review-notes/forbidden",
                    },
                    ensure_ascii=False,
                ).encode()
            )

            refreshed = runtime_service.get_requirement(response.req_id)
            assert refreshed is not None
            self.assertEqual(status, 400)
            self.assertEqual(payload["error"], "invalid_payload")

    def test_human_confirmation_card_callback_advances_to_final_review(self) -> None:
        class FakeGateway:
            def __init__(self) -> None:
                self.cards = []

            def sync_requirement_document(self, requirement) -> None:
                return None

            def update_requirement_record(self, requirement) -> None:
                return None

            def send_card(self, receive_id, card, receive_id_type="chat_id") -> None:
                self.cards.append((receive_id, receive_id_type, card))

            def bitable_url(self) -> str:
                return "https://example.com/bitable"

        with TemporaryDirectory() as temp_dir:
            runtime_service = CoordinatorService()
            response = runtime_service.create_requirement_from_group(
                CreationRequest(
                    project="HARNESS",
                    name="人工确认卡片回调测试",
                    summary="验证人工确认按钮会自动推进工作流。",
                    creator="tester",
                    creator_user_id="user-1",
                    creation_chat_id="chat-1",
                )
            )
            requirement = runtime_service.get_requirement(response.req_id)
            assert requirement is not None
            runtime_service.handoff_to_author(requirement)
            requirement.status = WorkflowStatus.HUMAN_CONFIRM
            requirement.ai_ready = True

            gateway = FakeGateway()
            app = CoordinatorRuntimeApp(
                Settings(
                    feishu_app_id="app-id",
                    feishu_app_secret="app-secret",
                    state_store_path=str(Path(temp_dir) / "state.json"),
                ),
                service=runtime_service,
                gateway=gateway,
            )

            status, payload = app.handle_card_callback(
                json.dumps(
                    {
                        "operator": {"open_id": "user-1", "name": "tester"},
                        "action": {
                            "value": {
                                "action": "human_confirm_yes",
                                "req_id": response.req_id,
                            }
                        },
                    },
                    ensure_ascii=False,
                ).encode()
            )

            refreshed = runtime_service.get_requirement(response.req_id)
            assert refreshed is not None
            self.assertEqual(status, 200)
            self.assertEqual(payload["toast"]["type"], "success")
            self.assertEqual(refreshed.status, WorkflowStatus.FINAL_REVIEW)
            self.assertTrue(refreshed.human_confirmed)

    def test_final_review_card_callback_advances_to_approved(self) -> None:
        class FakeGateway:
            def __init__(self) -> None:
                self.cards = []

            def sync_requirement_document(self, requirement) -> None:
                return None

            def update_requirement_record(self, requirement) -> None:
                return None

            def send_card(self, receive_id, card, receive_id_type="chat_id") -> None:
                self.cards.append((receive_id, receive_id_type, card))

            def bitable_url(self) -> str:
                return "https://example.com/bitable"

        with TemporaryDirectory() as temp_dir:
            runtime_service = CoordinatorService()
            response = runtime_service.create_requirement_from_group(
                CreationRequest(
                    project="HARNESS",
                    name="正式审查卡片回调测试",
                    summary="验证正式审查按钮会自动推进工作流。",
                    creator="tester",
                    creator_user_id="user-1",
                    creation_chat_id="chat-1",
                )
            )
            requirement = runtime_service.get_requirement(response.req_id)
            assert requirement is not None
            runtime_service.handoff_to_author(requirement)
            requirement.status = WorkflowStatus.FINAL_REVIEW
            requirement.ai_ready = True
            requirement.human_confirmed = True

            gateway = FakeGateway()
            app = CoordinatorRuntimeApp(
                Settings(
                    feishu_app_id="app-id",
                    feishu_app_secret="app-secret",
                    state_store_path=str(Path(temp_dir) / "state.json"),
                ),
                service=runtime_service,
                gateway=gateway,
            )

            status, payload = app.handle_card_callback(
                json.dumps(
                    {
                        "operator": {"open_id": "user-1", "name": "tester"},
                        "action": {
                            "value": {
                                "action": "final_review_pass",
                                "req_id": response.req_id,
                            }
                        },
                    },
                    ensure_ascii=False,
                ).encode()
            )

            refreshed = runtime_service.get_requirement(response.req_id)
            assert refreshed is not None
            self.assertEqual(status, 200)
            self.assertEqual(payload["toast"]["type"], "success")
            self.assertEqual(refreshed.status, WorkflowStatus.APPROVED)

    def test_openclaw_requirement_context_query_returns_context(self) -> None:
        class FakeGateway:
            def sync_requirement_document(self, requirement) -> None:
                return None

            def update_requirement_record(self, requirement) -> None:
                return None

            def bitable_url(self) -> str:
                return "https://example.com/base/app-token?table=tbl-1"

        with TemporaryDirectory() as temp_dir:
            runtime_service = CoordinatorService()
            response = runtime_service.create_requirement_from_group(
                CreationRequest(
                    project="HARNESS",
                    name="context query 测试",
                    summary="验证 agent 可按 req_id 拉取上下文。",
                    creator="tester",
                    creator_user_id="user-1",
                    creation_chat_id="chat-1",
                )
            )
            requirement = runtime_service.get_requirement(response.req_id)
            assert requirement is not None
            runtime_service.handoff_to_author(requirement)
            runtime_service.attach_bitable_record(response.req_id, "rec-1")
            runtime_service.attach_document(response.req_id, "doc-1", "https://example.com/doc/context")
            runtime_service.submit_author_event_payload(
                AgentAuthorEventPayload(
                    req_id=response.req_id,
                    event="author_ready_for_ai_review",
                    summary="author 已完成需求文档撰写。",
                    document_url="https://example.com/doc/context",
                    iteration_round=2,
                )
            )

            app = CoordinatorRuntimeApp(
                Settings(
                    feishu_app_id="app-id",
                    feishu_app_secret="app-secret",
                    state_store_path=str(Path(temp_dir) / "state.json"),
                ),
                service=runtime_service,
                gateway=FakeGateway(),
            )

            status, payload = app.handle_openclaw_requirement_context_query(
                json.dumps({"req_id": response.req_id}, ensure_ascii=False).encode()
            )

            self.assertEqual(status, 200)
            self.assertTrue(payload["ok"])
            context = payload["context"]
            self.assertEqual(context["req_id"], response.req_id)
            self.assertEqual(context["status"], WorkflowStatus.AI_REVIEWING.value)
            self.assertEqual(context["document_url"], "https://example.com/doc/context")
            self.assertEqual(context["bitable_record_id"], "rec-1")
            self.assertEqual(context["bitable_url"], "https://example.com/base/app-token?table=tbl-1")

    def test_openclaw_requirement_context_query_auto_handoffs_from_discussion_routing(self) -> None:
        class FakeGateway:
            def sync_requirement_document(self, requirement) -> None:
                return None

            def update_requirement_record(self, requirement) -> None:
                return None

            def bitable_url(self) -> str:
                return "https://example.com/base/app-token?table=tbl-1"

        with TemporaryDirectory() as temp_dir:
            runtime_service = CoordinatorService()
            response = runtime_service.create_requirement_from_group(
                CreationRequest(
                    project="HARNESS",
                    name="context auto handoff 测试",
                    summary="验证 agent 拉上下文时可自动进入 DISCUSSING。",
                    creator="tester",
                    creator_user_id="user-1",
                    creation_chat_id="chat-1",
                )
            )

            app = CoordinatorRuntimeApp(
                Settings(
                    feishu_app_id="app-id",
                    feishu_app_secret="app-secret",
                    state_store_path=str(Path(temp_dir) / "state.json"),
                ),
                service=runtime_service,
                gateway=FakeGateway(),
            )

            status, payload = app.handle_openclaw_requirement_context_query(
                json.dumps({"req_id": response.req_id}, ensure_ascii=False).encode()
            )

            refreshed = runtime_service.get_requirement(response.req_id)
            assert refreshed is not None
            self.assertEqual(status, 200)
            self.assertTrue(payload["ok"])
            self.assertEqual(refreshed.status, WorkflowStatus.DISCUSSING)
            self.assertEqual(payload["context"]["status"], WorkflowStatus.DISCUSSING.value)
            self.assertEqual(payload["context"]["current_owner"], "author")

    def test_openclaw_author_callback_auto_handoffs_from_discussion_routing(self) -> None:
        class FakeGateway:
            def sync_requirement_document(self, requirement) -> None:
                return None

            def update_requirement_record(self, requirement) -> None:
                return None

        with TemporaryDirectory() as temp_dir:
            runtime_service = CoordinatorService()
            response = runtime_service.create_requirement_from_group(
                CreationRequest(
                    project="HARNESS",
                    name="author callback auto handoff 测试",
                    summary="验证 author callback 不会再被 DISCUSSION_ROUTING 卡住。",
                    creator="tester",
                    creator_user_id="user-1",
                    creation_chat_id="chat-1",
                )
            )

            app = CoordinatorRuntimeApp(
                Settings(
                    feishu_app_id="app-id",
                    feishu_app_secret="app-secret",
                    state_store_path=str(Path(temp_dir) / "state.json"),
                ),
                service=runtime_service,
                gateway=FakeGateway(),
            )

            status, payload = app.handle_openclaw_author_turn_callback(
                json.dumps(
                    {
                        "req_id": response.req_id,
                        "event": "author_ready_for_ai_review",
                        "summary": "author 已完成需求文档撰写。",
                        "document_url": "https://example.com/doc/auto-handoff",
                        "iteration_round": 1,
                    },
                    ensure_ascii=False,
                ).encode()
            )

            refreshed = runtime_service.get_requirement(response.req_id)
            assert refreshed is not None
            self.assertEqual(status, 200)
            self.assertTrue(payload["ok"])
            self.assertEqual(refreshed.status, WorkflowStatus.AI_REVIEWING)
            self.assertEqual(refreshed.current_phase, "AI Review")
            self.assertEqual(refreshed.document_url, "https://example.com/doc/auto-handoff")

    def test_openclaw_requirement_context_query_rejects_missing_signature(self) -> None:
        class FakeGateway:
            def sync_requirement_document(self, requirement) -> None:
                return None

            def update_requirement_record(self, requirement) -> None:
                return None

            def bitable_url(self) -> str:
                return ""

        with TemporaryDirectory() as temp_dir:
            runtime_service = CoordinatorService()
            response = runtime_service.create_requirement_from_group(
                CreationRequest(
                    project="HARNESS",
                    name="context query 鉴权测试",
                    summary="验证上下文查询缺签名时会被拒绝。",
                    creator="tester",
                    creator_user_id="user-1",
                    creation_chat_id="chat-1",
                )
            )

            app = CoordinatorRuntimeApp(
                Settings(
                    feishu_app_id="app-id",
                    feishu_app_secret="app-secret",
                    openclaw_callback_secret="shared-secret",
                    state_store_path=str(Path(temp_dir) / "state.json"),
                ),
                service=runtime_service,
                gateway=FakeGateway(),
            )

            status, payload = app.handle_openclaw_requirement_context_query(
                json.dumps({"req_id": response.req_id}, ensure_ascii=False).encode()
            )

            self.assertEqual(status, 401)
            self.assertEqual(payload["error"], "unauthorized")


if __name__ == "__main__":
    unittest.main()
