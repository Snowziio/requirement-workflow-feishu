"""Layer-3 facade: domain verbs over GitHub primitives.

``ProjectRepoTools`` is the Protocol orchestrators depend on.
``GitHubProjectRepoTools`` is the default implementation that delegates
to ``GitHubGateway``. Errors from the gateway are wrapped in
``ProjectRepoError`` so layer 2 never sees HTTP-level exceptions.
"""
from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from ..github_gateway import GitHubGateway, GitHubGatewayError
from .types import PrRef, ProjectContext, SpecArtifacts


_logger = logging.getLogger(__name__)


class ProjectRepoError(RuntimeError):
    """Layer-3 error wrapping a lower-level gateway failure.

    ``recoverable=True`` hints the caller may retry (e.g. transient
    network issues); ``False`` means human intervention is needed.
    """

    def __init__(self, message: str, *, recoverable: bool = False):
        super().__init__(message)
        self.recoverable = recoverable


@runtime_checkable
class ProjectRepoTools(Protocol):
    """Domain-verb facade. Layer 2 depends only on this Protocol."""

    def fetch_project_context(self, project_repo: str) -> ProjectContext: ...

    def commit_spec_artifacts(
        self, req_id: str, artifacts: SpecArtifacts,
    ) -> PrRef: ...

    def cleanup_failed_branch(self, project_repo: str, branch: str) -> None: ...


class GitHubProjectRepoTools:
    """Default implementation; delegates to ``GitHubGateway``."""

    def __init__(self, gateway: "GitHubGateway"):
        self._gw = gateway

    def fetch_project_context(self, project_repo: str) -> ProjectContext:
        try:
            arch_sha, arch_text = self._gw.fetch_file_sha(
                project_repo, "main", "ARCHITECTURE.yaml",
            )
            registry_sha, registry_text = self._gw.fetch_file_sha(
                project_repo, "main", "acm-registry.yaml",
            )
        except GitHubGatewayError as exc:
            raise ProjectRepoError(
                f"fetch_project_context failed for {project_repo}: {exc}",
                recoverable=False,
            ) from exc
        return ProjectContext(
            project_repo=project_repo,
            arch_sha=arch_sha,
            arch_text=arch_text,
            registry_sha=registry_sha,
            registry_text=registry_text,
        )

    def cleanup_failed_branch(self, project_repo: str, branch: str) -> None:
        try:
            self._gw.delete_branch(project_repo, branch)
        except GitHubGatewayError as exc:
            _logger.warning(
                "cleanup_failed_branch could not delete %s/%s: %s",
                project_repo, branch, exc,
            )

    def commit_spec_artifacts(
        self, req_id: str, artifacts: SpecArtifacts,
    ) -> PrRef:
        owner, name = artifacts.project_repo.split("/", 1)
        try:
            self._gw.create_branch(
                owner=owner, repo=name,
                branch=artifacts.branch, from_branch=artifacts.base_branch,
            )
            head_sha = self._gw.commit_spec_pr_files(
                artifacts.project_repo, artifacts.branch,
                artifacts.files, artifacts.commit_message,
            )
            pr = self._gw.open_pull_request(
                owner=owner, repo=name,
                head_branch=artifacts.branch, base_branch=artifacts.base_branch,
                title=artifacts.pr_title, body=artifacts.pr_body,
            )
        except GitHubGatewayError as exc:
            self.cleanup_failed_branch(artifacts.project_repo, artifacts.branch)
            raise ProjectRepoError(
                f"commit_spec_artifacts failed for {req_id}: {exc}",
                recoverable=False,
            ) from exc
        return PrRef(
            number=int(pr["number"]),
            html_url=str(pr["html_url"]),
            head_sha=head_sha,
            branch=artifacts.branch,
        )
