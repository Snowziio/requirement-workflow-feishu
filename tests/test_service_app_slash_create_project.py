"""Unit tests for /create project slash command parser + routing."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.service_app import parse_create_project_command  # noqa: E402


def test_parse_create_project_happy_path():
    cmd = parse_create_project_command(
        "/create project test3 --category saas-ai-automation --owner ou_abc"
    )
    assert cmd is not None
    assert cmd.project == "test3"
    assert cmd.category == "saas-ai-automation"
    assert cmd.owner_user_id == "ou_abc"
    assert cmd.resume is False


def test_parse_create_project_resume_flag():
    cmd = parse_create_project_command(
        "/create project test3 --category saas-ai-automation --owner ou_abc --resume"
    )
    assert cmd is not None
    assert cmd.resume is True


def test_parse_create_project_returns_none_for_other_text():
    assert parse_create_project_command("随便聊聊") is None
    assert parse_create_project_command("/create req test3 foo") is None


def test_parse_create_project_missing_owner_is_allowed():
    """Owner is optional — handler defaults it to the sender's open_id."""
    cmd = parse_create_project_command(
        "/create project test3 --category saas-ai-automation"
    )
    assert cmd is not None
    assert cmd.project == "test3"
    assert cmd.category == "saas-ai-automation"
    assert cmd.owner_user_id == ""


def test_parse_create_project_missing_category_is_allowed():
    """Category is optional at parse-time — handler validates and lists choices."""
    cmd = parse_create_project_command("/create project test3")
    assert cmd is not None
    assert cmd.project == "test3"
    assert cmd.category == ""
    assert cmd.owner_user_id == ""


def test_handle_text_message_routes_create_project_triggers_bootstrap(tmp_path):
    from unittest.mock import MagicMock, patch

    from requirement_workflow_v12.service_app import (
        CoordinatorRuntimeApp,
        MessageContext,
    )
    from requirement_workflow_v12.config import Settings
    from requirement_workflow_v12.store import JsonStateStore
    from requirement_workflow_v12.coordinator_service import CoordinatorService
    from requirement_workflow_v12.project_bootstrap.types import BootstrapResult

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

    bootstrap_svc = MagicMock()
    bootstrap_svc.run.return_value = BootstrapResult(
        project="test3",
        github_repo_url="https://github.com/Snowziio/test3",
        architecture_doc_id="doc_x",
        architecture_doc_url="https://feishu.example/doc_x",
        feishu_chat_id="oc_test3",
        template_version="saas-ai-automation.v1",
    )

    service = CoordinatorService()
    store = JsonStateStore(settings.state_store_path)
    gateway = MagicMock()
    gateway.list_project_configs.return_value = {}
    with patch.object(Settings, "validate_runtime", return_value=None):
        settings.validate_runtime = lambda: None
        app = CoordinatorRuntimeApp(
            settings=settings, store=store, service=service, gateway=gateway,
            project_bootstrap_service=bootstrap_svc,
        )

    ctx = MessageContext(
        message_id="m1",
        chat_id="group_c",
        chat_type="group",
        user_id="ou_alice",
        sender_name="Alice",
        text="/create project test3 --category saas-ai-automation --owner ou_alice",
    )
    messages = app.handle_text_message(ctx)
    bootstrap_svc.run.assert_called_once()
    req = bootstrap_svc.run.call_args.args[0]
    assert req.project == "test3"
    assert req.category == "saas-ai-automation"
    assert req.owner_user_id == "ou_alice"
    assert req.resume is False
    assert any("test3" in getattr(m, "text", "") for m in messages)


def _make_app(tmp_path):
    """Helper: minimal CoordinatorRuntimeApp with mocked bootstrap service."""
    from unittest.mock import MagicMock, patch

    from requirement_workflow_v12.service_app import CoordinatorRuntimeApp
    from requirement_workflow_v12.config import Settings
    from requirement_workflow_v12.store import JsonStateStore
    from requirement_workflow_v12.coordinator_service import CoordinatorService
    from requirement_workflow_v12.project_bootstrap.types import BootstrapResult

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

    bootstrap_svc = MagicMock()
    bootstrap_svc.run.return_value = BootstrapResult(
        project="test3",
        github_repo_url="https://github.com/Snowziio/test3",
        architecture_doc_id="doc_x",
        architecture_doc_url="https://feishu.example/doc_x",
        feishu_chat_id="oc_test3",
        template_version="saas-ai-automation.v1",
    )
    service = CoordinatorService()
    store = JsonStateStore(settings.state_store_path)
    gateway = MagicMock()
    gateway.list_project_configs.return_value = {}
    with patch.object(Settings, "validate_runtime", return_value=None):
        settings.validate_runtime = lambda: None
        app = CoordinatorRuntimeApp(
            settings=settings, store=store, service=service, gateway=gateway,
            project_bootstrap_service=bootstrap_svc,
        )
    return app, bootstrap_svc


def test_handle_create_project_owner_defaults_to_sender(tmp_path):
    """Without --owner, the sender's open_id is used."""
    from requirement_workflow_v12.service_app import MessageContext

    app, bootstrap_svc = _make_app(tmp_path)
    ctx = MessageContext(
        message_id="m1", chat_id="group_c", chat_type="group",
        user_id="ou_alice", sender_name="Alice",
        text="/create project test3 --category saas-ai-automation",
    )
    app.handle_text_message(ctx)
    req = bootstrap_svc.run.call_args.args[0]
    assert req.owner_user_id == "ou_alice"


def test_handle_create_project_missing_category_lists_choices(tmp_path):
    """Without --category, bot replies with the available list and does not run bootstrap."""
    from requirement_workflow_v12.service_app import MessageContext

    app, bootstrap_svc = _make_app(tmp_path)
    ctx = MessageContext(
        message_id="m1", chat_id="group_c", chat_type="group",
        user_id="ou_alice", sender_name="Alice",
        text="/create project test3",
    )
    msgs = app.handle_text_message(ctx)
    bootstrap_svc.run.assert_not_called()
    text = "\n".join(getattr(m, "text", "") for m in msgs)
    assert "saas-ai-automation" in text
    assert "category" in text.lower() or "类目" in text or "可选" in text


def test_handle_create_project_invalid_category_lists_choices(tmp_path):
    """Unknown --category value is rejected with the available list."""
    from requirement_workflow_v12.service_app import MessageContext

    app, bootstrap_svc = _make_app(tmp_path)
    ctx = MessageContext(
        message_id="m1", chat_id="group_c", chat_type="group",
        user_id="ou_alice", sender_name="Alice",
        text="/create project test3 --category not-a-real-category",
    )
    msgs = app.handle_text_message(ctx)
    bootstrap_svc.run.assert_not_called()
    text = "\n".join(getattr(m, "text", "") for m in msgs)
    assert "saas-ai-automation" in text
    assert "not-a-real-category" in text
