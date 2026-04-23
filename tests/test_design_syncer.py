import sys
from pathlib import Path
from unittest.mock import MagicMock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.design_syncer import (
    DesignSyncer, DesignSyncResult, DesignSyncError,
)


def _mk_archive_dir(tmp: Path, req_id: str, slug: str) -> Path:
    d = tmp / "design" / "archive" / f"{req_id}_{slug}"
    d.mkdir(parents=True)
    (d / "MANIFEST.md").write_text("# mf\n", encoding="utf-8")
    (d / "BRIEF.md").write_text("# bf\n", encoding="utf-8")
    (d / "bundle.zip").write_bytes(b"zipbytes")
    ex = d / "extracted"
    ex.mkdir()
    (ex / "README.md").write_text("readme\n", encoding="utf-8")
    return d


def test_sync_commits_archive_and_updates_registry(tmp_path: Path) -> None:
    archive = _mk_archive_dir(tmp_path, "REQ-X-001", "foo")
    registry = tmp_path / "design" / "PAGES.yaml"
    registry.write_text("schema_version: '1.0'\npages: []\n", encoding="utf-8")
    index = tmp_path / "design" / "INDEX.md"
    index.write_text("# Design Handoff Index\n", encoding="utf-8")

    gateway = MagicMock()
    gateway.project_repo_commit.return_value = "commit-sha-abc"

    result = DesignSyncer(gateway).sync(
        project_repo="org/repo",
        req_id="REQ-X-001",
        slug="foo",
        archive_dir=archive,
        pages_registry_path=registry,
        index_path=index,
        pages_touched=[
            {"display_name": "Dashboard", "action": "modify"},
            {"display_name": "ProfileUpload", "action": "new"},
        ],
    )
    assert isinstance(result, DesignSyncResult)
    assert result.commit_sha == "commit-sha-abc"
    gateway.project_repo_commit.assert_called_once()
    _, kwargs = gateway.project_repo_commit.call_args
    files = kwargs["files"]
    assert any("design/archive/REQ-X-001_foo/MANIFEST.md" in f for f in files)
    assert "design/PAGES.yaml" in files
    assert "design/INDEX.md" in files


def test_sync_updates_registry_new_page_entry(tmp_path: Path) -> None:
    archive = _mk_archive_dir(tmp_path, "REQ-X-002", "bar")
    registry = tmp_path / "design" / "PAGES.yaml"
    registry.write_text("schema_version: '1.0'\npages: []\n", encoding="utf-8")
    index = tmp_path / "design" / "INDEX.md"
    index.write_text("# Design Handoff Index\n", encoding="utf-8")

    gateway = MagicMock()
    gateway.project_repo_commit.return_value = "c"

    DesignSyncer(gateway).sync(
        project_repo="org/repo", req_id="REQ-X-002", slug="bar",
        archive_dir=archive, pages_registry_path=registry, index_path=index,
        pages_touched=[{"display_name": "Upload", "action": "new"}],
    )
    new_reg = registry.read_text(encoding="utf-8")
    assert "Upload" in new_reg
    assert "REQ-X-002" in new_reg


def test_sync_updates_index_prepends_entry(tmp_path: Path) -> None:
    archive = _mk_archive_dir(tmp_path, "REQ-X-003", "baz")
    registry = tmp_path / "design" / "PAGES.yaml"
    registry.write_text("schema_version: '1.0'\npages: []\n", encoding="utf-8")
    index = tmp_path / "design" / "INDEX.md"
    index.write_text("# Design Handoff Index\n\n## 2026-04-20 prior\n", encoding="utf-8")

    gateway = MagicMock()
    gateway.project_repo_commit.return_value = "c"

    DesignSyncer(gateway).sync(
        project_repo="org/repo", req_id="REQ-X-003", slug="baz",
        archive_dir=archive, pages_registry_path=registry, index_path=index,
        pages_touched=[{"display_name": "X", "action": "new"}],
    )
    new_idx = index.read_text(encoding="utf-8")
    assert new_idx.index("REQ-X-003") < new_idx.index("2026-04-20 prior")


