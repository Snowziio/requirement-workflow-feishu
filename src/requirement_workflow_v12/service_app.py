from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from .config import Settings, load_settings
from .coordinator_service import CoordinatorService
from .feishu_gateway import FeishuGateway
from .protocols import AuthorStartBinding, CreationRequest
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

        class HealthHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                body = json.dumps({"status": "ok", "service": service_name}).encode()
                self.send_response(200)
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
        for message in self.handle_text_message(context):
            self.gateway.send_text(message.receive_id, message.text, receive_id_type=message.receive_id_type)

    def handle_text_message(self, context: MessageContext) -> list[OutboundMessage]:
        text = context.text.strip()
        if not text:
            return []

        if self._is_creation_group_message(context):
            return self._handle_creation_group_message(context)

        if context.chat_type == "p2p":
            return self._handle_author_private_message(context)

        return []

    def _handle_creation_group_message(self, context: MessageContext) -> list[OutboundMessage]:
        if "创建需求" not in context.text:
            return []
        self._observed_creation_group_chat_id = context.chat_id
        fields = self._parse_creation_command(context.text)
        if fields is None:
            return [
                OutboundMessage(
                    receive_id=context.chat_id,
                    text=(
                        "创建需求消息格式不完整，请按下面格式发送：\n"
                        "创建需求\n"
                        "项目：HARNESS\n"
                        "名称：多轮需求构造工作流\n"
                        "简述：把一次性讨论升级成多轮需求构造与 review 闭环"
                    ),
                )
            ]

        response = self.service.create_requirement_from_group(
            CreationRequest(
                project=fields["project"],
                name=fields["name"],
                summary=fields["summary"],
                creator=context.sender_name or context.user_id,
                creator_user_id=context.user_id,
                creation_chat_id=context.chat_id,
            )
        )
        requirement = self.service.get_requirement(response.req_id)
        if requirement is not None:
            if not self._is_feishu_chat_id(requirement.project_group_id):
                try:
                    project_group = self.gateway.create_project_group(
                        project=requirement.project,
                        owner_user_id=context.user_id,
                        member_user_ids=[context.user_id],
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
        messages = [OutboundMessage(receive_id=context.chat_id, text=creation_text)]
        if self._is_feishu_chat_id(response.project_group_id):
            project_text = response.message_to_project_group
            if requirement and requirement.document_url:
                project_text += f"\n需求文档：{requirement.document_url}"
            messages.append(OutboundMessage(receive_id=response.project_group_id, text=project_text))
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

        response = self.service.confirm_author_private_binding(context.user_id, text)
        if response.accepted:
            self._save_state()
            return [OutboundMessage(receive_id=context.chat_id, text=response.message)]

        active_req_id = self.service.active_req_by_user.get(context.user_id)
        if active_req_id:
            return [
                OutboundMessage(
                    receive_id=context.chat_id,
                    text=(
                        f"已收到你对 {active_req_id} 的补充。\n"
                        "当前长连接入口和私聊绑定已打通；下一步会继续接 author/reviewer 的结构化多轮写作闭环。"
                    ),
                )
            ]

        return [OutboundMessage(receive_id=context.chat_id, text=response.message)]

    def _parse_creation_command(self, text: str) -> dict[str, str] | None:
        fields: dict[str, str] = {}
        aliases = {"项目": "project", "名称": "name", "简述": "summary", "背景": "summary"}
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if "：" not in line:
                continue
            key, value = line.split("：", 1)
            normalized = aliases.get(key.strip())
            if normalized and value.strip():
                fields[normalized] = value.strip()

        required = {"project", "name", "summary"}
        if not required.issubset(fields):
            return None
        return fields

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
