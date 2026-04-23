"""P0 + P1 regression guards for the transition-notification card system.

P0: three content/footer fixes
  - spec_submitted must surface spec-author's summary AND link the Spec doc
  - design_brief_ready must NOT claim an "上传 Handoff" button that doesn't exist
  - design_ready must link the Feishu Brief doc

P1: per-trigger target assignment
  - _CARD_TARGETS table routes each trigger to the right audience
  - fallback on unlisted triggers is DM-only (safer than blasting)
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.service_app import CoordinatorRuntimeApp
from requirement_workflow_v12.models import Requirement, WorkflowStatus
from requirement_workflow_v12.plan_state_machine import DesignStatus


def _app() -> CoordinatorRuntimeApp:
    app = CoordinatorRuntimeApp.__new__(CoordinatorRuntimeApp)
    app.service = MagicMock()
    app.settings = MagicMock()
    app.settings.openclaw_reviewer_agent_name = "reviewer"
    app.settings.openclaw_author_agent_name = "author"
    app.settings.openclaw_spec_agent_name = "spec-reviewer"
    app.settings.openclaw_plan_author_agent_name = "plan-author"
    app.settings.feishu_user_id_type = "open_id"
    app.gateway = MagicMock()
    app.gateway.bitable_url.return_value = "https://feishu/bitable"
    return app


def _req(**kw) -> Requirement:
    defaults = dict(
        req_id="REQ-T-001", name="n", project="P", summary="s", creator="c",
        status=WorkflowStatus.APPROVED,
        project_group_id="oc_group_x",
        creator_user_id="ou_creator",
        document_url="https://feishu/d/req-001",
    )
    defaults.update(kw)
    return Requirement(**defaults)


# ────────────────────────────────────────────────────────────────
# P0: spec_submitted surfaces summary + Spec doc link
# ────────────────────────────────────────────────────────────────


def test_spec_submitted_surfaces_spec_author_summary_in_reason():
    """Previously the reason was hardcoded 'Spec Agent 已完成 9 节...' which
    buried whatever spec-author actually reported. Now the author-provided
    summary (stored in spec_review_summary at submit time) is the reason."""
    app = _app()
    r = _req(
        spec_review_summary="v0.3: Dashboard API schema 增加游标分页, token bucket 限流",
    )
    _, _, reason, _, _ = app._transition_notification_content(
        r, trigger="spec_submitted",
    )
    assert "游标分页" in reason
    assert "限流" in reason


def test_spec_submitted_falls_back_to_generic_when_summary_missing():
    """Backward compat: if spec_review_summary is empty (legacy or bug), use
    a generic placeholder rather than an empty reason string."""
    app = _app()
    r = _req(spec_review_summary="")
    _, _, reason, _, _ = app._transition_notification_content(
        r, trigger="spec_submitted",
    )
    assert reason  # non-empty
    assert "Spec" in reason


def test_spec_submitted_card_links_spec_doc_in_footer():
    """The reviewer needs one-click access to the Spec doc from this card.
    Previously only the spec_locked card linked it, hiding it from reviewers
    on the card that matters most."""
    app = _app()
    r = _req(
        spec_document_url="https://feishu/d/spec-doc-abc",
        spec_review_summary="summary",
    )
    card = app._build_transition_notification_card(r, trigger="spec_submitted")
    assert card is not None
    # find the links row
    flat_content = " ".join(
        e.get("content", "")
        for e in card["elements"]
        if isinstance(e, dict) and "content" in e
    )
    assert "查看 Spec 文档" in flat_content
    assert "spec-doc-abc" in flat_content


# ────────────────────────────────────────────────────────────────
# P0: design_brief_ready no longer claims a fake button
# ────────────────────────────────────────────────────────────────


def test_design_brief_ready_does_not_claim_nonexistent_button():
    """Prior text said '点击本卡片的「上传 Handoff」按钮' but the button was
    never wired. Card was lying to users. Must not mention that button."""
    app = _app()
    r = _req(design_status=DesignStatus.DRAFTING)
    _, _, _, _, next_action = app._transition_notification_content(
        r, trigger="design_brief_ready",
    )
    assert "「上传 Handoff」按钮" not in next_action
    assert "点击本卡片的" not in next_action
    # Must still tell user what to do
    assert next_action  # non-empty


# ────────────────────────────────────────────────────────────────
# P0: design_ready links the Feishu Brief doc
# ────────────────────────────────────────────────────────────────


def test_design_ready_card_links_feishu_brief():
    """After design approval, the card going to DM (for next-phase plan kickoff)
    should let the user reopen the Brief with one click."""
    app = _app()
    r = _req(
        design_status=DesignStatus.READY,
        design_doc_url="https://feishu/d/brief-xyz",
        design_archive_path="design/archive/REQ-T-001_foo/",
        design_github_revision="sha",
    )
    card = app._build_transition_notification_card(r, trigger="design_ready")
    assert card is not None
    flat = " ".join(
        e.get("content", "")
        for e in card["elements"]
        if isinstance(e, dict) and "content" in e
    )
    assert "查看设计 Brief" in flat
    assert "brief-xyz" in flat


def test_design_submit_pending_review_card_links_feishu_brief():
    """The terminal reviewer needs the Brief too, to understand what the
    designer was asked to do."""
    app = _app()
    r = _req(
        design_status=DesignStatus.SUBMIT_PENDING_REVIEW,
        design_doc_url="https://feishu/d/brief-xyz",
        design_archive_path="design/archive/REQ-T-001_foo/",
    )
    card = app._build_transition_notification_card(r, trigger="design_submit_pending_review")
    assert card is not None
    flat = " ".join(
        e.get("content", "")
        for e in card["elements"]
        if isinstance(e, dict) and "content" in e
    )
    assert "查看设计 Brief" in flat


# ────────────────────────────────────────────────────────────────
# P1: _CARD_TARGETS routes correctly
# ────────────────────────────────────────────────────────────────


def test_dispatch_group_only_triggers_skip_creator_dm():
    """Milestone announcements (author_submit / human_confirmed / spec_locked /
    design_submit_pending_review) go ONLY to the project group. They're watch-
    only events; routing them to the creator DM was noise."""
    for trigger in ("author_submit", "human_confirmed", "spec_locked", "design_submit_pending_review"):
        app = _app()
        r = _req()
        app._dispatch_transition_notifications(r, trigger=trigger)
        call_args_list = app.gateway.send_card.call_args_list
        receive_ids = [c.args[0] for c in call_args_list]
        assert "oc_group_x" in receive_ids, f"{trigger} should go to group"
        assert "ou_creator" not in receive_ids, f"{trigger} should NOT DM creator"


def test_dispatch_dm_only_triggers_skip_group():
    """Personal action items go to the creator DM only — posting them in the
    group creates doubled buttons (both spots clickable) and visual noise."""
    for trigger in (
        "ai_review_pass", "ai_review_reject", "human_rejected",
        "final_review_rejected", "spec_submitted", "spec_review_reject",
        "plan_submitted_pending_review", "design_brief_ready", "handoff_to_author",
    ):
        app = _app()
        r = _req(spec_review_summary="x", spec_document_url="https://x")
        app._dispatch_transition_notifications(r, trigger=trigger)
        receive_ids = [c.args[0] for c in app.gateway.send_card.call_args_list]
        assert "ou_creator" in receive_ids, f"{trigger} should DM creator"
        assert "oc_group_x" not in receive_ids, f"{trigger} should NOT go to group"


def test_dispatch_both_triggers_go_to_both():
    """Phase-handoff milestones (final_review_passed / plan_ready / design_ready)
    are simultaneously (a) group-visible milestones and (b) trigger creator's
    next action. Both audiences matter."""
    for trigger in ("final_review_passed", "plan_ready", "design_ready"):
        app = _app()
        r = _req(
            design_status=DesignStatus.READY,
            design_doc_url="u", design_archive_path="p",
            plan_doc_url="u",
        )
        app._dispatch_transition_notifications(r, trigger=trigger)
        receive_ids = [c.args[0] for c in app.gateway.send_card.call_args_list]
        assert "ou_creator" in receive_ids, f"{trigger} should DM creator"
        assert "oc_group_x" in receive_ids, f"{trigger} should go to group"


def test_dispatch_unknown_trigger_defaults_to_dm_only():
    """Safer default: new triggers introduced without an explicit CARD_TARGETS
    entry won't accidentally broadcast to the group."""
    app = _app()
    r = _req()
    # Trigger returns empty content by default; to force card generation we
    # patch _build_transition_notification_card to return a stub.
    app._build_transition_notification_card = MagicMock(return_value={"stub": True})
    app._build_transition_notification_text = MagicMock(return_value="")
    app._dispatch_transition_notifications(r, trigger="some_new_trigger_without_mapping")
    receive_ids = [c.args[0] for c in app.gateway.send_card.call_args_list]
    assert "oc_group_x" not in receive_ids
    assert "ou_creator" in receive_ids


def test_dispatch_respects_missing_creator_user_id():
    """DM-only trigger with empty creator_user_id: no crash, no send."""
    app = _app()
    r = _req(creator_user_id="")
    app._dispatch_transition_notifications(r, trigger="spec_submitted")
    app.gateway.send_card.assert_not_called()


def test_dispatch_respects_missing_project_group_id():
    """Group-only trigger with invalid project_group_id: no crash, no send."""
    app = _app()
    r = _req(project_group_id="")
    app._dispatch_transition_notifications(r, trigger="spec_locked")
    app.gateway.send_card.assert_not_called()
