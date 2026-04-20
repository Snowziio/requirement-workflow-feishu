"""End-to-end integration: Bootstrap -> REQ creation -> registry append.

Uses MagicMock gateway boundaries; verifies the full happy-path
without hitting real GitHub/Feishu. Real-world smoke is a manual
step (see docs/superpowers/plans/2026-04-20-project-layer-plan.md
Phase J - smoke task).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from unittest.mock import MagicMock, patch


def test_e2e_bootstrap_then_create_req_appends_registry(tmp_path):
    from requirement_workflow_v12.service_app import (
        CoordinatorRuntimeApp,
        MessageContext,
    )
    from requirement_workflow_v12.config import Settings
    from requirement_workflow_v12.store import JsonStateStore
    from requirement_workflow_v12.coordinator_service import CoordinatorService
    from requirement_workflow_v12.project_bootstrap.service import ProjectBootstrapService
    from requirement_workflow_v12.project_repo.types import BootstrapRepoResult

    settings = MagicMock(spec=Settings)
    settings.state_store_path = str(tmp_path / "state.json")
    settings.creation_group_chat_id = "group_c"
    settings.openclaw_callback_secret = ""
    settings.openclaw_callback_ttl_seconds = 600
    settings.github_token = ""
    settings.github_template_owner = "Snowziio"
    settings.github_template_repo = "Template-repository"
    settings.github_org_owner = "Snowziio"
    settings.feishu_user_id_type = "open_id"
    settings.spec_trace_dir = str(tmp_path / "trace")

    state: dict = {}
    gateway = MagicMock()
    gateway.list_project_configs.side_effect = lambda: dict(state)
    gateway.upsert_project_config.side_effect = (
        lambda p, cfg: state.__setitem__(p, cfg) or cfg
    )
    gateway.create_architecture_document.return_value = MagicMock(
        document_id="doc_test3",
        document_url="https://feishu.example/doc_test3",
    )
    gateway.write_document_text.return_value = None
    gateway.create_project_group.return_value = MagicMock(chat_id="oc_test3_group")
    gateway.create_requirement_record.return_value = None
    gateway.create_requirement_document.return_value = None
    gateway.fetch_file_sha.return_value = (
        "sha_old", "project: test3\nrequirements: []\n",
    )
    gateway.commit_files.return_value = "sha_new"

    repo_tools = MagicMock()
    repo_tools.bootstrap_project_repo.return_value = BootstrapRepoResult(
        html_url="https://github.com/Snowziio/test3",
        default_branch="main",
        initial_populate_commit_sha="pop_sha",
    )
    github_gw_mock = MagicMock()
    github_gw_mock.get_repo.return_value = None
    github_gw_mock.fetch_file_sha.return_value = (
        "sha_old", "project: test3\nrequirements: []\n",
    )
    github_gw_mock.commit_files.return_value = "sha_new"
    bootstrap_svc = ProjectBootstrapService(
        repo_tools=repo_tools,
        feishu_gateway=gateway,
        github_gateway=github_gw_mock,
        template_owner="Snowziio",
        template_repo="Template-repository",
        new_owner="Snowziio",
    )

    service = CoordinatorService()
    store = JsonStateStore(settings.state_store_path)

    with patch.object(Settings, "validate_runtime", return_value=None):
        settings.validate_runtime = lambda: None
        app = CoordinatorRuntimeApp(
            settings=settings, store=store, service=service, gateway=gateway,
            project_bootstrap_service=bootstrap_svc,
        )
    # Redirect registry append to the github gateway mock we control.
    app._github_gateway = github_gw_mock

    # Step A: bare `/create project` opens the card (no side effects).
    ctx_bootstrap = MessageContext(
        message_id="m1", chat_id="group_c", chat_type="group",
        user_id="ou_alice", sender_name="Alice",
        text="/create project",
    )
    msgs = app.handle_text_message(ctx_bootstrap)
    assert msgs, "bare /create project should produce an outbound card"

    # Step B: submit the project creation form → Bootstrap runs.
    status_a, _ = app._handle_card_action_payload({
        "operator": {"open_id": "ou_alice", "name": "Alice"},
        "context": {"open_chat_id": "group_c", "open_message_id": "om_proj_1"},
        "action": {
            "value": {"action": "submit_create_project", "creator_chat_id": "group_c"},
            "form_value": {
                "project": "test3",
                "category": "saas-ai-automation",
                "display_name": "", "brief": "", "github_username": "", "tech_stack": "",
            },
        },
    })
    assert status_a == 200

    # Bootstrap runs in a daemon thread — wait for it before asserting.
    import threading as _threading
    import time as _time
    deadline = _time.time() + 5.0
    while _time.time() < deadline:
        non_main = [t for t in _threading.enumerate() if t is not _threading.main_thread()]
        if not non_main:
            break
        _time.sleep(0.05)

    cfg = state["test3"]
    assert cfg.bootstrap_status == "PROVISIONED"
    service.project_configs["test3"] = cfg

    # Step C: submit the requirement creation form → REQ created + registry appended.
    status_b, _ = app._handle_card_action_payload({
        "operator": {"open_id": "ou_alice", "name": "Alice"},
        "context": {"open_chat_id": "group_c", "open_message_id": "om_req_1"},
        "action": {
            "value": {"action": "submit_create_requirement", "creation_chat_id": "group_c"},
            "form_value": {
                "project": "test3",
                "name": "会话鉴权改造",
                "summary": "支持 JWT 单点登录",
            },
        },
    })
    assert status_b == 200

    # Provisioning runs in a daemon thread — wait for it to finish so the
    # registry append completes before we assert.
    import threading as _threading
    import time as _time
    deadline = _time.time() + 5.0
    while _time.time() < deadline:
        non_main = [t for t in _threading.enumerate() if t is not _threading.main_thread()]
        if not non_main:
            break
        _time.sleep(0.05)

    reqs = list(service.requirements.values())
    assert len(reqs) == 1
    assert reqs[0].project == "test3"

    registry_calls = [
        c for c in github_gw_mock.commit_files.call_args_list
        if any(
            fc.path == "project/req-registry.yaml"
            for fc in c.kwargs.get("files", [])
        )
    ]
    assert len(registry_calls) == 1
