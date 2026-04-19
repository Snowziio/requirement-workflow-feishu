import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.project_repo import GitHubProjectRepoTools
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
    registry = MagicMock()
    registry.parse_active_slice.return_value = ["AC-001", "AC-002"]

    feishu = MagicMock()
    feishu.fetch_document_revision.return_value = "rev-77"

    from requirement_workflow_v12.spec_transform import SpecTransformOrchestrator
    orch = SpecTransformOrchestrator(
        tools=GitHubProjectRepoTools(gateway), registry=registry,
        feishu=feishu, trace_dir=tmp_path,
    )
    snap = orch.on_enter_transforming(
        req_id="REQ-P-1", project_repo="owner/proj-repo",
        spec_doc_id="doc-1",
    )
    assert snap.spec_source_revision == "rev-77"
    assert snap.architecture_revision == "arch-sha"
    assert snap.acm_registry_revision == "registry-sha"
    assert snap.acm_active_slice == ["AC-001", "AC-002"]
    trace = (tmp_path / "REQ-P-1.jsonl").read_text()
    assert '"transform_started"' in trace


def test_archive_trace_returns_path_and_drops_round_context(tmp_path):
    from requirement_workflow_v12.spec_transform import SpecTransformOrchestrator
    orch = SpecTransformOrchestrator(
        tools=GitHubProjectRepoTools(MagicMock()), registry=MagicMock(), feishu=MagicMock(),
        trace_dir=tmp_path,
    )
    # Pre-existing trace + in-memory ctx (simulates a deadlocked session)
    orch._trace.append("REQ-X", {"event": "transform_started"})
    orch._rounds["REQ-X"] = RoundContext(snapshot=TransformContextSnapshot(
        req_id="REQ-X", spec_source_revision="", architecture_revision="",
        acm_registry_revision="", acm_active_slice=[], captured_at="",
    ))
    archived = orch.archive_trace("REQ-X", suffix="restart")
    assert archived is not None
    assert archived.exists()
    assert "restart" in archived.name
    assert not (tmp_path / "REQ-X.jsonl").exists()
    assert "REQ-X" not in orch._rounds


def test_archive_trace_returns_none_when_no_trace(tmp_path):
    from requirement_workflow_v12.spec_transform import SpecTransformOrchestrator
    orch = SpecTransformOrchestrator(
        tools=GitHubProjectRepoTools(MagicMock()), registry=MagicMock(), feishu=MagicMock(),
        trace_dir=tmp_path,
    )
    assert orch.archive_trace("REQ-NONE", suffix="restart") is None


