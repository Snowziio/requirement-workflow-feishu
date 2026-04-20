"""Unit tests for /create project slash command parser + routing."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.service_app import parse_create_project_command  # noqa: E402


def test_parse_create_project_matches_bare_command():
    cmd = parse_create_project_command("/create project")
    assert cmd is not None


def test_parse_create_project_matches_with_trailing_whitespace():
    cmd = parse_create_project_command("/create project   ")
    assert cmd is not None


def test_parse_create_project_rejects_trailing_args():
    """Tightened: any trailing arg (project name, flag) is no longer accepted."""
    assert parse_create_project_command("/create project test3") is None
    assert parse_create_project_command(
        "/create project test3 --category saas-ai-automation"
    ) is None
    assert parse_create_project_command("/create project --category x") is None


def test_parse_create_project_returns_none_for_other_text():
    assert parse_create_project_command("随便聊聊") is None
    assert parse_create_project_command("/create req test3 foo") is None


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


def test_handle_create_project_bare_command_returns_card(tmp_path):
    """`/create project` (no flags) returns the project creation card, does NOT run Bootstrap."""
    from requirement_workflow_v12.service_app import MessageContext, OutboundCard

    app, bootstrap_svc = _make_app(tmp_path)
    ctx = MessageContext(
        message_id="m1", chat_id="oc_chat_x", chat_type="p2p",
        user_id="ou_alice", sender_name="Alice", text="/create project",
    )
    msgs = app.handle_text_message(ctx)
    bootstrap_svc.run.assert_not_called()
    assert len(msgs) == 1
    assert isinstance(msgs[0], OutboundCard)
    card = msgs[0].card
    form = card["body"]["elements"][0]
    assert form["tag"] == "form"


def test_handle_create_project_bare_command_in_group(tmp_path):
    from requirement_workflow_v12.service_app import MessageContext, OutboundCard

    app, bootstrap_svc = _make_app(tmp_path)
    ctx = MessageContext(
        message_id="m1", chat_id="oc_group_y", chat_type="group",
        user_id="ou_bob", sender_name="Bob", text="/create project",
    )
    msgs = app.handle_text_message(ctx)
    bootstrap_svc.run.assert_not_called()
    assert isinstance(msgs[0], OutboundCard)
    assert msgs[0].receive_id == "oc_group_y"


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
        text="/create project",
    )
    app._on_message_receive(event)
    app._on_message_receive(event)
    # The slash command only renders a card now; Bootstrap must never be
    # invoked from the text-message path.
    bootstrap_svc.run.assert_not_called()
    # The card is sent exactly once despite two identical deliveries.
    assert app.gateway.send_card.call_count == 1


def test_on_message_receive_still_allows_distinct_message_ids(tmp_path):
    """Different message_ids must both be processed (two cards, zero Bootstrap calls)."""
    app, bootstrap_svc = _make_app(tmp_path)
    app._on_message_receive(_fake_receive_event(
        message_id="msg_a", chat_id="oc_abc", text="/create project",
    ))
    app._on_message_receive(_fake_receive_event(
        message_id="msg_b", chat_id="oc_abc", text="/create project",
    ))
    bootstrap_svc.run.assert_not_called()
    assert app.gateway.send_card.call_count == 2


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
