import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.models import Requirement


def _make_req() -> Requirement:
    return Requirement(
        req_id="REQ-X-001", name="n", project="X", summary="s", creator="c",
    )


def test_design_doc_fields_default_empty():
    r = _make_req()
    assert r.design_doc_id == ""
    assert r.design_doc_url == ""


def test_design_archive_fields_default_empty():
    r = _make_req()
    assert r.design_archive_path == ""
    assert r.design_github_revision == ""


def test_design_precondition_met_defaults_false():
    r = _make_req()
    assert r.design_precondition_met is False


def test_pending_design_brief_defaults_none():
    r = _make_req()
    assert r.pending_design_brief is None


def test_pending_design_handoff_defaults_none():
    r = _make_req()
    assert r.pending_design_handoff is None
