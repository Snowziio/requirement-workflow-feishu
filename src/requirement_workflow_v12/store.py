from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .models import (
    DiscussionTurn,
    HumanReviewResult,
    Requirement,
    ReviewFinding,
    ReviewResult,
    WorkflowStatus,
    utc_now,
)
from .plan_state_machine import DesignStatus, PlanPhase, PlanStatus
from .project_config import ProjectConfig
from .spec_state_machine import SpecStatus

LEGACY_STATUS_ALIASES = {
    "DISCUSSION_ROUTING": WorkflowStatus.DRAFTING.value,
    "DISCUSSING": WorkflowStatus.DRAFTING.value,
    "AI_REVIEWING": WorkflowStatus.AI_REVIEW.value,
    "HUMAN_CONFIRMING": WorkflowStatus.HUMAN_CONFIRM.value,
    "REVIEWING": WorkflowStatus.FINAL_REVIEW.value,
    "REQ_APPROVED": WorkflowStatus.APPROVED.value,
    # Spec 子状态从 2026-04 起不再写入 Requirement.status；历史 state.json 里
    # 残留的 SPEC_DRAFTING/SPEC_LOCKED 一律回推为 APPROVED，spec_status 由下面
    # 的 LEGACY_SPEC_STATUS_BACKFILL 补齐。
    "SPEC_DRAFTING": WorkflowStatus.APPROVED.value,
    "SPEC_LOCKED": WorkflowStatus.APPROVED.value,
}

LEGACY_SPEC_STATUS_BACKFILL = {
    "SPEC_DRAFTING": "SPEC_DRAFTING",
    "SPEC_LOCKED": "SPEC_LOCKED",
}


