from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Requirement


SCHEMA_PATH = Path(__file__).resolve().parents[2] / "bitable_schema_v12.json"

BITABLE_FIELD_TYPE_TEXT = 1
BITABLE_FIELD_TYPE_NUMBER = 2
BITABLE_FIELD_TYPE_CHECKBOX = 7

BITABLE_FIELD_TYPE_MAP = {
    "text": BITABLE_FIELD_TYPE_TEXT,
    "number": BITABLE_FIELD_TYPE_NUMBER,
    "checkbox": BITABLE_FIELD_TYPE_CHECKBOX,
}


@dataclass(frozen=True)
class BitableFieldSpec:
    name: str
    field_type: str
    required: bool
    writer: str
    readers: tuple[str, ...]
    description: str

    @property
    def bitable_type(self) -> int:
        return BITABLE_FIELD_TYPE_MAP[self.field_type]


@lru_cache(maxsize=1)
def load_bitable_field_specs() -> tuple[BitableFieldSpec, ...]:
    payload = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return tuple(
        BitableFieldSpec(
            name=str(item["name"]),
            field_type=str(item["field_type"]),
            required=bool(item.get("required", False)),
            writer=str(item.get("writer", "")),
            readers=tuple(str(reader) for reader in item.get("readers", [])),
            description=str(item.get("description", "")),
        )
        for item in payload.get("fields", [])
    )


def coordinator_managed_field_specs() -> tuple[BitableFieldSpec, ...]:
    return tuple(spec for spec in load_bitable_field_specs() if spec.writer == "coordinator")


def reader_visible_field_specs(reader: str) -> tuple[BitableFieldSpec, ...]:
    return tuple(spec for spec in load_bitable_field_specs() if reader in spec.readers)


def coordinator_managed_field_names() -> tuple[str, ...]:
    return tuple(spec.name for spec in coordinator_managed_field_specs())


def build_coordinator_record_fields(requirement: "Requirement") -> dict[str, object]:
    field_extractors = {
        "REQ ID": lambda req: req.req_id,
        "需求名称": lambda req: req.name,
        "项目代号": lambda req: req.project,
        "需求简述": lambda req: req.summary,
        "状态": lambda req: req.status.value,
        "当前阶段": lambda req: req.current_phase,
        "当前轮次": lambda req: req.current_round,
        "当前讨论字段": lambda req: req.current_discussion_field,
        "当前Owner": lambda req: req.current_owner,
        "当前接手角色": lambda req: req.current_role_label,
        "已完成字段": lambda req: json.dumps(req.completed_fields, ensure_ascii=False),
        "待补字段": lambda req: json.dumps(req.pending_fields, ensure_ascii=False),
        "最近一次提问": lambda req: req.latest_question,
        "最近一次review结论": lambda req: req.latest_review_summary,
        "AI Ready": lambda req: req.ai_ready,
        "Human Confirmed": lambda req: req.human_confirmed,
        "需求文档链接": lambda req: req.document_url,
        "最近一次写回时间": lambda req: req.latest_writeback_at.isoformat() if req.latest_writeback_at else "",
    }
    expected_names = set(coordinator_managed_field_names())
    actual_names = set(field_extractors)
    if actual_names != expected_names:
        missing = sorted(expected_names - actual_names)
        extra = sorted(actual_names - expected_names)
        raise ValueError(
            "Coordinator record field mapping is out of sync with bitable_schema_v12.json: "
            f"missing={missing} extra={extra}"
        )
    return {name: field_extractors[name](requirement) for name in coordinator_managed_field_names()}
