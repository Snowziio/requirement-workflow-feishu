"""Regression: final_review_pass (both text and card paths) must trigger
design dispatch for needs_ui requirements.

The card-button path previously skipped dispatch_design_start_if_needed,
leaving APPROVED+needs_ui reqs stuck — the user hit the plan-start guard
saying "设计阶段未完成" with no way forward.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.models import Requirement, WorkflowStatus
from requirement_workflow_v12.plan_state_machine import DesignStatus
from requirement_workflow_v12.project_config import ProjectConfig


def _bootstrap_app_with_approved_needs_ui_req():
    """Build a CoordinatorRuntimeApp with a req ready to be final_review_pass'd."""
    from requirement_workflow_v12.coordinator_service import CoordinatorService
    from requirement_workflow_v12.service_app import CoordinatorRuntimeApp

    req = Requirement(
        req_id="REQ-X-001", name="n", project="X", summary="s",
        creator="c", creator_user_id="ou_alice",
        status=WorkflowStatus.FINAL_REVIEW, needs_ui=True,
        human_confirmed=True,  # required by approve_requirement state machine
    )
    cfg = ProjectConfig(
        category="saas-ai-automation",
        template_version="saas-ai-automation.v1",
        architecture_doc_id="d", architecture_doc_url="u",
        claude_design_project_url="https://claude.ai/design/p/xyz",
        github_repo_url="https://github.com/org/X",
        feishu_chat_id="oc_group",
    )
    svc = CoordinatorService()
    svc.requirements[req.req_id] = req
    svc.project_configs[req.project] = cfg

    app = CoordinatorRuntimeApp.__new__(CoordinatorRuntimeApp)
    app.service = svc
    app.gateway = MagicMock()
    app.gateway.create_design_document.return_value = MagicMock(
        document_id="design-doc-id", document_url="https://my.feishu.cn/docx/design",
    )
    # Stub methods _handle_card_action_payload depends on
    app._sync_requirement_outputs = MagicMock()
    app._save_state = MagicMock()
    app._dispatch_transition_notifications = MagicMock()
    app._mark_event_seen = MagicMock(return_value=True)
    app._seen_event_ids = {}
    app._seen_event_ids_max = 100
    return app, req


def test_final_review_pass_card_action_dispatches_design_for_needs_ui():
    """The fix — card-button path now calls _on_final_review_approved."""
    app, req = _bootstrap_app_with_approved_needs_ui_req()

    payload = {
        "header": {"event_id": "evt_card_approve"},
        "operator": {"open_id": "ou_alice", "user_id": "ou_alice"},
        "context": {"open_chat_id": "oc_x", "open_message_id": "om_1"},
        "action": {
            "value": {
                "action": "final_review_pass",
                "req_id": req.req_id,
            },
        },
    }
    status, response = app._handle_card_action_payload(payload)

    assert status == 200
    assert response["toast"]["type"] == "success"
    refreshed = app.service.get_requirement(req.req_id)
    assert refreshed.status == WorkflowStatus.APPROVED
    # The key assertion: design phase was dispatched
    assert refreshed.design_status == DesignStatus.DRAFTING, (
        f"design dispatch missing; design_status={refreshed.design_status}"
    )
    app.gateway.create_design_document.assert_called_once()


def test_final_review_pass_card_action_skips_design_for_non_ui_req():
    """Non-UI requirements should approve without touching design pipeline."""
    app, req = _bootstrap_app_with_approved_needs_ui_req()
    # Flip needs_ui off
    req.needs_ui = False

    payload = {
        "header": {"event_id": "evt_card_approve_noui"},
        "operator": {"open_id": "ou_alice", "user_id": "ou_alice"},
        "context": {"open_chat_id": "oc_x", "open_message_id": "om_1"},
        "action": {
            "value": {
                "action": "final_review_pass",
                "req_id": req.req_id,
            },
        },
    }
    status, _ = app._handle_card_action_payload(payload)

    assert status == 200
    refreshed = app.service.get_requirement(req.req_id)
    assert refreshed.status == WorkflowStatus.APPROVED
    assert refreshed.design_status is None
    app.gateway.create_design_document.assert_not_called()


def test_final_review_reject_card_action_does_not_dispatch_design():
    """Rejection path must not trigger design regardless of needs_ui."""
    app, req = _bootstrap_app_with_approved_needs_ui_req()

    payload = {
        "header": {"event_id": "evt_card_reject"},
        "operator": {"open_id": "ou_alice", "user_id": "ou_alice"},
        "context": {"open_chat_id": "oc_x", "open_message_id": "om_1"},
        "action": {
            "value": {
                "action": "final_review_reject",
                "req_id": req.req_id,
            },
        },
    }
    status, _ = app._handle_card_action_payload(payload)

    assert status == 200
    refreshed = app.service.get_requirement(req.req_id)
    assert refreshed.status != WorkflowStatus.APPROVED
    app.gateway.create_design_document.assert_not_called()
