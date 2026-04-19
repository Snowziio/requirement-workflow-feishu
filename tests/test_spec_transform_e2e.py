"""End-to-end integration tests for the Spec transform game loop.

Exercises the full Coordinator path: ``submit_checkpoint_1a_pass`` →
``on_enter_transforming`` → ``handle_transformer_output`` →
``handle_reviewer_verdict`` → terminal (lock or deadlock). Uses a real
``CoordinatorService`` + real ``AcmRegistry`` + real
``SpecTransformOrchestrator``; only ``github_gateway`` and ``feishu`` are
mocked.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.coordinator_service import CoordinatorService
from requirement_workflow_v12.models import Requirement, WorkflowStatus
from requirement_workflow_v12.project_config import ProjectConfig
from requirement_workflow_v12.project_repo import GitHubProjectRepoTools
from requirement_workflow_v12.spec_state_machine import SpecStatus


# ── Shared fixtures ─────────────────────────────────────────────────────

_REGISTRY_YAML = (
    "version: 3\n"
    "entries:\n"
    "  - {ac_id: AC-1, req_id: R-PRIOR, status: active, priority: P0}\n"
)


def _gateway_mock():
    """GitHubGateway mock wired for the full game: fetch/create/commit/PR."""
    gateway = MagicMock()

    def fake_fetch(project_repo, ref, path):
        if path == "ARCHITECTURE.yaml":
            return ("arch-sha", "kind: Architecture\n")
        if path == "acm-registry.yaml":
            return ("registry-sha", _REGISTRY_YAML)
        raise AssertionError(f"unexpected fetch_file_sha path={path}")

    gateway.fetch_file_sha = MagicMock(side_effect=fake_fetch)
    gateway.create_branch = MagicMock(return_value=None)
    gateway.commit_spec_pr_files = MagicMock(return_value="commit-sha")
    gateway.open_pull_request = MagicMock(
        return_value={"number": 42, "html_url": "https://gh/pr/42"},
    )
    return gateway


def _build_wired_service(tmp_path, *, req_id="REQ-P-1", project="P"):
    """CoordinatorService with a Requirement ready for checkpoint_1a_pass
    and a fully wired orchestrator."""
    svc = CoordinatorService()
    req = Requirement(
        req_id=req_id, name="n", project=project, summary="s", creator="c",
    )
    req.status = WorkflowStatus.APPROVED
    req.spec_status = SpecStatus.DRAFTING
    req.spec_document_id = "doc-1"
    req.spec_document_url = "https://feishu/doc/1"
    svc.requirements[req_id] = req

    cfg = ProjectConfig(
        category="application", template_version="v1",
        architecture_doc_id="arch-doc", architecture_doc_url="https://arch",
    )
    cfg.github_repo_url = "acme/scaffold-repo"
    svc.project_configs[project] = cfg

    gateway = _gateway_mock()
    feishu = MagicMock()
    feishu.fetch_document_revision = MagicMock(return_value="feishu-rev-77")
    svc.configure_spec_orchestrator(
        tools=GitHubProjectRepoTools(gateway),
        trace_dir=tmp_path, feishu=feishu,
    )
    return svc, req, gateway, feishu


def _good_payload():
    """Transformer payload that passes spec_gate and anchors AC-1 + AC-100.

    ``skeleton_unique_anchor`` requires exactly one ``@pytest.mark.ac`` per
    harness file, so prior-AC regression coverage lives in its own file.
    """
    return {
        "design_md": (
            "# Design\n## 项目级上下文消费\n- ARCHITECTURE rev: arch-sha\n"
            "## supersedes\nno supersession\n"
        ),
        "tasks_md": "T-001 init\n",
        "ac_schedule_yaml": (
            "version: 1\nacs:\n"
            "  - {id: AC-100, title: t, priority: P0, given: g, "
            "expected: e, test_file: harness/tests/REQ-P-1/test_x.py, "
            "test_function: test_x}\n"
        ),
        "harness_files": {
            "harness/tests/REQ-P-1/test_x.py":
                "import pytest\n"
                "@pytest.mark.ac('AC-100')\ndef test_x(): pass\n",
            "harness/tests/REQ-P-1/test_prior.py":
                "import pytest\n"
                "@pytest.mark.ac('AC-1')\ndef test_prior(): pass\n",
        },
        "supersedes_decl": [],
        "round_zero_ac_ids": ["AC-1"],
    }


def _payload_missing_ac1():
    """Gate-passing payload that anchors only AC-100 → regression fails on AC-1."""
    p = _good_payload()
    p["harness_files"] = {
        "harness/tests/REQ-P-1/test_x.py":
            "import pytest\n"
            "@pytest.mark.ac('AC-100')\ndef test_x(): pass\n",
    }
    return p


# ── Scenario 1: one_round_converged ─────────────────────────────────────

def test_one_round_converged_locks_spec_with_audit_fields(tmp_path):
    """Happy path: gate pass → reviewer converged → regression pass → lock."""
    svc, req, gateway, _feishu = _build_wired_service(tmp_path)

    svc.submit_checkpoint_1a_pass("REQ-P-1")
    assert req.spec_status is SpecStatus.TRANSFORMING
    # fetch_project_context triggered once in on_enter_transforming
    assert gateway.fetch_file_sha.call_count >= 2  # ARCHITECTURE + acm-registry

    action = svc.spec_orchestrator.handle_transformer_output(
        "REQ-P-1", _good_payload(),
    )
    assert action == "wake_reviewer"

    action = svc.spec_orchestrator.handle_reviewer_verdict(
        "REQ-P-1", "converged", [],
    )
    assert action == "converged"

    assert req.spec_status is SpecStatus.LOCKED
    assert req.spec_pr_url == "https://gh/pr/42"
    assert req.spec_source_revision == "feishu-rev-77"
    assert len(req.transform_trace_digest) == 12
    gateway.commit_spec_pr_files.assert_called_once()
    gateway.open_pull_request.assert_called_once()

    # In-memory ctx dropped after lock.
    assert "REQ-P-1" not in svc.spec_orchestrator._rounds


# ── Scenario 2: three_round_deadlock ────────────────────────────────────

def test_three_round_deadlock_sets_spec_deadlocked_flag(tmp_path):
    """Reviewer rejects 3 consecutive rounds → deadlock; flag flips, state
    stays in TRANSFORMING (methodology §7.2 TRANSFORM_DEADLOCK is a self-loop)."""
    svc, req, _gateway, _feishu = _build_wired_service(tmp_path)
    svc.submit_checkpoint_1a_pass("REQ-P-1")

    findings = [{"dimension": "completeness", "severity": "blocking", "detail": "gap"}]
    for round_num in (1, 2):
        assert svc.spec_orchestrator.handle_transformer_output(
            "REQ-P-1", _good_payload(),
        ) == "wake_reviewer"
        action = svc.spec_orchestrator.handle_reviewer_verdict(
            "REQ-P-1", "reject", findings,
        )
        assert action == "wake_transformer_next_round"
        assert svc.spec_orchestrator._rounds["REQ-P-1"].round_index == round_num + 1

    # Round 3 reject → deadlock
    assert svc.spec_orchestrator.handle_transformer_output(
        "REQ-P-1", _good_payload(),
    ) == "wake_reviewer"
    action = svc.spec_orchestrator.handle_reviewer_verdict(
        "REQ-P-1", "reject", findings,
    )
    assert action == "deadlock"

    assert req.spec_status is SpecStatus.TRANSFORMING  # self-loop, not LOCKED
    assert req.spec_deadlocked is True
    assert req.spec_pr_url == ""
    assert "REQ-P-1" not in svc.spec_orchestrator._rounds

    # Trace captured the deadlock reason for audit.
    trace = (tmp_path / "REQ-P-1.jsonl").read_text()
    assert "max_rounds" in trace


# ── Scenario 3: regression_retry_then_pass ──────────────────────────────

def test_regression_retry_then_pass_locks_spec(tmp_path):
    """Reviewer converges but first payload misses AC-1 anchor → regression
    retry → transformer returns corrected payload → lock."""
    svc, req, gateway, _feishu = _build_wired_service(tmp_path)
    svc.submit_checkpoint_1a_pass("REQ-P-1")

    # Round 1: gate passes but AC-1 unanchored
    assert svc.spec_orchestrator.handle_transformer_output(
        "REQ-P-1", _payload_missing_ac1(),
    ) == "wake_reviewer"
    action = svc.spec_orchestrator.handle_reviewer_verdict(
        "REQ-P-1", "converged", [],
    )
    assert action == "wake_transformer_regression_retry"
    assert req.spec_status is SpecStatus.TRANSFORMING  # not locked yet
    gateway.commit_spec_pr_files.assert_not_called()

    ctx = svc.spec_orchestrator._rounds["REQ-P-1"]
    assert ctx.regression_retry_count == 1
    assert ctx.last_regression_missing == ["AC-1"]

    # Transformer re-runs with AC-1 anchored; reviewer converges again.
    assert svc.spec_orchestrator.handle_transformer_output(
        "REQ-P-1", _good_payload(),
    ) == "wake_reviewer"
    action = svc.spec_orchestrator.handle_reviewer_verdict(
        "REQ-P-1", "converged", [],
    )
    assert action == "converged"

    assert req.spec_status is SpecStatus.LOCKED
    assert req.spec_pr_url == "https://gh/pr/42"
    gateway.commit_spec_pr_files.assert_called_once()
    gateway.open_pull_request.assert_called_once()

    trace = (tmp_path / "REQ-P-1.jsonl").read_text()
    assert "regression_retry" in trace
    assert "locked" in trace


# ── Anchor: submit_checkpoint_1a_pass fires TRANSFORMING enter hook ─────

def test_submit_checkpoint_1a_pass_fires_on_enter_transforming_hook(tmp_path):
    """Regression anchor for Task 4.3 hook refactor: the TRANSFORMING
    on_enter hook must drive fetch_project_context and transition state."""
    svc, req, gateway, _feishu = _build_wired_service(tmp_path)

    svc.submit_checkpoint_1a_pass("REQ-P-1")

    # on_enter_transforming → fetch_project_context → 2x fetch_file_sha
    assert gateway.fetch_file_sha.call_count == 2
    assert req.spec_status is SpecStatus.TRANSFORMING
