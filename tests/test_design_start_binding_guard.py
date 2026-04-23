"""Test the Claude Design binding guard in CoordinatorService.design_start."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.models import Requirement, WorkflowStatus
from requirement_workflow_v12.plan_state_machine import DesignStatus
from requirement_workflow_v12.coordinator_service import CoordinatorService
from requirement_workflow_v12.project_config import ProjectConfig


def _svc() -> CoordinatorService:
    svc = CoordinatorService.__new__(CoordinatorService)
    svc.requirements = {}
    svc.project_configs = {}
    svc._hooks = MagicMock()
    return svc


def _req(**kw) -> Requirement:
    return Requirement(
        req_id="REQ-X-001", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
        **kw,
    )


def _cfg(**kw) -> ProjectConfig:
    return ProjectConfig(
        category="enterprise-app",
        template_version="enterprise-app.v1",
        architecture_doc_id="d", architecture_doc_url="u",
        **kw,
    )


def test_design_start_refuses_when_claude_design_url_empty():
    svc = _svc()
    r = _req()
    svc.requirements[r.req_id] = r
    svc.project_configs["X"] = _cfg(claude_design_project_url="")
    import pytest
    with pytest.raises(ValueError, match="Claude Design 未绑定"):
        svc.design_start(r.req_id, design_doc_id="d", design_doc_url="u")


def test_design_start_refuses_when_project_config_missing():
    svc = _svc()
    r = _req()
    svc.requirements[r.req_id] = r
    # No project_configs entry for "X"
    import pytest
    with pytest.raises(ValueError, match="Claude Design 未绑定"):
        svc.design_start(r.req_id, design_doc_id="d", design_doc_url="u")


def test_design_start_succeeds_when_url_is_configured():
    svc = _svc()
    r = _req()
    svc.requirements[r.req_id] = r
    svc.project_configs["X"] = _cfg(
        claude_design_project_url="https://claude.ai/design/p/xyz",
    )
    result = svc.design_start(r.req_id, design_doc_id="d", design_doc_url="u")
    assert result.design_status is DesignStatus.DRAFTING


def test_design_start_guard_message_references_project_name():
    svc = _svc()
    r = _req()
    svc.requirements[r.req_id] = r
    svc.project_configs["X"] = _cfg(claude_design_project_url="")
    import pytest
    with pytest.raises(ValueError) as exc_info:
        svc.design_start(r.req_id, design_doc_id="d", design_doc_url="u")
    assert "X" in str(exc_info.value)
