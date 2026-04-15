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
    r = Requirement(req_id=req_id, name="n", project=project, summary="s", creator="c")
    r.status = status
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
    other = Requirement(req_id="REQ-2", name="n", project="ProjA", summary="s", creator="c")
    other.status = WorkflowStatus.SPEC_DRAFTING
    svc.requirements["REQ-2"] = other
    gateway = MagicMock()
    gateway.fetch_document_revision.return_value = "rev-1"
    builder = SpecContextBuilder(service=svc, gateway=gateway)
    with pytest.raises(ConcurrentSpecInProgress):
        builder.build("REQ-1")


def test_build_allows_same_req_in_spec_drafting():
    svc = _svc_with_req(status=WorkflowStatus.SPEC_DRAFTING)
    gateway = MagicMock()
    gateway.fetch_document_revision.return_value = "rev-9"
    builder = SpecContextBuilder(service=svc, gateway=gateway)
    result = builder.build("REQ-1")
    assert result.context["status"] == "SPEC_DRAFTING"
