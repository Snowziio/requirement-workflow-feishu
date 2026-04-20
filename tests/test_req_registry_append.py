"""Tests for the project/req-registry.yaml append helper."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.req_registry import (  # noqa: E402
    RegistryAppendError,
    append_req_to_registry,
    render_registry_with_new_req,
)


def test_render_registry_with_new_req_appends_structured_line():
    original = "project: test3\nrequirements: []\n"
    new_text = render_registry_with_new_req(
        original_text=original,
        req_id="REQ-2026-04-20-001",
        title="会话鉴权",
        status="DRAFTING",
        created_at="2026-04-20T10:00:00+00:00",
    )
    import yaml
    parsed = yaml.safe_load(new_text)
    assert parsed["project"] == "test3"
    assert len(parsed["requirements"]) == 1
    entry = parsed["requirements"][0]
    assert entry["req_id"] == "REQ-2026-04-20-001"
    assert entry["title"] == "会话鉴权"
    assert entry["status"] == "DRAFTING"
    assert entry["plan_id"] is None
    assert entry["spec_pr"] is None


def test_render_registry_appends_to_existing_list():
    original = (
        "project: test3\n"
        "requirements:\n"
        "  - req_id: REQ-001\n"
        "    title: old\n"
        "    status: MERGED\n"
        "    plan_id: null\n"
        "    spec_pr: null\n"
        "    created_at: t1\n"
    )
    new_text = render_registry_with_new_req(
        original_text=original,
        req_id="REQ-002",
        title="new one",
        status="DRAFTING",
        created_at="t2",
    )
    import yaml
    parsed = yaml.safe_load(new_text)
    ids = [e["req_id"] for e in parsed["requirements"]]
    assert ids == ["REQ-001", "REQ-002"]


def test_append_req_to_registry_commits_via_gateway():
    from unittest.mock import MagicMock
    gw = MagicMock()
    gw.fetch_file_sha.return_value = ("sha_old", "project: test3\nrequirements: []\n")
    gw.commit_files.return_value = "sha_new"

    append_req_to_registry(
        github_gateway=gw,
        project_repo="Snowziio/test3",
        req_id="REQ-1",
        title="t",
        status="DRAFTING",
        created_at="ts",
    )
    gw.commit_files.assert_called_once()
    args = gw.commit_files.call_args.kwargs
    assert args["owner"] == "Snowziio"
    assert args["repo"] == "test3"
    assert args["branch"] == "main"
    file_changes = list(args["files"])
    assert len(file_changes) == 1
    assert file_changes[0].path == "project/req-registry.yaml"


def test_append_req_to_registry_swallows_gateway_errors(caplog):
    from unittest.mock import MagicMock
    from requirement_workflow_v12.github_gateway import GitHubGatewayError
    gw = MagicMock()
    gw.fetch_file_sha.side_effect = GitHubGatewayError(500, "boom")
    with caplog.at_level("WARNING"):
        append_req_to_registry(
            github_gateway=gw,
            project_repo="Snowziio/test3",
            req_id="REQ-1",
            title="t",
            status="DRAFTING",
            created_at="ts",
            swallow_errors=True,
        )
    assert any("req-registry" in r.message for r in caplog.records)
