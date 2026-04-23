import sys
from pathlib import Path
from unittest.mock import MagicMock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.service_app import CoordinatorRuntimeApp
from requirement_workflow_v12.models import Requirement, WorkflowStatus
from requirement_workflow_v12.plan_state_machine import DesignStatus
from requirement_workflow_v12.design_context import DesignContextBuilder


def _app_with_req(req: Requirement, cfg=None) -> CoordinatorRuntimeApp:
    """Build a minimally-initialized CoordinatorRuntimeApp for testing."""
    app = CoordinatorRuntimeApp.__new__(CoordinatorRuntimeApp)
    app.service = MagicMock()
    app.service.requirements = {req.req_id: req}
    app.service.project_configs = {req.project: cfg} if cfg else {}
    app.gateway = MagicMock()
    app._design_context_builder = DesignContextBuilder(app.service)
    return app


def _cfg():
    cfg = MagicMock()
    cfg.tech_stack = {"frontend": "Vite+React"}
    cfg.category = "enterprise-app"
    cfg.template_version = "v1"
    cfg.claude_design_project_url = "https://claude.ai/design/p/xyz"
    cfg.frontend_subpath = "src/x_webapp"
    cfg.architecture_doc_url = ""
    cfg.github_repo_url = ""
    return cfg


def test_design_context_endpoint_returns_200_with_payload():
    r = Requirement(
        req_id="REQ-X-001", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
        design_status=DesignStatus.DRAFTING,
        design_doc_id="d-1", design_doc_url="https://feishu/d/1",
    )
    app = _app_with_req(r, _cfg())
    status, body = app.handle_openclaw_design_context_query("REQ-X-001")
    assert status == 200
    assert body["req_id"] == "REQ-X-001"
    assert body["claude_design_project_url"] == "https://claude.ai/design/p/xyz"


def test_design_context_endpoint_returns_404_for_unknown_req():
    r = Requirement(
        req_id="REQ-X-999", name="n", project="X", summary="s", creator="c",
    )
    app = _app_with_req(r, _cfg())
    status, body = app.handle_openclaw_design_context_query("REQ-NOT-EXIST")
    assert status == 404
    assert body["error"] == "not_found"


def test_design_context_endpoint_returns_409_on_wrong_status():
    r = Requirement(
        req_id="REQ-X-002", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.CREATED,
    )
    app = _app_with_req(r, _cfg())
    status, body = app.handle_openclaw_design_context_query("REQ-X-002")
    assert status == 409
    assert body["error"] == "gate_failed"


def test_design_context_endpoint_returns_409_when_misconfigured():
    r = Requirement(
        req_id="REQ-X-003", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
        design_status=DesignStatus.DRAFTING,
    )
    app = _app_with_req(r, cfg=None)
    status, body = app.handle_openclaw_design_context_query("REQ-X-003")
    assert status == 409
    assert body["error"] == "misconfigured"
