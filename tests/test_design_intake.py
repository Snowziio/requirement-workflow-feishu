import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.design_intake import (
    DesignIntake, IntakeResult, IntakeError,
)


FIXTURE_ZIP = Path(__file__).parent / "fixtures" / "design" / "handoff_sample.zip"


def test_intake_extracts_zip_to_archive_dir(tmp_path: Path) -> None:
    archive_root = tmp_path / "design" / "archive"
    archive_root.mkdir(parents=True)
    result = DesignIntake().intake(
        zip_path=FIXTURE_ZIP,
        req_id="REQ-TEST-001",
        slug="report-editor",
        archive_root=archive_root,
    )
    assert isinstance(result, IntakeResult)
    assert result.archive_dir.name == "REQ-TEST-001_report-editor"
    # extracted tree must have at least untitled/README.md
    assert (result.archive_dir / "extracted" / "untitled" / "README.md").exists()
    # original zip preserved
    assert (result.archive_dir / "bundle.zip").exists()


def test_intake_generates_manifest(tmp_path: Path) -> None:
    archive_root = tmp_path / "design" / "archive"
    archive_root.mkdir(parents=True)
    result = DesignIntake().intake(
        zip_path=FIXTURE_ZIP,
        req_id="REQ-TEST-001",
        slug="report-editor",
        archive_root=archive_root,
    )
    manifest = (result.archive_dir / "MANIFEST.md").read_text(encoding="utf-8")
    assert "REQ-TEST-001" in manifest
    assert "export_type:" in manifest
    assert "design_handoff_" in manifest


def test_intake_detects_chinese_filenames(tmp_path: Path) -> None:
    """zip contains Chinese CN file/dir names; intake must preserve them via
    cp437→utf-8 repair."""
    archive_root = tmp_path / "design" / "archive"
    archive_root.mkdir(parents=True)
    result = DesignIntake().intake(
        zip_path=FIXTURE_ZIP,
        req_id="REQ-TEST-001",
        slug="x",
        archive_root=archive_root,
    )
    extracted_files = list((result.archive_dir / "extracted").rglob("*"))
    chinese = [f for f in extracted_files if any("一" <= c <= "鿿" for c in f.name)]
    assert len(chinese) > 0, "Expected some Chinese-named files in the sample zip"


def test_intake_raises_on_corrupt_zip(tmp_path: Path) -> None:
    bad_zip = tmp_path / "bad.zip"
    bad_zip.write_bytes(b"not a zip")
    archive_root = tmp_path / "design" / "archive"
    archive_root.mkdir(parents=True)
    import pytest
    with pytest.raises(IntakeError):
        DesignIntake().intake(
            zip_path=bad_zip, req_id="REQ-TEST-001", slug="x",
            archive_root=archive_root,
        )
