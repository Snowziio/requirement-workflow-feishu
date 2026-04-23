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
