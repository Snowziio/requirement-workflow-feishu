import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.models import Requirement


def test_pending_plan_review_defaults_to_none():
    r = Requirement(req_id="R1", name="n", project="P", summary="s", creator="c")
    assert r.pending_plan_review is None


def test_pending_plan_review_is_independent_of_pending_plan_draft():
    r = Requirement(req_id="R1", name="n", project="P", summary="s", creator="c")
    r.pending_plan_draft = {"plan_md_content": "x"}
    r.pending_plan_review = {"plan_md_content": "y", "project_context_change": None}
    assert r.pending_plan_draft["plan_md_content"] == "x"
    assert r.pending_plan_review["plan_md_content"] == "y"
