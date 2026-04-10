from __future__ import annotations

import json
import logging
import re
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from .config import Settings, load_settings
from .coordinator_service import AuthorTurnResult, CoordinatorService
from .feishu_gateway import FeishuGateway
from .models import ReviewResult, WorkflowStatus
from .protocols import AuthorStartBinding, CreationFormPayload, CreationRequest
from .store import JsonStateStore

try:
    import lark_oapi as lark
    from lark_oapi.api.im.v1.model.p2_im_message_receive_v1 import P2ImMessageReceiveV1
except ImportError:  # pragma: no cover - optional during local editing before deps are installed
    lark = None
    P2ImMessageReceiveV1 = Any


LOGGER = logging.getLogger(__name__)


@dataclass
class MessageContext:
    chat_id: str
    chat_type: str
    user_id: str
    text: str
    message_id: str = ""
    thread_id: str = ""
    sender_name: str = ""


@dataclass
class OutboundMessage:
    receive_id: str
    text: str
    receive_id_type: str = "chat_id"


@dataclass
class OutboundCard:
    receive_id: str
    card: dict[str, object]
    receive_id_type: str = "chat_id"


class CoordinatorRuntimeApp:
    """Harness-style runtime for the coordinator service."""

    def __init__(
        self,
        settings: Settings,
        store: JsonStateStore | None = None,
        service: CoordinatorService | None = None,
    ) -> None:
        self.settings = settings
        self.settings.validate_runtime()
        self.store = store or JsonStateStore(settings.state_store_path)
        self.service = service or CoordinatorService()
        self.gateway = FeishuGateway(settings)
        requirements, active_req_by_user, project_groups = self.store.load_snapshot()
        self.service.restore_snapshot(requirements, active_req_by_user, project_groups)
        self._health_server: HTTPServer | None = None
        self._observed_creation_group_chat_id = settings.creation_group_chat_id

    def build_event_dispatcher(self):
        self._require_lark()
        builder = lark.EventDispatcherHandler.builder(
            self.settings.feishu_encrypt_key,
            self.settings.feishu_verification_token,
            getattr(lark.LogLevel, self.settings.feishu_log_level.upper(), lark.LogLevel.INFO),
        )
        return builder.register_p2_im_message_receive_v1(self._on_message_receive).build()

    def build_ws_client(self):
        self._require_lark()
        return lark.ws.Client(
            self.settings.feishu_app_id,
            self.settings.feishu_app_secret,
            event_handler=self.build_event_dispatcher(),
            log_level=getattr(lark.LogLevel, self.settings.feishu_log_level.upper(), lark.LogLevel.INFO),
        )

    def start(self) -> None:
        self.start_health_server()
        LOGGER.info("Starting coordinator long connection runtime")
        self.build_ws_client().start()

    def start_health_server(self) -> None:
        service_name = self.settings.service_name
        app = self

        class HealthHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                body = json.dumps({"status": "ok", "service": service_name}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                raw_body = self.rfile.read(length) if length else b"{}"
                if self.path == "/callbacks/card":
                    status, payload = app.handle_card_callback(raw_body)
                else:
                    status, payload = 404, {"error": "not_found"}
                body = json.dumps(payload, ensure_ascii=False).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args):
                return

        self._health_server = HTTPServer(("0.0.0.0", self.settings.service_port), HealthHandler)
        thread = threading.Thread(target=self._health_server.serve_forever, daemon=True)
        thread.start()
        LOGGER.info("Health server listening on %s", self.settings.service_port)

    def _on_message_receive(self, data: P2ImMessageReceiveV1) -> None:
        context = self._extract_message_context(data)
        if context is None:
            return
        LOGGER.info(
            "Received message chat_id=%s chat_type=%s user_id=%s text=%r",
            context.chat_id,
            context.chat_type,
            context.user_id,
            context.text,
        )
        for outbound in self.handle_text_message(context):
            if isinstance(outbound, OutboundCard):
                self.gateway.send_card(outbound.receive_id, outbound.card, receive_id_type=outbound.receive_id_type)
            else:
                self.gateway.send_text(outbound.receive_id, outbound.text, receive_id_type=outbound.receive_id_type)

    def handle_text_message(self, context: MessageContext) -> list[OutboundMessage | OutboundCard]:
        text = context.text.strip()
        if not text:
            return []

        if self._is_creation_group_message(context):
            return self._handle_creation_group_message(context)

        if context.chat_type == "p2p":
            return self._handle_author_private_message(context)

        return []

    def _handle_creation_group_message(self, context: MessageContext) -> list[OutboundMessage | OutboundCard]:
        if "创建需求" not in context.text:
            return []
        self._observed_creation_group_chat_id = context.chat_id
        return [
            OutboundCard(
                receive_id=context.chat_id,
                card=self._build_requirement_creation_card(context),
            )
        ]

    def _create_requirement_from_form(
        self,
        payload: CreationFormPayload,
    ) -> list[OutboundMessage | OutboundCard]:
        response = self.service.create_requirement_from_group(
            CreationRequest(
                project=payload.project,
                name=payload.name,
                summary=payload.summary,
                creator=payload.creator,
                creator_user_id=payload.creator_user_id,
                creation_chat_id=payload.creation_chat_id,
            )
        )
        requirement = self.service.get_requirement(response.req_id)
        if requirement is not None:
            if not self._is_feishu_chat_id(requirement.project_group_id):
                try:
                    project_group = self.gateway.create_project_group(
                        project=requirement.project,
                        owner_user_id=payload.creator_user_id,
                        member_user_ids=[payload.creator_user_id],
                    )
                    self.service.assign_project_group(requirement.req_id, project_group.chat_id)
                    response.project_group_id = project_group.chat_id
                except Exception as exc:
                    LOGGER.warning("Failed to create project group for %s: %s", requirement.req_id, exc)

            try:
                created_record = self.gateway.create_requirement_record(requirement)
                if created_record:
                    self.service.attach_bitable_record(requirement.req_id, created_record.record_id)
            except Exception as exc:
                LOGGER.warning("Failed to create bitable record for %s: %s", requirement.req_id, exc)

            try:
                created_document = self.gateway.create_requirement_document(requirement)
                if created_document:
                    self.service.attach_document(
                        requirement.req_id,
                        created_document.document_id,
                        created_document.document_url,
                    )
            except Exception as exc:
                LOGGER.warning("Failed to create document for %s: %s", requirement.req_id, exc)

            requirement = self.service.get_requirement(requirement.req_id)
            if requirement and requirement.document_id:
                try:
                    self.gateway.sync_requirement_document(requirement)
                except Exception as exc:
                    LOGGER.warning("Failed to sync requirement document for %s: %s", requirement.req_id, exc)

            if requirement and requirement.bitable_record_id:
                try:
                    self.gateway.update_requirement_record(requirement)
                except Exception as exc:
                    LOGGER.warning("Failed to refresh bitable record for %s: %s", requirement.req_id, exc)

        self._save_state()
        requirement = self.service.get_requirement(response.req_id)
        creation_text = response.message_to_creation_group
        if requirement and requirement.document_url:
            creation_text += f"\n需求文档：{requirement.document_url}"
        bitable_url = self.gateway.bitable_url()
        if bitable_url:
            creation_text += f"\n多维表格：{bitable_url}"
        messages: list[OutboundMessage | OutboundCard] = [
            OutboundMessage(receive_id=payload.creation_chat_id, text=creation_text)
        ]
        if self._is_feishu_chat_id(response.project_group_id):
            messages.append(
                OutboundCard(
                    receive_id=response.project_group_id,
                    card=self._build_project_group_card(requirement),
                )
            )
        return messages

    def _handle_author_private_message(self, context: MessageContext) -> list[OutboundMessage]:
        text = context.text.strip()
        if text.startswith("开始需求构造 "):
            req_id = text.replace("开始需求构造 ", "", 1).strip()
            response = self.service.start_author_private_session(
                AuthorStartBinding(
                    req_id=req_id,
                    author_dm_chat_id=context.chat_id,
                    user_id=context.user_id,
                )
            )
            self._save_state()
            return [OutboundMessage(receive_id=context.chat_id, text=response.message)]

        if text.startswith("切换需求 "):
            req_id = text.replace("切换需求 ", "", 1).strip()
            response = self.service.switch_active_requirement(context.user_id, req_id)
            self._save_state()
            return [OutboundMessage(receive_id=context.chat_id, text=response.message)]

        if text == "确认需求":
            return self._handle_human_confirmation(context, approved=True)

        if text == "继续修改":
            return self._handle_human_confirmation(context, approved=False)

        response = self.service.confirm_author_private_binding(context.user_id, text)
        if response.accepted:
            self._save_state()
            return [OutboundMessage(receive_id=context.chat_id, text=response.message)]

        active_req_id = self.service.active_req_by_user.get(context.user_id)
        if active_req_id:
            requirement = self.service.get_requirement(active_req_id)
            if requirement is not None and requirement.active_private_binding_confirmed:
                if requirement.status == WorkflowStatus.DISCUSSING:
                    return self._handle_author_turn(context, requirement)
                if requirement.status == WorkflowStatus.HUMAN_CONFIRMING:
                    return [
                        OutboundMessage(
                            receive_id=context.chat_id,
                            text="当前处于人工确认阶段，请回复“确认需求”或“继续修改”。",
                        )
                    ]
                if requirement.status == WorkflowStatus.REQ_APPROVED:
                    return [
                        OutboundMessage(
                            receive_id=context.chat_id,
                            text=f"{requirement.req_id} 已完成当前阶段，如需新需求请回创建群重新发起。",
                        )
                    ]

        return [OutboundMessage(receive_id=context.chat_id, text=response.message)]

    def _handle_author_turn(self, context: MessageContext, requirement) -> list[OutboundMessage]:
        current_field = requirement.current_discussion_field
        next_field = self._next_discussion_field(requirement)
        if next_field:
            next_question = self._question_for_field(next_field)
        else:
            next_question = "当前核心字段已补齐，AI review 将进入人工确认。若内容准确，请回复“确认需求”；如需继续打磨，请回复“继续修改”。"

        turn = AuthorTurnResult(
            updates={current_field: context.text.strip()},
            next_question=next_question,
            current_field_completed=True,
            next_field=next_field,
        )
        requirement = self.service.handle_author_turn(requirement, turn)

        review = ReviewResult(
            ready_for_human_confirmation=not requirement.pending_fields,
            summary=(
                "当前核心字段已齐备，可以进入人工确认。"
                if not requirement.pending_fields
                else f"当前已补充【{current_field}】，下一轮请继续完善【{requirement.current_discussion_field}】。"
            ),
            next_focus=None if not requirement.pending_fields else requirement.latest_question,
        )
        requirement = self.service.handle_review_result(requirement, review)
        self._sync_requirement_outputs(requirement)
        self._save_state()

        if requirement.status == WorkflowStatus.HUMAN_CONFIRMING:
            response_text = (
                f"需求构造 Agent：已更新【{current_field}】。\n\n"
                f"审查 Agent：{requirement.latest_review_summary}\n\n"
                f"{requirement.latest_question}\n"
                "请回复“确认需求”或“继续修改”。"
            )
        else:
            response_text = (
                f"需求构造 Agent：已更新【{current_field}】。\n\n"
                f"审查 Agent：{requirement.latest_review_summary}\n\n"
                f"下一步：{requirement.latest_question}"
            )
        return [OutboundMessage(receive_id=context.chat_id, text=response_text)]

    def _handle_human_confirmation(self, context: MessageContext, approved: bool) -> list[OutboundMessage]:
        active_req_id = self.service.active_req_by_user.get(context.user_id)
        if not active_req_id:
            return [OutboundMessage(receive_id=context.chat_id, text="当前没有激活的需求，请先发送“开始需求构造 REQ-ID”。")]

        requirement = self.service.get_requirement(active_req_id)
        if requirement is None:
            return [OutboundMessage(receive_id=context.chat_id, text=f"未知需求：{active_req_id}")]
        if requirement.status != WorkflowStatus.HUMAN_CONFIRMING:
            return [OutboundMessage(receive_id=context.chat_id, text="当前还没到人工确认阶段，请先继续完成需求构造。")]

        requirement = self.service.handle_human_confirmation(requirement, approved=approved)
        if approved:
            requirement = self.service.approve_requirement(requirement)

        self._sync_requirement_outputs(requirement)
        self._save_state()

        if approved:
            response_text = (
                f"{requirement.req_id} 已完成需求构造并进入通过状态。\n\n"
                f"当前状态：{requirement.status.value}\n"
                f"需求文档：{requirement.document_url or '待同步'}"
            )
        else:
            response_text = (
                f"{requirement.req_id} 已退回继续打磨。\n\n"
                f"下一步：{requirement.latest_question}"
            )
        return [OutboundMessage(receive_id=context.chat_id, text=response_text)]

    def handle_card_callback(self, raw_body: bytes) -> tuple[int, dict[str, object]]:
        try:
            payload = json.loads(raw_body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return 400, {"error": "invalid_json"}

        if "challenge" in payload:
            return 200, {"challenge": payload["challenge"]}

        action = payload.get("action", {}) or {}
        value = self._extract_callback_value(action)
        action_name = value.get("action")
        operator = payload.get("operator", {}) or {}
        user_id = operator.get("open_id", "")
        user_name = operator.get("name", "")

        if action_name == "submit_create_requirement":
            form_payload = self._extract_creation_form_payload(payload, user_id=user_id, user_name=user_name)
            if form_payload is None:
                return 200, {"toast": {"type": "error", "content": "创建表单字段不完整，请补充项目、名称和简述。"}}
            messages = self._create_requirement_from_form(form_payload)
            for outbound in messages:
                if isinstance(outbound, OutboundCard):
                    self.gateway.send_card(outbound.receive_id, outbound.card, receive_id_type=outbound.receive_id_type)
                else:
                    self.gateway.send_text(outbound.receive_id, outbound.text, receive_id_type=outbound.receive_id_type)
            return 200, {"toast": {"type": "success", "content": "需求已创建，项目群同步已开始。"}}

        if action_name == "send_author_start":
            req_id = value.get("req_id", "")
            if not req_id:
                return 200, {"toast": {"type": "error", "content": "缺少需求ID。"}}
            agent_name = self.settings.openclaw_author_agent_name
            start_command = f"开始需求构造 {req_id}"
            self.gateway.send_text(
                user_id,
                f"请私聊 {agent_name}，并发送：\n{start_command}",
                receive_id_type=self.settings.feishu_user_id_type,
            )
            return 200, {"toast": {"type": "success", "content": "已将启动指令私发给你。"}}

        return 200, {"toast": {"type": "info", "content": "未识别的卡片动作，已忽略。"}}

    def _parse_creation_command(self, text: str) -> dict[str, str] | None:
        fields: dict[str, str] = {}
        aliases = {"项目": "project", "名称": "name", "简述": "summary", "背景": "summary"}
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if "：" in line:
                key, value = line.split("：", 1)
            elif ":" in line:
                key, value = line.split(":", 1)
            else:
                continue
            normalized = aliases.get(key.strip())
            if normalized and value.strip():
                fields[normalized] = value.strip()

        # Allow one-line freeform messages like:
        # 创建需求 项目: HARNESS 名称: xxx 简述: yyy
        if "project" not in fields:
            matched = re.search(r"项目\s*[:：]\s*([^\n]+?)(?=\s+名称\s*[:：]|$)", text)
            if matched:
                fields["project"] = matched.group(1).strip()
        if "name" not in fields:
            matched = re.search(r"名称\s*[:：]\s*([^\n]+?)(?=\s+简述\s*[:：]|\s+背景\s*[:：]|$)", text)
            if matched:
                fields["name"] = matched.group(1).strip()
        if "summary" not in fields:
            matched = re.search(r"(?:简述|背景)\s*[:：]\s*([^\n]+)", text)
            if matched:
                fields["summary"] = matched.group(1).strip()

        required = {"project", "name", "summary"}
        if not required.issubset(fields):
            return None
        return fields

    def _extract_creation_form_payload(
        self,
        payload: dict[str, object],
        *,
        user_id: str,
        user_name: str,
    ) -> CreationFormPayload | None:
        action = payload.get("action", {}) or {}
        value = self._extract_callback_value(action)
        form_value = action.get("form_value") or payload.get("form_value") or {}
        if not isinstance(form_value, dict):
            form_value = {}

        project = self._normalize_form_value(form_value.get("project"))
        name = self._normalize_form_value(form_value.get("name"))
        summary = self._normalize_form_value(form_value.get("summary"))
        if not project or not name or not summary:
            return None

        creation_chat_id = self._normalize_form_value(value.get("creation_chat_id")) or self._observed_creation_group_chat_id
        return CreationFormPayload(
            project=project,
            name=name,
            summary=summary,
            creator=user_name or user_id,
            creator_user_id=user_id,
            creation_chat_id=creation_chat_id,
            background_links=self._normalize_form_value(form_value.get("background_links")),
            priority=self._normalize_form_value(form_value.get("priority")),
            expected_due_date=self._normalize_form_value(form_value.get("expected_due_date")),
        )

    def _normalize_form_value(self, value: object) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, list):
            normalized = [self._normalize_form_value(item) for item in value]
            return ", ".join(item for item in normalized if item)
        if isinstance(value, dict):
            for key in ("value", "text", "name", "content"):
                if key in value:
                    return self._normalize_form_value(value[key])
            return ""
        return str(value).strip()

    def _extract_callback_value(self, action: dict[str, object]) -> dict[str, object]:
        direct = action.get("value")
        if isinstance(direct, dict):
            return direct
        behaviors = action.get("behaviors")
        if isinstance(behaviors, list):
            for item in behaviors:
                if isinstance(item, dict) and item.get("type") == "callback" and isinstance(item.get("value"), dict):
                    return item["value"]
        return {}

    def _build_requirement_creation_card(self, context: MessageContext) -> dict[str, object]:
        return {
            "schema": "2.0",
            "config": {"wide_screen_mode": True},
            "header": {
                "template": "blue",
                "title": {"tag": "plain_text", "content": "创建需求"},
            },
            "body": {
                "elements": [
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": (
                                "请填写最小需求信息。\n"
                                "提交后，CoordinatorService 会自动创建 `REQ ID`、多维表格记录、需求文档和项目需求群。"
                            ),
                        },
                    },
                    {
                        "tag": "note",
                        "elements": [
                            {"tag": "plain_text", "content": "必填：项目代号、需求名称、需求简述"},
                        ],
                    },
                    {
                        "tag": "form",
                        "name": "requirement_create_form",
                        "elements": [
                            {
                                "tag": "input",
                                "name": "project",
                                "required": True,
                                "width": "fill",
                                "placeholder": {"tag": "plain_text", "content": "项目代号，例如 HARNESS"},
                            },
                            {
                                "tag": "input",
                                "name": "name",
                                "required": True,
                                "width": "fill",
                                "placeholder": {"tag": "plain_text", "content": "需求名称，例如 多轮需求构造工作流"},
                            },
                            {
                                "tag": "input",
                                "name": "summary",
                                "required": True,
                                "width": "fill",
                                "input_type": "multiline_text",
                                "max_length": 500,
                                "placeholder": {"tag": "plain_text", "content": "需求简述：要解决什么问题，期望得到什么结果"},
                            },
                            {
                                "tag": "input",
                                "name": "background_links",
                                "width": "fill",
                                "input_type": "multiline_text",
                                "max_length": 1000,
                                "placeholder": {"tag": "plain_text", "content": "背景材料链接，可选；多个链接请换行"},
                            },
                            {
                                "tag": "select_static",
                                "name": "priority",
                                "placeholder": {"tag": "plain_text", "content": "优先级，可选"},
                                "options": [
                                    {"text": {"tag": "plain_text", "content": "P0"}, "value": "P0"},
                                    {"text": {"tag": "plain_text", "content": "P1"}, "value": "P1"},
                                    {"text": {"tag": "plain_text", "content": "P2"}, "value": "P2"},
                                ],
                            },
                            {
                                "tag": "date_picker",
                                "name": "expected_due_date",
                                "placeholder": {"tag": "plain_text", "content": "期望完成时间，可选"},
                            },
                            {
                                "tag": "button",
                                "name": "submit_create_requirement",
                                "text": {"tag": "plain_text", "content": "提交创建"},
                                "type": "primary_filled",
                                "form_action_type": "submit",
                                "behaviors": [
                                    {
                                        "type": "callback",
                                        "value": {
                                            "action": "submit_create_requirement",
                                            "creation_chat_id": context.chat_id,
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                ]
            },
        }

    def _build_project_group_card(self, requirement) -> dict[str, object]:
        elements: list[dict[str, object]] = [
            {
                "tag": "markdown",
                "content": (
                    f"已创建需求 **{requirement.req_id}**\n"
                    f"- 名称：{requirement.name}\n"
                    f"- 当前状态：{requirement.status.value}\n"
                    f"- 当前角色：{requirement.current_role_label}"
                ),
            }
        ]

        links: list[str] = []
        if requirement.document_url:
            links.append(f"[查看需求文档]({requirement.document_url})")
        bitable_url = self.gateway.bitable_url()
        if bitable_url:
            links.append(f"[查看多维表格]({bitable_url})")
        if links:
            elements.append({"tag": "markdown", "content": " | ".join(links)})

        actions: list[dict[str, object]] = [
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "私发启动指令"},
                "type": "primary",
                "value": {"action": "send_author_start", "req_id": requirement.req_id},
            }
        ]
        if self.settings.author_agent_chat_url_template:
            actions.insert(
                0,
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "打开需求构造助手"},
                    "type": "default",
                    "multi_url": {
                        "url": self.settings.author_agent_chat_url_template.format(req_id=requirement.req_id),
                    },
                },
            )
        elements.append({"tag": "action", "actions": actions})
        elements.append(
            {
                "tag": "note",
                "elements": [
                    {
                        "tag": "plain_text",
                        "content": f"如果需要手动启动，请私聊 {self.settings.openclaw_author_agent_name} 并发送：开始需求构造 {requirement.req_id}",
                    }
                ],
            }
        )

        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": "green",
                "title": {"tag": "plain_text", "content": f"{requirement.req_id} 已创建"},
            },
            "elements": elements,
        }

    def _extract_message_context(self, data: P2ImMessageReceiveV1) -> MessageContext | None:
        event = getattr(data, "event", None)
        if event is None or event.message is None:
            return None
        message = event.message
        if message.message_type != "text":
            return None
        sender = event.sender.sender_id if event.sender else None
        content = message.content or "{}"
        try:
            text = json.loads(content).get("text", "")
        except json.JSONDecodeError:
            text = content
        return MessageContext(
            chat_id=message.chat_id or "",
            chat_type=message.chat_type or "",
            user_id=getattr(sender, "open_id", "") if sender else "",
            text=text,
            message_id=message.message_id or "",
            thread_id=message.thread_id or "",
        )

    def _next_discussion_field(self, requirement) -> str | None:
        for field in requirement.pending_fields:
            if field != requirement.current_discussion_field:
                return field
        return None

    def _question_for_field(self, field: str) -> str:
        prompts = {
            "问题描述": "请说明这个需求当前要解决的核心问题，以及不解决会造成什么影响。",
            "使用场景": "请补充谁会在什么情况下使用它，以及期望完成什么结果。",
            "输入": "请说明这个需求依赖哪些输入，来源、格式和约束分别是什么。",
            "输出": "请说明最终输出是什么，输出方式、格式和接收方分别是什么。",
            "边界": "请明确这次需求不包含什么，哪些事项仍然留在边界之外。",
            "验收标准": "请给出可以验证的验收标准，尽量使用阈值、布尔条件或明确结果。",
            "非功能要求": "请补充性能、稳定性、权限、安全或可观测性等非功能要求。",
        }
        return prompts.get(field, "请继续补充当前需求。")

    def _sync_requirement_outputs(self, requirement) -> None:
        if requirement.document_id:
            try:
                self.gateway.sync_requirement_document(requirement)
            except Exception as exc:
                LOGGER.warning("Failed to sync requirement document for %s: %s", requirement.req_id, exc)

        if requirement.bitable_record_id:
            try:
                self.gateway.update_requirement_record(requirement)
            except Exception as exc:
                LOGGER.warning("Failed to update bitable record for %s: %s", requirement.req_id, exc)

    def _save_state(self) -> None:
        self.store.save_snapshot(
            self.service.requirements,
            self.service.active_req_by_user,
            self.service.project_groups,
        )

    def _is_feishu_chat_id(self, value: str) -> bool:
        return value.startswith("oc_")

    def _is_creation_group_message(self, context: MessageContext) -> bool:
        if context.chat_type == "p2p":
            return False
        if self._observed_creation_group_chat_id:
            return context.chat_id == self._observed_creation_group_chat_id
        return "创建需求" in context.text

    def _require_lark(self) -> None:
        if lark is None:
            raise RuntimeError("lark_oapi is not installed. Install service dependencies first.")


def create_runtime_app() -> CoordinatorRuntimeApp:
    return CoordinatorRuntimeApp(load_settings())
