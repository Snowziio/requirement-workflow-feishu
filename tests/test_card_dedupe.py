"""Tests for card-action callback dedupe (_seen_card_action_ids)."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.service_app import CoordinatorRuntimeApp  # noqa: E402
from requirement_workflow_v12.config import Settings  # noqa: E402
from requirement_workflow_v12.store import JsonStateStore  # noqa: E402
from requirement_workflow_v12.coordinator_service import CoordinatorService  # noqa: E402
from requirement_workflow_v12.project_bootstrap.types import BootstrapResult  # noqa: E402


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
    bootstrap_svc = MagicMock()
    bootstrap_svc.run.return_value = BootstrapResult(
        project="test5",
        github_repo_url="u", architecture_doc_id="d", architecture_doc_url="ud",
        feishu_chat_id="oc", template_version="x.v1",
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


def test_mark_card_action_seen_returns_true_then_false():
    from requirement_workflow_v12.service_app import CoordinatorRuntimeApp
    app = CoordinatorRuntimeApp.__new__(CoordinatorRuntimeApp)
    import collections
    app._seen_card_action_ids = collections.OrderedDict()
    app._seen_card_action_ids_max = 3
    assert app._mark_card_action_seen("om_1", "submit_create_project") is True
    assert app._mark_card_action_seen("om_1", "submit_create_project") is False
    assert app._mark_card_action_seen("om_2", "submit_create_project") is True
    assert app._mark_card_action_seen("om_1", "human_confirm_yes") is True


def test_mark_card_action_seen_bounded_lru():
    from requirement_workflow_v12.service_app import CoordinatorRuntimeApp
    import collections
    app = CoordinatorRuntimeApp.__new__(CoordinatorRuntimeApp)
    app._seen_card_action_ids = collections.OrderedDict()
    app._seen_card_action_ids_max = 2
    app._mark_card_action_seen("a", "x")
    app._mark_card_action_seen("b", "x")
    app._mark_card_action_seen("c", "x")
    assert app._mark_card_action_seen("a", "x") is True


def test_handle_card_action_dedupes_same_payload_twice(tmp_path):
    app, bootstrap_svc = _make_app(tmp_path)
    payload = {
        "operator": {"open_id": "ou_alice", "name": "Alice"},
        "context": {"open_chat_id": "oc_x", "open_message_id": "om_card_99"},
        "action": {
            "value": {"action": "submit_create_project", "creator_chat_id": "oc_x"},
            "form_value": {
                "project": "test5",
                "category": "saas-ai-automation",
                "display_name": "", "brief": "", "github_username": "", "tech_stack": "",
            },
        },
    }
    app._handle_card_action_payload(payload)
    app._handle_card_action_payload(payload)
    bootstrap_svc.run.assert_called_once()
