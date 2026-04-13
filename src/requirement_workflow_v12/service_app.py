from __future__ import annotations

import hmac
import hashlib
import json
import logging
import re
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from .config import Settings, load_settings
from .coordinator_service import AuthorTurnResult, CoordinatorService
from .feishu_gateway import FeishuGateway
from .models import DISCUSSION_FIELDS, Requirement, ReviewFinding, ReviewResult, WorkflowStatus
from .protocols import (
    AgentAuthorEventPayload,
    AgentRequirementContextQuery,
    AgentReviewEventPayload,
    AuthorStartBinding,
    CreationFormPayload,
    CreationRequest,
)
from .store import JsonStateStore

try:
    import lark_oapi as lark
    from lark_oapi.event.callback.model.p2_card_action_trigger import (
        P2CardActionTrigger,
        P2CardActionTriggerResponse,
    )
    from lark_oapi.api.im.v1.model.p2_im_message_receive_v1 import P2ImMessageReceiveV1
except ImportError:  # pragma: no cover - optional during local editing before deps are installed
    lark = None
    P2ImMessageReceiveV1 = Any
    P2CardActionTrigger = Any
    P2CardActionTriggerResponse = Any


LOGGER = logging.getLogger(__name__)

AUTHOR_CALLBACK_EVENT_ALIASES = {
    "author_ready_for_ai_review": "author_submit",
}

