import sys
from pathlib import Path
from unittest.mock import MagicMock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.models import Requirement, WorkflowStatus
from requirement_workflow_v12.plan_state_machine import DesignStatus
from requirement_workflow_v12.coordinator_service import CoordinatorService


def _svc() -> CoordinatorService:
    svc = CoordinatorService.__new__(CoordinatorService)
    svc.requirements = {}
    svc.project_configs = {}
    from requirement_workflow_v12.project_repo import StateTransitionHooks
    svc._hooks = StateTransitionHooks()
    return svc


def test_configure_design_hooks_registers_on_enter_ready(tmp_path: Path):
    svc = _svc()
    syncer = MagicMock()
    design_root = tmp_path / "design"
    design_root.mkdir()

    svc.configure_design_hooks(syncer=syncer, design_root=design_root)

    # Verify _design_syncer and _design_root stored
    assert svc._design_syncer is syncer
    assert svc._design_root == design_root


def test_on_enter_ready_invokes_syncer_with_correct_args(tmp_path: Path):
    svc = _svc()
    # Make ProjectConfig resolvable for _project_repo_for
    from unittest.mock import MagicMock as _MM
    cfg = _MM()
    cfg.github_repo_url = "https://github.com/org/myrepo"
    svc.project_configs = {"X": cfg}

    syncer = MagicMock()
    syncer.sync.return_value = MagicMock(commit_sha="c-abc")

    design_root = tmp_path / "design"
    (design_root / "archive" / "REQ-X-001_foo").mkdir(parents=True)
    (design_root / "PAGES.yaml").write_text("schema_version: '1.0'\npages: []\n")
    (design_root / "INDEX.md").write_text("# Design Handoff Index\n")

    svc.configure_design_hooks(syncer=syncer, design_root=design_root)

    r = Requirement(
        req_id="REQ-X-001", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
        design_status=DesignStatus.READY,
        design_archive_path="design/archive/REQ-X-001_foo/",
        pending_design_handoff={
            "archive_path": "design/archive/REQ-X-001_foo/",
            "pages_touched": [{"display_name": "Upload", "action": "new"}],
            "submitted_at": "t",
        },
    )
    svc.requirements[r.req_id] = r

    # Fire the on_enter hook manually
    svc._hooks.fire_enter(DesignStatus.READY, r)

    syncer.sync.assert_called_once()
    kwargs = syncer.sync.call_args.kwargs
    assert kwargs["req_id"] == "REQ-X-001"
    assert kwargs["slug"] == "foo"
    assert kwargs["project_repo"] == "https://github.com/org/myrepo"
    assert kwargs["pages_touched"] == [{"display_name": "Upload", "action": "new"}]
    # commit_sha propagated to requirement
    assert r.design_github_revision == "c-abc"


def test_configure_design_hooks_is_idempotent(tmp_path: Path):
    svc = _svc()
    syncer1 = MagicMock()
    syncer2 = MagicMock()
    design_root = tmp_path / "design"
    design_root.mkdir()

    svc.configure_design_hooks(syncer=syncer1, design_root=design_root)
    svc.configure_design_hooks(syncer=syncer2, design_root=design_root)

    # Second call should update the syncer reference, not register duplicate hooks
    assert svc._design_syncer is syncer2


def test_on_enter_ready_without_pending_handoff_uses_empty_pages(tmp_path: Path):
    """If pending_design_handoff is None (edge case), pages_touched defaults to []."""
    svc = _svc()
    cfg = MagicMock()
    cfg.github_repo_url = "https://github.com/org/myrepo"
    svc.project_configs = {"X": cfg}

    syncer = MagicMock()
    syncer.sync.return_value = MagicMock(commit_sha="c")
    design_root = tmp_path / "design"
    (design_root / "archive" / "REQ-X-002_bar").mkdir(parents=True)
    (design_root / "PAGES.yaml").write_text("pages: []\n")
    (design_root / "INDEX.md").write_text("# Design Handoff Index\n")

    svc.configure_design_hooks(syncer=syncer, design_root=design_root)

    r = Requirement(
        req_id="REQ-X-002", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
        design_status=DesignStatus.READY,
        design_archive_path="design/archive/REQ-X-002_bar/",
        pending_design_handoff=None,
    )
    svc.requirements[r.req_id] = r
    svc._hooks.fire_enter(DesignStatus.READY, r)
    syncer.sync.assert_called_once()
    assert syncer.sync.call_args.kwargs["pages_touched"] == []
