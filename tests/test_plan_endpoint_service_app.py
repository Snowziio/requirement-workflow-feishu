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
