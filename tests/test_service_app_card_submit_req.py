"""Tests for the refactored requirement creation card (project dropdown, no category)."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.service_app import (  # noqa: E402
    CoordinatorRuntimeApp,
    MessageContext,
    OutboundCard,
    OutboundMessage,
)
from requirement_workflow_v12.config import Settings  # noqa: E402
from requirement_workflow_v12.store import JsonStateStore  # noqa: E402
from requirement_workflow_v12.coordinator_service import CoordinatorService  # noqa: E402
from requirement_workflow_v12.project_config import ProjectConfig  # noqa: E402


def _provisioned(category="saas-ai-automation"):
    return ProjectConfig(
        category=category,
        template_version="x.v1",
        architecture_doc_id="d",
        architecture_doc_url="u",
        bootstrap_status="PROVISIONED",
        project_status="PROVISIONED",
    )


def _bootstrapping():
    return ProjectConfig(
        category="saas-ai-automation",
        template_version="x.v1",
        architecture_doc_id="",
        architecture_doc_url="",
        bootstrap_status="BOOTSTRAPPING",
        project_status="BOOTSTRAPPING",
    )


def _make_app(tmp_path, project_configs):
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
    service = CoordinatorService()
    service.project_configs = dict(project_configs)
    store = JsonStateStore(settings.state_store_path)
    gateway = MagicMock()
    gateway.list_project_configs.return_value = project_configs
    with patch.object(Settings, "validate_runtime", return_value=None):
        settings.validate_runtime = lambda: None
        app = CoordinatorRuntimeApp(
            settings=settings, store=store, service=service, gateway=gateway,
        )
    return app


def test_req_card_project_is_select_static_with_provisioned_options(tmp_path):
    app = _make_app(tmp_path, {
        "test3": _provisioned(),
        "test4": _provisioned(),
        "test_bootstrapping": _bootstrapping(),
    })
    ctx = MessageContext(
        message_id="m1", chat_id="oc_x", chat_type="p2p",
        user_id="ou_alice", sender_name="Alice", text="/create req",
    )
    card = app._build_requirement_creation_card(ctx)
    form = card["body"]["elements"][0]
    project_field = next(e for e in form["elements"] if e.get("name") == "project")
    assert project_field["tag"] == "select_static"
    option_values = {o["value"] for o in project_field["options"]}
    # Only PROVISIONED projects listed
    assert option_values == {"test3", "test4"}


def test_req_card_omits_category_field(tmp_path):
    app = _make_app(tmp_path, {"test3": _provisioned()})
    ctx = MessageContext(
        message_id="m1", chat_id="oc_x", chat_type="p2p",
        user_id="ou_alice", sender_name="Alice", text="/create req",
    )
    card = app._build_requirement_creation_card(ctx)
    form = card["body"]["elements"][0]
    names = [e.get("name") for e in form["elements"] if isinstance(e, dict)]
    assert "category" not in names


def test_create_req_with_no_provisioned_projects_rejects_without_card(tmp_path):
    app = _make_app(tmp_path, {})
    ctx = MessageContext(
        message_id="m1", chat_id="oc_x", chat_type="p2p",
        user_id="ou_alice", sender_name="Alice", text="/create req",
    )
    msgs = app.handle_text_message(ctx)
    # Only a text reply, no card
    assert all(not isinstance(m, OutboundCard) for m in msgs)
    text = "\n".join(getattr(m, "text", "") for m in msgs if isinstance(m, OutboundMessage))
    assert "/create project" in text


def test_create_req_with_only_bootstrapping_project_rejects_without_card(tmp_path):
    app = _make_app(tmp_path, {"test_bb": _bootstrapping()})
    ctx = MessageContext(
        message_id="m1", chat_id="oc_x", chat_type="p2p",
        user_id="ou_alice", sender_name="Alice", text="/create req",
    )
    msgs = app.handle_text_message(ctx)
    assert all(not isinstance(m, OutboundCard) for m in msgs)


def test_submit_requirement_rejects_bootstrapping_project(tmp_path):
    """If the selected project's status regressed to non-PROVISIONED, reject the submit."""
    app = _make_app(tmp_path, {"test_bb": _bootstrapping()})
    payload = {
        "operator": {"open_id": "ou_alice", "name": "Alice"},
        "context": {"open_chat_id": "oc_x", "open_message_id": "om_1"},
        "action": {
            "value": {"action": "submit_create_requirement", "creation_chat_id": "oc_x"},
            "form_value": {
                "project": "test_bb",
                "name": "some req",
                "summary": "some summary",
            },
        },
    }
    status, resp = app._handle_card_action_payload(payload)
    assert status == 200
    assert resp.get("toast", {}).get("type") == "error"
    # No requirement was created
    assert len(app.service.requirements) == 0
