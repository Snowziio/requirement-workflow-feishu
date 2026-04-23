import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.models import Requirement, WorkflowStatus
from requirement_workflow_v12.store import JsonStateStore


def test_requirement_has_spec_context_fields():
    req = Requirement(req_id="REQ-T-001", name="t", project="P", summary="s", creator="c")
    assert req.active_spec_context_token == ""
    assert req.spec_context_snapshot_revision == ""


def test_store_round_trips_spec_context_fields():
    req = Requirement(req_id="REQ-T-002", name="t", project="P", summary="s", creator="c")
    req.active_spec_context_token = "spec_ctx_REQ-T-002_1700000000_abcd"
    req.spec_context_snapshot_revision = "rev-20260415-001"

    with tempfile.TemporaryDirectory() as tmpdir:
        store = JsonStateStore(f"{tmpdir}/state.json")
        store.save_snapshot({"REQ-T-002": req}, {}, {})
        reqs, _, _, _ = store.load_snapshot()
        loaded = reqs["REQ-T-002"]
        assert loaded.active_spec_context_token == "spec_ctx_REQ-T-002_1700000000_abcd"
        assert loaded.spec_context_snapshot_revision == "rev-20260415-001"


def test_store_reads_legacy_snapshot_without_spec_context_fields():
    import json
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "state.json"
        path.write_text(json.dumps({
            "requirements": {
                "REQ-LEGACY-001": {
                    "req_id": "REQ-LEGACY-001",
                    "name": "legacy",
                    "project": "L",
                    "summary": "s",
                    "creator": "c",
                    "status": "APPROVED",
                    "spec_context_snapshot_sha": "deadbeef",
                    "github_repo_url": "https://github.com/org/legacy",
                }
            },
            "active_req_by_user": {},
            "project_groups": {},
            "project_configs": {},
        }, ensure_ascii=False))
        store = JsonStateStore(str(path))
        reqs, _, _, _ = store.load_snapshot()
        loaded = reqs["REQ-LEGACY-001"]
        assert loaded.active_spec_context_token == ""
        assert loaded.spec_context_snapshot_revision == ""
        assert not hasattr(loaded, "github_repo_url")
        assert not hasattr(loaded, "spec_context_snapshot_sha")


from unittest.mock import MagicMock

import pytest

from requirement_workflow_v12.coordinator_service import CoordinatorService
from requirement_workflow_v12.models import WorkflowStatus
from requirement_workflow_v12.project_config import ProjectConfig
from requirement_workflow_v12.spec_context import (
    ConcurrentSpecInProgress,
    SpecContextBuilder,
    SpecContextGateError,
    SpecContextMisconfigured,
)


def _svc_with_req(req_id="REQ-1", project="ProjA", status=WorkflowStatus.APPROVED) -> CoordinatorService:
    svc = CoordinatorService()
    from requirement_workflow_v12.models import Requirement
    from requirement_workflow_v12.plan_state_machine import PlanStatus
    r = Requirement(req_id=req_id, name="n", project=project, summary="s", creator="c")
    r.status = status
    r.plan_status = PlanStatus.READY
    r.document_url = "https://feishu.example/docx/req_doc"
    r.latest_review_summary = "ready"
    svc.requirements[req_id] = r
    svc.project_configs[project] = ProjectConfig(
        category="saas-ai-automation",
        template_version="saas-ai-automation.v1",
        architecture_doc_id="doc_arch",
        architecture_doc_url="https://feishu.example/docx/doc_arch",
        tech_stack={"backend": "FastAPI"},
    )
    return svc


