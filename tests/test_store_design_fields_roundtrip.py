"""Regression: design_* fields must round-trip through JsonStateStore.

Same bug class as test_store_plan_fields_roundtrip — the loader in
JsonStateStore must read each design_* field back off the on-disk payload.
asdict() picks these up automatically on save, but _requirement_from_payload
must explicitly deserialize them or they silently default.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.models import Requirement, WorkflowStatus
from requirement_workflow_v12.plan_state_machine import DesignStatus
from requirement_workflow_v12.store import JsonStateStore


def test_design_fields_roundtrip(tmp_path: Path) -> None:
    store = JsonStateStore(str(tmp_path / "state.json"))
    r = Requirement(
        req_id="REQ-X-001",
        name="n",
        project="X",
        summary="s",
        creator="c",
        design_status=DesignStatus.SUBMIT_PENDING_REVIEW,
        design_doc_id="doc-id-1",
        design_doc_url="https://feishu/d/1",
        design_archive_path="design/archive/REQ-X-001_foo/",
        design_github_revision="abc1234",
        design_precondition_met=True,
        pending_design_brief={"brief_yaml_frontmatter": "a"},
        pending_design_handoff={"manifest_summary": "b"},
    )
    store.save_snapshot({r.req_id: r}, {}, {})

    store2 = JsonStateStore(str(tmp_path / "state.json"))
    reqs, _, _, _ = store2.load_snapshot()
    loaded = reqs["REQ-X-001"]

    assert loaded.design_status is DesignStatus.SUBMIT_PENDING_REVIEW
    assert loaded.design_doc_id == "doc-id-1"
    assert loaded.design_doc_url == "https://feishu/d/1"
    assert loaded.design_archive_path == "design/archive/REQ-X-001_foo/"
    assert loaded.design_github_revision == "abc1234"
    assert loaded.design_precondition_met is True
    assert loaded.pending_design_brief == {"brief_yaml_frontmatter": "a"}
    assert loaded.pending_design_handoff == {"manifest_summary": "b"}


def test_missing_design_fields_load_as_defaults(tmp_path: Path) -> None:
    """Old snapshots lack new fields; loader must tolerate and default."""
    path = tmp_path / "state.json"
    # Hand-craft a legacy-shaped payload with no design_* fields set.
    path.write_text(
        json.dumps(
            {
                "requirements": {
                    "OLD-001": {
                        "req_id": "OLD-001",
                        "name": "n",
                        "project": "X",
                        "summary": "s",
                        "creator": "c",
                        "status": WorkflowStatus.CREATED.value,
                    }
                },
                "active_req_by_user": {},
                "project_groups": {},
            }
        )
    )

    reqs, _, _, _ = JsonStateStore(str(path)).load_snapshot()
    loaded = reqs["OLD-001"]

    assert loaded.design_status is None
    assert loaded.design_doc_id == ""
    assert loaded.design_doc_url == ""
    assert loaded.design_archive_path == ""
    assert loaded.design_github_revision == ""
    assert loaded.design_precondition_met is False
    assert loaded.pending_design_brief is None
    assert loaded.pending_design_handoff is None
