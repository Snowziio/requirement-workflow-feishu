import sys
from pathlib import Path
from unittest.mock import MagicMock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.models import Requirement, WorkflowStatus
from requirement_workflow_v12.plan_state_machine import DesignStatus
from requirement_workflow_v12.design_context import (
    DesignContextBuilder, DesignContextGateError, DesignContextMisconfigured,
)


def _approved_req(**kw) -> Requirement:
    defaults = dict(
        req_id="REQ-X-001", name="测试需求", project="X",
        summary="用户上传头像审核流程", creator="user1",
        status=WorkflowStatus.APPROVED,
        needs_ui=True,
        design_status=DesignStatus.DRAFTING,
        document_url="https://feishu/d/req001",
        design_doc_id="design-doc-001",
        design_doc_url="https://feishu/d/design001",
    )
    defaults.update(kw)
    return Requirement(**defaults)


def _service_with(requirement, project_config=None):
    svc = MagicMock()
    svc.requirements = {requirement.req_id: requirement}
    svc.project_configs = {requirement.project: project_config} if project_config else {}
    return svc


def _cfg(**kw):
    cfg = MagicMock()
    cfg.tech_stack = kw.get("tech_stack", {"frontend": "Vite+React"})
    cfg.category = kw.get("category", "enterprise-app")
    cfg.template_version = kw.get("template_version", "v1")
    cfg.claude_design_project_url = kw.get("claude_design_project_url", "")
    cfg.frontend_subpath = kw.get("frontend_subpath", "src/x_webapp")
    cfg.architecture_doc_url = kw.get("architecture_doc_url", "")
    cfg.github_repo_url = kw.get("github_repo_url", "")
    return cfg


def test_build_returns_full_context_for_drafting_req():
    req = _approved_req()
    svc = _service_with(req, _cfg(claude_design_project_url="https://claude.ai/design/p/xyz"))
    ctx = DesignContextBuilder(svc).build("REQ-X-001")
    assert ctx["req_id"] == "REQ-X-001"
    assert ctx["needs_ui"] is True
    assert ctx["claude_design_project_url"] == "https://claude.ai/design/p/xyz"
    assert ctx["frontend_subpath"] == "src/x_webapp"
    assert ctx["design_doc_id"] == "design-doc-001"
    assert ctx["design_doc_url"] == "https://feishu/d/design001"
    assert "current_pages" in ctx
    assert ctx["current_pages"] == []


def test_build_rejects_wrong_status():
    req = _approved_req(status=WorkflowStatus.CREATED)
    svc = _service_with(req, _cfg())
    import pytest
    with pytest.raises(DesignContextGateError):
        DesignContextBuilder(svc).build("REQ-X-001")


def test_build_rejects_needs_ui_false():
    req = _approved_req(needs_ui=False)
    svc = _service_with(req, _cfg())
    import pytest
    with pytest.raises(DesignContextGateError):
        DesignContextBuilder(svc).build("REQ-X-001")


def test_build_rejects_wrong_design_status():
    req = _approved_req(design_status=DesignStatus.READY)
    svc = _service_with(req, _cfg())
    import pytest
    with pytest.raises(DesignContextGateError):
        DesignContextBuilder(svc).build("REQ-X-001")


def test_build_raises_misconfigured_when_no_project_config():
    req = _approved_req()
    svc = _service_with(req, project_config=None)
    import pytest
    with pytest.raises(DesignContextMisconfigured):
        DesignContextBuilder(svc).build("REQ-X-001")


def test_build_empty_claude_design_url_still_succeeds():
    """Bootstrap may not have run; url may be empty. Context still emits."""
    req = _approved_req()
    svc = _service_with(req, _cfg(claude_design_project_url=""))
    ctx = DesignContextBuilder(svc).build("REQ-X-001")
    assert ctx["claude_design_project_url"] == ""
