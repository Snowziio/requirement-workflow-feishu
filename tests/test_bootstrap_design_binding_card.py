"""Tests for Claude Design binding reminder card builder + emitter."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def test_build_design_binding_card_includes_project_and_repo_url():
    from requirement_workflow_v12.project_bootstrap.service import build_design_binding_card
    card = build_design_binding_card(
        project="testp",
        github_repo_url="https://github.com/org/testp",
    )
    assert isinstance(card, dict)
    # Must have Feishu card structure (header + elements)
    assert "header" in card
    assert "elements" in card
    # Content references
    import json
    text = json.dumps(card, ensure_ascii=False)
    assert "testp" in text
    assert "https://github.com/org/testp" in text
    assert "Claude Design" in text
    assert "bind_claude_design_project" in text


def test_build_design_binding_card_default_template_is_indigo():
    from requirement_workflow_v12.project_bootstrap.service import build_design_binding_card
    card = build_design_binding_card(
        project="testp",
        github_repo_url="https://github.com/org/testp",
    )
    assert card["header"]["template"] == "indigo"


def test_build_design_binding_card_with_error_context_shows_message_and_orange():
    from requirement_workflow_v12.project_bootstrap.service import build_design_binding_card
    card = build_design_binding_card(
        project="testp",
        github_repo_url="https://github.com/org/testp",
        error_context="Claude Design 未绑定（触发原因：design_start guard）",
    )
    # Template should change to orange when error_context present
    assert card["header"]["template"] == "orange"
    # Error message must appear in elements
    import json
    text = json.dumps(card, ensure_ascii=False)
    assert "未绑定" in text or "触发" in text


def test_build_design_binding_card_has_input_and_action_elements():
    from requirement_workflow_v12.project_bootstrap.service import build_design_binding_card
    card = build_design_binding_card(
        project="testp",
        github_repo_url="https://github.com/org/testp",
    )
    tags = [elem.get("tag") for elem in card["elements"]]
    assert "input" in tags
    assert "action" in tags


def test_emit_design_binding_reminder_card_skips_when_no_feishu_chat_id():
    from requirement_workflow_v12.project_bootstrap.service import ProjectBootstrapService
    from requirement_workflow_v12.project_config import ProjectConfig

    service = ProjectBootstrapService(
        repo_tools=MagicMock(), feishu_gateway=MagicMock(), github_gateway=MagicMock(),
        template_owner="org", template_repo="t", new_owner="new",
    )
    cfg = ProjectConfig(
        category="enterprise-app", template_version="enterprise-app.v1",
        architecture_doc_id="d", architecture_doc_url="u",
        feishu_chat_id="",  # empty — skip
        github_repo_url="https://github.com/org/testp",
    )
    service._emit_design_binding_reminder_card(project="testp", cfg=cfg)
    service._feishu.send_card.assert_not_called()


def test_emit_design_binding_reminder_card_calls_send_card_when_chat_id_present():
    from requirement_workflow_v12.project_bootstrap.service import ProjectBootstrapService
    from requirement_workflow_v12.project_config import ProjectConfig

    service = ProjectBootstrapService(
        repo_tools=MagicMock(), feishu_gateway=MagicMock(), github_gateway=MagicMock(),
        template_owner="org", template_repo="t", new_owner="new",
    )
    cfg = ProjectConfig(
        category="enterprise-app", template_version="enterprise-app.v1",
        architecture_doc_id="d", architecture_doc_url="u",
        feishu_chat_id="oc_xyz",
        github_repo_url="https://github.com/org/testp",
    )
    service._emit_design_binding_reminder_card(project="testp", cfg=cfg)
    service._feishu.send_card.assert_called_once()
    call_args = service._feishu.send_card.call_args
    # Accept either positional or keyword receive_id
    chat_id = call_args.args[0] if call_args.args else call_args.kwargs.get("receive_id")
    assert chat_id == "oc_xyz"


def test_emit_design_binding_reminder_card_failure_does_not_raise():
    """Best-effort: send_card failure is logged, not re-raised."""
    from requirement_workflow_v12.project_bootstrap.service import ProjectBootstrapService
    from requirement_workflow_v12.project_config import ProjectConfig

    service = ProjectBootstrapService(
        repo_tools=MagicMock(), feishu_gateway=MagicMock(), github_gateway=MagicMock(),
        template_owner="org", template_repo="t", new_owner="new",
    )
    service._feishu.send_card.side_effect = RuntimeError("feishu 500")
    cfg = ProjectConfig(
        category="enterprise-app", template_version="enterprise-app.v1",
        architecture_doc_id="d", architecture_doc_url="u",
        feishu_chat_id="oc_xyz",
        github_repo_url="https://github.com/org/testp",
    )
    # Must not raise
    service._emit_design_binding_reminder_card(project="testp", cfg=cfg)
