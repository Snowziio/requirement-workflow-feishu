"""PLANNING-layer context builder used by plan-author agents.

The ``design_artifact`` slice implements the Coordinator side of the
Design → Plan alignment contract (methodology v3.0 §6.2.8). It gives
plan-author enough pointers to actually read the design output before
identifying decisions, avoiding two failure modes:

- decision duplication: plan-author proposes layout/color/interaction items
  the designer already decided in Claude Design
- decision omission: plan-author doesn't know the UI was designed, so
  plan-level UI-adjacent decisions (data source, routing, framework,
  token translation) never surface
"""
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
    def __init__(self, service, *, feishu_base_url: str = "https://my.feishu.cn") -> None:
        self._service = service
        self._feishu_base_url = feishu_base_url.rstrip("/")

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
            "design_artifact": self._design_artifact_slice(r, cfg),
        }

    def _design_artifact_slice(self, r, cfg) -> dict:
        """Build the design_artifact slice per §6.2.8.

        For needs_ui=true + DesignStatus=READY requirements, plan-author uses
        these pointers to (a) read the archive at the pinned commit SHA via
        GitHub, (b) consult the Feishu Brief + DS doc for visual context, and
        (c) enumerate which pages this REQ touched — so it can skip
        design-decided items and surface design-open boundary decisions.
        """
        ds_doc_id = getattr(cfg, "design_system_doc_id", None)
        design_system_doc_url = (
            f"{self._feishu_base_url}/docx/{ds_doc_id}"
            if ds_doc_id else ""
        )
        return {
            "archive_path": getattr(r, "design_archive_path", "") or "",
            "needs_ui": getattr(r, "needs_ui", False),
            "design_status": r.design_status.value if getattr(r, "design_status", None) else None,
            "github_revision": getattr(r, "design_github_revision", "") or "",
            "feishu_brief_url": getattr(r, "design_doc_url", "") or "",
            "design_system_doc_url": design_system_doc_url,
            "pages": list(getattr(r, "design_pages", []) or []),
        }
