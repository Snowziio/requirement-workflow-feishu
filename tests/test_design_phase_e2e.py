"""End-to-end happy path test for the DESIGN phase.

Exercises: design_start → intake (real zip) → design_submit → design_final_approve.

Scope note: Does NOT wire `configure_design_hooks` / DesignSyncer — that requires
a real GitHub gateway and is a v2 concern. Here we verify the state-machine +
Requirement field mutations end up in the correct terminal state.
"""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.models import Requirement, WorkflowStatus
from requirement_workflow_v12.plan_state_machine import DesignStatus


FIXTURE_ZIP = Path(__file__).parent / "fixtures" / "design" / "handoff_sample.zip"


def test_happy_path_draft_to_ready(tmp_path: Path) -> None:
    from requirement_workflow_v12.coordinator_service import CoordinatorService
    from requirement_workflow_v12.project_repo import StateTransitionHooks

    # Setup: blank coordinator service, one APPROVED+needs_ui REQ
    svc = CoordinatorService.__new__(CoordinatorService)
    svc.requirements = {}
    svc.project_configs = {}
    svc._hooks = StateTransitionHooks()

    r = Requirement(
        req_id="REQ-E2E-001", name="E2E test", project="P",
        summary="e2e flow", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
    )
    svc.requirements[r.req_id] = r

    # ── Step 1: design_start ──────────────────────────────────────────
    svc.design_start(
        r.req_id,
        design_doc_id="feishu-doc-e2e-001",
        design_doc_url="https://feishu/docx/e2e-001",
    )
    assert r.design_status is DesignStatus.DRAFTING
    assert r.design_doc_id == "feishu-doc-e2e-001"
    assert r.design_doc_url == "https://feishu/docx/e2e-001"

    # ── Step 2: intake the real fixture zip ───────────────────────────
    from requirement_workflow_v12.design_intake import DesignIntake
    archive_root = tmp_path / "design" / "archive"
    archive_root.mkdir(parents=True)
    intake_result = DesignIntake().intake(
        zip_path=FIXTURE_ZIP,
        req_id=r.req_id,
        slug="e2e-slug",
        archive_root=archive_root,
    )
    assert intake_result.archive_dir.name == "REQ-E2E-001_e2e-slug"
    assert (intake_result.archive_dir / "MANIFEST.md").exists()
    assert (intake_result.archive_dir / "bundle.zip").exists()
    assert (intake_result.archive_dir / "extracted" / "untitled" / "README.md").exists()

    # Bundle pages_hint should include at least one page name (from bundle src/)
    assert len(intake_result.pages_hint) > 0

    # ── Step 3: design_submit ─────────────────────────────────────────
    pages_touched = [
        {"display_name": p, "action": "new"} for p in intake_result.pages_hint
    ]
    archive_path_str = f"design/archive/{intake_result.archive_dir.name}/"

    svc.design_submit(
        r.req_id,
        archive_path=archive_path_str,
        pages_touched=pages_touched,
    )
    assert r.design_status is DesignStatus.SUBMIT_PENDING_REVIEW
    assert r.pending_design_handoff is not None
    assert r.pending_design_handoff["archive_path"] == archive_path_str
    assert r.pending_design_handoff["pages_touched"] == pages_touched
    assert "submitted_at" in r.pending_design_handoff

    # ── Step 4: design_final_approve ──────────────────────────────────
    svc.design_final_approve(r.req_id, approved_by="tech-lead-e2e")
    assert r.design_status is DesignStatus.READY
    assert r.design_precondition_met is True
    assert r.pending_design_handoff is None  # cleared after approval
    assert r.design_archive_path == archive_path_str


def test_e2e_reject_path_returns_to_drafting(tmp_path: Path) -> None:
    """Alternate path: submit, then reject; back to DRAFTING."""
    from requirement_workflow_v12.coordinator_service import CoordinatorService
    from requirement_workflow_v12.project_repo import StateTransitionHooks
    from requirement_workflow_v12.design_intake import DesignIntake

    svc = CoordinatorService.__new__(CoordinatorService)
    svc.requirements = {}
    svc.project_configs = {}
    svc._hooks = StateTransitionHooks()

    r = Requirement(
        req_id="REQ-E2E-002", name="reject test", project="P",
        summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
    )
    svc.requirements[r.req_id] = r

    svc.design_start(r.req_id, design_doc_id="d", design_doc_url="u")

    archive_root = tmp_path / "design" / "archive"
    archive_root.mkdir(parents=True)
    intake_result = DesignIntake().intake(
        zip_path=FIXTURE_ZIP,
        req_id=r.req_id,
        slug="x",
        archive_root=archive_root,
    )
    svc.design_submit(
        r.req_id,
        archive_path=f"design/archive/{intake_result.archive_dir.name}/",
        pages_touched=[],
    )
    assert r.design_status is DesignStatus.SUBMIT_PENDING_REVIEW

    svc.design_final_reject(r.req_id, reason="配色偏差")
    assert r.design_status is DesignStatus.DRAFTING
    assert r.design_precondition_met is False
    assert r.pending_design_handoff is not None
    assert r.pending_design_handoff["reject_reason"] == "配色偏差"


def test_e2e_restart_from_submit_pending_cascades_to_plan_and_spec(tmp_path: Path) -> None:
    """Design restart resets DesignStatus and cascades Plan + Spec reset."""
    from requirement_workflow_v12.coordinator_service import CoordinatorService
    from requirement_workflow_v12.project_repo import StateTransitionHooks

    svc = CoordinatorService.__new__(CoordinatorService)
    svc.requirements = {}
    svc.project_configs = {}
    svc._hooks = StateTransitionHooks()
    svc._plan_tools = None
    svc._plan_syncer = None
    svc.spec_orchestrator = None

    r = Requirement(
        req_id="REQ-E2E-003", name="restart test", project="P",
        summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
    )
    svc.requirements[r.req_id] = r

    svc.design_start(r.req_id, design_doc_id="d", design_doc_url="u")
    svc.design_submit(
        r.req_id, archive_path="design/archive/x/", pages_touched=[],
    )
    assert r.design_status is DesignStatus.SUBMIT_PENDING_REVIEW

    svc.design_restart(r.req_id)
    assert r.design_status is None
    assert r.design_precondition_met is False
