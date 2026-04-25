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


def test_design_callback_design_brief_submit_caches_on_requirement():
    r = Requirement(
        req_id="REQ-X-030", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
        design_status=DesignStatus.DRAFTING,
    )
    app = _app_with_req(r, _cfg())
    # Stub _save_state + _dispatch_transition_notifications + gateway.write_document_text
    app._save_state = MagicMock()
    app._dispatch_transition_notifications = MagicMock()

    body = {
        "req_id": "REQ-X-030",
        "event": "design_brief_submit",
        "payload": {
            "brief_yaml_frontmatter": "schema_version: '1.0'\nreq_id: REQ-X-030\n",
            "brief_markdown_body": "# Brief\n...",
        },
    }
    status, resp = app.handle_openclaw_design_callback(body)
    assert status == 200
    assert resp["design_status"] == DesignStatus.DRAFTING.value
    assert r.pending_design_brief is not None
    assert r.pending_design_brief["brief_yaml_frontmatter"].startswith("schema_version")
    assert r.pending_design_brief["brief_markdown_body"] == "# Brief\n..."
    assert "submitted_at" in r.pending_design_brief
    app._save_state.assert_called_once()


def test_design_callback_returns_404_for_unknown_req():
    r = Requirement(
        req_id="REQ-X-999", name="n", project="X", summary="s", creator="c",
    )
    app = _app_with_req(r, _cfg())
    status, resp = app.handle_openclaw_design_callback({
        "req_id": "REQ-NOT-EXIST", "event": "design_brief_submit", "payload": {},
    })
    assert status == 404


def test_design_callback_returns_409_when_not_drafting():
    r = Requirement(
        req_id="REQ-X-031", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
        design_status=DesignStatus.READY,
    )
    app = _app_with_req(r, _cfg())
    app._save_state = MagicMock()
    status, resp = app.handle_openclaw_design_callback({
        "req_id": "REQ-X-031", "event": "design_brief_submit", "payload": {},
    })
    assert status == 409
    assert resp["error"] == "invalid_state"


def test_design_callback_unknown_event_returns_400():
    r = Requirement(
        req_id="REQ-X-032", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
        design_status=DesignStatus.DRAFTING,
    )
    app = _app_with_req(r, _cfg())
    app._save_state = MagicMock()
    status, resp = app.handle_openclaw_design_callback({
        "req_id": "REQ-X-032", "event": "unknown_foo", "payload": {},
    })
    assert status == 400
    assert resp["error"] == "unknown_event"


def test_design_upload_bundle_action_intakes_and_submits(tmp_path: Path):
    from pathlib import Path as _P
    FIXTURE_ZIP = _P(__file__).parent / "fixtures" / "design" / "handoff_sample.zip"

    r = Requirement(
        req_id="REQ-X-040", name="头像审核", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
        design_status=DesignStatus.DRAFTING,
    )
    app = _app_with_req(r, _cfg())
    app.archive_root = tmp_path / "design" / "archive"
    app.archive_root.mkdir(parents=True)
    app._save_state = MagicMock()
    app._dispatch_transition_notifications = MagicMock()

    # Fake download: copy fixture bytes to dest_path
    def fake_download(*, file_key, message_id, dest_path):
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(FIXTURE_ZIP.read_bytes())
        return dest_path
    app.gateway.download_card_attachment = MagicMock(side_effect=fake_download)

    # Stub service.design_submit to report success (returns the requirement)
    app.service.design_submit = MagicMock(return_value=r)

    value = {
        "action": "design_upload_bundle",
        "req_id": "REQ-X-040",
        "file_key": "fk-1",
        "message_id": "mid-1",
    }
    operator = {"operator_id": {"user_id": "u1"}}
    status, resp = app._handle_design_upload_bundle_action(value, operator)
    assert status == 200
    assert resp.get("toast", {}).get("type") == "success"
    app.gateway.download_card_attachment.assert_called_once()
    app.service.design_submit.assert_called_once()
    kwargs = app.service.design_submit.call_args.kwargs
    assert kwargs["archive_path"].startswith("design/archive/REQ-X-040_")