class JsonStateStore:
    """Very small persistence layer for early deployment and local testing."""

    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def save_snapshot(
        self,
        requirements: dict[str, Requirement],
        active_req_by_user: dict[str, str],
        project_groups: dict[str, str],
    ) -> None:
        # project_configs is NOT persisted here anymore — the Bitable ProjectConfigs
        # table is the single source of truth. Coordinator loads it at startup via
        # FeishuGateway.list_project_configs() and upserts on every mutation.
        payload = {
            "requirements": {req_id: asdict(req) for req_id, req in requirements.items()},
            "active_req_by_user": active_req_by_user,
            "project_groups": project_groups,
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, default=str, indent=2))

    def load_snapshot(
        self,
    ) -> tuple[dict[str, Requirement], dict[str, str], dict[str, str], dict[str, ProjectConfig]]:
        # project_configs is returned as an empty dict for backward compatibility
        # with callers that still unpack 4 values; real data comes from the
        # Bitable ProjectConfigs table, not from state.json.
        if not self.path.exists():
            return {}, {}, {}, {}

        payload = json.loads(self.path.read_text())
        requirements = {
            req_id: self._requirement_from_payload(data)
            for req_id, data in payload.get("requirements", {}).items()
        }
        return (
            requirements,
            payload.get("active_req_by_user", {}),
            payload.get("project_groups", {}),
            {},
        )

    def _requirement_from_payload(self, data: dict) -> Requirement:
        discussion_history_payload = data.get("discussion_history", [])
        review_history_payload = data.get("review_history", [])
        human_review_history_payload = data.get("human_review_history", [])
        raw_status = str(data.get("status", WorkflowStatus.CREATED.value))
        normalized_status = LEGACY_STATUS_ALIASES.get(raw_status, raw_status)
        raw_spec_status = data.get("spec_status")
        if raw_spec_status in (None, "") and raw_status in LEGACY_SPEC_STATUS_BACKFILL:
            raw_spec_status = LEGACY_SPEC_STATUS_BACKFILL[raw_status]
        spec_status: SpecStatus | None
        if raw_spec_status in (None, ""):
            spec_status = None
        else:
            spec_status = SpecStatus(str(raw_spec_status))

        raw_plan_status = data.get("plan_status")
        plan_status = PlanStatus(str(raw_plan_status)) if raw_plan_status else None
        raw_plan_phase = data.get("plan_phase")
        plan_phase = PlanPhase(str(raw_plan_phase)) if raw_plan_phase else None
        raw_design_status = data.get("design_status")
        design_status = DesignStatus(str(raw_design_status)) if raw_design_status else None
        design_doc_id = str(data.get("design_doc_id") or "")
        design_doc_url = str(data.get("design_doc_url") or "")
        design_archive_path = str(data.get("design_archive_path") or "")
        design_github_revision = str(data.get("design_github_revision") or "")
        design_precondition_met = bool(data.get("design_precondition_met", False))
        pending_design_brief = data.get("pending_design_brief")
        if pending_design_brief is not None and not isinstance(pending_design_brief, dict):
            pending_design_brief = None
        pending_design_handoff = data.get("pending_design_handoff")
        if pending_design_handoff is not None and not isinstance(pending_design_handoff, dict):
            pending_design_handoff = None

        requirement = Requirement(
            req_id=data["req_id"],
            name=data["name"],
            project=data["project"],
            summary=data["summary"],
            creator=data["creator"],
            status=WorkflowStatus(normalized_status),
            current_phase=data.get("current_phase", "需求构造"),
            current_round=data.get("current_round", 0),
            current_discussion_field=data.get("current_discussion_field", ""),
            completed_fields=data.get("completed_fields", []),
            pending_fields=data.get("pending_fields", []),
            current_owner=data.get("current_owner", "coordinator-service"),
            current_role_label=data.get("current_role_label", "需求协调服务"),
            latest_review_summary=data.get("latest_review_summary", ""),
            ai_ready=data.get("ai_ready", False),
            human_confirmed=data.get("human_confirmed", False),
            latest_question=data.get("latest_question", ""),
            creator_user_id=data.get("creator_user_id", ""),
            creation_chat_id=data.get("creation_chat_id", ""),
            project_group_id=data.get("project_group_id", ""),
            author_dm_chat_id=data.get("author_dm_chat_id", ""),
            bitable_record_id=data.get("bitable_record_id", ""),
            document_id=data.get("document_id", ""),
            document_url=data.get("document_url", ""),
            active_private_binding_confirmed=data.get("active_private_binding_confirmed", False),
            latest_writeback_at=self._parse_datetime(data.get("latest_writeback_at")),
            needs_ui=data.get("needs_ui", False),
            hifi_prototype_url=data.get("hifi_prototype_url", ""),
            hifi_prototype_confirmed=data.get("hifi_prototype_confirmed", False),
            spec_status=spec_status,
            spec_document_id=data.get("spec_document_id", ""),
            spec_document_url=data.get("spec_document_url", ""),
            spec_review_summary=data.get("spec_review_summary", ""),
            active_spec_context_token=data.get("active_spec_context_token", ""),
            spec_context_snapshot_revision=data.get("spec_context_snapshot_revision", ""),
            spec_deadlocked=bool(data.get("spec_deadlocked", False)),
            spec_transform_snapshot=data.get("spec_transform_snapshot"),
            spec_pr_url=data.get("spec_pr_url", ""),
            spec_source_revision=data.get("spec_source_revision", ""),
            transform_trace_digest=data.get("transform_trace_digest", ""),
            plan_status=plan_status,
            plan_phase=plan_phase,
            plan_pr_url=data.get("plan_pr_url", ""),
            plan_outline=list(data.get("plan_outline", []) or []),
            plan_decisions_wip=list(data.get("plan_decisions_wip", []) or []),
            pending_plan_draft=data.get("pending_plan_draft"),
            pending_plan_review=data.get("pending_plan_review"),
            plan_doc_id=data.get("plan_doc_id", ""),
            plan_doc_url=data.get("plan_doc_url", ""),
            plan_github_path=data.get("plan_github_path", ""),
            plan_github_revision=data.get("plan_github_revision", ""),
            spec_github_path=data.get("spec_github_path", ""),
            spec_github_revision=data.get("spec_github_revision", ""),
            design_status=design_status,
            design_doc_id=design_doc_id,
            design_doc_url=design_doc_url,
            design_archive_path=design_archive_path,
            design_github_revision=design_github_revision,
            design_precondition_met=design_precondition_met,
            pending_design_brief=pending_design_brief,
            pending_design_handoff=pending_design_handoff,
            discussion_history=[self._discussion_turn_from_payload(item) for item in discussion_history_payload],
            review_history=[self._review_result_from_payload(item) for item in review_history_payload],
            human_review_history=[
                self._human_review_result_from_payload(item) for item in human_review_history_payload
            ],
            updated_at=self._parse_datetime(data.get("updated_at")) or utc_now(),
        )
        return requirement

    def _review_result_from_payload(self, data: dict) -> ReviewResult:
        return ReviewResult(
            ready_for_human_confirmation=data.get("ready_for_human_confirmation", False),
            summary=data.get("summary", ""),
            findings=[
                ReviewFinding(
                    dimension=item.get("dimension", ""),
                    summary=item.get("summary", ""),
                    severity=item.get("severity", ""),
                )
                for item in data.get("findings", [])
            ],
            weak_fields=[str(item) for item in data.get("weak_fields", [])],
            conflicts=[str(item) for item in data.get("conflicts", [])],
            non_testable_acceptance_criteria=[
                str(item) for item in data.get("non_testable_acceptance_criteria", [])
            ],
            next_focus=data.get("next_focus"),
            reviewed_at=self._parse_datetime(data.get("reviewed_at")) or utc_now(),
        )

    def _discussion_turn_from_payload(self, data: dict) -> DiscussionTurn:
        return DiscussionTurn(
            round_number=data.get("round_number", 0),
            focused_field=data.get("focused_field", ""),
            user_input=data.get("user_input", ""),
            review_summary=data.get("review_summary", ""),
            next_question=data.get("next_question", ""),
            ai_ready_after_review=data.get("ai_ready_after_review", False),
            created_at=self._parse_datetime(data.get("created_at")) or utc_now(),
        )

    def _human_review_result_from_payload(self, data: dict) -> HumanReviewResult:
        return HumanReviewResult(
            approved=data.get("approved", False),
            summary=data.get("summary", ""),
            reviewed_at=self._parse_datetime(data.get("reviewed_at")) or utc_now(),
        )

    def _parse_datetime(self, raw: str | None) -> datetime | None:
        if not raw:
            return None
        return datetime.fromisoformat(raw)
