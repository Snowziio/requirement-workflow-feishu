"""Unit tests for ProjectBootstrapService (validate step + later steps)."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.project_bootstrap.service import (  # noqa: E402
    ProjectBootstrapService,
    ValidationError,
)
from requirement_workflow_v12.project_bootstrap.types import (  # noqa: E402
    BootstrapRequest,
)


def _make_service(existing_projects=None):
    existing = existing_projects or {}
    repo_tools = MagicMock()
    feishu_gw = MagicMock()
    feishu_gw.list_project_configs.return_value = existing
    feishu_gw.upsert_project_config.side_effect = lambda project, cfg: cfg
    github_gw = MagicMock()
    github_gw.get_repo.return_value = None
    svc = ProjectBootstrapService(
        repo_tools=repo_tools,
        feishu_gateway=feishu_gw,
        github_gateway=github_gw,
        template_owner="Snowziio",
        template_repo="Template-repository",
        new_owner="Snowziio",
    )
    return svc, repo_tools, feishu_gw, github_gw


def test_validate_rejects_uppercase_project_name():
    svc, *_ = _make_service()
    req = BootstrapRequest(
        project="TestProj",
        category="saas-ai-automation",
        owner_user_id="ou_1",
        creator_chat_id="c1",
    )
    with pytest.raises(ValidationError, match="name"):
        svc.validate(req)


def test_validate_rejects_short_project_name():
    svc, *_ = _make_service()
    req = BootstrapRequest(
        project="ab",
        category="saas-ai-automation",
        owner_user_id="ou_1",
        creator_chat_id="c1",
    )
    with pytest.raises(ValidationError):
        svc.validate(req)


def test_validate_rejects_unknown_category():
    svc, *_ = _make_service()
    req = BootstrapRequest(
        project="test3",
        category="no-such-category",
        owner_user_id="ou_1",
        creator_chat_id="c1",
    )
    with pytest.raises(ValidationError, match="category"):
        svc.validate(req)


def test_validate_rejects_existing_project_when_not_resuming():
    from requirement_workflow_v12.project_config import ProjectConfig

    existing = {
        "test3": ProjectConfig(
            category="saas-ai-automation",
            template_version="saas-ai-automation.v1",
            architecture_doc_id="",
            architecture_doc_url="",
            bootstrap_status="PROVISIONED",
        )
    }
    svc, *_ = _make_service(existing_projects=existing)
    req = BootstrapRequest(
        project="test3",
        category="saas-ai-automation",
        owner_user_id="ou_1",
        creator_chat_id="c1",
        resume=False,
    )
    with pytest.raises(ValidationError, match="already"):
        svc.validate(req)


def test_validate_rejects_existing_repo_name():
    svc, _, _, github_gw = _make_service()
    github_gw.get_repo.return_value = {"html_url": "https://github.com/Snowziio/test3"}
    req = BootstrapRequest(
        project="test3",
        category="saas-ai-automation",
        owner_user_id="ou_1",
        creator_chat_id="c1",
    )
    with pytest.raises(ValidationError, match="GitHub"):
        svc.validate(req)


def test_validate_accepts_valid_name_and_category():
    svc, *_ = _make_service()
    req = BootstrapRequest(
        project="test3",
        category="saas-ai-automation",
        owner_user_id="ou_1",
        creator_chat_id="c1",
    )
    svc.validate(req)


def test_upsert_config_creates_new_row_with_bootstrapping_status():
    from requirement_workflow_v12.project_bootstrap.types import BootstrapStep

    svc, _, feishu_gw, _ = _make_service()
    req = BootstrapRequest(
        project="test3",
        category="saas-ai-automation",
        owner_user_id="ou_1",
        creator_chat_id="c1",
    )
    cfg = svc.upsert_config(req, template_version="saas-ai-automation.v1")
    assert cfg.bootstrap_status == "BOOTSTRAPPING"
    assert cfg.project_status == "BOOTSTRAPPING"
    assert cfg.category == "saas-ai-automation"
    assert cfg.template_version == "saas-ai-automation.v1"
    feishu_gw.upsert_project_config.assert_called_once()
    assert any(
        e["step"] == int(BootstrapStep.UPSERT_CONFIG) and e["status"] == "ok"
        for e in cfg.bootstrap_log
    )


def test_create_repo_and_populate_renders_all_seven_files_and_records_sha():
    from requirement_workflow_v12.project_bootstrap.types import BootstrapStep
    from requirement_workflow_v12.project_repo.types import BootstrapRepoResult
    from requirement_workflow_v12.project_config import ProjectConfig

    existing = ProjectConfig(
        category="saas-ai-automation",
        template_version="saas-ai-automation.v1",
        architecture_doc_id="",
        architecture_doc_url="",
        bootstrap_status="BOOTSTRAPPING",
        bootstrap_log=[
            {"step": 2, "step_name": "UPSERT_CONFIG", "ts": "t", "status": "ok"}
        ],
    )
    svc, repo_tools, _, _ = _make_service(existing_projects={"test3": existing})
    repo_tools.bootstrap_project_repo.return_value = BootstrapRepoResult(
        html_url="https://github.com/Snowziio/test3",
        default_branch="main",
        initial_populate_commit_sha="sha_xyz",
    )
    req = BootstrapRequest(
        project="test3",
        category="saas-ai-automation",
        owner_user_id="ou_1",
        creator_chat_id="c1",
        github_username="alice",
        resume=True,
    )
    rendered_arch = "# arch for test3"

    cfg_after = svc.create_repo_and_populate(
        req,
        template_version="saas-ai-automation.v1",
        rendered_architecture_md=rendered_arch,
    )
    call = repo_tools.bootstrap_project_repo.call_args
    populate_files = call.kwargs["populate_files"]
    assert set(populate_files.keys()) == {
        "docs/ARCHITECTURE.md",
        "project/README.md",
        "project/req-registry.yaml",
        "project/environments.yaml",
        "project/SECRETS-TODO.md",
        "CLAUDE.md",
        "SKILL.md",
    }
    assert populate_files["docs/ARCHITECTURE.md"] == rendered_arch
    assert "project: test3" in populate_files["project/req-registry.yaml"]
    assert cfg_after.github_repo_url == "https://github.com/Snowziio/test3"
    step_numbers = {e["step"] for e in cfg_after.bootstrap_log}
    assert int(BootstrapStep.CREATE_REPO) in step_numbers
    assert int(BootstrapStep.POPULATE_MAIN) in step_numbers


def test_create_repo_skips_when_already_present_in_log():
    from requirement_workflow_v12.project_config import ProjectConfig
    from requirement_workflow_v12.project_bootstrap.types import BootstrapStep

    prior_log = [
        {"step": int(BootstrapStep.UPSERT_CONFIG), "step_name": "UPSERT_CONFIG", "ts": "t", "status": "ok"},
        {"step": int(BootstrapStep.CREATE_REPO), "step_name": "CREATE_REPO", "ts": "t", "status": "ok"},
        {"step": int(BootstrapStep.POPULATE_MAIN), "step_name": "POPULATE_MAIN", "ts": "t", "status": "ok"},
    ]
    existing = ProjectConfig(
        category="saas-ai-automation",
        template_version="saas-ai-automation.v1",
        architecture_doc_id="",
        architecture_doc_url="",
        bootstrap_status="BOOTSTRAPPING",
        bootstrap_log=prior_log,
        github_repo_url="https://github.com/Snowziio/test3",
    )
    svc, repo_tools, _, _ = _make_service(existing_projects={"test3": existing})
    req = BootstrapRequest(
        project="test3",
        category="saas-ai-automation",
        owner_user_id="ou_1",
        creator_chat_id="c1",
        resume=True,
    )
    svc.create_repo_and_populate(
        req,
        template_version="saas-ai-automation.v1",
        rendered_architecture_md="# arch",
    )
    repo_tools.bootstrap_project_repo.assert_not_called()


def test_create_architecture_doc_writes_rendered_text_to_feishu():
    from requirement_workflow_v12.project_bootstrap.types import BootstrapStep
    from requirement_workflow_v12.project_config import ProjectConfig

    existing = ProjectConfig(
        category="saas-ai-automation",
        template_version="saas-ai-automation.v1",
        architecture_doc_id="",
        architecture_doc_url="",
        bootstrap_status="BOOTSTRAPPING",
        github_repo_url="https://github.com/Snowziio/test3",
        bootstrap_log=[
            {"step": int(s), "step_name": s.name, "ts": "t", "status": "ok"}
            for s in (
                BootstrapStep.UPSERT_CONFIG,
                BootstrapStep.CREATE_REPO,
                BootstrapStep.POPULATE_MAIN,
            )
        ],
    )
    svc, _, feishu_gw, _ = _make_service(existing_projects={"test3": existing})
    feishu_gw.create_architecture_document.return_value = MagicMock(
        document_id="doc_arch", document_url="https://feishu.example/doc_arch"
    )
    feishu_gw.write_document_text.return_value = None

    req = BootstrapRequest(
        project="test3",
        category="saas-ai-automation",
        owner_user_id="ou_1",
        creator_chat_id="c1",
    )
    cfg = svc.create_architecture_doc(req, rendered_architecture_md="# arch doc content")

    assert cfg.architecture_doc_id == "doc_arch"
    assert cfg.architecture_doc_url == "https://feishu.example/doc_arch"
    feishu_gw.create_architecture_document.assert_called_once_with("test3")
    feishu_gw.write_document_text.assert_called_once_with("doc_arch", "# arch doc content")


def test_create_architecture_doc_skips_when_already_set():
    from requirement_workflow_v12.project_bootstrap.types import BootstrapStep
    from requirement_workflow_v12.project_config import ProjectConfig

    existing = ProjectConfig(
        category="saas-ai-automation",
        template_version="saas-ai-automation.v1",
        architecture_doc_id="doc_existing",
        architecture_doc_url="https://feishu.example/doc_existing",
        bootstrap_status="BOOTSTRAPPING",
        bootstrap_log=[
            {"step": int(s), "step_name": s.name, "ts": "t", "status": "ok"}
            for s in (
                BootstrapStep.UPSERT_CONFIG,
                BootstrapStep.CREATE_REPO,
                BootstrapStep.POPULATE_MAIN,
                BootstrapStep.CREATE_ARCHITECTURE_DOC,
            )
        ],
    )
    svc, _, feishu_gw, _ = _make_service(existing_projects={"test3": existing})
    req = BootstrapRequest(
        project="test3",
        category="saas-ai-automation",
        owner_user_id="ou_1",
        creator_chat_id="c1",
        resume=True,
    )
    svc.create_architecture_doc(req, rendered_architecture_md="# arch")
    feishu_gw.create_architecture_document.assert_not_called()


def test_upsert_config_preserves_existing_fields_on_resume():
    from requirement_workflow_v12.project_config import ProjectConfig

    existing = ProjectConfig(
        category="saas-ai-automation",
        template_version="saas-ai-automation.v1",
        architecture_doc_id="doc_old",
        architecture_doc_url="https://old",
        bootstrap_status="BOOTSTRAPPING",
        bootstrap_log=[
            {"step": 2, "step_name": "UPSERT_CONFIG", "ts": "old-ts", "status": "ok"}
        ],
    )
    svc, _, _, _ = _make_service(existing_projects={"test3": existing})
    req = BootstrapRequest(
        project="test3",
        category="saas-ai-automation",
        owner_user_id="ou_1",
        creator_chat_id="c1",
        resume=True,
    )
    cfg = svc.upsert_config(req, template_version="saas-ai-automation.v1")
    assert cfg.architecture_doc_id == "doc_old"
    assert cfg.bootstrap_status == "BOOTSTRAPPING"


def test_create_feishu_group_persists_chat_id():
    from requirement_workflow_v12.project_config import ProjectConfig
    from requirement_workflow_v12.project_bootstrap.types import BootstrapStep

    prior_steps = [
        BootstrapStep.UPSERT_CONFIG,
        BootstrapStep.CREATE_REPO,
        BootstrapStep.POPULATE_MAIN,
        BootstrapStep.CREATE_ARCHITECTURE_DOC,
    ]
    existing = ProjectConfig(
        category="saas-ai-automation",
        template_version="saas-ai-automation.v1",
        architecture_doc_id="doc_x",
        architecture_doc_url="https://example/doc_x",
        bootstrap_status="BOOTSTRAPPING",
        bootstrap_log=[
            {"step": int(s), "step_name": s.name, "ts": "t", "status": "ok"}
            for s in prior_steps
        ],
    )
    svc, _, feishu_gw, _ = _make_service(existing_projects={"test3": existing})
    feishu_gw.create_project_group.return_value = MagicMock(chat_id="oc_test3_group")

    req = BootstrapRequest(
        project="test3",
        category="saas-ai-automation",
        owner_user_id="ou_1",
        creator_chat_id="c1",
    )
    cfg = svc.create_feishu_group(req)
    assert cfg.feishu_chat_id == "oc_test3_group"
    feishu_gw.create_project_group.assert_called_once_with(
        project="test3", owner_user_id="ou_1", member_user_ids=["ou_1"]
    )


def test_create_feishu_group_skip_when_chat_id_already_set():
    from requirement_workflow_v12.project_config import ProjectConfig
    from requirement_workflow_v12.project_bootstrap.types import BootstrapStep

    prior_steps = [
        BootstrapStep.UPSERT_CONFIG,
        BootstrapStep.CREATE_REPO,
        BootstrapStep.POPULATE_MAIN,
        BootstrapStep.CREATE_ARCHITECTURE_DOC,
        BootstrapStep.CREATE_FEISHU_GROUP,
    ]
    existing = ProjectConfig(
        category="saas-ai-automation",
        template_version="saas-ai-automation.v1",
        architecture_doc_id="doc_x",
        architecture_doc_url="",
        bootstrap_status="BOOTSTRAPPING",
        feishu_chat_id="oc_existing",
        bootstrap_log=[
            {"step": int(s), "step_name": s.name, "ts": "t", "status": "ok"}
            for s in prior_steps
        ],
    )
    svc, _, feishu_gw, _ = _make_service(existing_projects={"test3": existing})
    req = BootstrapRequest(
        project="test3",
        category="saas-ai-automation",
        owner_user_id="ou_1",
        creator_chat_id="c1",
        resume=True,
    )
    svc.create_feishu_group(req)
    feishu_gw.create_project_group.assert_not_called()


def test_run_end_to_end_produces_provisioned_config_and_bootstrap_result():
    from requirement_workflow_v12.project_bootstrap.types import BootstrapStep
    from requirement_workflow_v12.project_repo.types import BootstrapRepoResult

    svc, repo_tools, feishu_gw, _ = _make_service()
    repo_tools.bootstrap_project_repo.return_value = BootstrapRepoResult(
        html_url="https://github.com/Snowziio/test3",
        default_branch="main",
        initial_populate_commit_sha="sha1",
    )
    feishu_gw.create_architecture_document.return_value = MagicMock(
        document_id="doc_x", document_url="https://feishu.example/doc_x",
    )
    feishu_gw.write_document_text.return_value = None
    feishu_gw.create_project_group.return_value = MagicMock(chat_id="oc_test3_group")

    state: dict = {}

    def _upsert(project, cfg):
        state[project] = cfg
        return cfg

    feishu_gw.upsert_project_config.side_effect = _upsert
    feishu_gw.list_project_configs.side_effect = lambda: dict(state)

    req = BootstrapRequest(
        project="test3",
        category="saas-ai-automation",
        owner_user_id="ou_1",
        creator_chat_id="c1",
        github_username="alice",
    )
    result = svc.run(req)
    assert result.project == "test3"
    assert result.github_repo_url == "https://github.com/Snowziio/test3"
    assert result.architecture_doc_id == "doc_x"
    assert result.feishu_chat_id == "oc_test3_group"
    final_cfg = state["test3"]
    assert final_cfg.bootstrap_status == "PROVISIONED"
    assert final_cfg.project_status == "PROVISIONED"
    assert final_cfg.bootstrap_completed_at is not None
    step_numbers = {e["step"] for e in final_cfg.bootstrap_log if e["status"] == "ok"}
    assert step_numbers == {int(s) for s in BootstrapStep}
