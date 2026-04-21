"""Tests for the Feishu → GitHub freeze-point syncer (Phase 3-E).

The syncer is the seam where the construction-phase Feishu SOT hands
off to the implementation-phase GitHub SOT. These tests pin behavior at
the module boundary; the real FeishuGateway / ProjectRepoTools live
behind Protocols and are mocked here.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.feishu_to_github_syncer import (  # noqa: E402
    FeishuSyncerError,
    FeishuToGitHubSyncer,
    PlanSyncResult,
    SpecSyncResult,
)
from requirement_workflow_v12.project_repo import (  # noqa: E402
    PlanCommitResult,
    ProjectRepoError,
    SpecMdCommitResult,
)


def _make_syncer(
    *, feishu_text: str = "# plan", commit_result: PlanCommitResult | None = None,
):
    feishu = MagicMock()
    feishu.read_document_text.return_value = feishu_text
    tools = MagicMock()
    tools.commit_plan_artifacts.return_value = commit_result or PlanCommitResult(
        commit_sha="sha-x", branch="main",
        plan_md_path="docs/specs/REQ-1/plan.md",
        architecture_updated=False,
    )
    return FeishuToGitHubSyncer(
        feishu=feishu, project_repo_tools=tools,
    ), feishu, tools


def test_sync_plan_reads_feishu_and_delegates_to_commit_plan_artifacts():
    syncer, feishu, tools = _make_syncer(feishu_text="# plan from Feishu\n")

    result = syncer.sync_plan(
        req_id="REQ-1",
        project_repo="owner/repo",
        plan_doc_id="docx-plan-abc",
        project_context_change=None,
        commit_message="plan(REQ-1): land plan.md",
    )

    feishu.read_document_text.assert_called_once_with("docx-plan-abc")
    tools.commit_plan_artifacts.assert_called_once()
    artifacts = tools.commit_plan_artifacts.call_args.args[0]
    assert artifacts.project_repo == "owner/repo"
    assert artifacts.req_id == "REQ-1"
    assert artifacts.plan_md_content == "# plan from Feishu\n"
    assert artifacts.project_context_change is None
    assert isinstance(result, PlanSyncResult)
    assert result.commit_sha == "sha-x"
    assert result.plan_github_path == "docs/specs/REQ-1/plan.md"
    assert result.architecture_updated is False


def test_sync_plan_forwards_project_context_change_untouched():
    syncer, _feishu, tools = _make_syncer(
        commit_result=PlanCommitResult(
            commit_sha="sha-y", branch="main",
            plan_md_path="docs/specs/REQ-2/plan.md",
            architecture_updated=True,
        ),
    )
    pcc = {
        "summary": "Add Redis",
        "changes": [
            {"artifact": "architecture", "section_path": "## Storage",
             "before": "", "after": "Redis", "rationale": "D1"},
        ],
        "authorized": True,
        "authorized_by": "u-1",
        "authorized_at": "2026-04-21T10:00:00Z",
    }

    result = syncer.sync_plan(
        req_id="REQ-2",
        project_repo="owner/repo",
        plan_doc_id="docx-plan-2",
        project_context_change=pcc,
        commit_message="plan(REQ-2): land plan.md + Redis",
    )

    artifacts = tools.commit_plan_artifacts.call_args.args[0]
    assert artifacts.project_context_change is pcc
    assert result.architecture_updated is True


def test_sync_plan_raises_syncer_error_when_feishu_fails_without_fallback():
    syncer, feishu, tools = _make_syncer()
    feishu.read_document_text.side_effect = RuntimeError("feishu 5xx")

    with pytest.raises(FeishuSyncerError, match="cannot read Feishu plan doc"):
        syncer.sync_plan(
            req_id="REQ-1", project_repo="o/r", plan_doc_id="docx-bad",
            project_context_change=None, commit_message="m",
        )
    tools.commit_plan_artifacts.assert_not_called()


def test_sync_plan_falls_back_to_audit_copy_when_feishu_fails():
    syncer, feishu, tools = _make_syncer()
    feishu.read_document_text.side_effect = RuntimeError("feishu down")

    result = syncer.sync_plan(
        req_id="REQ-3", project_repo="o/r", plan_doc_id="docx-3",
        project_context_change=None, commit_message="m",
        fallback_plan_md="# audit copy\n",
    )

    artifacts = tools.commit_plan_artifacts.call_args.args[0]
    assert artifacts.plan_md_content == "# audit copy\n"
    assert result.commit_sha == "sha-x"


def test_sync_plan_without_doc_id_uses_fallback_when_provided():
    syncer, feishu, tools = _make_syncer()

    syncer.sync_plan(
        req_id="REQ-4", project_repo="o/r", plan_doc_id="",
        project_context_change=None, commit_message="m",
        fallback_plan_md="# legacy audit copy\n",
    )

    feishu.read_document_text.assert_not_called()
    artifacts = tools.commit_plan_artifacts.call_args.args[0]
    assert artifacts.plan_md_content == "# legacy audit copy\n"


def test_sync_plan_without_doc_id_and_no_fallback_raises():
    syncer, _feishu, tools = _make_syncer()

    with pytest.raises(FeishuSyncerError, match="no plan_doc_id and no fallback"):
        syncer.sync_plan(
            req_id="REQ-5", project_repo="o/r", plan_doc_id="",
            project_context_change=None, commit_message="m",
        )
    tools.commit_plan_artifacts.assert_not_called()


def test_sync_plan_wraps_project_repo_error_preserving_recoverable():
    syncer, _feishu, tools = _make_syncer()
    tools.commit_plan_artifacts.side_effect = ProjectRepoError(
        "apply conflict", recoverable=True,
    )

    with pytest.raises(FeishuSyncerError) as exc_info:
        syncer.sync_plan(
            req_id="REQ-6", project_repo="o/r", plan_doc_id="docx-6",
            project_context_change=None, commit_message="m",
        )
    assert exc_info.value.recoverable is True


def test_sync_plan_wraps_non_recoverable_project_repo_error():
    syncer, _feishu, tools = _make_syncer()
    tools.commit_plan_artifacts.side_effect = ProjectRepoError(
        "403 forbidden", recoverable=False,
    )

    with pytest.raises(FeishuSyncerError) as exc_info:
        syncer.sync_plan(
            req_id="REQ-7", project_repo="o/r", plan_doc_id="docx-7",
            project_context_change=None, commit_message="m",
        )
    assert exc_info.value.recoverable is False


# ── sync_spec (Checkpoint 1a freeze) ────────────────────────────────────


def _make_spec_syncer(
    *, feishu_text: str = "# spec", commit_result: SpecMdCommitResult | None = None,
):
    feishu = MagicMock()
    feishu.read_document_text.return_value = feishu_text
    tools = MagicMock()
    tools.commit_spec_md.return_value = commit_result or SpecMdCommitResult(
        commit_sha="spec-sha-1", branch="main",
        spec_md_path="docs/specs/REQ-S-1/spec.md",
    )
    return FeishuToGitHubSyncer(
        feishu=feishu, project_repo_tools=tools,
    ), feishu, tools


def test_sync_spec_reads_feishu_and_delegates_to_commit_spec_md():
    syncer, feishu, tools = _make_spec_syncer(
        feishu_text="# Spec from Feishu\n\n## Section 1\n",
    )

    result = syncer.sync_spec(
        req_id="REQ-S-1",
        project_repo="owner/repo",
        spec_doc_id="docx-spec-abc",
        commit_message="spec(REQ-S-1): freeze 9-section spec (Checkpoint 1a)",
    )

    feishu.read_document_text.assert_called_once_with("docx-spec-abc")
    tools.commit_spec_md.assert_called_once()
    artifacts = tools.commit_spec_md.call_args.args[0]
    assert artifacts.project_repo == "owner/repo"
    assert artifacts.req_id == "REQ-S-1"
    assert artifacts.spec_md_content == "# Spec from Feishu\n\n## Section 1\n"
    assert isinstance(result, SpecSyncResult)
    assert result.commit_sha == "spec-sha-1"
    assert result.spec_github_path == "docs/specs/REQ-S-1/spec.md"


def test_sync_spec_raises_syncer_error_when_feishu_fails_without_fallback():
    syncer, feishu, tools = _make_spec_syncer()
    feishu.read_document_text.side_effect = RuntimeError("feishu 5xx")

    with pytest.raises(FeishuSyncerError, match="cannot read Feishu spec doc"):
        syncer.sync_spec(
            req_id="REQ-S-2", project_repo="o/r", spec_doc_id="docx-bad",
            commit_message="m",
        )
    tools.commit_spec_md.assert_not_called()


def test_sync_spec_falls_back_to_audit_copy_when_feishu_fails():
    syncer, feishu, tools = _make_spec_syncer()
    feishu.read_document_text.side_effect = RuntimeError("feishu down")

    result = syncer.sync_spec(
        req_id="REQ-S-3", project_repo="o/r", spec_doc_id="docx-3",
        commit_message="m", fallback_spec_md="# audit spec\n",
    )

    artifacts = tools.commit_spec_md.call_args.args[0]
    assert artifacts.spec_md_content == "# audit spec\n"
    assert result.commit_sha == "spec-sha-1"


def test_sync_spec_without_doc_id_and_no_fallback_raises():
    syncer, _feishu, tools = _make_spec_syncer()

    with pytest.raises(FeishuSyncerError, match="no spec_doc_id and no fallback"):
        syncer.sync_spec(
            req_id="REQ-S-4", project_repo="o/r", spec_doc_id="",
            commit_message="m",
        )
    tools.commit_spec_md.assert_not_called()


def test_sync_spec_wraps_project_repo_error_preserving_recoverable():
    syncer, _feishu, tools = _make_spec_syncer()
    tools.commit_spec_md.side_effect = ProjectRepoError(
        "commit failed", recoverable=True,
    )

    with pytest.raises(FeishuSyncerError) as exc_info:
        syncer.sync_spec(
            req_id="REQ-S-5", project_repo="o/r", spec_doc_id="docx-5",
            commit_message="m",
        )
    assert exc_info.value.recoverable is True
