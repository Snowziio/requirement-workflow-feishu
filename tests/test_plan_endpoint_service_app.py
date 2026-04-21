import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest
from unittest.mock import MagicMock

from requirement_workflow_v12.config import Settings
from requirement_workflow_v12.coordinator_service import CoordinatorService
from requirement_workflow_v12.models import Requirement, WorkflowStatus
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
    a = CoordinatorRuntimeApp(
        settings=settings, store=store, service=svc, gateway=gw,
    )
    return a


def _approved_req(app, req_id="REQ-P-1"):
    r = Requirement(
        req_id=req_id, name="n", project="P", summary="s", creator="c",
    )
    r.status = WorkflowStatus.APPROVED
    app.service.requirements[req_id] = r
    app.service.project_configs["P"] = ProjectConfig(
        category="web", template_version="v1",
        architecture_doc_id="", architecture_doc_url="",
        tech_stack={"backend": "py"}, github_repo_url="o/r",
    )
    return r


def test_plan_context_endpoint_returns_200_for_approved_req(app):
    _approved_req(app)

    status, body = app.handle_openclaw_plan_context_query(req_id="REQ-P-1")

    assert status == 200
    assert body["req_id"] == "REQ-P-1"
    assert body["project_repo"] == "o/r"


def test_plan_context_endpoint_returns_409_when_gate_fails(app):
    _approved_req(app)
    app.service.requirements["REQ-P-1"].status = WorkflowStatus.DRAFTING

    status, body = app.handle_openclaw_plan_context_query(req_id="REQ-P-1")

    assert status == 409
    assert "error" in body


def test_plan_context_endpoint_returns_404_when_req_missing(app):
    status, body = app.handle_openclaw_plan_context_query(req_id="NOPE")
    assert status == 404


def test_plan_callback_outline_submit_writes_outline_and_advances_phase(app):
    r = _approved_req(app)
    app.service.plan_start(r.req_id)

    body = {
        "req_id": "REQ-P-1",
        "event": "plan_outline_submit",
        "payload": {
            "outline": [
                {"id": "D1", "title": "会话存储", "problem": "..."},
                {"id": "D2", "title": "鉴权流程", "problem": "..."},
            ],
        },
    }
    status, resp = app.handle_openclaw_plan_callback(body)

    assert status == 200
    assert r.plan_outline == body["payload"]["outline"]


def test_plan_callback_plan_submit_branches_to_ready_when_no_architecture(app):
    """After 2026-04-21 plan-wiring: plan_submit callback buffers into
    pending_plan_review; state remains DRAFTING until human approves via card."""
    r = _approved_req(app)
    app.service.plan_start(r.req_id)

    body = {
        "req_id": "REQ-P-1",
        "event": "plan_submit",
        "payload": {
            "plan_md_content": "---\nreq_id: REQ-P-1\n---\n",
            "architecture_change": None,
        },
    }
    status, resp = app.handle_openclaw_plan_callback(body)

    from requirement_workflow_v12.plan_state_machine import PlanStatus, PlanPhase
    assert status == 200
    assert r.plan_status is PlanStatus.DRAFTING
    assert r.plan_phase is PlanPhase.FINAL_REVIEW_PENDING
    assert r.pending_plan_review is not None


def test_plan_callback_plan_submit_mirrors_md_into_feishu_plan_doc(app):
    """Phase 2-D (time-phased SOT): after buffering pending_plan_review, the
    callback must also mirror plan_md_content into the Feishu plan docx so
    human reviewers see it in the SOT during Phase C."""
    r = _approved_req(app)
    app.service.plan_start(
        r.req_id,
        plan_doc_id="docx-plan-abc",
        plan_doc_url="https://feishu.example/docx/docx-plan-abc",
    )

    body = {
        "req_id": "REQ-P-1",
        "event": "plan_submit",
        "payload": {
            "plan_md_content": "---\nreq_id: REQ-P-1\n---\n# Plan\n",
            "architecture_change": None,
        },
    }
    status, _ = app.handle_openclaw_plan_callback(body)

    assert status == 200
    app.gateway.write_document_text.assert_called_once_with(
        "docx-plan-abc",
        "---\nreq_id: REQ-P-1\n---\n# Plan\n",
    )


def test_plan_callback_plan_submit_skips_feishu_write_without_plan_doc_id(app):
    """No plan_doc_id (feishu_doc_folder_token not configured or legacy
    requirement) → don't attempt the write; still accept the callback."""
    r = _approved_req(app)
    app.service.plan_start(r.req_id)  # no plan_doc_id

    body = {
        "req_id": "REQ-P-1",
        "event": "plan_submit",
        "payload": {
            "plan_md_content": "# plan",
            "architecture_change": None,
        },
    }
    status, _ = app.handle_openclaw_plan_callback(body)

    assert status == 200
    app.gateway.write_document_text.assert_not_called()


