"""Unit tests for design-brief-author handoff DM helpers."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.models import Requirement, WorkflowStatus


def _req(**kw) -> Requirement:
    defaults = dict(
        req_id="REQ-PROJ-007",
        name="头像审核",
        project="proj",
        summary="用户上传头像走审核",
        creator="u1",
        creator_user_id="ou_designer",
        status=WorkflowStatus.APPROVED,
        needs_ui=True,
    )
    defaults.update(kw)
    return Requirement(**defaults)


def test_build_handoff_text_contains_req_id_and_trigger_phrase():
    from requirement_workflow_v12.service_app import _build_design_brief_author_handoff_text
    text = _build_design_brief_author_handoff_text(_req())
    assert "REQ-PROJ-007" in text
    assert "请开始设计 Brief 生成" in text


def test_build_handoff_text_includes_coordinator_base_url_env():
    from requirement_workflow_v12.service_app import _build_design_brief_author_handoff_text
    with patch.dict(os.environ, {"COORDINATOR_BASE_URL": "https://staging.example.com"}):
        text = _build_design_brief_author_handoff_text(_req())
        assert "https://staging.example.com" in text


def test_build_handoff_text_has_default_base_url_when_env_missing():
    from requirement_workflow_v12.service_app import _build_design_brief_author_handoff_text
    env = {k: v for k, v in os.environ.items() if k != "COORDINATOR_BASE_URL"}
    with patch.dict(os.environ, env, clear=True):
        text = _build_design_brief_author_handoff_text(_req())
        assert "COORDINATOR_BASE_URL=" in text
        assert "http" in text


def test_build_handoff_text_instructs_to_forward():
    """Handoff text should tell the user to forward the message to the agent."""
    from requirement_workflow_v12.service_app import _build_design_brief_author_handoff_text
    text = _build_design_brief_author_handoff_text(_req())
    assert "design-brief-author" in text
    assert "转发" in text or "forward" in text.lower() or "粘贴" in text or "贴给" in text


def test_send_handoff_skips_when_creator_user_id_empty():
    from requirement_workflow_v12.service_app import _send_design_brief_author_handoff
    app = MagicMock()
    app.gateway = MagicMock()
    r = _req(creator_user_id="")
    _send_design_brief_author_handoff(app, r)
    app.gateway.send_text.assert_not_called()


def test_send_handoff_calls_send_text_when_creator_user_id_present():
    from requirement_workflow_v12.service_app import _send_design_brief_author_handoff
    app = MagicMock()
    app.gateway = MagicMock()
    r = _req(creator_user_id="ou_designer_123")
    _send_design_brief_author_handoff(app, r)
    app.gateway.send_text.assert_called_once()
    kwargs = app.gateway.send_text.call_args.kwargs
    args = app.gateway.send_text.call_args.args
    receive_id = args[0] if args else kwargs.get("receive_id")
    assert receive_id == "ou_designer_123"
    text = args[1] if len(args) > 1 else kwargs.get("text")
    assert "REQ-PROJ-007" in text
    assert kwargs.get("receive_id_type") == "user_id"


def test_send_handoff_swallows_gateway_failure():
    """Gateway errors must not propagate (best-effort)."""
    from requirement_workflow_v12.service_app import _send_design_brief_author_handoff
    app = MagicMock()
    app.gateway = MagicMock()
    app.gateway.send_text.side_effect = RuntimeError("feishu 500")
    r = _req()
    # Must not raise
    _send_design_brief_author_handoff(app, r)


def test_dispatch_design_start_triggers_handoff_dm():
    """dispatch_design_start_if_needed must call _send_design_brief_author_handoff
    after a successful design_start."""
    from requirement_workflow_v12.service_app import dispatch_design_start_if_needed
    from requirement_workflow_v12.project_config import ProjectConfig
    app = MagicMock()
    app.service = MagicMock()
    cfg = ProjectConfig(
        category="enterprise-app",
        template_version="enterprise-app.v1",
        architecture_doc_id="d",
        architecture_doc_url="u",
        claude_design_project_url="https://claude.ai/design/p/abc",
    )
    app.service.project_configs = {"proj": cfg}
    app.service.design_start = MagicMock()
    app.gateway = MagicMock()
    created_doc = MagicMock(document_id="d-1", document_url="https://feishu/d/1")
    app.gateway.create_design_document.return_value = created_doc

    r = _req()

    dispatch_design_start_if_needed(app, r)

    # Handoff DM should have been sent
    app.gateway.send_text.assert_called_once()


def test_dispatch_design_start_handoff_failure_does_not_break_flow():
    """Even if the handoff DM fails, dispatch must not raise."""
    from requirement_workflow_v12.service_app import dispatch_design_start_if_needed
    from requirement_workflow_v12.project_config import ProjectConfig
    app = MagicMock()
    app.service = MagicMock()
    cfg = ProjectConfig(
        category="enterprise-app",
        template_version="enterprise-app.v1",
        architecture_doc_id="d",
        architecture_doc_url="u",
        claude_design_project_url="https://claude.ai/design/p/abc",
    )
    app.service.project_configs = {"proj": cfg}
    app.service.design_start = MagicMock()
    app.gateway = MagicMock()
    created_doc = MagicMock(document_id="d-1", document_url="https://feishu/d/1")
    app.gateway.create_design_document.return_value = created_doc
    app.gateway.send_text.side_effect = RuntimeError("feishu send failed")

    r = _req()

    # Must not raise
    dispatch_design_start_if_needed(app, r)
