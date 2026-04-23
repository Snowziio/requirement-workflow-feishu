"""Tests for the bind_claude_design_project card action."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.service_app import CoordinatorRuntimeApp
from requirement_workflow_v12.project_config import ProjectConfig


def _app_with_config(project: str, cfg: ProjectConfig) -> CoordinatorRuntimeApp:
    app = CoordinatorRuntimeApp.__new__(CoordinatorRuntimeApp)
    app.service = MagicMock()
    app.service.project_configs = {project: cfg}
    app.gateway = MagicMock()
    return app


def _base_cfg() -> ProjectConfig:
    return ProjectConfig(
        category="enterprise-app",
        template_version="enterprise-app.v1",
        architecture_doc_id="d",
        architecture_doc_url="u",
    )


def test_bind_claude_design_updates_project_config():
    cfg = _base_cfg()
    app = _app_with_config("testp", cfg)

    payload = {
        "action": {
            "value": {"action": "bind_claude_design_project", "project": "testp"},
            "form_value": {"claude_design_project_url": "https://claude.ai/design/p/xyz"},
        },
        "operator": {"operator_id": {"user_id": "u1"}},
    }
    status, resp = app._handle_card_action_payload(payload)
    assert status == 200
    assert resp.get("toast", {}).get("type") == "success"
    assert app.service.project_configs["testp"].claude_design_project_url == "https://claude.ai/design/p/xyz"
    app.gateway.upsert_project_config.assert_called_once()


def test_bind_claude_design_rejects_missing_project():
    app = CoordinatorRuntimeApp.__new__(CoordinatorRuntimeApp)
    app.service = MagicMock()
    app.service.project_configs = {}
    app.gateway = MagicMock()
    payload = {
        "action": {
            "value": {"action": "bind_claude_design_project"},
            "form_value": {"claude_design_project_url": "https://claude.ai/design/p/xyz"},
        },
        "operator": {},
    }
    status, resp = app._handle_card_action_payload(payload)
    assert status == 200
    assert resp.get("toast", {}).get("type") == "error"


def test_bind_claude_design_rejects_empty_url():
    cfg = _base_cfg()
    app = _app_with_config("testp", cfg)
    payload = {
        "action": {
            "value": {"action": "bind_claude_design_project", "project": "testp"},
            "form_value": {"claude_design_project_url": ""},
        },
        "operator": {},
    }
    status, resp = app._handle_card_action_payload(payload)
    assert status == 200
    assert resp.get("toast", {}).get("type") == "error"
    app.gateway.upsert_project_config.assert_not_called()


def test_bind_claude_design_rejects_non_claude_ai_url():
    cfg = _base_cfg()
    app = _app_with_config("testp", cfg)
    payload = {
        "action": {
            "value": {"action": "bind_claude_design_project", "project": "testp"},
            "form_value": {"claude_design_project_url": "https://example.com/design/xyz"},
        },
        "operator": {},
    }
    status, resp = app._handle_card_action_payload(payload)
    assert status == 200
    assert resp.get("toast", {}).get("type") == "error"
    app.gateway.upsert_project_config.assert_not_called()


def test_bind_claude_design_rejects_unknown_project():
    app = CoordinatorRuntimeApp.__new__(CoordinatorRuntimeApp)
    app.service = MagicMock()
    app.service.project_configs = {}
    app.gateway = MagicMock()
    payload = {
        "action": {
            "value": {"action": "bind_claude_design_project", "project": "unknown"},
            "form_value": {"claude_design_project_url": "https://claude.ai/design/p/xyz"},
        },
        "operator": {},
    }
    status, resp = app._handle_card_action_payload(payload)
    assert status == 200
    assert resp.get("toast", {}).get("type") == "error"


def test_bind_claude_design_handles_upsert_failure_and_rollback():
    cfg = _base_cfg()
    app = _app_with_config("testp", cfg)
    app.gateway.upsert_project_config.side_effect = RuntimeError("bitable 500")
    payload = {
        "action": {
            "value": {"action": "bind_claude_design_project", "project": "testp"},
            "form_value": {"claude_design_project_url": "https://claude.ai/design/p/xyz"},
        },
        "operator": {},
    }
    status, resp = app._handle_card_action_payload(payload)
    assert status == 200
    assert resp.get("toast", {}).get("type") == "error"
    # In-memory rollback: ProjectConfig URL should be reverted to empty
    assert app.service.project_configs["testp"].claude_design_project_url == ""
