"""Verify Bootstrap Step 4 (POPULATE_MAIN) includes design-related files."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def _make_service(category: str = "enterprise-app"):
    from requirement_workflow_v12.project_bootstrap.service import ProjectBootstrapService
    from requirement_workflow_v12.project_config import ProjectConfig

    service = ProjectBootstrapService(
        repo_tools=MagicMock(),
        feishu_gateway=MagicMock(),
        github_gateway=MagicMock(),
        template_owner="org",
        template_repo="Template-repository",
        new_owner="new-org",
    )
    # Prime existing config
    existing_cfg = ProjectConfig(
        category=category,
        template_version=f"{category}.v1",
        architecture_doc_id="",
        architecture_doc_url="",
        bootstrap_status="BOOTSTRAPPING",
        project_status="BOOTSTRAPPING",
    )
    configs = {"testp": existing_cfg}
    service._feishu.list_project_configs.return_value = configs

    def _upsert(project, cfg):
        configs[project] = cfg
        return cfg
    service._feishu.upsert_project_config.side_effect = _upsert
    return service


def test_populate_files_contains_all_design_files():
    """POPULATE_MAIN must commit 6 new design-related files + 1 frontend gitkeep."""
    from requirement_workflow_v12.project_bootstrap.types import BootstrapRequest

    service = _make_service(category="enterprise-app")
    service._repo_tools.bootstrap_project_repo.return_value = MagicMock(
        html_url="https://github.com/new-org/testp",
    )
    request = BootstrapRequest(
        project="testp",
        category="enterprise-app",
        owner_user_id="u1",
        creator_chat_id="c1",
    )
    service.create_repo_and_populate(
        request,
        template_version="enterprise-app.v1",
        rendered_architecture_md="# arch\n",
    )

    call = service._repo_tools.bootstrap_project_repo.call_args
    populate_files = call.kwargs["populate_files"]
    expected_paths = [
        "design/README.md",
        "design/PAGES.yaml",
        "design/INDEX.md",
        "design/system/.gitkeep",
        "design/archive/.gitkeep",
        ".gitattributes",
    ]
    for p in expected_paths:
        assert p in populate_files, f"missing {p} in populate_files"
    # Frontend subpath gitkeep — for enterprise-app with pkg=testp → src/testp_webapp
    frontend_gitkeep_keys = [
        k for k in populate_files if "_webapp/" in k and k.endswith("/.gitkeep")
    ]
    assert len(frontend_gitkeep_keys) == 1, (
        f"expected exactly one frontend gitkeep; got {frontend_gitkeep_keys}"
    )
    assert "testp_webapp" in frontend_gitkeep_keys[0]


def test_populate_for_enterprise_bot_skips_frontend_gitkeep():
    """enterprise-bot has frontend: null; no src/*_webapp/.gitkeep should be added."""
    from requirement_workflow_v12.project_bootstrap.types import BootstrapRequest

    service = _make_service(category="enterprise-bot")
    service._repo_tools.bootstrap_project_repo.return_value = MagicMock(
        html_url="https://github.com/new-org/testp",
    )
    request = BootstrapRequest(
        project="testp", category="enterprise-bot",
        owner_user_id="u1", creator_chat_id="c1",
    )
    service.create_repo_and_populate(
        request, template_version="enterprise-bot.v1",
        rendered_architecture_md="# arch\n",
    )
    populate_files = service._repo_tools.bootstrap_project_repo.call_args.kwargs["populate_files"]
    frontend_gitkeeps = [
        k for k in populate_files
        if (("_webapp/" in k) or ("_miniapp/" in k)) and k.endswith("/.gitkeep")
    ]
    assert frontend_gitkeeps == [], f"expected no frontend gitkeep, got {frontend_gitkeeps}"


def test_populate_for_miniprogram_uses_miniapp_subpath():
    """miniprogram uses src/{pkg}_miniapp/.gitkeep, not _webapp."""
    from requirement_workflow_v12.project_bootstrap.types import BootstrapRequest

    service = _make_service(category="miniprogram")
    service._repo_tools.bootstrap_project_repo.return_value = MagicMock(
        html_url="https://github.com/new-org/testp",
    )
    request = BootstrapRequest(
        project="testp", category="miniprogram",
        owner_user_id="u1", creator_chat_id="c1",
    )
    service.create_repo_and_populate(
        request, template_version="miniprogram.v1",
        rendered_architecture_md="# arch\n",
    )
    populate_files = service._repo_tools.bootstrap_project_repo.call_args.kwargs["populate_files"]
    assert "src/testp_miniapp/.gitkeep" in populate_files
    assert "src/testp_webapp/.gitkeep" not in populate_files


def test_populate_writes_frontend_fields_to_project_config():
    """After POPULATE_MAIN, ProjectConfig has frontend_subpath + frontend_tech_stack populated."""
    from requirement_workflow_v12.project_bootstrap.types import BootstrapRequest

    service = _make_service(category="enterprise-app")
    service._repo_tools.bootstrap_project_repo.return_value = MagicMock(
        html_url="https://github.com/new-org/testp",
    )
    request = BootstrapRequest(
        project="testp", category="enterprise-app",
        owner_user_id="u1", creator_chat_id="c1",
    )
    cfg = service.create_repo_and_populate(
        request, template_version="enterprise-app.v1",
        rendered_architecture_md="# arch\n",
    )
    assert cfg.frontend_subpath == "src/testp_webapp"
    assert cfg.frontend_tech_stack.get("framework", "").startswith("React 18")


def test_populate_for_enterprise_bot_writes_empty_frontend_fields():
    """enterprise-bot has frontend: null; ProjectConfig.frontend_subpath stays empty."""
    from requirement_workflow_v12.project_bootstrap.types import BootstrapRequest

    service = _make_service(category="enterprise-bot")
    service._repo_tools.bootstrap_project_repo.return_value = MagicMock(
        html_url="https://github.com/new-org/testp",
    )
    request = BootstrapRequest(
        project="testp", category="enterprise-bot",
        owner_user_id="u1", creator_chat_id="c1",
    )
    cfg = service.create_repo_and_populate(
        request, template_version="enterprise-bot.v1",
        rendered_architecture_md="# arch\n",
    )
    assert cfg.frontend_subpath == ""
    assert cfg.frontend_tech_stack == {}