def test_design_upload_bundle_action_rejects_unknown_req():
    r = Requirement(
        req_id="REQ-X-041", name="n", project="X", summary="s", creator="c",
    )
    app = _app_with_req(r, _cfg())
    app.archive_root = Path("/tmp/nonexistent_archive_root_041")
    value = {"action": "design_upload_bundle", "req_id": "REQ-UNKNOWN",
             "file_key": "fk", "message_id": "mid"}
    status, resp = app._handle_design_upload_bundle_action(value, {})
    assert status == 200
    assert resp.get("toast", {}).get("type") == "error"


def test_design_upload_bundle_action_rejects_non_drafting_state():
    r = Requirement(
        req_id="REQ-X-042", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
        design_status=DesignStatus.READY,
    )
    app = _app_with_req(r, _cfg())
    app.archive_root = Path("/tmp/nonexistent_archive_root_042")
    value = {"action": "design_upload_bundle", "req_id": "REQ-X-042",
             "file_key": "fk", "message_id": "mid"}
    status, resp = app._handle_design_upload_bundle_action(value, {})
    assert status == 200
    assert resp.get("toast", {}).get("type") == "error"


def test_design_upload_bundle_action_rejects_missing_params():
    r = Requirement(
        req_id="REQ-X-043", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
        design_status=DesignStatus.DRAFTING,
    )
    app = _app_with_req(r, _cfg())
    app.archive_root = Path("/tmp/nonexistent_archive_root_043")
    value = {"action": "design_upload_bundle", "req_id": "REQ-X-043"}
    status, resp = app._handle_design_upload_bundle_action(value, {})
    assert status == 200
    assert resp.get("toast", {}).get("type") == "error"


def test_design_final_approve_action_promotes_req_to_ready():
    r = Requirement(
        req_id="REQ-X-050", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
        design_status=DesignStatus.SUBMIT_PENDING_REVIEW,
        pending_design_handoff={
            "archive_path": "design/archive/REQ-X-050_x/",
            "pages_touched": [],
            "submitted_at": "2026-04-23T00:00:00+00:00",
        },
    )
    app = _app_with_req(r, _cfg())
    app._save_state = MagicMock()
    app._dispatch_transition_notifications = MagicMock()

    def fake_approve(req_id, *, approved_by=""):
        r.design_status = DesignStatus.READY
        r.design_precondition_met = True
        return r
    app.service.design_final_approve = MagicMock(side_effect=fake_approve)

    status, resp = app._handle_card_action_payload({
        "action": {"value": {"action": "design_final_approve", "req_id": "REQ-X-050"}},
        "operator": {"operator_id": {"user_id": "u-tech-lead"}},
    })
    app.service.design_final_approve.assert_called_once()
    kwargs = app.service.design_final_approve.call_args.kwargs
    assert kwargs.get("approved_by") == "u-tech-lead"
    assert app._save_state.called


def test_design_final_reject_action_returns_to_drafting():
    r = Requirement(
        req_id="REQ-X-051", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
        design_status=DesignStatus.SUBMIT_PENDING_REVIEW,
    )
    app = _app_with_req(r, _cfg())
    app._save_state = MagicMock()
    app._dispatch_transition_notifications = MagicMock()
    app.service.design_final_reject = MagicMock(return_value=r)

    status, resp = app._handle_card_action_payload({
        "action": {"value": {
            "action": "design_final_reject",
            "req_id": "REQ-X-051",
            "reason": "配色不对",
        }},
        "operator": {"operator_id": {"user_id": "u"}},
    })
    app.service.design_final_reject.assert_called_once_with(
        "REQ-X-051", reason="配色不对",
    )


