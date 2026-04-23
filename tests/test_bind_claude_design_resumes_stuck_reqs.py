"""When claude_design_project_url gets bound after a needs_ui req is already
APPROVED, the handler must retry design dispatch for that stuck req —
otherwise the flow deadlocks: the plan-start guard says "design incomplete"
but no one ever triggers design.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.models import Requirement, WorkflowStatus
from requirement_workflow_v12.plan_state_machine import DesignStatus
from requirement_workflow_v12.project_config import ProjectConfig


def _bootstrap_app_with_stuck_req():
    from requirement_workflow_v12.coordinator_service import CoordinatorService
    from requirement_workflow_v12.service_app import CoordinatorRuntimeApp

    req = Requirement(
        req_id="REQ-X-001", name="n", project="X", summary="s",
        creator="c", creator_user_id="ou_alice",
        status=WorkflowStatus.APPROVED, needs_ui=True,
        human_confirmed=True,
    )
    # Binding was initially empty — this is what caused the stuck state
    cfg = ProjectConfig(
        category="public-web-site",
        template_version="public-web-site.v1",
        architecture_doc_id="d", architecture_doc_url="u",
        claude_design_project_url="",  # <-- empty = blocked
        github_repo_url="https://github.com/org/X",
        feishu_chat_id="oc_group",
    )
    svc = CoordinatorService()
    svc.requirements[req.req_id] = req
    svc.project_configs[req.project] = cfg

    app = CoordinatorRuntimeApp.__new__(CoordinatorRuntimeApp)
    app.service = svc
    app.gateway = MagicMock()
    app.gateway.upsert_project_config.return_value = None
    app.gateway.create_design_document.return_value = MagicMock(
        document_id="design-doc-id",
        document_url="https://my.feishu.cn/docx/design-doc",
    )
    app._save_state = MagicMock()
    app._mark_event_seen = MagicMock(return_value=True)
    app._seen_event_ids = {}
    app._seen_event_ids_max = 100
    return app, req


def test_bind_url_resumes_design_dispatch_for_stuck_approved_req():
    app, req = _bootstrap_app_with_stuck_req()
    assert req.design_status is None  # precondition: stuck

    payload = {
        "header": {"event_id": "evt_bind"},
        "operator": {"open_id": "ou_alice", "user_id": "ou_alice"},
        "context": {"open_chat_id": "oc_group", "open_message_id": "om_bind"},
        "action": {
            "value": {
                "action": "bind_claude_design_project",
                "project": "X",
            },
            "form_value": {
                "claude_design_project_url": "https://claude.ai/design/p/abc",
            },
        },
    }
    status, response = app._handle_card_action_payload(payload)

    assert status == 200
    assert response["toast"]["type"] == "success"
    # Toast message should mention the resumed req count
    assert "1 个卡住的需求" in response["toast"]["content"]

    refreshed = app.service.get_requirement(req.req_id)
    assert refreshed.design_status == DesignStatus.DRAFTING, (
        f"design dispatch did not fire; design_status={refreshed.design_status}"
    )
    app.gateway.create_design_document.assert_called_once()


def test_bind_url_does_not_resume_non_approved_reqs():
    app, req = _bootstrap_app_with_stuck_req()
    # Move req back to FINAL_REVIEW — shouldn't be resumed
    req.status = WorkflowStatus.FINAL_REVIEW

    payload = {
        "header": {"event_id": "evt_bind_2"},
        "operator": {"open_id": "ou_alice", "user_id": "ou_alice"},
        "context": {"open_chat_id": "oc_group", "open_message_id": "om_bind"},
        "action": {
            "value": {"action": "bind_claude_design_project", "project": "X"},
            "form_value": {
                "claude_design_project_url": "https://claude.ai/design/p/abc",
            },
        },
    }
    status, response = app._handle_card_action_payload(payload)
    assert status == 200
    assert "卡住的需求" not in response["toast"]["content"]
    app.gateway.create_design_document.assert_not_called()


def test_bind_url_does_not_resume_non_ui_reqs():
    app, req = _bootstrap_app_with_stuck_req()
    req.needs_ui = False

    payload = {
        "header": {"event_id": "evt_bind_3"},
        "operator": {"open_id": "ou_alice", "user_id": "ou_alice"},
        "context": {"open_chat_id": "oc_group", "open_message_id": "om_bind"},
        "action": {
            "value": {"action": "bind_claude_design_project", "project": "X"},
            "form_value": {
                "claude_design_project_url": "https://claude.ai/design/p/abc",
            },
        },
    }
    status, response = app._handle_card_action_payload(payload)
    assert status == 200
    assert "卡住的需求" not in response["toast"]["content"]
    app.gateway.create_design_document.assert_not_called()


def test_bind_url_does_not_re_resume_reqs_already_in_design():
    app, req = _bootstrap_app_with_stuck_req()
    # Simulate a req that's already past DRAFTING
    req.design_status = DesignStatus.READY

    payload = {
        "header": {"event_id": "evt_bind_4"},
        "operator": {"open_id": "ou_alice", "user_id": "ou_alice"},
        "context": {"open_chat_id": "oc_group", "open_message_id": "om_bind"},
        "action": {
            "value": {"action": "bind_claude_design_project", "project": "X"},
            "form_value": {
                "claude_design_project_url": "https://claude.ai/design/p/abc",
            },
        },
    }
    status, response = app._handle_card_action_payload(payload)
    assert status == 200
    assert "卡住的需求" not in response["toast"]["content"]
    app.gateway.create_design_document.assert_not_called()
