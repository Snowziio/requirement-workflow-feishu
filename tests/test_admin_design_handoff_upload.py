"""Tests for the /admin/design-handoff-upload endpoint — localhost-only path
that skips the Feishu attachment download and ingests a base64-encoded zip
directly. Used for ops interventions when the Feishu upload path is
unavailable (e.g. file-message DMs not yet wired).
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.models import Requirement, WorkflowStatus
from requirement_workflow_v12.plan_state_machine import DesignStatus
from requirement_workflow_v12.project_config import ProjectConfig

FIXTURE_ZIP = Path(__file__).parent / "fixtures" / "design" / "handoff_sample.zip"


def _app_with_drafting_req(tmp_path):
    from requirement_workflow_v12.coordinator_service import CoordinatorService
    from requirement_workflow_v12.service_app import CoordinatorRuntimeApp

    r = Requirement(
        req_id="REQ-Y-001", name="n", project="Y", summary="s", creator="c",
        creator_user_id="ou_alice",
        status=WorkflowStatus.APPROVED, needs_ui=True,
        design_status=DesignStatus.DRAFTING,
        design_doc_id="d", design_doc_url="u",
    )
    cfg = ProjectConfig(
        category="public-web-site",
        template_version="public-web-site.v1",
        architecture_doc_id="d", architecture_doc_url="u",
        github_repo_url="https://github.com/org/Y",
        feishu_chat_id="oc_group",
    )
    svc = CoordinatorService()
    svc.requirements[r.req_id] = r
    svc.project_configs[r.project] = cfg

    app = CoordinatorRuntimeApp.__new__(CoordinatorRuntimeApp)
    app.service = svc
    app.gateway = MagicMock()
    app.archive_root = tmp_path / "design" / "archive"
    app.archive_root.mkdir(parents=True)
    app._save_state = MagicMock()
    app._dispatch_transition_notifications = MagicMock()
    # design_submit is a service method; stub to return the req
    svc.design_submit = MagicMock(return_value=r)
    return app, r


def _payload(req_id: str, zip_bytes: bytes) -> bytes:
    return json.dumps({
        "req_id": req_id,
        "zip_b64": base64.b64encode(zip_bytes).decode("ascii"),
    }).encode("utf-8")


def test_admin_upload_rejects_non_localhost_client(tmp_path):
    app, r = _app_with_drafting_req(tmp_path)
    status, resp = app.handle_admin_design_handoff_upload(
        _payload(r.req_id, FIXTURE_ZIP.read_bytes()),
        client_ip="172.17.0.1",  # docker bridge
    )
    assert status == 403
    assert "localhost" in resp["error"].lower()
    # Intake must not have run
    app._dispatch_transition_notifications.assert_not_called()


def test_admin_upload_rejects_external_ip(tmp_path):
    app, r = _app_with_drafting_req(tmp_path)
    status, resp = app.handle_admin_design_handoff_upload(
        _payload(r.req_id, FIXTURE_ZIP.read_bytes()),
        client_ip="203.0.113.42",
    )
    assert status == 403


def test_admin_upload_accepts_localhost_v4(tmp_path):
    app, r = _app_with_drafting_req(tmp_path)
    status, resp = app.handle_admin_design_handoff_upload(
        _payload(r.req_id, FIXTURE_ZIP.read_bytes()),
        client_ip="127.0.0.1",
    )
    assert status == 200
    assert resp["ok"] is True
    assert resp["req_id"] == r.req_id
    assert resp["archive_path"].startswith("design/archive/REQ-Y-001_")
    app.service.design_submit.assert_called_once()
    app._dispatch_transition_notifications.assert_called_once()


def test_admin_upload_merges_pages_from_pending_design_brief(tmp_path):
    app, r = _app_with_drafting_req(tmp_path)
    r.pending_design_brief = {
        "brief_yaml_frontmatter": """
expected_pages:
  - display_name: Dashboard
    action: modify
    source_req_id: REQ-OLD-1
  - name: Settings
    type: new
""",
        "brief_markdown_body": "# Brief",
    }

    status, resp = app.handle_admin_design_handoff_upload(
        _payload(r.req_id, FIXTURE_ZIP.read_bytes()),
        client_ip="127.0.0.1",
    )

    assert status == 200
    assert resp["ok"] is True
    pages_touched = app.service.design_submit.call_args.kwargs["pages_touched"]
    assert {"display_name": "Dashboard", "action": "modify", "source_req_id": "REQ-OLD-1"} in pages_touched
    assert {"display_name": "Settings", "action": "new"} in pages_touched


def test_admin_upload_accepts_localhost_v6(tmp_path):
    app, r = _app_with_drafting_req(tmp_path)
    status, _ = app.handle_admin_design_handoff_upload(
        _payload(r.req_id, FIXTURE_ZIP.read_bytes()),
        client_ip="::1",
    )
    assert status == 200


def test_admin_upload_rejects_invalid_json(tmp_path):
    app, _ = _app_with_drafting_req(tmp_path)
    status, resp = app.handle_admin_design_handoff_upload(
        b"not json",
        client_ip="127.0.0.1",
    )
    assert status == 400
    assert "invalid_json" in resp["error"]


def test_admin_upload_rejects_missing_req_id(tmp_path):
    app, _ = _app_with_drafting_req(tmp_path)
    body = json.dumps({"zip_b64": "aGVsbG8="}).encode()
    status, resp = app.handle_admin_design_handoff_upload(
        body, client_ip="127.0.0.1",
    )
    assert status == 400


def test_admin_upload_rejects_missing_zip_b64(tmp_path):
    app, _ = _app_with_drafting_req(tmp_path)
    body = json.dumps({"req_id": "REQ-Y-001"}).encode()
    status, resp = app.handle_admin_design_handoff_upload(
        body, client_ip="127.0.0.1",
    )
    assert status == 400


def test_admin_upload_rejects_invalid_base64(tmp_path):
    app, _ = _app_with_drafting_req(tmp_path)
    body = json.dumps({"req_id": "REQ-Y-001", "zip_b64": "!!!not base64!!!"}).encode()
    status, resp = app.handle_admin_design_handoff_upload(
        body, client_ip="127.0.0.1",
    )
    assert status == 400
    assert "invalid_base64" in resp["error"]


def test_admin_upload_rejects_unknown_req(tmp_path):
    app, _ = _app_with_drafting_req(tmp_path)
    status, resp = app.handle_admin_design_handoff_upload(
        _payload("REQ-NOPE-999", FIXTURE_ZIP.read_bytes()),
        client_ip="127.0.0.1",
    )
    assert status == 400
    assert "unknown_req_id" in resp["error"]


def test_admin_upload_rejects_req_not_in_drafting(tmp_path):
    app, r = _app_with_drafting_req(tmp_path)
    r.design_status = DesignStatus.READY
    status, resp = app.handle_admin_design_handoff_upload(
        _payload(r.req_id, FIXTURE_ZIP.read_bytes()),
        client_ip="127.0.0.1",
    )
    assert status == 400
    assert "not_in_drafting" in resp["error"]
    assert resp["current_design_status"] == "DESIGN_READY"
