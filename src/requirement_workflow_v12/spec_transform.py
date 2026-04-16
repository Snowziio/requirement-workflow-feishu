from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


NextAction = Literal[
    "soft_retry_transformer",
    "wake_reviewer",
    "wake_transformer_next_round",
    "deadlock",
    "converged",
]


@dataclass(frozen=True)
class TransformContextSnapshot:
    req_id: str
    spec_source_revision: str
    architecture_revision: str
    acm_registry_revision: str
    acm_active_slice: list[str]
    captured_at: str


@dataclass
class RoundContext:
    snapshot: TransformContextSnapshot
    round_index: int = 1
    soft_retry_count: int = 0
    race_retry_count: int = 0
    last_transformer_payload: dict | None = None
    last_reviewer_findings: list[dict] = field(default_factory=list)
