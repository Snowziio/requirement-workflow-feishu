"""DESIGN-layer context builder used by design-brief-author skill."""
from __future__ import annotations

from typing import Any

from .models import WorkflowStatus
from .plan_state_machine import DesignStatus


DESIGN_CONTEXT_ALLOWED_STATUSES = {DesignStatus.DRAFTING}


class DesignContextGateError(Exception):
    def __init__(self, message: str, current_status: str) -> None:
        super().__init__(message)
        self.current_status = current_status


class DesignContextMisconfigured(Exception):
    """No ProjectConfig for this project."""


class DesignContextBuilder:
    def __init__(self, service) -> None:
        self._service = service

    def build(self, req_id: str) -> dict[str, Any]:
        r = self._service.requirements.get(req_id)
        if r is None:
            raise ValueError(f"未知需求：{req_id}")
        if r.status != WorkflowStatus.APPROVED or not r.needs_ui:
            raise DesignContextGateError(
                f"design-context 要求 APPROVED + needs_ui=true; "
                f"got status={r.status.value} needs_ui={r.needs_ui}",
                current_status=r.status.value,
            )
        if r.design_status not in DESIGN_CONTEXT_ALLOWED_STATUSES:
            label = r.design_status.value if r.design_status else "None"
            raise DesignContextGateError(
                f"design-context 要求 DesignStatus=DRAFTING; got {label}",
                current_status=r.status.value,
            )
        cfg = self._service.project_configs.get(r.project)
        if cfg is None:
            raise DesignContextMisconfigured(f"项目 {r.project} 未初始化")

        current_pages = self._load_pages_registry_slice(cfg)
        prior_archive = self._find_prior_archive(req_id, r.project)

        return {
            "req_id": r.req_id,
            "project": r.project,
            "requirement_document_url": r.document_url,
            "needs_ui": r.needs_ui,
            "claude_design_project_url": getattr(cfg, "claude_design_project_url", ""),
            "frontend_subpath": getattr(cfg, "frontend_subpath", ""),
            "frontend_tech_stack": dict(getattr(cfg, "tech_stack", {})),
            "category": cfg.category,
            "template_version": cfg.template_version,
            "architecture_doc_url": cfg.architecture_doc_url,
            "project_repo": cfg.github_repo_url,
            "design_doc_id": r.design_doc_id,
            "design_doc_url": r.design_doc_url,
            "current_pages": current_pages,
            "prior_handoff_archive_ref": prior_archive,
        }

    def _load_pages_registry_slice(self, cfg) -> list[dict]:
        """Read design/PAGES.yaml from the project repo (if accessible).

        In MVP we return [] when the file is unreachable (no project repo cloned
        locally for coordinator to read). Real integration hooks this to a
        project-repo gateway in a future task.
        """
        return []

    def _find_prior_archive(self, req_id: str, project: str) -> str:
        """Return path of the most recent predecessor REQ's design archive.

        v1: returns "" — the coordinator does not have filesystem access to the
        project repo to enumerate. The skill handles empty gracefully.
        """
        return ""
