from __future__ import annotations

import logging
from datetime import datetime, timezone

try:
    from github import Github, GithubException
except ImportError:  # pragma: no cover
    Github = None  # type: ignore[assignment, misc]
    GithubException = Exception  # type: ignore[assignment, misc]

LOGGER = logging.getLogger(__name__)

_ARCHITECTURE_YAML_TEMPLATE = """\
# ARCHITECTURE.yaml
# 维护者: checkpoint-handler（自动更新）+ 人工（首次建立）
# 更新策略: 每次 Impl PR 合并后更新

version: "{date}"
project: {project}

tech_stack:
  language: {language}
  framework: {framework}
  database: {database}
  test_framework: {test_framework}

services: []
modules: []
data_models: []
external_dependencies: []
"""

_ACM_REGISTRY_TEMPLATE = """\
# spec/registry/consolidated.yaml
# 维护者: checkpoint-handler（自动更新）
# 更新策略: append-only

last_updated: "{date}"

registry: []
"""


class ProjectBootstrapper:
    def __init__(self, github_token: str, default_branch: str = "main") -> None:
        self.github_token = github_token
        self.default_branch = default_branch

    def render_architecture_yaml(self, project: str, tech_stack: dict[str, str]) -> str:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return _ARCHITECTURE_YAML_TEMPLATE.format(
            date=date,
            project=project,
            language=tech_stack.get("language", ""),
            framework=tech_stack.get("framework", ""),
            database=tech_stack.get("database", ""),
            test_framework=tech_stack.get("test_framework", ""),
        )

    def render_acm_registry_yaml(self) -> str:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return _ACM_REGISTRY_TEMPLATE.format(date=date)

    def bootstrap_new_project(
        self,
        repo_url: str,
        project: str,
        tech_stack: dict[str, str],
    ) -> None:
        """Path C: create ARCHITECTURE.yaml + ACM registry in GitHub repo."""
        if Github is None:
            raise RuntimeError("PyGithub not installed. Run: pip install PyGithub")

        repo_path = self._repo_path_from_url(repo_url)
        g = Github(self.github_token)
        repo = g.get_repo(repo_path)

        arch_yaml = self.render_architecture_yaml(project, tech_stack)
        self._create_file_if_missing(
            repo,
            path="ARCHITECTURE.yaml",
            content=arch_yaml,
            commit_message="chore: initialize ARCHITECTURE.yaml (project context bootstrap)",
        )

        acm_yaml = self.render_acm_registry_yaml()
        self._create_file_if_missing(
            repo,
            path="spec/registry/consolidated.yaml",
            content=acm_yaml,
            commit_message="chore: initialize ACM registry (project context bootstrap)",
        )
        LOGGER.info("Bootstrap complete for project=%s repo=%s", project, repo_url)

    def verify_architecture_yaml_exists(self, repo_url: str) -> bool:
        """Used in path B to verify the user has run the bootstrap script."""
        if Github is None:
            return False
        try:
            repo_path = self._repo_path_from_url(repo_url)
            g = Github(self.github_token)
            repo = g.get_repo(repo_path)
            repo.get_contents("ARCHITECTURE.yaml")
            return True
        except Exception:
            return False

    def _create_file_if_missing(self, repo, path: str, content: str, commit_message: str) -> None:
        try:
            repo.get_contents(path)
            LOGGER.info("File already exists, skipping: %s", path)
        except Exception:
            repo.create_file(
                path=path,
                message=commit_message,
                content=content,
                branch=self.default_branch,
            )
            LOGGER.info("Created file: %s", path)

    @staticmethod
    def _repo_path_from_url(repo_url: str) -> str:
        """'https://github.com/org/repo' → 'org/repo'"""
        return repo_url.rstrip("/").removeprefix("https://github.com/")
