"""PLANNING-layer context builder used by plan-author agents."""
from __future__ import annotations

from .models import WorkflowStatus
from .plan_state_machine import PlanStatus


PLAN_CONTEXT_ALLOWED_STATUSES = {None, PlanStatus.DRAFTING}


class PlanContextGateError(Exception):
    def __init__(self, message: str, current_status: str) -> None:
        super().__init__(message)
        self.current_status = current_status


class PlanContextMisconfigured(Exception):
    """No ProjectConfig for this project."""


class PlanContextBuilder:
    def __init__(self, service) -> None:
        self._service = service

    def build(self, req_id: str) -> dict:
        r = self._service.requirements.get(req_id)
        if r is None:
            raise ValueError(f"未知需求：{req_id}")
        if (
            r.status != WorkflowStatus.APPROVED
            or r.plan_status not in PLAN_CONTEXT_ALLOWED_STATUSES
        ):
            plan_label = r.plan_status.value if r.plan_status else "None"
            raise PlanContextGateError(
                f"当前状态 status={r.status.value} plan_status={plan_label} "
                "不允许获取 plan-context",
                current_status=r.status.value,
            )
        cfg = self._service.project_configs.get(r.project)
        if cfg is None:
            raise PlanContextMisconfigured(f"项目 {r.project} 未初始化")

        return {
            "req_id": r.req_id,
            "project": r.project,
            "requirement_document_url": r.document_url,
            "needs_ui": r.needs_ui,
            "tech_stack": dict(cfg.tech_stack),
            "category": cfg.category,
            "template_version": cfg.template_version,
            "architecture_doc_url": cfg.architecture_doc_url,
            "project_repo": cfg.github_repo_url,
            "plan_doc_id": r.plan_doc_id,
            "plan_doc_url": r.plan_doc_url,
            "plan_outline": list(r.plan_outline),
            "plan_decisions_wip": list(r.plan_decisions_wip),
            "plan_phase": r.plan_phase.value if r.plan_phase else None,
            "design_artifact": self._design_artifact_slice(r),
        }

    def _design_artifact_slice(self, r) -> dict:
        return {
            "archive_path": getattr(r, "design_archive_path", "") or "",
            "needs_ui": getattr(r, "needs_ui", False),
            "design_status": r.design_status.value if getattr(r, "design_status", None) else None,
        }
