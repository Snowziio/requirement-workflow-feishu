"""Wire-level regression: GET /queries/openclaw/plan-context/{req_id} must
dispatch to handle_openclaw_plan_context_query, not fall through to the health
handler. plan-author SKILL.md does `curl -s GET ...`, so GET routing matters."""
from __future__ import annotations

import json
import socket
import sys
import threading
import time
import urllib.request

_NO_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.config import Settings
from requirement_workflow_v12.coordinator_service import CoordinatorService
from requirement_workflow_v12.models import Requirement, WorkflowStatus
from requirement_workflow_v12.project_config import ProjectConfig
from requirement_workflow_v12.service_app import CoordinatorRuntimeApp
from requirement_workflow_v12.store import JsonStateStore


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def running_app(tmp_path):
    port = _free_port()
    settings = Settings(
        feishu_app_id="x", feishu_app_secret="y",
        feishu_verification_token="t", feishu_encrypt_key="",
        state_store_path=str(tmp_path / "state.json"),
        spec_trace_dir=str(tmp_path / "trace"),
        github_token="", service_port=port,
    )
    svc = CoordinatorService()
    store = JsonStateStore(settings.state_store_path)
    gw = MagicMock()
    gw.list_project_configs.return_value = {}
    gw.upsert_project_config.return_value = None
    app = CoordinatorRuntimeApp(settings=settings, store=store, service=svc, gateway=gw)

    r = Requirement(
        req_id="REQ-WIRE-1", name="n", project="P", summary="s", creator="c",
    )
    r.status = WorkflowStatus.APPROVED
    r.document_url = "https://feishu.example/doc"
    svc.requirements["REQ-WIRE-1"] = r
    svc.project_configs["P"] = ProjectConfig(
        category="web", template_version="v1",
        architecture_doc_id="", architecture_doc_url="",
        tech_stack={"backend": "py"}, github_repo_url="o/r",
    )

    app.start_health_server()
    # Health server binds synchronously; tiny guard for any startup race.
    for _ in range(20):
        try:
            _NO_PROXY.open(f"http://127.0.0.1:{port}/", timeout=0.5).read()
            break
        except Exception:
            time.sleep(0.05)
    try:
        yield app, port
    finally:
        app._health_server.shutdown()
        app._health_server.server_close()


def test_get_plan_context_returns_full_body_not_health_payload(running_app):
    _, port = running_app

    resp = _NO_PROXY.open(
        f"http://127.0.0.1:{port}/queries/openclaw/plan-context/REQ-WIRE-1",
        timeout=1.0,
    )
    body = json.loads(resp.read().decode("utf-8"))

    assert body.get("req_id") == "REQ-WIRE-1"
    assert "plan_phase" in body
    assert body.get("project_repo") == "o/r"
    assert "status" not in body or body.get("status") != "ok"


def test_get_health_root_still_returns_health_payload(running_app):
    _, port = running_app
    resp = _NO_PROXY.open(f"http://127.0.0.1:{port}/", timeout=1.0)
    body = json.loads(resp.read().decode("utf-8"))
    assert body == {"status": "ok", "service": "coordinator-service"}