def test_sync_raises_when_gateway_fails(tmp_path: Path) -> None:
    archive = _mk_archive_dir(tmp_path, "REQ-X-004", "qux")
    registry = tmp_path / "design" / "PAGES.yaml"
    registry.write_text("schema_version: '1.0'\npages: []\n", encoding="utf-8")
    index = tmp_path / "design" / "INDEX.md"
    index.write_text("# Design Handoff Index\n", encoding="utf-8")

    gateway = MagicMock()
    gateway.project_repo_commit.side_effect = RuntimeError("gh 500")

    import pytest
    with pytest.raises(DesignSyncError):
        DesignSyncer(gateway).sync(
            project_repo="org/repo", req_id="REQ-X-004", slug="qux",
            archive_dir=archive, pages_registry_path=registry, index_path=index,
            pages_touched=[],
        )


def test_sync_hydrates_missing_registry_from_github(tmp_path: Path) -> None:
    """On a fresh coordinator container, PAGES.yaml + INDEX.md don't exist
    locally — they were only written to the GitHub repo by Bootstrap. The
    syncer must pull them from GitHub before appending the new entry.

    Before the fix: FileNotFoundError raised in _update_pages_registry.
    """
    archive = _mk_archive_dir(tmp_path, "REQ-X-005", "fresh")
    registry = tmp_path / "design" / "PAGES.yaml"  # does NOT exist
    index = tmp_path / "design" / "INDEX.md"       # does NOT exist
    assert not registry.exists()
    assert not index.exists()

    gateway = MagicMock()
    # GitHub returns the Bootstrap-written initial content
    def fake_read(project_repo, path, *, branch="main", default=None):
        if path == "design/PAGES.yaml":
            return 'schema_version: "1.0"\npages: []\n'
        if path == "design/INDEX.md":
            return "# Design Handoff Index\n\n<!-- ... -->\n"
        raise AssertionError(f"unexpected read: {path}")
    gateway.read_project_file.side_effect = fake_read
    gateway.project_repo_commit.return_value = "commit-sha-fresh"

    result = DesignSyncer(gateway).sync(
        project_repo="org/repo", req_id="REQ-X-005", slug="fresh",
        archive_dir=archive, pages_registry_path=registry, index_path=index,
        pages_touched=[{"display_name": "NewPage", "action": "new"}],
    )
    assert result.commit_sha == "commit-sha-fresh"
    # Both files should now exist locally (hydrated + then appended)
    assert registry.exists()
    assert index.exists()
    # Registry must have the new page appended
    import yaml
    doc = yaml.safe_load(registry.read_text())
    names = [p["display_name"] for p in doc["pages"]]
    assert "NewPage" in names
    # Index must have the new entry
    assert "REQ-X-005" in index.read_text()
    # The gateway read_project_file was called for both paths
    assert gateway.read_project_file.call_count == 2


def test_sync_falls_back_to_default_when_registry_missing_on_remote(tmp_path: Path) -> None:
    """If GitHub genuinely has no PAGES.yaml/INDEX.md (unusual — Bootstrap
    writes them), the syncer should fall back to empty defaults rather than
    crash. Defensive behavior.
    """
    archive = _mk_archive_dir(tmp_path, "REQ-X-006", "noremote")
    registry = tmp_path / "design" / "PAGES.yaml"
    index = tmp_path / "design" / "INDEX.md"

    gateway = MagicMock()
    # Simulate: read_project_file honors the default= kwarg on remote-404
    def fake_read(project_repo, path, *, branch="main", default=None):
        return default  # pretend remote returned 404; method falls back
    gateway.read_project_file.side_effect = fake_read
    gateway.project_repo_commit.return_value = "commit-sha-default"

    result = DesignSyncer(gateway).sync(
        project_repo="org/repo", req_id="REQ-X-006", slug="noremote",
        archive_dir=archive, pages_registry_path=registry, index_path=index,
        pages_touched=[],
    )
    assert result.commit_sha == "commit-sha-default"
    assert registry.exists()
    assert index.exists()


