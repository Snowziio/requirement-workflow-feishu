"""Tests for plan-wiring card flow in service_app."""
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
from requirement_workflow_v12.project_config import ProjectConfig
from requirement_workflow_v12.service_app import CoordinatorRuntimeApp
from requirement_workflow_v12.store import JsonStateStore


@pytest.fixture
def app(tmp_path):
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
    return CoordinatorRuntimeApp(
        settings=settings, store=store, service=svc, gateway=gw,
    )


def _approved_req(app, req_id="REQ-PW-1"):
    r = Requirement(
        req_id=req_id, name="Plan-Wiring Demo", project="P", summary="s", creator="c",
    )
    r.status = WorkflowStatus.APPROVED
    r.creator_user_id = "ou_alice"
    app.service.requirements[req_id] = r
    app.service.project_configs["P"] = ProjectConfig(
        category="web", template_version="v1",
        architecture_doc_id="", architecture_doc_url="",
        tech_stack={"backend": "py"}, github_repo_url="o/r",
    )
    return r


def _operator() -> dict:
    return {"open_id": "ou_alice", "name": "Alice"}


def _card_payload(action: str, req_id: str, **extra) -> dict:
    value = {"action": action, "req_id": req_id, **extra}
    return {
        "operator": _operator(),
        "context": {"open_chat_id": "oc_x", "open_message_id": "om_1"},
        "action": {"value": value, "form_value": {}},
    }


def test_build_plan_author_handoff_text_contains_agent_and_req(app):
    r = _approved_req(app)
    r.document_url = "https://feishu.example/req-doc"

    text = app._build_plan_author_handoff_text(r)

    agent_name = app.settings.openclaw_plan_author_agent_name
    assert agent_name in text
    assert r.req_id in text
    assert r.name in text
    assert "https://feishu.example/req-doc" in text


def test_send_plan_author_start_transitions_state_and_dispatches_dm(app):
    r = _approved_req(app)
    app.gateway.user_id_from_open_id = MagicMock(return_value=("ou_alice", "open_id"))

    status, resp = app._handle_card_action_payload(
        _card_payload("send_plan_author_start", r.req_id)
    )

    assert status == 200
    assert resp.get("toast", {}).get("type") == "success"
    assert r.plan_status == PlanStatus.DRAFTING
    assert r.plan_phase == PlanPhase.OUTLINE_PENDING
    app.gateway.send_text.assert_called_once()
    send_args = app.gateway.send_text.call_args
    text = send_args.args[1]
    assert "Plan 撰写" in text
    assert r.req_id in text


def test_send_plan_author_start_rejects_when_not_approved(app):
    r = _approved_req(app)
    r.status = WorkflowStatus.DRAFTING

    status, resp = app._handle_card_action_payload(
        _card_payload("send_plan_author_start", r.req_id)
    )

    assert status == 200
    assert resp.get("toast", {}).get("type") == "error"
    assert r.plan_status is None
    app.gateway.send_text.assert_not_called()


def test_send_plan_author_start_unknown_req_id_returns_error_toast(app):
    status, resp = app._handle_card_action_payload(
        _card_payload("send_plan_author_start", "NOPE")
    )
    assert status == 200
    assert resp.get("toast", {}).get("type") == "error"
    app.gateway.send_text.assert_not_called()


def test_final_review_passed_card_has_plan_button(app):
    r = _approved_req(app)

    actions = app._build_transition_notification_actions(r, trigger="final_review_passed")

    assert len(actions) == 1
    assert actions[0]["value"]["action"] == "send_plan_author_start"
    assert "Plan 撰写" in actions[0]["text"]["content"]


def test_final_review_passed_card_content_mentions_plan(app):
    r = _approved_req(app)
    template, title, reason, result, next_action = app._transition_notification_content(
        r, trigger="final_review_passed"
    )
    assert "Plan" in next_action


def test_plan_submitted_pending_review_content_and_actions(app):
    r = _approved_req(app)

    template, title, reason, result, next_action = app._transition_notification_content(
        r, trigger="plan_submitted_pending_review"
    )
    assert title  # non-empty
    assert "Plan" in title
    assert "审查" in result or "审查" in next_action

    actions = app._build_transition_notification_actions(r, trigger="plan_submitted_pending_review")
    action_names = {a["value"]["action"] for a in actions}
    assert action_names == {"approve_plan_submit", "reject_plan_submit"}


def _seed_pending_review(app, r, *, with_acc=False):
    """Drive a requirement to plan_status=DRAFTING + pending_plan_review set."""
    app.service.plan_start(r.req_id)
    r.plan_phase = PlanPhase.FINAL_REVIEW_PENDING
    r.pending_plan_review = {
        "plan_md_content": "# plan\n...",
        "project_context_change": {"foo": "bar"} if with_acc else None,
        "submitted_at": "2026-04-21T00:00:00+00:00",
    }
    return r


def test_approve_plan_submit_transitions_to_ready_and_clears_pending(app):
    r = _seed_pending_review(app, _approved_req(app))

    # Stub the hook's tool to prevent real GitHub calls; see configure_plan_hooks.
    class _StubTools:
        def commit_plan_artifacts(self, artifacts):
            from requirement_workflow_v12.project_repo import PlanCommitResult
            return PlanCommitResult(
                commit_sha="https://github.com/o/r/pull/1",
                branch="main",
                plan_md_path="docs/specs/REQ-PW-1/plan.md",
                architecture_updated=False,
            )
    app.service.configure_plan_hooks(tools=_StubTools())

    status, resp = app._handle_card_action_payload(
        _card_payload("approve_plan_submit", r.req_id)
    )

    assert status == 200
    assert resp.get("toast", {}).get("type") == "success"
    assert r.plan_status == PlanStatus.READY
    assert r.pending_plan_review is None
    assert r.plan_pr_url == "https://github.com/o/r/pull/1"


def test_approve_plan_submit_rejects_if_no_pending(app):
    r = _approved_req(app)
    app.service.plan_start(r.req_id)  # plan_phase=OUTLINE_PENDING, no pending review

    status, resp = app._handle_card_action_payload(
        _card_payload("approve_plan_submit", r.req_id)
    )

    assert status == 200
    assert resp.get("toast", {}).get("type") == "error"
    assert r.plan_status == PlanStatus.DRAFTING


def test_approve_plan_submit_rejects_architecture_change(app):
    r = _seed_pending_review(app, _approved_req(app), with_acc=True)

    status, resp = app._handle_card_action_payload(
        _card_payload("approve_plan_submit", r.req_id)
    )

    assert status == 200
    assert resp.get("toast", {}).get("type") == "error"
    assert r.plan_status == PlanStatus.DRAFTING
    assert r.pending_plan_review is not None  # retained


def test_approve_plan_submit_retains_pending_on_service_error(app):
    r = _seed_pending_review(app, _approved_req(app))

    class _FailingTools:
        def commit_plan_artifacts(self, artifacts):
            raise RuntimeError("github down")
    app.service.configure_plan_hooks(tools=_FailingTools())

    status, resp = app._handle_card_action_payload(
        _card_payload("approve_plan_submit", r.req_id)
    )

    assert status == 200
    assert resp.get("toast", {}).get("type") == "error"
    assert r.pending_plan_review is not None  # user can retry
