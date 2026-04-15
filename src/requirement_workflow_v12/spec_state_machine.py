from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class SpecStatus(str, Enum):
    DRAFTING = "SPEC_DRAFTING"
    LOCKED = "SPEC_LOCKED"


class SpecEvent(str, Enum):
    SPEC_START = "spec_start"
    SPEC_REVIEW_PASS = "spec_review_pass"
    SPEC_REVIEW_REJECT = "spec_review_reject"


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
