"""Unit tests for /create req slash command parser + routing."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.service_app import parse_create_req_command  # noqa: E402


def test_parse_create_req_matches_bare_command():
    cmd = parse_create_req_command("/create req")
    assert cmd is not None


def test_parse_create_req_rejects_trailing_args():
    assert parse_create_req_command("/create req test3 foo") is None
    assert parse_create_req_command("/create req test3 foo --summary bar") is None
    assert parse_create_req_command("/create req --project x") is None


def test_parse_create_req_returns_none_for_other_text():
    assert parse_create_req_command("随便聊聊") is None
    assert parse_create_req_command("/create project test3") is None


def _build_runtime_app(tmp_path, *, project_configs=None):
    from unittest.mock import MagicMock, patch

    from requirement_workflow_v12.service_app import (
        CoordinatorRuntimeApp,
        MessageContext,
    )
    from requirement_workflow_v12.config import Settings
    from requirement_workflow_v12.store import JsonStateStore
    from requirement_workflow_v12.coordinator_service import CoordinatorService

    settings = MagicMock(spec=Settings)
    settings.state_store_path = str(tmp_path / "state.json")
    settings.creation_group_chat_id = "group_c"
    settings.openclaw_callback_secret = ""
    settings.openclaw_callback_ttl_seconds = 600
    settings.github_token = ""
    settings.feishu_user_id_type = "open_id"
    settings.github_template_owner = "Snowziio"
    settings.github_template_repo = "Template-repository"
    settings.github_org_owner = "Snowziio"

    gateway = MagicMock()
    gateway.list_project_configs.return_value = project_configs or {}
    gateway.create_requirement_record.return_value = None
    gateway.create_requirement_document.return_value = None
    gateway.create_project_group.side_effect = Exception("skip")
    gateway.bitable_url.return_value = ""

    service = CoordinatorService()
    service.project_configs = dict(gateway.list_project_configs())
    store = JsonStateStore(settings.state_store_path)
    with patch.object(Settings, "validate_runtime", return_value=None):
        settings.validate_runtime = lambda: None
        app = CoordinatorRuntimeApp(
            settings=settings, store=store, service=service, gateway=gateway,
        )
    return app, service, gateway, MessageContext


def test_handle_text_message_routes_create_req_command(tmp_path):
    from requirement_workflow_v12.project_config import ProjectConfig

    project_configs = {
        "test3": ProjectConfig(
            category="saas-ai-automation",
            template_version="saas-ai-automation.v1",
            architecture_doc_id="doc_x",
            architecture_doc_url="https://example/doc_x",
            bootstrap_status="PROVISIONED",
            project_status="PROVISIONED",
        ),
    }
    app, service, gateway, MessageContext = _build_runtime_app(
        tmp_path, project_configs=project_configs
    )

    ctx = MessageContext(
        message_id="m1",
        chat_id="group_c",
        chat_type="group",
        user_id="ou_creator",
        sender_name="Alice",
        text="/create req test3 会话鉴权",
    )
    messages = app.handle_text_message(ctx)
    assert len(messages) >= 1
    reqs = list(service.requirements.values())
    assert any(r.project == "test3" and r.name == "会话鉴权" for r in reqs)


def test_handle_text_message_rejects_free_text_creation_in_group(tmp_path):
    app, _, _, MessageContext = _build_runtime_app(tmp_path)

    ctx = MessageContext(
        message_id="m1",
        chat_id="group_c",
        chat_type="group",
        user_id="u1",
        sender_name="Alice",
        text="创建需求",
    )
    messages = app.handle_text_message(ctx)
    assert len(messages) == 1
    text = getattr(messages[0], "text", "")
    assert "/create req" in text
