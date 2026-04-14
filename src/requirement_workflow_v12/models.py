from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


DISCUSSION_FIELDS = [
    "问题描述",
    "使用场景",
    "输入",
    "输出",
    "边界",
    "验收标准",
    "非功能要求",
    "技术范围声明",
]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class WorkflowStatus(str, Enum):
    CREATED = "CREATED"
    DRAFTING = "DRAFTING"
    DISCUSSION_ROUTING = "DRAFTING"
    DISCUSSING = "DRAFTING"
    AI_REVIEW = "AI_REVIEW"
    AI_REVIEWING = "AI_REVIEW"
    HUMAN_CONFIRM = "HUMAN_CONFIRM"
    HUMAN_CONFIRMING = "HUMAN_CONFIRM"
    FINAL_REVIEW = "FINAL_REVIEW"
    REVIEWING = "FINAL_REVIEW"
    APPROVED = "APPROVED"
    REQ_APPROVED = "APPROVED"
    SPEC_DRAFTING = "SPEC_DRAFTING"
    SPEC_LOCKED = "SPEC_LOCKED"


@dataclass
class ReviewFinding:
    dimension: str
    summary: str
    severity: str


@dataclass
class ReviewResult:
    ready_for_human_confirmation: bool
    summary: str
    findings: list[ReviewFinding] = field(default_factory=list)
    weak_fields: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    non_testable_acceptance_criteria: list[str] = field(default_factory=list)
    next_focus: str | None = None
    reviewed_at: datetime = field(default_factory=utc_now)


@dataclass
class DiscussionTurn:
    round_number: int
    focused_field: str
    user_input: str
    review_summary: str = ""
    next_question: str = ""
    ai_ready_after_review: bool = False
    created_at: datetime = field(default_factory=utc_now)


@dataclass
class HumanReviewResult:
    approved: bool
    summary: str
    reviewed_at: datetime = field(default_factory=utc_now)


@dataclass
class Requirement:
    req_id: str
    name: str
    project: str
    summary: str
    creator: str
    status: WorkflowStatus = WorkflowStatus.CREATED
    current_phase: str = "需求构造"
    current_round: int = 0
    current_discussion_field: str = DISCUSSION_FIELDS[0]
    completed_fields: list[str] = field(default_factory=list)
    pending_fields: list[str] = field(default_factory=lambda: list(DISCUSSION_FIELDS))
    current_owner: str = "coordinator-service"
    current_role_label: str = "需求协调服务"
    latest_review_summary: str = ""
    ai_ready: bool = False
    human_confirmed: bool = False
    latest_question: str = ""
    creator_user_id: str = ""
    creation_chat_id: str = ""
    project_group_id: str = ""
    author_dm_chat_id: str = ""
    bitable_record_id: str = ""
    document_id: str = ""
    document_url: str = ""
    active_private_binding_confirmed: bool = False
    latest_writeback_at: datetime | None = None
    discussion_history: list[DiscussionTurn] = field(default_factory=list)
    review_history: list[ReviewResult] = field(default_factory=list)
    human_review_history: list[HumanReviewResult] = field(default_factory=list)
    needs_ui: bool = False
    github_repo_url: str = ""
    hifi_prototype_url: str = ""
    hifi_prototype_confirmed: bool = False
    spec_document_id: str = ""
    spec_document_url: str = ""
    spec_review_summary: str = ""
    updated_at: datetime = field(default_factory=utc_now)

    def touch(self) -> None:
        self.updated_at = utc_now()
