from __future__ import annotations

import concurrent.futures
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
from .coordinator_service import CoordinatorService
from .feishu_gateway import FeishuGateway
from .models import DISCUSSION_FIELDS, Requirement, ReviewFinding, ReviewResult, WorkflowStatus
from .project_bootstrapper import ProjectBootstrapper
from .project_config import OnboardingState, ProjectConfig
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
        requirements, active_req_by_user, project_groups, project_configs = self.store.load_snapshot()
        if service is None or requirements or active_req_by_user or project_groups:
            self.service.restore_snapshot(requirements, active_req_by_user, project_groups, project_configs)
        self._health_server: HTTPServer | None = None
        self._observed_creation_group_chat_id = settings.creation_group_chat_id
        self._pending_onboarding_project: dict[str, str] = {}   # user_id → project
        self._pending_requirement_info: dict[str, dict] = {}    # user_id → creation args

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
        # If user is mid-onboarding, route their reply to the onboarding handler
        pending_project = self._pending_onboarding_project.get(context.user_id)
        if pending_project:
            return self._handle_onboarding_reply(context, pending_project)

        if "创建需求" not in context.text and "新建需求" not in context.text:
            return []

        self._observed_creation_group_chat_id = context.chat_id
        parsed = self._parse_creation_command(context.text)
        if parsed is None:
            return [OutboundMessage(
                receive_id=context.chat_id,
                text="格式：新建需求 [项目名] [需求名] [简述]（可加 --ui 标记表示需要UI设计）",
            )]

        project, name, summary, needs_ui = parsed

        if self.service.is_new_project(project):
            self._pending_onboarding_project[context.user_id] = project
            self._pending_requirement_info[context.user_id] = {
                "project": project,
                "name": name,
                "summary": summary,
                "needs_ui": needs_ui,
                "creator": context.sender_name,
                "creator_user_id": context.user_id,
                "creation_chat_id": context.chat_id,
            }
            return [OutboundMessage(
                receive_id=context.chat_id,
                text=(
                    f"检测到 {project} 是新项目，需要先完成项目初始化（3 个问题）。\n\n"
                    "问题 1/3：GitHub 仓库地址？\n（格式：https://github.com/org/repo）"
                ),
            )]

        # Existing project → normal card-based creation flow
        return [OutboundCard(receive_id=context.chat_id, card=self._build_requirement_creation_card(context))]

    # ── Onboarding conversation ───────────────────────────────────────────────

    @staticmethod
    def _parse_creation_command(text: str) -> tuple[str, str, str, bool] | None:
        needs_ui = "--ui" in text
        clean = text.replace("--ui", "").strip()
        m = re.match(r"(?:新建需求|创建需求)\s+(\S+)\s+(\S+)\s+(.+)", clean)
        if not m:
            return None
        return m.group(1), m.group(2), m.group(3).strip(), needs_ui

    @staticmethod
    def _parse_tech_stack(text: str) -> dict[str, str]:
        parts = [p.strip() for p in re.split(r"[/,；;、]", text) if p.strip()]
        keys = ["language", "framework", "database", "test_framework"]
        return {keys[i]: parts[i] for i in range(min(len(keys), len(parts)))}

    def _handle_onboarding_reply(self, context: MessageContext, project: str) -> list[OutboundMessage]:
        cfg = self.service.project_configs.get(project)
        state = cfg.onboarding_state if cfg else OnboardingState.COLLECTING_REPO
        text = context.text.strip()

        if state == OnboardingState.COLLECTING_REPO or cfg is None:
            return self._onboarding_collect_repo(context, project, text)
        if state == OnboardingState.COLLECTING_PROJECT_TYPE:
            return self._onboarding_collect_project_type(context, project, text)
        if state == OnboardingState.COLLECTING_TECH_STACK:
            return self._onboarding_collect_tech_stack(context, project, text)
        if state == OnboardingState.WAITING_ARCH_CONFIRMATION:
            return self._onboarding_wait_arch_confirmation(context, project, text)
        return []

    def _onboarding_collect_repo(self, context: MessageContext, project: str, text: str) -> list[OutboundMessage]:
        if not re.match(r"https://github\.com/[\w.\-]+/[\w.\-]+", text):
            return [OutboundMessage(
                receive_id=context.chat_id,
                text="格式不正确，请提供 GitHub 仓库地址（https://github.com/org/repo）",
            )]
        self.service.register_project_config(project, text, True, {})
        return [OutboundMessage(
            receive_id=context.chat_id,
            text=(
                "问题 2/3：全新项目还是已有代码库？\n"
                "A. 全新项目（从零开始，无现有代码）\n"
                "B. 已有代码库（需先运行初始化脚本生成 ARCHITECTURE.yaml）"
            ),
        )]

    def _onboarding_collect_project_type(self, context: MessageContext, project: str, text: str) -> list[OutboundMessage]:
        upper = text.upper()
        if "A" in upper or "全新" in upper:
            self.service.set_project_type(project, is_new_project=True)
        elif "B" in upper or "已有" in upper or "代码" in upper:
            self.service.set_project_type(project, is_new_project=False)
        else:
            return [OutboundMessage(
                receive_id=context.chat_id,
                text="请回复 A（全新项目）或 B（已有代码库）",
            )]
        self.service.advance_onboarding_state(project, OnboardingState.COLLECTING_TECH_STACK)
        return [OutboundMessage(
            receive_id=context.chat_id,
            text="问题 3/3：技术栈？\n（如：Python/FastAPI/PostgreSQL/pytest）",
        )]

    def _onboarding_collect_tech_stack(self, context: MessageContext, project: str, text: str) -> list[OutboundMessage]:
        tech_stack = self._parse_tech_stack(text)
        self.service.set_tech_stack(project, tech_stack)
        cfg = self.service.project_configs[project]

        if not cfg.is_new_project:
            self.service.advance_onboarding_state(project, OnboardingState.WAITING_ARCH_CONFIRMATION)
            return [OutboundMessage(
                receive_id=context.chat_id,
                text=(
                    "已有代码库需先生成架构快照，请运行：\n\n"
                    f"  python scripts/bootstrap_architecture.py --repo {cfg.github_repo_url}\n\n"
                    "完成后回复「初始化完成」继续。"
                ),
            )]

        # Path C: new project → async bootstrap
        self.service.advance_onboarding_state(project, OnboardingState.BOOTSTRAPPING)
        threading.Thread(
            target=self._run_bootstrap_new_project,
            args=(context, project),
            daemon=True,
        ).start()
        return [OutboundMessage(
            receive_id=context.chat_id,
            text="信息收集完成，正在初始化项目上下文，请稍候…",
        )]

    def _onboarding_wait_arch_confirmation(self, context: MessageContext, project: str, text: str) -> list[OutboundMessage]:
        if "完成" not in text:
            return [OutboundMessage(
                receive_id=context.chat_id,
                text="请运行完脚本后回复「初始化完成」",
            )]
        cfg = self.service.project_configs[project]
        bootstrapper = self._make_bootstrapper()
        if not bootstrapper.verify_architecture_yaml_exists(cfg.github_repo_url):
            return [OutboundMessage(
                receive_id=context.chat_id,
                text="未检测到 ARCHITECTURE.yaml，请确认脚本运行成功后重试。",
            )]
        self.service.advance_onboarding_state(project, OnboardingState.BOOTSTRAPPING)
        threading.Thread(
            target=self._run_bootstrap_existing_project,
            args=(context, project),
            daemon=True,
        ).start()
        return [OutboundMessage(
            receive_id=context.chat_id,
            text="已确认，正在完成剩余初始化（ACM 注册表）…",
        )]

    def _run_bootstrap_new_project(self, context: MessageContext, project: str) -> None:
        cfg = self.service.project_configs[project]
        try:
            bootstrapper = self._make_bootstrapper()
            bootstrapper.bootstrap_new_project(
                repo_url=cfg.github_repo_url,
                project=project,
                tech_stack=cfg.tech_stack,
            )
            self.service.complete_onboarding(project, architecture_initialized=True, acm_initialized=True)
        except Exception as exc:
            LOGGER.error("Bootstrap failed for project=%s: %s", project, exc)
            self.gateway.send_text(context.chat_id, f"项目初始化失败：{exc}\n请检查 GitHub Token 权限后重试。")
            return
        finally:
            self._save_state()
            self._pending_onboarding_project.pop(context.user_id, None)
        self._finish_onboarding(context, project)

    def _run_bootstrap_existing_project(self, context: MessageContext, project: str) -> None:
        cfg = self.service.project_configs[project]
        try:
            bootstrapper = self._make_bootstrapper()
            from github import Github
            repo_path = bootstrapper._repo_path_from_url(cfg.github_repo_url)
            g = Github(self.settings.github_token)
            repo = g.get_repo(repo_path)
            acm_yaml = bootstrapper.render_acm_registry_yaml()
            bootstrapper._create_file_if_missing(
                repo,
                path="spec/registry/consolidated.yaml",
                content=acm_yaml,
                commit_message="chore: initialize ACM registry",
            )
            self.service.complete_onboarding(project, architecture_initialized=True, acm_initialized=True)
        except Exception as exc:
            LOGGER.error("Bootstrap (existing) failed for project=%s: %s", project, exc)
            self.gateway.send_text(context.chat_id, f"ACM 注册表初始化失败：{exc}")
            return
        finally:
            self._save_state()
            self._pending_onboarding_project.pop(context.user_id, None)
        self._finish_onboarding(context, project)

    def _finish_onboarding(self, context: MessageContext, project: str) -> None:
        req_info = self._pending_requirement_info.pop(context.user_id, None)
        self.gateway.send_text(
            context.chat_id,
            f"{project} 初始化完成 ✓\n"
            "· ARCHITECTURE.yaml 已就绪\n"
            "· ACM 注册表已就绪（spec/registry/consolidated.yaml）\n\n"
            "正在创建需求，稍后通知 Author 进入讨论…",
        )
        if req_info is None:
            return
        request = CreationRequest(
            project=req_info["project"],
            name=req_info["name"],
            summary=req_info["summary"],
            creator=req_info["creator"],
            creator_user_id=req_info["creator_user_id"],
            creation_chat_id=req_info["creation_chat_id"],
        )
        response = self.service.create_requirement_from_group(request)
        requirement = self.service.get_requirement(response.req_id)
        if requirement is not None:
            requirement.needs_ui = req_info.get("needs_ui", False)
            requirement.github_repo_url = self.service.project_configs[project].github_repo_url
        self._save_state()
        threading.Thread(
            target=self._provision_requirement_after_creation,
            args=(request, response.req_id),
            daemon=True,
        ).start()

    def _make_bootstrapper(self) -> ProjectBootstrapper:
        return ProjectBootstrapper(
            github_token=self.settings.github_token,
            default_branch=self.settings.github_default_branch,
        )

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
        self._save_state()
        if requirement is not None:
            LOGGER.info(
                "Accepted requirement creation from form req_id=%s status=%s project=%s creator_user_id=%s",
                requirement.req_id,
                requirement.status.value,
                requirement.project,
                requirement.creator_user_id,
            )
        return request, requirement, response.req_id

    def _provision_requirement_after_creation(self, request: CreationRequest, req_id: str) -> None:
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
