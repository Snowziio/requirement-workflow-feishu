"""Tool-layer facade for GitHub (and future platforms) project repos.

Layer 3 in the four-layer spec architecture: orchestrators and coordinator
depend on this module instead of ``GitHubGateway`` directly.
"""
from __future__ import annotations

from .types import (
    CommitRef,
    PrRef,
    ProjectContext,
    RepoRef,
    SpecArtifacts,
)

__all__ = [
    "CommitRef",
    "PrRef",
    "ProjectContext",
    "RepoRef",
    "SpecArtifacts",
]
