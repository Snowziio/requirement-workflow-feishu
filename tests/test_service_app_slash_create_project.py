"""Unit tests for /create project slash command parser + routing."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.service_app import parse_create_project_command  # noqa: E402


def test_parse_create_project_happy_path():
    cmd = parse_create_project_command(
        "/create project test3 --category saas-ai-automation --owner ou_abc"
    )
    assert cmd is not None
    assert cmd.project == "test3"
    assert cmd.category == "saas-ai-automation"
    assert cmd.owner_user_id == "ou_abc"
    assert cmd.resume is False


def test_parse_create_project_resume_flag():
    cmd = parse_create_project_command(
        "/create project test3 --category saas-ai-automation --owner ou_abc --resume"
    )
    assert cmd is not None
    assert cmd.resume is True


def test_parse_create_project_returns_none_for_other_text():
    assert parse_create_project_command("随便聊聊") is None
    assert parse_create_project_command("/create req test3 foo") is None


def test_parse_create_project_missing_owner_returns_none():
    assert (
        parse_create_project_command(
            "/create project test3 --category saas-ai-automation"
        )
        is None
    )
