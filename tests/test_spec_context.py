import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.models import Requirement, WorkflowStatus
from requirement_workflow_v12.store import JsonStateStore


def test_requirement_has_spec_context_fields():
    req = Requirement(req_id="REQ-T-001", name="t", project="P", summary="s", creator="c")
    assert req.active_spec_context_token == ""
    assert req.spec_context_snapshot_revision == ""


def test_store_round_trips_spec_context_fields():
    req = Requirement(req_id="REQ-T-002", name="t", project="P", summary="s", creator="c")
    req.active_spec_context_token = "spec_ctx_REQ-T-002_1700000000_abcd"
    req.spec_context_snapshot_revision = "rev-20260415-001"

    with tempfile.TemporaryDirectory() as tmpdir:
        store = JsonStateStore(f"{tmpdir}/state.json")
        store.save_snapshot({"REQ-T-002": req}, {}, {})
        reqs, _, _, _ = store.load_snapshot()
        loaded = reqs["REQ-T-002"]
        assert loaded.active_spec_context_token == "spec_ctx_REQ-T-002_1700000000_abcd"
        assert loaded.spec_context_snapshot_revision == "rev-20260415-001"


def test_store_reads_legacy_snapshot_without_spec_context_fields():
    import json
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "state.json"
        path.write_text(json.dumps({
            "requirements": {
                "REQ-LEGACY-001": {
                    "req_id": "REQ-LEGACY-001",
                    "name": "legacy",
                    "project": "L",
                    "summary": "s",
                    "creator": "c",
                    "status": "APPROVED",
                    "spec_context_snapshot_sha": "deadbeef",
                    "github_repo_url": "https://github.com/org/legacy",
                }
            },
            "active_req_by_user": {},
            "project_groups": {},
            "project_configs": {},
        }, ensure_ascii=False))
        store = JsonStateStore(str(path))
        reqs, _, _, _ = store.load_snapshot()
        loaded = reqs["REQ-LEGACY-001"]
        assert loaded.active_spec_context_token == ""
        assert loaded.spec_context_snapshot_revision == ""
        assert not hasattr(loaded, "github_repo_url")
        assert not hasattr(loaded, "spec_context_snapshot_sha")
