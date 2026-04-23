import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest
from unittest.mock import MagicMock

from requirement_workflow_v12.coordinator_service import CoordinatorService
from requirement_workflow_v12.models import Requirement, WorkflowStatus
from requirement_workflow_v12.plan_context import (
    PlanContextBuilder, PlanContextGateError,
)
from requirement_workflow_v12.plan_state_machine import PlanStatus
from requirement_workflow_v12.project_config import ProjectConfig


def _req(svc, req_id="REQ-P-1"):
    r = Requirement(
        req_id=req_id, name="n", project="P", summary="s", creator="c",
    )
    r.status = WorkflowStatus.APPROVED
    svc.requirements[req_id] = r
    svc.project_configs["P"] = ProjectConfig(
        category="web", template_version="v1",
        architecture_doc_id="doc-a", architecture_doc_url="https://x",
        tech_stack={"backend": "python"}, github_repo_url="owner/repo",
    )
    return r


def test_plan_context_returns_expected_fields_when_plan_none():
    svc = CoordinatorService()
    r = _req(svc)
    builder = PlanContextBuilder(service=svc)

    ctx = builder.build(r.req_id)

    assert ctx["req_id"] == "REQ-P-1"
    assert ctx["project"] == "P"
    assert ctx["needs_ui"] is False
    assert ctx["tech_stack"] == {"backend": "python"}
    assert ctx["project_repo"] == "owner/repo"
    assert ctx["architecture_doc_url"] == "https://x"


def test_plan_context_rejected_when_not_approved():
    svc = CoordinatorService()
    r = _req(svc)
    r.status = WorkflowStatus.DRAFTING
    builder = PlanContextBuilder(service=svc)
    with pytest.raises(PlanContextGateError):
        builder.build(r.req_id)


def test_plan_context_rejected_when_already_ready():
    svc = CoordinatorService()
    r = _req(svc)
    r.plan_status = PlanStatus.READY
    builder = PlanContextBuilder(service=svc)
    with pytest.raises(PlanContextGateError):
        builder.build(r.req_id)


def test_plan_context_allowed_when_drafting():
    svc = CoordinatorService()
    r = _req(svc)
    r.plan_status = PlanStatus.DRAFTING
    builder = PlanContextBuilder(service=svc)
    ctx = builder.build(r.req_id)
    assert ctx["req_id"] == "REQ-P-1"


def test_plan_context_allowed_when_needs_ui_true_and_no_design():
    """MVP (2026-04-21): plan_start no longer couples to needs_ui/design_status;
    plan_context must stay consistent with that — it should NOT gate on design."""
    svc = CoordinatorService()
    r = _req(svc)
    r.needs_ui = True
    # design_status stays None
    builder = PlanContextBuilder(service=svc)
    ctx = builder.build(r.req_id)
    assert ctx["req_id"] == "REQ-P-1"
    assert ctx["needs_ui"] is True


def test_plan_context_exposes_feishu_plan_doc_fields():
    """Time-phased SOT (2026-04-21): plan-author MUST see the Feishu plan docx
    URL/id so it can read/write the construction-phase SOT. Without these
    fields the agent falls back to 'where is my plan doc?' confusion."""
    svc = CoordinatorService()
    r = _req(svc)
    r.plan_status = PlanStatus.DRAFTING
    r.plan_doc_id = "docx-plan-abc"
    r.plan_doc_url = "https://my.feishu.cn/docx/docx-plan-abc"
    builder = PlanContextBuilder(service=svc)

    ctx = builder.build(r.req_id)

    assert ctx["plan_doc_id"] == "docx-plan-abc"
    assert ctx["plan_doc_url"] == "https://my.feishu.cn/docx/docx-plan-abc"


def test_plan_context_plan_doc_fields_default_empty_string():
    """Backward-compatible default: for REQs whose plan docx was never
    created (legacy or misconfigured folder_token), plan-author receives
    empty strings rather than missing keys, so jq/JSON access stays safe."""
    svc = CoordinatorService()
    r = _req(svc)
    # plan_doc_id / plan_doc_url never set
    builder = PlanContextBuilder(service=svc)

    ctx = builder.build(r.req_id)

    assert ctx["plan_doc_id"] == ""
    assert ctx["plan_doc_url"] == ""


def test_plan_context_includes_design_artifact():
    """Plan context must include design_artifact slice for plan-author consumption."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

    from unittest.mock import MagicMock
    from requirement_workflow_v12.models import Requirement, WorkflowStatus
    from requirement_workflow_v12.plan_state_machine import DesignStatus
    from requirement_workflow_v12.plan_context import PlanContextBuilder

    r = Requirement(
        req_id="REQ-X-001", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
        design_status=DesignStatus.READY,
        design_archive_path="design/archive/REQ-X-001_foo/",
    )
    svc = MagicMock()
    svc.requirements = {r.req_id: r}
    cfg = MagicMock()
    cfg.tech_stack = {}; cfg.category = "enterprise-app"
    cfg.template_version = "v1"
    cfg.architecture_doc_url = ""; cfg.github_repo_url = ""
    svc.project_configs = {r.project: cfg}

    ctx = PlanContextBuilder(svc).build("REQ-X-001")
    assert "design_artifact" in ctx
    assert ctx["design_artifact"]["archive_path"] == "design/archive/REQ-X-001_foo/"
    assert ctx["design_artifact"]["needs_ui"] is True
    assert ctx["design_artifact"]["design_status"] == "DESIGN_READY"


def test_plan_context_design_artifact_when_needs_ui_false():
    """Non-UI REQ still gets a design_artifact slice, but with empty/None fields."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

    from unittest.mock import MagicMock
    from requirement_workflow_v12.models import Requirement, WorkflowStatus
    from requirement_workflow_v12.plan_context import PlanContextBuilder

    r = Requirement(
        req_id="REQ-X-002", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=False,
    )
    svc = MagicMock()
    svc.requirements = {r.req_id: r}
    cfg = MagicMock()
    cfg.tech_stack = {}; cfg.category = "enterprise-app"
    cfg.template_version = "v1"
    cfg.architecture_doc_url = ""; cfg.github_repo_url = ""
    svc.project_configs = {r.project: cfg}

    ctx = PlanContextBuilder(svc).build("REQ-X-002")
    assert ctx["design_artifact"]["needs_ui"] is False
    assert ctx["design_artifact"]["archive_path"] == ""
    assert ctx["design_artifact"]["design_status"] is None
