"""Unit tests for GitHubProjectRepoTools.bootstrap_project_repo."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.project_repo.tools import (
    GitHubProjectRepoTools,
    ProjectRepoError,
)


def _fake_gateway_happy():
    gw = MagicMock()
    gw.get_repo.return_value = None
    gw.create_repo_from_template.return_value = "https://github.com/Snowziio/test3"
    gw.commit_files.return_value = "commit_sha_1"
    gw.add_collaborator.return_value = None
    gw.wait_for_branch_ready.return_value = "generate_head_sha"
    return gw


def test_bootstrap_project_repo_generates_and_populates_main():
    gw = _fake_gateway_happy()
    tools = GitHubProjectRepoTools(gw)

    populate_files = {
        "docs/ARCHITECTURE.md": "# arch",
        "project/README.md": "# proj readme",
        "project/req-registry.yaml": "project: test3\nrequirements: []\n",
        "project/environments.yaml": "environments:\n  dev: {}\n",
        "project/SECRETS-TODO.md": "# secrets",
        "CLAUDE.md": "# claude",
        "SKILL.md": "# skill",
    }

    result = tools.bootstrap_project_repo(
        template_owner="Snowziio",
        template_repo="Template-repository",
        new_owner="Snowziio",
        new_name="test3",
        populate_files=populate_files,
        populate_commit_message="project bootstrap: populate",
        collaborator_username="alice",
    )

    assert result.html_url == "https://github.com/Snowziio/test3"
    assert result.initial_populate_commit_sha == "commit_sha_1"
    assert result.default_branch == "main"
    gw.create_repo_from_template.assert_called_once()
    gw.wait_for_branch_ready.assert_called_once_with("Snowziio", "test3", "main")
    # Order matters: must wait for main to be ready before commit_files.
    call_names = [c[0] for c in gw.method_calls]
    assert call_names.index("wait_for_branch_ready") < call_names.index("commit_files")
    gw.commit_files.assert_called_once()
    gw.add_collaborator.assert_called_once_with(
        owner="Snowziio", name="test3", username="alice", permission="push"
    )


def test_bootstrap_project_repo_does_not_wait_for_existing_repo():
    gw = MagicMock()
    gw.get_repo.return_value = {
        "html_url": "https://github.com/Snowziio/test3",
        "default_branch": "main",
    }
    gw.commit_files.return_value = "commit_sha_2"
    tools = GitHubProjectRepoTools(gw)
    tools.bootstrap_project_repo(
        template_owner="Snowziio",
        template_repo="Template-repository",
        new_owner="Snowziio",
        new_name="test3",
        populate_files={"CLAUDE.md": "x"},
        populate_commit_message="populate",
        collaborator_username=None,
    )
    gw.wait_for_branch_ready.assert_not_called()


def test_bootstrap_project_repo_skips_repo_creation_when_already_exists():
    gw = MagicMock()
    gw.get_repo.return_value = {
        "html_url": "https://github.com/Snowziio/test3",
        "default_branch": "main",
    }
    gw.commit_files.return_value = "commit_sha_2"

    tools = GitHubProjectRepoTools(gw)
    result = tools.bootstrap_project_repo(
        template_owner="Snowziio",
        template_repo="Template-repository",
        new_owner="Snowziio",
        new_name="test3",
        populate_files={"CLAUDE.md": "x"},
        populate_commit_message="populate",
        collaborator_username=None,
    )
    gw.create_repo_from_template.assert_not_called()
    gw.add_collaborator.assert_not_called()
    assert result.html_url == "https://github.com/Snowziio/test3"
    assert result.initial_populate_commit_sha == "commit_sha_2"


def test_bootstrap_project_repo_wraps_gateway_errors():
    from requirement_workflow_v12.github_gateway import GitHubGatewayError

    gw = MagicMock()
    gw.get_repo.return_value = None
    gw.create_repo_from_template.side_effect = GitHubGatewayError(500, "boom")

    tools = GitHubProjectRepoTools(gw)
    with pytest.raises(ProjectRepoError) as excinfo:
        tools.bootstrap_project_repo(
            template_owner="Snowziio",
            template_repo="Template-repository",
            new_owner="Snowziio",
            new_name="test3",
            populate_files={"CLAUDE.md": "x"},
            populate_commit_message="populate",
            collaborator_username=None,
        )
    assert "bootstrap_project_repo" in str(excinfo.value)
