from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .models import WorkflowStatus


class Event(str, Enum):
    CREATE_REQUIREMENT = "create_requirement"
    HANDOFF_TO_AUTHOR = "handoff_to_author"
    SUBMIT_AUTHOR_ROUND = "submit_author_round"
    FINISH_AI_REVIEW_NOT_READY = "finish_ai_review_not_ready"
    FINISH_AI_REVIEW_READY = "finish_ai_review_ready"
    HUMAN_CONFIRM_YES = "human_confirm_yes"
    HUMAN_CONFIRM_NO = "human_confirm_no"
    APPROVE_REQUIREMENT = "approve_requirement"
    REQUEST_CHANGES = "request_changes"


@dataclass
class TransitionDecision:
    allowed: bool
    next_status: WorkflowStatus
    message: str
    requires: list[str] = field(default_factory=list)


TRANSITIONS: dict[tuple[WorkflowStatus, Event], WorkflowStatus] = {
    (WorkflowStatus.CREATED, Event.CREATE_REQUIREMENT): WorkflowStatus.DISCUSSION_ROUTING,
    (WorkflowStatus.DISCUSSION_ROUTING, Event.HANDOFF_TO_AUTHOR): WorkflowStatus.DISCUSSING,
    (WorkflowStatus.DISCUSSING, Event.SUBMIT_AUTHOR_ROUND): WorkflowStatus.AI_REVIEWING,
    (WorkflowStatus.AI_REVIEWING, Event.FINISH_AI_REVIEW_NOT_READY): WorkflowStatus.DISCUSSING,
    (WorkflowStatus.AI_REVIEWING, Event.FINISH_AI_REVIEW_READY): WorkflowStatus.HUMAN_CONFIRMING,
    (WorkflowStatus.HUMAN_CONFIRMING, Event.HUMAN_CONFIRM_NO): WorkflowStatus.DISCUSSING,
    (WorkflowStatus.HUMAN_CONFIRMING, Event.HUMAN_CONFIRM_YES): WorkflowStatus.REVIEWING,
    (WorkflowStatus.REVIEWING, Event.APPROVE_REQUIREMENT): WorkflowStatus.REQ_APPROVED,
    (WorkflowStatus.REVIEWING, Event.REQUEST_CHANGES): WorkflowStatus.DISCUSSING,
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

    if event == Event.APPROVE_REQUIREMENT and not human_confirmed:
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
