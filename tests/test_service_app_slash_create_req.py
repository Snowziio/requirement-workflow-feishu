"""Unit tests for /create req slash command parser + routing."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.service_app import parse_create_req_command  # noqa: E402


def test_parse_create_req_minimal():
    cmd = parse_create_req_command("/create req test3 会话鉴权改造")
    assert cmd is not None
    assert cmd.project == "test3"
    assert cmd.name == "会话鉴权改造"
    assert cmd.summary == ""
    assert cmd.category == ""


def test_parse_create_req_with_summary_and_category():
    cmd = parse_create_req_command(
        '/create req test3 会话鉴权改造 --summary "支持JWT" --category saas-ai-automation'
    )
    assert cmd is not None
    assert cmd.project == "test3"
    assert cmd.name == "会话鉴权改造"
    assert cmd.summary == "支持JWT"
    assert cmd.category == "saas-ai-automation"


def test_parse_create_req_rejects_other_prefix():
    assert parse_create_req_command("/create project test3 ...") is None
    assert parse_create_req_command("创建需求 test3") is None
