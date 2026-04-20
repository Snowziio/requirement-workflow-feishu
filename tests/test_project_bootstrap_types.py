"""Unit tests for project_bootstrap.types (frozen dataclasses + enums)."""
from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def test_bootstrap_request_frozen_and_has_required_fields():
    from requirement_workflow_v12.project_bootstrap.types import BootstrapRequest

    req = BootstrapRequest(
        project="test3",
        category="saas-ai-automation",
        owner_user_id="ou_123",
        creator_chat_id="chat_abc",
    )
    assert dataclasses.is_dataclass(req)
    assert req.project == "test3"
    with pytest.raises(dataclasses.FrozenInstanceError):
        req.project = "x"  # type: ignore[misc]


def test_bootstrap_step_enum_values():
    from requirement_workflow_v12.project_bootstrap.types import BootstrapStep

    assert BootstrapStep.VALIDATE.value == 1
    assert BootstrapStep.UPSERT_CONFIG.value == 2
    assert BootstrapStep.CREATE_REPO.value == 3
    assert BootstrapStep.POPULATE_MAIN.value == 4
    assert BootstrapStep.CREATE_ARCHITECTURE_DOC.value == 5
    assert BootstrapStep.CREATE_FEISHU_GROUP.value == 6
    assert BootstrapStep.FINALIZE.value == 7


def test_bootstrap_result_aggregates_repo_doc_chat():
    from requirement_workflow_v12.project_bootstrap.types import BootstrapResult

    r = BootstrapResult(
        project="test3",
        github_repo_url="https://github.com/Snowziio/test3",
        architecture_doc_id="doc_x",
        architecture_doc_url="https://example/doc_x",
        feishu_chat_id="oc_chat",
        template_version="saas-ai-automation.v1",
    )
    assert r.github_repo_url.endswith("/test3")
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.project = "x"  # type: ignore[misc]


def test_bootstrap_step_error_preserves_step_number():
    from requirement_workflow_v12.project_bootstrap.types import (
        BootstrapStep,
        BootstrapStepError,
    )

    err = BootstrapStepError(step=BootstrapStep.CREATE_REPO, message="boom")
    assert err.step == BootstrapStep.CREATE_REPO
    assert "boom" in str(err)
    assert "CREATE_REPO" in str(err)
