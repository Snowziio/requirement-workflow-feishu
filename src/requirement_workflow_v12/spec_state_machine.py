from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class SpecStatus(str, Enum):
    DRAFTING = "SPEC_DRAFTING"
    TRANSFORMING = "SPEC_TRANSFORMING"
    LOCKED = "SPEC_LOCKED"


class SpecEvent(str, Enum):
    SPEC_START = "spec_start"
    SPEC_REVIEW_PASS = "spec_review_pass"
    SPEC_REVIEW_REJECT = "spec_review_reject"
    # 转化博弈进入: checkpoint_1a_pass 后 Coordinator 显式触发；保留为独立事件
    # 而不是复用 SPEC_REVIEW_PASS，避免老调用链(目前仍走 DRAFTING→LOCKED)被一并改向。
    CHECKPOINT_1A_PASS = "checkpoint_1a_pass"
    TRANSFORM_CONVERGED = "transform_converged"
    # Deadlock = 博弈达到 max_rounds 仍 reject。状态留在 TRANSFORMING(自循环),
    # Coordinator 同时写人工工单。**不**回退 SPEC_DRAFTING(保护人工确认结论)。
    TRANSFORM_DEADLOCK = "transform_deadlock"


@dataclass
class SpecTransitionDecision:
    allowed: bool
    next_status: Optional[SpecStatus]
    message: str
    requires: list[str] = field(default_factory=list)


# Transition table keyed on (current_spec_status, event).
# `None` represents "没有进入规格层"（APPROVED 之后、spec_start 之前）。
SPEC_TRANSITIONS: dict[tuple[Optional[SpecStatus], SpecEvent], SpecStatus] = {
    (None, SpecEvent.SPEC_START): SpecStatus.DRAFTING,
    (SpecStatus.DRAFTING, SpecEvent.SPEC_REVIEW_PASS): SpecStatus.LOCKED,
    (SpecStatus.DRAFTING, SpecEvent.SPEC_REVIEW_REJECT): SpecStatus.DRAFTING,
    (SpecStatus.DRAFTING, SpecEvent.CHECKPOINT_1A_PASS): SpecStatus.TRANSFORMING,
    (SpecStatus.TRANSFORMING, SpecEvent.TRANSFORM_CONVERGED): SpecStatus.LOCKED,
    (SpecStatus.TRANSFORMING, SpecEvent.TRANSFORM_DEADLOCK): SpecStatus.TRANSFORMING,
}


def apply_spec_event(
    current: Optional[SpecStatus],
    event: SpecEvent,
) -> SpecTransitionDecision:
    next_status = SPEC_TRANSITIONS.get((current, event))
    if next_status is None:
        current_label = current.value if current is not None else "<未进入规格层>"
        return SpecTransitionDecision(
            allowed=False,
            next_status=current,
            message=f"当前规格层状态 {current_label} 不能执行 {event.value}",
        )
    return SpecTransitionDecision(
        allowed=True,
        next_status=next_status,
        message=f"规格层状态已更新为 {next_status.value}",
    )
