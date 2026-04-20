"""End-to-end: APPROVED → Plan 撰写 → Plan READY → Spec 撰写 handoff."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.config import Settings
from requirement_workflow_v12.coordinator_service import CoordinatorService
from requirement_workflow_v12.models import Requirement, WorkflowStatus
from requirement_workflow_v12.plan_state_machine import PlanStatus, PlanPhase
from requirement_workflow_v12.project_repo import PlanCommitResult
from requirement_workflow_v12.project_config import ProjectConfig
from requirement_workflow_v12.service_app import CoordinatorRuntimeApp
from requirement_workflow_v12.store import JsonStateStore


class _StubTools:
    def commit_plan_artifacts(self, artifacts):
        return PlanCommitResult(
            commit_sha="https://github.com/o/r/pull/1",
            branch="main",
            plan_md_path="docs/specs/REQ-E2E/plan.md",
            architecture_updated=False,
        )


def _operator() -> dict:
    return {"open_id": "ou_alice", "name": "Alice"}


def _card(action: str, req_id: str) -> dict:
    return {
        "operator": _operator(),
        "context": {"open_chat_id": "oc_x", "open_message_id": "om_e2e"},
        "action": {"value": {"action": action, "req_id": req_id}, "form_value": {}},
    }


def test_full_happy_path_approved_to_spec_handoff(tmp_path):
    settings = Settings(
        feishu_app_id="x", feishu_app_secret="y",
        feishu_verification_token="t", feishu_encrypt_key="",
        state_store_path=str(tmp_path / "state.json"),
        spec_trace_dir=str(tmp_path / "trace"),
        github_token="",
    )
    svc = CoordinatorService()
    store = JsonStateStore(settings.state_store_path)
    gw = MagicMock()
    gw.list_project_configs.return_value = {}
    gw.upsert_project_config.return_value = None
    gw.bitable_url.return_value = ""

    app = CoordinatorRuntimeApp(
        settings=settings, store=store, service=svc, gateway=gw,
    )
    app.service.configure_plan_hooks(tools=_StubTools())

    # Seed an APPROVED requirement on a known project.
    r = Requirement(
        req_id="REQ-E2E", name="E2E Plan-Wire", project="P", summary="s", creator="c",
    )
    r.status = WorkflowStatus.APPROVED
    r.creator_user_id = "ou_alice"
    svc.requirements["REQ-E2E"] = r
    svc.project_configs["P"] = ProjectConfig(
        category="web", template_version="v1",
        architecture_doc_id="", architecture_doc_url="",
        tech_stack={"backend": "py"}, github_repo_url="o/r",
    )

    # T1: Click "开始 Plan 撰写".
    status, resp = app._handle_card_action_payload(_card("send_plan_author_start", "REQ-E2E"))
    assert status == 200 and resp["toast"]["type"] == "success"
    assert r.plan_status == PlanStatus.DRAFTING
    assert r.plan_phase == PlanPhase.OUTLINE_PENDING

    # T2: plan-author /plan-context check — gate already passes at endpoint, smoke-skip here.

    # T3: Plan-author submits outline.
    svc.set_plan_outline("REQ-E2E", outline=[{"id": "D1", "title": "decision 1"}])
    assert r.plan_phase == PlanPhase.DECISIONS_IN_PROGRESS

    # T4: Plan-author POST /openclaw/plan-callback event=plan_submit.
    status, resp = app.handle_openclaw_plan_callback({
        "req_id": "REQ-E2E",
        "event": "plan_submit",
        "payload": {"plan_md_content": "# plan\nD1", "project_context_change": None},
    })
    assert status == 200
    assert r.plan_status == PlanStatus.DRAFTING  # still drafting!
    assert r.plan_phase == PlanPhase.FINAL_REVIEW_PENDING
    assert r.pending_plan_review is not None

    # T6: User clicks "通过".
    status, resp = app._handle_card_action_payload(_card("approve_plan_submit", "REQ-E2E"))
    assert status == 200 and resp["toast"]["type"] == "success"
    assert r.plan_status == PlanStatus.READY
    assert r.pending_plan_review is None
    assert r.plan_pr_url == "https://github.com/o/r/pull/1"

    # T8: User clicks "开始 Spec 撰写".
    gw.send_text.reset_mock()
    status, resp = app._handle_card_action_payload(_card("send_spec_author_start", "REQ-E2E"))
    assert status == 200
    assert resp["toast"]["type"] == "success"
    gw.send_text.assert_called()
    text = gw.send_text.call_args.args[1]
    assert "Spec 撰写" in text
    assert "REQ-E2E" in text
