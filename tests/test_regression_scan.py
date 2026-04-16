import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.regression_scan import scan, RegressionResult
from requirement_workflow_v12.acm_registry import SupersedeDecl


def test_scan_passes_when_active_anchored_in_harness():
    result = scan(
        active_ids=["AC-001"],
        supersedes_decl=[],
        harness_files={
            "harness/tests/x.py":
                "import pytest\n@pytest.mark.ac('AC-001')\ndef test(): pass\n",
        },
    )
    assert result.passed is True


def test_scan_passes_when_active_is_superseded():
    result = scan(
        active_ids=["AC-001"],
        supersedes_decl=[SupersedeDecl("AC-001", "AC-100")],
        harness_files={},
    )
    assert result.passed is True


def test_scan_fails_when_active_not_anchored_and_not_superseded():
    result = scan(
        active_ids=["AC-001", "AC-002"],
        supersedes_decl=[SupersedeDecl("AC-002", "AC-200")],
        harness_files={},
    )
    assert result.passed is False
    assert result.missing == ["AC-001"]
