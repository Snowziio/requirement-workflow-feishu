import json
import re
import pytest

SPEC_RESTART_RE = re.compile(r"^/spec\s+restart\s+(REQ-\S+)\s*$")


@pytest.mark.parametrize("text,expected", [
    ("/spec restart REQ-PROJ-005", "REQ-PROJ-005"),
    ("/spec  restart  REQ-X-1", "REQ-X-1"),
    ("/spec restart REQ-X ", "REQ-X"),
])
def test_slash_restart_parses(text, expected):
    m = SPEC_RESTART_RE.match(text)
    assert m is not None
    assert m.group(1) == expected


@pytest.mark.parametrize("text", [
    "/spec restart",
    "spec restart REQ-X",
    "/spec lock REQ-X",
    "",
])
def test_slash_restart_rejects(text):
    assert SPEC_RESTART_RE.match(text) is None


from unittest.mock import MagicMock


def test_handle_spec_restart_command_calls_coordinator():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from requirement_workflow_v12.service_app import CoordinatorRuntimeApp
    app = CoordinatorRuntimeApp.__new__(CoordinatorRuntimeApp)
    app.service = MagicMock()
    event = MagicMock()
    event.chat_id = "oc_test_chat"
    result = app._handle_spec_restart_command(req_id="REQ-PROJ-1", context=event)
    app.service.spec_restart.assert_called_once_with("REQ-PROJ-1")
    assert len(result) == 1
    assert "REQ-PROJ-1" in result[0].text


