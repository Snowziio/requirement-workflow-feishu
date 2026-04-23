"""Tests for parse_template_yaml + UI Context section generation."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def test_parse_template_yaml_returns_dict_with_expected_keys():
    """parse_template_yaml returns a dict with at least the existing base fields."""
    from requirement_workflow_v12.architecture_templates import parse_template_yaml
    parsed = parse_template_yaml("enterprise-app")
    assert isinstance(parsed, dict)
    assert "category" in parsed  # existing field still there
    assert "tech_stack" in parsed  # existing field


def test_fmt_tech_stack_joins_key_values():
    from requirement_workflow_v12.architecture_templates import _fmt_tech_stack
    stack = {"framework": "React 18", "build": "Vite 5.x"}
    result = _fmt_tech_stack(stack)
    assert "framework: React 18" in result
    assert "build: Vite 5.x" in result
    assert " / " in result


def test_fmt_tech_stack_empty_returns_placeholder():
    from requirement_workflow_v12.architecture_templates import _fmt_tech_stack
    assert _fmt_tech_stack({}) == "（未定义）"


def test_build_ui_context_section_with_frontend_and_design():
    from requirement_workflow_v12.architecture_templates import _build_ui_context_section
    parsed = {
        "frontend": {
            "subpath": "src/test_webapp",
            "tech_stack": {"framework": "React 18", "build": "Vite 5.x"},
        },
        "design": {
            "claude_design_project_url": "",
            "design_system_snapshot_path": "design/system/",
            "pages_registry_path": "design/PAGES.yaml",
            "archive_path": "design/archive/",
        },
    }
    section = _build_ui_context_section(parsed)
    assert section is not None
    assert "## UI Context" in section
    assert "src/test_webapp" in section
    assert "React 18" in section
    assert "design/system/" in section
    assert "design/PAGES.yaml" in section


def test_build_ui_context_section_with_frontend_null_returns_explanation():
    from requirement_workflow_v12.architecture_templates import _build_ui_context_section
    parsed = {
        "frontend": None,
        "design": {"design_system_snapshot_path": "design/system/"},
    }
    section = _build_ui_context_section(parsed)
    assert section is not None
    assert "无前端" in section or "enterprise-app" in section


def test_build_ui_context_section_without_frontend_or_design_returns_none():
    from requirement_workflow_v12.architecture_templates import _build_ui_context_section
    parsed = {"category": "something-else"}
    section = _build_ui_context_section(parsed)
    assert section is None
