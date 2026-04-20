from __future__ import annotations

import collections
import concurrent.futures
import hmac
import hashlib
import json
import logging
import re
import threading
import time
from dataclasses import dataclass, replace
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from .config import Settings, load_settings
from .coordinator_service import CoordinatorService
from .feishu_gateway import FeishuGateway
from .models import DISCUSSION_FIELDS, Requirement, ReviewFinding, ReviewResult, WorkflowStatus, utc_now
from .plan_state_machine import PlanPhase, PlanStatus
from .spec_state_machine import SpecStatus
from .project_config import ProjectConfig
from .protocols import (
    AgentAuthorEventPayload,
    AgentRequirementContextQuery,
    AgentReviewEventPayload,
    AuthorStartBinding,
    CreationFormPayload,
    CreationRequest,
    ProjectCreationFormPayload,
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

SPEC_RESTART_RE = re.compile(r"^/spec\s+restart\s+(REQ-\S+)\s*$")
PLAN_RESTART_RE = re.compile(r"^/plan\s+restart\s+(REQ-\S+)\s*$")
DESIGN_RESTART_RE = re.compile(r"^/design\s+restart\s+(REQ-\S+)\s*$")

# Feishu prepends '@_user_<key> ' (one per @ in the message) before the
# actual text when the bot is mentioned. Strip leading occurrences so
# slash-command parsers see plain '/...'.
_MENTION_PREFIX_RE = re.compile(r"^(?:@_user_\w+\s+)+")


def _strip_mention_prefix(text: str) -> str:
    return _MENTION_PREFIX_RE.sub("", text, count=1)


@dataclass(frozen=True)
class CreateProjectCommand:
    """Marker object: `/create project` with no args was received.

    Card-based flow: the actual form values come later via
    _handle_card_action_payload(action_name='submit_create_project').
    """


_CREATE_PROJECT_RE = re.compile(r"^/create\s+project\s*$")

# Categories supported by Bootstrap. Keep in sync with
# project_bootstrap.static_content._SECRETS_CATEGORY_HINTS.
KNOWN_PROJECT_CATEGORIES: tuple[str, ...] = (
    "enterprise-app",
    "enterprise-bot",
    "miniprogram",
    "public-web-site",
    "saas-ai-automation",
)


def parse_create_project_command(text: str) -> CreateProjectCommand | None:
    if not _CREATE_PROJECT_RE.match(text.strip()):
        return None
    return CreateProjectCommand()


@dataclass(frozen=True)
class CreateReqCommand:
    """Marker: `/create req` with no args was received."""


_CREATE_REQ_RE = re.compile(r"^/create\s+req\s*$")


def parse_create_req_command(text: str) -> CreateReqCommand | None:
    if not _CREATE_REQ_RE.match(text.strip()):
        return None
    return CreateReqCommand()


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
        project_bootstrap_service: object | None = None,
    ) -> None:
        self.settings = settings
        self.settings.validate_runtime()
        self.store = store or JsonStateStore(settings.state_store_path)
        self.service = service or CoordinatorService()
        self.gateway = gateway or FeishuGateway(settings)
        self._project_bootstrap_service = project_bootstrap_service
        self._github_gateway: object | None = None
        requirements, active_req_by_user, project_groups, _legacy_project_configs = self.store.load_snapshot()
        project_configs: dict = {}
        list_fn = getattr(self.gateway, "list_project_configs", None)
        if callable(list_fn):
            try:
                project_configs = list_fn() or {}
            except Exception as exc:
                LOGGER.error(
                    "Failed to load project_configs from Bitable at startup: %s. "
                    "project_configs will be empty; spec-context calls will fail until the table is reachable.",
                    exc,
                )
                project_configs = {}
        if service is None or requirements or active_req_by_user or project_groups or project_configs:
            self.service.restore_snapshot(requirements, active_req_by_user, project_groups, project_configs)
        upsert_fn = getattr(self.gateway, "upsert_project_config", None)
        if callable(upsert_fn):
            self.service.set_project_config_persister(upsert_fn)
        self._health_server: HTTPServer | None = None
        self._observed_creation_group_chat_id = settings.creation_group_chat_id
        self._pending_form_payloads: dict[str, CreationFormPayload] = {}
        # Feishu can re-deliver the same IM event (at-least-once). Paired
        # with idempotent slash handlers this surfaces as duplicate replies.
        # Dedupe by message_id; bounded so we don't grow unbounded.
        self._seen_message_ids: collections.OrderedDict[str, None] = collections.OrderedDict()
        self._seen_message_ids_max = 1024
        # Feishu also re-delivers card actions; dedupe by (open_message_id, action_name).
        self._seen_card_action_ids: collections.OrderedDict[tuple[str, str], None] = collections.OrderedDict()
        self._seen_card_action_ids_max = 1024

        if settings.github_token:
            from pathlib import Path
            from .github_gateway import GitHubGateway
            from .project_repo import GitHubProjectRepoTools
            github_gateway = GitHubGateway(settings)
            self._github_gateway = github_gateway
            tools = GitHubProjectRepoTools(github_gateway)
            trace_dir = Path(settings.spec_trace_dir)
            trace_dir.mkdir(parents=True, exist_ok=True)
            self.service.configure_spec_orchestrator(
                tools=tools,
                trace_dir=trace_dir,
                feishu=self.gateway,
            )
            if self._project_bootstrap_service is None:
                from .project_bootstrap.service import ProjectBootstrapService
                self._project_bootstrap_service = ProjectBootstrapService(
                    repo_tools=tools,
                    feishu_gateway=self.gateway,
                    github_gateway=github_gateway,
                    template_owner=settings.github_template_owner,
                    template_repo=settings.github_template_repo,
                    new_owner=settings.github_org_owner,
                )

        from .spec_context import SpecContextBuilder

        self._spec_context_builder = SpecContextBuilder(
            service=self.service,
            gateway=self.gateway,
        )
        from .plan_context import PlanContextBuilder
        self._plan_context_builder = PlanContextBuilder(service=self.service)

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
                if self.path.startswith("/queries/openclaw/plan-context/"):
                    req_id = self.path.rsplit("/", 1)[-1]
                    status, payload = app.handle_openclaw_plan_context_query(req_id)
                else:
                    status, payload = 200, {"status": "ok", "service": service_name}
                body = json.dumps(payload, ensure_ascii=False).encode()
                self.send_response(status)
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
                elif self.path == "/queries/openclaw/spec-context":
                    status, payload = app.handle_openclaw_spec_context_query(raw_body, headers=headers)
                elif self.path.startswith("/queries/openclaw/plan-context/"):
                    req_id = self.path.rsplit("/", 1)[-1]
                    status, payload = app.handle_openclaw_plan_context_query(req_id)
                elif self.path == "/callbacks/openclaw/spec-turn":
                    status, payload = app.handle_openclaw_spec_turn_callback(raw_body, headers=headers)
                elif self.path == "/callbacks/openclaw/spec-transform":
                    status, payload = app.handle_openclaw_spec_transform_callback(raw_body, headers=headers)
                elif self.path == "/openclaw/plan-callback":
                    body_json = json.loads(raw_body.decode("utf-8") or "{}")
                    status, payload = app.handle_openclaw_plan_callback(body_json)
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
        if context.message_id and not self._mark_message_seen(context.message_id):
            LOGGER.info(
                "Dropping duplicate message_id=%s chat_id=%s text=%r",
                context.message_id, context.chat_id, context.text,
            )
            return
        LOGGER.info(
            "Received message chat_id=%s chat_type=%s user_id=%s text=%r",
            context.chat_id,
            context.chat_type,
            context.user_id,
            context.text,
        )
        try:
            outbounds = self.handle_text_message(context)
        except Exception as exc:
            LOGGER.exception(
                "handle_text_message crashed chat_id=%s text=%r",
                context.chat_id, context.text,
            )
            try:
                self.gateway.send_text(
                    context.chat_id,
                    f"内部错误：{type(exc).__name__}: {exc}",
                    receive_id_type="chat_id",
                )
            except Exception:
                LOGGER.exception("Failed to send error reply to chat_id=%s", context.chat_id)
            return
        for outbound in outbounds:
            try:
                if isinstance(outbound, OutboundCard):
                    self.gateway.send_card(outbound.receive_id, outbound.card, receive_id_type=outbound.receive_id_type)
                else:
                    self.gateway.send_text(outbound.receive_id, outbound.text, receive_id_type=outbound.receive_id_type)
            except Exception:
                LOGGER.exception(
                    "send failed receive_id=%s receive_id_type=%s",
                    outbound.receive_id, outbound.receive_id_type,
                )

    def _mark_message_seen(self, message_id: str) -> bool:
        """Returns True if message_id is new (and records it), False if already seen."""
        if message_id in self._seen_message_ids:
            return False
        self._seen_message_ids[message_id] = None
        while len(self._seen_message_ids) > self._seen_message_ids_max:
            self._seen_message_ids.popitem(last=False)
        return True

    def _mark_card_action_seen(self, open_message_id: str, action_name: str) -> bool:
        """Returns True if (open_message_id, action_name) is new; False if already seen."""
        key = (open_message_id, action_name)
        if key in self._seen_card_action_ids:
            return False
        self._seen_card_action_ids[key] = None
        while len(self._seen_card_action_ids) > self._seen_card_action_ids_max:
            self._seen_card_action_ids.popitem(last=False)
        return True

    def _on_card_action_trigger(self, data: P2CardActionTrigger):
        payload = self._card_event_to_payload(data)
        status, response_payload = self._handle_card_action_payload(payload)
        if status != 200:
            LOGGER.warning("Card action handled with status=%s payload=%s", status, payload)
        return P2CardActionTriggerResponse(response_payload)

    def handle_text_message(self, context: MessageContext) -> list[OutboundMessage | OutboundCard]:
        text = _strip_mention_prefix(context.text.strip())
        if not text:
            return []
        # Keep the stripped text on the context so downstream handlers
        # (slash parsers, free-text matchers) see it consistently.
        if text != context.text:
            context = replace(context, text=text)

        m = SPEC_RESTART_RE.match(text)
        if m:
            return self._handle_spec_restart_command(req_id=m.group(1), context=context)

        reply = self.handle_slash_command(text)
        if reply is not None:
            return [OutboundMessage(receive_id=context.chat_id, text=reply)]

        # /create project and /create req work from any chat (DM, group, creation group).
        project_cmd = parse_create_project_command(text)
        if project_cmd is not None:
            return self._handle_create_project_command(project_cmd, context)
        req_cmd = parse_create_req_command(text)
        if req_cmd is not None:
            return self._handle_create_req_command(req_cmd, context)

        if text.strip() in {"/create", "/create "}:
            return [OutboundMessage(
                receive_id=context.chat_id,
                text="请用 `/create project` 或 `/create req`",
            )]

        if self._is_creation_group_message(context):
            return self._handle_creation_group_message(context)

        if context.chat_type == "p2p":
            return self._handle_author_private_message(context)

        return []

    def _handle_creation_group_message(self, context: MessageContext) -> list[OutboundMessage | OutboundCard]:
        if "创建需求" in context.text or "新建需求" in context.text:
            self._observed_creation_group_chat_id = context.chat_id
            return [OutboundMessage(
                receive_id=context.chat_id,
                text=(
                    "REQ 创建已改用卡片：\n"
                    "直接发送 `/create req`，在弹出的卡片里选项目、填名称和简述。"
                ),
            )]
        return []

    def _handle_create_req_command(
        self, cmd: "CreateReqCommand", context: MessageContext,
    ) -> list[OutboundMessage | OutboundCard]:
        provisioned = [
            name for name, cfg in self.service.project_configs.items()
            if cfg.bootstrap_status == "PROVISIONED"
        ]
        if not provisioned:
            return [OutboundMessage(
                receive_id=context.chat_id,
                text="尚无已注册（PROVISIONED）的项目，请先 `/create project`。",
            )]
        return [OutboundCard(
            receive_id=context.chat_id,
            card=self._build_requirement_creation_card(context),
        )]

    def _handle_create_project_command(
        self, cmd: "CreateProjectCommand", context: MessageContext,
    ) -> list[OutboundMessage | OutboundCard]:
        if self._project_bootstrap_service is None:
            return [OutboundMessage(
                receive_id=context.chat_id,
                text="Bootstrap 服务未启用；请联系运维检查 settings.github_token 配置",
            )]
        return [OutboundCard(
            receive_id=context.chat_id,
            card=self._build_project_creation_card(context),
        )]

    def _handle_spec_restart_command(self, *, req_id: str, context: MessageContext) -> list[OutboundMessage]:
        try:
            self.service.spec_restart(req_id)
        except KeyError:
            return [OutboundMessage(receive_id=context.chat_id, text=f"未找到 {req_id}")]
        except ValueError as exc:
            return [OutboundMessage(receive_id=context.chat_id, text=f"重启失败：{exc}")]
        return [OutboundMessage(
            receive_id=context.chat_id,
            text=f"{req_id} 规格层已重置，请重新点击「启动 Spec 撰写」",
        )]

    def _create_requirement_from_form(
        self,
        payload: CreationFormPayload,
    ) -> tuple[CreationRequest, Requirement | None, str]:
        request = CreationRequest(
            project=payload.project,
            name=payload.name,
            summary=payload.summary,
            creator=payload.creator,
            creator_user_id=payload.creator_user_id,
            creation_chat_id=payload.creation_chat_id,
        )
        response = self.service.create_requirement_from_group(request)
        requirement = self.service.get_requirement(response.req_id)
        if requirement is not None:
            requirement.needs_ui = payload.needs_ui
        self._save_state()
        self._pending_form_payloads[response.req_id] = payload
        if requirement is not None:
            LOGGER.info(
                "Accepted requirement creation from form req_id=%s status=%s project=%s creator_user_id=%s needs_ui=%s",
                requirement.req_id,
                requirement.status.value,
                requirement.project,
                requirement.creator_user_id,
                requirement.needs_ui,
            )
        return request, requirement, response.req_id

    def _run_project_bootstrap_async(self, req) -> None:
        """Run ProjectBootstrapService.run in a daemon thread and dispatch
        the result (success or failure) back to the creator chat by text."""
        from .project_bootstrap.types import BootstrapStepError
        from .project_bootstrap.service import ValidationError
        try:
            result = self._project_bootstrap_service.run(req)
        except ValidationError as exc:
            LOGGER.warning("Bootstrap validation failed project=%s: %s", req.project, exc)
            try:
                self.gateway.send_text(
                    req.creator_chat_id, f"Bootstrap 校验失败：{exc}",
                )
            except Exception:
                LOGGER.exception("Failed to send validation-error text")
            return
        except BootstrapStepError as exc:
            LOGGER.warning(
                "Bootstrap step failed project=%s step=%s: %s",
                req.project, exc.step.name, exc.message,
            )
            try:
                self.gateway.send_text(
                    req.creator_chat_id,
                    (
                        f"Bootstrap 中断于 Step {int(exc.step)} ({exc.step.name})：{exc.message}\n"
                        f"请重新 `/create project`，填同样的项目代号即可自动续跑。"
                    ),
                )
            except Exception:
                LOGGER.exception("Failed to send step-error text")
            return
        except Exception:
            LOGGER.exception("Unexpected Bootstrap failure project=%s", req.project)
            try:
                self.gateway.send_text(
                    req.creator_chat_id,
                    f"Bootstrap 内部错误，请联系运维查日志。项目：{req.project}",
                )
            except Exception:
                LOGGER.exception("Failed to send unexpected-error text")
            return

        # Bootstrap wrote the project to Bitable via `upsert_project_config`,
        # but `service.project_configs` is only loaded at startup. Refresh
        # the entry for this project so `/create req` sees it immediately.
        try:
            fresh = self.gateway.list_project_configs()
            if fresh and req.project in fresh:
                self.service.project_configs[req.project] = fresh[req.project]
        except Exception:
            LOGGER.exception(
                "Failed to refresh project_configs after Bootstrap project=%s", req.project,
            )
        try:
            self._save_state()
        except Exception:
            LOGGER.exception("Failed to persist state after Bootstrap project=%s", req.project)
        try:
            self.gateway.send_text(
                req.creator_chat_id,
                (
                    f"项目 {result.project} 已就绪：\n"
                    f"- Repo: {result.github_repo_url}\n"
                    f"- ARCHITECTURE: {result.architecture_doc_url}\n"
                    f"- 群 chat_id: {result.feishu_chat_id}\n"
                    f"可开始用 `/create req` 创建需求。"
                ),
            )
        except Exception:
            LOGGER.exception("Failed to send Bootstrap success text project=%s", req.project)

    def _provision_requirement_after_creation(self, request: CreationRequest, req_id: str) -> None:
        form_payload = self._pending_form_payloads.pop(req_id, None)
        if form_payload is not None:
            existing = self.service.project_configs.get(form_payload.project)
            if existing is None:
                LOGGER.warning(
                    "REQ %s created but project %s missing from project_configs — "
                    "Bootstrap should have populated it; skipping project-init",
                    req_id, form_payload.project,
                )

        requirement = self.service.get_requirement(req_id)
        if requirement is None:
            LOGGER.warning("Skipped provisioning because requirement disappeared req_id=%s", req_id)
            return
        if not self._is_feishu_chat_id(requirement.project_group_id):
            try:
                project_group = self.gateway.create_project_group(
                    project=requirement.project,
                    owner_user_id=request.creator_user_id,
                    member_user_ids=[request.creator_user_id],
                )
                self.service.assign_project_group(requirement.req_id, project_group.chat_id)
            except Exception as exc:
                LOGGER.warning("Failed to create project group for %s: %s", requirement.req_id, exc)

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            record_future = executor.submit(self.gateway.create_requirement_record, requirement)
            document_future = executor.submit(self.gateway.create_requirement_document, requirement)
            try:
                created_record = record_future.result()
                if created_record:
                    self.service.attach_bitable_record(requirement.req_id, created_record.record_id)
            except Exception as exc:
                LOGGER.warning("Failed to create bitable record for %s: %s", requirement.req_id, exc)
            try:
                created_document = document_future.result()
                if created_document:
                    self.service.attach_document(
                        requirement.req_id,
                        created_document.document_id,
                        created_document.document_url,
                    )
            except Exception as exc:
                LOGGER.warning("Failed to create document for %s: %s", requirement.req_id, exc)

        if requirement.bitable_record_id:
            try:
                self.gateway.update_requirement_record(requirement)
            except Exception as exc:
                LOGGER.warning("Failed to refresh bitable record for %s: %s", requirement.req_id, exc)

        existing_cfg = self.service.project_configs.get(request.project)
        if existing_cfg and existing_cfg.github_repo_url and self._github_gateway is not None:
            from datetime import datetime, timezone
            from .req_registry import append_req_to_registry
            owner_name = existing_cfg.github_repo_url.rstrip("/").rsplit("/", 2)[-2:]
            if len(owner_name) == 2:
                project_repo = "/".join(owner_name)
                append_req_to_registry(
                    github_gateway=self._github_gateway,
                    project_repo=project_repo,
                    req_id=req_id,
                    title=requirement.name if requirement else req_id,
                    status="DRAFTING",
                    created_at=datetime.now(timezone.utc).isoformat(),
                    swallow_errors=True,
                )

        LOGGER.info(
            "Provisioned requirement from form req_id=%s status=%s project_group_id=%s bitable_record_id=%s document_url=%s",
            requirement.req_id,
            requirement.status.value,
            requirement.project_group_id,
            requirement.bitable_record_id,
            requirement.document_url,
        )
        requirement = self.service.get_requirement(req_id)
        messages: list[OutboundMessage | OutboundCard] = []
        if requirement:
            messages.append(
                OutboundCard(
                    receive_id=request.creation_chat_id,
                    receive_id_type="chat_id",
                    card=self._build_requirement_created_result_card(requirement),
                )
            )
        else:
            creation_text = (
                f"{req_id} 已创建\n"
                f"项目：{request.project}\n"
                f"需求文档入口已准备，后续由需求构造 Agent 持续撰写\n"
                f"请私聊需求构造 Agent，并发送：\n开始需求构造 {req_id}"
            )
            bitable_url = self.gateway.bitable_url()
            if bitable_url:
                creation_text += f"\n多维表格：{bitable_url}"
            messages.append(OutboundMessage(receive_id=request.creation_chat_id, text=creation_text))
        if requirement and self._is_feishu_chat_id(requirement.project_group_id):
            messages.append(
                OutboundCard(
                    receive_id=requirement.project_group_id,
                    card=self._build_project_group_card(requirement),
                )
            )
        for outbound in messages:
            try:
                if isinstance(outbound, OutboundCard):
                    self.gateway.send_card(outbound.receive_id, outbound.card, receive_id_type=outbound.receive_id_type)
                else:
                    self.gateway.send_text(outbound.receive_id, outbound.text, receive_id_type=outbound.receive_id_type)
            except Exception as exc:
                LOGGER.warning(
                    "Failed to send post-create outbound req_id=%s receive_id=%s kind=%s: %s",
                    req_id,
                    outbound.receive_id,
                    "card" if isinstance(outbound, OutboundCard) else "text",
                    exc,
                )
        self._save_state()

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
        agent_name = self.settings.openclaw_author_agent_name
        return [
            OutboundMessage(
                receive_id=context.chat_id,
                text=(
                    "\u8bf7\u524d\u5f80 " + agent_name + " \u7ee7\u7eed\u9700\u6c42\u6784\u9020\u3002\n"
                    "\u5728 " + agent_name + " \u4e2d\u53d1\u9001\uff1a\n"
                    "\u5f00\u59cb\u9700\u6c42\u6784\u9020 " + requirement.req_id
                ),
            )
        ]

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

        # Create design system document for the first UI requirement that gets APPROVED
        if approved and requirement.status == WorkflowStatus.APPROVED and requirement.needs_ui:
            if self.service.should_create_design_system(requirement.project):
                try:
                    doc_id = self.gateway.create_design_system_document(requirement.project)
                    self.service.set_design_system_doc(requirement.project, doc_id)
                    LOGGER.info(
                        "Design system document created project=%s doc_id=%s",
                        requirement.project, doc_id,
                    )
                except Exception as exc:
                    LOGGER.warning("Failed to create design system document: %s", exc)

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
        completed_fields_raw = payload.get("completed_fields", [])
        completed_fields = [str(f) for f in completed_fields_raw] if isinstance(completed_fields_raw, list) else []

        if not req_id or not event or not summary:
            return 400, {"error": "invalid_payload", "message": "req_id、event、summary 为必填字段。"}
        if normalized_event != "author_submit":
            return 400, {"error": "invalid_payload", "message": f"不支持的 author 事件：{event}。"}
        if iteration_round is not None and not isinstance(iteration_round, int):
            return 400, {"error": "invalid_payload", "message": "iteration_round 必须是整数。"}

        LOGGER.info(
            "Received author callback req_id=%s event=%s iteration_round=%s document_url=%s completed_fields=%s",
            req_id,
            normalized_event,
            iteration_round,
            document_url,
            completed_fields,
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
                    completed_fields=completed_fields,
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
            if requirement.spec_status == SpecStatus.TRANSFORMING:
                self._dispatch_transition_notifications(requirement, trigger="spec_transforming")
                self._wake_spec_transform_agent(requirement.req_id, "wake_transformer")
            elif requirement.spec_status == SpecStatus.LOCKED:
                self._dispatch_transition_notifications(requirement, trigger="spec_locked")
            elif requirement.spec_status == SpecStatus.DRAFTING and normalized_event == "ai_review_reject":
                self._dispatch_transition_notifications(requirement, trigger="spec_review_reject")
            else:
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

    def handle_openclaw_spec_context_query(
        self,
        raw_body: bytes,
        *,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, object]]:
        from .spec_context import (
            ConcurrentSpecInProgress,
            SpecContextGateError,
            SpecContextMisconfigured,
        )

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

        LOGGER.info("Received spec-context query req_id=%s", req_id)

        try:
            result = self._spec_context_builder.build(req_id)
        except ValueError as exc:
            return 404, {"error": "not_found", "message": str(exc)}
        except SpecContextGateError as exc:
            return 409, {
                "error": "invalid_state",
                "message": str(exc),
                "current_status": exc.current_status,
            }
        except ConcurrentSpecInProgress as exc:
            return 409, {"error": "concurrent_spec_in_progress", "message": str(exc)}
        except SpecContextMisconfigured as exc:
            return 500, {"error": "project_not_initialized", "message": str(exc)}
        except Exception as exc:
            LOGGER.exception("Unexpected failure handling spec-context req_id=%s", req_id)
            return 500, {"error": "spec_context_failed", "message": str(exc)}

        self._save_state()

        LOGGER.info(
            "Spec-context served req_id=%s doc_revision=%s",
            req_id,
            result.context["architecture_doc_revision"],
        )
        return 200, {
            "ok": True,
            "context": result.context,
            "context_token": result.context_token,
            "expires_hint": "valid until SPEC_LOCKED or a newer token is issued",
        }

    def handle_openclaw_plan_context_query(
        self, req_id: str,
    ) -> tuple[int, dict]:
        from .plan_context import (
            PlanContextGateError, PlanContextMisconfigured,
        )
        r = self.service.requirements.get(req_id)
        if r is None:
            return 404, {"error": "not_found", "req_id": req_id}
        try:
            ctx = self._plan_context_builder.build(req_id)
            return 200, ctx
        except PlanContextGateError as exc:
            return 409, {"error": "gate_failed", "message": str(exc)}
        except PlanContextMisconfigured as exc:
            return 409, {"error": "misconfigured", "message": str(exc)}
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.exception("plan-context failed req_id=%s", req_id)
            return 500, {"error": "plan_context_failed", "message": str(exc)}

    def handle_slash_command(self, text: str) -> str | None:
        """Return human-readable reply, or None if no match."""
        m = PLAN_RESTART_RE.match(text.strip())
        if m:
            req_id = m.group(1)
            try:
                self.service.plan_restart(req_id)
            except KeyError:
                return f"未知需求：{req_id}"
            except ValueError as exc:
                return f"不能执行 /plan restart {req_id}：{exc}"
            self._save_state()
            return f"规划层已重置（含下游 spec 级联清理）：{req_id}"
        m = DESIGN_RESTART_RE.match(text.strip())
        if m:
            req_id = m.group(1)
            try:
                self.service.design_restart(req_id)
            except KeyError:
                return f"未知需求：{req_id}"
            except ValueError as exc:
                return f"不能执行 /design restart {req_id}：{exc}"
            self._save_state()
            return f"设计层已重置（含下游 plan + spec 级联清理）：{req_id}"
        return None

    def handle_openclaw_plan_callback(
        self, body: dict,
    ) -> tuple[int, dict]:
        req_id = body.get("req_id", "")
        event = body.get("event", "")
        payload = body.get("payload") or {}

        r = self.service.requirements.get(req_id)
        if r is None:
            return 404, {"error": "not_found", "req_id": req_id}

        try:
            if event == "plan_outline_submit":
                self.service.set_plan_outline(req_id, payload.get("outline", []))
                self._save_state()
                return 200, {"req_id": req_id, "plan_phase": "decisions_in_progress"}
            if event == "plan_submit":
                if r.plan_status != PlanStatus.DRAFTING:
                    return 409, {
                        "error": "invalid_state",
                        "message": f"plan_submit requires plan_status=DRAFTING, got {r.plan_status.value if r.plan_status else 'None'}",
                    }
                r.pending_plan_review = {
                    "plan_md_content": payload.get("plan_md_content", ""),
                    "project_context_change": (
                        payload.get("project_context_change")
                        or payload.get("architecture_change")
                    ),
                    "submitted_at": utc_now().isoformat(),
                }
                r.plan_phase = PlanPhase.FINAL_REVIEW_PENDING
                self._save_state()
                self._dispatch_transition_notifications(
                    r, trigger="plan_submitted_pending_review"
                )
                return 200, {
                    "req_id": req_id,
                    "plan_status": r.plan_status.value,
                    "plan_phase": r.plan_phase.value,
                }
            return 400, {"error": "unknown_event", "event": event}
        except ValueError as exc:
            return 409, {"error": "invalid_state", "message": str(exc)}
        except Exception as exc:  # pragma: no cover
            LOGGER.exception("plan-callback failed req_id=%s event=%s", req_id, event)
            return 500, {"error": "plan_callback_failed", "message": str(exc)}

    def handle_openclaw_spec_turn_callback(
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
        summary = str(payload.get("summary", "")).strip()
        spec_document_url_from_payload = str(payload.get("spec_document_url", "")).strip()
        architecture_doc_revision = str(payload.get("architecture_doc_revision", "")).strip()

        if not req_id or not event or not summary:
            return 400, {"error": "invalid_payload", "message": "req_id、event、summary 为必填字段。"}

        supported_events = {"spec_start", "spec_submit"}
        if event not in supported_events:
            return 400, {"error": "invalid_payload", "message": f"不支持的 spec 事件：{event}。"}

        LOGGER.info("Received spec-turn callback req_id=%s event=%s", req_id, event)

        requirement = self.service.get_requirement(req_id)
        if requirement is None:
            return 404, {"error": "not_found", "message": f"未知需求：{req_id}"}

        if event == "spec_start":
            if requirement.status != WorkflowStatus.APPROVED:
                return 400, {
                    "error": "invalid_state",
                    "message": f"spec_start 只能在 APPROVED 状态执行，当前状态：{requirement.status.value}",
                }
            if self.service._has_concurrent_spec(
                requirement.project, exclude_req_id=req_id
            ):
                return 409, {
                    "error": "concurrent_spec_in_progress",
                    "message": (
                        f"项目 {requirement.project} 已有另一条需求处于 SPEC_DRAFTING，"
                        "请先等待其锁定。"
                    ),
                }
            try:
                created_doc = self.gateway.create_spec_document(requirement)
            except Exception as exc:
                LOGGER.exception("Failed to create spec document for %s", req_id)
                return 500, {"error": "create_spec_document_failed", "message": str(exc)}

            spec_doc_id = created_doc.document_id if created_doc else ""
            spec_doc_url = created_doc.document_url if created_doc else ""

            try:
                requirement = self.service.submit_spec_start(
                    req_id,
                    spec_document_id=spec_doc_id,
                    spec_document_url=spec_doc_url,
                )
            except ValueError as exc:
                return 400, {"error": "invalid_state", "message": str(exc)}

            self._sync_requirement_outputs(requirement)
            self._save_state()
            LOGGER.info(
                "Spec start accepted req_id=%s status=%s spec_document_id=%s",
                req_id, requirement.status.value, spec_doc_id,
            )
            return 200, {
                "ok": True,
                "req_id": req_id,
                "status": requirement.status.value,
                "spec_status": requirement.spec_status.value if requirement.spec_status else None,
                "spec_document_id": requirement.spec_document_id,
                "spec_document_url": requirement.spec_document_url,
                "requirement_document_url": requirement.document_url,
            }

        if event == "spec_submit":
            if requirement.spec_status != SpecStatus.DRAFTING:
                spec_label = requirement.spec_status.value if requirement.spec_status else "None"
                return 400, {
                    "error": "invalid_state",
                    "message": f"spec_submit 只能在 spec_status=SPEC_DRAFTING 状态执行，当前：{spec_label}",
                }
            if not architecture_doc_revision:
                return 400, {
                    "error": "missing_doc_revision",
                    "message": "spec_submit 必须回传 architecture_doc_revision。",
                }
            try:
                requirement = self.service.submit_spec_submit(req_id, summary=summary)
            except ValueError as exc:
                return 400, {"error": "invalid_state", "message": str(exc)}

            requirement.spec_context_snapshot_revision = architecture_doc_revision
            if spec_document_url_from_payload:
                requirement.spec_document_url = spec_document_url_from_payload

            self._save_state()
            self._dispatch_transition_notifications(requirement, trigger="spec_submitted")
            LOGGER.info("Spec submit accepted req_id=%s summary=%s", req_id, summary)
            return 200, {"ok": True, "message": "Spec 已提交，已通知项目群发起审查"}

        return 400, {"error": "invalid_event"}

    def handle_openclaw_spec_transform_callback(
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
        data = payload.get("data") or {}
        if not req_id or not event:
            return 400, {"error": "invalid_payload", "message": "req_id、event 为必填字段。"}
        if not isinstance(data, dict):
            return 400, {"error": "invalid_payload", "message": "data 必须是对象。"}

        orch = self.service.spec_orchestrator
        if orch is None:
            return 503, {"error": "orchestrator_unavailable"}

        try:
            if event == "transformer_output":
                action = orch.handle_transformer_output(req_id, data)
            elif event == "reviewer_verdict":
                verdict = str(data.get("verdict", "")).strip()
                findings = data.get("findings", []) or []
                if not verdict:
                    return 400, {"error": "invalid_payload", "message": "reviewer_verdict 缺少 verdict。"}
                action = orch.handle_reviewer_verdict(req_id, verdict, findings)
            else:
                return 400, {"error": f"unknown_event: {event}"}
        except Exception as exc:
            LOGGER.exception(
                "Spec transform callback failed req_id=%s event=%s", req_id, event,
            )
            return 500, {"error": "spec_transform_failed", "message": str(exc)}

        self._save_state()
        if action in (
            "wake_reviewer",
            "wake_transformer_next_round",
            "wake_transformer_regression_retry",
            "soft_retry_transformer",
        ):
            self._wake_spec_transform_agent(req_id, action)

        return 200, {"ok": True, "req_id": req_id, "next_action": action}

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

        context = payload.get("context", {}) or {}
        open_message_id = context.get("open_message_id", "") or ""
        if open_message_id and action_name and not self._mark_card_action_seen(
            open_message_id, str(action_name)
        ):
            LOGGER.info(
                "Dropping duplicate card action open_message_id=%s action=%s",
                open_message_id, action_name,
            )
            return 200, {"toast": {"type": "info", "content": "已处理，跳过重复回调。"}}

        if action_name == "submit_create_project":
            form = self._extract_project_form_payload(
                payload, user_id=user_id, user_name=user_name,
            )
            if form is None:
                return 200, {"toast": {"type": "error", "content": "项目代号 / 类目为必填字段。"}}
            if not re.match(r"^[a-z][a-z0-9-]{1,30}$", form.project):
                self.gateway.send_text(
                    form.creator_chat_id,
                    f"项目代号格式不合法：{form.project!r}（需小写字母开头、2-30 位、仅含 a-z 0-9 -）",
                )
                return 200, {"toast": {"type": "error", "content": "项目代号格式不合法。"}}
            if form.category not in KNOWN_PROJECT_CATEGORIES:
                return 200, {"toast": {"type": "error", "content": f"未知类目：{form.category}"}}
            if self._project_bootstrap_service is None:
                return 200, {"toast": {"type": "error", "content": "Bootstrap 服务未启用。"}}

            existing = self.service.project_configs.get(form.project)
            if existing is not None and existing.bootstrap_status == "PROVISIONED":
                self.gateway.send_text(
                    form.creator_chat_id,
                    f"项目 {form.project} 已经完成 Bootstrap，请用 `/create req` 创建需求。",
                )
                return 200, {"toast": {"type": "info", "content": "项目已完成 Bootstrap。"}}

            resume = existing is not None and existing.bootstrap_status != "PROVISIONED"

            from .project_bootstrap.types import BootstrapRequest
            req = BootstrapRequest(
                project=form.project,
                category=form.category,
                owner_user_id=form.owner_user_id,
                creator_chat_id=form.creator_chat_id,
                resume=resume,
                github_username=form.github_username,
                architecture_seed={
                    "display_name": form.display_name,
                    "brief": form.brief,
                    "tech_stack": form.tech_stack,
                },
            )
            # Bootstrap takes ~30s (clone, push, docs, group). Feishu drops
            # the card with 回调超时 if we block the callback that long, so
            # kick Bootstrap onto a daemon thread and ack immediately.
            threading.Thread(
                target=self._run_project_bootstrap_async,
                args=(req,),
                daemon=True,
            ).start()
            verb = "续跑" if resume else "创建"
            return 200, {"toast": {"type": "info", "content": f"{verb}中：{req.project}（Bootstrap 约需 30s，完成后会发群消息）"}}

        if action_name == "submit_create_requirement":
            form_payload = self._extract_creation_form_payload(payload, user_id=user_id, user_name=user_name)
            if form_payload is None:
                return 200, {"toast": {"type": "error", "content": "创建表单字段不完整，请补充项目、名称和简述。"}}
            project_cfg = self.service.project_configs.get(form_payload.project)
            if project_cfg is None or project_cfg.bootstrap_status != "PROVISIONED":
                status_label = project_cfg.bootstrap_status if project_cfg else "不存在"
                return 200, {"toast": {"type": "error", "content": f"项目 {form_payload.project} 当前状态 {status_label}，无法新建需求。"}}
            request, _, req_id = self._create_requirement_from_form(form_payload)
            threading.Thread(
                target=self._provision_requirement_after_creation,
                args=(request, req_id),
                daemon=True,
            ).start()
            return 200, {"toast": {"type": "success", "content": "需求已受理，正在同步文档、表格和项目群。"}}

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

        if action_name == "send_plan_author_start":
            req_id = value.get("req_id", "")
            if not req_id:
                return 200, {"toast": {"type": "error", "content": "缺少需求ID。"}}
            requirement = self.service.get_requirement(req_id)
            if requirement is None:
                return 200, {"toast": {"type": "error", "content": f"未知需求：{req_id}。"}}
            if requirement.status != WorkflowStatus.APPROVED:
                return 200, {"toast": {"type": "error", "content": f"当前需求不处于 APPROVED 阶段（status={requirement.status.value}），不能启动 Plan 撰写。"}}
            try:
                self.service.plan_start(req_id)
            except ValueError as exc:
                return 200, {"toast": {"type": "error", "content": f"Plan 启动失败：{exc}"}}
            self._save_state()
            target_user_id, receive_id_type = self._resolve_operator_receive_target(operator)
            if not target_user_id:
                return 200, {"toast": {"type": "error", "content": "无法识别当前点击人身份，请手动私聊 Plan 撰写助手。"}}
            try:
                self.gateway.send_text(
                    target_user_id,
                    self._build_plan_author_handoff_text(requirement),
                    receive_id_type=receive_id_type,
                )
            except Exception as exc:
                LOGGER.warning("Failed to send plan author handoff req_id=%s: %s", req_id, exc)
                return 200, {"toast": {"type": "error", "content": "私发失败，请手动私聊 Plan 撰写助手。"}}
            return 200, {"toast": {"type": "success", "content": "已将 Plan 撰写启动指令私发给你。"}}

        if action_name == "approve_plan_submit":
            req_id = value.get("req_id", "")
            if not req_id:
                return 200, {"toast": {"type": "error", "content": "缺少需求ID。"}}
            requirement = self.service.get_requirement(req_id)
            if requirement is None:
                return 200, {"toast": {"type": "error", "content": f"未知需求：{req_id}。"}}
            pending = requirement.pending_plan_review
            if not pending:
                return 200, {"toast": {"type": "error", "content": "Plan 草稿不存在，请让 Plan Author 重新提交。"}}
            if pending.get("project_context_change"):
                return 200, {"toast": {"type": "error", "content": "MVP 暂不支持 architecture_change 的 Plan 提交，请联系维护者。"}}
            try:
                self.service.plan_submit(
                    req_id,
                    plan_md_content=pending.get("plan_md_content", ""),
                    project_context_change=None,
                )
            except Exception as exc:
                LOGGER.exception("approve_plan_submit failed req_id=%s", req_id)
                return 200, {"toast": {"type": "error", "content": f"Plan 提交失败：{exc}；可再次点击重试。"}}
            requirement.pending_plan_review = None
            self._save_state()
            self._dispatch_transition_notifications(requirement, trigger="plan_ready")
            return 200, {"toast": {"type": "success", "content": "Plan 已通过并提交至 GitHub。"}}

        if action_name == "reject_plan_submit":
            req_id = value.get("req_id", "")
            if not req_id:
                return 200, {"toast": {"type": "error", "content": "缺少需求ID。"}}
            requirement = self.service.get_requirement(req_id)
            if requirement is None:
                return 200, {"toast": {"type": "error", "content": f"未知需求：{req_id}。"}}
            if not requirement.pending_plan_review:
                return 200, {"toast": {"type": "error", "content": "无可驳回的 Plan 草稿。"}}
            requirement.pending_plan_review = None
            requirement.plan_phase = PlanPhase.DECISIONS_IN_PROGRESS
            self._save_state()
            return 200, {"toast": {"type": "success", "content": "已驳回 Plan 草稿；请重新私聊 Plan Author 修改。"}}

        if action_name == "send_spec_author_start":
            req_id = value.get("req_id", "")
            if not req_id:
                return 200, {"toast": {"type": "error", "content": "缺少需求ID。"}}
            requirement = self.service.get_requirement(req_id)
            if requirement is None:
                return 200, {"toast": {"type": "error", "content": f"未知需求：{req_id}。"}}
            if (
                requirement.status != WorkflowStatus.APPROVED
                or requirement.spec_status not in {None, SpecStatus.DRAFTING}
                or requirement.plan_status != PlanStatus.READY
            ):
                spec_label = requirement.spec_status.value if requirement.spec_status else "None"
                plan_label = requirement.plan_status.value if requirement.plan_status else "None"
                return 200, {"toast": {"type": "error", "content": f"当前需求不处于 Spec 撰写阶段（status={requirement.status.value} spec_status={spec_label} plan_status={plan_label}）。Plan 未 READY，不能启动 Spec 撰写。"}}
            target_user_id, receive_id_type = self._resolve_operator_receive_target(operator)
            if not target_user_id:
                return 200, {"toast": {"type": "error", "content": "无法识别当前点击人身份，请手动私聊 Spec 撰写助手。"}}
            try:
                self.gateway.send_text(
                    target_user_id,
                    self._build_spec_author_handoff_text(requirement),
                    receive_id_type=receive_id_type,
                )
            except Exception as exc:
                LOGGER.warning("Failed to send spec author handoff req_id=%s: %s", req_id, exc)
                return 200, {"toast": {"type": "error", "content": "私发失败，请手动私聊 Spec 撰写助手。"}}
            return 200, {"toast": {"type": "success", "content": "已将 Spec 撰写启动指令私发给你。"}}

        if action_name == "send_spec_reviewer_start":
            req_id = value.get("req_id", "")
            if not req_id:
                return 200, {"toast": {"type": "error", "content": "缺少需求ID。"}}
            requirement = self.service.get_requirement(req_id)
            if requirement is None:
                return 200, {"toast": {"type": "error", "content": f"未知需求：{req_id}。"}}
            if requirement.spec_status != SpecStatus.DRAFTING:
                spec_label = requirement.spec_status.value if requirement.spec_status else "None"
                return 200, {"toast": {"type": "error", "content": f"当前需求不处于 Spec 审查阶段（status={requirement.status.value} spec_status={spec_label}）。"}}
            target_user_id, receive_id_type = self._resolve_operator_receive_target(operator)
            if not target_user_id:
                return 200, {"toast": {"type": "error", "content": "无法识别当前点击人身份，请手动私聊 Spec 审查助手。"}}
            try:
                self.gateway.send_text(
                    target_user_id,
                    self._build_spec_review_handoff(requirement),
                    receive_id_type=receive_id_type,
                )
            except Exception as exc:
                LOGGER.warning("Failed to send spec reviewer handoff req_id=%s: %s", req_id, exc)
                return 200, {"toast": {"type": "error", "content": "私发失败，请手动私聊 Spec 审查助手。"}}
            return 200, {"toast": {"type": "success", "content": "已将 Spec 审查启动指令私发给你。"}}

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
        needs_ui_raw = self._normalize_form_value(form_value.get("needs_ui")).lower()
        needs_ui = needs_ui_raw in ("yes", "true", "1", "是", "需要")
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
            needs_ui=needs_ui,
        )

    def _extract_project_form_payload(
        self,
        payload: dict[str, object],
        *,
        user_id: str,
        user_name: str,
    ) -> ProjectCreationFormPayload | None:
        action = payload.get("action", {}) or {}
        value = self._extract_callback_value(action)
        form_value = action.get("form_value") or payload.get("form_value") or {}
        if not isinstance(form_value, dict):
            form_value = {}

        project = self._normalize_form_value(form_value.get("project"))
        category = self._normalize_form_value(form_value.get("category"))
        if not project or not category:
            return None

        context = payload.get("context", {}) or {}
        creator_chat_id = (
            self._normalize_form_value(value.get("creator_chat_id"))
            or self._normalize_form_value(context.get("open_chat_id"))
        )
        return ProjectCreationFormPayload(
            project=project,
            category=category,
            owner_user_id=user_id,
            creator_chat_id=creator_chat_id,
            display_name=self._normalize_form_value(form_value.get("display_name")),
            brief=self._normalize_form_value(form_value.get("brief")),
            github_username=self._normalize_form_value(form_value.get("github_username")),
            tech_stack=self._normalize_form_value(form_value.get("tech_stack")),
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

    def _build_project_creation_card(self, context: MessageContext) -> dict[str, object]:
        category_options = [
            {"text": {"tag": "plain_text", "content": label}, "value": value}
            for label, value in (
                ("企业内部应用", "enterprise-app"),
                ("企业内 Bot / Agent", "enterprise-bot"),
                ("小程序", "miniprogram"),
                ("公开 Web 站点", "public-web-site"),
                ("SaaS AI 自动化", "saas-ai-automation"),
            )
        ]
        return {
            "schema": "2.0",
            "config": {"wide_screen_mode": True},
            "header": {
                "template": "green",
                "title": {"tag": "plain_text", "content": "新建项目"},
                "subtitle": {"tag": "plain_text", "content": "填写项目基本信息 · 提交后自动跑 Bootstrap 并生成 ARCHITECTURE.md"},
            },
            "body": {
                "elements": [
                    {
                        "tag": "form",
                        "name": "project_create_form",
                        "elements": [
                            {
                                "tag": "input",
                                "name": "project",
                                "required": True,
                                "width": "fill",
                                "label": {"tag": "plain_text", "content": "项目代号（必填，小写字母开头，2-30 位）"},
                                "placeholder": {"tag": "plain_text", "content": "例如 test5 / payment-core"},
                            },
                            {
                                "tag": "div",
                                "text": {"tag": "plain_text", "content": "项目类目（必填）"},
                            },
                            {
                                "tag": "select_static",
                                "name": "category",
                                "required": True,
                                "width": "fill",
                                "placeholder": {"tag": "plain_text", "content": "选择项目类目"},
                                "options": category_options,
                            },
                            {
                                "tag": "input",
                                "name": "display_name",
                                "required": False,
                                "width": "fill",
                                "label": {"tag": "plain_text", "content": "项目显示名（选填）"},
                                "placeholder": {"tag": "plain_text", "content": "例如 测试项目 5"},
                            },
                            {
                                "tag": "input",
                                "name": "brief",
                                "required": False,
                                "width": "fill",
                                "input_type": "multiline_text",
                                "max_length": 500,
                                "label": {"tag": "plain_text", "content": "项目简述（选填，会写进 ARCHITECTURE.md）"},
                                "placeholder": {"tag": "plain_text", "content": "一两句话描述项目做什么"},
                            },
                            {
                                "tag": "input",
                                "name": "github_username",
                                "required": False,
                                "width": "fill",
                                "label": {"tag": "plain_text", "content": "GitHub 用户名（选填，会加为 repo collaborator）"},
                                "placeholder": {"tag": "plain_text", "content": "例如 alice"},
                            },
                            {
                                "tag": "input",
                                "name": "tech_stack",
                                "required": False,
                                "width": "fill",
                                "input_type": "multiline_text",
                                "max_length": 500,
                                "label": {"tag": "plain_text", "content": "技术栈备注（选填，会写进 ARCHITECTURE.md）"},
                                "placeholder": {"tag": "plain_text", "content": "例如 FastAPI + PostgreSQL + Redis"},
                            },
                            {
                                "tag": "button",
                                "name": "submit_create_project",
                                "text": {"tag": "plain_text", "content": "提交"},
                                "type": "primary_filled",
                                "form_action_type": "submit",
                                "behaviors": [
                                    {
                                        "type": "callback",
                                        "value": {
                                            "action": "submit_create_project",
                                            "creator_chat_id": context.chat_id,
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                ]
            },
        }

    def _build_requirement_creation_card(self, context: MessageContext) -> dict[str, object]:
        provisioned_projects = sorted(
            name for name, cfg in self.service.project_configs.items()
            if cfg.bootstrap_status == "PROVISIONED"
        )
        project_options = [
            {"text": {"tag": "plain_text", "content": name}, "value": name}
            for name in provisioned_projects
        ]
        return {
            "schema": "2.0",
            "config": {"wide_screen_mode": True},
            "header": {
                "template": "blue",
                "title": {"tag": "plain_text", "content": "新建需求"},
                "subtitle": {"tag": "plain_text", "content": "提交后自动生成 REQ ID · 创建文档 · 写入表格 · 通知项目群"},
            },
            "body": {
                "elements": [
                    {
                        "tag": "form",
                        "name": "requirement_create_form",
                        "elements": [
                            {
                                "tag": "div",
                                "text": {"tag": "plain_text", "content": "项目（必填）"},
                            },
                            {
                                "tag": "select_static",
                                "name": "project",
                                "required": True,
                                "width": "fill",
                                "placeholder": {"tag": "plain_text", "content": "选择已就绪的项目"},
                                "options": project_options,
                            },
                            {
                                "tag": "input",
                                "name": "name",
                                "required": True,
                                "width": "fill",
                                "label": {"tag": "plain_text", "content": "需求名称"},
                                "placeholder": {"tag": "plain_text", "content": "例如 多轮需求构造工作流"},
                            },
                            {
                                "tag": "input",
                                "name": "summary",
                                "required": True,
                                "width": "fill",
                                "input_type": "multiline_text",
                                "max_length": 500,
                                "label": {"tag": "plain_text", "content": "需求简述"},
                                "placeholder": {"tag": "plain_text", "content": "要解决什么问题，期望得到什么结果"},
                            },
                            {
                                "tag": "input",
                                "name": "background_links",
                                "width": "fill",
                                "input_type": "multiline_text",
                                "max_length": 1000,
                                "label": {"tag": "plain_text", "content": "背景材料链接（选填）"},
                                "placeholder": {"tag": "plain_text", "content": "多个链接请换行"},
                            },
                            {
                                "tag": "column_set",
                                "horizontal_spacing": "8px",
                                "columns": [
                                    {
                                        "tag": "column",
                                        "width": "weighted",
                                        "weight": 1,
                                        "elements": [
                                            {"tag": "div", "text": {"tag": "plain_text", "content": "优先级"}},
                                            {
                                                "tag": "select_static",
                                                "name": "priority",
                                                "placeholder": {"tag": "plain_text", "content": "选填"},
                                                "options": [
                                                    {"text": {"tag": "plain_text", "content": "P0 紧急"}, "value": "P0"},
                                                    {"text": {"tag": "plain_text", "content": "P1 高"}, "value": "P1"},
                                                    {"text": {"tag": "plain_text", "content": "P2 普通"}, "value": "P2"},
                                                ],
                                            },
                                        ],
                                    },
                                    {
                                        "tag": "column",
                                        "width": "weighted",
                                        "weight": 1,
                                        "elements": [
                                            {"tag": "div", "text": {"tag": "plain_text", "content": "期望完成时间"}},
                                            {
                                                "tag": "date_picker",
                                                "name": "expected_due_date",
                                                "placeholder": {"tag": "plain_text", "content": "选填"},
                                            },
                                        ],
                                    },
                                    {
                                        "tag": "column",
                                        "width": "weighted",
                                        "weight": 1,
                                        "elements": [
                                            {"tag": "div", "text": {"tag": "plain_text", "content": "需要 UI 设计"}},
                                            {
                                                "tag": "select_static",
                                                "name": "needs_ui",
                                                "placeholder": {"tag": "plain_text", "content": "选填"},
                                                "options": [
                                                    {"text": {"tag": "plain_text", "content": "是"}, "value": "yes"},
                                                    {"text": {"tag": "plain_text", "content": "否"}, "value": "no"},
                                                ],
                                            },
                                        ],
                                    },
                                ],
                            },
                            {
                                "tag": "button",
                                "name": "submit_create_requirement",
                                "text": {"tag": "plain_text", "content": "提交"},
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
                        "tag": "div",
                        "text": {
                            "tag": "plain_text",
                            "content": "项目群和需求构造接手卡片已同步发送；接下来请在项目群里继续推进需求构造。",
                        },
                    },
                    self._build_button_columns(actions) if actions else {"tag": "hr"},
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
            body_elements.append(self._build_button_columns(top_actions))
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
                self._build_button_columns(primary_actions),
                {
                    "tag": "div",
                    "text": {
                        "tag": "plain_text",
                        "content": (
                            f"如果自动私发失败，请手动私聊 {self.settings.openclaw_author_agent_name}，"
                            "并发送完整启动消息。"
                        ),
                    },
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

    def _build_plan_author_handoff_text(self, requirement: Requirement) -> str:
        agent_name = self.settings.openclaw_plan_author_agent_name
        return (
            f"请私聊 {agent_name}，并发送以下完整上下文：\n\n"
            f"请开始 Plan 撰写 {requirement.req_id}\n"
            f"需求名称：{requirement.name}\n"
            f"需求文档：{requirement.document_url or '（待同步）'}"
        )

    def _build_spec_author_handoff_text(self, requirement: Requirement) -> str:
        spec_agent_name = self.settings.openclaw_spec_agent_name
        return (
            f"请私聊 {spec_agent_name}，并发送以下完整上下文：\n\n"
            f"请开始 Spec 撰写 {requirement.req_id}\n"
            f"需求名称：{requirement.name}\n"
            f"需求文档：{requirement.document_url or '（待同步）'}"
        )

    def _build_spec_review_handoff(self, requirement: Requirement) -> str:
        return (
            f"请开始 Spec 审查 {requirement.req_id}\n"
            f"需求名称：{requirement.name}\n"
            f"Spec 文档：{requirement.spec_document_url or '（创建中）'}\n"
            f"需求文档：{requirement.document_url or '（待同步）'}\n\n"
            f"请按 6+2+1 维度审查，单次上报 ai_review_pass 或 ai_review_reject。"
        )

    def _wake_spec_transform_agent(self, req_id: str, action: str) -> None:
        chat_id = self.settings.feishu_spec_transform_ops_chat_id
        if not chat_id:
            LOGGER.warning("FEISHU_SPEC_TRANSFORM_OPS_CHAT_ID not configured; skipping wake for %s", req_id)
            return

        orch = self.service.spec_orchestrator
        ctx = orch._rounds.get(req_id) if orch else None
        round_index = ctx.round_index if ctx else 1

        if action in ("wake_reviewer",):
            agent_name = self.settings.openclaw_spec_transformer_reviewer_agent_name
            text = f"请评审 Spec 转化产出 {req_id} (round={round_index})"
        elif action in (
            "wake_transformer",
            "wake_transformer_next_round",
            "wake_transformer_regression_retry",
            "soft_retry_transformer",
        ):
            agent_name = self.settings.openclaw_spec_transformer_agent_name
            suffix = ""
            if action == "wake_transformer_regression_retry":
                suffix = ", regression_retry"
            elif action == "soft_retry_transformer":
                suffix = ", soft_retry"
            text = f"请开始 Spec 转化 {req_id} (round={round_index}{suffix})"
        else:
            return

        try:
            self.gateway.send_text(chat_id, text, receive_id_type="chat_id")
            LOGGER.info("Woke %s for %s action=%s", agent_name, req_id, action)
        except Exception as exc:
            LOGGER.exception("Failed to wake %s for %s: %s", agent_name, req_id, exc)

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
        else:
            try:
                created_record = self.gateway.create_requirement_record(requirement)
                if created_record:
                    self.service.attach_bitable_record(requirement.req_id, created_record.record_id)
                    LOGGER.info("Backfilled bitable record for %s: %s", requirement.req_id, created_record.record_id)
            except Exception as exc:
                LOGGER.warning("Failed to backfill bitable record for %s: %s", requirement.req_id, exc)

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
        if hasattr(requirement, "spec_document_url") and requirement.spec_document_url and trigger == "spec_locked":
            links.append(f"[查看 Spec 文档]({requirement.spec_document_url})")
        if links:
            elements.append({"tag": "markdown", "content": " | ".join(links)})

        actions = self._build_transition_notification_actions(requirement, trigger=trigger)
        if actions:
            elements.append(self._build_button_columns(actions))

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

    def _build_button_columns(self, actions: list[dict[str, object]]) -> dict[str, object]:
        return {
            "tag": "column_set",
            "horizontal_spacing": "12px",
            "columns": [
                {
                    "tag": "column",
                    "width": "weighted",
                    "weight": 1,
                    "elements": [action],
                }
                for action in actions
            ],
        }

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
        if trigger == "final_review_passed":
            return [
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "开始 Plan 撰写"},
                    "type": "primary",
                    "value": {"action": "send_plan_author_start", "req_id": requirement.req_id},
                },
            ]
        if trigger == "spec_submitted":
            return [
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "开始 Spec 审查"},
                    "type": "primary",
                    "value": {"action": "send_spec_reviewer_start", "req_id": requirement.req_id},
                },
            ]
        if trigger == "spec_review_reject":
            return [
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "重新开始 Spec 撰写"},
                    "type": "default",
                    "value": {"action": "send_spec_author_start", "req_id": requirement.req_id},
                },
            ]
        if trigger == "plan_submitted_pending_review":
            return [
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "通过"},
                    "type": "primary",
                    "value": {"action": "approve_plan_submit", "req_id": requirement.req_id},
                },
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "需要修改"},
                    "type": "default",
                    "value": {"action": "reject_plan_submit", "req_id": requirement.req_id},
                },
            ]
        if trigger == "plan_ready":
            return [
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "开始 Spec 撰写"},
                    "type": "primary",
                    "value": {"action": "send_spec_author_start", "req_id": requirement.req_id},
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
            plan_agent_name = self.settings.openclaw_plan_author_agent_name
            return (
                "green",
                f"{requirement.req_id} 已批准通过",
                latest_review,
                "正式审查已通过，需求进入 Plan 撰写阶段。",
                f"请点击「开始 Plan 撰写」，将启动指令私发给自己后转发给 {plan_agent_name}。",
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
        if trigger == "spec_submitted":
            spec_reviewer_name = self.settings.openclaw_spec_agent_name
            return (
                "indigo",
                f"{requirement.req_id} Spec 已提交，待审查",
                "Spec Agent 已完成 9 节 Spec 文档撰写。",
                "Spec 文档已提交，等待 Spec Reviewer 按 6+2+1 维度审查。",
                f"请点击「开始 Spec 审查」，将审查启动指令私发给自己后转发给 Spec Reviewer。",
            )
        if trigger == "spec_locked":
            return (
                "green",
                f"{requirement.req_id} Spec 已锁定",
                requirement.spec_review_summary or "Spec Reviewer 审查通过",
                "Spec 文档已锁定，可进入 Harness 生成阶段（卡点1a）。",
                "无需操作，流程自动继续。",
            )
        if trigger == "spec_review_reject":
            return (
                "orange",
                f"{requirement.req_id} Spec 审查未通过",
                requirement.spec_review_summary or "Spec 需要修改",
                "Spec Reviewer 判定当前文档未达到标准，已通知 Spec Agent 修改。",
                "等待 Spec Agent 修改后重新提交。",
            )
        if trigger == "plan_submitted_pending_review":
            return (
                "indigo",
                f"{requirement.req_id} Plan 已提交，待审查",
                "Plan Author 已完成 plan.md 终稿提交。",
                "Plan 文档已进入最终审查阶段，等待需求提出者裁决。",
                "请 review plan.md 内容后，点击「通过」提交 PR，或「需要修改」驳回重写。",
            )
        if trigger == "plan_ready":
            spec_agent_name = self.settings.openclaw_spec_agent_name
            return (
                "green",
                f"{requirement.req_id} Plan 已通过",
                f"Plan PR：{requirement.plan_pr_url or '（创建中）'}",
                "Plan 已合并至项目仓库，需求进入 Spec 撰写阶段。",
                f"请点击「开始 Spec 撰写」，将启动指令私发给自己后转发给 {spec_agent_name}。",
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
