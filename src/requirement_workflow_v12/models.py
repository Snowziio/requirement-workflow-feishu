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
]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class WorkflowStatus(str, Enum):
    CREATED = "CREATED"
    DISCUSSION_ROUTING = "DISCUSSION_ROUTING"
    DISCUSSING = "DISCUSSING"
    AI_REVIEWING = "AI_REVIEWING"
    HUMAN_CONFIRMING = "HUMAN_CONFIRMING"
    REVIEWING = "REVIEWING"
    REQ_APPROVED = "REQ_APPROVED"


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
    next_focus: str | None = None
    reviewed_at: datetime = field(default_factory=utc_now)


@dataclass
class RequirementDocument:
    title: str
    sections: dict[str, str] = field(default_factory=dict)
    updated_at: datetime = field(default_factory=utc_now)

    def rewrite_section(self, section: str, content: str) -> None:
        self.sections[section] = content.strip()
        self.updated_at = utc_now()


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
    document: RequirementDocument | None = None
    review_history: list[ReviewResult] = field(default_factory=list)
    updated_at: datetime = field(default_factory=utc_now)

    def touch(self) -> None:
        self.updated_at = utc_now()
