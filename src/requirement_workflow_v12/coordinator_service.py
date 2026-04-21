from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from typing import Callable

from .models import DISCUSSION_FIELDS, DiscussionTurn, HumanReviewResult, Requirement, ReviewResult, WorkflowStatus, utc_now
from .project_config import ProjectConfig
from .protocols import (
    AgentAuthorEventPayload,
    AgentRequirementContextQuery,
    AgentReviewEventPayload,
    AuthorStartBinding,
    AuthorStartResponse,
    CreationRequest,
    CreationResponse,
)
from .plan_state_machine import (
    DesignEvent, PlanEvent, PlanPhase, PlanStatus,
    apply_design_event, apply_plan_event,
)
from .project_repo import PlanArtifacts
from .spec_state_machine import SpecEvent, SpecStatus, apply_spec_event
from .state_machine import Event, apply_event


LOGGER = logging.getLogger(__name__)

FIELD_HINTS: dict[str, str] = {
    "输入": "列举每个入参的字段名、类型、约束，例：license_image: File(jpg/png, max 5MB)",
    "输出": "列举每个出参的字段名、类型、示例值，例：risk_level: str('low'|'medium'|'high')",
    "验收标准": "每条写为可测试断言：Given [前置条件], When [动作], Then [期望结果]",
    "技术范围声明": "说明影响哪些模块/API/数据表，以及明确不包含什么",
}

AUTHOR_EVENT_ALIASES = {
    "author_ready_for_ai_review": "author_submit",
}

REVIEW_EVENT_ALIASES = {
    "review_returned_for_revision": "ai_review_reject",
    "review_ready_for_human_confirmation": "ai_review_pass",
}