def test_build_returns_payload_with_new_fields():
    svc = _svc_with_req()
    gateway = MagicMock()
    gateway.fetch_document_revision.return_value = "rev-7"
    builder = SpecContextBuilder(service=svc, gateway=gateway)

    result = builder.build("REQ-1")

    ctx = result.context
    assert ctx["architecture_doc_url"] == "https://feishu.example/docx/doc_arch"
    assert ctx["architecture_doc_revision"] == "rev-7"
    assert ctx["template_version"] == "saas-ai-automation.v1"
    assert ctx["category"] == "saas-ai-automation"
    assert ctx["requirement_document_url"] == "https://feishu.example/docx/req_doc"
    assert "architecture_yaml" not in ctx
    assert "architecture_commit_sha" not in ctx
    assert "github_repo_url" not in ctx
    assert result.context_token.startswith("spec_ctx_REQ-1_")
    assert svc.requirements["REQ-1"].active_spec_context_token == result.context_token


def test_build_rejects_wrong_status():
    svc = _svc_with_req(status=WorkflowStatus.DRAFTING)
    builder = SpecContextBuilder(service=svc, gateway=MagicMock())
    with pytest.raises(SpecContextGateError):
        builder.build("REQ-1")


def test_build_rejects_when_project_not_initialized():
    svc = _svc_with_req()
    svc.project_configs.clear()
    builder = SpecContextBuilder(service=svc, gateway=MagicMock())
    with pytest.raises(SpecContextMisconfigured):
        builder.build("REQ-1")


def test_build_rejects_concurrent_spec_in_same_project():
    svc = _svc_with_req()
    from requirement_workflow_v12.models import Requirement
    from requirement_workflow_v12.spec_state_machine import SpecStatus
    other = Requirement(req_id="REQ-2", name="n", project="ProjA", summary="s", creator="c")
    other.status = WorkflowStatus.APPROVED
    other.spec_status = SpecStatus.DRAFTING
    svc.requirements["REQ-2"] = other
    gateway = MagicMock()
    gateway.fetch_document_revision.return_value = "rev-1"
    builder = SpecContextBuilder(service=svc, gateway=gateway)
    with pytest.raises(ConcurrentSpecInProgress):
        builder.build("REQ-1")


def test_build_allows_same_req_in_spec_drafting():
    from requirement_workflow_v12.spec_state_machine import SpecStatus
    svc = _svc_with_req(status=WorkflowStatus.APPROVED)
    svc.requirements["REQ-1"].spec_status = SpecStatus.DRAFTING
    gateway = MagicMock()
    gateway.fetch_document_revision.return_value = "rev-9"
    builder = SpecContextBuilder(service=svc, gateway=gateway)
    result = builder.build("REQ-1")
    assert result.context["status"] == "APPROVED"
    assert result.context["spec_status"] == "SPEC_DRAFTING"


def test_spec_context_rejected_when_plan_not_ready(tmp_path):
    from requirement_workflow_v12.plan_state_machine import PlanStatus
    from requirement_workflow_v12.spec_context import (
        SpecContextBuilder, SpecContextGateError,
    )
    from requirement_workflow_v12.coordinator_service import CoordinatorService
    from requirement_workflow_v12.models import Requirement, WorkflowStatus
    from requirement_workflow_v12.project_config import ProjectConfig
    from unittest.mock import MagicMock

    svc = CoordinatorService()
    r = Requirement(req_id="R", name="n", project="P", summary="s", creator="c")
    r.status = WorkflowStatus.APPROVED
    r.plan_status = PlanStatus.DRAFTING  # not READY
    svc.requirements["R"] = r
    svc.project_configs["P"] = ProjectConfig(
        category="web", template_version="v1",
        architecture_doc_id="a", architecture_doc_url="u",
        tech_stack={}, github_repo_url="o/r",
    )
    gw = MagicMock()
    gw.fetch_document_revision.return_value = "rev-1"
    builder = SpecContextBuilder(svc, gw)
    import pytest
    with pytest.raises(SpecContextGateError, match="plan"):
        builder.build("R")


