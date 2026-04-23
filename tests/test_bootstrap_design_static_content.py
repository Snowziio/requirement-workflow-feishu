"""Unit tests for design-related render functions in static_content."""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def test_render_design_readme_mentions_claude_design_and_archive():
    from requirement_workflow_v12.project_bootstrap.static_content import render_design_readme
    text = render_design_readme()
    assert "Claude Design" in text
    assert "design/archive" in text
    assert "PAGES.yaml" in text


def test_render_design_pages_yaml_parses_as_empty_pages():
    from requirement_workflow_v12.project_bootstrap.static_content import render_design_pages_yaml
    text = render_design_pages_yaml()
    parsed = yaml.safe_load(text)
    assert parsed == {"schema_version": "1.0", "pages": []}


def test_render_design_index_md_has_header_and_comment():
    from requirement_workflow_v12.project_bootstrap.static_content import render_design_index_md
    text = render_design_index_md()
    assert "# Design Handoff Index" in text
    assert "DO NOT edit by hand" in text


def test_render_gitattributes_has_lfs_rule_for_bundle_zip():
    from requirement_workflow_v12.project_bootstrap.static_content import render_gitattributes
    text = render_gitattributes()
    assert "design/archive/**/bundle.zip" in text
    assert "filter=lfs" in text


def test_render_claude_md_has_design_reference_rules_section():
    from requirement_workflow_v12.project_bootstrap.static_content import render_claude_md
    text = render_claude_md(project="testproj")
    assert "## Design Reference Rules" in text
    assert "design/archive/" in text
    # Spec mentions bundle JSX is NOT production code
    assert "React-via-CDN" in text or "不是生产代码" in text
    # Spec mentions commit message tag requirement
    assert "design:" in text.lower() or "Commit message" in text


def test_render_claude_md_preserves_existing_conventions_section():
    from requirement_workflow_v12.project_bootstrap.static_content import render_claude_md
    text = render_claude_md(project="testproj")
    # Existing content should still be there
    assert "testproj" in text
    assert "Conventions" in text
