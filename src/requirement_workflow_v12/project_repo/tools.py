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
