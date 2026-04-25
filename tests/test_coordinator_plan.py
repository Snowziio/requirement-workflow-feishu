import sys
import copy
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from requirement_workflow_v12.coordinator_service import CoordinatorService
from requirement_workflow_v12.models import Requirement, WorkflowStatus
from requirement_workflow_v12.plan_state_machine import (
    PlanStatus, PlanPhase, DesignStatus,
)


def _approved_req(svc, req_id="REQ-P-1", needs_ui=False):
    r = Requirement(
        req_id=req_id, name="n", project="P", summary="s", creator="c",
    )
    r.status = WorkflowStatus.APPROVED
    r.needs_ui = needs_ui
    svc.requirements[req_id] = r
    return r


def test_plan_start_sets_status_drafting_and_outline_pending_phase():
    svc = CoordinatorService()
    r = _approved_req(svc)

    result = svc.plan_start(r.req_id)

    assert result.plan_status is PlanStatus.DRAFTING
    assert result.plan_phase is PlanPhase.OUTLINE_PENDING


def test_plan_start_rejected_when_not_approved():
    svc = CoordinatorService()
    r = _approved_req(svc)
    r.status = WorkflowStatus.DRAFTING

    with pytest.raises(ValueError, match="APPROVED"):
        svc.plan_start(r.req_id)


def test_plan_start_rejected_when_already_drafting():
    svc = CoordinatorService()
    r = _approved_req(svc)
    svc.plan_start(r.req_id)
    with pytest.raises(ValueError):
        svc.plan_start(r.req_id)


def test_plan_start_persists_plan_doc_id_and_url_when_provided():
    svc = CoordinatorService()
    r = _approved_req(svc)

    result = svc.plan_start(
        r.req_id,
        plan_doc_id="docx-plan-abc",
        plan_doc_url="https://feishu.example/docx/docx-plan-abc",
    )

    assert result.plan_doc_id == "docx-plan-abc"
    assert result.plan_doc_url == "https://feishu.example/docx/docx-plan-abc"


def test_plan_start_plan_doc_fields_default_empty_when_omitted():
    svc = CoordinatorService()
    r = _approved_req(svc)

    result = svc.plan_start(r.req_id)

    assert result.plan_doc_id == ""
    assert result.plan_doc_url == ""


from unittest.mock import MagicMock


def test_plan_submit_without_project_context_change_goes_ready():
    svc = CoordinatorService()
    r = _approved_req(svc)
    svc.plan_start(r.req_id)
    svc._hooks.on_enter(PlanStatus.READY, lambda _r: None)

    plan_md = "---\nreq_id: REQ-P-1\n---\n"
    svc.plan_submit(r.req_id, plan_md_content=plan_md, project_context_change=None)

    assert r.plan_status is PlanStatus.READY
    assert r.pending_plan_draft is not None
    assert r.pending_plan_draft["plan_md_content"] == plan_md
    assert r.pending_plan_draft["project_context_change"] is None


def test_plan_submit_rolls_back_when_ready_hook_fails():
    svc = CoordinatorService()
    r = _approved_req(svc)
    svc.plan_start(r.req_id)
    before_phase = r.plan_phase

    def fail_ready(_r):
        raise RuntimeError("plan sync failed")

    svc._hooks.on_enter(PlanStatus.READY, fail_ready)

    with pytest.raises(RuntimeError, match="plan sync failed"):
        svc.plan_submit(
            r.req_id,
            plan_md_content="---\nreq_id: REQ-P-1\n---\n",
            project_context_change=None,
        )

    assert r.plan_status is PlanStatus.DRAFTING
    assert r.plan_phase is before_phase
    assert r.pending_plan_draft is None
    assert r.plan_pr_url == ""


def test_plan_submit_with_project_context_change_goes_auth_pending():
    svc = CoordinatorService()
    r = _approved_req(svc)
    svc.plan_start(r.req_id)
    svc._hooks.on_enter(PlanStatus.AUTH_PENDING, lambda _r: None)

    arch = {"summary": "x", "changes": [], "authorized": False}
    svc.plan_submit(
        r.req_id, plan_md_content="---\n---\n", project_context_change=arch,
    )
    assert r.plan_status is PlanStatus.AUTH_PENDING
    assert r.pending_plan_draft["project_context_change"] == arch


def test_plan_submit_rejected_when_not_drafting():
    svc = CoordinatorService()
    r = _approved_req(svc)
    with pytest.raises(ValueError):
        svc.plan_submit(
            r.req_id, plan_md_content="---\n---\n", project_context_change=None,
        )


