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

        current_pages = self._load_pages_registry_slice(cfg, project=r.project)
        prior_archive = self._find_prior_archive(req_id, r.project)

        return {
            "req_id": r.req_id,
            "project": r.project,
            "requirement_name": r.name,
            "requirement_summary": r.summary,
            "requirement_document_id": getattr(r, "document_id", "") or "",
            "requirement_document_url": r.document_url,
            "needs_ui": r.needs_ui,
            "claude_design_project_url": getattr(cfg, "claude_design_project_url", ""),
            "frontend_subpath": getattr(cfg, "frontend_subpath", ""),
            "frontend_tech_stack": dict(
                getattr(cfg, "frontend_tech_stack", None)
                or getattr(cfg, "tech_stack", {})
            ),
            "category": cfg.category,
            "template_version": cfg.template_version,
            "architecture_doc_url": cfg.architecture_doc_url,
            "project_repo": cfg.github_repo_url,
            "design_doc_id": r.design_doc_id,
            "design_doc_url": r.design_doc_url,
            "current_pages": current_pages,
            "prior_handoff_archive_ref": prior_archive,
        }

    def _load_pages_registry_slice(self, cfg, *, project: str) -> list[dict]:
        """Read design/PAGES.yaml from the project repo (if accessible).

        The coordinator does not clone project repos in the current runtime,
        so use the durable Requirement.design_pages records from prior READY
        design handoffs as the local page registry slice.
        """
        pages_by_name: dict[str, dict] = {}
        for req in self._service.requirements.values():
            if req.project != project or req.design_status is not DesignStatus.READY:
                continue
            for page in getattr(req, "design_pages", []) or []:
                if not isinstance(page, dict):
                    continue
                name = str(page.get("display_name", "")).strip()
                if not name:
                    continue
                pages_by_name[name] = dict(page)
        return [pages_by_name[name] for name in sorted(pages_by_name)]

    def _find_prior_archive(self, req_id: str, project: str) -> str:
        """Return path of the most recent predecessor REQ's design archive.

        Uses coordinator state rather than GitHub: the last READY design handoff
        for the same project is the closest available predecessor.
        """
        candidates = [
            req for req in self._service.requirements.values()
            if req.project == project
            and req.req_id != req_id
            and req.design_status is DesignStatus.READY
            and getattr(req, "design_archive_path", "")
        ]
        if not candidates:
            return ""
        candidates.sort(key=lambda req: getattr(req, "updated_at", None), reverse=True)
        return candidates[0].design_archive_path
