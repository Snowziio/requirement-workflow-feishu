"""Tool-layer facade for GitHub (and future platforms) project repos.

Layer 3 in the four-layer spec architecture: orchestrators and coordinator
depend on this module instead of ``GitHubGateway`` directly.
"""
from __future__ import annotations

from .hooks import StateTransitionHooks
from .tools import GitHubProjectRepoTools, ProjectRepoError, ProjectRepoTools
from .types import (
    CommitRef,
    PlanArtifacts,
    PlanCommitResult,
    PrRef,
    ProjectContext,
    RepoRef,
    SpecArtifacts,
    SpecMdArtifacts,
    SpecMdCommitResult,
)

__all__ = [
    "CommitRef",
    "GitHubProjectRepoTools",
    "PlanArtifacts",
    "PlanCommitResult",
    "PrRef",
    "ProjectContext",
    "ProjectRepoError",
    "ProjectRepoTools",
    "RepoRef",
    "SpecArtifacts",
    "SpecMdArtifacts",
    "SpecMdCommitResult",
    "StateTransitionHooks",
]
