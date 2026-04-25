from __future__ import annotations

import secrets
import time
from dataclasses import dataclass

from .models import WorkflowStatus
from .plan_state_machine import PlanStatus
from .spec_state_machine import SpecStatus


# Spec-context 端点准入：requirement 必须 APPROVED；spec 子状态必须是 None（尚未开始）
# 或 DRAFTING（重入握手）。SPEC_LOCKED 不允许再次拉取上下文。
SPEC_CONTEXT_ALLOWED_SPEC_STATUSES = {None, SpecStatus.DRAFTING}


class SpecContextGateError(Exception):
    """Requirement is not in a state that permits spec-context retrieval."""

    def __init__(self, message: str, current_status: str) -> None:
        super().__init__(message)
        self.current_status = current_status


class SpecContextMisconfigured(Exception):
    """Project has no ProjectConfig — initialize_project never ran."""


class ConcurrentSpecInProgress(Exception):
    """Another REQ in the same project currently holds spec_status=SPEC_DRAFTING."""


@dataclass
class SpecContextResult:
    context: dict
    context_token: str


class SpecContextBuilder:
    def __init__(self, service, gateway) -> None:
        self._service = service
        self._gateway = gateway

    def build(self, req_id: str) -> SpecContextResult:
        requirement = self._service.get_requirement(req_id)
        if requirement is None:
            raise ValueError(f"未知需求：{req_id}")

        if (
            requirement.status != WorkflowStatus.APPROVED
            or requirement.spec_status not in SPEC_CONTEXT_ALLOWED_SPEC_STATUSES
        ):
            spec_label = (
                requirement.spec_status.value if requirement.spec_status else "None"
            )
            raise SpecContextGateError(
                f"当前状态 status={requirement.status.value} spec_status={spec_label} "
                "不允许获取 spec-context",
                current_status=requirement.status.value,
            )

        if requirement.plan_status != PlanStatus.READY:
            plan_label = (
                requirement.plan_status.value if requirement.plan_status else "None"
            )
            raise SpecContextGateError(
                f"spec-context 要求 plan_status=PLAN_READY，当前 plan_status={plan_label}",
                current_status=requirement.status.value,
            )

        project_cfg = self._service.project_configs.get(requirement.project)
        if project_cfg is None:
            raise SpecContextMisconfigured(
                f"项目 {requirement.project} 尚未初始化 ProjectConfig"
            )

        if self._service._has_concurrent_spec(
            requirement.project, exclude_req_id=req_id
        ):
            raise ConcurrentSpecInProgress(
                f"项目 {requirement.project} 已有另一条需求处于 spec_status=SPEC_DRAFTING，请先等待其锁定。"
            )

        revision = self._gateway.fetch_document_revision(project_cfg.architecture_doc_id)

        context_token = self._mint_token(req_id)
        requirement.active_spec_context_token = context_token

        context = {
            "req_id": requirement.req_id,
            "name": requirement.name,
            "project": requirement.project,
            "category": project_cfg.category,
            "status": requirement.status.value,
            "spec_status": requirement.spec_status.value if requirement.spec_status else None,
            "needs_ui": requirement.needs_ui,
            "hifi_prototype_url": requirement.hifi_prototype_url,
            "design_system_snapshot": None,
            "requirement_document_url": requirement.document_url,
            "architecture_doc_id": project_cfg.architecture_doc_id,
            "architecture_doc_url": project_cfg.architecture_doc_url,
            "architecture_doc_revision": revision,
            "template_version": project_cfg.template_version,
            "spec_document_url": requirement.spec_document_url,
            "spec_document_id": requirement.spec_document_id,
            "latest_review_summary": requirement.latest_review_summary,
            "design_artifact": self._design_artifact_slice(requirement),
        }
        plan_md = self._service._fetch_plan_md(req_id) if hasattr(
            self._service, "_fetch_plan_md",
        ) else ""
        context["plan_md_content"] = plan_md
        context["plan_decision_ids"] = _extract_decision_ids(plan_md)
        return SpecContextResult(context=context, context_token=context_token)

    @staticmethod
    def _mint_token(req_id: str) -> str:
        return f"spec_ctx_{req_id}_{int(time.time())}_{secrets.token_hex(4)}"

    def _design_artifact_slice(self, r) -> dict:
        return {
            "archive_path": getattr(r, "design_archive_path", "") or "",
            "needs_ui": getattr(r, "needs_ui", False),
            "design_status": r.design_status.value if getattr(r, "design_status", None) else None,
        }


def _extract_decision_ids(plan_md_text: str) -> list[str]:
    """Extract `- id: Dxx` lines from plan.md YAML frontmatter."""
    import re
    return re.findall(r"^\s*-\s*id:\s*([A-Za-z0-9]+)\s*$", plan_md_text, re.MULTILINE)
