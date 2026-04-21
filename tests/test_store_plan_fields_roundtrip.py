"""Regression: plan/design + spec_* fields must round-trip through JsonStateStore.

Symptom (2026-04-21 smoke test): user clicks "开始 Plan 撰写", plan_start
persists plan_status=DRAFTING + plan_phase=OUTLINE_PENDING, coordinator later
restarts, and on reload Requirement.plan_status comes back None because the
loader silently drops the field. plan-author then submits outline and the
service rejects it with "plan outline can only be set in DRAFTING".
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.models import Requirement, WorkflowStatus
from requirement_workflow_v12.plan_state_machine import (
    DesignStatus, PlanPhase, PlanStatus,
)
from requirement_workflow_v12.spec_state_machine import SpecStatus
from requirement_workflow_v12.store import JsonStateStore


def _seed_full(req_id: str = "REQ-RT-1") -> Requirement:
    r = Requirement(
        req_id=req_id, name="n", project="P", summary="s", creator="c",
    )
    r.status = WorkflowStatus.APPROVED
    r.plan_status = PlanStatus.DRAFTING
    r.plan_phase = PlanPhase.OUTLINE_PENDING
    r.plan_outline = [{"id": "D1", "title": "decision 1"}]
    r.plan_decisions_wip = [{"id": "D1", "chosen": "a"}]
    r.plan_pr_url = "https://github.com/o/r/pull/42"
    r.pending_plan_review = {
        "plan_md_content": "# plan",
        "project_context_change": None,
        "submitted_at": "2026-04-21T00:00:00+00:00",
    }
    r.pending_plan_draft = {"note": "internal"}
    r.plan_doc_id = "doc-plan-xyz"
    r.plan_doc_url = "https://feishu.example/doc/plan-xyz"
    r.plan_github_path = "plans/REQ-RT-1.md"
    r.plan_github_revision = "sha-plan-1"
    r.spec_github_path = "specs/REQ-RT-1/spec.md"
    r.spec_github_revision = "sha-spec-1"
    r.design_status = DesignStatus.DRAFTING
    r.spec_status = SpecStatus.DRAFTING
    r.spec_deadlocked = True
    r.spec_transform_snapshot = {"round": 1}
    r.spec_pr_url = "https://github.com/o/r/pull/7"
    r.spec_source_revision = "abc123"
    r.transform_trace_digest = "deadbeef"
    return r


def test_plan_fields_survive_save_load_roundtrip(tmp_path):
    store = JsonStateStore(str(tmp_path / "state.json"))
    r = _seed_full()
    store.save_snapshot({r.req_id: r}, {}, {})

    reqs, _, _, _ = store.load_snapshot()

    reloaded = reqs[r.req_id]
    assert reloaded.plan_status == PlanStatus.DRAFTING
    assert reloaded.plan_phase == PlanPhase.OUTLINE_PENDING
    assert reloaded.plan_outline == [{"id": "D1", "title": "decision 1"}]
    assert reloaded.plan_decisions_wip == [{"id": "D1", "chosen": "a"}]
    assert reloaded.plan_pr_url == "https://github.com/o/r/pull/42"
    assert reloaded.pending_plan_review == {
        "plan_md_content": "# plan",
        "project_context_change": None,
        "submitted_at": "2026-04-21T00:00:00+00:00",
    }
    assert reloaded.pending_plan_draft == {"note": "internal"}
    assert reloaded.plan_doc_id == "doc-plan-xyz"
    assert reloaded.plan_doc_url == "https://feishu.example/doc/plan-xyz"
    assert reloaded.plan_github_path == "plans/REQ-RT-1.md"
    assert reloaded.plan_github_revision == "sha-plan-1"
    assert reloaded.spec_github_path == "specs/REQ-RT-1/spec.md"
    assert reloaded.spec_github_revision == "sha-spec-1"
    assert reloaded.design_status == DesignStatus.DRAFTING


def test_spec_extension_fields_survive_save_load_roundtrip(tmp_path):
    """Same bug class as plan fields — loader silently drops spec_deadlocked,
    spec_transform_snapshot, spec_pr_url, spec_source_revision,
    transform_trace_digest. Catch them in the same fix."""
    store = JsonStateStore(str(tmp_path / "state.json"))
    r = _seed_full()
    store.save_snapshot({r.req_id: r}, {}, {})

    reqs, _, _, _ = store.load_snapshot()

    reloaded = reqs[r.req_id]
    assert reloaded.spec_deadlocked is True
    assert reloaded.spec_transform_snapshot == {"round": 1}
    assert reloaded.spec_pr_url == "https://github.com/o/r/pull/7"
    assert reloaded.spec_source_revision == "abc123"
    assert reloaded.transform_trace_digest == "deadbeef"


def test_plan_fields_tolerate_absent_keys_from_legacy_state(tmp_path):
    """Old state.json files written before plan fields existed must still load;
    missing keys → default (None / empty)."""
    store = JsonStateStore(str(tmp_path / "state.json"))
    r = Requirement(
        req_id="REQ-OLD-1", name="n", project="P", summary="s", creator="c",
    )
    r.status = WorkflowStatus.APPROVED
    store.save_snapshot({r.req_id: r}, {}, {})

    reqs, _, _, _ = store.load_snapshot()

    reloaded = reqs[r.req_id]
    assert reloaded.plan_status is None
    assert reloaded.plan_phase is None
    assert reloaded.plan_outline == []
    assert reloaded.pending_plan_review is None
    assert reloaded.design_status is None
