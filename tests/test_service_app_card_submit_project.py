"""Integration tests for the submit_create_project card-action branch."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.service_app import CoordinatorRuntimeApp  # noqa: E402
from requirement_workflow_v12.config import Settings  # noqa: E402
from requirement_workflow_v12.store import JsonStateStore  # noqa: E402
from requirement_workflow_v12.coordinator_service import CoordinatorService  # noqa: E402
from requirement_workflow_v12.project_bootstrap.types import (  # noqa: E402
    BootstrapRequest,
    BootstrapResult,
    BootstrapStep,
    BootstrapStepError,
)
from requirement_workflow_v12.project_config import ProjectConfig  # noqa: E402


def _make_app(tmp_path, *, project_configs=None):
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
        github_repo_url="https://github.com/Snowziio/test5",
        architecture_doc_id="doc_x",
        architecture_doc_url="https://feishu.example/doc_x",
        feishu_chat_id="oc_test5",
        template_version="saas-ai-automation.v1",
    )
    service = CoordinatorService()
    store = JsonStateStore(settings.state_store_path)
    gateway = MagicMock()
    gateway.list_project_configs.return_value = project_configs or {}
    with patch.object(Settings, "validate_runtime", return_value=None):
        settings.validate_runtime = lambda: None
        app = CoordinatorRuntimeApp(
            settings=settings, store=store, service=service, gateway=gateway,
            project_bootstrap_service=bootstrap_svc,
        )
    return app, bootstrap_svc


def _submit_payload(**form_overrides):
    form_value = {
        "project": "test5",
        "category": "saas-ai-automation",
        "display_name": "Test 5",
        "brief": "测试简述",
        "github_username": "alice",
        "tech_stack": "FastAPI",
        **form_overrides,
    }
    return {
        "operator": {"open_id": "ou_alice", "name": "Alice"},
        "context": {"open_chat_id": "oc_chat_x", "open_message_id": "om_card_1"},
        "action": {
            "value": {"action": "submit_create_project", "creator_chat_id": "oc_chat_x"},
            "form_value": form_value,
        },
    }


def test_submit_new_project_runs_bootstrap_without_resume(tmp_path):
    app, bootstrap_svc = _make_app(tmp_path)
    status, resp = app._handle_card_action_payload(_submit_payload())
    assert status == 200
    bootstrap_svc.run.assert_called_once()
    req: BootstrapRequest = bootstrap_svc.run.call_args.args[0]
    assert req.project == "test5"
    assert req.category == "saas-ai-automation"
    assert req.owner_user_id == "ou_alice"
    assert req.creator_chat_id == "oc_chat_x"
    assert req.resume is False
    assert req.github_username == "alice"
    # Toast shows success
    assert resp.get("toast", {}).get("type") == "success"


def test_submit_existing_nonprovisioned_project_resumes(tmp_path):
    existing = ProjectConfig(
        category="saas-ai-automation",
        template_version="saas-ai-automation.v1",
        architecture_doc_id="",
        architecture_doc_url="",
        bootstrap_status="BOOTSTRAPPING",
        project_status="BOOTSTRAPPING",
    )
    app, bootstrap_svc = _make_app(tmp_path, project_configs={"test5": existing})
    status, _ = app._handle_card_action_payload(_submit_payload())
    assert status == 200
    bootstrap_svc.run.assert_called_once()
    req = bootstrap_svc.run.call_args.args[0]
    assert req.resume is True


def test_submit_existing_provisioned_project_rejected(tmp_path):
    existing = ProjectConfig(
        category="saas-ai-automation",
        template_version="saas-ai-automation.v1",
        architecture_doc_id="doc",
        architecture_doc_url="url",
        bootstrap_status="PROVISIONED",
        project_status="PROVISIONED",
    )
    app, bootstrap_svc = _make_app(tmp_path, project_configs={"test5": existing})
    status, resp = app._handle_card_action_payload(_submit_payload())
    assert status == 200
    bootstrap_svc.run.assert_not_called()
    # A toast error is returned, and a text reply is sent to the chat.
    toast = resp.get("toast", {})
    assert toast.get("type") in ("error", "info")
    # The gateway should have sent a rejection text to creator_chat_id.
    app.gateway.send_text.assert_called()
    text = app.gateway.send_text.call_args.args[1]
    assert "/create req" in text
    assert "test5" in text


def test_submit_bootstrap_step_error_reports_step(tmp_path):
    app, bootstrap_svc = _make_app(tmp_path)
    bootstrap_svc.run.side_effect = BootstrapStepError(
        step=BootstrapStep.CREATE_REPO, message="rate limited",
    )
    status, resp = app._handle_card_action_payload(_submit_payload())
    assert status == 200
    app.gateway.send_text.assert_called()
    text = app.gateway.send_text.call_args.args[1]
    assert "CREATE_REPO" in text
    assert "rate limited" in text
    assert "/create project" in text  # retry hint


def test_submit_invalid_form_returns_toast_error(tmp_path):
    app, bootstrap_svc = _make_app(tmp_path)
    payload = _submit_payload(project="", category="")
    status, resp = app._handle_card_action_payload(payload)
    assert status == 200
    bootstrap_svc.run.assert_not_called()
    assert resp.get("toast", {}).get("type") == "error"


def test_submit_passes_seed_to_bootstrap_via_architecture_md(tmp_path):
    """Seed fields from the card should drive render_template's seed kwarg."""
    app, bootstrap_svc = _make_app(tmp_path)
    # Intercept the render_template call indirectly: Bootstrap stub receives
    # the full BootstrapRequest; we exposed the seed via its own attribute.
    status, _ = app._handle_card_action_payload(_submit_payload())
    assert status == 200
    req: BootstrapRequest = bootstrap_svc.run.call_args.args[0]
    assert req.architecture_seed == {
        "display_name": "Test 5",
        "brief": "测试简述",
        "tech_stack": "FastAPI",
    }
