"""P2: cards self-lock after a decision button is clicked.

Each of the 5 main decision buttons (human_confirm_yes/no, final_review_pass/
reject, approve_plan_submit/reject_plan_submit, design_final_approve/
reject, bind_claude_design_project) returns a ``card`` field in the
P2CardActionTriggerResponse so Feishu replaces the still-actionable card
with a locked variant — buttons gone, decision note shown.

Without this, the card stays clickable after the click, inviting double-
submissions and confusing the user about whether the action took effect.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.config import Settings
from requirement_workflow_v12.coordinator_service import CoordinatorService
from requirement_workflow_v12.models import Requirement, WorkflowStatus
from requirement_workflow_v12.plan_state_machine import (
    DesignStatus, PlanPhase, PlanStatus,
)
from requirement_workflow_v12.project_config import ProjectConfig
from requirement_workflow_v12.service_app import CoordinatorRuntimeApp
from requirement_workflow_v12.store import JsonStateStore


# ── Fixtures ────────────────────────────────────────────────────


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


def _seed_requirement(app, *, req_id="REQ-LOCK-1", **overrides) -> Requirement:
    r = Requirement(
        req_id=req_id, name="lock-test", project="P", summary="s", creator="c",
    )
    r.status = WorkflowStatus.APPROVED
    r.creator_user_id = "ou_alice"
    for k, v in overrides.items():
        setattr(r, k, v)
    app.service.requirements[req_id] = r
    app.service.project_configs["P"] = ProjectConfig(
        category="web", template_version="v1",
        architecture_doc_id="", architecture_doc_url="",
        tech_stack={"backend": "py"}, github_repo_url="o/r",
    )
    return r


def _payload(action: str, req_id: str, **extra) -> dict:
    value = {"action": action, "req_id": req_id, **extra}
    return {
        "operator": {"open_id": "ou_alice", "name": "Alice"},
        "context": {"open_chat_id": "oc_dm", "open_message_id": "om_1"},
        "action": {"value": value, "form_value": {}},
    }


def _has_action_buttons(card: dict) -> bool:
    """True iff the card contains any callback button (column_set with button)."""
    for el in card.get("elements", []) or []:
        if not isinstance(el, dict):
            continue
        if el.get("tag") == "column_set":
            for col in el.get("columns", []) or []:
                for inner in (col.get("elements") if isinstance(col, dict) else []) or []:
                    if isinstance(inner, dict) and inner.get("tag") == "button":
                        return True
        if el.get("tag") == "button":
            return True
        if el.get("tag") == "form":
            for inner in el.get("elements", []) or []:
                if isinstance(inner, dict) and inner.get("tag") == "button":
                    return True
    return False


def _flat_text(node) -> str:
    out: list[str] = []
    if isinstance(node, dict):
        c = node.get("content")
        if isinstance(c, str):
            out.append(c)
        for v in node.values():
            out.append(_flat_text(v))
    elif isinstance(node, list):
        for v in node:
            out.append(_flat_text(v))
    return " ".join(s for s in out if s)


# ── 1. human_confirm_yes / human_confirm_no ────────────────────


def test_human_confirm_yes_response_includes_locked_card(app):
    r = _seed_requirement(app)
    r.status = WorkflowStatus.HUMAN_CONFIRM
    r.ai_ready = True

    status, resp = app._handle_card_action_payload(
        _payload("human_confirm_yes", r.req_id)
    )

    assert status == 200
    assert resp.get("toast", {}).get("type") == "success"
    card_envelope = resp.get("card")
    assert card_envelope is not None, "human_confirm_yes must return a card to lock the original"
    assert card_envelope.get("type") == "raw"
    locked = card_envelope.get("data") or {}
    assert not _has_action_buttons(locked)
    assert "操作结果" in _flat_text(locked)


def test_human_confirm_no_response_includes_locked_card(app):
    r = _seed_requirement(app)
    r.status = WorkflowStatus.HUMAN_CONFIRM

    status, resp = app._handle_card_action_payload(
        _payload("human_confirm_no", r.req_id)
    )

    assert status == 200
    locked = (resp.get("card") or {}).get("data") or {}
    assert not _has_action_buttons(locked)
    assert "操作结果" in _flat_text(locked)


# ── 2. final_review_pass / final_review_reject ─────────────────


def test_final_review_pass_response_includes_locked_card(app):
    r = _seed_requirement(app)
    r.status = WorkflowStatus.FINAL_REVIEW
    r.ai_ready = True
    r.human_confirmed = True

    status, resp = app._handle_card_action_payload(
        _payload("final_review_pass", r.req_id)
    )

    assert status == 200
    locked = (resp.get("card") or {}).get("data") or {}
    assert not _has_action_buttons(locked)
    assert "操作结果" in _flat_text(locked)


def test_final_review_reject_response_includes_locked_card(app):
    r = _seed_requirement(app)
    r.status = WorkflowStatus.FINAL_REVIEW

    status, resp = app._handle_card_action_payload(
        _payload("final_review_reject", r.req_id)
    )

    assert status == 200
    locked = (resp.get("card") or {}).get("data") or {}
    assert not _has_action_buttons(locked)
    assert "操作结果" in _flat_text(locked)


# ── 3. approve_plan_submit / reject_plan_submit ────────────────


def _seed_plan_pending_review(app, r: Requirement) -> Requirement:
    """Lift `r` into a plan_phase=FINAL_REVIEW_PENDING state with a pending draft."""
    app.service.plan_start(r.req_id)
    r.plan_phase = PlanPhase.FINAL_REVIEW_PENDING
    r.pending_plan_review = {
        "plan_md_content": "# plan\n",
        "summary": "s",
        "project_context_change": None,
    }
    return r


def test_approve_plan_submit_response_includes_locked_card(app):
    r = _seed_plan_pending_review(app, _seed_requirement(app))

    class _StubTools:
        def commit_plan_artifacts(self, artifacts):
            from requirement_workflow_v12.project_repo import PlanCommitResult
            return PlanCommitResult(
                commit_sha="https://github.com/o/r/pull/1",
                branch="main",
                plan_md_path="docs/specs/REQ-LOCK-1/plan.md",
                architecture_updated=False,
            )
    app.service.configure_plan_hooks(tools=_StubTools())

    status, resp = app._handle_card_action_payload(
        _payload("approve_plan_submit", r.req_id)
    )

    assert status == 200
    locked = (resp.get("card") or {}).get("data") or {}
    assert not _has_action_buttons(locked)
    assert "操作结果" in _flat_text(locked)


def test_reject_plan_submit_response_includes_locked_card(app):
    r = _seed_plan_pending_review(app, _seed_requirement(app))

    status, resp = app._handle_card_action_payload(
        _payload("reject_plan_submit", r.req_id)
    )

    assert status == 200
    locked = (resp.get("card") or {}).get("data") or {}
    assert not _has_action_buttons(locked)
    assert "操作结果" in _flat_text(locked)


# ── 4. design_final_approve / design_final_reject ──────────────


def test_design_final_approve_response_includes_locked_card(app):
    r = _seed_requirement(app, needs_ui=True, design_status=DesignStatus.SUBMIT_PENDING_REVIEW)
    r.pending_design_handoff = {
        "archive_path": "design/archive/REQ-LOCK-1_x/",
        "pages_touched": [],
        "submitted_at": "2026-04-23T00:00:00+00:00",
    }

    def fake_approve(req_id, *, approved_by=""):
        r.design_status = DesignStatus.READY
        r.design_precondition_met = True
        return r
    app.service.design_final_approve = MagicMock(side_effect=fake_approve)

    status, resp = app._handle_card_action_payload(
        _payload("design_final_approve", r.req_id)
    )

    assert status == 200
    locked = (resp.get("card") or {}).get("data") or {}
    assert not _has_action_buttons(locked)
    assert "操作结果" in _flat_text(locked)


def test_design_final_reject_response_includes_locked_card(app):
    r = _seed_requirement(app, needs_ui=True, design_status=DesignStatus.SUBMIT_PENDING_REVIEW)
    app.service.design_final_reject = MagicMock(return_value=r)

    status, resp = app._handle_card_action_payload(
        _payload("design_final_reject", r.req_id, reason="配色")
    )

    assert status == 200
    locked = (resp.get("card") or {}).get("data") or {}
    assert not _has_action_buttons(locked)
    assert "操作结果" in _flat_text(locked)


# ── 5. bind_claude_design_project (form save) ──────────────────


def test_submit_create_requirement_response_includes_locked_card(app):
    """新建需求 form's 提交 button locks the card on success — without this,
    users see no visual change after submit and may double-click, producing
    duplicate requirements."""
    _seed_requirement(app)
    cfg = app.service.project_configs["P"]
    from dataclasses import replace
    app.service.project_configs["P"] = replace(cfg, bootstrap_status="PROVISIONED")

    # Stub the threaded provisioning + creation so the test doesn't actually
    # mutate state or sleep. We only care about the response shape.
    app._provision_requirement_after_creation = MagicMock()

    payload = {
        "operator": {"open_id": "ou_alice", "name": "Alice"},
        "context": {"open_chat_id": "oc_creation_group", "open_message_id": "om_form"},
        "action": {
            "value": {"action": "submit_create_requirement"},
            "form_value": {
                "project": "P",
                "name": "测试需求",
                "summary": "做个东西",
                "needs_ui": "no",
            },
        },
    }

    status, resp = app._handle_card_action_payload(payload)

    assert status == 200
    assert resp.get("toast", {}).get("type") == "success"
    locked = (resp.get("card") or {}).get("data") or {}
    assert not _has_action_buttons(locked)
    text = _flat_text(locked)
    assert "已受理" in text or "已提交" in text
    # Surface what was submitted so the user sees it landed
    assert "测试需求" in text


def test_submit_create_project_response_includes_locked_card(app):
    """新建项目 form's 提交 button locks the card on success and shows the
    project being bootstrapped."""
    # Wire a stub bootstrap service so the handler doesn't NoOp.
    app._project_bootstrap_service = MagicMock()
    app._run_project_bootstrap_async = MagicMock()

    payload = {
        "operator": {"open_id": "ou_alice", "name": "Alice"},
        "context": {"open_chat_id": "oc_creation_group", "open_message_id": "om_proj"},
        "action": {
            "value": {"action": "submit_create_project"},
            "form_value": {
                "project": "newproj",
                "category": "enterprise-app",
                "display_name": "New Project",
            },
        },
    }

    status, resp = app._handle_card_action_payload(payload)

    assert status == 200
    locked = (resp.get("card") or {}).get("data") or {}
    assert not _has_action_buttons(locked)
    text = _flat_text(locked)
    assert "newproj" in text
    assert "Bootstrap" in text or "创建中" in text or "受理" in text


def _seed_plan_auth_pending(app, r: Requirement) -> Requirement:
    """Lift `r` into plan_status=AUTH_PENDING with a pending_plan_draft."""
    app.service.plan_start(r.req_id)
    r.plan_status = PlanStatus.AUTH_PENDING
    r.pending_plan_draft = {
        "plan_md_content": "# plan\n",
        "project_context_change": {"summary": "add x", "changes": []},
        "summary": "s",
    }
    return r


def test_authorize_plan_context_change_response_includes_locked_card(app):
    """plan_auth_pending card's "授权项目级变更" decision must lock after click."""
    r = _seed_plan_auth_pending(app, _seed_requirement(app))

    # Stub the hook's tool to prevent real GitHub commit
    class _StubTools:
        def commit_plan_artifacts(self, artifacts):
            from requirement_workflow_v12.project_repo import PlanCommitResult
            return PlanCommitResult(
                commit_sha="https://github.com/o/r/pull/2",
                branch="main",
                plan_md_path="docs/specs/REQ-LOCK-1/plan.md",
                architecture_updated=True,
            )
    app.service.configure_plan_hooks(tools=_StubTools())

    payload = {
        "operator": {"open_id": "ou_alice", "user_id": "ou_alice"},
        "context": {"open_chat_id": "oc_dm", "open_message_id": "om_auth"},
        "action": {
            "value": {"action": "authorize_plan_context_change", "req_id": r.req_id},
            "form_value": {},
        },
    }

    status, resp = app._handle_card_action_payload(payload)

    assert status == 200
    assert resp.get("toast", {}).get("type") == "success"
    locked = (resp.get("card") or {}).get("data") or {}
    assert not _has_action_buttons(locked)
    assert "操作结果" in _flat_text(locked)


