import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def _make_app_with_stub_gateway(tmp_path):
    from requirement_workflow_v12.service_app import CoordinatorRuntimeApp
    from requirement_workflow_v12.config import Settings
    from requirement_workflow_v12.store import JsonStateStore
    from requirement_workflow_v12.coordinator_service import CoordinatorService

    settings = MagicMock(spec=Settings)
    settings.state_store_path = str(tmp_path / "state.json")
    settings.creation_group_chat_id = "group_c"
    settings.openclaw_callback_secret = ""
    settings.openclaw_callback_ttl_seconds = 600
    settings.github_token = ""

    gateway = MagicMock()
    gateway.create_architecture_document.return_value = MagicMock(
        document_id="doc_arch",
        document_url="https://feishu.example/docx/doc_arch",
    )
    gateway.write_document_text.return_value = None
    gateway.create_project_group.side_effect = Exception("skip")
    gateway.create_requirement_record.return_value = None
    gateway.create_requirement_document.return_value = None
    gateway.list_project_configs.return_value = {}
    gateway.upsert_project_config.side_effect = lambda project, cfg: cfg

    service = CoordinatorService()
    store = JsonStateStore(settings.state_store_path)

    with patch.object(Settings, "validate_runtime", return_value=None):
        settings.validate_runtime = lambda: None
        app = CoordinatorRuntimeApp(
            settings=settings,
            store=store,
            service=service,
            gateway=gateway,
        )
    return app, gateway, service


def test_first_req_creates_architecture_doc_and_project_config(tmp_path):
    app, gateway, service = _make_app_with_stub_gateway(tmp_path)

    from requirement_workflow_v12.protocols import CreationFormPayload

    payload = CreationFormPayload(
        project="MyProj",
        name="first req",
        summary="kickoff",
        creator="Alice",
        creator_user_id="u1",
        creation_chat_id="group_c",
        needs_ui=False,
        category="saas-ai-automation",
    )

    request, _, req_id = app._create_requirement_from_form(payload)
    app._provision_requirement_after_creation(request, req_id)

    cfg = service.project_configs["MyProj"]
    assert cfg.category == "saas-ai-automation"
    assert cfg.template_version == "saas-ai-automation.v1"
    assert cfg.architecture_doc_id == "doc_arch"
    gateway.create_architecture_document.assert_called_once_with("MyProj")
    gateway.write_document_text.assert_called_once()
    written_text = gateway.write_document_text.call_args.args[1]
    assert "category: saas-ai-automation" in written_text
    assert "my_proj" in written_text


def test_second_req_does_not_recreate_architecture_doc(tmp_path):
    app, gateway, service = _make_app_with_stub_gateway(tmp_path)
    service.initialize_project(
        project="MyProj",
        category="miniprogram",
        template_version="miniprogram.v1",
        architecture_doc_id="doc_existing",
        architecture_doc_url="https://feishu.example/docx/doc_existing",
        tech_stack={},
    )

    from requirement_workflow_v12.protocols import CreationFormPayload

    payload = CreationFormPayload(
        project="MyProj",
        name="second req",
        summary="more work",
        creator="Bob",
        creator_user_id="u2",
        creation_chat_id="group_c",
        needs_ui=False,
        category="",
    )

    request, _, req_id = app._create_requirement_from_form(payload)
    app._provision_requirement_after_creation(request, req_id)

    gateway.create_architecture_document.assert_not_called()
    gateway.write_document_text.assert_not_called()
    assert service.project_configs["MyProj"].architecture_doc_id == "doc_existing"


def test_first_req_without_category_raises(tmp_path):
    app, _, _ = _make_app_with_stub_gateway(tmp_path)
    from requirement_workflow_v12.protocols import CreationFormPayload
    import pytest as _pytest

    payload = CreationFormPayload(
        project="NewProj",
        name="x",
        summary="y",
        creator="c",
        creator_user_id="u",
        creation_chat_id="group_c",
        category="",
    )
    with _pytest.raises(ValueError, match="category is required"):
        app._initialize_project_for_first_req(payload)