def _orch(tmp_path):
    from requirement_workflow_v12.spec_transform import SpecTransformOrchestrator
    return SpecTransformOrchestrator(
        tools=GitHubProjectRepoTools(MagicMock()), registry=MagicMock(), feishu=MagicMock(),
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
        tools=GitHubProjectRepoTools(gateway), registry=registry, feishu=feishu, trace_dir=tmp_path,
    )
    snap = TransformContextSnapshot(
        req_id="R", spec_source_revision="", architecture_revision="",
        acm_registry_revision="", acm_active_slice=[], captured_at="",
    )
    orch._rounds["R"] = RoundContext(snapshot=snap)
    payload = {
        "design_md": (
            "# Design\n## 项目级上下文消费\n- ARCHITECTURE rev: x\n"
            "## supersedes\nno supersession\n"
        ),
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
    assert action == "wake_reviewer", orch._trace.read_all("R")
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


def test_deadlock_callback_invoked(tmp_path):
    from requirement_workflow_v12.spec_transform import SpecTransformOrchestrator
    called = []
    orch = SpecTransformOrchestrator(
        tools=GitHubProjectRepoTools(MagicMock()), registry=MagicMock(), feishu=MagicMock(),
        trace_dir=tmp_path,
        on_deadlock=lambda req, reason: called.append((req, reason)),
    )
    ctx = RoundContext(snapshot=_blank_snap())
    ctx.round_index = 3
    orch._rounds["R"] = ctx
    action = orch.handle_reviewer_verdict("R", "reject", [])
    assert action == "deadlock"
    assert called == [("R", "max_rounds")]


def test_recovery_deadlock_callback_invoked(tmp_path):
    from requirement_workflow_v12.spec_transform import SpecTransformOrchestrator
    called = []
    orch = SpecTransformOrchestrator(
        tools=GitHubProjectRepoTools(MagicMock()), registry=MagicMock(), feishu=MagicMock(),
        trace_dir=tmp_path,
        on_deadlock=lambda req, reason: called.append((req, reason)),
    )
    action = orch.handle_transformer_output("R", {})
    assert action == "deadlock"
    assert called == [("R", "recovery")]


def test_on_converged_commits_pr_and_locks(tmp_path):
    from requirement_workflow_v12.acm_registry import AcmRegistry
    from requirement_workflow_v12.spec_transform import SpecTransformOrchestrator
    gateway = MagicMock()
    gateway.fetch_file_sha = MagicMock(return_value=(
        "registry-sha-1",
        "version: 3\nentries:\n  - {ac_id: AC-1, req_id: R, status: active, priority: P0}\n",
    ))
    gateway.commit_spec_pr_files = MagicMock(return_value="commit-sha")
    gateway.open_pull_request = MagicMock(
        return_value={"number": 1, "html_url": "https://gh/pr/1"},
    )
    registry = AcmRegistry(gateway=gateway)
    feishu = MagicMock()

    orch = SpecTransformOrchestrator(
        tools=GitHubProjectRepoTools(gateway), registry=registry, feishu=feishu, trace_dir=tmp_path,
    )
    snap = TransformContextSnapshot(
        req_id="REQ-P-1", spec_source_revision="r",
        architecture_revision="a", acm_registry_revision="registry-sha-1",
        acm_active_slice=["AC-1"], captured_at="2026-04-16",
    )
    ctx = RoundContext(snapshot=snap)
    ctx.last_transformer_payload = {
        "design_md": "## supersedes\nno supersession\n",
        "tasks_md": "T-001 init\n",
        "ac_schedule_yaml": (
            "version: 1\nacs:\n"
            "  - {id: AC-100, title: t, priority: P0, given: g, expected: e, "
            "test_file: harness/tests/REQ-P-1/test_x.py, test_function: test_x}\n"
        ),
        "harness_files": {
            "harness/tests/REQ-P-1/test_x.py":
                "import pytest\n@pytest.mark.ac('AC-1')\ndef test(): pass\n"
                "@pytest.mark.ac('AC-100')\ndef test2(): pass\n",
        },
        "supersedes_decl": [],
        "round_zero_ac_ids": ["AC-1"],
    }
    orch._rounds["REQ-P-1"] = ctx
    orch._project_repo_for = lambda req_id: "o/r"

    orch._on_converged("REQ-P-1")

    gateway.commit_spec_pr_files.assert_called_once()
    gateway.open_pull_request.assert_called_once()
    trace = (tmp_path / "REQ-P-1.jsonl").read_text()
    assert '"locked"' in trace


def _make_regression_fail_orch(tmp_path, **orch_kwargs):
    """Helper: orch where regression scan fails (AC-1 active but not anchored)."""
    from requirement_workflow_v12.acm_registry import AcmRegistry
    from requirement_workflow_v12.spec_transform import SpecTransformOrchestrator
    gateway = MagicMock()
    gateway.fetch_file_sha = MagicMock(return_value=(
        "sha-1",
        "version: 3\nentries:\n  - {ac_id: AC-1, req_id: R, status: active, priority: P0}\n",
    ))
    registry = AcmRegistry(gateway=gateway)
    orch = SpecTransformOrchestrator(
        tools=GitHubProjectRepoTools(gateway), registry=registry, feishu=MagicMock(),
        trace_dir=tmp_path, **orch_kwargs,
    )
    snap = TransformContextSnapshot(
        req_id="REQ-P-1", spec_source_revision="",
        architecture_revision="", acm_registry_revision="sha-1",
        acm_active_slice=["AC-1"], captured_at="",
    )
    ctx = RoundContext(snapshot=snap)
    ctx.last_transformer_payload = {
        "design_md": "## supersedes\nno supersession\n",
        "tasks_md": "T-001 a\n",
        "ac_schedule_yaml": (
            "version: 1\nacs:\n"
            "  - {id: AC-100, title: t, priority: P0, given: g, expected: e, "
            "test_file: harness/tests/REQ-P-1/test_x.py, test_function: test_x}\n"
        ),
        "harness_files": {
            "harness/tests/REQ-P-1/test_x.py":
                "import pytest\n@pytest.mark.ac('AC-100')\ndef test(): pass\n",
        },
        "supersedes_decl": [],
        "round_zero_ac_ids": ["AC-1"],
    }
    orch._rounds["REQ-P-1"] = ctx
    orch._project_repo_for = lambda req_id: "o/r"
    return orch, gateway, ctx


def test_on_converged_regression_first_failure_soft_retries(tmp_path):
    called = []
    orch, gateway, ctx = _make_regression_fail_orch(
        tmp_path, on_deadlock=lambda req, reason: called.append(reason),
    )
    outcome = orch._on_converged("REQ-P-1")
    assert outcome == "regression_retry"
    assert called == []  # no deadlock fired
    assert ctx.regression_retry_count == 1
    assert ctx.last_regression_missing == ["AC-1"]
    assert "REQ-P-1" in orch._rounds  # ctx kept alive
    gateway.commit_spec_pr_files.assert_not_called()
    trace = (tmp_path / "REQ-P-1.jsonl").read_text()
    assert "regression_retry" in trace


def test_on_converged_regression_exhausted_deadlocks(tmp_path):
    called = []
    orch, gateway, ctx = _make_regression_fail_orch(
        tmp_path, on_deadlock=lambda req, reason: called.append(reason),
    )
    ctx.regression_retry_count = 1  # already at max_regression_retries (default 1)
    outcome = orch._on_converged("REQ-P-1")
    assert outcome == "deadlock"
    assert called == ["regression_failed"]
    assert "REQ-P-1" not in orch._rounds
    trace = (tmp_path / "REQ-P-1.jsonl").read_text()
    assert "regression_failed" in trace
    assert "max_regression_retries" in trace


def test_handle_reviewer_verdict_regression_retry_returns_wake_transformer(tmp_path):
    orch, _gateway, _ctx = _make_regression_fail_orch(tmp_path)
    action = orch.handle_reviewer_verdict("REQ-P-1", "converged", [])
    assert action == "wake_transformer_regression_retry"


def test_compute_trace_digest_is_stable_sha256_prefix():
    from requirement_workflow_v12.spec_transform import _compute_trace_digest
    assert _compute_trace_digest("") == _compute_trace_digest("")
    d = _compute_trace_digest("hello\n")
    assert len(d) == 12
    assert d != _compute_trace_digest("hello")


def test_on_converged_pr_body_carries_audit_fields_and_callback_kwargs(tmp_path):
    """PR body must encode spec_source_revision/transform_round/transform_trace_digest;
    on_locked callback must receive the same values as kwargs."""
    from requirement_workflow_v12.acm_registry import AcmRegistry
    from requirement_workflow_v12.spec_transform import (
        SpecTransformOrchestrator, _compute_trace_digest,
    )
    gateway = MagicMock()
    gateway.fetch_file_sha = MagicMock(return_value=(
        "registry-sha-2",
        "version: 3\nentries:\n  - {ac_id: AC-1, req_id: R, status: active, priority: P0}\n",
    ))
    gateway.commit_spec_pr_files = MagicMock(return_value="commit-sha")
    gateway.open_pull_request = MagicMock(
        return_value={"number": 7, "html_url": "https://gh/pr/7"},
    )
    captured: dict = {}

    def on_locked(req_id, pr_url, **kwargs):
        captured["req_id"] = req_id
        captured["pr_url"] = pr_url
        captured.update(kwargs)

    registry = AcmRegistry(gateway=gateway)
    orch = SpecTransformOrchestrator(
        tools=GitHubProjectRepoTools(gateway), registry=registry, feishu=MagicMock(),
        trace_dir=tmp_path, on_locked=on_locked,
    )
    snap = TransformContextSnapshot(
        req_id="REQ-P-1", spec_source_revision="rev-feishu-42",
        architecture_revision="a", acm_registry_revision="registry-sha-2",
        acm_active_slice=["AC-1"], captured_at="2026-04-17",
    )
    ctx = RoundContext(snapshot=snap)
    ctx.round_index = 2
    ctx.last_transformer_payload = {
        "design_md": "## supersedes\nno supersession\n",
        "tasks_md": "T-001 init\n",
        "ac_schedule_yaml": (
            "version: 1\nacs:\n"
            "  - {id: AC-100, title: t, priority: P0, given: g, expected: e, "
            "test_file: harness/tests/REQ-P-1/test_x.py, test_function: test_x}\n"
        ),
        "harness_files": {
            "harness/tests/REQ-P-1/test_x.py":
                "import pytest\n@pytest.mark.ac('AC-1')\ndef test(): pass\n"
                "@pytest.mark.ac('AC-100')\ndef test2(): pass\n",
        },
        "supersedes_decl": [],
        "round_zero_ac_ids": ["AC-1"],
    }
    orch._rounds["REQ-P-1"] = ctx
    orch._project_repo_for = lambda req_id: "o/r"

    orch._on_converged("REQ-P-1")

    pr_kwargs = gateway.open_pull_request.call_args.kwargs
    body = pr_kwargs["body"]
    assert "spec_source_revision=rev-feishu-42" in body
    assert "transform_round=2" in body
    assert "transform_trace_digest=" in body

    # Callback received the audit fields
    assert captured["source_revision"] == "rev-feishu-42"
    assert captured["transform_round"] == 2
    assert len(captured["trace_digest"]) == 12
    # Digest in body matches digest passed to callback
    assert f"transform_trace_digest={captured['trace_digest']}" in body


def test_on_converged_regression_pass_after_soft_retry_locks(tmp_path):
    """Sim: first call regression-retries; second call (with fixed payload) locks."""
    orch, gateway, ctx = _make_regression_fail_orch(tmp_path)
    gateway.commit_spec_pr_files = MagicMock(return_value="sha-x")
    gateway.open_pull_request = MagicMock(
        return_value={"number": 1, "html_url": "https://gh/pr/1"},
    )
    # First converged call: regression fails (AC-1 not anchored)
    assert orch._on_converged("REQ-P-1") == "regression_retry"
    # Transformer "fixes" the payload by anchoring AC-1
    ctx.last_transformer_payload["harness_files"][
        "harness/tests/REQ-P-1/test_ac1.py"
    ] = "import pytest\n@pytest.mark.ac('AC-1')\ndef test(): pass\n"
    # Second converged call: scan now passes, commit + PR fire
    outcome = orch._on_converged("REQ-P-1")
    assert outcome == "locked"
    gateway.commit_spec_pr_files.assert_called_once()
    gateway.open_pull_request.assert_called_once()
