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


def test_render_template_output_is_unchanged_when_yaml_has_no_frontend_or_design():
    """Backward compat: render_template on a YAML without frontend/design keys
    should produce identical output (no trailing UI Context section)."""
    from requirement_workflow_v12.architecture_templates import render_template
    # enterprise-app.v1.yaml currently has no frontend/design keys (pre-Task 5)
    version, text = render_template("enterprise-app", project="myproj")
    assert version == "enterprise-app.v1"
    assert "myproj" in text


def test_render_template_appends_ui_context_section_if_yaml_has_frontend_or_design(tmp_path):
    """render_template must call _build_ui_context_section and append its output."""
    from unittest.mock import patch
    from requirement_workflow_v12.architecture_templates import render_template

    stub_yaml = """
category: stub-test
frontend:
  subpath: "src/stub_webapp"
  tech_stack:
    framework: "React 18"
design:
  design_system_snapshot_path: "design/system/"
  pages_registry_path: "design/PAGES.yaml"
"""
    stub_path = tmp_path / "stub-test.v1.yaml"
    stub_path.write_text(stub_yaml, encoding="utf-8")

    with patch(
        "requirement_workflow_v12.architecture_templates._latest_template_path",
        return_value=("stub-test.v1", stub_path),
    ):
        version, text = render_template("stub-test", project="myproj")
        assert "## UI Context" in text
        assert "src/stub_webapp" in text
        assert "React 18" in text
