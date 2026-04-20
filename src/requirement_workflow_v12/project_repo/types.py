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
    """Reference to a GitHub repository.

    ``initial_commit_sha`` is the sha of the first commit after Bootstrap's
    Populate step (Step 4). Used by callers that want a post-Bootstrap
    anchor (e.g., e2e fixtures).
    """
    owner: str
    name: str
    html_url: str
    default_branch: str
    initial_commit_sha: str


@dataclass(frozen=True)
class BootstrapRepoResult:
    """Returned by ``ProjectRepoTools.bootstrap_project_repo``.

    ``initial_populate_commit_sha`` is the sha of the Populate commit
    (Bootstrap Step 4); ``html_url`` is the URL of the generated or
    reused repo.
    """
    html_url: str
    default_branch: str
    initial_populate_commit_sha: str


@dataclass(frozen=True)
class PlanArtifacts:
    """plan.md content + optional structured architecture diff.

    ``architecture_change`` is the raw payload (dict) carrying
    ``summary`` / ``changes[]`` / ``authorized*`` — matches plan-author's
    callback schema. ``None`` means this plan doesn't touch ARCHITECTURE.md.
    """
    project_repo: str
    req_id: str
    plan_md_content: str
    architecture_change: dict | None
    commit_message: str


@dataclass(frozen=True)
class PlanCommitResult:
    commit_sha: str
    branch: str
    plan_md_path: str
    architecture_updated: bool
