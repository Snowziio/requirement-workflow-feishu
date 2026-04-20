"""Resume integration test: simulate a mid-flow failure and re-run with resume=True."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.project_bootstrap.service import (  # noqa: E402
    ProjectBootstrapService,
)
from requirement_workflow_v12.project_bootstrap.types import (  # noqa: E402
    BootstrapRequest,
    BootstrapStep,
    BootstrapStepError,
)
from requirement_workflow_v12.project_repo.types import BootstrapRepoResult  # noqa: E402


def _make_svc_with_state():
    repo_tools = MagicMock()
    feishu_gw = MagicMock()
    github_gw = MagicMock()
    state: dict = {}
    feishu_gw.list_project_configs.side_effect = lambda: dict(state)

    def _upsert(project, cfg):
        state[project] = cfg
        return cfg

    feishu_gw.upsert_project_config.side_effect = _upsert
    github_gw.get_repo.return_value = None
    svc = ProjectBootstrapService(
        repo_tools=repo_tools,
        feishu_gateway=feishu_gw,
        github_gateway=github_gw,
        template_owner="Snowziio",
        template_repo="Template-repository",
        new_owner="Snowziio",
    )
    return svc, repo_tools, feishu_gw, state


def test_run_recovers_after_failure_in_architecture_doc():
    svc, repo_tools, feishu_gw, state = _make_svc_with_state()
    repo_tools.bootstrap_project_repo.return_value = BootstrapRepoResult(
        html_url="https://github.com/Snowziio/test3",
        default_branch="main",
        initial_populate_commit_sha="sha1",
    )
    feishu_gw.create_architecture_document.side_effect = [
        RuntimeError("feishu down"),
        MagicMock(document_id="doc_x", document_url="https://feishu.example/doc_x"),
    ]
    feishu_gw.write_document_text.return_value = None
    feishu_gw.create_project_group.return_value = MagicMock(chat_id="oc_group")

    req = BootstrapRequest(
        project="test3",
        category="saas-ai-automation",
        owner_user_id="ou_1",
        creator_chat_id="c1",
    )
    with pytest.raises(BootstrapStepError) as exc_info:
        svc.run(req)
    assert exc_info.value.step == BootstrapStep.CREATE_ARCHITECTURE_DOC

    resume_req = BootstrapRequest(
        project="test3",
        category="saas-ai-automation",
        owner_user_id="ou_1",
        creator_chat_id="c1",
        resume=True,
    )
    result = svc.run(resume_req)
    assert result.architecture_doc_id == "doc_x"
    assert repo_tools.bootstrap_project_repo.call_count == 1
    assert state["test3"].bootstrap_status == "PROVISIONED"
