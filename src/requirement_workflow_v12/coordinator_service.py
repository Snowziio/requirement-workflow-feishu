from __future__ import annotations

from dataclasses import dataclass

from .compiler import RequirementDocumentCompiler
from .models import DISCUSSION_FIELDS, Requirement, ReviewResult, WorkflowStatus
from .protocols import AuthorStartBinding, AuthorStartResponse, CreationRequest, CreationResponse
from .state_machine import Event, apply_event


@dataclass
class AuthorTurnResult:
    updates: dict[str, str]
    next_question: str
    current_field_completed: bool = True
    next_field: str | None = None


class CoordinatorService:
    """Independent backend coordinator for Feishu events and workflow state."""

    def __init__(self, compiler: RequirementDocumentCompiler | None = None) -> None:
        self.compiler = compiler or RequirementDocumentCompiler()
        self.project_groups: dict[str, str] = {}
        self.requirements: dict[str, Requirement] = {}
        self.active_req_by_user: dict[str, str] = {}

    def restore_snapshot(
        self,
        requirements: dict[str, Requirement],
        active_req_by_user: dict[str, str],
        project_groups: dict[str, str],
    ) -> None:
        self.requirements = requirements
        self.active_req_by_user = active_req_by_user
        self.project_groups = project_groups

    def get_requirement(self, req_id: str) -> Requirement | None:
        return self.requirements.get(req_id)

    def assign_project_group(self, req_id: str, project_group_id: str) -> Requirement:
        requirement = self.requirements[req_id]
        requirement.project_group_id = project_group_id
        self.project_groups[requirement.project] = project_group_id
        requirement.touch()
        return requirement

    def attach_bitable_record(self, req_id: str, record_id: str) -> Requirement:
        requirement = self.requirements[req_id]
        requirement.bitable_record_id = record_id
        requirement.touch()
        return requirement

    def attach_document(self, req_id: str, document_id: str, document_url: str) -> Requirement:
        requirement = self.requirements[req_id]
        requirement.document_id = document_id
        requirement.document_url = document_url
        requirement.touch()
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

        start_command = f"开始需求构造 {req_id}"
        creation_message = (
            f"{req_id} 已创建\n"
            f"项目：{request.project}\n"
            f"需求文档已初始化\n"
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
        if requirement.status != WorkflowStatus.DISCUSSING:
            self.handoff_to_author(requirement)
        else:
            requirement.current_owner = "author"
            requirement.current_role_label = "需求构造Agent"
            requirement.touch()
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
        requirement.document = self.compiler.create_document(requirement)
        requirement.touch()
        return requirement

    def handoff_to_author(self, requirement: Requirement) -> Requirement:
        decision = apply_event(requirement.status, Event.HANDOFF_TO_AUTHOR)
        if not decision.allowed:
            raise ValueError(decision.message)
        requirement.status = decision.next_status
        requirement.current_owner = "author"
        requirement.current_role_label = "需求构造Agent"
        requirement.touch()
        return requirement

    def handle_author_turn(self, requirement: Requirement, turn: AuthorTurnResult) -> Requirement:
        decision = apply_event(requirement.status, Event.SUBMIT_AUTHOR_ROUND)
        if not decision.allowed:
            raise ValueError(decision.message)

        requirement.current_round += 1
        requirement.status = decision.next_status
        requirement.document = self.compiler.rewrite_sections(requirement, turn.updates)
        requirement.latest_writeback_at = requirement.document.updated_at

        for field in turn.updates:
            if field not in requirement.completed_fields:
                requirement.completed_fields.append(field)

        requirement.pending_fields = [field for field in DISCUSSION_FIELDS if field not in requirement.completed_fields]
        requirement.current_discussion_field = turn.next_field or (
            requirement.pending_fields[0] if requirement.pending_fields else DISCUSSION_FIELDS[-1]
        )
        requirement.latest_question = turn.next_question
        requirement.current_owner = "reviewer"
        requirement.current_role_label = "审查Agent"
        requirement.touch()
        return requirement

    def handle_review_result(self, requirement: Requirement, result: ReviewResult) -> Requirement:
        event = Event.FINISH_AI_REVIEW_READY if result.ready_for_human_confirmation else Event.FINISH_AI_REVIEW_NOT_READY
        decision = apply_event(requirement.status, event)
        if not decision.allowed:
            raise ValueError(decision.message)

        requirement.status = decision.next_status
        requirement.review_history.append(result)
        requirement.latest_review_summary = result.summary
        requirement.ai_ready = result.ready_for_human_confirmation

        if result.ready_for_human_confirmation:
            requirement.current_owner = "human"
            requirement.current_role_label = "人工确认"
            requirement.latest_question = "AI 评审已通过，请确认当前需求是否准确表达你的意图。"
        else:
            requirement.current_owner = "author"
            requirement.current_role_label = "需求构造Agent"
            requirement.latest_question = result.next_focus or requirement.latest_question

        requirement.touch()
        return requirement

    def handle_human_confirmation(self, requirement: Requirement, approved: bool) -> Requirement:
        event = Event.HUMAN_CONFIRM_YES if approved else Event.HUMAN_CONFIRM_NO
        decision = apply_event(requirement.status, event, ai_ready=requirement.ai_ready)
        if not decision.allowed:
            raise ValueError(decision.message)

        requirement.status = decision.next_status
        requirement.human_confirmed = approved
        if approved:
            requirement.current_owner = "coordinator-service"
            requirement.current_role_label = "需求协调服务"
            requirement.latest_question = "需求构造完成，可进入正式审查。"
        else:
            requirement.current_owner = "author"
            requirement.current_role_label = "需求构造Agent"
            requirement.latest_question = "请继续补充或修正需求内容，然后我们会再进行一轮 AI review。"

        requirement.touch()
        return requirement

    def approve_requirement(self, requirement: Requirement) -> Requirement:
        decision = apply_event(
            requirement.status,
            Event.APPROVE_REQUIREMENT,
            human_confirmed=requirement.human_confirmed,
        )
        if not decision.allowed:
            raise ValueError(decision.message)

        requirement.status = decision.next_status
        requirement.current_owner = "coordinator-service"
        requirement.current_role_label = "需求协调服务"
        requirement.latest_question = f"需求已批准，建议后续分支名为 spec/{requirement.req_id}。"
        requirement.touch()
        return requirement

    def _next_req_id(self, project: str) -> str:
        count = sum(1 for item in self.requirements.values() if item.project == project) + 1
        return f"REQ-{project}-{count:03d}"