def test_plan_authorize_from_auth_pending_goes_ready_and_marks_authorized():
    svc = CoordinatorService()
    r = _approved_req(svc)
    svc.plan_start(r.req_id)
    svc._hooks.on_enter(PlanStatus.AUTH_PENDING, lambda _r: None)
    svc._hooks.on_enter(PlanStatus.READY, lambda _r: None)
    svc.plan_submit(
        r.req_id, plan_md_content="---\n---\n",
        project_context_change={"summary": "x", "changes": [], "authorized": False},
    )
    assert r.plan_status is PlanStatus.AUTH_PENDING

    svc.plan_authorize(r.req_id, authorized_by="ou-123")

    assert r.plan_status is PlanStatus.READY
    arch = r.pending_plan_draft["project_context_change"]
    assert arch["authorized"] is True
    assert arch["authorized_by"] == "ou-123"
    assert arch["authorized_at"]


def test_plan_authorize_rolls_back_when_ready_hook_fails():
    svc = CoordinatorService()
    r = _approved_req(svc)
    svc.plan_start(r.req_id)
    svc._hooks.on_enter(PlanStatus.AUTH_PENDING, lambda _r: None)
    svc.plan_submit(
        r.req_id, plan_md_content="---\n---\n",
        project_context_change={"summary": "x", "changes": [], "authorized": False},
    )
    before_draft = copy.deepcopy(r.pending_plan_draft)

    def fail_ready(_r):
        raise RuntimeError("plan sync failed")

    svc._hooks.on_enter(PlanStatus.READY, fail_ready)

    with pytest.raises(RuntimeError, match="plan sync failed"):
        svc.plan_authorize(r.req_id, authorized_by="ou-123")

    assert r.plan_status is PlanStatus.AUTH_PENDING
    assert r.pending_plan_draft == before_draft


def test_plan_authorization_reject_returns_to_drafting():
    svc = CoordinatorService()
    r = _approved_req(svc)
    svc.plan_start(r.req_id)
    svc._hooks.on_enter(PlanStatus.AUTH_PENDING, lambda _r: None)
    svc.plan_submit(
        r.req_id, plan_md_content="---\n---\n",
        project_context_change={"summary": "x", "changes": []},
    )

    svc.plan_authorization_reject(r.req_id, reason="need more context")

    assert r.plan_status is PlanStatus.DRAFTING
    assert r.plan_phase is PlanPhase.DECISIONS_IN_PROGRESS
    assert r.pending_plan_draft is not None


def test_plan_authorize_rejected_when_not_auth_pending():
    svc = CoordinatorService()
    r = _approved_req(svc)
    svc.plan_start(r.req_id)
    with pytest.raises(ValueError):
        svc.plan_authorize(r.req_id, authorized_by="ou-123")


from requirement_workflow_v12.project_repo import (
    PlanArtifacts, PlanCommitResult, ProjectRepoError,
)


def test_configure_plan_hooks_wires_ready_commit_hook():
    svc = CoordinatorService()
    tools = MagicMock()
    svc.configure_plan_hooks(tools=tools)
    assert PlanStatus.READY in svc._hooks._on_enter
    assert len(svc._hooks._on_enter[PlanStatus.READY]) == 1


def test_on_enter_ready_commits_plan_and_clears_draft():
    svc = CoordinatorService()
    tools = MagicMock()
    tools.commit_plan_artifacts.return_value = PlanCommitResult(
        commit_sha="sha-1", branch="main",
        plan_md_path="docs/specs/REQ-P-1/plan.md",
        architecture_updated=False,
    )
    svc.configure_plan_hooks(tools=tools)

    from requirement_workflow_v12.project_config import ProjectConfig
    svc.project_configs["P"] = ProjectConfig(
        category="web", template_version="v1",
        architecture_doc_id="", architecture_doc_url="",
        tech_stack={}, github_repo_url="owner/repo",
    )
    r = _approved_req(svc)
    svc.plan_start(r.req_id)
    svc.plan_submit(
        r.req_id, plan_md_content="---\nreq_id: REQ-P-1\n---\n",
        project_context_change=None,
    )

    assert r.plan_status is PlanStatus.READY
    assert r.plan_pr_url == "sha-1"
    assert r.pending_plan_draft is None
    tools.commit_plan_artifacts.assert_called_once()
    artifacts = tools.commit_plan_artifacts.call_args.args[0]
    assert isinstance(artifacts, PlanArtifacts)
    assert artifacts.req_id == "REQ-P-1"
    assert artifacts.project_repo == "owner/repo"