REVIEW_CALLBACK_EVENT_ALIASES = {
    "review_returned_for_revision": "ai_review_reject",
    "review_ready_for_human_confirmation": "ai_review_pass",
}


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
        gateway: FeishuGateway | None = None,
    ) -> None:
        self.settings = settings
        self.settings.validate_runtime()
        self.store = store or JsonStateStore(settings.state_store_path)
        self.service = service or CoordinatorService()
        self.gateway = gateway or FeishuGateway(settings)
        requirements, active_req_by_user, project_groups = self.store.load_snapshot()
        if service is None or requirements or active_req_by_user or project_groups:
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
        return (
            builder
            .register_p2_im_message_receive_v1(self._on_message_receive)
            .register_p2_card_action_trigger(self._on_card_action_trigger)
            .build()
        )

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
                headers = {key: value for key, value in self.headers.items()}
                if self.path == "/callbacks/card":
                    status, payload = app.handle_card_callback(raw_body)
                elif self.path == "/callbacks/openclaw/author-turn":
                    status, payload = app.handle_openclaw_author_turn_callback(raw_body, headers=headers)
                elif self.path == "/callbacks/openclaw/review-result":
                    status, payload = app.handle_openclaw_review_result_callback(raw_body, headers=headers)
                elif self.path == "/queries/openclaw/requirement-context":
                    status, payload = app.handle_openclaw_requirement_context_query(raw_body, headers=headers)
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

    def _on_card_action_trigger(self, data: P2CardActionTrigger):
        payload = self._card_event_to_payload(data)
        status, response_payload = self._handle_card_action_payload(payload)
        if status != 200:
            LOGGER.warning("Card action handled with status=%s payload=%s", status, payload)
        return P2CardActionTriggerResponse(response_payload)

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
    ) -> tuple[list[OutboundMessage | OutboundCard], Requirement | None]:
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

            if requirement and requirement.bitable_record_id:
                try:
                    self.gateway.update_requirement_record(requirement)
                except Exception as exc:
                    LOGGER.warning("Failed to refresh bitable record for %s: %s", requirement.req_id, exc)

        self._save_state()
        if requirement is not None:
            LOGGER.info(
                "Created requirement from form req_id=%s status=%s project_group_id=%s bitable_record_id=%s document_url=%s",
                requirement.req_id,
                requirement.status.value,
                requirement.project_group_id,
                requirement.bitable_record_id,
                requirement.document_url,
            )
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
        return messages, requirement

    def _handle_author_private_message(self, context: MessageContext) -> list[OutboundMessage]:
        text = context.text.strip()
        LOGGER.info("Handling p2p command user_id=%s chat_id=%s text=%s", context.user_id, context.chat_id, text)
        req_id = self._extract_author_start_req_id(text)
        if req_id is not None:
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

        if text in {"确认通过", "通过审查"}:
            return self._handle_formal_review_decision(context, approved=True)

        if text in {"需要修改", "审查退回"}:
            return self._handle_formal_review_decision(context, approved=False)

        if text == "查看状态":
            return self._handle_status_query(context)

        response = self.service.confirm_author_private_binding(context.user_id, text)
        if response.accepted:
            self._save_state()
            return [OutboundMessage(receive_id=context.chat_id, text=response.message)]

        active_req_id = self.service.active_req_by_user.get(context.user_id)
        if active_req_id:
            requirement = self.service.get_requirement(active_req_id)
            if requirement is not None and requirement.active_private_binding_confirmed:
                if requirement.status == WorkflowStatus.DRAFTING:
                    return self._handle_author_turn(context, requirement)
                if requirement.status == WorkflowStatus.HUMAN_CONFIRM:
                    return [
                        OutboundMessage(
                            receive_id=context.chat_id,
                            text="当前处于人工确认阶段，请回复“确认需求”或“继续修改”。",
                        )
                    ]
                if requirement.status == WorkflowStatus.APPROVED:
                    return [
                        OutboundMessage(
                            receive_id=context.chat_id,
                            text=f"{requirement.req_id} 已完成当前阶段，如需新需求请回创建群重新发起。",
                        )
                    ]

        return [OutboundMessage(receive_id=context.chat_id, text=response.message)]

    def _extract_author_start_req_id(self, text: str) -> str | None:
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if line.startswith("开始需求构造 "):
                req_id = line.replace("开始需求构造 ", "", 1).strip()
                if req_id:
                    return req_id
        return None

    def _handle_author_turn(self, context: MessageContext, requirement: Requirement) -> list[OutboundMessage]:
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

        review = self._build_rule_based_review(requirement, current_field=current_field)
        requirement = self.service.handle_review_result(requirement, review)
        self._sync_requirement_outputs(requirement)
        self._save_state()
        if requirement.status == WorkflowStatus.HUMAN_CONFIRM:
            self._dispatch_transition_notifications(requirement, trigger="ai_review_pass")
        else:
            self._dispatch_transition_notifications(requirement, trigger="ai_review_reject")

        if requirement.status == WorkflowStatus.HUMAN_CONFIRM:
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

    def _handle_status_query(self, context: MessageContext) -> list[OutboundMessage]:
        active_req_id = self.service.active_req_by_user.get(context.user_id)
        if not active_req_id:
            return [OutboundMessage(receive_id=context.chat_id, text="当前没有激活的需求，请先发送“开始需求构造 REQ-ID”。")]

        requirement = self.service.get_requirement(active_req_id)
        if requirement is None:
            return [OutboundMessage(receive_id=context.chat_id, text=f"未知需求：{active_req_id}")]

        completed = "、".join(requirement.completed_fields) or "无"
        pending = "、".join(requirement.pending_fields) or "无"
        latest_ai_review = requirement.review_history[-1].summary if requirement.review_history else "暂无"
        latest_human_review = requirement.human_review_history[-1].summary if requirement.human_review_history else "暂无"
        text = (
            f"{requirement.req_id} 当前状态\n"
            f"状态：{requirement.status.value}\n"
            f"阶段：{requirement.current_phase}\n"
            f"轮次：{requirement.current_round}\n"
            f"当前字段：{requirement.current_discussion_field}\n"
            f"已完成：{completed}\n"
            f"待补：{pending}\n"
            f"AI Review：{latest_ai_review}\n"
            f"人工 Review：{latest_human_review}\n"
            f"下一步：{requirement.latest_question}\n"
            f"需求文档：{requirement.document_url or '待同步'}"
        )
        return [OutboundMessage(receive_id=context.chat_id, text=text)]

    def _handle_human_confirmation(self, context: MessageContext, approved: bool) -> list[OutboundMessage]:
        active_req_id = self.service.active_req_by_user.get(context.user_id)
        if not active_req_id:
            return [OutboundMessage(receive_id=context.chat_id, text="当前没有激活的需求，请先发送“开始需求构造 REQ-ID”。")]

        requirement = self.service.get_requirement(active_req_id)
        if requirement is None:
            return [OutboundMessage(receive_id=context.chat_id, text=f"未知需求：{active_req_id}")]
        if requirement.status != WorkflowStatus.HUMAN_CONFIRM:
            return [OutboundMessage(receive_id=context.chat_id, text="当前还没到人工确认阶段，请先继续完成需求构造。")]

        requirement = self.service.handle_human_confirmation(requirement, approved=approved)

        self._sync_requirement_outputs(requirement)
        self._save_state()
        self._dispatch_transition_notifications(requirement, trigger="human_confirmed" if approved else "human_rejected")

        if approved:
            response_text = (
                f"{requirement.req_id} 已完成人工确认并进入正式审查。\n\n"
                f"当前状态：{requirement.status.value}\n"
                f"下一步：请回复“确认通过”或“需要修改”。\n"
                f"需求文档：{requirement.document_url or '待同步'}"
            )
        else:
            response_text = (
                f"{requirement.req_id} 已退回继续打磨。\n\n"
                f"下一步：{requirement.latest_question}"
            )
        return [OutboundMessage(receive_id=context.chat_id, text=response_text)]

    def _handle_formal_review_decision(self, context: MessageContext, approved: bool) -> list[OutboundMessage]:
        active_req_id = self.service.active_req_by_user.get(context.user_id)
        if not active_req_id:
            return [OutboundMessage(receive_id=context.chat_id, text="当前没有激活的需求，请先发送“开始需求构造 REQ-ID”。")]

        requirement = self.service.get_requirement(active_req_id)
        if requirement is None:
            return [OutboundMessage(receive_id=context.chat_id, text=f"未知需求：{active_req_id}")]
        if requirement.status != WorkflowStatus.FINAL_REVIEW:
            return [OutboundMessage(receive_id=context.chat_id, text="当前还没进入正式审查阶段。")]

        if approved:
            requirement = self.service.approve_requirement(requirement)
            response_text = (
                f"{requirement.req_id} 已完成正式审查并批准通过。\n\n"
                f"当前状态：{requirement.status.value}\n"
                f"需求文档：{requirement.document_url or '待同步'}"
            )
        else:
            requirement = self.service.request_changes_after_review(requirement)
            response_text = (
                f"{requirement.req_id} 已被正式审查退回。\n\n"
                f"下一步：{requirement.latest_question}"
            )

        self._sync_requirement_outputs(requirement)
        self._save_state()
        self._dispatch_transition_notifications(requirement, trigger="final_review_passed" if approved else "final_review_rejected")
        return [OutboundMessage(receive_id=context.chat_id, text=response_text)]

    def handle_card_callback(self, raw_body: bytes) -> tuple[int, dict[str, object]]:
        try:
            payload = json.loads(raw_body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return 400, {"error": "invalid_json"}

        return self._handle_card_action_payload(payload)

    def handle_openclaw_author_turn_callback(
        self,
        raw_body: bytes,
        *,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, object]]:
        auth_error = self._validate_openclaw_callback_auth(raw_body, headers=headers)
        if auth_error is not None:
            return auth_error
        try:
            payload = json.loads(raw_body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return 400, {"error": "invalid_json"}

        req_id = str(payload.get("req_id", "")).strip()
        event = str(payload.get("event", "")).strip()
        normalized_event = AUTHOR_CALLBACK_EVENT_ALIASES.get(event, event)
        summary = str(payload.get("summary", "")).strip()
        document_url = str(payload.get("document_url", "")).strip()
        document_version = str(payload.get("document_version", "")).strip()
        iteration_round = payload.get("iteration_round")

        if not req_id or not event or not summary:
            return 400, {"error": "invalid_payload", "message": "req_id、event、summary 为必填字段。"}
        if normalized_event != "author_submit":
            return 400, {"error": "invalid_payload", "message": f"不支持的 author 事件：{event}。"}
        if iteration_round is not None and not isinstance(iteration_round, int):
            return 400, {"error": "invalid_payload", "message": "iteration_round 必须是整数。"}

        LOGGER.info(
            "Received author callback req_id=%s event=%s iteration_round=%s document_url=%s",
            req_id,
            normalized_event,
            iteration_round,
            document_url,
        )

        try:
            requirement = self.service.submit_author_event_payload(
                AgentAuthorEventPayload(
                    req_id=req_id,
                    event=normalized_event,
                    summary=summary,
                    document_url=document_url,
                    document_version=document_version,
                    iteration_round=iteration_round,
                )
            )
            self._sync_requirement_outputs(requirement)
            self._save_state()
            self._dispatch_transition_notifications(requirement, trigger="author_submit")
        except ValueError as exc:
            return 404, {"error": "not_found", "message": str(exc)}
        except Exception as exc:
            LOGGER.exception("Failed handling OpenClaw author turn callback for %s", req_id)
            return 500, {"error": "author_turn_failed", "message": str(exc)}

        LOGGER.info(
            "Author callback applied req_id=%s status=%s phase=%s owner=%s",
            requirement.req_id,
            requirement.status.value,
            requirement.current_phase,
            requirement.current_owner,
        )

        return 200, {
            "ok": True,
            "req_id": requirement.req_id,
            "status": requirement.status.value,
            "current_phase": requirement.current_phase,
            "current_round": requirement.current_round,
            "current_owner": requirement.current_owner,
            "latest_review_summary": requirement.latest_review_summary,
        }

    def handle_openclaw_review_result_callback(
        self,
        raw_body: bytes,
        *,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, object]]:
        auth_error = self._validate_openclaw_callback_auth(raw_body, headers=headers)
        if auth_error is not None:
            return auth_error
        try:
            payload = json.loads(raw_body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return 400, {"error": "invalid_json"}

        req_id = str(payload.get("req_id", "")).strip()
        event = str(payload.get("event", "")).strip()
        normalized_event = REVIEW_CALLBACK_EVENT_ALIASES.get(event, event)
        review_summary = str(payload.get("review_summary", "")).strip()
        review_notes_url = str(payload.get("review_notes_url", "")).strip()
        document_url = str(payload.get("document_url", "")).strip()
        review_result = str(payload.get("review_result", "")).strip()

        if not req_id or not event or not review_summary:
            return 400, {"error": "invalid_payload", "message": "req_id、event、review_summary 为必填字段。"}
        supported_events = {
            "ai_review_reject",
            "ai_review_pass",
        }
        if normalized_event not in supported_events:
            return 400, {
                "error": "invalid_payload",
                "message": (
                    "review callback 只允许 reviewer 上报 AI review 结论："
                    "`ai_review_reject` 或 `ai_review_pass`。"
                    "人工确认与正式审查请通过 Coordinator 的人工操作入口推进。"
                ),
            }

        LOGGER.info(
            "Received review callback req_id=%s event=%s document_url=%s review_notes_url=%s",
            req_id,
            normalized_event,
            document_url,
            review_notes_url,
        )

        try:
            requirement = self.service.submit_review_event_payload(
                AgentReviewEventPayload(
                    req_id=req_id,
                    event=normalized_event,
                    review_summary=review_summary,
                    review_notes_url=review_notes_url,
                    document_url=document_url,
                    review_result=review_result,
                )
            )
            self._sync_requirement_outputs(requirement)
            self._save_state()
            self._dispatch_transition_notifications(requirement, trigger=normalized_event)
        except PermissionError as exc:
            return 400, {"error": "invalid_payload", "message": str(exc)}
        except ValueError as exc:
            return 404, {"error": "not_found", "message": str(exc)}
        except Exception as exc:
            LOGGER.exception("Failed handling OpenClaw review result callback for %s", req_id)
            return 500, {"error": "review_result_failed", "message": str(exc)}

        LOGGER.info(
            "Review callback applied req_id=%s status=%s phase=%s owner=%s ai_ready=%s human_confirmed=%s",
            requirement.req_id,
            requirement.status.value,
            requirement.current_phase,
            requirement.current_owner,
            requirement.ai_ready,
            requirement.human_confirmed,
        )

        return 200, {
            "ok": True,
            "req_id": requirement.req_id,
            "status": requirement.status.value,
            "current_phase": requirement.current_phase,
            "ai_ready": requirement.ai_ready,
            "latest_review_summary": requirement.latest_review_summary,
            "current_owner": requirement.current_owner,
        }

    def handle_openclaw_requirement_context_query(
        self,
        raw_body: bytes,
        *,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, object]]:
        auth_error = self._validate_openclaw_callback_auth(raw_body, headers=headers)
        if auth_error is not None:
            return auth_error
        try:
            payload = json.loads(raw_body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return 400, {"error": "invalid_json"}

        req_id = str(payload.get("req_id", "")).strip()
        if not req_id:
            return 400, {"error": "invalid_payload", "message": "req_id 为必填字段。"}

        LOGGER.info("Received requirement context query req_id=%s", req_id)

        try:
            context_payload = self.service.get_agent_requirement_context(AgentRequirementContextQuery(req_id=req_id))
        except ValueError as exc:
            return 404, {"error": "not_found", "message": str(exc)}
        except Exception as exc:
            LOGGER.exception("Failed handling OpenClaw requirement context query for %s", req_id)
            return 500, {"error": "context_query_failed", "message": str(exc)}

        bitable_url = self.gateway.bitable_url()
        if bitable_url:
            context_payload["bitable_url"] = bitable_url

        LOGGER.info(
            "Requirement context query served req_id=%s status=%s phase=%s owner=%s",
            context_payload["req_id"],
            context_payload["status"],
            context_payload["current_phase"],
            context_payload["current_owner"],
        )

        return 200, {
            "ok": True,
            "context": context_payload,
        }

    def _handle_card_action_payload(self, payload: dict[str, object]) -> tuple[int, dict[str, object]]:
        LOGGER.info("Handling card payload: %s", payload)

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
            messages, created_requirement = self._create_requirement_from_form(form_payload)
            for outbound in messages:
                if isinstance(outbound, OutboundCard):
                    self.gateway.send_card(outbound.receive_id, outbound.card, receive_id_type=outbound.receive_id_type)
                else:
                    self.gateway.send_text(outbound.receive_id, outbound.text, receive_id_type=outbound.receive_id_type)
            response_payload: dict[str, object] = {
                "toast": {"type": "success", "content": "需求已创建，项目群同步已开始。"}
            }
            if created_requirement is not None:
                response_payload["card"] = {
                    "type": "raw",
                    "data": self._build_requirement_created_result_card(created_requirement),
                }
            return 200, response_payload

        if action_name == "send_author_start":
            req_id = value.get("req_id", "")
            if not req_id:
                return 200, {"toast": {"type": "error", "content": "缺少需求ID。"}}
            requirement = self.service.get_requirement(req_id)
            if requirement is None:
                return 200, {"toast": {"type": "error", "content": f"未知需求：{req_id}。"}}
            requirement = self.service.handoff_to_author(requirement)
            self._sync_requirement_outputs(requirement)
            self._save_state()
            agent_name = self.settings.openclaw_author_agent_name
            target_user_id, receive_id_type = self._resolve_operator_receive_target(operator)
            if not target_user_id:
                return 200, {
                    "toast": {
                        "type": "error",
                        "content": "无法识别当前点击人的飞书身份，请改用手动私聊启动。",
                    }
                }
            try:
                self.gateway.send_text(
                    target_user_id,
                    self._build_author_handoff_text(requirement, agent_name=agent_name),
                    receive_id_type=receive_id_type,
                )
            except Exception as exc:
                LOGGER.warning(
                    "Failed to send author handoff text req_id=%s target_user_id=%s receive_id_type=%s: %s",
                    req_id,
                    target_user_id,
                    receive_id_type,
                    exc,
                )
                return 200, {
                    "toast": {
                        "type": "error",
                        "content": "私发启动指令失败，请改为手动私聊需求构造助手并发送完整启动消息。",
                    }
                }
            return 200, {"toast": {"type": "success", "content": "已将启动指令私发给你。"}}

        if action_name in {"human_confirm_yes", "human_confirm_no"}:
            req_id = value.get("req_id", "")
            if not req_id:
                return 200, {"toast": {"type": "error", "content": "缺少需求ID。"}}
            requirement = self.service.get_requirement(req_id)
            if requirement is None:
                return 200, {"toast": {"type": "error", "content": f"未知需求：{req_id}。"}}
            if requirement.creator_user_id and requirement.creator_user_id != user_id:
                return 200, {"toast": {"type": "error", "content": "只有需求提出者可以执行人工确认。"}}
            if requirement.status != WorkflowStatus.HUMAN_CONFIRM:
                return 200, {"toast": {"type": "error", "content": "当前需求不处于人工确认阶段。"}}

            approved = action_name == "human_confirm_yes"
            requirement = self.service.handle_human_confirmation(requirement, approved=approved)
            self._sync_requirement_outputs(requirement)
            self._save_state()
            self._dispatch_transition_notifications(
                requirement,
                trigger="human_confirmed" if approved else "human_rejected",
            )
            return 200, {
                "toast": {
                    "type": "success",
                    "content": "人工确认已更新。"
                    if approved
                    else "已退回需求构造，可继续修改。",
                }
            }

        if action_name in {"final_review_pass", "final_review_reject"}:
            req_id = value.get("req_id", "")
            if not req_id:
                return 200, {"toast": {"type": "error", "content": "缺少需求ID。"}}
            requirement = self.service.get_requirement(req_id)
            if requirement is None:
                return 200, {"toast": {"type": "error", "content": f"未知需求：{req_id}。"}}
            if requirement.creator_user_id and requirement.creator_user_id != user_id:
                return 200, {"toast": {"type": "error", "content": "当前版本仅允许需求提出者执行正式审查操作。"}}
            if requirement.status != WorkflowStatus.FINAL_REVIEW:
                return 200, {"toast": {"type": "error", "content": "当前需求不处于正式审查阶段。"}}

            approved = action_name == "final_review_pass"
            if approved:
                requirement = self.service.approve_requirement(requirement)
            else:
                requirement = self.service.request_changes_after_review(requirement)
            self._sync_requirement_outputs(requirement)
            self._save_state()
            self._dispatch_transition_notifications(
                requirement,
                trigger="final_review_passed" if approved else "final_review_rejected",
            )
            return 200, {
                "toast": {
                    "type": "success",
                    "content": "正式审查结论已更新。"
                    if approved
                    else "正式审查已退回，需求已回到构造阶段。",
                }
            }

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

    def _resolve_operator_receive_target(self, operator: dict[str, object]) -> tuple[str, str]:
        configured_type = self.settings.feishu_user_id_type
        configured_value = self._normalize_form_value(operator.get(configured_type))
        if configured_value:
            return configured_value, configured_type

        open_id = self._normalize_form_value(operator.get("open_id"))
        if open_id:
            return open_id, "open_id"

        user_id = self._normalize_form_value(operator.get("user_id"))
        if user_id:
            return user_id, "user_id"

        return "", configured_type

    def _card_event_to_payload(self, data: P2CardActionTrigger) -> dict[str, object]:
        event = getattr(data, "event", None)
        operator = getattr(event, "operator", None)
        action = getattr(event, "action", None)
        context = getattr(event, "context", None)
        return {
            "operator": {
                "open_id": getattr(operator, "open_id", "") if operator else "",
                "user_id": getattr(operator, "user_id", "") if operator else "",
            },
            "action": {
                "value": getattr(action, "value", None) if action else None,
                "name": getattr(action, "name", None) if action else None,
                "tag": getattr(action, "tag", None) if action else None,
                "option": getattr(action, "option", None) if action else None,
                "input_value": getattr(action, "input_value", None) if action else None,
                "options": getattr(action, "options", None) if action else None,
                "checked": getattr(action, "checked", None) if action else None,
                "form_value": getattr(action, "form_value", None) if action else None,
            },
            "context": {
                "open_message_id": getattr(context, "open_message_id", "") if context else "",
                "open_chat_id": getattr(context, "open_chat_id", "") if context else "",
            },
        }

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

    def _review_result_from_payload(self, payload: dict[str, object]) -> ReviewResult:
        findings_payload = payload.get("findings", [])
        findings: list[ReviewFinding] = []
        if isinstance(findings_payload, list):
            for item in findings_payload:
                if not isinstance(item, dict):
                    continue
                severity = str(item.get("severity", "")).strip() or "medium"
                if severity not in {"high", "medium", "low"}:
                    severity = "medium"
                findings.append(
                    ReviewFinding(
                        dimension=str(item.get("dimension", "")).strip(),
                        summary=str(item.get("summary", "")).strip(),
                        severity=severity,
                    )
                )
        return ReviewResult(
            ready_for_human_confirmation=bool(payload.get("ready_for_human_confirmation", False)),
            summary=str(payload.get("summary", "")).strip(),
            findings=findings,
            weak_fields=[
                str(item).strip() for item in payload.get("weak_fields", []) if str(item).strip()
            ] if isinstance(payload.get("weak_fields", []), list) else [],
            conflicts=[
                str(item).strip() for item in payload.get("conflicts", []) if str(item).strip()
            ] if isinstance(payload.get("conflicts", []), list) else [],
            non_testable_acceptance_criteria=[
                str(item).strip()
                for item in payload.get("non_testable_acceptance_criteria", [])
                if str(item).strip()
            ] if isinstance(payload.get("non_testable_acceptance_criteria", []), list) else [],
            next_focus=str(payload.get("next_focus", "")).strip() or None,
        )

    def _validate_openclaw_callback_auth(
        self,
        raw_body: bytes,
        *,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, object]] | None:
        secret = self.settings.openclaw_callback_secret.strip()
        if not secret:
            return None

        normalized_headers = {key.lower(): value for key, value in (headers or {}).items()}
        timestamp = normalized_headers.get("x-openclaw-timestamp", "").strip()
        signature = normalized_headers.get("x-openclaw-signature", "").strip().lower()
        if not timestamp or not signature:
            return 401, {"error": "unauthorized", "message": "缺少 OpenClaw 回调签名头。"}
        if not timestamp.isdigit():
            return 401, {"error": "unauthorized", "message": "OpenClaw 回调时间戳非法。"}

        timestamp_value = int(timestamp)
        now = int(time.time())
        if abs(now - timestamp_value) > self.settings.openclaw_callback_ttl_seconds:
            return 401, {"error": "unauthorized", "message": "OpenClaw 回调签名已过期。"}

        expected = hmac.new(
            secret.encode("utf-8"),
            timestamp.encode("utf-8") + b"." + raw_body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            return 401, {"error": "unauthorized", "message": "OpenClaw 回调签名不匹配。"}
        return None

    def _build_requirement_creation_card(self, context: MessageContext) -> dict[str, object]:
        return {
            "schema": "2.0",
            "config": {"wide_screen_mode": True},
            "header": {
                "template": "blue",
                "title": {"tag": "plain_text", "content": "新建需求"},
            },
            "body": {
                "elements": [
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": (
                                "**提交后将自动完成以下动作：**\n"
                                "- 生成 `REQ ID`\n"
                                "- 创建需求文档\n"
                                "- 写入多维表格\n"
                                "- 向项目需求群发送接手卡片"
                            ),
                        },
                    },
                    {"tag": "hr"},
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": (
                                "**请先填写最小信息集**\n"
                                "必填：项目代号、需求名称、需求简述\n"
                                "选填：背景链接、优先级、期望完成时间"
                            ),
                        },
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
                                "tag": "column_set",
                                "horizontal_spacing": "12px",
                                "columns": [
                                    {
                                        "tag": "column",
                                        "width": "weighted",
                                        "weight": 1,
                                        "elements": [
                                            {
                                                "tag": "select_static",
                                                "name": "priority",
                                                "placeholder": {"tag": "plain_text", "content": "优先级，可选"},
                                                "options": [
                                                    {"text": {"tag": "plain_text", "content": "P0"}, "value": "P0"},
                                                    {"text": {"tag": "plain_text", "content": "P1"}, "value": "P1"},
                                                    {"text": {"tag": "plain_text", "content": "P2"}, "value": "P2"},
                                                ],
                                            }
                                        ],
                                    },
                                    {
                                        "tag": "column",
                                        "width": "weighted",
                                        "weight": 1,
                                        "elements": [
                                            {
                                                "tag": "date_picker",
                                                "name": "expected_due_date",
                                                "placeholder": {"tag": "plain_text", "content": "期望完成时间，可选"},
                                            }
                                        ],
                                    },
                                ],
                            },
                            {
                                "tag": "button",
                                "name": "submit_create_requirement",
                                "text": {"tag": "plain_text", "content": "创建需求"},
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

    def _build_requirement_created_result_card(self, requirement: Requirement) -> dict[str, object]:
        bitable_url = self.gateway.bitable_url()
        actions: list[dict[str, object]] = []
        if requirement.document_url:
            actions.append(
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "查看需求文档"},
                    "type": "default",
                    "multi_url": {"url": requirement.document_url},
                }
            )
        if bitable_url:
            actions.append(
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "查看多维表格"},
                    "type": "default",
                    "multi_url": {"url": bitable_url},
                }
            )

        return {
            "schema": "2.0",
            "config": {"wide_screen_mode": True},
            "header": {
                "template": "green",
                "title": {"tag": "plain_text", "content": f"{requirement.req_id} 已创建"},
            },
            "body": {
                "elements": [
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": (
                                f"**创建完成**\n"
                                f"- 需求名称：{requirement.name}\n"
                                f"- 当前状态：{requirement.status.value}\n"
                                f"- 当前接手：{requirement.current_role_label}"
                            ),
                        },
                    },
                    {
                        "tag": "note",
                        "elements": [
                            {
                                "tag": "plain_text",
                                "content": "项目群和需求构造接手卡片已同步发送；接下来请在项目群里继续推进需求构造。",
                            }
                        ],
                    },
                    {"tag": "action", "actions": actions} if actions else {"tag": "hr"},
                ],
            },
        }

    def _build_project_group_card(self, requirement) -> dict[str, object]:
        bitable_url = self.gateway.bitable_url()
        top_actions: list[dict[str, object]] = []
        if requirement.document_url:
            top_actions.append(
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "查看需求文档"},
                    "type": "default",
                    "multi_url": {"url": requirement.document_url},
                }
            )
        if bitable_url:
            top_actions.append(
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "查看多维表格"},
                    "type": "default",
                    "multi_url": {"url": bitable_url},
                }
            )

        primary_actions: list[dict[str, object]] = [
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "私发启动消息"},
                "type": "primary_filled",
                "behaviors": [
                    {
                        "type": "callback",
                        "value": {"action": "send_author_start", "req_id": requirement.req_id},
                    }
                ],
            }
        ]
        if self.settings.author_agent_chat_url_template:
            primary_actions.insert(
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

        body_elements: list[dict[str, object]] = [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        f"**需求已创建成功**\n"
                        f"当前已进入 **{requirement.status.value}**，由 **{requirement.current_role_label}** 接手。"
                    ),
                },
            },
            {
                "tag": "column_set",
                "horizontal_spacing": "12px",
                "columns": [
                    {
                        "tag": "column",
                        "width": "weighted",
                        "weight": 1,
                        "elements": [
                            {
                                "tag": "markdown",
                                "content": (
                                    f"**REQ ID**\n`{requirement.req_id}`\n\n"
                                    f"**名称**\n{requirement.name}"
                                ),
                            }
                        ],
                    },
                    {
                        "tag": "column",
                        "width": "weighted",
                        "weight": 1,
                        "elements": [
                            {
                                "tag": "markdown",
                                "content": (
                                    f"**状态**\n{requirement.status.value}\n\n"
                                    f"**当前角色**\n{requirement.current_role_label}"
                                ),
                            }
                        ],
                    },
                ],
            },
        ]
        if top_actions:
            body_elements.append({"tag": "action", "actions": top_actions})
        body_elements.extend(
            [
                {"tag": "hr"},
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": (
                            "**推荐下一步**\n"
                            "1. 点击“私发启动消息”\n"
                            "2. 将收到的完整启动消息原样转发给需求构造助手\n"
                            "3. 在同一份需求文档里继续多轮构造，不要新建第二份文档"
                        ),
                    },
                },
                {"tag": "action", "actions": primary_actions},
                {
                    "tag": "note",
                    "elements": [
                        {
                            "tag": "plain_text",
                            "content": (
                                f"如果自动私发失败，请手动私聊 {self.settings.openclaw_author_agent_name}，"
                                "并发送完整启动消息。"
                            ),
                        }
                    ],
                },
            ]
        )

        return {
            "schema": "2.0",
            "config": {"wide_screen_mode": True},
            "header": {
                "template": "green",
                "title": {"tag": "plain_text", "content": f"{requirement.req_id} 已创建"},
            },
            "body": {"elements": body_elements},
        }

    def _build_author_handoff_text(self, requirement: Requirement, *, agent_name: str) -> str:
        bitable_url = self.gateway.bitable_url() or "待同步"
        document_url = requirement.document_url or "待同步"
        return (
            f"请私聊 {agent_name}，并发送以下完整上下文：\n\n"
            f"开始需求构造 {requirement.req_id}\n"
            f"需求名称：{requirement.name}\n"
            f"需求简述：{requirement.summary}\n"
            f"需求文档：{document_url}\n"
            f"多维表格：{bitable_url}\n\n"
            "要求：如果需求文档链接已存在，必须直接在该文档上继续撰写，不要重新创建第二份文档。"
        )

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

    def _build_rule_based_review(self, requirement: Requirement, *, current_field: str) -> ReviewResult:
        if requirement.document is None:
            return ReviewResult(
                ready_for_human_confirmation=False,
                summary="正式需求文档尚未初始化完成，请继续等待系统同步。",
                next_focus=requirement.latest_question,
            )

        findings: list[ReviewFinding] = []
        weak_fields: list[str] = []
        conflicts: list[str] = []
        non_testable_acceptance_criteria: list[str] = []
        sections = requirement.document.sections
        for field in DISCUSSION_FIELDS:
            content = (sections.get(field) or "").strip()
            if not content or content == "待补充":
                findings.append(ReviewFinding(dimension=field, summary="该字段仍未补充。", severity="high"))
                weak_fields.append(field)
                continue
            if len(content) < 12:
                findings.append(ReviewFinding(dimension=field, summary="内容过短，仍不足以支撑后续实现。", severity="medium"))
                weak_fields.append(field)
                continue
            if field == "验收标准" and not any(token in content for token in ("应", "必须", ">= ", "<=", "至少", "小于", "大于", "true", "false", "%", "秒", "分钟")):
                findings.append(ReviewFinding(dimension=field, summary="缺少可验证或可量化的验收口径。", severity="high"))
                weak_fields.append(field)
                non_testable_acceptance_criteria.append(content)
            if field == "边界" and not any(token in content for token in ("不包含", "不做", "不在本次", "排除", "暂不")):
                findings.append(ReviewFinding(dimension=field, summary="边界描述不够明确，未清楚说明本次不做什么。", severity="medium"))
                weak_fields.append(field)
            if field == "输入":
                output = (sections.get("输出") or "").strip()
                if output and content and output == content:
                    findings.append(ReviewFinding(dimension="一致性", summary="输入与输出内容完全相同，可能存在语义混淆。", severity="medium"))
                    conflicts.append("输入与输出内容重复，尚未体现处理前后差异。")

        ready = not weak_fields
        if ready:
            return ReviewResult(
                ready_for_human_confirmation=True,
                summary="AI review 认为当前需求已具备完整性、一致性与可验证性，可以进入人工确认。",
                conflicts=conflicts,
            )

        next_focus = self._question_for_field(weak_fields[0])
        if current_field in weak_fields:
            summary = f"当前已补充【{current_field}】，但该字段仍需继续打磨；请优先完善【{weak_fields[0]}】。"
        else:
            summary = f"当前已补充【{current_field}】，下一轮请优先完善【{weak_fields[0]}】。"
        return ReviewResult(
            ready_for_human_confirmation=False,
            summary=summary,
            findings=findings,
            weak_fields=weak_fields,
            conflicts=conflicts,
            non_testable_acceptance_criteria=non_testable_acceptance_criteria,
            next_focus=next_focus,
        )

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
        LOGGER.info(
            "Syncing requirement outputs req_id=%s status=%s phase=%s owner=%s bitable_record_id=%s document_url=%s",
            requirement.req_id,
            requirement.status.value,
            requirement.current_phase,
            requirement.current_owner,
            requirement.bitable_record_id,
            requirement.document_url,
        )
        if requirement.bitable_record_id:
            try:
                self.gateway.update_requirement_record(requirement)
            except Exception as exc:
                LOGGER.warning("Failed to update bitable record for %s: %s", requirement.req_id, exc)

    def _dispatch_transition_notifications(self, requirement: Requirement, *, trigger: str) -> None:
        card = self._build_transition_notification_card(requirement, trigger=trigger)
        text = self._build_transition_notification_text(requirement, trigger=trigger)
        if card is None and not text:
            return

        targets: list[tuple[str, str]] = []
        if self._is_feishu_chat_id(requirement.project_group_id):
            targets.append((requirement.project_group_id, "chat_id"))
        if requirement.creator_user_id:
            targets.append((requirement.creator_user_id, self.settings.feishu_user_id_type))

        for receive_id, receive_id_type in targets:
            try:
                if card is not None and hasattr(self.gateway, "send_card"):
                    self.gateway.send_card(receive_id, card, receive_id_type=receive_id_type)
                elif text and hasattr(self.gateway, "send_text"):
                    self.gateway.send_text(receive_id, text, receive_id_type=receive_id_type)
            except Exception as exc:
                LOGGER.warning(
                    "Failed to send transition notification req_id=%s trigger=%s receive_id=%s: %s",
                    requirement.req_id,
                    trigger,
                    receive_id,
                    exc,
                )

    def _build_transition_notification_card(self, requirement: Requirement, *, trigger: str) -> dict[str, object] | None:
        template, title, reason, result, next_action = self._transition_notification_content(requirement, trigger=trigger)
        if not title:
            return None

        elements: list[dict[str, object]] = [
            {
                "tag": "markdown",
                "content": (
                    f"**需求ID**：{requirement.req_id}\n"
                    f"**当前状态**：{requirement.status.value}\n"
                    f"**当前阶段**：{requirement.current_phase}\n"
                    f"**当前接手角色**：{requirement.current_role_label}"
                ),
            },
            {"tag": "hr"},
            {"tag": "markdown", "content": f"**流转原因**\n{reason}"},
            {"tag": "markdown", "content": f"**流转结果**\n{result}"},
            {"tag": "markdown", "content": f"**需要操作**\n{next_action}"},
        ]

        links: list[str] = []
        if requirement.document_url:
            links.append(f"[查看需求文档]({requirement.document_url})")
        bitable_url = self.gateway.bitable_url() if hasattr(self.gateway, "bitable_url") else ""
        if bitable_url:
            links.append(f"[查看多维表格]({bitable_url})")
        if links:
            elements.append({"tag": "markdown", "content": " | ".join(links)})

        actions = self._build_transition_notification_actions(requirement, trigger=trigger)
        if actions:
            elements.append({"tag": "action", "actions": actions})

        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": template,
                "title": {"tag": "plain_text", "content": title},
            },
            "elements": elements,
        }

    def _build_transition_notification_text(self, requirement: Requirement, *, trigger: str) -> str:
        _, title, reason, result, next_action = self._transition_notification_content(requirement, trigger=trigger)
        if not title:
            return ""
        return (
            f"{title}\n"
            f"需求ID：{requirement.req_id}\n"
            f"当前状态：{requirement.status.value}\n"
            f"流转原因：{reason}\n"
            f"流转结果：{result}\n"
            f"需要操作：{next_action}\n"
            f"需求文档：{requirement.document_url or '待同步'}"
        )

    def _build_transition_notification_actions(
        self,
        requirement: Requirement,
        *,
        trigger: str,
    ) -> list[dict[str, object]]:
        if trigger == "ai_review_pass":
            return [
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "确认需求"},
                    "type": "primary",
                    "value": {"action": "human_confirm_yes", "req_id": requirement.req_id},
                },
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "继续修改"},
                    "type": "default",
                    "value": {"action": "human_confirm_no", "req_id": requirement.req_id},
                },
            ]
        if trigger == "human_confirmed":
            return [
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "确认通过"},
                    "type": "primary",
                    "value": {"action": "final_review_pass", "req_id": requirement.req_id},
                },
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "需要修改"},
                    "type": "default",
                    "value": {"action": "final_review_reject", "req_id": requirement.req_id},
                },
            ]
        return []

    def _transition_notification_content(self, requirement: Requirement, *, trigger: str) -> tuple[str, str, str, str, str]:
        reviewer_name = self.settings.openclaw_reviewer_agent_name
        author_name = self.settings.openclaw_author_agent_name
        latest_review = requirement.latest_review_summary or "暂无"

        if trigger == "author_submit":
            return (
                "indigo",
                f"{requirement.req_id} 已进入 AI Review",
                "author 已确认当前轮需求文档达到可审查门槛。",
                "状态已切换到 AI Review，reviewer 可以开始正式审查当前文档。",
                f"请由 {reviewer_name} 接手审查；若审查不通过，请明确给出退回原因。",
            )
        if trigger == "ai_review_reject":
            return (
                "orange",
                f"{requirement.req_id} AI Review 未通过",
                latest_review,
                "reviewer 判定当前文档尚未达到 AI Review 标准，流程已退回需求构造阶段。",
                f"请由 {author_name} 根据审查意见继续修改文档后，再发起下一轮 AI Review。",
            )
        if trigger == "ai_review_pass":
            return (
                "green",
                f"{requirement.req_id} AI Review 已通过",
                latest_review,
                "reviewer 已确认文档达到 AI Ready，流程进入人工确认。",
                "请需求提出者确认当前文档是否准确表达需求；如不准确，请明确指出继续修改的内容。",
            )
        if trigger == "human_confirmed":
            return (
                "green",
                f"{requirement.req_id} 已进入正式审查",
                "需求提出者已完成人工确认。",
                "流程已进入正式审查阶段。",
                "请执行正式审查，并给出“确认通过”或“需要修改”的结论。",
            )
        if trigger == "human_rejected":
            return (
                "orange",
                f"{requirement.req_id} 被人工确认退回",
                latest_review,
                "人工确认未通过，流程已退回需求构造阶段。",
                f"请由 {author_name} 根据反馈继续修改，并准备下一轮 AI Review。",
            )
        if trigger == "final_review_passed":
            return (
                "green",
                f"{requirement.req_id} 已批准通过",
                latest_review,
                "正式审查已通过，当前需求进入批准完成状态。",
                "无需进一步介入，可按后续规格/实现流程继续推进。",
            )
        if trigger == "final_review_rejected":
            return (
                "orange",
                f"{requirement.req_id} 正式审查退回",
                latest_review,
                "正式审查未通过，流程已退回需求构造阶段。",
                f"请由 {author_name} 继续补充修改后，再发起新一轮 AI Review。",
            )
        if trigger == "handoff_to_author":
            return (
                "blue",
                f"{requirement.req_id} 已交由需求构造",
                "需求已创建并完成 author 接手。",
                "当前需求进入需求构造阶段，由需求构造助手继续推进文档。",
                f"请需求提出者继续与 {author_name} 私聊完成多轮需求构造。",
            )
        return ("grey", "", "", "", "")

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
