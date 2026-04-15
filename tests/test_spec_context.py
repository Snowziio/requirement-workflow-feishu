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


import json as _jsonmod
from unittest.mock import patch


class _FakeGateway:
    """Minimal gateway stub that avoids lark_oapi dependency."""
    def update_requirement_record(self, req) -> None:
        pass

    def bitable_url(self) -> str:
        return ""

    def send_text(self, receive_id, text, receive_id_type="chat_id"):
        pass

    def send_card(self, receive_id, card, receive_id_type="chat_id"):
        pass


def _make_app_with_req(tmpdir_factory):
    """Create a CoordinatorRuntimeApp with a pre-seeded APPROVED requirement."""
    import tempfile
    tmpdir = tempfile.mkdtemp()
    from requirement_workflow_v12.service_app import CoordinatorRuntimeApp
    from requirement_workflow_v12.config import Settings

    settings = Settings(
        feishu_app_id="x",
        feishu_app_secret="y",
        state_store_path=f"{tmpdir}/state.json",
        github_token="fake-token-for-tests",
    )
    app = CoordinatorRuntimeApp(settings=settings, gateway=_FakeGateway())
    req = _make_requirement()
    app.service.requirements[req.req_id] = req
    app.service.project_configs["P"] = ProjectConfig(
        github_repo_url="https://github.com/org/repo",
        is_new_project=False,
        tech_stack={},
    )
    return app, req


def test_spec_context_endpoint_unknown_req_returns_404(tmp_path):
    app, _ = _make_app_with_req(None)
    body = _jsonmod.dumps({"req_id": "REQ-MISSING"}).encode()
    status, payload = app.handle_openclaw_spec_context_query(body)
    assert status == 404
    assert payload["error"] == "not_found"


def test_spec_context_endpoint_invalid_state_returns_409(tmp_path):
    app, req = _make_app_with_req(None)
    req.status = WorkflowStatus.DRAFTING
    body = _jsonmod.dumps({"req_id": req.req_id}).encode()
    status, payload = app.handle_openclaw_spec_context_query(body)
    assert status == 409
    assert payload["error"] == "invalid_state"


def test_spec_context_endpoint_success(tmp_path):
    app, req = _make_app_with_req(None)
    with patch.object(
        app.github_client, "fetch_file",
        return_value=FetchedFile(content="services: []\n", commit_sha="sha-xyz"),
    ):
        body = _jsonmod.dumps({"req_id": req.req_id}).encode()
        status, payload = app.handle_openclaw_spec_context_query(body)
    assert status == 200
    assert payload["ok"] is True
    assert payload["context"]["architecture_yaml"] == "services: []\n"
    assert payload["context"]["architecture_commit_sha"] == "sha-xyz"
    assert payload["context_token"].startswith("spec_ctx_")
    assert req.active_spec_context_token == payload["context_token"]


def test_spec_context_endpoint_github_auth_failure_returns_502(tmp_path):
    app, req = _make_app_with_req(None)
    with patch.object(app.github_client, "fetch_file", side_effect=GitHubAuthError("bad token")):
        body = _jsonmod.dumps({"req_id": req.req_id}).encode()
        status, payload = app.handle_openclaw_spec_context_query(body)
    assert status == 502
    assert payload["error"] == "github_auth_failed"


def test_spec_context_endpoint_github_missing_file_returns_502(tmp_path):
    app, req = _make_app_with_req(None)
    with patch.object(app.github_client, "fetch_file", side_effect=GitHubNotFoundError("nf")):
        body = _jsonmod.dumps({"req_id": req.req_id}).encode()
        status, payload = app.handle_openclaw_spec_context_query(body)
    assert status == 502
    assert payload["error"] == "architecture_yaml_missing"


def test_spec_context_endpoint_misconfigured_returns_500(tmp_path):
    app, req = _make_app_with_req(None)
    app.service.project_configs["P"] = ProjectConfig(
        github_repo_url="",
        is_new_project=False,
        tech_stack={},
    )
    body = _jsonmod.dumps({"req_id": req.req_id}).encode()
    status, payload = app.handle_openclaw_spec_context_query(body)
    assert status == 500
    assert payload["error"] == "project_misconfigured"


def test_spec_context_endpoint_missing_github_token_returns_500(tmp_path):
    app, req = _make_app_with_req(None)
    app.settings.github_token = ""
    body = _jsonmod.dumps({"req_id": req.req_id}).encode()
    status, payload = app.handle_openclaw_spec_context_query(body)
    assert status == 500
    assert payload["error"] == "github_auth_missing"


def test_spec_start_rejects_missing_context_token():
    app, req = _make_app_with_req(None)
    req.active_spec_context_token = "spec_ctx_REQ-SC-001_1_aaaa"
    body = _jsonmod.dumps({
        "req_id": req.req_id, "event": "spec_start", "summary": "go",
    }).encode()
    status, payload = app.handle_openclaw_spec_turn_callback(body)
    assert status == 400
    assert payload["error"] == "missing_context_token"


def test_spec_start_rejects_stale_context_token():
    app, req = _make_app_with_req(None)
    req.active_spec_context_token = "spec_ctx_CURRENT"
    body = _jsonmod.dumps({
        "req_id": req.req_id, "event": "spec_start", "summary": "go",
        "context_token": "spec_ctx_OLD",
    }).encode()
    status, payload = app.handle_openclaw_spec_turn_callback(body)
    assert status == 409
    assert payload["error"] == "stale_context_token"


def test_spec_submit_rejects_missing_commit_sha():
    app, req = _make_app_with_req(None)
    req.status = WorkflowStatus.SPEC_DRAFTING
    req.active_spec_context_token = "tok"
    body = _jsonmod.dumps({
        "req_id": req.req_id, "event": "spec_submit", "summary": "done",
        "context_token": "tok",
    }).encode()
    status, payload = app.handle_openclaw_spec_turn_callback(body)
    assert status == 400
    assert payload["error"] == "missing_commit_sha"


def test_spec_submit_writes_sha_and_clears_token():
    app, req = _make_app_with_req(None)
    req.status = WorkflowStatus.SPEC_DRAFTING
    req.active_spec_context_token = "tok"
    body = _jsonmod.dumps({
        "req_id": req.req_id, "event": "spec_submit", "summary": "done",
        "context_token": "tok",
        "architecture_commit_sha": "sha-locked",
    }).encode()
    status, payload = app.handle_openclaw_spec_turn_callback(body)
    assert status == 200
    assert req.spec_context_snapshot_sha == "sha-locked"
    assert req.active_spec_context_token == ""
    assert req.status == WorkflowStatus.SPEC_DRAFTING
