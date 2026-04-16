import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.spec_gate import (
    GateFinding, GateResult, run_gate,
)
from requirement_workflow_v12.spec_transform import TransformContextSnapshot


def _snap():
    return TransformContextSnapshot(
        req_id="REQ-P-1", spec_source_revision="r",
        architecture_revision="a", acm_registry_revision="r",
        acm_active_slice=[], captured_at="2026-04-16",
    )


def test_run_gate_passes_on_minimal_valid_payload():
    payload = {
        "design_md": "# Design\n## supersedes\nno supersession\n",
        "tasks_md": "T-001 init\n",
        "ac_schedule_yaml": (
            "version: 1\n"
            "acs:\n"
            "  - id: AC-100\n"
            "    title: t\n"
            "    priority: P0\n"
            "    given: x\n"
            "    expected: y\n"
            "    test_file: harness/tests/REQ-P-1/test_x.py\n"
            "    test_function: test_x\n"
        ),
        "harness_files": {
            "harness/tests/REQ-P-1/test_x.py": (
                "import pytest\n"
                "@pytest.mark.ac('AC-100')\n"
                "def test_x():\n    pass\n"
            ),
        },
        "supersedes_decl": [],
        "round_zero_ac_ids": [],
    }
    result = run_gate(payload, _snap())
    assert result.passed is True


def test_run_gate_fails_on_missing_required_ac_field():
    payload = {
        "design_md": "## supersedes\nno supersession\n",
        "tasks_md": "T-001 a\n",
        "ac_schedule_yaml": "version: 1\nacs:\n  - id: AC-100\n",
        "harness_files": {},
        "supersedes_decl": [],
        "round_zero_ac_ids": [],
    }
    result = run_gate(payload, _snap())
    assert result.passed is False
    assert any(f.rule == "ac_schedule_schema" for f in result.findings)
    assert all(f.kind == "format" for f in result.findings if f.rule == "ac_schedule_schema")


def test_run_gate_fails_on_malformed_tasks_md():
    payload = {
        "design_md": "## supersedes\nno supersession\n",
        "tasks_md": "no tasks here at all\n",
        "ac_schedule_yaml": (
            "version: 1\nacs:\n"
            "  - {id: AC-100, title: t, priority: P0, given: g, expected: e, "
            "test_file: harness/tests/REQ-P-1/test_x.py, test_function: test_x}\n"
        ),
        "harness_files": {
            "harness/tests/REQ-P-1/test_x.py":
                "import pytest\n@pytest.mark.ac('AC-100')\ndef test_x(): pass\n",
        },
        "supersedes_decl": [], "round_zero_ac_ids": [],
    }
    result = run_gate(payload, _snap())
    assert any(f.rule == "tasks_md_format" for f in result.findings)


def test_run_gate_fails_on_test_file_not_in_harness_payload():
    payload = {
        "design_md": "## supersedes\nno supersession\n",
        "tasks_md": "T-001 init\n",
        "ac_schedule_yaml": (
            "version: 1\nacs:\n"
            "  - {id: AC-100, title: t, priority: P0, given: g, expected: e, "
            "test_file: harness/tests/REQ-P-1/missing.py, test_function: test_x}\n"
        ),
        "harness_files": {},
        "supersedes_decl": [], "round_zero_ac_ids": [],
    }
    result = run_gate(payload, _snap())
    assert any(f.rule == "path_consistency" for f in result.findings)


def test_run_gate_fails_when_round_zero_recall_missing_active_ac():
    snap = TransformContextSnapshot(
        req_id="REQ-P-1", spec_source_revision="r",
        architecture_revision="a", acm_registry_revision="r",
        acm_active_slice=["AC-001", "AC-002"], captured_at="2026-04-16",
    )
    payload = {
        "design_md": "## supersedes\nno supersession\n",
        "tasks_md": "T-001 init\n",
        "ac_schedule_yaml": "version: 1\nacs: []\n",
        "harness_files": {},
        "supersedes_decl": [],
        "round_zero_ac_ids": ["AC-001"],   # missing AC-002
    }
    result = run_gate(payload, snap)
    finding = next(f for f in result.findings if f.rule == "round_zero_ac_recall")
    assert finding.kind == "semantic"
    assert "AC-002" in finding.detail


def test_run_gate_fails_when_supersedes_decl_inconsistent():
    snap = TransformContextSnapshot(
        req_id="REQ-P-1", spec_source_revision="r",
        architecture_revision="a", acm_registry_revision="r",
        acm_active_slice=["AC-001"], captured_at="2026-04-16",
    )
    # design.md says supersedes AC-999 but AC-999 is not in active slice
    payload = {
        "design_md": "## supersedes\nReplaces AC-999\n",
        "tasks_md": "T-001 init\n",
        "ac_schedule_yaml": "version: 1\nacs: []\n",
        "harness_files": {},
        "supersedes_decl": [{"old_ac_id": "AC-999", "by_ac_id": "AC-100"}],
        "round_zero_ac_ids": ["AC-001"],
    }
    result = run_gate(payload, snap)
    finding = next(f for f in result.findings if f.rule == "supersedes_completeness")
    assert finding.kind == "semantic"
    assert "AC-999" in finding.detail