def test_sync_raises_when_archive_dir_missing(tmp_path: Path) -> None:
    """Observed 2026-04-24: coordinator container was redeployed between
    SUBMIT_PENDING_REVIEW and READY. /app/design/archive/<REQ>/ (not in a
    volume) was wiped. On approve, rglob returned 0 files silently and the
    syncer committed only PAGES.yaml + INDEX.md — a hollow 'design lock'
    commit with no artifacts. Must raise instead.
    """
    registry = tmp_path / "design" / "PAGES.yaml"
    registry.parent.mkdir(parents=True)
    registry.write_text("schema_version: '1.0'\npages: []\n", encoding="utf-8")
    index = tmp_path / "design" / "INDEX.md"
    index.write_text("# Design Handoff Index\n", encoding="utf-8")

    missing_archive = tmp_path / "design" / "archive" / "REQ-X-008_missing"
    # DO NOT mkdir the archive dir
    assert not missing_archive.exists()

    gateway = MagicMock()
    gateway.project_repo_commit.return_value = "should-not-happen"

    import pytest
    with pytest.raises(DesignSyncError, match="archive_dir does not exist"):
        DesignSyncer(gateway).sync(
            project_repo="org/repo", req_id="REQ-X-008", slug="missing",
            archive_dir=missing_archive,
            pages_registry_path=registry, index_path=index,
            pages_touched=[{"display_name": "Dashboard", "action": "new"}],
        )
    gateway.project_repo_commit.assert_not_called()


def test_sync_raises_when_archive_dir_empty(tmp_path: Path) -> None:
    """Defensive: if archive_dir exists but contains no files (empty dir or
    only nested empty subdirs), bail rather than commit a 2-file hollow."""
    registry = tmp_path / "design" / "PAGES.yaml"
    registry.parent.mkdir(parents=True)
    registry.write_text("schema_version: '1.0'\npages: []\n", encoding="utf-8")
    index = tmp_path / "design" / "INDEX.md"
    index.write_text("# Design Handoff Index\n", encoding="utf-8")

    empty_archive = tmp_path / "design" / "archive" / "REQ-X-009_empty"
    empty_archive.mkdir(parents=True)
    # No files in archive_dir

    gateway = MagicMock()
    gateway.project_repo_commit.return_value = "should-not-happen"

    import pytest
    with pytest.raises(DesignSyncError, match="archive_dir is empty"):
        DesignSyncer(gateway).sync(
            project_repo="org/repo", req_id="REQ-X-009", slug="empty",
            archive_dir=empty_archive,
            pages_registry_path=registry, index_path=index,
            pages_touched=[],
        )
    gateway.project_repo_commit.assert_not_called()


def test_sync_skips_hydrate_when_local_files_already_exist(tmp_path: Path) -> None:
    """If local files exist (subsequent READY syncs within same container
    lifetime), don't re-fetch from GitHub — respect the local cache.
    """
    archive = _mk_archive_dir(tmp_path, "REQ-X-007", "cached")
    registry = tmp_path / "design" / "PAGES.yaml"
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text("schema_version: '1.0'\npages:\n  - display_name: Existing\n", encoding="utf-8")
    index = tmp_path / "design" / "INDEX.md"
    index.write_text("# Design Handoff Index\n", encoding="utf-8")

    gateway = MagicMock()
    gateway.project_repo_commit.return_value = "commit-sha-cached"

    DesignSyncer(gateway).sync(
        project_repo="org/repo", req_id="REQ-X-007", slug="cached",
        archive_dir=archive, pages_registry_path=registry, index_path=index,
        pages_touched=[{"display_name": "Dashboard", "action": "new"}],
    )
    # Must not have called read_project_file — local files sufficed
    gateway.read_project_file.assert_not_called()
