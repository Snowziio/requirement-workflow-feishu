from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Requirement


SCHEMA_PATH = Path(__file__).resolve().parents[2] / "bitable_schema_v12.json"
PROJECT_CONFIG_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2] / "bitable_project_configs_schema.json"
)

BITABLE_FIELD_TYPE_TEXT = 1
BITABLE_FIELD_TYPE_NUMBER = 2
BITABLE_FIELD_TYPE_SINGLE_SELECT = 3
BITABLE_FIELD_TYPE_DATETIME = 5
BITABLE_FIELD_TYPE_CHECKBOX = 7
BITABLE_FIELD_TYPE_URL = 15

BITABLE_FIELD_TYPE_MAP = {
    "text": BITABLE_FIELD_TYPE_TEXT,
    "number": BITABLE_FIELD_TYPE_NUMBER,
    "single_select": BITABLE_FIELD_TYPE_SINGLE_SELECT,
    "datetime": BITABLE_FIELD_TYPE_DATETIME,
    "checkbox": BITABLE_FIELD_TYPE_CHECKBOX,
    "url": BITABLE_FIELD_TYPE_URL,
}


@dataclass(frozen=True)
class BitableFieldSpec:
    name: str
    field_type: str
    required: bool
    writer: str
    readers: tuple[str, ...]
    description: str
    options: tuple[str, ...] = ()

    @property
    def bitable_type(self) -> int:
        return BITABLE_FIELD_TYPE_MAP[self.field_type]


@dataclass(frozen=True)
class ProjectConfigFieldSpec:
    name: str
    field_type: str
    required: bool
    description: str
    options: tuple[str, ...] = ()

    @property
    def bitable_type(self) -> int:
        return BITABLE_FIELD_TYPE_MAP[self.field_type]


PROJECT_CONFIG_FIELD_PROJECT = "项目名"
PROJECT_CONFIG_FIELD_CATEGORY = "类别"
PROJECT_CONFIG_FIELD_TEMPLATE_VERSION = "模板版本"
PROJECT_CONFIG_FIELD_ARCH_DOC_ID = "架构文档ID"
PROJECT_CONFIG_FIELD_ARCH_DOC_URL = "架构文档URL"
PROJECT_CONFIG_FIELD_TECH_STACK_JSON = "技术栈JSON"
PROJECT_CONFIG_FIELD_DESIGN_SYSTEM_DOC_ID = "设计系统文档ID"
PROJECT_CONFIG_FIELD_GITHUB_REPO_URL = "GitHub仓库URL"
PROJECT_CONFIG_FIELD_GITHUB_OWNER_USERNAME = "GitHub负责人用户名"
PROJECT_CONFIG_FIELD_BOOTSTRAP_STATUS = "引导状态"
PROJECT_CONFIG_FIELD_BOOTSTRAP_LOG_JSON = "引导日志JSON"
PROJECT_CONFIG_FIELD_BOOTSTRAP_COMPLETED_AT = "引导完成时间"
PROJECT_CONFIG_FIELD_PROJECT_STATUS = "项目状态"
PROJECT_CONFIG_FIELD_FEISHU_CHAT_ID = "飞书群chat_id"
PROJECT_CONFIG_FIELD_CLAUDE_DESIGN_PROJECT_URL = "Claude设计项目URL"
PROJECT_CONFIG_FIELD_FRONTEND_SUBPATH = "前端子路径"
PROJECT_CONFIG_FIELD_FRONTEND_TECH_STACK_JSON = "前端技术栈JSON"


@lru_cache(maxsize=1)
def load_project_config_field_specs() -> tuple[ProjectConfigFieldSpec, ...]:
    payload = json.loads(PROJECT_CONFIG_SCHEMA_PATH.read_text(encoding="utf-8"))
    return tuple(
        ProjectConfigFieldSpec(
            name=str(item["name"]),
            field_type=str(item["field_type"]),
            required=bool(item.get("required", False)),
            description=str(item.get("description", "")),
        )
        for item in payload.get("fields", [])
    )


def project_config_table_name() -> str:
    payload = json.loads(PROJECT_CONFIG_SCHEMA_PATH.read_text(encoding="utf-8"))
    return str(payload.get("table_name", "ProjectConfigs"))


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
            options=tuple(str(opt) for opt in item.get("options", [])),
        )
        for item in payload.get("fields", [])
    )


def coordinator_managed_field_specs() -> tuple[BitableFieldSpec, ...]:
    return tuple(spec for spec in load_bitable_field_specs() if spec.writer == "coordinator")


def reader_visible_field_specs(reader: str) -> tuple[BitableFieldSpec, ...]:
    return tuple(spec for spec in load_bitable_field_specs() if reader in spec.readers)


def coordinator_managed_field_names() -> tuple[str, ...]:
    return tuple(spec.name for spec in coordinator_managed_field_specs())


def _url_payload(url: str) -> dict[str, str] | str:
    # Bitable URL 字段期望 {"link": "...", "text": "..."}；空值直接写空串。
    if not url:
        return ""
    return {"link": url, "text": url}


def _datetime_to_ms(value) -> int | None:
    if value is None:
        return None
    return int(value.timestamp() * 1000)


def build_coordinator_record_fields(requirement: "Requirement") -> dict[str, object]:
    field_extractors = {
        "REQ ID": lambda req: req.req_id,
        "需求名称": lambda req: req.name,
        "项目代号": lambda req: req.project,
        "需求简述": lambda req: req.summary,
        "状态": lambda req: req.status.value,
        "Spec 阶段": lambda req: req.spec_status.value if req.spec_status else "",
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
        "需求文档链接": lambda req: _url_payload(req.document_url),
        "最近一次写回时间": lambda req: _datetime_to_ms(req.latest_writeback_at),
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