def test_reject_plan_context_change_response_includes_locked_card(app):
    """plan_auth_pending card's "驳回变更" must also lock."""
    r = _seed_plan_auth_pending(app, _seed_requirement(app))

    payload = {
        "operator": {"open_id": "ou_alice", "user_id": "ou_alice"},
        "context": {"open_chat_id": "oc_dm", "open_message_id": "om_rej"},
        "action": {
            "value": {"action": "reject_plan_context_change", "req_id": r.req_id, "reason": "太宽"},
            "form_value": {},
        },
    }

    status, resp = app._handle_card_action_payload(payload)

    assert status == 200
    locked = (resp.get("card") or {}).get("data") or {}
    assert not _has_action_buttons(locked)
    assert "操作结果" in _flat_text(locked)


def test_bind_claude_design_project_response_includes_locked_card(app):
    r = _seed_requirement(app)
    payload = {
        "operator": {"open_id": "ou_alice", "name": "Alice"},
        "context": {"open_chat_id": "oc_dm", "open_message_id": "om_2"},
        "action": {
            "value": {"action": "bind_claude_design_project", "project": "P"},
            "form_value": {"claude_design_project_url": "https://claude.ai/design/p/abc"},
        },
    }

    status, resp = app._handle_card_action_payload(payload)

    assert status == 200
    assert resp.get("toast", {}).get("type") == "success"
    locked = (resp.get("card") or {}).get("data") or {}
    assert not _has_action_buttons(locked)
    text = _flat_text(locked)
    # Locked card surfaces the saved URL so the user sees what was persisted
    assert "https://claude.ai/design/p/abc" in text
