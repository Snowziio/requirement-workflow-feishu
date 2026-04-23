"""End-to-end Bootstrap integration test for design-phase prerequisites.

Scenarios:
- Bootstrap 7 steps (with mocked gateways) → design files land in populate_files
  + binding reminder card emitted after FINALIZE
- needs_ui=True REQ without binding → design_start guard blocks → user
  "clicks card" (ProjectConfig updated) → design_start retry succeeds
- enterprise-bot (no frontend) → no frontend .gitkeep but binding card still sent
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def _make_gateways():
    """Build the mocked gateways + shared config store used by the E2E tests."""
    repo_tools = MagicMock()
    repo_tools.bootstrap_project_repo.return_value = MagicMock(
        html_url="https://github.com/new-org/testp",
    )
    feishu = MagicMock()
    github = MagicMock()
    github.get_repo.return_value = None  # fresh project — no existing repo

    configs: dict = {}

    def _list():
        return dict(configs)

    def _upsert(project, cfg):
        configs[project] = cfg
        return cfg

    feishu.list_project_configs.side_effect = _list
    feishu.upsert_project_config.side_effect = _upsert
    feishu.create_project_group.return_value = MagicMock(chat_id="oc_chatxyz")
    feishu.create_architecture_document.return_value = MagicMock(
        document_id="doc1",
        document_url="https://feishu/docx/doc1",
    )
    feishu.write_document_text.return_value = None

    return repo_tools, feishu, github, configs


def test_bootstrap_e2e_produces_design_artifacts_and_binding_card():
    """Bootstrap end-to-end: design files land in populate + binding card sent."""
    from requirement_workflow_v12.project_bootstrap.service import (
        ProjectBootstrapService,
    )
    from requirement_workflow_v12.project_bootstrap.types import BootstrapRequest

    repo_tools, feishu, github, configs = _make_gateways()

    service = ProjectBootstrapService(
        repo_tools=repo_tools,
        feishu_gateway=feishu,
        github_gateway=github,
        template_owner="org",
        template_repo="Template-repository",
        new_owner="new-org",
    )
    request = BootstrapRequest(
        project="testp",
        category="enterprise-app",
        owner_user_id="u1",
        creator_chat_id="c1",
    )

    # run() chains all 7 steps in order
    service.run(request)

    cfg = configs["testp"]

    # ── Assertion 1: populate_files contains all design artifacts ──
    populate_call = repo_tools.bootstrap_project_repo.call_args
    populate_files = populate_call.kwargs["populate_files"]
    for must_have in [
        "design/README.md",
        "design/PAGES.yaml",
        "design/INDEX.md",
        "design/system/.gitkeep",
        "design/archive/.gitkeep",
        ".gitattributes",
    ]:
        assert must_have in populate_files, f"missing {must_have}"
    # Frontend gitkeep for enterprise-app (src/testp_webapp/.gitkeep)
    frontend_gitkeeps = [
        k for k in populate_files if "_webapp/" in k and k.endswith("/.gitkeep")
    ]
    assert len(frontend_gitkeeps) == 1, (
        f"expected exactly 1 frontend gitkeep, got {frontend_gitkeeps}"
    )

    # ── Assertion 2: Binding reminder card sent after FINALIZE ──
    assert feishu.send_card.called, (
        "binding reminder card not sent after FINALIZE"
    )
    last_send_card = feishu.send_card.call_args
    chat_id = (
        last_send_card.args[0]
        if last_send_card.args
        else last_send_card.kwargs.get("receive_id")
    )
    assert chat_id == "oc_chatxyz"

    # ── Assertion 3: ProjectConfig has frontend fields + empty URL ──
    assert cfg.frontend_subpath == "src/testp_webapp"
    assert "React 18" in cfg.frontend_tech_stack.get("framework", "")
    # Awaiting user binding — card was sent but URL not yet saved
    assert cfg.claude_design_project_url == ""
    # Bootstrap itself completed
    assert cfg.bootstrap_status == "PROVISIONED"


def test_bootstrap_then_binding_then_design_start_succeeds():
    """Post-Bootstrap: needs_ui REQ blocked by guard → user binds → retry OK."""
    from dataclasses import replace

    import pytest

    from requirement_workflow_v12.coordinator_service import CoordinatorService
    from requirement_workflow_v12.models import Requirement, WorkflowStatus
    from requirement_workflow_v12.plan_state_machine import DesignStatus
    from requirement_workflow_v12.project_config import ProjectConfig

    svc = CoordinatorService.__new__(CoordinatorService)
    svc.requirements = {}
    svc.project_configs = {}
    svc._hooks = MagicMock()

    # Post-bootstrap state: ProjectConfig exists but claude_design_project_url empty
    cfg = ProjectConfig(
        category="enterprise-app",
        template_version="enterprise-app.v1",
        architecture_doc_id="d",
        architecture_doc_url="u",
        frontend_subpath="src/testp_webapp",
        claude_design_project_url="",
    )
    svc.project_configs["testp"] = cfg

    r = Requirement(
        req_id="REQ-testp-001",
        name="n",
        project="testp",
        summary="s",
        creator="c",
        status=WorkflowStatus.APPROVED,
        needs_ui=True,
    )
    svc.requirements[r.req_id] = r

    # Step 1: design_start fails due to binding guard
    with pytest.raises(ValueError, match="Claude Design 未绑定"):
        svc.design_start(r.req_id, design_doc_id="d", design_doc_url="u")
    # Design state was not advanced
    assert r.design_status is None

    # Step 2: simulate user clicking binding card (updates ProjectConfig URL)
    svc.project_configs["testp"] = replace(
        cfg, claude_design_project_url="https://claude.ai/design/p/abc",
    )

    # Step 3: design_start now succeeds
    result = svc.design_start(r.req_id, design_doc_id="d", design_doc_url="u")
    assert result.design_status is DesignStatus.DRAFTING
    assert result.design_doc_id == "d"
    assert result.design_doc_url == "u"


def test_bootstrap_with_enterprise_bot_no_frontend_still_emits_binding_card():
    """enterprise-bot (frontend: null) → no frontend gitkeep but binding card still sent."""
    from requirement_workflow_v12.project_bootstrap.service import (
        ProjectBootstrapService,
    )
    from requirement_workflow_v12.project_bootstrap.types import BootstrapRequest

    repo_tools, feishu, github, configs = _make_gateways()
    repo_tools.bootstrap_project_repo.return_value = MagicMock(
        html_url="https://github.com/new-org/testbot",
    )
    feishu.create_project_group.return_value = MagicMock(chat_id="oc_bot_group")

    service = ProjectBootstrapService(
        repo_tools=repo_tools,
        feishu_gateway=feishu,
        github_gateway=github,
        template_owner="org",
        template_repo="Template-repository",
        new_owner="new-org",
    )
    request = BootstrapRequest(
        project="testbot",
        category="enterprise-bot",
        owner_user_id="u1",
        creator_chat_id="c1",
    )
    service.run(request)

    # No frontend gitkeep for enterprise-bot (frontend: null)
    populate_files = repo_tools.bootstrap_project_repo.call_args.kwargs[
        "populate_files"
    ]
    frontend_gitkeeps = [
        k
        for k in populate_files
        if (("_webapp/" in k) or ("_miniapp/" in k)) and k.endswith("/.gitkeep")
    ]
    assert frontend_gitkeeps == []

    # Binding card is still emitted (future-proof for adding UI later)
    assert feishu.send_card.called
    cfg = configs["testbot"]
    assert cfg.frontend_subpath == ""
