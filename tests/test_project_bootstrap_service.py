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
