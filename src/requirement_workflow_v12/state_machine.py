from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .models import WorkflowStatus


class Event(str, Enum):
    """需求层 Workflow Service 事件集合。规格层事件在 `spec_state_machine.SpecEvent`。"""

    CREATE_REQUIREMENT = "create_requirement"
    AUTHOR_SUBMIT = "author_submit"
    AI_REVIEW_REJECT = "ai_review_reject"
    AI_REVIEW_PASS = "ai_review_pass"
    HUMAN_CONFIRM_YES = "human_confirm_yes"
    HUMAN_CONFIRM_NO = "human_confirm_no"
    FINAL_REVIEW_PASS = "final_review_pass"
    FINAL_REVIEW_REJECT = "final_review_reject"


@dataclass
class TransitionDecision:
    allowed: bool
    next_status: WorkflowStatus
    message: str
    requires: list[str] = field(default_factory=list)


TRANSITIONS: dict[tuple[WorkflowStatus, Event], WorkflowStatus] = {
    (WorkflowStatus.CREATED, Event.CREATE_REQUIREMENT): WorkflowStatus.DRAFTING,
    (WorkflowStatus.DRAFTING, Event.AUTHOR_SUBMIT): WorkflowStatus.AI_REVIEW,
    (WorkflowStatus.AI_REVIEW, Event.AI_REVIEW_REJECT): WorkflowStatus.DRAFTING,
    (WorkflowStatus.AI_REVIEW, Event.AI_REVIEW_PASS): WorkflowStatus.HUMAN_CONFIRM,
    (WorkflowStatus.HUMAN_CONFIRM, Event.HUMAN_CONFIRM_NO): WorkflowStatus.DRAFTING,
    (WorkflowStatus.HUMAN_CONFIRM, Event.HUMAN_CONFIRM_YES): WorkflowStatus.FINAL_REVIEW,
    (WorkflowStatus.FINAL_REVIEW, Event.FINAL_REVIEW_PASS): WorkflowStatus.APPROVED,
    (WorkflowStatus.FINAL_REVIEW, Event.FINAL_REVIEW_REJECT): WorkflowStatus.DRAFTING,
}


def apply_event(
    current_status: WorkflowStatus,
    event: Event,
    *,
    ai_ready: bool | None = None,
    human_confirmed: bool | None = None,
) -> TransitionDecision:
    if event == Event.HUMAN_CONFIRM_YES and not ai_ready:
        return TransitionDecision(
            allowed=False,
            next_status=current_status,
            message="AI Ready 未满足，不能进入正式审查。",
            requires=["AI Ready = true"],
        )

    if event == Event.FINAL_REVIEW_PASS and not human_confirmed:
        return TransitionDecision(
            allowed=False,
            next_status=current_status,
            message="Human Confirmed 未满足，不能批准需求。",
            requires=["Human Confirmed = true"],
        )

    next_status = TRANSITIONS.get((current_status, event))
    if next_status is None:
        return TransitionDecision(
            allowed=False,
            next_status=current_status,
            message=f"当前状态 {current_status.value} 不能执行 {event.value}",
        )

    return TransitionDecision(
        allowed=True,
        next_status=next_status,
        message=f"状态已更新为 {next_status.value}",
    )
