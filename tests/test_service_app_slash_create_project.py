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


def test_handle_create_project_works_in_p2p_dm(tmp_path):
    """In a DM (p2p), /create project should still route into Bootstrap."""
    from requirement_workflow_v12.service_app import MessageContext

    app, bootstrap_svc = _make_app(tmp_path)
    ctx = MessageContext(
        message_id="m1", chat_id="p2p_chat_alice", chat_type="p2p",
        user_id="ou_alice", sender_name="Alice",
        text="/create project test4 --category saas-ai-automation",
    )
    msgs = app.handle_text_message(ctx)
    bootstrap_svc.run.assert_called_once()
    text = "\n".join(getattr(m, "text", "") for m in msgs)
    assert "test4" in text or "test3" in text  # mock returns test3
    assert "当前没有激活的需求" not in text


def test_handle_create_project_works_in_arbitrary_group(tmp_path):
    """A non-creation group should also accept /create project."""
    from requirement_workflow_v12.service_app import MessageContext

    app, bootstrap_svc = _make_app(tmp_path)
    ctx = MessageContext(
        message_id="m1", chat_id="oc_some_other_group", chat_type="group",
        user_id="ou_alice", sender_name="Alice",
        text="/create project test4 --category saas-ai-automation",
    )
    app.handle_text_message(ctx)
    bootstrap_svc.run.assert_called_once()


def test_handle_create_project_strips_at_mention_prefix(tmp_path):
    """When user @-mentions the bot, Feishu prepends '@_user_<id> '; we must strip it."""
    from requirement_workflow_v12.service_app import MessageContext

    app, bootstrap_svc = _make_app(tmp_path)
    ctx = MessageContext(
        message_id="m1", chat_id="oc_some_group", chat_type="group",
        user_id="ou_alice", sender_name="Alice",
        text="@_user_1 /create project test4 --category saas-ai-automation",
    )
    app.handle_text_message(ctx)
    bootstrap_svc.run.assert_called_once()


def test_handle_create_project_strips_multiple_at_mention_prefixes(tmp_path):
    """Multiple stacked mentions should all be stripped."""
    from requirement_workflow_v12.service_app import MessageContext

    app, bootstrap_svc = _make_app(tmp_path)
    ctx = MessageContext(
        message_id="m1", chat_id="oc_some_group", chat_type="group",
        user_id="ou_alice", sender_name="Alice",
        text="@_user_1 @_user_2 /create project test4 --category saas-ai-automation",
    )
    app.handle_text_message(ctx)
    bootstrap_svc.run.assert_called_once()


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


def _fake_receive_event(*, message_id: str, chat_id: str, text: str):
    """Build a shim matching what _extract_message_context reads off P2ImMessageReceiveV1."""
    from types import SimpleNamespace
    import json as _json

    return SimpleNamespace(
        event=SimpleNamespace(
            sender=SimpleNamespace(sender_id=SimpleNamespace(open_id="ou_alice")),
            message=SimpleNamespace(
                chat_id=chat_id,
                chat_type="group",
                message_id=message_id,
                thread_id="",
                message_type="text",
                content=_json.dumps({"text": text}),
            ),
        )
    )


def test_on_message_receive_dedupes_by_message_id(tmp_path):
    """Duplicate Feishu deliveries with the same message_id must not invoke the handler twice."""
    app, bootstrap_svc = _make_app(tmp_path)
    event = _fake_receive_event(
        message_id="msg_dup_42",
        chat_id="oc_abc",
        text="/create project test3 --category saas-ai-automation",
    )
    app._on_message_receive(event)
    app._on_message_receive(event)
    # Bootstrap must run exactly once despite two identical deliveries.
    bootstrap_svc.run.assert_called_once()
    # Gateway.send_text must also be called exactly once.
    assert app.gateway.send_text.call_count == 1


def test_on_message_receive_still_allows_distinct_message_ids(tmp_path):
    """Different message_ids must both be processed."""
    app, bootstrap_svc = _make_app(tmp_path)
    app._on_message_receive(_fake_receive_event(
        message_id="msg_a", chat_id="oc_abc",
        text="/create project test3 --category saas-ai-automation",
    ))
    app._on_message_receive(_fake_receive_event(
        message_id="msg_b", chat_id="oc_abc",
        text="/create project test3 --category saas-ai-automation --resume",
    ))
    assert bootstrap_svc.run.call_count == 2


def test_mark_message_seen_evicts_oldest_when_full(tmp_path):
    """Bounded cache: old ids get evicted to keep memory footprint fixed."""
    app, _ = _make_app(tmp_path)
    app._seen_message_ids_max = 3
    assert app._mark_message_seen("a") is True
    assert app._mark_message_seen("b") is True
    assert app._mark_message_seen("c") is True
    assert app._mark_message_seen("d") is True  # evicts 'a'
    # 'a' was evicted, so it looks new again
    assert app._mark_message_seen("a") is True
    # 'd' is still cached
    assert app._mark_message_seen("d") is False