def test_on_enter_ready_hook_delegates_to_feishu_syncer_when_wired():
    """When a FeishuToGitHubSyncer is wired, the hook reads plan.md from the
    Feishu SOT via the syncer (passing pending_plan_draft.plan_md_content as
    audit fallback) instead of building PlanArtifacts directly from the draft.
    """
    from requirement_workflow_v12.feishu_to_github_syncer import PlanSyncResult
    svc = CoordinatorService()
    tools = MagicMock()
    syncer = MagicMock()
    syncer.sync_plan.return_value = PlanSyncResult(
        commit_sha="https://github.com/owner/repo/commit/sha-s",
        plan_github_path="docs/specs/REQ-P-1/plan.md",
        architecture_updated=False,
    )
    svc.configure_plan_hooks(tools=tools, syncer=syncer)

    from requirement_workflow_v12.project_config import ProjectConfig
    svc.project_configs["P"] = ProjectConfig(
        category="web", template_version="v1",
        architecture_doc_id="", architecture_doc_url="",
        tech_stack={}, github_repo_url="owner/repo",
    )
    r = _approved_req(svc)
    svc.plan_start(
        r.req_id, plan_doc_id="docx-plan-abc",
        plan_doc_url="https://feishu/docx/docx-plan-abc",
    )
    svc.plan_submit(
        r.req_id, plan_md_content="---\nreq_id: REQ-P-1\n---\n",
        project_context_change=None,
    )

    syncer.sync_plan.assert_called_once()
    kwargs = syncer.sync_plan.call_args.kwargs
    assert kwargs["req_id"] == "REQ-P-1"
    assert kwargs["project_repo"] == "owner/repo"
    assert kwargs["plan_doc_id"] == "docx-plan-abc"
    assert kwargs["project_context_change"] is None
    assert kwargs["fallback_plan_md"] == "---\nreq_id: REQ-P-1\n---\n"
    tools.commit_plan_artifacts.assert_not_called()
    assert r.plan_pr_url == "https://github.com/owner/repo/commit/sha-s"
    assert r.pending_plan_draft is None


def test_on_enter_ready_hook_syncer_recoverable_error_wraps_cleanly():
    """Syncer-raised FeishuSyncerError(recoverable=True) propagates so the
    approve card can retry — mirrors legacy ProjectRepoError behavior."""
    from requirement_workflow_v12.feishu_to_github_syncer import FeishuSyncerError
    svc = CoordinatorService()
    tools = MagicMock()
    syncer = MagicMock()
    syncer.sync_plan.side_effect = FeishuSyncerError(
        "apply conflict", recoverable=True,
    )
    svc.configure_plan_hooks(tools=tools, syncer=syncer)

    from requirement_workflow_v12.project_config import ProjectConfig
    svc.project_configs["P"] = ProjectConfig(
        category="web", template_version="v1",
        architecture_doc_id="", architecture_doc_url="",
        tech_stack={}, github_repo_url="o/r",
    )
    r = _approved_req(svc)
    svc.plan_start(r.req_id, plan_doc_id="docx-1", plan_doc_url="u")
    with pytest.raises(FeishuSyncerError) as exc_info:
        svc.plan_submit(
            r.req_id, plan_md_content="---\n---\n", project_context_change=None,
        )
    assert exc_info.value.recoverable is True


def test_on_enter_ready_hook_propagates_recoverable_error():
    svc = CoordinatorService()
    tools = MagicMock()
    tools.commit_plan_artifacts.side_effect = ProjectRepoError(
        "conflict", recoverable=True,
    )
    svc.configure_plan_hooks(tools=tools)

    from requirement_workflow_v12.project_config import ProjectConfig
    svc.project_configs["P"] = ProjectConfig(
        category="web", template_version="v1",
        architecture_doc_id="", architecture_doc_url="",
        tech_stack={}, github_repo_url="o/r",
    )
    r = _approved_req(svc)
    svc.plan_start(r.req_id)
    with pytest.raises(ProjectRepoError) as exc_info:
        svc.plan_submit(
            r.req_id, plan_md_content="---\n---\n", project_context_change=None,
        )
    assert exc_info.value.recoverable is True


def test_plan_start_requires_design_ready_when_needs_ui_true():
    """needs_ui=True couples Plan to Design readiness (re-enabled 2026-04-22
    when the design flow landed). plan_start must refuse without precondition,
    and succeed once design_precondition_met=True."""
    svc = CoordinatorService()
    r = Requirement(req_id="R-UI", name="n", project="P", summary="s", creator="c")
    r.status = WorkflowStatus.APPROVED
    r.needs_ui = True
    r.design_status = None
    r.design_precondition_met = False
    svc.requirements["R-UI"] = r

    with pytest.raises(ValueError, match="design"):
        svc.plan_start("R-UI")

    # Once design precondition is met, plan_start proceeds.
    r.design_precondition_met = True
    result = svc.plan_start("R-UI")
    assert result.plan_status == PlanStatus.DRAFTING
    assert result.plan_phase == PlanPhase.OUTLINE_PENDING