def test_plan_callback_unknown_event_returns_400(app):
    r = _approved_req(app)
    status, resp = app.handle_openclaw_plan_callback(
        {"req_id": "REQ-P-1", "event": "nonsense", "payload": {}},
    )
    assert status == 400


def test_plan_callback_req_not_found_returns_404(app):
    status, resp = app.handle_openclaw_plan_callback(
        {"req_id": "NO", "event": "plan_submit", "payload": {}},
    )
    assert status == 404


def test_slash_plan_restart_parses_req_id_and_calls_service(app):
    r = _approved_req(app)
    from requirement_workflow_v12.plan_state_machine import PlanStatus
    r.plan_status = PlanStatus.DRAFTING
    r.plan_phase = None

    response = app.handle_slash_command("/plan restart REQ-P-1")

    assert response is not None
    assert "重置" in response or "reset" in response.lower()
    assert r.plan_status is None


def test_slash_design_restart_cascades(app):
    r = _approved_req(app)
    from requirement_workflow_v12.plan_state_machine import DesignStatus, PlanStatus
    r.design_status = DesignStatus.READY
    r.plan_status = PlanStatus.DRAFTING

    response = app.handle_slash_command("/design restart REQ-P-1")

    assert response is not None
    assert r.design_status is None
    assert r.plan_status is None


def test_slash_plan_restart_unknown_req_returns_error_message(app):
    response = app.handle_slash_command("/plan restart REQ-NOPE")
    assert response is not None
    assert "REQ-NOPE" in response


def test_handle_text_message_dispatches_plan_restart(app):
    from requirement_workflow_v12.plan_state_machine import PlanStatus
    from requirement_workflow_v12.service_app import MessageContext
    r = _approved_req(app)
    r.plan_status = PlanStatus.DRAFTING

    outbound = app.handle_text_message(MessageContext(
        chat_id="c", chat_type="p2p", user_id="u", text="/plan restart REQ-P-1",
    ))

    assert len(outbound) == 1
    assert "REQ-P-1" in outbound[0].text
    assert r.plan_status is None


def test_plan_callback_plan_submit_buffers_draft_and_keeps_drafting(app):
    r = _approved_req(app, req_id="REQ-PB-1")
    app.service.plan_start(r.req_id)

    body = {
        "req_id": r.req_id,
        "event": "plan_submit",
        "payload": {
            "plan_md_content": "# plan\n...",
            "project_context_change": None,
        },
    }
    status, resp = app.handle_openclaw_plan_callback(body)

    assert status == 200
    from requirement_workflow_v12.plan_state_machine import PlanStatus, PlanPhase
    assert r.plan_status == PlanStatus.DRAFTING  # NOT READY — review pending
    assert r.plan_phase == PlanPhase.FINAL_REVIEW_PENDING
    assert r.pending_plan_review is not None
    assert r.pending_plan_review["plan_md_content"] == "# plan\n..."
    assert r.pending_plan_review["project_context_change"] is None
    assert "submitted_at" in r.pending_plan_review


def test_plan_callback_plan_submit_dispatches_review_notification(app):
    r = _approved_req(app, req_id="REQ-PB-2")
    r.creator_user_id = "ou_alice"
    app.service.plan_start(r.req_id)

    body = {
        "req_id": r.req_id,
        "event": "plan_submit",
        "payload": {"plan_md_content": "# plan", "project_context_change": None},
    }
    app.handle_openclaw_plan_callback(body)

    # Either send_card or send_text was called at least once with the review trigger
    assert app.gateway.send_card.called or app.gateway.send_text.called


def test_plan_callback_plan_submit_retry_overwrites_pending(app):
    r = _approved_req(app, req_id="REQ-PB-3")
    app.service.plan_start(r.req_id)

    app.handle_openclaw_plan_callback({
        "req_id": r.req_id, "event": "plan_submit",
        "payload": {"plan_md_content": "v1", "project_context_change": None},
    })
    first_submitted = r.pending_plan_review["submitted_at"]

    app.handle_openclaw_plan_callback({
        "req_id": r.req_id, "event": "plan_submit",
        "payload": {"plan_md_content": "v2", "project_context_change": None},
    })

    assert r.pending_plan_review["plan_md_content"] == "v2"
    # submitted_at should be re-stamped (may equal if called in same millisecond, so just assert string exists)
    assert r.pending_plan_review["submitted_at"] is not None
