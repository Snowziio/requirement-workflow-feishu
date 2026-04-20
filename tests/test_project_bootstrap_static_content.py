"""Unit tests for project_bootstrap.static_content.

All rendering functions are pure string builders: no I/O, no side effects.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def test_project_readme_contains_req_registry_schema_doc():
    from requirement_workflow_v12.project_bootstrap.static_content import PROJECT_README_MD

    assert "req-registry.yaml" in PROJECT_README_MD
    assert "req_id:" in PROJECT_README_MD
    assert "project:" in PROJECT_README_MD


def test_req_registry_initial_yaml_has_empty_requirements_for_project():
    from requirement_workflow_v12.project_bootstrap.static_content import (
        render_req_registry_yaml,
    )

    text = render_req_registry_yaml(project="test3")
    assert "project: test3" in text
    assert "requirements: []" in text


def test_environments_yaml_default_is_stub():
    from requirement_workflow_v12.project_bootstrap.static_content import (
        render_environments_yaml,
    )

    text = render_environments_yaml(category="saas-ai-automation")
    parsed = yaml.safe_load(text)
    assert "environments" in parsed


def test_secrets_todo_md_is_category_dependent():
    from requirement_workflow_v12.project_bootstrap.static_content import (
        render_secrets_todo,
    )

    text_saas = render_secrets_todo(category="saas-ai-automation")
    text_bot = render_secrets_todo(category="enterprise-bot")
    assert "saas-ai-automation" in text_saas
    assert "enterprise-bot" in text_bot
    assert "OPENAI_API_KEY" in text_saas
    assert "FEISHU_APP_ID" in text_bot


def test_render_claude_md_substitutes_placeholders():
    from requirement_workflow_v12.project_bootstrap.static_content import render_claude_md

    text = render_claude_md(project="test3")
    assert "test3" in text
    assert "{project}" not in text


def test_render_skill_md_substitutes_placeholders():
    from requirement_workflow_v12.project_bootstrap.static_content import render_skill_md

    text = render_skill_md(project="test3")
    assert "test3" in text
    assert "{project}" not in text
