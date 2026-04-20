"""Pure state machines for the PLANNING layer.

Two independent columns — PlanStatus and DesignStatus — live alongside
the existing SpecStatus column. Transition rules are side-effect free;
all commits, card sends, and orchestrator dispatches happen in hooks
registered via ``StateTransitionHooks`` (see state-machine-hook-pattern.md).

``PlanPhase`` is a sub-field on ``Requirement`` that tracks plan-author
conversation progress **inside** ``PlanStatus.DRAFTING``. It is NOT a
state-machine state — phase advances are direct field writes, not events.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class PlanStatus(str, Enum):
    DRAFTING = "PLAN_DRAFTING"
    AUTH_PENDING = "PLAN_AUTH_PENDING"
    READY = "PLAN_READY"


class PlanEvent(str, Enum):
    PLAN_START = "plan_start"
    PLAN_SUBMIT = "plan_submit"
    PLAN_AUTHORIZE = "plan_authorize"
    PLAN_AUTHORIZATION_REJECT = "plan_authorization_reject"
    PLAN_RESTART = "plan_restart"


class PlanPhase(str, Enum):
    OUTLINE_PENDING = "outline_pending"
    OUTLINE_CONFIRMED = "outline_confirmed"
    DECISIONS_IN_PROGRESS = "decisions_in_progress"
    FINAL_REVIEW_PENDING = "final_review_pending"


class DesignStatus(str, Enum):
    DRAFTING = "DESIGN_DRAFTING"
    READY = "DESIGN_READY"


class DesignEvent(str, Enum):
    DESIGN_START = "design_start"
    DESIGN_SUBMIT = "design_submit"
    DESIGN_RESTART = "design_restart"


@dataclass
class PlanTransitionDecision:
    allowed: bool
    next_status: Optional[PlanStatus]
    message: str
    requires: list[str] = field(default_factory=list)


@dataclass
class DesignTransitionDecision:
    allowed: bool
    next_status: Optional[DesignStatus]
    message: str
    requires: list[str] = field(default_factory=list)


_PLAN_TRANSITIONS: dict[tuple[Optional[PlanStatus], PlanEvent], PlanStatus] = {
    (None, PlanEvent.PLAN_START): PlanStatus.DRAFTING,
    (PlanStatus.AUTH_PENDING, PlanEvent.PLAN_AUTHORIZE): PlanStatus.READY,
    (PlanStatus.AUTH_PENDING, PlanEvent.PLAN_AUTHORIZATION_REJECT): PlanStatus.DRAFTING,
}


def apply_plan_event(
    current: Optional[PlanStatus],
    event: PlanEvent,
    *,
    has_project_context_change: bool = False,
) -> PlanTransitionDecision:
    if event is PlanEvent.PLAN_RESTART:
        if current is None:
            return PlanTransitionDecision(
                allowed=False,
                next_status=current,
                message="规划层未进入，无法 restart",
            )
        return PlanTransitionDecision(
            allowed=True,
            next_status=None,
            message="规划层状态已重置（restart）",
        )

    if event is PlanEvent.PLAN_SUBMIT and current is PlanStatus.DRAFTING:
        next_status = (
            PlanStatus.AUTH_PENDING if has_project_context_change else PlanStatus.READY
        )
        return PlanTransitionDecision(
            allowed=True,
            next_status=next_status,
            message=f"规划层状态已更新为 {next_status.value}",
        )

    next_status = _PLAN_TRANSITIONS.get((current, event))
    if next_status is None:
        label = current.value if current is not None else "<未进入规划层>"
        return PlanTransitionDecision(
            allowed=False,
            next_status=current,
            message=f"当前规划层状态 {label} 不能执行 {event.value}",
        )
    return PlanTransitionDecision(
        allowed=True,
        next_status=next_status,
        message=f"规划层状态已更新为 {next_status.value}",
    )


_DESIGN_TRANSITIONS: dict[tuple[Optional[DesignStatus], DesignEvent], DesignStatus] = {
    (None, DesignEvent.DESIGN_START): DesignStatus.DRAFTING,
    (DesignStatus.DRAFTING, DesignEvent.DESIGN_SUBMIT): DesignStatus.READY,
}


def apply_design_event(
    current: Optional[DesignStatus],
    event: DesignEvent,
) -> DesignTransitionDecision:
    if event is DesignEvent.DESIGN_RESTART:
        if current is None:
            return DesignTransitionDecision(
                allowed=False,
                next_status=current,
                message="设计层未进入，无法 restart",
            )
        return DesignTransitionDecision(
            allowed=True,
            next_status=None,
            message="设计层状态已重置（restart）",
        )

    next_status = _DESIGN_TRANSITIONS.get((current, event))
    if next_status is None:
        label = current.value if current is not None else "<未进入设计层>"
        return DesignTransitionDecision(
            allowed=False,
            next_status=current,
            message=f"当前设计层状态 {label} 不能执行 {event.value}",
        )
    return DesignTransitionDecision(
        allowed=True,
        next_status=next_status,
        message=f"设计层状态已更新为 {next_status.value}",
    )
