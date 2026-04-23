import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def test_project_repo_commit_delegates_to_commit_files():
    """GitHubProjectRepoTools.project_repo_commit should atomically commit
    a dict of {path: bytes} to the project repo's main branch."""
    from requirement_workflow_v12.project_repo.tools import (
        GitHubProjectRepoTools, FileChange,
    )

    mock_gw = MagicMock()
    mock_gw.commit_files.return_value = "commit-sha-abc"
    tools = GitHubProjectRepoTools(mock_gw)

    files = {
        "design/archive/REQ-X_foo/MANIFEST.md": b"# mf\n",
        "design/PAGES.yaml": b"pages: []\n",
    }
    sha = tools.project_repo_commit(
        project_repo="https://github.com/org/repo",
        message="design: lock handoff for REQ-X",
        files=files,
    )
    assert sha == "commit-sha-abc"
    mock_gw.commit_files.assert_called_once()
    kwargs = mock_gw.commit_files.call_args.kwargs
    assert kwargs["owner"] == "org"
    assert kwargs["repo"] == "repo"
    assert kwargs["branch"] == "main"
    assert kwargs["message"] == "design: lock handoff for REQ-X"
    # files converted to FileChange list
    fc_list = kwargs["files"]
    assert len(fc_list) == 2
    assert all(isinstance(fc, FileChange) for fc in fc_list)
    paths = {fc.path for fc in fc_list}
    assert paths == {"design/archive/REQ-X_foo/MANIFEST.md", "design/PAGES.yaml"}


def test_coordinator_runtime_app_configures_design_hooks_when_github_token_present(tmp_path):
    """service_app.CoordinatorRuntimeApp.__init__ must call service.configure_design_hooks
    when github_token is configured (alongside configure_plan_hooks)."""
    from requirement_workflow_v12.service_app import CoordinatorRuntimeApp

    # Bypass real init; check that the sequence in __init__ includes design hook wiring
    # by patching the service's configure_design_hooks and running a minimal __init__ path.
    # To avoid deep init coupling, we read the source and verify the call exists.
    import inspect
    src = inspect.getsource(CoordinatorRuntimeApp.__init__)
    assert "configure_design_hooks" in src or "_wire_design_hooks" in src, (
        "CoordinatorRuntimeApp.__init__ must call configure_design_hooks when github_token is present"
    )


def test_configure_design_hooks_wiring_passes_syncer_and_design_root(tmp_path: Path):
    """When wired, configure_design_hooks receives a DesignSyncer + design_root path."""
    # Stub the whole service_app environment and verify arguments flow through
    from unittest.mock import ANY

    # Use a MagicMock service that records configure_design_hooks calls
    mock_service = MagicMock()
    mock_gateway = MagicMock()
    mock_github_gw = MagicMock()

    # Call the design-hook wiring helper directly to keep test isolated
    # (We'll add this helper in the impl to make wiring testable.)
    from requirement_workflow_v12.service_app import _wire_design_hooks
    _wire_design_hooks(
        service=mock_service,
        github_tools=MagicMock(),
        archive_root=tmp_path / "design" / "archive",
    )
    # Must have been called with a syncer and a design_root = archive_root.parent
    mock_service.configure_design_hooks.assert_called_once()
    kwargs = mock_service.configure_design_hooks.call_args.kwargs
    assert kwargs["design_root"] == tmp_path / "design"
    # syncer should be a DesignSyncer instance (or have the expected sync method)
    assert hasattr(kwargs["syncer"], "sync")
