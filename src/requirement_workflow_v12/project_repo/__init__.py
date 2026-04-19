"""Tool-layer facade for GitHub (and future platforms) project repos.

Layer 3 in the four-layer spec architecture: orchestrators and coordinator
depend on this module instead of ``GitHubGateway`` directly.
"""
from __future__ import annotations

from .tools import GitHubProjectRepoTools, ProjectRepoError, ProjectRepoTools
from .types import (
    CommitRef,
    PrRef,
    ProjectContext,
    RepoRef,
    SpecArtifacts,
)

__all__ = [
    "CommitRef",
    "GitHubProjectRepoTools",
    "PrRef",
    "ProjectContext",
    "ProjectRepoError",
    "ProjectRepoTools",
    "RepoRef",
    "SpecArtifacts",
]
