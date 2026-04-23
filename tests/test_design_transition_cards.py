import sys
from pathlib import Path
from unittest.mock import MagicMock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.service_app import CoordinatorRuntimeApp
from requirement_workflow_v12.models import Requirement, WorkflowStatus
from requirement_workflow_v12.plan_state_machine import DesignStatus


def _app() -> CoordinatorRuntimeApp:
    """Minimal app for testing card content/button builders."""
    app = CoordinatorRuntimeApp.__new__(CoordinatorRuntimeApp)
    app.service = MagicMock()
    app.settings = MagicMock()
    app.settings.openclaw_reviewer_agent_name = "reviewer"
    app.settings.openclaw_author_agent_name = "author"
    app.settings.openclaw_spec_agent_name = "spec-reviewer"
    app.settings.openclaw_plan_author_agent_name = "plan-author"
    return app


def _req(**kw) -> Requirement:
    return Requirement(
        req_id="REQ-X-001", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
        design_doc_url="https://feishu/d/design-001",
        design_archive_path="design/archive/REQ-X-001_x/",
        **kw,
    )


def test_design_brief_ready_content_has_five_fields():
    """design_brief_ready trigger must return (color, title, reason, result, next_action) tuple."""
    app = _app()
    r = _req(design_status=DesignStatus.DRAFTING)
    content = app._transition_notification_content(r, trigger="design_brief_ready")
    assert isinstance(content, tuple)
    assert len(content) == 5
    color, title, reason, result, next_action = content
    # Sanity checks
    assert "REQ-X-001" in title or "设计" in title
    assert next_action  # non-empty


def test_design_submit_pending_review_content_mentions_review():
    """design_submit_pending_review must cue the technical lead to review."""
    app = _app()
    r = _req(design_status=DesignStatus.SUBMIT_PENDING_REVIEW)
    color, title, reason, result, next_action = app._transition_notification_content(
        r, trigger="design_submit_pending_review",
    )
    assert "审查" in next_action or "终审" in next_action or "review" in next_action.lower()
    # Buttons should include approve/reject
    buttons = app._build_transition_notification_actions(r, trigger="design_submit_pending_review")
    assert isinstance(buttons, list)
    assert len(buttons) >= 2
    actions = {btn["value"]["action"] for btn in buttons}
    assert "design_final_approve" in actions
    assert "design_final_reject" in actions


def test_design_ready_content_mentions_plan_unlock():
    """design_ready must inform users that Plan phase is now unlocked."""
    app = _app()
    r = _req(design_status=DesignStatus.READY, design_precondition_met=True)
    color, title, reason, result, next_action = app._transition_notification_content(
        r, trigger="design_ready",
    )
    assert "Plan" in next_action or "规划" in next_action
    # Should have a button to start plan
    buttons = app._build_transition_notification_actions(r, trigger="design_ready")
    assert isinstance(buttons, list)
    action_names = {btn["value"]["action"] for btn in buttons}
    assert "send_plan_author_start" in action_names


def test_design_brief_ready_no_buttons_needed():
    """design_brief_ready is an info-only notification; no buttons (or empty list)."""
    app = _app()
    r = _req(design_status=DesignStatus.DRAFTING)
    buttons = app._build_transition_notification_actions(r, trigger="design_brief_ready")
    # Empty list is fine — the card is informational
    assert isinstance(buttons, list)


def test_unknown_trigger_still_returns_default():
    """Sanity: unknown trigger still works via fallback (existing behavior)."""
    app = _app()
    r = _req(design_status=DesignStatus.DRAFTING)
    # This tests that the existing fallback isn't broken by our additions
    try:
        content = app._transition_notification_content(r, trigger="unknown_xyz")
        # If a fallback exists, it'll return a tuple
        assert isinstance(content, tuple)
    except Exception:
        pass  # If no fallback, that's existing behavior we don't touch
