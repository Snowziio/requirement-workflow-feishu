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