def _build_bare_app():
    """Construct a CoordinatorRuntimeApp stub bypassing __init__ for pure handler tests."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from requirement_workflow_v12.service_app import CoordinatorRuntimeApp
    app = CoordinatorRuntimeApp.__new__(CoordinatorRuntimeApp)
    app._validate_openclaw_callback_auth = lambda raw_body, *, headers=None: None
    app.service = MagicMock()
    app.service.spec_orchestrator = MagicMock()
    app.settings = MagicMock()
    app.settings.feishu_spec_transform_ops_chat_id = ""
    app.gateway = MagicMock()
    app._save_state = MagicMock()
    return app


def test_spec_transform_callback_routes_transformer_output():
    app = _build_bare_app()
    app.service.spec_orchestrator.handle_transformer_output = MagicMock(
        return_value="wake_reviewer"
    )
    body = json.dumps({
        "req_id": "REQ-P-1",
        "event": "transformer_output",
        "data": {
            "design_md": "x", "tasks_md": "T-001 a\n",
            "ac_schedule_yaml": "version: 1\nacs: []\n",
            "harness_files": {}, "supersedes_decl": [],
            "round_zero_ac_ids": [],
        },
    }).encode()

    status, payload = app.handle_openclaw_spec_transform_callback(body)

    assert status == 200
    assert payload["ok"] is True
    assert payload["next_action"] == "wake_reviewer"
    app.service.spec_orchestrator.handle_transformer_output.assert_called_once()
    args, kwargs = app.service.spec_orchestrator.handle_transformer_output.call_args
    assert args[0] == "REQ-P-1"
    assert args[1]["tasks_md"] == "T-001 a\n"


def test_spec_transform_callback_routes_reviewer_verdict():
    app = _build_bare_app()
    app.service.spec_orchestrator.handle_reviewer_verdict = MagicMock(
        return_value="converged"
    )
    body = json.dumps({
        "req_id": "REQ-P-1",
        "event": "reviewer_verdict",
        "data": {"verdict": "converged", "findings": []},
    }).encode()

    status, payload = app.handle_openclaw_spec_transform_callback(body)

    assert status == 200
    assert payload["next_action"] == "converged"
    app.service.spec_orchestrator.handle_reviewer_verdict.assert_called_once_with(
        "REQ-P-1", "converged", [],
    )


def test_spec_transform_callback_rejects_unknown_event():
    app = _build_bare_app()
    body = json.dumps({"req_id": "REQ-P-1", "event": "garbage", "data": {}}).encode()
    status, payload = app.handle_openclaw_spec_transform_callback(body)
    assert status == 400
    assert "unknown_event" in payload.get("error", "")


def test_spec_transform_callback_rejects_invalid_json():
    app = _build_bare_app()
    status, payload = app.handle_openclaw_spec_transform_callback(b"not json")
    assert status == 400
    assert payload["error"] == "invalid_json"


def test_spec_transform_callback_auth_failure_propagates():
    app = _build_bare_app()
    app._validate_openclaw_callback_auth = lambda raw_body, *, headers=None: (
        401, {"error": "unauthorized"}
    )
    body = json.dumps({"req_id": "R", "event": "transformer_output", "data": {}}).encode()
    status, payload = app.handle_openclaw_spec_transform_callback(body)
    assert status == 401
    assert payload["error"] == "unauthorized"


def _build_app_with_ops_chat():
    """Bare app with ops chat configured for wake tests."""
    app = _build_bare_app()
    app.settings.feishu_spec_transform_ops_chat_id = "oc_ops_chat"
    app.settings.openclaw_spec_transformer_agent_name = "Spec 转化助手"
    app.settings.openclaw_spec_transformer_reviewer_agent_name = "Spec 转化审查助手"
    app.service.spec_orchestrator._rounds = {}
    return app


def test_callback_wake_reviewer_sends_text_to_ops_chat():
    app = _build_app_with_ops_chat()
    app.service.spec_orchestrator.handle_transformer_output = MagicMock(
        return_value="wake_reviewer"
    )
    from unittest.mock import PropertyMock
    app.service.spec_orchestrator._rounds = {"REQ-P-1": MagicMock(round_index=2)}
    body = json.dumps({
        "req_id": "REQ-P-1", "event": "transformer_output",
        "data": {"design_md": "x", "tasks_md": "t\n", "ac_schedule_yaml": "y",
                 "harness_files": {}, "supersedes_decl": [], "round_zero_ac_ids": []},
    }).encode()

    status, payload = app.handle_openclaw_spec_transform_callback(body)

    assert status == 200
    assert payload["next_action"] == "wake_reviewer"
    app.gateway.send_text.assert_called_once_with(
        "oc_ops_chat", "请评审 Spec 转化产出 REQ-P-1 (round=2)", receive_id_type="chat_id",
    )


def test_callback_wake_transformer_next_round_sends_text():
    app = _build_app_with_ops_chat()
    app.service.spec_orchestrator.handle_reviewer_verdict = MagicMock(
        return_value="wake_transformer_next_round"
    )
    app.service.spec_orchestrator._rounds = {"REQ-P-1": MagicMock(round_index=3)}
    body = json.dumps({
        "req_id": "REQ-P-1", "event": "reviewer_verdict",
        "data": {"verdict": "reject", "findings": [{"severity": "blocking"}]},
    }).encode()

    status, payload = app.handle_openclaw_spec_transform_callback(body)

    assert status == 200
    app.gateway.send_text.assert_called_once()
    text_arg = app.gateway.send_text.call_args[0][1]
    assert "请开始 Spec 转化 REQ-P-1 (round=3)" == text_arg


def test_callback_converged_does_not_wake():
    app = _build_app_with_ops_chat()
    app.service.spec_orchestrator.handle_reviewer_verdict = MagicMock(
        return_value="converged"
    )
    body = json.dumps({
        "req_id": "REQ-P-1", "event": "reviewer_verdict",
        "data": {"verdict": "converged", "findings": []},
    }).encode()

    status, _ = app.handle_openclaw_spec_transform_callback(body)
    assert status == 200
    app.gateway.send_text.assert_not_called()


def test_callback_no_ops_chat_skips_wake_gracefully():
    app = _build_bare_app()
    app.settings.feishu_spec_transform_ops_chat_id = ""
    app.service.spec_orchestrator.handle_transformer_output = MagicMock(
        return_value="wake_reviewer"
    )
    body = json.dumps({
        "req_id": "REQ-P-1", "event": "transformer_output",
        "data": {"design_md": "x", "tasks_md": "t\n", "ac_schedule_yaml": "y",
                 "harness_files": {}, "supersedes_decl": [], "round_zero_ac_ids": []},
    }).encode()

    status, payload = app.handle_openclaw_spec_transform_callback(body)
    assert status == 200
    app.gateway.send_text.assert_not_called()


def test_runtime_wires_spec_orchestrator_when_github_token_set(tmp_path, monkeypatch):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    # httpx.Client picks up proxy env vars at construction; clear them so the
    # GitHubGateway constructor does not fail in environments with SOCKS proxies.
    for key in ("all_proxy", "ALL_PROXY", "http_proxy", "HTTP_PROXY",
                "https_proxy", "HTTPS_PROXY"):
        monkeypatch.delenv(key, raising=False)
    from requirement_workflow_v12.config import Settings
    from requirement_workflow_v12.service_app import CoordinatorRuntimeApp
    from requirement_workflow_v12.coordinator_service import CoordinatorService
    settings = Settings(
        feishu_app_id="x", feishu_app_secret="y",
        state_store_path=str(tmp_path / "state.json"),
        github_token="ghp_test",
        spec_trace_dir=str(tmp_path / "traces"),
    )
    svc = CoordinatorService()
    gateway = MagicMock()
    gateway.list_project_configs = MagicMock(return_value={})
    app = CoordinatorRuntimeApp(settings, service=svc, gateway=gateway)
    assert app.service.spec_orchestrator is not None
    assert app.service._acm_registry is not None


def test_runtime_leaves_spec_orchestrator_none_when_no_github_token(tmp_path):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from requirement_workflow_v12.config import Settings
    from requirement_workflow_v12.service_app import CoordinatorRuntimeApp
    from requirement_workflow_v12.coordinator_service import CoordinatorService
    settings = Settings(
        feishu_app_id="x", feishu_app_secret="y",
        state_store_path=str(tmp_path / "state.json"),
        github_token="",  # explicit: no GitHub token configured
    )
    svc = CoordinatorService()
    gateway = MagicMock()
    gateway.list_project_configs = MagicMock(return_value={})
    app = CoordinatorRuntimeApp(settings, service=svc, gateway=gateway)
    assert app.service.spec_orchestrator is None
