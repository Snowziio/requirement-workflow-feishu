"""Tests for FeishuGateway.list_project_configs / upsert_project_config.

These tests inject a fake Lark client into the gateway so they run without
any real Feishu credentials.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.config import Settings
from requirement_workflow_v12.feishu_gateway import FeishuGateway
from requirement_workflow_v12.project_config import ProjectConfig


def _make_gateway() -> FeishuGateway:
    settings = Settings(
        feishu_app_id="app",
        feishu_app_secret="secret",
        feishu_bitable_app_token="tok",
        feishu_bitable_project_configs_table_id="tbl_pc",
    )
    # Bypass FeishuGateway.__init__ (it requires lark_oapi) and inject a fake client.
    gateway = FeishuGateway.__new__(FeishuGateway)
    gateway.settings = settings
    gateway.client = MagicMock()
    return gateway


@dataclass
class _FakeResponse:
    data: Any
    _ok: bool = True
    code: int = 0
    msg: str = "ok"

    def success(self) -> bool:
        return self._ok


@dataclass
class _FakeListData:
    items: list
    has_more: bool = False
    page_token: str = ""


@dataclass
class _FakeRecord:
    fields: dict
    record_id: str


def test_list_project_configs_returns_empty_when_table_unconfigured():
    settings = Settings(feishu_app_id="a", feishu_app_secret="b")
    gateway = FeishuGateway.__new__(FeishuGateway)
    gateway.settings = settings
    gateway.client = MagicMock()
    assert gateway.list_project_configs() == {}


def test_list_project_configs_parses_rows():
    gateway = _make_gateway()
    record = _FakeRecord(
        fields={
            "项目名": "MyProj",
            "类别": "saas-ai-automation",
            "模板版本": "saas-ai-automation.v1",
            "架构文档ID": "doc_x",
            "架构文档URL": "https://example/docx/doc_x",
            "技术栈JSON": json.dumps({"backend": "FastAPI"}, ensure_ascii=False),
            "设计系统文档ID": "",
        },
        record_id="rec_1",
    )
    gateway.client.bitable.v1.app_table_record.list.return_value = _FakeResponse(
        data=_FakeListData(items=[record])
    )

    loaded = gateway.list_project_configs()
    assert set(loaded.keys()) == {"MyProj"}
    cfg = loaded["MyProj"]
    assert cfg.category == "saas-ai-automation"
    assert cfg.architecture_doc_id == "doc_x"
    assert cfg.tech_stack == {"backend": "FastAPI"}
    assert cfg.design_system_doc_id is None
    assert cfg.bitable_record_id == "rec_1"


def test_list_project_configs_skips_rows_without_project_name():
    gateway = _make_gateway()
    bad = _FakeRecord(fields={"项目名": "", "类别": "x"}, record_id="rec_bad")
    good = _FakeRecord(
        fields={
            "项目名": "P",
            "类别": "c",
            "模板版本": "v",
            "架构文档ID": "d",
            "架构文档URL": "u",
            "技术栈JSON": "",
            "设计系统文档ID": "",
        },
        record_id="rec_good",
    )
    gateway.client.bitable.v1.app_table_record.list.return_value = _FakeResponse(
        data=_FakeListData(items=[bad, good])
    )
    loaded = gateway.list_project_configs()
    assert list(loaded.keys()) == ["P"]


def test_list_project_configs_recovers_from_invalid_tech_stack_json():
    gateway = _make_gateway()
    record = _FakeRecord(
        fields={
            "项目名": "P",
            "类别": "c",
            "模板版本": "v",
            "架构文档ID": "d",
            "架构文档URL": "u",
            "技术栈JSON": "{not json",
            "设计系统文档ID": "",
        },
        record_id="rec_1",
    )
    gateway.client.bitable.v1.app_table_record.list.return_value = _FakeResponse(
        data=_FakeListData(items=[record])
    )
    loaded = gateway.list_project_configs()
    assert loaded["P"].tech_stack == {}


def test_upsert_project_config_creates_when_no_record_id():
    gateway = _make_gateway()
    created_record = MagicMock()
    created_record.record_id = "rec_new"
    gateway.client.bitable.v1.app_table_record.create.return_value = _FakeResponse(
        data=MagicMock(record=created_record)
    )

    cfg = ProjectConfig(
        category="c",
        template_version="v",
        architecture_doc_id="d",
        architecture_doc_url="u",
        tech_stack={"x": "y"},
    )
    result = gateway.upsert_project_config("MyProj", cfg)

    assert result.bitable_record_id == "rec_new"
    gateway.client.bitable.v1.app_table_record.create.assert_called_once()
    gateway.client.bitable.v1.app_table_record.update.assert_not_called()


def test_upsert_project_config_updates_when_record_id_present():
    gateway = _make_gateway()
    gateway.client.bitable.v1.app_table_record.update.return_value = _FakeResponse(
        data=MagicMock()
    )

    cfg = ProjectConfig(
        category="c",
        template_version="v",
        architecture_doc_id="d",
        architecture_doc_url="u",
        tech_stack={},
        bitable_record_id="rec_existing",
    )
    result = gateway.upsert_project_config("MyProj", cfg)

    assert result.bitable_record_id == "rec_existing"
    gateway.client.bitable.v1.app_table_record.update.assert_called_once()
    gateway.client.bitable.v1.app_table_record.create.assert_not_called()


def test_upsert_project_config_noop_when_table_unconfigured():
    settings = Settings(feishu_app_id="a", feishu_app_secret="b")
    gateway = FeishuGateway.__new__(FeishuGateway)
    gateway.settings = settings
    gateway.client = MagicMock()

    cfg = ProjectConfig(
        category="c", template_version="v",
        architecture_doc_id="d", architecture_doc_url="u",
    )
    result = gateway.upsert_project_config("MyProj", cfg)
    assert result is cfg
    gateway.client.bitable.v1.app_table_record.create.assert_not_called()
    gateway.client.bitable.v1.app_table_record.update.assert_not_called()


def test_initialize_project_triggers_persister():
    """Coordinator service calls the persister hook on initialize_project."""
    from requirement_workflow_v12.coordinator_service import CoordinatorService
    svc = CoordinatorService()
    calls: list[tuple[str, ProjectConfig]] = []

    def persister(project: str, cfg: ProjectConfig) -> ProjectConfig:
        calls.append((project, cfg))
        cfg.bitable_record_id = "rec_from_persister"
        return cfg

    svc.set_project_config_persister(persister)
    svc.initialize_project(
        project="P", category="c", template_version="v",
        architecture_doc_id="d", architecture_doc_url="u", tech_stack={},
    )
    assert len(calls) == 1
    assert calls[0][0] == "P"
    assert svc.project_configs["P"].bitable_record_id == "rec_from_persister"


def test_set_design_system_doc_triggers_persister():
    from requirement_workflow_v12.coordinator_service import CoordinatorService
    svc = CoordinatorService()
    svc.initialize_project(
        project="P", category="c", template_version="v",
        architecture_doc_id="d", architecture_doc_url="u", tech_stack={},
    )
    calls: list[str] = []
    svc.set_project_config_persister(lambda project, cfg: calls.append(project) or cfg)

    svc.set_design_system_doc("P", "ds_doc_1")
    assert calls == ["P"]
    assert svc.project_configs["P"].design_system_doc_id == "ds_doc_1"
