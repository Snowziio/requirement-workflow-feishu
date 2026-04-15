import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.models import Requirement, WorkflowStatus
from requirement_workflow_v12.store import JsonStateStore


def test_requirement_has_spec_context_fields():
    req = Requirement(req_id="REQ-T-001", name="t", project="P", summary="s", creator="c")
    assert req.active_spec_context_token == ""
    assert req.spec_context_snapshot_sha == ""


def test_store_round_trips_spec_context_fields():
    req = Requirement(req_id="REQ-T-002", name="t", project="P", summary="s", creator="c")
    req.active_spec_context_token = "spec_ctx_REQ-T-002_1700000000_abcd"
    req.spec_context_snapshot_sha = "deadbeef1234"

    with tempfile.TemporaryDirectory() as tmpdir:
        store = JsonStateStore(f"{tmpdir}/state.json")
        store.save_snapshot({"REQ-T-002": req}, {}, {})
        reqs, _, _, _ = store.load_snapshot()
        loaded = reqs["REQ-T-002"]
        assert loaded.active_spec_context_token == "spec_ctx_REQ-T-002_1700000000_abcd"
        assert loaded.spec_context_snapshot_sha == "deadbeef1234"


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
        assert loaded.spec_context_snapshot_sha == ""


from unittest.mock import MagicMock

from requirement_workflow_v12.github_client import (
    FetchedFile,
    GitHubAuthError,
    GitHubNotFoundError,
)
from requirement_workflow_v12.project_config import ProjectConfig
from requirement_workflow_v12.spec_context import (
    SpecContextBuilder,
    SpecContextGateError,
    SpecContextMisconfigured,
)


def _make_requirement(status: WorkflowStatus = WorkflowStatus.APPROVED) -> Requirement:
    req = Requirement(req_id="REQ-SC-001", name="n", project="P", summary="s", creator="c")
    req.status = status
    req.document_url = "https://feishu.cn/docx/tok123"
    req.needs_ui = True
    req.hifi_prototype_url = "https://figma.com/prototype"
    req.latest_review_summary = "looks good"
    return req


def _make_service(req: Requirement) -> MagicMock:
    svc = MagicMock()
    svc.get_requirement.return_value = req
    svc.project_configs = {
        "P": ProjectConfig(
            github_repo_url="https://github.com/org/repo",
            is_new_project=False,
            tech_stack={},
        )
    }
    return svc


def test_spec_context_build_success():
    req = _make_requirement()
    service = _make_service(req)
    gh = MagicMock()
    gh.fetch_file.return_value = FetchedFile(content="services: []\n", commit_sha="sha-abc")
    builder = SpecContextBuilder(service=service, github_client=gh)

    result = builder.build("REQ-SC-001")

    assert result.context["req_id"] == "REQ-SC-001"
    assert result.context["architecture_yaml"] == "services: []\n"
    assert result.context["architecture_commit_sha"] == "sha-abc"
    assert result.context["requirement_document_url"] == "https://feishu.cn/docx/tok123"
    assert result.context["needs_ui"] is True
    assert result.context["design_system_snapshot"] is None
    assert result.context["github_repo_url"] == "https://github.com/org/repo"
    assert result.context_token.startswith("spec_ctx_REQ-SC-001_")
    assert req.active_spec_context_token == result.context_token


def test_spec_context_rejects_non_approved():
    import pytest
    req = _make_requirement(status=WorkflowStatus.DRAFTING)
    service = _make_service(req)
    builder = SpecContextBuilder(service=service, github_client=MagicMock())

    with pytest.raises(SpecContextGateError):
        builder.build("REQ-SC-001")


def test_spec_context_rejects_spec_locked():
    import pytest
    req = _make_requirement(status=WorkflowStatus.SPEC_LOCKED)
    service = _make_service(req)
    builder = SpecContextBuilder(service=service, github_client=MagicMock())

    with pytest.raises(SpecContextGateError):
        builder.build("REQ-SC-001")


def test_spec_context_allows_spec_drafting():
    req = _make_requirement(status=WorkflowStatus.SPEC_DRAFTING)
    service = _make_service(req)
    gh = MagicMock()
    gh.fetch_file.return_value = FetchedFile(content="x", commit_sha="s")
    builder = SpecContextBuilder(service=service, github_client=gh)
    result = builder.build("REQ-SC-001")
    assert result.context_token


def test_spec_context_missing_project_config():
    import pytest
    req = _make_requirement()
    service = _make_service(req)
    service.project_configs = {}
    builder = SpecContextBuilder(service=service, github_client=MagicMock())
    with pytest.raises(SpecContextMisconfigured):
        builder.build("REQ-SC-001")


def test_spec_context_missing_github_repo_url():
    import pytest
    req = _make_requirement()
    service = _make_service(req)
    service.project_configs["P"] = ProjectConfig(github_repo_url="", is_new_project=False, tech_stack={})
    builder = SpecContextBuilder(service=service, github_client=MagicMock())
    with pytest.raises(SpecContextMisconfigured):
        builder.build("REQ-SC-001")


def test_spec_context_unknown_req():
    import pytest
    service = MagicMock()
    service.get_requirement.return_value = None
    builder = SpecContextBuilder(service=service, github_client=MagicMock())
    with pytest.raises(ValueError):
        builder.build("REQ-UNKNOWN")


def test_spec_context_token_overwrites_previous():
    req = _make_requirement()
    req.active_spec_context_token = "old_token"
    service = _make_service(req)
    gh = MagicMock()
    gh.fetch_file.return_value = FetchedFile(content="x", commit_sha="s")
    builder = SpecContextBuilder(service=service, github_client=gh)
    result = builder.build("REQ-SC-001")
    assert req.active_spec_context_token == result.context_token
    assert req.active_spec_context_token != "old_token"
