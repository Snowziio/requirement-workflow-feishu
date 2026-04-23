"""Test the Claude Design binding guard in CoordinatorService.design_start."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.models import Requirement, WorkflowStatus
from requirement_workflow_v12.plan_state_machine import DesignStatus
from requirement_workflow_v12.coordinator_service import CoordinatorService
from requirement_workflow_v12.project_config import ProjectConfig


def _svc() -> CoordinatorService:
    svc = CoordinatorService.__new__(CoordinatorService)
    svc.requirements = {}
    svc.project_configs = {}
    svc._hooks = MagicMock()
    return svc


def _req(**kw) -> Requirement:
    return Requirement(
        req_id="REQ-X-001", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
        **kw,
    )


def _cfg(**kw) -> ProjectConfig:
    return ProjectConfig(
        category="enterprise-app",
        template_version="enterprise-app.v1",
        architecture_doc_id="d", architecture_doc_url="u",
        **kw,
    )


def test_design_start_refuses_when_claude_design_url_empty():
    svc = _svc()
    r = _req()
    svc.requirements[r.req_id] = r
    svc.project_configs["X"] = _cfg(claude_design_project_url="")
    import pytest
    with pytest.raises(ValueError, match="Claude Design 未绑定"):
        svc.design_start(r.req_id, design_doc_id="d", design_doc_url="u")


def test_design_start_refuses_when_project_config_missing():
    svc = _svc()
    r = _req()
    svc.requirements[r.req_id] = r
    # No project_configs entry for "X"
    import pytest
    with pytest.raises(ValueError, match="Claude Design 未绑定"):
        svc.design_start(r.req_id, design_doc_id="d", design_doc_url="u")


def test_design_start_succeeds_when_url_is_configured():
    svc = _svc()
    r = _req()
    svc.requirements[r.req_id] = r
    svc.project_configs["X"] = _cfg(
        claude_design_project_url="https://claude.ai/design/p/xyz",
    )
    result = svc.design_start(r.req_id, design_doc_id="d", design_doc_url="u")
    assert result.design_status is DesignStatus.DRAFTING


def test_design_start_guard_message_references_project_name():
    svc = _svc()
    r = _req()
    svc.requirements[r.req_id] = r
    svc.project_configs["X"] = _cfg(claude_design_project_url="")
    import pytest
    with pytest.raises(ValueError) as exc_info:
        svc.design_start(r.req_id, design_doc_id="d", design_doc_url="u")
    assert "X" in str(exc_info.value)


def test_dispatch_design_start_if_needed_emits_binding_card_on_guard_failure():
    """When design_start raises 'Claude Design 未绑定', the runtime must emit a binding card."""
    from requirement_workflow_v12.service_app import (
        CoordinatorRuntimeApp, dispatch_design_start_if_needed,
    )
    from unittest.mock import MagicMock

    r = _req()
    app = CoordinatorRuntimeApp.__new__(CoordinatorRuntimeApp)
    app.service = MagicMock()
    app.service.requirements = {r.req_id: r}
    cfg = _cfg(claude_design_project_url="")
    # Set feishu_chat_id on cfg so the card has somewhere to go
    from dataclasses import replace
    cfg = replace(
        cfg,
        feishu_chat_id="oc_xyz_group",
        github_repo_url="https://github.com/org/X",
    )
    app.service.project_configs = {"X": cfg}
    app.service.design_start.side_effect = ValueError(
        "Claude Design 未绑定（project=X）。请先在项目创建群的绑定卡中填写 claude_design_project_url。"
    )
    app.gateway = MagicMock()
    app.gateway.create_design_document.return_value = MagicMock(
        document_id="d", document_url="u",
    )

    dispatch_design_start_if_needed(app, r)

    # Binding card should have been sent via gateway.send_card
    app.gateway.send_card.assert_called_once()
    call = app.gateway.send_card.call_args
    chat_id = call.args[0] if call.args else call.kwargs.get("receive_id")
    assert chat_id == "oc_xyz_group"
    # The card passed to send_card is the second positional/keyword arg
    card = call.args[1] if len(call.args) > 1 else call.kwargs.get("card")
    assert isinstance(card, dict)
    # Card should have the orange template (error_context present)
    assert card["header"]["template"] == "orange"


def test_dispatch_design_start_non_binding_error_only_logs():
    """ValueErrors that aren't binding-related should just log, not emit a card."""
    from requirement_workflow_v12.service_app import (
        CoordinatorRuntimeApp, dispatch_design_start_if_needed,
    )
    from unittest.mock import MagicMock

    r = _req()
    app = CoordinatorRuntimeApp.__new__(CoordinatorRuntimeApp)
    app.service = MagicMock()
    app.service.requirements = {r.req_id: r}
    app.service.project_configs = {"X": _cfg(claude_design_project_url="https://claude.ai/design/p/x")}
    # Different ValueError — should just log, not send card
    app.service.design_start.side_effect = ValueError("some other error")
    app.gateway = MagicMock()
    app.gateway.create_design_document.return_value = MagicMock(
        document_id="d", document_url="u",
    )

    dispatch_design_start_if_needed(app, r)
    app.gateway.send_card.assert_not_called()


def test_dispatch_design_start_guard_with_no_chat_id_skips_card():
    """If feishu_chat_id is empty and requirement.project_group_id is also empty,
    the card cannot be sent; log warning and exit."""
    from requirement_workflow_v12.service_app import (
        CoordinatorRuntimeApp, dispatch_design_start_if_needed,
    )
    from unittest.mock import MagicMock
    from dataclasses import replace

    r = _req()
    # Ensure requirement has no project_group_id either
    # (Requirement defaults should give us this, but be explicit)
    app = CoordinatorRuntimeApp.__new__(CoordinatorRuntimeApp)
    app.service = MagicMock()
    app.service.requirements = {r.req_id: r}
    cfg = _cfg(claude_design_project_url="")
    app.service.project_configs = {"X": cfg}  # no feishu_chat_id
    app.service.design_start.side_effect = ValueError(
        "Claude Design 未绑定（project=X）。"
    )
    app.gateway = MagicMock()
    app.gateway.create_design_document.return_value = MagicMock(
        document_id="d", document_url="u",
    )

    # Must not raise; just log
    dispatch_design_start_if_needed(app, r)
    app.gateway.send_card.assert_not_called()