class CoordinatorService:
    """Independent backend coordinator for Feishu events and workflow state."""

    def __init__(self) -> None:
        from .project_repo import StateTransitionHooks
        self.project_groups: dict[str, str] = {}
        self.requirements: dict[str, Requirement] = {}
        self.active_req_by_user: dict[str, str] = {}
        self.project_configs: dict[str, ProjectConfig] = {}
        self._project_config_persister: Callable[[str, ProjectConfig], ProjectConfig] | None = None
        self.spec_orchestrator = None
        self._acm_registry = None
        self._hooks = StateTransitionHooks()

    def set_project_config_persister(
        self, persister: Callable[[str, ProjectConfig], ProjectConfig] | None
    ) -> None:
        self._project_config_persister = persister

    def _persist_project_config(self, project: str) -> None:
        if self._project_config_persister is None:
            return
        cfg = self.project_configs.get(project)
        if cfg is None:
            return
        self._project_config_persister(project, cfg)

    def restore_snapshot(
        self,
        requirements: dict[str, Requirement],
        active_req_by_user: dict[str, str],
        project_groups: dict[str, str],
        project_configs: dict[str, ProjectConfig] | None = None,
    ) -> None:
        self.requirements = requirements
        self.active_req_by_user = active_req_by_user
        self.project_groups = project_groups
        self.project_configs = project_configs or {}

    # ── Project initialization ────────────────────────────────────────────

    def get_project_config(self, project: str) -> ProjectConfig | None:
        return self.project_configs.get(project)

    def initialize_project(
        self,
        *,
        project: str,
        category: str,
        template_version: str,
        architecture_doc_id: str,
        architecture_doc_url: str,
        tech_stack: dict[str, str],
    ) -> ProjectConfig:
        if project in self.project_configs:
            raise ValueError(f"project already initialized: {project}")
        cfg = ProjectConfig(
            category=category,
            template_version=template_version,
            architecture_doc_id=architecture_doc_id,
            architecture_doc_url=architecture_doc_url,
            tech_stack=dict(tech_stack),
        )
        self.project_configs[project] = cfg
        self._persist_project_config(project)
        return cfg

    def set_design_system_doc(self, project: str, doc_id: str) -> None:
        if project in self.project_configs:
            self.project_configs[project].design_system_doc_id = doc_id
            self._persist_project_config(project)

    def should_create_design_system(self, project: str) -> bool:
        cfg = self.project_configs.get(project)
        if cfg is None:
            return False
        return cfg.design_system_doc_id is None

    def _has_concurrent_spec(self, project: str, *, exclude_req_id: str) -> bool:
        for req in self.requirements.values():
            if (
                req.project == project
                and req.req_id != exclude_req_id
                and req.spec_status == SpecStatus.DRAFTING
            ):
                return True
        return False

    def get_requirement(self, req_id: str) -> Requirement | None:
        return self.requirements.get(req_id)

    def assign_project_group(self, req_id: str, project_group_id: str) -> Requirement:
        requirement = self.requirements[req_id]
        requirement.project_group_id = project_group_id
        self.project_groups[requirement.project] = project_group_id
        requirement.touch()
        LOGGER.info("Assigned project group req_id=%s project_group_id=%s", req_id, project_group_id)
        return requirement

    def attach_bitable_record(self, req_id: str, record_id: str) -> Requirement:
        requirement = self.requirements[req_id]
        requirement.bitable_record_id = record_id
        requirement.touch()
        LOGGER.info("Attached bitable record req_id=%s record_id=%s", req_id, record_id)
        return requirement

    def attach_document(self, req_id: str, document_id: str, document_url: str) -> Requirement:
        requirement = self.requirements[req_id]
        requirement.document_id = document_id
        requirement.document_url = document_url
        requirement.touch()
        LOGGER.info("Attached document req_id=%s document_id=%s document_url=%s", req_id, document_id, document_url)
        return requirement

    def create_requirement_from_group(self, request: CreationRequest) -> CreationResponse:
        req_id = self._next_req_id(request.project)
        project_group_id = self.project_groups.setdefault(request.project, f"project-group:{request.project}")
        requirement = Requirement(
            req_id=req_id,
            name=request.name,
            project=request.project,
            summary=request.summary,
            creator=request.creator,
            creator_user_id=request.creator_user_id,
            creation_chat_id=request.creation_chat_id,
            project_group_id=project_group_id,
        )
        requirement = self.initialize_requirement(requirement)
        self.requirements[req_id] = requirement
        LOGGER.info(
            "Created requirement req_id=%s project=%s status=%s creator_user_id=%s",
            req_id,
            request.project,
            requirement.status.value,
            request.creator_user_id,
        )

        start_command = f"开始需求构造 {req_id}"
        creation_message = (
            f"{req_id} 已创建\n"
            f"项目：{request.project}\n"
            f"需求文档入口已准备，后续由需求构造 Agent 持续撰写\n"
            f"请私聊需求构造 Agent，并发送：\n{start_command}"
        )
        project_message = (
            f"{req_id} 已创建\n"
            f"名称：{request.name}\n"
            f"当前状态：{requirement.status.value}\n"
            f"后续需求构造将在 author 私聊中进行；本群用于同步状态与最终结果。"
        )
        return CreationResponse(
            req_id=req_id,
            project_group_id=project_group_id,
            message_to_creation_group=creation_message,
            message_to_project_group=project_message,
            author_start_command=start_command,
        )

    def start_author_private_session(self, binding: AuthorStartBinding) -> AuthorStartResponse:
        requirement = self.requirements.get(binding.req_id)
        if requirement is None:
            return AuthorStartResponse(accepted=False, message=f"未知需求：{binding.req_id}")

        if requirement.creator_user_id and requirement.creator_user_id != binding.user_id:
            return AuthorStartResponse(
                accepted=False,
                message=f"{binding.req_id} 的创建人与当前私聊用户不一致，不能直接接手。",
            )

        requirement.author_dm_chat_id = binding.author_dm_chat_id
        requirement.active_private_binding_confirmed = False
        self.active_req_by_user[binding.user_id] = requirement.req_id
        requirement.current_owner = "author"
        requirement.current_role_label = "需求构造Agent"
        requirement.touch()
        LOGGER.info(
            "Started author private session req_id=%s user_id=%s chat_id=%s status=%s",
            requirement.req_id,
            binding.user_id,
            binding.author_dm_chat_id,
            requirement.status.value,
        )
        return AuthorStartResponse(
            accepted=True,
            active_req_id=requirement.req_id,
            message=(
                "我已收到需求构造请求。\n\n"
                f"请确认：\n- 需求ID：{requirement.req_id}\n- 项目：{requirement.project}\n- 名称：{requirement.name}\n\n"
                "如果无误，请回复：\n确认开始"
            ),
        )

    def confirm_author_private_binding(self, user_id: str, message_text: str) -> AuthorStartResponse:
        req_id = self.active_req_by_user.get(user_id)
        if not req_id:
            return AuthorStartResponse(accepted=False, message="当前没有激活的需求，请先发送“开始需求构造 REQ-ID”。")

        requirement = self.requirements[req_id]
        if message_text.strip() != "确认开始":
            return AuthorStartResponse(
                accepted=False,
                active_req_id=req_id,
                message="如信息无误，请直接回复“确认开始”。",
            )

        requirement.active_private_binding_confirmed = True
        requirement.latest_question = "请先说明这个需求当前要解决的核心问题，以及不解决会造成什么影响。"
        requirement.touch()
        LOGGER.info("Confirmed author private binding req_id=%s user_id=%s", requirement.req_id, user_id)
        return AuthorStartResponse(
            accepted=True,
            active_req_id=req_id,
            message=f"我已正式接手 {req_id}。\n\n{requirement.latest_question}",
        )

    def switch_active_requirement(self, user_id: str, req_id: str) -> AuthorStartResponse:
        requirement = self.requirements.get(req_id)
        if requirement is None:
            return AuthorStartResponse(accepted=False, message=f"未知需求：{req_id}")
        if requirement.creator_user_id and requirement.creator_user_id != user_id:
            return AuthorStartResponse(
                accepted=False,
                message=f"{req_id} 的创建人与当前私聊用户不一致，不能直接切换。",
            )
        self.active_req_by_user[user_id] = req_id
        requirement.active_private_binding_confirmed = True
        requirement.touch()
        LOGGER.info("Switched active requirement user_id=%s req_id=%s", user_id, req_id)
        return AuthorStartResponse(
            accepted=True,
            active_req_id=req_id,
            message=f"当前已切换到 {req_id}。\n\n{requirement.latest_question or '请继续补充当前需求。'}",
        )

    def initialize_requirement(self, requirement: Requirement) -> Requirement:
        decision = apply_event(requirement.status, Event.CREATE_REQUIREMENT)
        if not decision.allowed:
            raise ValueError(decision.message)

        requirement.status = decision.next_status
        requirement.current_phase = "需求构造"
        requirement.current_round = 0
        requirement.current_discussion_field = DISCUSSION_FIELDS[0]
        requirement.completed_fields = []
        requirement.pending_fields = list(DISCUSSION_FIELDS)
        requirement.current_owner = "author"
        requirement.current_role_label = "需求构造Agent"
        requirement.ai_ready = False
        requirement.human_confirmed = False
        requirement.latest_review_summary = ""
        requirement.latest_question = "请先澄清问题本质，我们会逐轮完成需求构造。"
        requirement.touch()
        LOGGER.info("Initialized requirement req_id=%s status=%s phase=%s", requirement.req_id, requirement.status.value, requirement.current_phase)
        return requirement

    def handoff_to_author(self, requirement: Requirement) -> Requirement:
        requirement.current_owner = "author"
        requirement.current_role_label = "需求构造Agent"
        requirement.touch()
        LOGGER.info("Prepared author ownership req_id=%s status=%s", requirement.req_id, requirement.status.value)
        return requirement

    def handle_review_result(self, requirement: Requirement, result: ReviewResult) -> Requirement:
        if requirement.status == WorkflowStatus.DRAFTING:
            author_submit = apply_event(requirement.status, Event.AUTHOR_SUBMIT)
            if not author_submit.allowed:
                raise ValueError(author_submit.message)
            requirement.status = author_submit.next_status
        event = Event.AI_REVIEW_PASS if result.ready_for_human_confirmation else Event.AI_REVIEW_REJECT
        decision = apply_event(requirement.status, event)
        if not decision.allowed:
            raise ValueError(decision.message)

        requirement.status = decision.next_status
        requirement.review_history.append(result)
        requirement.latest_review_summary = result.summary
        requirement.ai_ready = result.ready_for_human_confirmation
        if requirement.discussion_history:
            latest_turn = requirement.discussion_history[-1]
            latest_turn.review_summary = result.summary
            latest_turn.ai_ready_after_review = result.ready_for_human_confirmation
            if result.next_focus:
                latest_turn.next_question = result.next_focus

        if result.ready_for_human_confirmation:
            requirement.current_phase = "人工确认"
            requirement.current_owner = "human"
            requirement.current_role_label = "人工确认"
            requirement.latest_question = "AI 评审已通过，请确认当前需求是否准确表达你的意图。"
        else:
            requirement.current_phase = "需求构造"
            requirement.current_owner = "author"
            requirement.current_role_label = "需求构造Agent"
            requirement.latest_question = result.next_focus or requirement.latest_question

        requirement.touch()
        return requirement

    def submit_author_event_payload(self, payload: AgentAuthorEventPayload) -> Requirement:
        requirement = self.requirements.get(payload.req_id)
        if requirement is None:
            raise ValueError(f"未知需求：{payload.req_id}")
        event_name = AUTHOR_EVENT_ALIASES.get(payload.event, payload.event)
        if event_name != "author_submit":
            raise ValueError(f"不支持的 author 事件：{payload.event}")
        decision = apply_event(requirement.status, Event.AUTHOR_SUBMIT)
        if not decision.allowed:
            raise ValueError(decision.message)

        requirement.status = decision.next_status
        requirement.current_phase = "AI Review"
        requirement.current_owner = "reviewer"
        requirement.current_role_label = "需求审查Agent"
        requirement.latest_review_summary = payload.summary
        requirement.latest_question = "需求已提交 AI review，请由 review agent 与需求提出者完成审查。"
        if payload.completed_fields:
            requirement.completed_fields = list(payload.completed_fields)
            requirement.pending_fields = [
                f for f in DISCUSSION_FIELDS
                if f not in requirement.completed_fields
            ]
            if requirement.pending_fields:
                requirement.current_discussion_field = requirement.pending_fields[0]
        if payload.document_url:
            requirement.document_url = payload.document_url
        if payload.iteration_round is not None:
            requirement.current_round = payload.iteration_round
        requirement.latest_writeback_at = utc_now()
        requirement.touch()
        LOGGER.info(
            "Accepted author event req_id=%s event=%s status=%s round=%s document_url=%s",
            requirement.req_id,
            event_name,
            requirement.status.value,
            requirement.current_round,
            requirement.document_url,
        )
        return requirement

    def submit_review_event_payload(self, payload: AgentReviewEventPayload) -> Requirement:
        requirement = self.requirements.get(payload.req_id)
        if requirement is None:
            raise ValueError(f"未知需求：{payload.req_id}")
        event_name = REVIEW_EVENT_ALIASES.get(payload.event, payload.event)

        supported_events = {
            "ai_review_reject",
            "ai_review_pass",
        }
        if event_name not in supported_events:
            raise PermissionError(
                "review callback 只允许 reviewer 上报 AI review 结论："
                "`ai_review_reject` 或 `ai_review_pass`。"
                "人工确认和正式审查必须由 Coordinator 的人工操作入口推进。"
            )

        if payload.document_url:
            requirement.document_url = payload.document_url
        requirement.latest_writeback_at = utc_now()

        if requirement.spec_status == SpecStatus.DRAFTING:
            # Spec layer review branch — 走 spec 子状态机，不动 requirement.status
            if event_name == "ai_review_pass":
                requirement.spec_review_summary = payload.review_summary
                cfg = self.project_configs.get(requirement.project)
                can_transform = (
                    self.spec_orchestrator is not None
                    and cfg is not None
                    and cfg.github_repo_url
                )
                if can_transform:
                    self.submit_checkpoint_1a_pass(requirement.req_id)
                    requirement.current_phase = "Spec 转化中"
                    requirement.current_owner = "spec-transformer"
                    requirement.current_role_label = "Spec 转化 Agent"
                else:
                    decision = apply_spec_event(requirement.spec_status, SpecEvent.SPEC_REVIEW_PASS)
                    if not decision.allowed:
                        raise ValueError(decision.message)
                    requirement.spec_status = decision.next_status
                    requirement.current_phase = "Spec 已锁定"
                    requirement.current_owner = "coordinator-service"
                    requirement.current_role_label = "需求协调服务"
            else:  # ai_review_reject
                decision = apply_spec_event(requirement.spec_status, SpecEvent.SPEC_REVIEW_REJECT)
                if not decision.allowed:
                    raise ValueError(decision.message)
                requirement.spec_status = decision.next_status
                requirement.spec_review_summary = payload.review_summary
                requirement.current_phase = "Spec 撰写"
                requirement.current_owner = "spec-agent"
                requirement.current_role_label = "Spec 撰写 Agent"
        elif requirement.status == WorkflowStatus.AI_REVIEW:
            # Requirement layer review branch (original logic)
            requirement.latest_review_summary = payload.review_summary
            if event_name == "ai_review_reject":
                decision = apply_event(requirement.status, Event.AI_REVIEW_REJECT)
                if not decision.allowed:
                    raise ValueError(decision.message)
                requirement.status = decision.next_status
                requirement.current_phase = "需求构造"
                requirement.current_owner = "author"
                requirement.current_role_label = "需求构造Agent"
                requirement.ai_ready = False
                requirement.human_confirmed = False
                requirement.latest_question = payload.review_summary
            elif event_name == "ai_review_pass":
                decision = apply_event(requirement.status, Event.AI_REVIEW_PASS)
                if not decision.allowed:
                    raise ValueError(decision.message)
                requirement.status = decision.next_status
                requirement.current_phase = "人工确认"
                requirement.current_owner = "human"
                requirement.current_role_label = "人工确认"
                requirement.ai_ready = True
                requirement.latest_question = "AI review 已通过，请进行人工确认。"
        else:
            raise ValueError(
                f"当前状态 status={requirement.status.value} "
                f"spec_status={requirement.spec_status.value if requirement.spec_status else 'None'} "
                "不支持 review 事件。review callback 只能在 requirement.status=AI_REVIEW "
                "或 requirement.spec_status=SPEC_DRAFTING 时使用。"
            )

        requirement.touch()
        LOGGER.info(
            "Accepted review event req_id=%s event=%s status=%s phase=%s ai_ready=%s human_confirmed=%s",
            requirement.req_id,
            event_name,
            requirement.status.value,
            requirement.current_phase,
            requirement.ai_ready,
            requirement.human_confirmed,
        )
        return requirement

    def get_agent_requirement_context(self, payload: AgentRequirementContextQuery) -> dict[str, object]:
        requirement = self.requirements.get(payload.req_id)
        if requirement is None:
            raise ValueError(f"未知需求：{payload.req_id}")
        LOGGER.info(
            "Served requirement context req_id=%s status=%s phase=%s round=%s document_url=%s",
            requirement.req_id,
            requirement.status.value,
            requirement.current_phase,
            requirement.current_round,
            requirement.document_url,
        )

        return {
            "req_id": requirement.req_id,
            "name": requirement.name,
            "project": requirement.project,
            "summary": requirement.summary,
            "creator": requirement.creator,
            "status": requirement.status.value,
            "current_phase": requirement.current_phase,
            "current_owner": requirement.current_owner,
            "current_role_label": requirement.current_role_label,
            "current_round": requirement.current_round,
            "current_discussion_field": requirement.current_discussion_field,
            "completed_fields": list(requirement.completed_fields),
            "pending_fields": list(requirement.pending_fields),
            "ai_ready": requirement.ai_ready,
            "human_confirmed": requirement.human_confirmed,
            "latest_review_summary": requirement.latest_review_summary,
            "latest_question": requirement.latest_question,
            "document_url": requirement.document_url,
            "bitable_record_id": requirement.bitable_record_id,
            "project_group_id": requirement.project_group_id,
            "review_history": [
                {
                    "summary": review.summary,
                    "ready_for_human_confirmation": review.ready_for_human_confirmation,
                    "reviewed_at": review.reviewed_at.isoformat(),
                }
                for review in requirement.review_history[-5:]
            ],
            "human_review_history": [
                {
                    "approved": review.approved,
                    "summary": review.summary,
                    "reviewed_at": review.reviewed_at.isoformat(),
                }
                for review in requirement.human_review_history[-5:]
            ],
            "discussion_history": [
                {
                    "round_number": turn.round_number,
                    "focused_field": turn.focused_field,
                    "review_summary": turn.review_summary,
                    "next_question": turn.next_question,
                    "created_at": turn.created_at.isoformat(),
                }
                for turn in requirement.discussion_history[-5:]
            ],
            "field_hints": FIELD_HINTS,
            "latest_writeback_at": requirement.latest_writeback_at.isoformat()
            if requirement.latest_writeback_at
            else "",
            "updated_at": requirement.updated_at.isoformat(),
            "spec_document_id": requirement.spec_document_id,
            "spec_document_url": requirement.spec_document_url,
            "spec_review_summary": requirement.spec_review_summary,
        }

    def handle_human_confirmation(self, requirement: Requirement, approved: bool) -> Requirement:
        event = Event.HUMAN_CONFIRM_YES if approved else Event.HUMAN_CONFIRM_NO
        decision = apply_event(requirement.status, event, ai_ready=requirement.ai_ready)
        if not decision.allowed:
            raise ValueError(decision.message)

        requirement.status = decision.next_status
        requirement.human_confirmed = approved
        review_summary = "人工确认通过，需求表达与预期一致。" if approved else "人工确认未通过，需求仍需继续打磨。"
        requirement.human_review_history.append(HumanReviewResult(approved=approved, summary=review_summary))
        if approved:
            requirement.current_phase = "正式审查"
            requirement.current_owner = "review"
            requirement.current_role_label = "正式审查"
            requirement.latest_question = "需求构造完成，可进入正式审查。"
        else:
            requirement.current_phase = "需求构造"
            requirement.current_owner = "author"
            requirement.current_role_label = "需求构造Agent"
            requirement.ai_ready = False
            requirement.latest_question = "请继续补充或修正需求内容，然后我们会再进行一轮 AI review。"

        requirement.touch()
        LOGGER.info(
            "Handled human confirmation req_id=%s approved=%s status=%s phase=%s",
            requirement.req_id,
            approved,
            requirement.status.value,
            requirement.current_phase,
        )
        return requirement

    def approve_requirement(self, requirement: Requirement) -> Requirement:
        decision = apply_event(
            requirement.status,
            Event.FINAL_REVIEW_PASS,
            human_confirmed=requirement.human_confirmed,
        )
        if not decision.allowed:
            raise ValueError(decision.message)

        requirement.status = decision.next_status
        requirement.current_phase = "需求已批准"
        requirement.current_owner = "coordinator-service"
        requirement.current_role_label = "需求协调服务"
        requirement.latest_question = f"需求已批准，建议后续分支名为 spec/{requirement.req_id}。"
        requirement.touch()
        LOGGER.info("Approved requirement req_id=%s status=%s", requirement.req_id, requirement.status.value)
        return requirement

    def submit_spec_start(
        self,
        req_id: str,
        *,
        spec_document_id: str,
        spec_document_url: str,
    ) -> Requirement:
        requirement = self.requirements.get(req_id)
        if requirement is None:
            raise ValueError(f"未知需求：{req_id}")
        if requirement.status != WorkflowStatus.APPROVED:
            raise ValueError(
                f"spec_start 需要 requirement.status=APPROVED，当前：{requirement.status.value}"
            )
        decision = apply_spec_event(requirement.spec_status, SpecEvent.SPEC_START)
        if not decision.allowed:
            raise ValueError(decision.message)
        requirement.spec_status = decision.next_status
        requirement.spec_document_id = spec_document_id
        requirement.spec_document_url = spec_document_url
        requirement.current_phase = "Spec 撰写"
        requirement.current_owner = "spec-agent"
        requirement.current_role_label = "Spec 撰写 Agent"
        requirement.touch()
        LOGGER.info(
            "Spec start accepted req_id=%s status=%s spec_status=%s spec_document_id=%s",
            requirement.req_id,
            requirement.status.value,
            requirement.spec_status.value if requirement.spec_status else "None",
            spec_document_id,
        )
        return requirement

    def _on_spec_deadlock(self, req_id: str, reason: str) -> None:
        r = self.requirements.get(req_id)
        if r is None:
            return
        from .spec_state_machine import SpecEvent, apply_spec_event
        decision = apply_spec_event(r.spec_status, SpecEvent.TRANSFORM_DEADLOCK)
        if decision.allowed:
            r.spec_deadlocked = True

    def _on_spec_locked(
        self,
        req_id: str,
        pr_url: str,
        *,
        source_revision: str = "",
        trace_digest: str = "",
        transform_round: int = 0,
    ) -> None:
        r = self.requirements.get(req_id)
        if r is None:
            return
        from .spec_state_machine import SpecEvent, apply_spec_event
        decision = apply_spec_event(r.spec_status, SpecEvent.TRANSFORM_CONVERGED)
        if decision.allowed:
            r.spec_status = decision.next_status
            r.spec_pr_url = pr_url
            r.spec_source_revision = source_revision
            r.transform_trace_digest = trace_digest

    def _project_repo_for(self, req_id: str) -> str:
        r = self.requirements[req_id]
        cfg = self.project_configs.get(r.project)
        if cfg is None or not cfg.github_repo_url:
            raise ValueError(
                f"Project {r.project} has no github_repo_url; cannot resolve project repo."
            )
        return cfg.github_repo_url

    def configure_spec_orchestrator(
        self,
        *,
        tools,
        trace_dir,
        feishu=None,
    ) -> None:
        """Wire the spec transform orchestrator + ACM registry.

        ``tools`` is a ``ProjectRepoTools``; the caller (service_app) is
        responsible for wrapping a ``GitHubGateway`` if needed. Idempotent:
        calling twice replaces the previous orchestrator.
        """
        from .acm_registry import AcmRegistry
        from .spec_state_machine import SpecStatus
        from .spec_transform import SpecTransformOrchestrator
        self._acm_registry = AcmRegistry()
        self.spec_orchestrator = SpecTransformOrchestrator(
            tools=tools,
            registry=self._acm_registry,
            feishu=feishu,
            trace_dir=trace_dir,
            on_deadlock=self._on_spec_deadlock,
            on_locked=self._on_spec_locked,
        )
        self.spec_orchestrator._project_repo_for = self._project_repo_for
        self._hooks.on_enter(
            SpecStatus.TRANSFORMING, self._on_enter_transforming_hook,
        )

    def _on_enter_transforming_hook(self, r: Requirement) -> None:
        self.spec_orchestrator.on_enter_transforming(
            req_id=r.req_id,
            project_repo=self._project_repo_for(r.req_id),
            spec_doc_id=r.spec_document_id,
        )

    def spec_restart(self, req_id: str) -> Requirement:
        """Reset Spec state for re-entry. Allowed only in DRAFTING or
        TRANSFORMING(deadlocked=True). Archives the per-REQ trace.jsonl
        under ``trace_dir/archive/`` so the deadlocked attempt remains
        auditable, drops in-memory orchestrator state, and clears all
        ``spec_*``/audit fields."""
        r = self.requirements.get(req_id)
        if r is None:
            raise KeyError(req_id)
        from .spec_state_machine import SpecEvent, apply_spec_event
        decision = apply_spec_event(
            r.spec_status, SpecEvent.SPEC_RESTART, deadlocked=r.spec_deadlocked,
        )
        if not decision.allowed:
            raise ValueError(decision.message)
        if self.spec_orchestrator is not None:
            self.spec_orchestrator.archive_trace(req_id, suffix="restart")
        r.spec_status = None
        r.spec_document_url = ""
        r.spec_document_id = ""
        r.spec_deadlocked = False
        r.spec_transform_snapshot = None
        r.spec_source_revision = ""
        r.transform_trace_digest = ""
        r.spec_pr_url = ""
        return r

    def submit_spec_submit(self, req_id: str, *, summary: str) -> Requirement:
        requirement = self.requirements.get(req_id)
        if requirement is None:
            raise ValueError(f"未知需求：{req_id}")
        if requirement.spec_status != SpecStatus.DRAFTING:
            current = requirement.spec_status.value if requirement.spec_status else "None"
            raise ValueError(
                f"spec_submit 只能在 spec_status=SPEC_DRAFTING 状态执行，当前：{current}"
            )
        requirement.spec_review_summary = summary
        requirement.touch()
        LOGGER.info("Spec submit accepted req_id=%s summary=%s", req_id, summary)
        return requirement

    def request_changes_after_review(self, requirement: Requirement, summary: str | None = None) -> Requirement:
        decision = apply_event(requirement.status, Event.FINAL_REVIEW_REJECT)
        if not decision.allowed:
            raise ValueError(decision.message)

        requirement.status = decision.next_status
        requirement.current_phase = "需求构造"
        requirement.current_owner = "author"
        requirement.current_role_label = "需求构造Agent"
        requirement.latest_review_summary = summary or "正式审查要求继续修改。"
        requirement.ai_ready = False
        requirement.human_confirmed = False
        requirement.latest_question = "正式审查未通过，请根据审查意见继续补充，然后再发起下一轮 AI review。"
        requirement.touch()
        LOGGER.info(
            "Requested changes after review req_id=%s status=%s summary=%s",
            requirement.req_id,
            requirement.status.value,
            requirement.latest_review_summary,
        )
        return requirement

    def submit_checkpoint_1a_pass(self, req_id: str) -> Requirement:
        r = self.requirements[req_id]
        cfg = self.project_configs.get(r.project)
        if cfg is None or not cfg.github_repo_url:
            raise ValueError(f"项目 {r.project} 未配置 github_repo_url")
        decision = apply_spec_event(r.spec_status, SpecEvent.CHECKPOINT_1A_PASS)
        if not decision.allowed:
            raise ValueError(decision.message)

        prev_status = r.spec_status
        self._hooks.fire_exit(prev_status, r)
        r.spec_status = decision.next_status
        self._hooks.fire_enter(r.spec_status, r)
        return r

    def _next_req_id(self, project: str) -> str:
        count = sum(1 for item in self.requirements.values() if item.project == project) + 1
        return f"REQ-{project}-{count:03d}"

    # ── PLANNING layer ──────────────────────────────────────────────────

    def plan_start(
        self,
        req_id: str,
        *,
        plan_doc_id: str = "",
        plan_doc_url: str = "",
    ) -> Requirement:
        r = self.requirements[req_id]
        if r.status != WorkflowStatus.APPROVED:
            raise ValueError(
                f"plan_start requires workflow_status=APPROVED, got {r.status.value}"
            )
        decision = apply_plan_event(r.plan_status, PlanEvent.PLAN_START)
        if not decision.allowed:
            raise ValueError(decision.message)

        prev = r.plan_status
        self._hooks.fire_exit(prev, r)
        r.plan_status = decision.next_status
        r.plan_phase = PlanPhase.OUTLINE_PENDING
        r.plan_doc_id = plan_doc_id
        r.plan_doc_url = plan_doc_url
        self._hooks.fire_enter(r.plan_status, r)
        return r

    def plan_authorize(self, req_id: str, *, authorized_by: str) -> Requirement:
        r = self.requirements[req_id]
        decision = apply_plan_event(r.plan_status, PlanEvent.PLAN_AUTHORIZE)
        if not decision.allowed:
            raise ValueError(decision.message)

        draft = r.pending_plan_draft or {}
        pcc = draft.get("project_context_change") or {}
        pcc["authorized"] = True
        pcc["authorized_by"] = authorized_by
        pcc["authorized_at"] = datetime.now(timezone.utc).isoformat()
        draft["project_context_change"] = pcc
        r.pending_plan_draft = draft

        prev = r.plan_status
        self._hooks.fire_exit(prev, r)
        r.plan_status = decision.next_status
        self._hooks.fire_enter(r.plan_status, r)
        return r

    def plan_authorization_reject(
        self, req_id: str, *, reason: str = "",
    ) -> Requirement:
        r = self.requirements[req_id]
        decision = apply_plan_event(
            r.plan_status, PlanEvent.PLAN_AUTHORIZATION_REJECT,
        )
        if not decision.allowed:
            raise ValueError(decision.message)

        prev = r.plan_status
        self._hooks.fire_exit(prev, r)
        r.plan_status = decision.next_status
        r.plan_phase = PlanPhase.DECISIONS_IN_PROGRESS
        self._hooks.fire_enter(r.plan_status, r)
        LOGGER.info(
            "plan_authorization_reject req_id=%s reason=%s", req_id, reason,
        )
        return r

    def set_plan_outline(self, req_id: str, outline: list[dict]) -> Requirement:
        r = self.requirements[req_id]
        if r.plan_status is not PlanStatus.DRAFTING:
            raise ValueError("plan outline can only be set in DRAFTING")
        r.plan_outline = list(outline)
        r.plan_phase = PlanPhase.DECISIONS_IN_PROGRESS
        return r

    def plan_submit(
        self,
        req_id: str,
        *,
        plan_md_content: str,
        project_context_change: dict | None,
    ) -> Requirement:
        r = self.requirements[req_id]
        decision = apply_plan_event(
            r.plan_status, PlanEvent.PLAN_SUBMIT,
            has_project_context_change=project_context_change is not None,
        )
        if not decision.allowed:
            raise ValueError(decision.message)

        r.pending_plan_draft = {
            "plan_md_content": plan_md_content,
            "project_context_change": project_context_change,
        }
        r.plan_phase = PlanPhase.FINAL_REVIEW_PENDING

        prev = r.plan_status
        self._hooks.fire_exit(prev, r)
        r.plan_status = decision.next_status
        self._hooks.fire_enter(r.plan_status, r)
        return r

    def configure_plan_hooks(self, *, tools, syncer=None) -> None:
        """Register PLANNING-layer hooks. Idempotent: safe to call twice.

        When ``syncer`` (a ``FeishuToGitHubSyncer``) is provided, the READY
        hook reads plan.md from the Feishu SOT via the syncer and uses the
        buffered ``pending_plan_draft.plan_md_content`` as audit fallback.
        Without a syncer, the hook falls back to the legacy path that
        commits ``pending_plan_draft.plan_md_content`` directly — used only
        by tests that don't care about the Feishu seam.
        """
        if getattr(self, "_plan_tools", None) is not None:
            self._plan_tools = tools
            self._plan_syncer = syncer
            return
        self._plan_tools = tools
        self._plan_syncer = syncer
        self._hooks.on_enter(
            PlanStatus.READY, self._commit_plan_and_maybe_architecture,
        )

    def _commit_plan_and_maybe_architecture(self, r: Requirement) -> None:
        """``on_enter(PlanStatus.READY)`` hook: atomic commit of plan.md (+project context files)."""
        draft = r.pending_plan_draft or {}
        plan_md_content = draft.get("plan_md_content", "")
        project_context_change = draft.get("project_context_change")
        project_repo = self._project_repo_for(r.req_id)

        message_parts = [f"plan({r.req_id}): land plan.md"]
        if project_context_change is not None:
            message_parts.append("and apply project_context_change")
        commit_message = " ".join(message_parts)

        if getattr(self, "_plan_syncer", None) is not None:
            sync_result = self._plan_syncer.sync_plan(
                req_id=r.req_id,
                project_repo=project_repo,
                plan_doc_id=r.plan_doc_id,
                project_context_change=project_context_change,
                commit_message=commit_message,
                fallback_plan_md=plan_md_content,
            )
            r.plan_pr_url = sync_result.commit_sha
        else:
            artifacts = PlanArtifacts(
                project_repo=project_repo,
                req_id=r.req_id,
                plan_md_content=plan_md_content,
                project_context_change=project_context_change,
                commit_message=commit_message,
            )
            result = self._plan_tools.commit_plan_artifacts(artifacts)
            r.plan_pr_url = result.commit_sha
        r.pending_plan_draft = None

    def _fetch_plan_md(self, req_id: str) -> str:
        """Default stub; override in production to pull plan.md from GitHub."""
        return ""

    def plan_restart(self, req_id: str) -> Requirement:
        r = self.requirements[req_id]
        decision = apply_plan_event(r.plan_status, PlanEvent.PLAN_RESTART)
        if not decision.allowed:
            raise ValueError(decision.message)

        prev = r.plan_status
        self._hooks.fire_exit(prev, r)
        r.plan_status = None
        r.plan_phase = None
        r.plan_pr_url = ""
        r.plan_outline = []
        r.plan_decisions_wip = []
        r.pending_plan_draft = None
        self._cascade_reset_spec(r)
        return r

    def design_restart(self, req_id: str) -> Requirement:
        r = self.requirements[req_id]
        decision = apply_design_event(r.design_status, DesignEvent.DESIGN_RESTART)
        if not decision.allowed:
            raise ValueError(decision.message)

        r.design_status = None
        if r.plan_status is not None:
            self.plan_restart(req_id)
        return r

    def _cascade_reset_spec(self, r: Requirement) -> None:
        """Quiet spec reset used by plan_restart; no deadlock precondition."""
        if r.spec_status is None:
            return
        if self.spec_orchestrator is not None:
            try:
                self.spec_orchestrator.archive_trace(r.req_id, suffix="cascade")
            except Exception:
                LOGGER.exception(
                    "cascade spec archive failed req_id=%s", r.req_id,
                )
        r.spec_status = None
        r.spec_document_id = ""
        r.spec_document_url = ""
        r.spec_deadlocked = False
        r.spec_transform_snapshot = None
        r.spec_source_revision = ""
        r.transform_trace_digest = ""
        r.spec_pr_url = ""
