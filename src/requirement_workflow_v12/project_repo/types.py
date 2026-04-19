"""Domain objects for the project-repo tool-layer facade.

These are pure data carriers, frozen to prevent accidental mutation as
they flow between layers. The layer-3 facade exchanges these with
orchestrators (layer 2); layer 4 primitives never see them.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProjectContext:
    """Structured snapshot of a project's current repo state.

    Returned by ``ProjectRepoTools.fetch_project_context``. Bundles the
    ARCHITECTURE + acm-registry shas and texts so callers don't have to
    juggle individual fetch calls.
    """
    project_repo: str
    arch_sha: str
    arch_text: str
    registry_sha: str
    registry_text: str


@dataclass(frozen=True)
class SpecArtifacts:
    """Spec-stage four-file payload + acm-registry patch bundled for commit.

    Input to ``ProjectRepoTools.commit_spec_artifacts``. ``files`` maps
    full repo path → text content; the facade commits them atomically.
    """
    project_repo: str
    branch: str
    base_branch: str
    files: dict[str, str]
    commit_message: str
    pr_title: str
    pr_body: str


@dataclass(frozen=True)
class CommitRef:
    sha: str
    branch: str


@dataclass(frozen=True)
class PrRef:
    number: int
    html_url: str
    head_sha: str
    branch: str


@dataclass(frozen=True)
class RepoRef:
    """Returned by Bootstrap once project-level repo generation lands.

    Unused in this iteration; reserved for the PLANNING spec so the
    domain model is stable when Bootstrap verbs are added.
    """
    owner: str
    name: str
    html_url: str
    default_branch: str
    initial_commit_sha: str
