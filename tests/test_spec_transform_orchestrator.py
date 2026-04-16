import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.spec_transform import (
    TransformContextSnapshot, RoundContext, TraceWriter,
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


def test_trace_writer_appends_jsonl(tmp_path):
    writer = TraceWriter(tmp_path)
    writer.append("REQ-P-1", {"event": "transform_started", "round": 0})
    writer.append("REQ-P-1", {"event": "gate_pass", "round": 1})
    file = tmp_path / "REQ-P-1.jsonl"
    lines = file.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["event"] == "transform_started"
    assert json.loads(lines[1])["round"] == 1


def test_trace_writer_truncates_on_reset(tmp_path):
    writer = TraceWriter(tmp_path)
    writer.append("REQ-P-1", {"event": "x"})
    writer.reset("REQ-P-1")
    writer.append("REQ-P-1", {"event": "y"})
    lines = (tmp_path / "REQ-P-1.jsonl").read_text().strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["event"] == "y"


def test_trace_writer_archive_renames_with_suffix(tmp_path):
    writer = TraceWriter(tmp_path)
    writer.append("REQ-P-1", {"event": "x"})
    archived = writer.archive("REQ-P-1", suffix="deadlocked")
    assert archived.exists()
    assert "deadlocked" in archived.name
    assert not (tmp_path / "REQ-P-1.jsonl").exists()


from unittest.mock import MagicMock


def test_on_enter_transforming_captures_snapshot_and_writes_trace(tmp_path):
    gateway = MagicMock()
    gateway.fetch_file_sha = MagicMock(side_effect=[
        ("arch-sha", "ARCHITECTURE: yaml"),
        ("registry-sha", "version: 3\nentries: []"),
    ])
    gateway.create_branch = MagicMock()
    registry = MagicMock()
    registry.parse_active_slice.return_value = ["AC-001", "AC-002"]

    feishu = MagicMock()
    feishu.fetch_document_revision.return_value = "rev-77"

    from requirement_workflow_v12.spec_transform import SpecTransformOrchestrator
    orch = SpecTransformOrchestrator(
        gateway=gateway, registry=registry,
        feishu=feishu, trace_dir=tmp_path,
    )
    snap = orch.on_enter_transforming(
        req_id="REQ-P-1", project_repo="proj-repo",
        spec_doc_id="doc-1",
    )
    assert snap.spec_source_revision == "rev-77"
    assert snap.architecture_revision == "arch-sha"
    assert snap.acm_registry_revision == "registry-sha"
    assert snap.acm_active_slice == ["AC-001", "AC-002"]
    gateway.create_branch.assert_called_once()
    trace = (tmp_path / "REQ-P-1.jsonl").read_text()
    assert '"transform_started"' in trace


def _orch(tmp_path):
    from requirement_workflow_v12.spec_transform import SpecTransformOrchestrator
    return SpecTransformOrchestrator(
        gateway=MagicMock(), registry=MagicMock(), feishu=MagicMock(),
        trace_dir=tmp_path,
    )


def _blank_snap():
    return TransformContextSnapshot(
        req_id="R", spec_source_revision="", architecture_revision="",
        acm_registry_revision="", acm_active_slice=[], captured_at="",
    )


def test_handle_transformer_output_pass_returns_wake_reviewer(tmp_path):
    gateway = MagicMock()
    registry = MagicMock()
    feishu = MagicMock()
    from requirement_workflow_v12.spec_transform import (
        SpecTransformOrchestrator, TransformContextSnapshot, RoundContext,
    )
    orch = SpecTransformOrchestrator(
        gateway=gateway, registry=registry, feishu=feishu, trace_dir=tmp_path,
    )
    snap = TransformContextSnapshot(
        req_id="R", spec_source_revision="", architecture_revision="",
        acm_registry_revision="", acm_active_slice=[], captured_at="",
    )
    orch._rounds["R"] = RoundContext(snapshot=snap)
    payload = {
        "design_md": "## supersedes\nno supersession\n",
        "tasks_md": "T-001 init\n",
        "ac_schedule_yaml": (
            "version: 1\nacs:\n"
            "  - {id: AC-100, title: t, priority: P0, given: g, expected: e, "
            "test_file: harness/tests/R/test_x.py, test_function: test_x}\n"
        ),
        "harness_files": {
            "harness/tests/R/test_x.py":
                "import pytest\n@pytest.mark.ac('AC-100')\ndef test_x(): pass\n",
        },
        "supersedes_decl": [],
        "round_zero_ac_ids": [],
    }
    action = orch.handle_transformer_output("R", payload)
    assert action == "wake_reviewer"
    trace = (tmp_path / "R.jsonl").read_text()
    assert "gate_pass" in trace


def test_handle_transformer_output_format_fail_soft_retry(tmp_path):
    orch = _orch(tmp_path)
    orch._rounds["R"] = RoundContext(snapshot=_blank_snap())
    bad_payload = {
        "design_md": "", "tasks_md": "T-001 a\n",
        "ac_schedule_yaml": "version: 1\nacs:\n  - id: AC-100\n",
        "harness_files": {}, "supersedes_decl": [], "round_zero_ac_ids": [],
    }
    action1 = orch.handle_transformer_output("R", bad_payload)
    assert action1 == "soft_retry_transformer"
    assert orch._rounds["R"].soft_retry_count == 1


def test_handle_reviewer_verdict_converged_returns_converged(tmp_path):
    orch = _orch(tmp_path)
    orch._rounds["R"] = RoundContext(snapshot=_blank_snap())
    orch._on_converged = MagicMock()
    action = orch.handle_reviewer_verdict("R", "converged", [])
    assert action == "converged"
    orch._on_converged.assert_called_once_with("R")


def test_handle_reviewer_verdict_reject_consumes_round(tmp_path):
    orch = _orch(tmp_path)
    orch._rounds["R"] = RoundContext(snapshot=_blank_snap())
    findings = [{"dimension": "completeness", "severity": "blocking", "detail": "x"}]
    action = orch.handle_reviewer_verdict("R", "reject", findings)
    assert action == "wake_transformer_next_round"
    assert orch._rounds["R"].round_index == 2
    assert orch._rounds["R"].last_reviewer_findings == findings


def test_handle_reviewer_verdict_reject_at_max_rounds_deadlocks(tmp_path):
    orch = _orch(tmp_path)
    ctx = RoundContext(snapshot=_blank_snap())
    ctx.round_index = 3
    orch._rounds["R"] = ctx
    action = orch.handle_reviewer_verdict("R", "reject", [])
    assert action == "deadlock"


def test_handle_transformer_output_without_round_context_deadlocks(tmp_path):
    orch = _orch(tmp_path)
    action = orch.handle_transformer_output("R", {})
    assert action == "deadlock"
    trace = (tmp_path / "R.jsonl").read_text()
    assert "recovery_deadlock" in trace


def test_handle_reviewer_verdict_without_round_context_deadlocks(tmp_path):
    orch = _orch(tmp_path)
    action = orch.handle_reviewer_verdict("R", "converged", [])
    assert action == "deadlock"
