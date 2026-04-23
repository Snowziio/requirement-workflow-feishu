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
