import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.spec_transform import (
    TransformContextSnapshot, RoundContext,
)


def test_transform_context_snapshot_fields():
    snap = TransformContextSnapshot(
        req_id="REQ-P-1",
        spec_source_revision="rev-1",
        architecture_revision="abc123",
        acm_registry_revision="def456",
        acm_active_slice=["AC-001", "AC-002"],
        captured_at="2026-04-16T00:00:00Z",
    )
    assert snap.req_id == "REQ-P-1"
    assert snap.acm_active_slice == ["AC-001", "AC-002"]


def test_round_context_starts_at_round_one_with_zero_retries():
    snap = TransformContextSnapshot(
        req_id="R", spec_source_revision="", architecture_revision="",
        acm_registry_revision="", acm_active_slice=[], captured_at="",
    )
    ctx = RoundContext(snapshot=snap)
    assert ctx.round_index == 1
    assert ctx.soft_retry_count == 0
    assert ctx.race_retry_count == 0