def test_design_final_approve_missing_req_id_returns_error_toast():
    r = Requirement(req_id="REQ-X-052", name="n", project="X", summary="s", creator="c")
    app = _app_with_req(r, _cfg())
    status, resp = app._handle_card_action_payload({
        "action": {"value": {"action": "design_final_approve"}},
        "operator": {},
    })
    assert status == 200
    assert resp.get("toast", {}).get("type") == "error"


def test_design_final_reject_handles_service_error():
    r = Requirement(
        req_id="REQ-X-053", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
        design_status=DesignStatus.DRAFTING,  # wrong state
    )
    app = _app_with_req(r, _cfg())
    app.service.design_final_reject = MagicMock(
        side_effect=ValueError("wrong state"),
    )
    status, resp = app._handle_card_action_payload({
        "action": {"value": {"action": "design_final_reject", "req_id": "REQ-X-053"}},
        "operator": {},
    })
    assert status == 200
    assert resp.get("toast", {}).get("type") == "error"


# ── DM file message routing ──────────────────────────────────────────────────

def _app_with_drafting_design_req(tmp_path, req_id="REQ-DM-1", creator_user_id="ou_alice"):
    from requirement_workflow_v12.coordinator_service import CoordinatorService
    from requirement_workflow_v12.service_app import CoordinatorRuntimeApp
    from requirement_workflow_v12.plan_state_machine import DesignStatus
    from requirement_workflow_v12.project_config import ProjectConfig

    r = Requirement(
        req_id=req_id, name="n", project="Y", summary="s", creator="c",
        creator_user_id=creator_user_id,
        status=WorkflowStatus.APPROVED, needs_ui=True,
        design_status=DesignStatus.DRAFTING,
        design_doc_id="d", design_doc_url="u",
    )
    cfg = ProjectConfig(
        category="public-web-site", template_version="public-web-site.v1",
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
    app._seen_message_ids = {}
    app._seen_message_ids_max = 1000
    svc.design_submit = MagicMock(return_value=r)
    return app, r


def _file_message_context(user_id, file_key, message_id, chat_id="oc_dm"):
    from requirement_workflow_v12.service_app import MessageContext
    return MessageContext(
        chat_id=chat_id, chat_type="p2p",
        user_id=user_id, text="",
        message_id=message_id,
        file_key=file_key, file_name="handoff.zip",
    )


def test_dm_file_routes_to_handoff_intake(tmp_path):
    app, r = _app_with_drafting_design_req(tmp_path)
    fixture_zip = Path(__file__).parent / "fixtures" / "design" / "handoff_sample.zip"
    app.gateway.download_card_attachment = MagicMock(
        side_effect=lambda *, file_key, message_id, dest_path: Path(dest_path).write_bytes(
            fixture_zip.read_bytes()
        )
    )
    ctx = _file_message_context(r.creator_user_id, "fk_001", "om_001")
    app._handle_dm_file_message(ctx)

    app.service.design_submit.assert_called_once()
    app.gateway.send_text.assert_called()
    reply = app.gateway.send_text.call_args[0][1]
    assert "Handoff 已接收" in reply


def test_dm_file_no_drafting_req_replies_with_info(tmp_path):
    app, r = _app_with_drafting_design_req(tmp_path)
    from requirement_workflow_v12.plan_state_machine import DesignStatus
    r.design_status = DesignStatus.READY  # not DRAFTING

    ctx = _file_message_context(r.creator_user_id, "fk_002", "om_002")
    app._handle_dm_file_message(ctx)

    app.service.design_submit.assert_not_called()
    reply = app.gateway.send_text.call_args[0][1]
    assert "未找到" in reply


def test_dm_file_group_message_ignored(tmp_path):
    app, r = _app_with_drafting_design_req(tmp_path)
    from requirement_workflow_v12.service_app import MessageContext
    ctx = MessageContext(
        chat_id="oc_group", chat_type="group",
        user_id=r.creator_user_id, text="",
        message_id="om_003", file_key="fk_003",
    )
    app._handle_dm_file_message(ctx)

    app.service.design_submit.assert_not_called()
    app.gateway.send_text.assert_not_called()
