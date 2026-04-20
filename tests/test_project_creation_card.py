"""Unit tests for _build_project_creation_card and _extract_project_form_payload."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.service_app import (  # noqa: E402
    CoordinatorRuntimeApp,
    KNOWN_PROJECT_CATEGORIES,
    MessageContext,
)
from requirement_workflow_v12.config import Settings
from requirement_workflow_v12.store import JsonStateStore
from requirement_workflow_v12.coordinator_service import CoordinatorService


def _make_app(tmp_path):
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
    store = JsonStateStore(settings.state_store_path)
    gateway = MagicMock()
    gateway.list_project_configs.return_value = {}
    with patch.object(Settings, "validate_runtime", return_value=None):
        settings.validate_runtime = lambda: None
        app = CoordinatorRuntimeApp(
            settings=settings, store=store, service=service, gateway=gateway,
        )
    return app


def test_project_card_has_required_fields(tmp_path):
    app = _make_app(tmp_path)
    ctx = MessageContext(
        message_id="m1", chat_id="oc_chat", chat_type="p2p",
        user_id="ou_alice", sender_name="Alice", text="/create project",
    )
    card = app._build_project_creation_card(ctx)
    form = card["body"]["elements"][0]
    assert form["tag"] == "form"
    names = [e.get("name") for e in form["elements"] if isinstance(e, dict)]
    # Required
    assert "project" in names
    assert "category" in names
    # Optional
    for optional in ("display_name", "brief", "github_username", "tech_stack"):
        assert optional in names, f"missing optional field {optional!r}"


def test_project_card_category_dropdown_has_all_known_categories(tmp_path):
    app = _make_app(tmp_path)
    ctx = MessageContext(
        message_id="m1", chat_id="oc_chat", chat_type="p2p",
        user_id="ou_alice", sender_name="Alice", text="/create project",
    )
    card = app._build_project_creation_card(ctx)
    form = card["body"]["elements"][0]
    category = next(e for e in form["elements"] if e.get("name") == "category")
    assert category["tag"] == "select_static"
    option_values = {o["value"] for o in category["options"]}
    assert option_values == set(KNOWN_PROJECT_CATEGORIES)


def test_project_card_select_static_has_no_label_property(tmp_path):
    """Feishu v2 `select_static` rejects the `label` property (error 200621).

    Labels must be rendered as a preceding `div` element, not as a
    property on the select_static itself.
    """
    app = _make_app(tmp_path)
    ctx = MessageContext(
        message_id="m1", chat_id="oc_chat", chat_type="p2p",
        user_id="ou_alice", sender_name="Alice", text="/create project",
    )
    card = app._build_project_creation_card(ctx)
    form = card["body"]["elements"][0]
    for element in form["elements"]:
        if isinstance(element, dict) and element.get("tag") == "select_static":
            assert "label" not in element, (
                f"select_static {element.get('name')!r} must not carry `label`"
            )


def test_project_card_submit_button_has_correct_action(tmp_path):
    app = _make_app(tmp_path)
    ctx = MessageContext(
        message_id="m1", chat_id="oc_chat_x", chat_type="group",
        user_id="ou_alice", sender_name="Alice", text="/create project",
    )
    card = app._build_project_creation_card(ctx)
    form = card["body"]["elements"][0]
    submit = next(e for e in form["elements"] if e.get("tag") == "button")
    assert submit["form_action_type"] == "submit"
    behavior = submit["behaviors"][0]
    assert behavior["type"] == "callback"
    assert behavior["value"]["action"] == "submit_create_project"
    # creator_chat_id is carried through the card for the submit handler.
    assert behavior["value"]["creator_chat_id"] == "oc_chat_x"


def test_extract_project_form_payload_happy_path(tmp_path):
    app = _make_app(tmp_path)
    payload = {
        "operator": {"open_id": "ou_alice"},
        "context": {"open_chat_id": "oc_chat_x"},
        "action": {
            "value": {"action": "submit_create_project", "creator_chat_id": "oc_chat_x"},
            "form_value": {
                "project": "  test5 ",
                "category": "saas-ai-automation",
                "display_name": "Test 5",
                "brief": "解决 X",
                "github_username": "alice",
                "tech_stack": "FastAPI",
            },
        },
    }
    form = app._extract_project_form_payload(
        payload, user_id="ou_alice", user_name="Alice",
    )
    assert form is not None
    assert form.project == "test5"  # trimmed
    assert form.category == "saas-ai-automation"
    assert form.owner_user_id == "ou_alice"
    assert form.creator_chat_id == "oc_chat_x"
    assert form.display_name == "Test 5"
    assert form.brief == "解决 X"
    assert form.github_username == "alice"
    assert form.tech_stack == "FastAPI"


def test_extract_project_form_payload_optional_fields_default_empty(tmp_path):
    app = _make_app(tmp_path)
    payload = {
        "operator": {"open_id": "ou_alice"},
        "context": {"open_chat_id": "oc_chat_x"},
        "action": {
            "value": {"action": "submit_create_project", "creator_chat_id": "oc_chat_x"},
            "form_value": {"project": "test5", "category": "saas-ai-automation"},
        },
    }
    form = app._extract_project_form_payload(
        payload, user_id="ou_alice", user_name="Alice",
    )
    assert form is not None
    assert form.display_name == ""
    assert form.brief == ""
    assert form.github_username == ""
    assert form.tech_stack == ""


def test_extract_project_form_payload_returns_none_if_required_missing(tmp_path):
    app = _make_app(tmp_path)
    payload = {
        "operator": {"open_id": "ou_alice"},
        "context": {"open_chat_id": "oc_chat_x"},
        "action": {
            "value": {"action": "submit_create_project"},
            "form_value": {"project": "", "category": ""},
        },
    }
    assert app._extract_project_form_payload(
        payload, user_id="ou_alice", user_name="Alice",
    ) is None
