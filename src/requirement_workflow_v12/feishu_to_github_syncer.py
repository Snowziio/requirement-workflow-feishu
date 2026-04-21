"""One-way Feishu → GitHub freeze-point syncer.

Closes the gap between the construction-phase SOT (Feishu docx where
humans co-edit plan.md / ARCHITECTURE / 9-section Spec) and the
implementation-phase SOT (GitHub, which AI reads). Invoked by state
transition hooks — Plan READY for plan/ARCHITECTURE, Checkpoint 1a for
the 9-section Spec — never by human action.

Keeps the module pure (Protocol deps only) so hooks can compose it with
any FeishuGateway/ProjectRepoTools pair without pulling in transport.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .project_repo import (
    PlanArtifacts,
    PlanCommitResult,
    ProjectRepoError,
    ProjectRepoTools,
    SpecMdArtifacts,
    SpecMdCommitResult,
)


_logger = logging.getLogger(__name__)


class FeishuSyncerError(RuntimeError):
    """Raised when the Feishu→GitHub sync cannot complete.

    ``recoverable`` mirrors ``ProjectRepoError.recoverable`` — True for
    transient causes (e.g., concurrent writes to ARCHITECTURE); False
    otherwise.
    """

    def __init__(self, message: str, *, recoverable: bool = False):
        super().__init__(message)
        self.recoverable = recoverable


@runtime_checkable
class FeishuDocReader(Protocol):
    """Minimal read surface the syncer needs from FeishuGateway."""

    def read_document_text(self, document_id: str) -> str: ...


@dataclass(frozen=True)
class PlanSyncResult:
    commit_sha: str
    plan_github_path: str
    architecture_updated: bool


@dataclass(frozen=True)
class SpecSyncResult:
    commit_sha: str
    spec_github_path: str


class FeishuToGitHubSyncer:
    """Freeze-point syncer for the time-phased SOT model.

    Feishu is authoritative during construction (read here); GitHub
    receives the frozen copy via ProjectRepoTools.
    """

    def __init__(
        self,
        *,
        feishu: FeishuDocReader,
        project_repo_tools: ProjectRepoTools,
    ) -> None:
        self._feishu = feishu
        self._tools = project_repo_tools

    def sync_plan(
        self,
        *,
        req_id: str,
        project_repo: str,
        plan_doc_id: str,
        project_context_change: dict | None,
        commit_message: str,
        fallback_plan_md: str = "",
    ) -> PlanSyncResult:
        """Freeze Feishu plan docx into GitHub docs/specs/<req_id>/plan.md.

        Prefers the Feishu SOT; only falls back to ``fallback_plan_md``
        (the pending_plan_review audit copy) when Feishu read fails and a
        fallback is explicitly provided. ``project_context_change``, if
        present, is applied to docs/ARCHITECTURE.md in the same commit.
        """
        plan_md = ""
        if plan_doc_id:
            try:
                plan_md = self._feishu.read_document_text(plan_doc_id)
            except Exception as exc:
                if not fallback_plan_md:
                    raise FeishuSyncerError(
                        f"sync_plan: cannot read Feishu plan doc {plan_doc_id}: {exc}",
                        recoverable=False,
                    ) from exc
                _logger.warning(
                    "sync_plan: Feishu read failed for doc_id=%s, falling back to audit copy: %s",
                    plan_doc_id, exc,
                )
                plan_md = fallback_plan_md
        else:
            if not fallback_plan_md:
                raise FeishuSyncerError(
                    "sync_plan: no plan_doc_id and no fallback_plan_md",
                    recoverable=False,
                )
            plan_md = fallback_plan_md

        artifacts = PlanArtifacts(
            project_repo=project_repo,
            req_id=req_id,
            plan_md_content=plan_md,
            project_context_change=project_context_change,
            commit_message=commit_message,
        )
        try:
            result: PlanCommitResult = self._tools.commit_plan_artifacts(artifacts)
        except ProjectRepoError as exc:
            raise FeishuSyncerError(
                f"sync_plan: commit to GitHub failed: {exc}",
                recoverable=exc.recoverable,
            ) from exc
        return PlanSyncResult(
            commit_sha=result.commit_sha,
            plan_github_path=result.plan_md_path,
            architecture_updated=result.architecture_updated,
        )

    def sync_spec(
        self,
        *,
        req_id: str,
        project_repo: str,
        spec_doc_id: str,
        commit_message: str,
        fallback_spec_md: str = "",
    ) -> SpecSyncResult:
        """Freeze Feishu 9-section spec docx into GitHub docs/specs/<req_id>/spec.md.

        Invoked at Checkpoint 1a — before the implementation-phase
        spec-transformer starts reading GitHub. ``fallback_spec_md`` is
        optional; the construction phase has no buffered audit copy by
        default, so callers normally leave it empty and let Feishu failure
        surface as ``FeishuSyncerError``.
        """
        spec_md = ""
        if spec_doc_id:
            try:
                spec_md = self._feishu.read_document_text(spec_doc_id)
            except Exception as exc:
                if not fallback_spec_md:
                    raise FeishuSyncerError(
                        f"sync_spec: cannot read Feishu spec doc {spec_doc_id}: {exc}",
                        recoverable=False,
                    ) from exc
                _logger.warning(
                    "sync_spec: Feishu read failed for doc_id=%s, falling back to audit copy: %s",
                    spec_doc_id, exc,
                )
                spec_md = fallback_spec_md
        else:
            if not fallback_spec_md:
                raise FeishuSyncerError(
                    "sync_spec: no spec_doc_id and no fallback_spec_md",
                    recoverable=False,
                )
            spec_md = fallback_spec_md

        artifacts = SpecMdArtifacts(
            project_repo=project_repo,
            req_id=req_id,
            spec_md_content=spec_md,
            commit_message=commit_message,
        )
        try:
            result: SpecMdCommitResult = self._tools.commit_spec_md(artifacts)
        except ProjectRepoError as exc:
            raise FeishuSyncerError(
                f"sync_spec: commit to GitHub failed: {exc}",
                recoverable=exc.recoverable,
            ) from exc
        return SpecSyncResult(
            commit_sha=result.commit_sha,
            spec_github_path=result.spec_md_path,
        )
