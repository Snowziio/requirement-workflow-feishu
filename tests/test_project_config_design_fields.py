"""ProjectConfig design-related field tests."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def _minimal_data():
    return {
        "category": "enterprise-app",
        "template_version": "enterprise-app.v1",
        "architecture_doc_id": "doc1",
        "architecture_doc_url": "https://feishu.example/docx/doc1",
    }


def test_project_config_new_design_fields_default_empty():
    from requirement_workflow_v12.project_config import ProjectConfig
    cfg = ProjectConfig(**_minimal_data())
    assert cfg.claude_design_project_url == ""
    assert cfg.frontend_subpath == ""
    assert cfg.frontend_tech_stack == {}


def test_project_config_from_dict_reads_design_fields():
    from requirement_workflow_v12.project_config import ProjectConfig
    data = _minimal_data()
    data["claude_design_project_url"] = "https://claude.ai/design/p/xyz"
    data["frontend_subpath"] = "src/myproj_webapp"
    data["frontend_tech_stack"] = {"framework": "React 18", "build": "Vite 5.x"}
    cfg = ProjectConfig.from_dict(data)
    assert cfg.claude_design_project_url == "https://claude.ai/design/p/xyz"
    assert cfg.frontend_subpath == "src/myproj_webapp"
    assert cfg.frontend_tech_stack == {"framework": "React 18", "build": "Vite 5.x"}


def test_project_config_from_dict_missing_design_fields_default_gracefully():
    from requirement_workflow_v12.project_config import ProjectConfig
    cfg = ProjectConfig.from_dict(_minimal_data())
    assert cfg.claude_design_project_url == ""
    assert cfg.frontend_subpath == ""
    assert cfg.frontend_tech_stack == {}


def test_project_config_from_dict_tolerates_non_dict_frontend_tech_stack():
    """Bitable may return None or a string if parse fails; coerce to empty dict."""
    from requirement_workflow_v12.project_config import ProjectConfig
    data = _minimal_data()
    data["frontend_tech_stack"] = None
    cfg = ProjectConfig.from_dict(data)
    assert cfg.frontend_tech_stack == {}


def test_feishu_gateway_has_design_field_constants():
    """3 new Bitable field name constants must be defined."""
    from requirement_workflow_v12.bitable_schema import (
        PROJECT_CONFIG_FIELD_CLAUDE_DESIGN_PROJECT_URL,
        PROJECT_CONFIG_FIELD_FRONTEND_SUBPATH,
        PROJECT_CONFIG_FIELD_FRONTEND_TECH_STACK_JSON,
    )
    assert PROJECT_CONFIG_FIELD_CLAUDE_DESIGN_PROJECT_URL
    assert PROJECT_CONFIG_FIELD_FRONTEND_SUBPATH
    assert PROJECT_CONFIG_FIELD_FRONTEND_TECH_STACK_JSON


def test_feishu_gateway_reads_design_fields_from_bitable_row():
    """list_project_configs parses the 3 new field values correctly."""
    from unittest.mock import MagicMock, patch
    from requirement_workflow_v12 import feishu_gateway as fg_module
    from requirement_workflow_v12.feishu_gateway import FeishuGateway
    from requirement_workflow_v12.bitable_schema import (
        PROJECT_CONFIG_FIELD_PROJECT,
        PROJECT_CONFIG_FIELD_CATEGORY,
        PROJECT_CONFIG_FIELD_TEMPLATE_VERSION,
        PROJECT_CONFIG_FIELD_ARCH_DOC_ID,
        PROJECT_CONFIG_FIELD_ARCH_DOC_URL,
        PROJECT_CONFIG_FIELD_CLAUDE_DESIGN_PROJECT_URL,
        PROJECT_CONFIG_FIELD_FRONTEND_SUBPATH,
        PROJECT_CONFIG_FIELD_FRONTEND_TECH_STACK_JSON,
    )
    gateway = FeishuGateway.__new__(FeishuGateway)
    settings = MagicMock()
    settings.feishu_bitable_app_token = "t"
    settings.feishu_bitable_project_configs_table_id = "tbl"
    gateway.settings = settings
    gateway.client = MagicMock()

    fake_fields = {
        PROJECT_CONFIG_FIELD_PROJECT: "testp",
        PROJECT_CONFIG_FIELD_CATEGORY: "enterprise-app",
        PROJECT_CONFIG_FIELD_TEMPLATE_VERSION: "enterprise-app.v1",
        PROJECT_CONFIG_FIELD_ARCH_DOC_ID: "d1",
        PROJECT_CONFIG_FIELD_ARCH_DOC_URL: "u1",
        PROJECT_CONFIG_FIELD_CLAUDE_DESIGN_PROJECT_URL: "https://claude.ai/design/p/abc",
        PROJECT_CONFIG_FIELD_FRONTEND_SUBPATH: "src/testp_webapp",
        PROJECT_CONFIG_FIELD_FRONTEND_TECH_STACK_JSON: '{"framework": "React 18"}',
    }
    fake_item = MagicMock(record_id="rec1", fields=fake_fields)
    fake_data = MagicMock(items=[fake_item], page_token=None, has_more=False)
    fake_response = MagicMock(data=fake_data, code=0, msg="ok")
    fake_response.success.return_value = True
    gateway.client.bitable.v1.app_table_record.list.return_value = fake_response

    # ListAppTableRecordRequest is optional-imported; stub its builder chain.
    fake_builder = MagicMock()
    fake_builder.app_token.return_value = fake_builder
    fake_builder.table_id.return_value = fake_builder
    fake_builder.page_size.return_value = fake_builder
    fake_builder.page_token.return_value = fake_builder
    fake_builder.build.return_value = MagicMock()
    fake_request_cls = MagicMock()
    fake_request_cls.builder.return_value = fake_builder
    with patch.object(fg_module, "ListAppTableRecordRequest", fake_request_cls):
        configs = gateway.list_project_configs()
    assert len(configs) >= 1
    cfg = configs["testp"]
    assert cfg.claude_design_project_url == "https://claude.ai/design/p/abc"
    assert cfg.frontend_subpath == "src/testp_webapp"
    assert cfg.frontend_tech_stack == {"framework": "React 18"}


def test_feishu_gateway_writes_design_fields_to_bitable_row():
    """_project_config_to_fields serializes the 3 new fields correctly."""
    from requirement_workflow_v12.feishu_gateway import FeishuGateway
    from requirement_workflow_v12.bitable_schema import (
        PROJECT_CONFIG_FIELD_CLAUDE_DESIGN_PROJECT_URL,
        PROJECT_CONFIG_FIELD_FRONTEND_SUBPATH,
        PROJECT_CONFIG_FIELD_FRONTEND_TECH_STACK_JSON,
    )
    from requirement_workflow_v12.project_config import ProjectConfig
    import json as _json

    gateway = FeishuGateway.__new__(FeishuGateway)
    cfg = ProjectConfig(**_minimal_data())
    cfg.claude_design_project_url = "https://claude.ai/design/p/xyz"
    cfg.frontend_subpath = "src/myproj_webapp"
    cfg.frontend_tech_stack = {"framework": "React 18", "build": "Vite 5.x"}

    fields = gateway._project_config_to_fields(cfg, "myproj")
    assert fields[PROJECT_CONFIG_FIELD_CLAUDE_DESIGN_PROJECT_URL] == "https://claude.ai/design/p/xyz"
    assert fields[PROJECT_CONFIG_FIELD_FRONTEND_SUBPATH] == "src/myproj_webapp"
    parsed = _json.loads(fields[PROJECT_CONFIG_FIELD_FRONTEND_TECH_STACK_JSON])
    assert parsed == {"framework": "React 18", "build": "Vite 5.x"}