def test_spec_context_includes_plan_md_content_when_ready(tmp_path):
    from requirement_workflow_v12.plan_state_machine import PlanStatus
    from requirement_workflow_v12.spec_context import SpecContextBuilder
    from requirement_workflow_v12.coordinator_service import CoordinatorService
    from requirement_workflow_v12.models import Requirement, WorkflowStatus
    from requirement_workflow_v12.project_config import ProjectConfig
    from unittest.mock import MagicMock

    svc = CoordinatorService()
    r = Requirement(req_id="R", name="n", project="P", summary="s", creator="c")
    r.status = WorkflowStatus.APPROVED
    r.plan_status = PlanStatus.READY
    svc.requirements["R"] = r
    svc.project_configs["P"] = ProjectConfig(
        category="web", template_version="v1",
        architecture_doc_id="a", architecture_doc_url="u",
        tech_stack={}, github_repo_url="o/r",
    )
    gw = MagicMock()
    gw.fetch_document_revision.return_value = "rev-1"
    # Stub the plan.md fetcher to return canned content
    svc._fetch_plan_md = MagicMock(
        return_value="---\nreq_id: R\ndecisions:\n  - id: D1\n  - id: D2\n---\n",
    )
    builder = SpecContextBuilder(svc, gw)

    result = builder.build("R")

    assert "plan_md_content" in result.context
    assert "req_id: R" in result.context["plan_md_content"]
    assert result.context["plan_decision_ids"] == ["D1", "D2"]


def test_spec_context_includes_design_artifact():
    """Spec context must include design_artifact slice for spec-author consumption."""
    from requirement_workflow_v12.plan_state_machine import PlanStatus, DesignStatus
    from requirement_workflow_v12.spec_context import SpecContextBuilder
    from requirement_workflow_v12.coordinator_service import CoordinatorService
    from requirement_workflow_v12.models import Requirement, WorkflowStatus
    from requirement_workflow_v12.project_config import ProjectConfig
    from unittest.mock import MagicMock

    svc = CoordinatorService()
    r = Requirement(req_id="R", name="n", project="P", summary="s", creator="c")
    r.status = WorkflowStatus.APPROVED
    r.plan_status = PlanStatus.READY
    r.needs_ui = True
    r.design_status = DesignStatus.READY
    r.design_archive_path = "design/archive/R_foo/"
    svc.requirements["R"] = r
    svc.project_configs["P"] = ProjectConfig(
        category="web", template_version="v1",
        architecture_doc_id="a", architecture_doc_url="u",
        tech_stack={}, github_repo_url="o/r",
    )
    gw = MagicMock()
    gw.fetch_document_revision.return_value = "rev-1"
    builder = SpecContextBuilder(svc, gw)

    result = builder.build("R")

    assert "design_artifact" in result.context
    assert result.context["design_artifact"]["archive_path"] == "design/archive/R_foo/"
    assert result.context["design_artifact"]["needs_ui"] is True
    assert result.context["design_artifact"]["design_status"] == "DESIGN_READY"


def test_spec_context_design_artifact_when_no_design():
    """REQ without design still gets design_artifact slice with None/empty defaults."""
    from requirement_workflow_v12.plan_state_machine import PlanStatus
    from requirement_workflow_v12.spec_context import SpecContextBuilder
    from requirement_workflow_v12.coordinator_service import CoordinatorService
    from requirement_workflow_v12.models import Requirement, WorkflowStatus
    from requirement_workflow_v12.project_config import ProjectConfig
    from unittest.mock import MagicMock

    svc = CoordinatorService()
    r = Requirement(req_id="R", name="n", project="P", summary="s", creator="c")
    r.status = WorkflowStatus.APPROVED
    r.plan_status = PlanStatus.READY
    svc.requirements["R"] = r
    svc.project_configs["P"] = ProjectConfig(
        category="web", template_version="v1",
        architecture_doc_id="a", architecture_doc_url="u",
        tech_stack={}, github_repo_url="o/r",
    )
    gw = MagicMock()
    gw.fetch_document_revision.return_value = "rev-1"
    builder = SpecContextBuilder(svc, gw)

    result = builder.build("R")

    assert result.context["design_artifact"]["archive_path"] == ""
    assert result.context["design_artifact"]["needs_ui"] is False
    assert result.context["design_artifact"]["design_status"] is None
