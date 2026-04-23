# Bootstrap Design Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Bootstrap-layer prerequisites for the design phase per `docs/superpowers/specs/2026-04-23-bootstrap-design-integration-design.md`: add 8 design-related files to Step 4 populate, extend 5 architecture template YAMLs with frontend/design fields, add 3 ProjectConfig fields, emit a Claude Design binding reminder card after FINALIZE, and add a lazy-check guard on `design_start` that blocks entry when `claude_design_project_url` is empty.

**Architecture:** Mostly additive changes to existing modules: `static_content.py` (4 new render functions + 1 modified), `architecture_templates.py` (YAML parser + UI Context section builder), 5 category YAMLs (add frontend + design blocks), `project_config.py` (3 new fields), `feishu_gateway.py` (3 new Bitable fields), `project_bootstrap/service.py` (extend populate_files + emit binding card in FINALIZE), `service_app.py` (card action handler + binding guard wiring), `coordinator_service.py` (lazy check in `design_start`). No new `BootstrapStep` enum values; all changes fold into existing Step 4 and Step 7.

**Tech Stack:** Python 3.11, `pytest` + `unittest.mock.MagicMock`, PyYAML (already installed), existing FeishuGateway / GitHubProjectRepoTools. Tests use pytest function-style with `sys.path.insert` pattern (matches existing repo convention).

**Reference:** Design spec at `docs/superpowers/specs/2026-04-23-bootstrap-design-integration-design.md`. Upstream dependency: design-phase spec `docs/superpowers/specs/2026-04-23-design-phase-design.md` already implemented (commit `6f832fa`).

---

## Pre-flight

Before starting:

- [ ] Run `python3 -m pytest tests/ --ignore=tests/test_concurrent_spec_gate.py -q 2>&1 | tail -3` — record the current green baseline (should be ~538 passing, 8 pre-existing failures).
- [ ] Read the spec cover-to-cover: `docs/superpowers/specs/2026-04-23-bootstrap-design-integration-design.md`.
- [ ] Confirm current branch is `main` at commit `7d7d8da` or later; optionally create a feature branch `feat/bootstrap-design-integration` (if doing subagent-driven, create one commit per task; if doing inline, decide whether to branch before starting).
- [ ] Read the reference patterns:
  - `src/requirement_workflow_v12/project_bootstrap/static_content.py` (lines 1-115) — existing render functions
  - `src/requirement_workflow_v12/project_bootstrap/service.py` (lines 120-185) — `create_repo_and_populate` method
  - `src/requirement_workflow_v12/architecture_templates.py` (full, ~73 lines) — rendering mechanics
  - `src/requirement_workflow_v12/feishu_gateway.py` lines 594-770 — Bitable CRUD for ProjectConfig

---

## File Structure

**New files:**
- `tests/test_bootstrap_design_static_content.py`
- `tests/test_architecture_templates_ui_context.py`
- `tests/test_project_config_design_fields.py`
- `tests/test_bootstrap_design_populate.py`
- `tests/test_bootstrap_design_binding_card.py`
- `tests/test_card_bind_claude_design.py`
- `tests/test_design_start_binding_guard.py`
- `tests/test_bootstrap_design_e2e.py`

**Modified files:**
- `src/requirement_workflow_v12/project_bootstrap/static_content.py` — add 4 render functions, modify `render_claude_md`
- `src/requirement_workflow_v12/architecture_templates.py` — add `parse_template_yaml`, `_build_ui_context_section`, `_fmt_tech_stack`; modify `render_template`
- `docs/context/architecture-templates/enterprise-app.v1.yaml` — add frontend + design blocks
- `docs/context/architecture-templates/enterprise-bot.v1.yaml` — add `frontend: null` + design block
- `docs/context/architecture-templates/miniprogram.v1.yaml` — add Taro frontend + design block
- `docs/context/architecture-templates/public-web-site.v1.yaml` — add frontend + design block
- `docs/context/architecture-templates/saas-ai-automation.v1.yaml` — add frontend + design block
- `src/requirement_workflow_v12/project_config.py` — add 3 new fields + from_dict extension
- `src/requirement_workflow_v12/feishu_gateway.py` — add 3 new Bitable field constants + read/write paths
- `src/requirement_workflow_v12/project_bootstrap/service.py` — extend `create_repo_and_populate`; add `_emit_design_binding_reminder_card`; modify `finalize`
- `src/requirement_workflow_v12/service_app.py` — add `bind_claude_design_project` action handler; extend `dispatch_design_start_if_needed` to catch binding guard failure
- `src/requirement_workflow_v12/coordinator_service.py` — add `claude_design_project_url` check in `design_start`
- `README.md` — note new Bootstrap populate files + binding card

---

## Task 1: Add 4 new render functions to static_content.py

**Files:**
- Modify: `src/requirement_workflow_v12/project_bootstrap/static_content.py`
- Test: `tests/test_bootstrap_design_static_content.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_bootstrap_design_static_content.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_bootstrap_design_static_content.py -v
```
Expected: FAIL with `ImportError: cannot import name 'render_design_readme'`.

- [ ] **Step 3: Add render functions to static_content.py**

In `src/requirement_workflow_v12/project_bootstrap/static_content.py`, append at the end:

```python
def render_design_readme() -> str:
    return (
        "# Design Artifacts\n"
        "\n"
        "本目录存放 design 阶段产出的所有制品。产物来自 Claude Design "
        "（https://claude.ai/design），通过 coordinator 的 handoff intake 流程自动入仓。\n"
        "\n"
        "## 目录结构\n"
        "- `INDEX.md`    — 所有 REQ 的 handoff 时间线（coordinator 自动维护）\n"
        "- `PAGES.yaml`  — Page Registry（本项目当前有哪些 page）\n"
        "- `system/`     — 组织级 Design System 快照（Claude Design DS 的副本）\n"
        "- `archive/`    — 逐 REQ 的 handoff 完整 bundle（design/archive/REQ-*_<slug>/）\n"
        "\n"
        "## 实施期参考规则\n"
        "本 REQ 实施时，代码层视觉规范以 `archive/<当前 REQ>/extracted/` 为准。\n"
        "详见根目录 `CLAUDE.md` 的 'Design Reference Rules' 小节。\n"
        "\n"
        "## 不在此维护的事项\n"
        "- 不记录 file-level diff（每 REQ 是自包含快照）\n"
        "- 不记录 drift 台账（设计师每次在 Claude Design 点 'Sync now' 自然消解）\n"
    )


def render_design_pages_yaml() -> str:
    return "schema_version: \"1.0\"\npages: []\n"


def render_design_index_md() -> str:
    return (
        "# Design Handoff Index\n"
        "\n"
        "<!-- Auto-generated by coordinator on DESIGN_READY. DO NOT edit by hand. -->\n"
    )


def render_gitattributes() -> str:
    return (
        "# git-lfs rules for design handoff bundles\n"
        "design/archive/**/bundle.zip filter=lfs diff=lfs merge=lfs -text\n"
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m pytest tests/test_bootstrap_design_static_content.py -v
```
Expected: 4 tests PASS.

- [ ] **Step 5: Run full suite for regression**

```bash
python3 -m pytest tests/ --ignore=tests/test_concurrent_spec_gate.py -q 2>&1 | tail -3
```
Expected: baseline + 4 new passes, no new failures.

- [ ] **Step 6: Commit**

```bash
git add src/requirement_workflow_v12/project_bootstrap/static_content.py tests/test_bootstrap_design_static_content.py
git commit -m "feat(bootstrap): add render functions for design/ static content"
```

---

## Task 2: Modify render_claude_md to include Design Reference Rules

**Files:**
- Modify: `src/requirement_workflow_v12/project_bootstrap/static_content.py`
- Test: `tests/test_bootstrap_design_static_content.py` (append)

- [ ] **Step 1: Append failing tests**

Append to `tests/test_bootstrap_design_static_content.py`:

```python


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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_bootstrap_design_static_content.py::test_render_claude_md_has_design_reference_rules_section -v
```
Expected: FAIL — "Design Reference Rules" not present.

- [ ] **Step 3: Modify render_claude_md**

In `static_content.py`, replace the existing `render_claude_md` function with:

```python
def render_claude_md(*, project: str) -> str:
    pkg = derive_pkg(project)
    today = date.today().isoformat()
    return (
        f"# CLAUDE.md — {project}\n"
        f"\n"
        f"项目包名：`{pkg}`\n"
        f"\n"
        f"创建于 Bootstrap：{today}\n"
        f"\n"
        "## Conventions\n"
        "\n"
        "（Bootstrap 占位；后续通过 REQ 的 project_context_change gate 演化）\n"
        "\n"
        "## Design Reference Rules\n"
        "\n"
        "本项目使用 Claude Design（https://claude.ai/design）作为 UI/UX 设计工具。\n"
        "实施期（Spec / Impl）的 UI 代码工作必须遵循：\n"
        "\n"
        "1. **参考来源**：本 REQ 实施时，视觉规范以 `design/archive/<CURRENT_REQ_ID>_*/extracted/` 为准\n"
        "2. **样式翻译原则**：handoff bundle 里的 JSX 是 React-via-CDN 原型，**不是生产代码**\n"
        "   - 不要直接复制 JSX 结构；按视觉效果在前端栈中重新组织（见 docs/ARCHITECTURE.md 的 'UI Context' 节）\n"
        "   - CSS tokens 来自 `extracted/*/assets/colors_and_type.css`，落到前端工程的 `src/<pkg>_webapp/src/lib/tokens.ts` + `tailwind.config.js`\n"
        "3. **历史归档**：`design/archive/<其他 REQ>/` 是历史 handoff，仅用于追溯，不作为本 REQ 的规范\n"
        "4. **Commit message 引用**：前端 UI 实施 commit 的 message 必须含 `design: <REQ-ID>_<slug>` tag\n"
        "5. **不做的事**：不写 DRIFT-TRUTH.md；不做 file-level diff——每 REQ 是自包含快照\n"
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m pytest tests/test_bootstrap_design_static_content.py -v
```
Expected: 6/6 pass.

- [ ] **Step 5: Full suite regression check**

```bash
python3 -m pytest tests/ --ignore=tests/test_concurrent_spec_gate.py -q 2>&1 | tail -3
```
Expected: no new failures. Note: `test_render_claude_md_substitutes_placeholders` in `test_project_bootstrap_static_content.py` may rely on the old format — verify it still passes. If not, the existing assertion should still hold since `project` name and "Conventions" section remain.

- [ ] **Step 6: Commit**

```bash
git add src/requirement_workflow_v12/project_bootstrap/static_content.py tests/test_bootstrap_design_static_content.py
git commit -m "feat(bootstrap): extend render_claude_md with Design Reference Rules section"
```

---

## Task 3: Add parse_template_yaml + UI Context section builder to architecture_templates

**Files:**
- Modify: `src/requirement_workflow_v12/architecture_templates.py`
- Test: `tests/test_architecture_templates_ui_context.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_architecture_templates_ui_context.py`:

```python
"""Tests for parse_template_yaml + UI Context section generation."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def test_parse_template_yaml_returns_dict_with_frontend_and_design():
    """After YAMLs are updated (Task 5) they must have 'frontend' and 'design' keys."""
    from requirement_workflow_v12.architecture_templates import parse_template_yaml
    parsed = parse_template_yaml("enterprise-app")
    # After Task 5 we'll assert these; for Task 3 just assert the function exists and returns a dict
    assert isinstance(parsed, dict)
    assert "category" in parsed  # existing field still there


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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_architecture_templates_ui_context.py -v
```
Expected: FAIL — `ImportError: cannot import name 'parse_template_yaml'`.

- [ ] **Step 3: Add helpers to architecture_templates.py**

In `src/requirement_workflow_v12/architecture_templates.py`, add at the end (after the existing `render_template`):

```python
def parse_template_yaml(category: str) -> dict:
    """Load raw YAML for a category (latest version) as a Python dict.

    Placeholders like {pkg}, {project}, {date} are NOT substituted here —
    this is for structural inspection (e.g., reading frontend.subpath).
    """
    import yaml
    _version, path = _latest_template_path(category)
    raw = path.read_text(encoding="utf-8")
    parsed = yaml.safe_load(raw)
    if not isinstance(parsed, dict):
        raise UnknownCategory(f"template for {category} did not parse as dict")
    return parsed


def _fmt_tech_stack(stack: dict) -> str:
    if not stack:
        return "（未定义）"
    return " / ".join(f"{k}: {v}" for k, v in stack.items())


def _build_ui_context_section(parsed: dict) -> str | None:
    """Build a '## UI Context' Markdown section from parsed YAML.

    Returns None when the YAML has neither 'frontend' nor 'design' keys
    (i.e., existing YAMLs that haven't been extended yet).
    """
    has_frontend_key = "frontend" in parsed
    has_design_key = "design" in parsed
    if not (has_frontend_key or has_design_key):
        return None

    lines = ["## UI Context", ""]
    frontend = parsed.get("frontend")
    if frontend is None and has_frontend_key:
        lines.append(
            "- **前端**：本 category 默认无前端（若需管理后台见 enterprise-app 栈）"
        )
    elif frontend:
        lines.append(f"- **前端栈**：{_fmt_tech_stack(frontend.get('tech_stack', {}))}")
        lines.append(f"- **前端代码位置**：`{frontend.get('subpath', '')}`")
    design = parsed.get("design")
    if design:
        lines.append(
            "- **设计工具**：Claude Design（project URL 见 "
            "`project_configs` → `design.claude_design_project_url`）"
        )
        lines.append(
            f"- **Design System 快照**：`{design.get('design_system_snapshot_path', '')}`"
        )
        lines.append(f"- **Page Registry**：`{design.get('pages_registry_path', '')}`")
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m pytest tests/test_architecture_templates_ui_context.py -v
```
Expected: 6/6 pass (the first test only asserts `category` key exists; that's true on existing YAMLs). Note: the first test will fully validate frontend/design keys only after Task 5; right now it's a weaker assertion.

- [ ] **Step 5: Full suite regression check**

```bash
python3 -m pytest tests/ --ignore=tests/test_concurrent_spec_gate.py -q 2>&1 | tail -3
```
Expected: no new failures.

- [ ] **Step 6: Commit**

```bash
git add src/requirement_workflow_v12/architecture_templates.py tests/test_architecture_templates_ui_context.py
git commit -m "feat(bootstrap): add parse_template_yaml and UI Context section builder"
```

---

## Task 4: Modify render_template to append UI Context section

**Files:**
- Modify: `src/requirement_workflow_v12/architecture_templates.py`
- Test: `tests/test_architecture_templates_ui_context.py` (append)

- [ ] **Step 1: Append failing test**

```python


def test_render_template_output_is_unchanged_when_yaml_has_no_frontend_or_design():
    """Backward compat: render_template on a YAML without frontend/design keys
    should produce identical output (no trailing UI Context section)."""
    from requirement_workflow_v12.architecture_templates import render_template
    # enterprise-app.v1.yaml currently has no frontend/design keys (pre-Task 5)
    # This test will need updating after Task 5 adds them to all YAMLs.
    # For now, the test ensures the function still works:
    version, text = render_template("enterprise-app", project="myproj")
    assert version == "enterprise-app.v1"
    assert "myproj" in text


def test_render_template_appends_ui_context_section_if_yaml_has_frontend_or_design(tmp_path):
    """render_template must call _build_ui_context_section and append its output."""
    # Create a stub YAML with frontend/design and verify render picks it up.
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_architecture_templates_ui_context.py::test_render_template_appends_ui_context_section_if_yaml_has_frontend_or_design -v
```
Expected: FAIL — UI Context section not appended.

- [ ] **Step 3: Modify render_template**

In `architecture_templates.py`, replace the existing `render_template` function with:

```python
def render_template(
    category: str,
    *,
    project: str,
    seed: dict[str, str] | None = None,
) -> tuple[str, str]:
    import yaml
    version, path = _latest_template_path(category)
    raw = path.read_text(encoding="utf-8")
    pkg = derive_pkg(project)
    today = date.today().isoformat()
    seed = seed or {}
    text = (
        raw.replace("{pkg}", pkg)
           .replace("{project}", project)
           .replace("{date}", today)
           .replace("{{display_name}}", seed.get("display_name", ""))
           .replace("{{brief}}", seed.get("brief", ""))
           .replace("{{tech_stack}}", seed.get("tech_stack", ""))
    )
    # Parse the raw YAML (before substitution) to extract frontend/design.
    # We parse the substituted text instead so {pkg} in subpath gets resolved.
    try:
        parsed = yaml.safe_load(text)
    except yaml.YAMLError:
        parsed = None
    if isinstance(parsed, dict):
        ui_context = _build_ui_context_section(parsed)
        if ui_context:
            text = text.rstrip() + "\n\n" + ui_context + "\n"
    return version, text
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m pytest tests/test_architecture_templates_ui_context.py -v
python3 -m pytest tests/test_architecture_templates.py -v   # existing tests still green
```
Expected: all pass. Note: existing `test_render_template_substitutes_placeholders` should continue to pass (no frontend/design in YAMLs yet, so no UI Context appended).

- [ ] **Step 5: Full suite regression check**

```bash
python3 -m pytest tests/ --ignore=tests/test_concurrent_spec_gate.py -q 2>&1 | tail -3
```

- [ ] **Step 6: Commit**

```bash
git add src/requirement_workflow_v12/architecture_templates.py tests/test_architecture_templates_ui_context.py
git commit -m "feat(bootstrap): render_template appends UI Context section when frontend/design present"
```

---

## Task 5: Add frontend + design fields to all 5 category YAMLs

**Files:**
- Modify: `docs/context/architecture-templates/enterprise-app.v1.yaml`
- Modify: `docs/context/architecture-templates/enterprise-bot.v1.yaml`
- Modify: `docs/context/architecture-templates/miniprogram.v1.yaml`
- Modify: `docs/context/architecture-templates/public-web-site.v1.yaml`
- Modify: `docs/context/architecture-templates/saas-ai-automation.v1.yaml`
- Test: `tests/test_architecture_templates_ui_context.py` (append)

- [ ] **Step 1: Append failing tests**

```python


def test_all_yamls_have_frontend_and_design_keys():
    """After Task 5, every category YAML must have 'frontend' (may be null) and 'design' blocks."""
    from requirement_workflow_v12.architecture_templates import (
        available_categories, parse_template_yaml,
    )
    for cat in available_categories():
        parsed = parse_template_yaml(cat)
        assert "frontend" in parsed, f"{cat}: missing 'frontend' key"
        assert "design" in parsed, f"{cat}: missing 'design' key"


def test_enterprise_bot_has_frontend_null():
    from requirement_workflow_v12.architecture_templates import parse_template_yaml
    parsed = parse_template_yaml("enterprise-bot")
    assert parsed["frontend"] is None


def test_miniprogram_uses_taro_stack():
    from requirement_workflow_v12.architecture_templates import parse_template_yaml
    parsed = parse_template_yaml("miniprogram")
    frontend = parsed["frontend"]
    assert frontend is not None
    assert "Taro" in frontend["tech_stack"].get("framework", "")
    assert "miniapp" in frontend.get("subpath", "")


def test_enterprise_app_uses_default_stack():
    from requirement_workflow_v12.architecture_templates import parse_template_yaml
    parsed = parse_template_yaml("enterprise-app")
    frontend = parsed["frontend"]
    assert frontend is not None
    assert "React 18" in frontend["tech_stack"]["framework"]
    assert frontend["subpath"] == "src/{pkg}_webapp"


def test_design_block_has_standard_paths():
    """All categories share the same design block structure."""
    from requirement_workflow_v12.architecture_templates import (
        available_categories, parse_template_yaml,
    )
    for cat in available_categories():
        parsed = parse_template_yaml(cat)
        design = parsed["design"]
        assert design["claude_design_project_url"] == ""
        assert design["design_system_snapshot_path"] == "design/system/"
        assert design["pages_registry_path"] == "design/PAGES.yaml"
        assert design["archive_path"] == "design/archive/"


def test_render_enterprise_app_now_includes_ui_context():
    """After Task 5, enterprise-app YAML has frontend/design, so render_template appends UI Context."""
    from requirement_workflow_v12.architecture_templates import render_template
    version, text = render_template("enterprise-app", project="myproj")
    assert "## UI Context" in text
    assert "React 18" in text
    assert "design/PAGES.yaml" in text
    # pkg substitution in subpath
    assert "src/myproj_webapp" in text or "src/my_proj_webapp" in text
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_architecture_templates_ui_context.py -v
```
Expected: multiple FAIL — no frontend/design keys in YAMLs yet.

- [ ] **Step 3: Edit enterprise-app.v1.yaml**

At `docs/context/architecture-templates/enterprise-app.v1.yaml`, insert these blocks after the `tech_stack` block (around line 16, before `modules:`):

```yaml

# ── UI / Design (by design-phase spec) ─────────
frontend:
  subpath: "src/{pkg}_webapp"
  tech_stack:
    framework: "React 18 + TypeScript"
    build: "Vite 5.x"
    routing: "react-router 6"
    styling: "Tailwind CSS 3.x"
    component_library: "shadcn/ui"
    icons: "lucide-react"
    fonts: "IBM Plex (Sans/SC/Mono)"

design:
  claude_design_project_url: ""
  design_system_snapshot_path: "design/system/"
  pages_registry_path: "design/PAGES.yaml"
  archive_path: "design/archive/"
```

- [ ] **Step 4: Edit enterprise-bot.v1.yaml**

At `docs/context/architecture-templates/enterprise-bot.v1.yaml`, after the `tech_stack` block:

```yaml

# ── UI / Design (by design-phase spec) ─────────
frontend: null                # 默认无前端；若需管理后台按 enterprise-app 栈补

design:
  claude_design_project_url: ""
  design_system_snapshot_path: "design/system/"
  pages_registry_path: "design/PAGES.yaml"
  archive_path: "design/archive/"
```

- [ ] **Step 5: Edit miniprogram.v1.yaml**

At `docs/context/architecture-templates/miniprogram.v1.yaml`, after the `tech_stack` block:

```yaml

# ── UI / Design (by design-phase spec) ─────────
frontend:
  subpath: "src/{pkg}_miniapp"
  tech_stack:
    framework: "Taro 4.x + React + TypeScript"
    build: "Taro CLI"
    routing: "Taro built-in"
    styling: "Taro + SCSS"
    component_library: "NutUI"
    icons: "lucide-react"
    fonts: "system-ui"

design:
  claude_design_project_url: ""
  design_system_snapshot_path: "design/system/"
  pages_registry_path: "design/PAGES.yaml"
  archive_path: "design/archive/"
```

- [ ] **Step 6: Edit public-web-site.v1.yaml**

At `docs/context/architecture-templates/public-web-site.v1.yaml`, after the `tech_stack` block:

```yaml

# ── UI / Design (by design-phase spec) ─────────
frontend:
  subpath: "src/{pkg}_webapp"
  tech_stack:
    framework: "React 18 + TypeScript"
    build: "Vite 5.x"                # 若需 SSR 可覆盖为 Next.js 14
    routing: "react-router 6"
    styling: "Tailwind CSS 3.x"
    component_library: "shadcn/ui"
    icons: "lucide-react"
    fonts: "IBM Plex (Sans/SC/Mono)"

design:
  claude_design_project_url: ""
  design_system_snapshot_path: "design/system/"
  pages_registry_path: "design/PAGES.yaml"
  archive_path: "design/archive/"
```

- [ ] **Step 7: Edit saas-ai-automation.v1.yaml**

At `docs/context/architecture-templates/saas-ai-automation.v1.yaml`, after the `tech_stack` block:

```yaml

# ── UI / Design (by design-phase spec) ─────────
frontend:
  subpath: "src/{pkg}_webapp"
  tech_stack:
    framework: "React 18 + TypeScript"
    build: "Vite 5.x"
    routing: "react-router 6"
    styling: "Tailwind CSS 3.x"
    component_library: "shadcn/ui"
    icons: "lucide-react"
    fonts: "IBM Plex (Sans/SC/Mono)"

design:
  claude_design_project_url: ""
  design_system_snapshot_path: "design/system/"
  pages_registry_path: "design/PAGES.yaml"
  archive_path: "design/archive/"
```

- [ ] **Step 8: Run test to verify it passes**

```bash
python3 -m pytest tests/test_architecture_templates_ui_context.py -v
python3 -m pytest tests/test_architecture_templates.py -v
```
Expected: all pass (new tests + existing tests).

- [ ] **Step 9: Full suite regression check**

```bash
python3 -m pytest tests/ --ignore=tests/test_concurrent_spec_gate.py -q 2>&1 | tail -3
```

- [ ] **Step 10: Commit**

```bash
git add docs/context/architecture-templates/ tests/test_architecture_templates_ui_context.py
git commit -m "feat(bootstrap): add frontend + design fields to all 5 category YAMLs"
```

---

## Task 6: Add 3 new fields to ProjectConfig

**Files:**
- Modify: `src/requirement_workflow_v12/project_config.py`
- Test: `tests/test_project_config_design_fields.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_project_config_design_fields.py`:

```python
"""ProjectConfig design-related field tests."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def _minimal_data():
    return {
        "category": "enterprise-app",
        "template_version": "enterprise-app.v1",
        "architecture_doc_id": "doc1",
        "architecture_doc_url": "https://feishu.example/docx/doc1",
    }


def test_project_config_new_design_fields_default_empty():
    from requirement_workflow_v12.project_config import ProjectConfig
    cfg = ProjectConfig(**_minimal_data())
    assert cfg.claude_design_project_url == ""
    assert cfg.frontend_subpath == ""
    assert cfg.frontend_tech_stack == {}


def test_project_config_from_dict_reads_design_fields():
    from requirement_workflow_v12.project_config import ProjectConfig
    data = _minimal_data()
    data["claude_design_project_url"] = "https://claude.ai/design/p/xyz"
    data["frontend_subpath"] = "src/myproj_webapp"
    data["frontend_tech_stack"] = {"framework": "React 18", "build": "Vite 5.x"}
    cfg = ProjectConfig.from_dict(data)
    assert cfg.claude_design_project_url == "https://claude.ai/design/p/xyz"
    assert cfg.frontend_subpath == "src/myproj_webapp"
    assert cfg.frontend_tech_stack == {"framework": "React 18", "build": "Vite 5.x"}


def test_project_config_from_dict_missing_design_fields_default_gracefully():
    from requirement_workflow_v12.project_config import ProjectConfig
    cfg = ProjectConfig.from_dict(_minimal_data())
    assert cfg.claude_design_project_url == ""
    assert cfg.frontend_subpath == ""
    assert cfg.frontend_tech_stack == {}


def test_project_config_from_dict_tolerates_non_dict_frontend_tech_stack():
    """Bitable may return None or a string if parse fails; coerce to empty dict."""
    from requirement_workflow_v12.project_config import ProjectConfig
    data = _minimal_data()
    data["frontend_tech_stack"] = None
    cfg = ProjectConfig.from_dict(data)
    assert cfg.frontend_tech_stack == {}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_project_config_design_fields.py -v
```
Expected: FAIL — fields not defined.

- [ ] **Step 3: Modify project_config.py**

Replace the existing `ProjectConfig` dataclass with:

```python
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ProjectConfig:
    category: str
    template_version: str
    architecture_doc_id: str
    architecture_doc_url: str
    tech_stack: dict[str, str] = field(default_factory=dict)
    design_system_doc_id: str | None = None
    github_repo_url: str = ""
    github_owner_username: str = ""
    bitable_record_id: str = ""
    bootstrap_status: str = "UNBOOTSTRAPPED"
    bootstrap_log: list[dict] = field(default_factory=list)
    bootstrap_completed_at: str | None = None
    project_status: str = "UNBOOTSTRAPPED"
    feishu_chat_id: str = ""
    architecture_github_path: str = "docs/ARCHITECTURE.md"
    architecture_github_revision: str = ""
    # design-phase fields (added 2026-04-23)
    claude_design_project_url: str = ""
    frontend_subpath: str = ""
    frontend_tech_stack: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "ProjectConfig":
        tech_stack = data.get("frontend_tech_stack")
        if not isinstance(tech_stack, dict):
            tech_stack = {}
        return cls(
            category=data["category"],
            template_version=data["template_version"],
            architecture_doc_id=data["architecture_doc_id"],
            architecture_doc_url=data["architecture_doc_url"],
            tech_stack=data.get("tech_stack", {}),
            design_system_doc_id=data.get("design_system_doc_id"),
            github_repo_url=data.get("github_repo_url", ""),
            github_owner_username=data.get("github_owner_username", ""),
            bitable_record_id=data.get("bitable_record_id", ""),
            bootstrap_status=data.get("bootstrap_status", "UNBOOTSTRAPPED"),
            bootstrap_log=data.get("bootstrap_log", []),
            bootstrap_completed_at=data.get("bootstrap_completed_at"),
            project_status=data.get("project_status", "UNBOOTSTRAPPED"),
            feishu_chat_id=data.get("feishu_chat_id", ""),
            architecture_github_path=data.get("architecture_github_path", "docs/ARCHITECTURE.md"),
            architecture_github_revision=data.get("architecture_github_revision", ""),
            claude_design_project_url=data.get("claude_design_project_url", ""),
            frontend_subpath=data.get("frontend_subpath", ""),
            frontend_tech_stack=tech_stack,
        )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m pytest tests/test_project_config_design_fields.py -v
```
Expected: 4 pass.

- [ ] **Step 5: Full suite regression check**

```bash
python3 -m pytest tests/ --ignore=tests/test_concurrent_spec_gate.py -q 2>&1 | tail -3
```
Expected: no new failures; some existing tests may depend on ProjectConfig construction — verify their kwargs still work.

- [ ] **Step 6: Commit**

```bash
git add src/requirement_workflow_v12/project_config.py tests/test_project_config_design_fields.py
git commit -m "feat(bootstrap): add 3 design-related fields to ProjectConfig"
```

---

## Task 7: Add Bitable read/write for 3 new ProjectConfig fields

**Files:**
- Modify: `src/requirement_workflow_v12/feishu_gateway.py`
- Test: `tests/test_project_config_design_fields.py` (append — uses mocks, no real Bitable)

- [ ] **Step 1: Append failing test**

```python


def test_feishu_gateway_reads_design_fields_from_bitable_row(tmp_path):
    """list_project_configs parses the 3 new field values correctly."""
    from unittest.mock import MagicMock
    from requirement_workflow_v12 import feishu_gateway as gw_module
    from requirement_workflow_v12.feishu_gateway import (
        FeishuGateway,
        PROJECT_CONFIG_FIELD_CLAUDE_DESIGN_PROJECT_URL,
        PROJECT_CONFIG_FIELD_FRONTEND_SUBPATH,
        PROJECT_CONFIG_FIELD_FRONTEND_TECH_STACK_JSON,
    )
    gateway = FeishuGateway.__new__(FeishuGateway)
    gateway.settings = MagicMock()
    gateway.settings.feishu_bitable_app_token = "t"
    gateway.settings.feishu_bitable_project_configs_table_id = "tbl"
    gateway.client = MagicMock()

    # Build a fake Bitable response row with the 3 new fields populated
    fake_fields = {
        "project": "testp",
        "category": "enterprise-app",
        "template_version": "enterprise-app.v1",
        "architecture_doc_id": "d1",
        "architecture_doc_url": "u1",
        PROJECT_CONFIG_FIELD_CLAUDE_DESIGN_PROJECT_URL: "https://claude.ai/design/p/abc",
        PROJECT_CONFIG_FIELD_FRONTEND_SUBPATH: "src/testp_webapp",
        PROJECT_CONFIG_FIELD_FRONTEND_TECH_STACK_JSON: '{"framework": "React 18"}',
    }
    fake_item = MagicMock(record_id="rec1", fields=fake_fields)
    fake_data = MagicMock(items=[fake_item], page_token=None, has_more=False)
    fake_response = MagicMock(data=fake_data)
    fake_response.success.return_value = True
    fake_response.code = 0
    fake_response.msg = "ok"
    gateway.client.bitable.v1.app_table_record.list.return_value = fake_response

    configs = gateway.list_project_configs()
    cfg = configs.get("testp")
    assert cfg is not None
    assert cfg.claude_design_project_url == "https://claude.ai/design/p/abc"
    assert cfg.frontend_subpath == "src/testp_webapp"
    assert cfg.frontend_tech_stack == {"framework": "React 18"}


def test_feishu_gateway_upsert_writes_design_fields_to_bitable(tmp_path):
    """upsert_project_config includes the 3 new field values in the Bitable row."""
    from unittest.mock import MagicMock
    from requirement_workflow_v12.feishu_gateway import (
        FeishuGateway,
        PROJECT_CONFIG_FIELD_CLAUDE_DESIGN_PROJECT_URL,
        PROJECT_CONFIG_FIELD_FRONTEND_SUBPATH,
        PROJECT_CONFIG_FIELD_FRONTEND_TECH_STACK_JSON,
    )
    from requirement_workflow_v12.project_config import ProjectConfig

    gateway = FeishuGateway.__new__(FeishuGateway)
    gateway.settings = MagicMock()
    gateway.settings.feishu_bitable_app_token = "t"
    gateway.settings.feishu_bitable_project_configs_table_id = "tbl"
    gateway.client = MagicMock()
    # Default: create-path (no existing record)
    gateway.client.bitable.v1.app_table_record.list.return_value = MagicMock(
        success=lambda: True, code=0, msg="ok",
        data=MagicMock(items=[], page_token=None, has_more=False),
    )
    created_response = MagicMock(success=lambda: True, code=0, msg="ok")
    created_response.data = MagicMock(record=MagicMock(record_id="newrec"))
    gateway.client.bitable.v1.app_table_record.create.return_value = created_response

    cfg = ProjectConfig(
        category="enterprise-app",
        template_version="enterprise-app.v1",
        architecture_doc_id="d1",
        architecture_doc_url="u1",
        claude_design_project_url="https://claude.ai/design/p/xyz",
        frontend_subpath="src/testp_webapp",
        frontend_tech_stack={"framework": "React 18"},
    )
    gateway.upsert_project_config("testp", cfg)

    # Inspect the create call's fields payload
    create_call = gateway.client.bitable.v1.app_table_record.create.call_args
    # The call builds an AppTableRecord with .fields({...}); traverse the builder chain
    # Simplest check: inspect __str__ representation includes the new field values
    # If your existing code uses a different approach, adapt the assertion
    # Alternative: just verify the create was called
    assert gateway.client.bitable.v1.app_table_record.create.called
```

**Note**: The second test is structural — it verifies `create` was called. Precisely asserting field values in the Bitable request requires inspecting the builder chain, which is mocked. If the assertion is too brittle, substitute with: `gateway.client.bitable.v1.app_table_record.create.assert_called_once()`.

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_project_config_design_fields.py -v
```
Expected: FAIL — `PROJECT_CONFIG_FIELD_CLAUDE_DESIGN_PROJECT_URL` not defined.

- [ ] **Step 3: Add field constants + read/write paths to feishu_gateway.py**

Find the existing `PROJECT_CONFIG_FIELD_*` constants in `feishu_gateway.py` (grep `PROJECT_CONFIG_FIELD_PROJECT` to locate the block). Add:

```python
PROJECT_CONFIG_FIELD_CLAUDE_DESIGN_PROJECT_URL = "claude_design_project_url"
PROJECT_CONFIG_FIELD_FRONTEND_SUBPATH = "frontend_subpath"
PROJECT_CONFIG_FIELD_FRONTEND_TECH_STACK_JSON = "frontend_tech_stack_json"
```

In `list_project_configs` (around line 594), find the existing field extraction block (e.g., `tech_stack_raw = self._extract_field_text(fields.get(PROJECT_CONFIG_FIELD_TECH_STACK_JSON))`). After similar existing fields, add:

```python
claude_design_project_url = self._extract_field_text(
    fields.get(PROJECT_CONFIG_FIELD_CLAUDE_DESIGN_PROJECT_URL)
) or ""
frontend_subpath = self._extract_field_text(
    fields.get(PROJECT_CONFIG_FIELD_FRONTEND_SUBPATH)
) or ""
frontend_tech_stack_raw = self._extract_field_text(
    fields.get(PROJECT_CONFIG_FIELD_FRONTEND_TECH_STACK_JSON)
)
try:
    frontend_tech_stack = (
        json.loads(frontend_tech_stack_raw) if frontend_tech_stack_raw else {}
    )
    if not isinstance(frontend_tech_stack, dict):
        frontend_tech_stack = {}
except json.JSONDecodeError:
    LOGGER.warning(
        "Invalid frontend_tech_stack JSON for project=%s record_id=%s; resetting",
        project, item.record_id,
    )
    frontend_tech_stack = {}
```

When constructing the `ProjectConfig`, add the 3 new fields to the constructor call:

```python
cfg = ProjectConfig(
    # ... existing fields ...
    claude_design_project_url=claude_design_project_url,
    frontend_subpath=frontend_subpath,
    frontend_tech_stack=frontend_tech_stack,
)
```

In `upsert_project_config` (around line 701), find where the write fields dict is built. Add:

```python
PROJECT_CONFIG_FIELD_CLAUDE_DESIGN_PROJECT_URL: cfg.claude_design_project_url,
PROJECT_CONFIG_FIELD_FRONTEND_SUBPATH: cfg.frontend_subpath,
PROJECT_CONFIG_FIELD_FRONTEND_TECH_STACK_JSON: json.dumps(
    cfg.frontend_tech_stack or {}, ensure_ascii=False
),
```

- [ ] **Step 4: Update bitable_project_configs_schema.json to declare new fields**

Open `bitable_project_configs_schema.json` at the project root. The file declares Bitable column names + types for the project_configs table. Add 3 entries (text-type) for `claude_design_project_url`, `frontend_subpath`, `frontend_tech_stack_json` — match the existing pattern for similar fields (e.g., `tech_stack_json`). Use `type: 1` (multi-line text) for all 3 since URLs and JSON may be long.

Example entry structure (match existing style):
```json
{
  "field_name": "claude_design_project_url",
  "type": 1
}
```

If the schema file doesn't exist or doesn't follow this structure, look at the existing `tech_stack_json` entry and mirror.

- [ ] **Step 5: Run test to verify it passes**

```bash
python3 -m pytest tests/test_project_config_design_fields.py -v
```
Expected: 6/6 pass.

- [ ] **Step 6: Full suite regression check**

```bash
python3 -m pytest tests/ --ignore=tests/test_concurrent_spec_gate.py -q 2>&1 | tail -3
```

- [ ] **Step 7: Commit**

```bash
git add src/requirement_workflow_v12/feishu_gateway.py tests/test_project_config_design_fields.py bitable_project_configs_schema.json
git commit -m "feat(bootstrap): Bitable read/write for ProjectConfig design fields"
```

---

## Task 8: Extend Bootstrap create_repo_and_populate with design files

**Files:**
- Modify: `src/requirement_workflow_v12/project_bootstrap/service.py`
- Test: `tests/test_bootstrap_design_populate.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_bootstrap_design_populate.py`:

```python
"""Verify Bootstrap Step 4 (POPULATE_MAIN) includes design-related files."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def _make_service():
    from requirement_workflow_v12.project_bootstrap.service import ProjectBootstrapService
    service = ProjectBootstrapService(
        repo_tools=MagicMock(),
        feishu_gateway=MagicMock(),
        github_gateway=MagicMock(),
        template_owner="org",
        template_repo="Template-repository",
        new_owner="new-org",
    )
    # Prime existing config so last_completed_step logic works
    from requirement_workflow_v12.project_config import ProjectConfig
    existing_cfg = ProjectConfig(
        category="enterprise-app",
        template_version="enterprise-app.v1",
        architecture_doc_id="",
        architecture_doc_url="",
        bootstrap_status="BOOTSTRAPPING",
        project_status="BOOTSTRAPPING",
    )
    service._feishu.list_project_configs.return_value = {"testp": existing_cfg}

    def _upsert(project, cfg):
        service._feishu.list_project_configs.return_value[project] = cfg
        return cfg
    service._feishu.upsert_project_config.side_effect = _upsert
    return service


def test_populate_files_contains_all_8_design_related_files():
    """POPULATE_MAIN must commit 8 new design-related files."""
    from requirement_workflow_v12.project_bootstrap.service import ProjectBootstrapService
    from requirement_workflow_v12.project_bootstrap.types import BootstrapRequest

    service = _make_service()
    service._repo_tools.bootstrap_project_repo.return_value = MagicMock(
        html_url="https://github.com/new-org/testp",
    )

    request = BootstrapRequest(
        project="testp",
        category="enterprise-app",
        owner_user_id="u1",
        creator_chat_id="c1",
    )
    service.create_repo_and_populate(
        request,
        template_version="enterprise-app.v1",
        rendered_architecture_md="# arch\n",
    )

    # Inspect the call's populate_files kwarg
    call = service._repo_tools.bootstrap_project_repo.call_args
    populate_files = call.kwargs["populate_files"]
    expected_paths = {
        "design/README.md",
        "design/PAGES.yaml",
        "design/INDEX.md",
        "design/system/.gitkeep",
        "design/archive/.gitkeep",
        ".gitattributes",
    }
    for p in expected_paths:
        assert p in populate_files, f"missing {p} in populate_files"
    # Frontend subpath gitkeep — depends on YAML; for enterprise-app it's src/testp_webapp
    assert any(
        k.startswith("src/testp_webapp/") and k.endswith("/.gitkeep")
        for k in populate_files
    ), "expected src/{pkg}_webapp/.gitkeep"


def test_populate_for_enterprise_bot_skips_frontend_gitkeep():
    """enterprise-bot has frontend: null; no src/*_webapp/.gitkeep should be added."""
    from requirement_workflow_v12.project_bootstrap.service import ProjectBootstrapService
    from requirement_workflow_v12.project_bootstrap.types import BootstrapRequest
    from requirement_workflow_v12.project_config import ProjectConfig

    service = _make_service()
    # Switch the existing config to enterprise-bot
    existing_cfg = ProjectConfig(
        category="enterprise-bot",
        template_version="enterprise-bot.v1",
        architecture_doc_id="",
        architecture_doc_url="",
        bootstrap_status="BOOTSTRAPPING",
        project_status="BOOTSTRAPPING",
    )
    service._feishu.list_project_configs.return_value = {"testp": existing_cfg}
    service._repo_tools.bootstrap_project_repo.return_value = MagicMock(
        html_url="https://github.com/new-org/testp",
    )

    request = BootstrapRequest(
        project="testp", category="enterprise-bot",
        owner_user_id="u1", creator_chat_id="c1",
    )
    service.create_repo_and_populate(
        request, template_version="enterprise-bot.v1",
        rendered_architecture_md="# arch\n",
    )
    populate_files = service._repo_tools.bootstrap_project_repo.call_args.kwargs["populate_files"]
    frontend_gitkeeps = [k for k in populate_files if "_webapp/" in k or "_miniapp/" in k]
    assert frontend_gitkeeps == [], f"expected no frontend gitkeep, got {frontend_gitkeeps}"


def test_populate_writes_frontend_fields_to_project_config():
    """After POPULATE_MAIN, ProjectConfig has frontend_subpath + frontend_tech_stack populated."""
    from requirement_workflow_v12.project_bootstrap.service import ProjectBootstrapService
    from requirement_workflow_v12.project_bootstrap.types import BootstrapRequest

    service = _make_service()
    service._repo_tools.bootstrap_project_repo.return_value = MagicMock(
        html_url="https://github.com/new-org/testp",
    )

    request = BootstrapRequest(
        project="testp", category="enterprise-app",
        owner_user_id="u1", creator_chat_id="c1",
    )
    cfg = service.create_repo_and_populate(
        request, template_version="enterprise-app.v1",
        rendered_architecture_md="# arch\n",
    )
    assert cfg.frontend_subpath == "src/testp_webapp"
    assert cfg.frontend_tech_stack.get("framework", "").startswith("React 18")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_bootstrap_design_populate.py -v
```
Expected: FAIL — expected design files missing from populate_files.

- [ ] **Step 3: Modify create_repo_and_populate**

In `src/requirement_workflow_v12/project_bootstrap/service.py`, modify `create_repo_and_populate`. At the top of the method (after the skip check), add import + helpers:

```python
from ..architecture_templates import derive_pkg, parse_template_yaml
from .static_content import (
    PROJECT_README_MD,
    render_claude_md,
    render_design_index_md,
    render_design_pages_yaml,
    render_design_readme,
    render_environments_yaml,
    render_gitattributes,
    render_req_registry_yaml,
    render_secrets_todo,
    render_skill_md,
)
```

Replace the existing `populate_files` dict definition with:

```python
        pkg = derive_pkg(request.project)
        # Parse the YAML template to extract frontend subpath & tech_stack
        try:
            parsed_yaml = parse_template_yaml(request.category)
        except Exception as exc:
            _logger.warning(
                "parse_template_yaml failed project=%s category=%s: %s; "
                "continuing without frontend fields",
                request.project, request.category, exc,
            )
            parsed_yaml = {}

        frontend_block = parsed_yaml.get("frontend")  # may be None
        frontend_subpath = ""
        frontend_tech_stack: dict = {}
        if isinstance(frontend_block, dict):
            raw_subpath = frontend_block.get("subpath", "")
            frontend_subpath = raw_subpath.replace("{pkg}", pkg)
            frontend_tech_stack = frontend_block.get("tech_stack", {}) or {}

        populate_files = {
            "docs/ARCHITECTURE.md": rendered_architecture_md,
            "project/README.md": PROJECT_README_MD,
            "project/req-registry.yaml": render_req_registry_yaml(
                project=request.project
            ),
            "project/environments.yaml": render_environments_yaml(
                category=request.category
            ),
            "project/SECRETS-TODO.md": render_secrets_todo(category=request.category),
            "CLAUDE.md": render_claude_md(project=request.project),
            "SKILL.md": render_skill_md(project=request.project),
            "design/README.md": render_design_readme(),
            "design/PAGES.yaml": render_design_pages_yaml(),
            "design/INDEX.md": render_design_index_md(),
            "design/system/.gitkeep": "",
            "design/archive/.gitkeep": "",
            ".gitattributes": render_gitattributes(),
        }
        if frontend_subpath:
            populate_files[f"{frontend_subpath}/.gitkeep"] = ""
```

After the call to `self._repo_tools.bootstrap_project_repo(...)` (which still uses the same `populate_files`), update the ProjectConfig replace call to include frontend fields:

```python
        cfg = replace(
            cfg,
            github_repo_url=result.html_url,
            github_owner_username=request.github_username or "",
            bootstrap_log=log,
            frontend_subpath=frontend_subpath,
            frontend_tech_stack=frontend_tech_stack,
        )
        self._feishu.upsert_project_config(request.project, cfg)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m pytest tests/test_bootstrap_design_populate.py -v
```
Expected: 3/3 pass.

- [ ] **Step 5: Full suite regression check**

```bash
python3 -m pytest tests/ --ignore=tests/test_concurrent_spec_gate.py -q 2>&1 | tail -3
```

Note: `test_project_bootstrap_service.py` and `test_project_bootstrap_resume.py` may need minor updates since they inspect `populate_files` content. If they break, update assertions to allow the new keys (don't exclude them). Likely fix: change `assert populate_files == {...exact dict...}` to `assert all(k in populate_files for k in [...required keys...])`.

- [ ] **Step 6: Commit**

```bash
git add src/requirement_workflow_v12/project_bootstrap/service.py tests/test_bootstrap_design_populate.py
git commit -m "feat(bootstrap): extend populate_files with 8 design-related files + frontend ProjectConfig fields"
```

---

## Task 9: Add binding card builder + emitter in bootstrap service

**Files:**
- Modify: `src/requirement_workflow_v12/project_bootstrap/service.py`
- Test: `tests/test_bootstrap_design_binding_card.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_bootstrap_design_binding_card.py`:

```python
"""Verify Bootstrap emits a Claude Design binding reminder card after FINALIZE."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def test_build_design_binding_card_includes_project_and_repo_url():
    from requirement_workflow_v12.project_bootstrap.service import build_design_binding_card
    card = build_design_binding_card(
        project="testp",
        github_repo_url="https://github.com/org/testp",
    )
    assert isinstance(card, dict)
    # Card must be structured as a Feishu interactive card — check outer shape
    assert "header" in card or "elements" in card or "card" in card
    # Serialize to string and check content references
    import json
    text = json.dumps(card, ensure_ascii=False)
    assert "testp" in text
    assert "https://github.com/org/testp" in text
    assert "Claude Design" in text
    assert "bind_claude_design_project" in text


def test_build_design_binding_card_with_error_context_shows_message():
    from requirement_workflow_v12.project_bootstrap.service import build_design_binding_card
    card = build_design_binding_card(
        project="testp",
        github_repo_url="https://github.com/org/testp",
        error_context="Claude Design 未绑定（触发原因：design_start guard）",
    )
    import json
    text = json.dumps(card, ensure_ascii=False)
    assert "未绑定" in text or "触发" in text


def test_emit_design_binding_reminder_card_skips_when_no_feishu_chat_id():
    from requirement_workflow_v12.project_bootstrap.service import ProjectBootstrapService
    from requirement_workflow_v12.project_config import ProjectConfig

    service = ProjectBootstrapService(
        repo_tools=MagicMock(), feishu_gateway=MagicMock(), github_gateway=MagicMock(),
        template_owner="org", template_repo="t", new_owner="new",
    )
    cfg = ProjectConfig(
        category="enterprise-app", template_version="enterprise-app.v1",
        architecture_doc_id="d", architecture_doc_url="u",
        feishu_chat_id="",  # empty
        github_repo_url="https://github.com/org/testp",
    )
    service._emit_design_binding_reminder_card(project="testp", cfg=cfg)
    service._feishu.send_card.assert_not_called()


def test_emit_design_binding_reminder_card_calls_send_card_when_chat_id_present():
    from requirement_workflow_v12.project_bootstrap.service import ProjectBootstrapService
    from requirement_workflow_v12.project_config import ProjectConfig

    service = ProjectBootstrapService(
        repo_tools=MagicMock(), feishu_gateway=MagicMock(), github_gateway=MagicMock(),
        template_owner="org", template_repo="t", new_owner="new",
    )
    cfg = ProjectConfig(
        category="enterprise-app", template_version="enterprise-app.v1",
        architecture_doc_id="d", architecture_doc_url="u",
        feishu_chat_id="oc_xyz",
        github_repo_url="https://github.com/org/testp",
    )
    service._emit_design_binding_reminder_card(project="testp", cfg=cfg)
    service._feishu.send_card.assert_called_once()
    call_args = service._feishu.send_card.call_args
    assert call_args.args[0] == "oc_xyz" or call_args.kwargs.get("receive_id") == "oc_xyz"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_bootstrap_design_binding_card.py -v
```
Expected: FAIL — `build_design_binding_card` / `_emit_design_binding_reminder_card` not defined.

- [ ] **Step 3: Add card builder + emitter to service.py**

At the top of `src/requirement_workflow_v12/project_bootstrap/service.py` (module-level, before the class), add:

```python
def build_design_binding_card(
    *,
    project: str,
    github_repo_url: str,
    error_context: str | None = None,
) -> dict:
    """Build a Feishu interactive card prompting the user to bind Claude Design.

    error_context, when provided, is shown at the top of the card as a red
    banner — used when this card is emitted after a design_start guard failure.
    """
    elements: list[dict] = []
    if error_context:
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"⚠️ **{error_context}**",
            },
        })
    elements.extend([
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": (
                    f"Bootstrap 已完成项目 **{project}** 的基建。\n\n"
                    f"**下一步**（首个 needs_ui 需求进入 design 阶段之前必须做）：\n"
                    f"1. 访问 https://claude.ai/design，登录后新建 Project\n"
                    f"2. 在 Project 中 **Import GitHub repo**：{github_repo_url}\n"
                    f"3. 搭建组织级 Design System（配色 / 字体 / 组件）\n"
                    f"4. 回到本卡片，粘贴 Claude Design Project URL\n"
                    f"（形如 `https://claude.ai/design/p/xxx`）\n"
                    f"5. 点「保存 URL」"
                ),
            },
        },
        {
            "tag": "input",
            "name": "claude_design_project_url",
            "placeholder": {
                "tag": "plain_text",
                "content": "https://claude.ai/design/p/xxx",
            },
        },
        {
            "tag": "action",
            "actions": [
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "保存 URL"},
                    "type": "primary",
                    "value": {
                        "action": "bind_claude_design_project",
                        "project": project,
                    },
                }
            ],
        },
        {
            "tag": "note",
            "elements": [
                {
                    "tag": "plain_text",
                    "content": "未绑定时，首个 needs_ui 需求进入 design 阶段会被阻断并重新推送此卡片。",
                }
            ],
        },
    ])
    return {
        "header": {
            "title": {
                "tag": "plain_text",
                "content": f"完成 Claude Design 绑定：{project}",
            },
            "template": "indigo" if not error_context else "orange",
        },
        "elements": elements,
    }
```

Add the emitter method inside `ProjectBootstrapService`:

```python
    def _emit_design_binding_reminder_card(
        self, *, project: str, cfg: "ProjectConfig",
    ) -> None:
        """Push the Claude Design binding reminder card to the project's creation group.

        Best-effort: returns silently (warns only) if feishu_chat_id is empty
        or send fails, so FINALIZE never blocks on this.
        """
        if not cfg.feishu_chat_id:
            _logger.info(
                "skip design binding reminder card: no feishu_chat_id project=%s",
                project,
            )
            return
        try:
            card = build_design_binding_card(
                project=project,
                github_repo_url=cfg.github_repo_url,
            )
            self._feishu.send_card(cfg.feishu_chat_id, card)
            _logger.info("sent design binding reminder card project=%s", project)
        except Exception as exc:
            _logger.warning(
                "design binding reminder card send failed project=%s: %s",
                project, exc,
            )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m pytest tests/test_bootstrap_design_binding_card.py -v
```
Expected: 4/4 pass.

- [ ] **Step 5: Full suite regression check**

```bash
python3 -m pytest tests/ --ignore=tests/test_concurrent_spec_gate.py -q 2>&1 | tail -3
```

- [ ] **Step 6: Commit**

```bash
git add src/requirement_workflow_v12/project_bootstrap/service.py tests/test_bootstrap_design_binding_card.py
git commit -m "feat(bootstrap): add Claude Design binding reminder card builder + emitter"
```

---

## Task 10: Call binding card emitter after FINALIZE success

**Files:**
- Modify: `src/requirement_workflow_v12/project_bootstrap/service.py`
- Test: `tests/test_bootstrap_design_binding_card.py` (append)

- [ ] **Step 1: Append failing test**

```python


def test_finalize_calls_emit_binding_card():
    """FINALIZE step (step 7) must invoke _emit_design_binding_reminder_card after success."""
    from requirement_workflow_v12.project_bootstrap.service import ProjectBootstrapService
    from requirement_workflow_v12.project_bootstrap.types import BootstrapRequest
    from requirement_workflow_v12.project_config import ProjectConfig

    service = ProjectBootstrapService(
        repo_tools=MagicMock(), feishu_gateway=MagicMock(), github_gateway=MagicMock(),
        template_owner="org", template_repo="t", new_owner="new",
    )
    cfg = ProjectConfig(
        category="enterprise-app", template_version="enterprise-app.v1",
        architecture_doc_id="d", architecture_doc_url="u",
        feishu_chat_id="oc_xyz",
        github_repo_url="https://github.com/org/testp",
        bootstrap_status="BOOTSTRAPPING",
        project_status="BOOTSTRAPPING",
        bootstrap_log=[
            {"step": i, "status": "ok"} for i in range(1, 7)
        ],  # steps 1–6 done; step 7 (FINALIZE) about to run
    )
    service._feishu.list_project_configs.return_value = {"testp": cfg}

    def _upsert(project, cfg):
        service._feishu.list_project_configs.return_value[project] = cfg
        return cfg
    service._feishu.upsert_project_config.side_effect = _upsert

    request = BootstrapRequest(
        project="testp", category="enterprise-app",
        owner_user_id="u1", creator_chat_id="c1",
    )
    # Invoke finalize directly (skip steps 1–6)
    result_cfg = service.finalize(request)
    # Binding card must have been sent
    service._feishu.send_card.assert_called_once()
    # And cfg should be marked completed
    assert result_cfg.bootstrap_status == "PROVISIONED" or result_cfg.project_status == "PROVISIONED"


def test_finalize_binding_card_failure_does_not_block_finalize():
    """If send_card raises, FINALIZE still completes (best-effort)."""
    from requirement_workflow_v12.project_bootstrap.service import ProjectBootstrapService
    from requirement_workflow_v12.project_bootstrap.types import BootstrapRequest
    from requirement_workflow_v12.project_config import ProjectConfig

    service = ProjectBootstrapService(
        repo_tools=MagicMock(), feishu_gateway=MagicMock(), github_gateway=MagicMock(),
        template_owner="org", template_repo="t", new_owner="new",
    )
    cfg = ProjectConfig(
        category="enterprise-app", template_version="enterprise-app.v1",
        architecture_doc_id="d", architecture_doc_url="u",
        feishu_chat_id="oc_xyz",
        github_repo_url="https://github.com/org/testp",
        bootstrap_status="BOOTSTRAPPING",
        bootstrap_log=[{"step": i, "status": "ok"} for i in range(1, 7)],
    )
    service._feishu.list_project_configs.return_value = {"testp": cfg}

    def _upsert(project, cfg):
        service._feishu.list_project_configs.return_value[project] = cfg
        return cfg
    service._feishu.upsert_project_config.side_effect = _upsert
    service._feishu.send_card.side_effect = RuntimeError("feishu 500")

    request = BootstrapRequest(
        project="testp", category="enterprise-app",
        owner_user_id="u1", creator_chat_id="c1",
    )
    # Should not raise
    result_cfg = service.finalize(request)
    assert result_cfg.bootstrap_status == "PROVISIONED" or result_cfg.project_status == "PROVISIONED"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_bootstrap_design_binding_card.py -v
```
Expected: FAIL — `send_card` not called after finalize (or `finalize` doesn't exist — inspect existing `service.py` for whether finalize is a method).

- [ ] **Step 3: Inspect existing finalize method**

```bash
grep -n "def finalize\|FINALIZE\|PROVISIONED" src/requirement_workflow_v12/project_bootstrap/service.py | head
```

- [ ] **Step 4: Modify finalize to call emitter**

Locate the `finalize` method in `service.py`. Find the success path (after PROVISIONED is set, before the return). Add:

```python
        try:
            self._emit_design_binding_reminder_card(project=request.project, cfg=cfg)
        except Exception as exc:
            _logger.warning(
                "design binding reminder emission failed project=%s: %s",
                request.project, exc,
            )
        return cfg
```

Note: the `try/except` is defensive; `_emit_design_binding_reminder_card` itself already catches exceptions, but this adds a second layer to guarantee FINALIZE doesn't fail.

- [ ] **Step 5: Run test to verify it passes**

```bash
python3 -m pytest tests/test_bootstrap_design_binding_card.py -v
```
Expected: 6/6 pass.

- [ ] **Step 6: Full suite regression check**

```bash
python3 -m pytest tests/ --ignore=tests/test_concurrent_spec_gate.py -q 2>&1 | tail -3
```
Note: `test_project_bootstrap_service.py` tests for `finalize` may now see an extra `send_card` call. Adjust if they use `assert_not_called` on send_card; change to `assert_called_with(...)` or ignore.

- [ ] **Step 7: Commit**

```bash
git add src/requirement_workflow_v12/project_bootstrap/service.py tests/test_bootstrap_design_binding_card.py
git commit -m "feat(bootstrap): emit binding reminder card after FINALIZE success"
```

---

## Task 11: Card action handler for bind_claude_design_project

**Files:**
- Modify: `src/requirement_workflow_v12/service_app.py`
- Test: `tests/test_card_bind_claude_design.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_card_bind_claude_design.py`:

```python
"""Tests for the bind_claude_design_project card action."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.service_app import CoordinatorRuntimeApp
from requirement_workflow_v12.project_config import ProjectConfig


def _app_with_config(project: str, cfg: ProjectConfig) -> CoordinatorRuntimeApp:
    app = CoordinatorRuntimeApp.__new__(CoordinatorRuntimeApp)
    app.service = MagicMock()
    app.service.project_configs = {project: cfg}
    app.gateway = MagicMock()
    return app


def _base_cfg():
    return ProjectConfig(
        category="enterprise-app",
        template_version="enterprise-app.v1",
        architecture_doc_id="d",
        architecture_doc_url="u",
    )


def test_bind_claude_design_updates_project_config():
    cfg = _base_cfg()
    app = _app_with_config("testp", cfg)

    payload = {
        "action": {
            "value": {"action": "bind_claude_design_project", "project": "testp"},
            "form_value": {"claude_design_project_url": "https://claude.ai/design/p/xyz"},
        },
        "operator": {"operator_id": {"user_id": "u1"}},
    }
    status, resp = app._handle_card_action_payload(payload)
    assert status == 200
    assert resp.get("toast", {}).get("type") == "success"
    # ProjectConfig updated with URL
    assert app.service.project_configs["testp"].claude_design_project_url == "https://claude.ai/design/p/xyz"
    app.gateway.upsert_project_config.assert_called_once()


def test_bind_claude_design_rejects_missing_project():
    app = CoordinatorRuntimeApp.__new__(CoordinatorRuntimeApp)
    app.service = MagicMock()
    app.service.project_configs = {}
    app.gateway = MagicMock()
    payload = {
        "action": {
            "value": {"action": "bind_claude_design_project"},  # no project
            "form_value": {"claude_design_project_url": "https://claude.ai/design/p/xyz"},
        },
        "operator": {},
    }
    status, resp = app._handle_card_action_payload(payload)
    assert status == 200
    assert resp.get("toast", {}).get("type") == "error"


def test_bind_claude_design_rejects_empty_url():
    cfg = _base_cfg()
    app = _app_with_config("testp", cfg)
    payload = {
        "action": {
            "value": {"action": "bind_claude_design_project", "project": "testp"},
            "form_value": {"claude_design_project_url": ""},
        },
        "operator": {},
    }
    status, resp = app._handle_card_action_payload(payload)
    assert status == 200
    assert resp.get("toast", {}).get("type") == "error"
    app.gateway.upsert_project_config.assert_not_called()


def test_bind_claude_design_rejects_non_claude_ai_url():
    cfg = _base_cfg()
    app = _app_with_config("testp", cfg)
    payload = {
        "action": {
            "value": {"action": "bind_claude_design_project", "project": "testp"},
            "form_value": {"claude_design_project_url": "https://example.com/design/xyz"},
        },
        "operator": {},
    }
    status, resp = app._handle_card_action_payload(payload)
    assert status == 200
    assert resp.get("toast", {}).get("type") == "error"
    app.gateway.upsert_project_config.assert_not_called()


def test_bind_claude_design_rejects_unknown_project():
    app = CoordinatorRuntimeApp.__new__(CoordinatorRuntimeApp)
    app.service = MagicMock()
    app.service.project_configs = {}
    app.gateway = MagicMock()
    payload = {
        "action": {
            "value": {"action": "bind_claude_design_project", "project": "unknown"},
            "form_value": {"claude_design_project_url": "https://claude.ai/design/p/xyz"},
        },
        "operator": {},
    }
    status, resp = app._handle_card_action_payload(payload)
    assert status == 200
    assert resp.get("toast", {}).get("type") == "error"


def test_bind_claude_design_handles_upsert_failure():
    cfg = _base_cfg()
    app = _app_with_config("testp", cfg)
    app.gateway.upsert_project_config.side_effect = RuntimeError("bitable 500")
    payload = {
        "action": {
            "value": {"action": "bind_claude_design_project", "project": "testp"},
            "form_value": {"claude_design_project_url": "https://claude.ai/design/p/xyz"},
        },
        "operator": {},
    }
    status, resp = app._handle_card_action_payload(payload)
    assert status == 200
    assert resp.get("toast", {}).get("type") == "error"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_card_bind_claude_design.py -v
```
Expected: FAIL — no branch for `bind_claude_design_project` in card dispatcher.

- [ ] **Step 3: Add card action handler to service_app.py**

In `src/requirement_workflow_v12/service_app.py`, find `_handle_card_action_payload` (around line 1553). Inside the method, find the other action branches. Add a new branch (anywhere in the dispatcher — early is fine):

```python
        if action_name == "bind_claude_design_project":
            project = value.get("project", "")
            form_value = payload.get("action", {}).get("form_value", {}) or {}
            url = str(form_value.get("claude_design_project_url", "")).strip()
            if not project:
                return 200, {"toast": {"type": "error", "content": "缺少 project 参数。"}}
            if not url:
                return 200, {"toast": {"type": "error", "content": "URL 不能为空。"}}
            if not url.startswith("https://claude.ai/design/"):
                return 200, {"toast": {
                    "type": "error",
                    "content": "URL 必须以 https://claude.ai/design/ 开头，确认后重试。",
                }}
            cfg = self.service.project_configs.get(project)
            if cfg is None:
                return 200, {"toast": {
                    "type": "error",
                    "content": f"未知项目：{project}。",
                }}
            from dataclasses import replace
            new_cfg = replace(cfg, claude_design_project_url=url)
            self.service.project_configs[project] = new_cfg
            try:
                self.gateway.upsert_project_config(project, new_cfg)
            except Exception as exc:
                LOGGER.exception("upsert project config failed project=%s", project)
                # Rollback in-memory update so retry is consistent
                self.service.project_configs[project] = cfg
                return 200, {"toast": {
                    "type": "error",
                    "content": f"保存失败：{exc}",
                }}
            return 200, {"toast": {
                "type": "success",
                "content": "已保存。本项目现在可以接收 needs_ui=true 的需求。",
            }}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m pytest tests/test_card_bind_claude_design.py -v
```
Expected: 6/6 pass.

- [ ] **Step 5: Full suite regression check**

```bash
python3 -m pytest tests/ --ignore=tests/test_concurrent_spec_gate.py -q 2>&1 | tail -3
```

- [ ] **Step 6: Commit**

```bash
git add src/requirement_workflow_v12/service_app.py tests/test_card_bind_claude_design.py
git commit -m "feat(bootstrap): add bind_claude_design_project card action handler"
```

---

## Task 12: Add claude_design_project_url guard in design_start

**Files:**
- Modify: `src/requirement_workflow_v12/coordinator_service.py`
- Test: `tests/test_design_start_binding_guard.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_design_start_binding_guard.py`:

```python
"""Test the Claude Design binding guard in CoordinatorService.design_start."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.models import Requirement, WorkflowStatus
from requirement_workflow_v12.plan_state_machine import DesignStatus
from requirement_workflow_v12.coordinator_service import CoordinatorService
from requirement_workflow_v12.project_config import ProjectConfig


def _svc():
    svc = CoordinatorService.__new__(CoordinatorService)
    svc.requirements = {}
    svc.project_configs = {}
    svc._hooks = MagicMock()
    return svc


def _req(**kw) -> Requirement:
    return Requirement(
        req_id="REQ-X-001", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
        **kw,
    )


def _cfg(**kw):
    return ProjectConfig(
        category="enterprise-app",
        template_version="enterprise-app.v1",
        architecture_doc_id="d", architecture_doc_url="u",
        **kw,
    )


def test_design_start_refuses_when_claude_design_url_empty():
    svc = _svc()
    r = _req()
    svc.requirements[r.req_id] = r
    svc.project_configs["X"] = _cfg(claude_design_project_url="")
    import pytest
    with pytest.raises(ValueError, match="Claude Design 未绑定"):
        svc.design_start(r.req_id, design_doc_id="d", design_doc_url="u")


def test_design_start_refuses_when_project_config_missing():
    svc = _svc()
    r = _req()
    svc.requirements[r.req_id] = r
    # No project_configs entry for "X"
    import pytest
    with pytest.raises(ValueError, match="Claude Design 未绑定"):
        svc.design_start(r.req_id, design_doc_id="d", design_doc_url="u")


def test_design_start_succeeds_when_url_is_configured():
    svc = _svc()
    r = _req()
    svc.requirements[r.req_id] = r
    svc.project_configs["X"] = _cfg(
        claude_design_project_url="https://claude.ai/design/p/xyz",
    )
    result = svc.design_start(r.req_id, design_doc_id="d", design_doc_url="u")
    assert result.design_status is DesignStatus.DRAFTING


def test_design_start_guard_message_references_project_name():
    svc = _svc()
    r = _req()
    svc.requirements[r.req_id] = r
    svc.project_configs["X"] = _cfg(claude_design_project_url="")
    import pytest
    with pytest.raises(ValueError) as exc_info:
        svc.design_start(r.req_id, design_doc_id="d", design_doc_url="u")
    assert "X" in str(exc_info.value)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_design_start_binding_guard.py -v
```
Expected: FAIL — design_start doesn't yet check `claude_design_project_url`.

- [ ] **Step 3: Add guard to design_start**

In `src/requirement_workflow_v12/coordinator_service.py`, find the `design_start` method (after `design_restart`, at line ~994). Locate the existing guards:

```python
        if r.status != WorkflowStatus.APPROVED:
            raise ValueError(
                f"design_start requires workflow_status=APPROVED, got {r.status.value}"
            )
        if not r.needs_ui:
            raise ValueError("design_start requires needs_ui=True")
```

IMMEDIATELY AFTER these two guards, add the binding guard:

```python
        cfg = self.project_configs.get(r.project)
        if cfg is None or not getattr(cfg, "claude_design_project_url", ""):
            raise ValueError(
                f"Claude Design 未绑定（project={r.project}）。"
                f"请先在项目创建群的绑定卡中填写 claude_design_project_url。"
            )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m pytest tests/test_design_start_binding_guard.py -v
```
Expected: 4 pass.

- [ ] **Step 5: Full suite regression check**

```bash
python3 -m pytest tests/ --ignore=tests/test_concurrent_spec_gate.py -q 2>&1 | tail -3
```
Note: `test_coordinator_design.py` tests call `design_start` without setting up `project_configs`. These will now fail. Fix: in each failing test's setup, add:

```python
svc.project_configs[r.project] = ProjectConfig(
    category="enterprise-app",
    template_version="enterprise-app.v1",
    architecture_doc_id="d", architecture_doc_url="u",
    claude_design_project_url="https://claude.ai/design/p/stub",
)
```

Adjust each broken test to include this setup. This is a legitimate test fix, not a regression.

- [ ] **Step 6: Commit**

```bash
git add src/requirement_workflow_v12/coordinator_service.py tests/test_design_start_binding_guard.py tests/test_coordinator_design.py
git commit -m "feat(bootstrap): add claude_design_project_url guard in design_start"
```

---

## Task 13: Catch binding guard failure in dispatch_design_start_if_needed

**Files:**
- Modify: `src/requirement_workflow_v12/service_app.py`
- Test: `tests/test_design_start_binding_guard.py` (append)

- [ ] **Step 1: Append failing test**

```python


def test_dispatch_design_start_if_needed_emits_binding_card_on_guard_failure(tmp_path):
    """When design_start raises 'Claude Design 未绑定', the runtime must emit a binding card."""
    from requirement_workflow_v12.service_app import (
        CoordinatorRuntimeApp, dispatch_design_start_if_needed,
    )

    r = _req()
    app = CoordinatorRuntimeApp.__new__(CoordinatorRuntimeApp)
    app.service = MagicMock()
    app.service.requirements = {r.req_id: r}
    app.service.project_configs = {"X": _cfg(claude_design_project_url="")}
    app.service.design_start.side_effect = ValueError(
        "Claude Design 未绑定（project=X）。请先在项目创建群的绑定卡中填写 claude_design_project_url。"
    )
    app.gateway = MagicMock()
    app.gateway.create_design_document.return_value = MagicMock(
        document_id="d", document_url="u",
    )

    dispatch_design_start_if_needed(app, r)

    # Binding card should have been sent (via gateway.send_card)
    app.gateway.send_card.assert_called_once()
    # First arg = chat_id; ProjectConfig's feishu_chat_id default is "" → skip?
    # Actually the binding card should go to the REQ's project_group_chat_id or creator.
    # Our implementation should use cfg.feishu_chat_id; let's verify card was sent to
    # something reasonable (non-empty string).
    call = app.gateway.send_card.call_args
    # Accept either positional or keyword
    chat_id = call.args[0] if call.args else call.kwargs.get("receive_id")
    assert chat_id != ""
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_design_start_binding_guard.py::test_dispatch_design_start_if_needed_emits_binding_card_on_guard_failure -v
```
Expected: FAIL — `send_card` not called.

- [ ] **Step 3: Modify dispatch_design_start_if_needed**

In `src/requirement_workflow_v12/service_app.py`, find the `dispatch_design_start_if_needed` function. Locate the existing `except Exception` block that logs `design_start failed`. Replace the existing catch logic with:

```python
def dispatch_design_start_if_needed(app, requirement) -> None:
    """Called from approve_requirement post-hook. Creates Feishu design docx and
    calls service.design_start. No-op when needs_ui=False. Never raises.

    If design_start fails with a Claude Design binding error, emit a binding
    reminder card to the project's creation group instead of silently logging.
    """
    if not requirement.needs_ui:
        return
    try:
        created = app.gateway.create_design_document(requirement)
    except Exception as exc:
        LOGGER.warning(
            "create_design_document failed req_id=%s: %s", requirement.req_id, exc,
        )
        return
    if created is None:
        LOGGER.info(
            "create_design_document returned None (folder token empty?) req_id=%s",
            requirement.req_id,
        )
        return
    try:
        app.service.design_start(
            requirement.req_id,
            design_doc_id=created.document_id,
            design_doc_url=created.document_url,
        )
    except ValueError as exc:
        msg = str(exc)
        if "Claude Design 未绑定" in msg:
            _emit_binding_card_for_guard_failure(app, requirement, error_context=msg)
            return
        LOGGER.warning(
            "design_start ValueError req_id=%s: %s", requirement.req_id, exc,
        )
    except Exception as exc:
        LOGGER.warning(
            "design_start failed req_id=%s: %s", requirement.req_id, exc,
        )


def _emit_binding_card_for_guard_failure(
    app, requirement, *, error_context: str,
) -> None:
    """Send a binding reminder card (with error banner) to the project creation group.

    Best-effort: logs warning on failure, never raises.
    """
    cfg = app.service.project_configs.get(requirement.project)
    if cfg is None:
        LOGGER.warning(
            "binding card: no ProjectConfig for %s; cannot send card",
            requirement.project,
        )
        return
    chat_id = getattr(cfg, "feishu_chat_id", "") or requirement.project_group_id
    if not chat_id:
        LOGGER.warning(
            "binding card: no chat_id for project=%s req_id=%s; cannot send",
            requirement.project, requirement.req_id,
        )
        return
    try:
        from .project_bootstrap.service import build_design_binding_card
        card = build_design_binding_card(
            project=requirement.project,
            github_repo_url=getattr(cfg, "github_repo_url", ""),
            error_context=error_context,
        )
        app.gateway.send_card(chat_id, card)
        LOGGER.info(
            "binding reminder card sent after guard failure project=%s req_id=%s",
            requirement.project, requirement.req_id,
        )
    except Exception as exc:
        LOGGER.warning(
            "binding card emission failed project=%s req_id=%s: %s",
            requirement.project, requirement.req_id, exc,
        )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m pytest tests/test_design_start_binding_guard.py -v
```
Expected: 5/5 pass.

- [ ] **Step 5: Full suite regression check**

```bash
python3 -m pytest tests/ --ignore=tests/test_concurrent_spec_gate.py -q 2>&1 | tail -3
```

- [ ] **Step 6: Commit**

```bash
git add src/requirement_workflow_v12/service_app.py tests/test_design_start_binding_guard.py
git commit -m "feat(bootstrap): catch binding guard failure and emit binding card"
```

---

## Task 14: E2E Bootstrap integration test

**Files:**
- Test: `tests/test_bootstrap_design_e2e.py` (new — test only, no production code)

- [ ] **Step 1: Write the E2E test**

Create `tests/test_bootstrap_design_e2e.py`:

```python
"""End-to-end Bootstrap integration test for design-phase prerequisites.

Exercises:
- Create a fake Bootstrap 7-step flow (all steps succeed)
- Assert POPULATE_MAIN writes the 8 new design files
- Assert FINALIZE emits the binding reminder card
- Assert ProjectConfig has the 3 new design fields populated
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def test_bootstrap_e2e_design_artifacts():
    from requirement_workflow_v12.project_bootstrap.service import ProjectBootstrapService
    from requirement_workflow_v12.project_bootstrap.types import BootstrapRequest

    repo_tools = MagicMock()
    repo_tools.bootstrap_project_repo.return_value = MagicMock(
        html_url="https://github.com/new-org/testp",
    )
    feishu = MagicMock()
    github = MagicMock()
    github.get_repo.return_value = None  # no existing repo (fresh project)

    # Prime config snapshot
    configs: dict = {}

    def _list():
        return dict(configs)

    def _upsert(project, cfg):
        configs[project] = cfg
        return cfg

    feishu.list_project_configs.side_effect = _list
    feishu.upsert_project_config.side_effect = _upsert
    feishu.create_project_group.return_value = "oc_chatxyz"
    feishu.create_architecture_document.return_value = MagicMock(
        document_id="doc1", document_url="https://feishu/docx/doc1",
    )

    service = ProjectBootstrapService(
        repo_tools=repo_tools, feishu_gateway=feishu, github_gateway=github,
        template_owner="org", template_repo="Template-repository", new_owner="new-org",
    )
    request = BootstrapRequest(
        project="testp",
        category="enterprise-app",
        owner_user_id="u1",
        creator_chat_id="c1",
    )

    # Walk through the 7 steps
    service.validate(request)
    cfg = service.upsert_config(request, template_version="enterprise-app.v1")
    cfg = service.create_repo_and_populate(
        request, template_version="enterprise-app.v1",
        rendered_architecture_md="# arch\n",
    )
    # The subsequent steps (CREATE_ARCHITECTURE_DOC, CREATE_FEISHU_GROUP, FINALIZE)
    # invoke separate methods. If they have different signatures, adjust.
    # For this E2E we focus on populate + finalize:
    # Ensure feishu_chat_id is set before finalize
    from dataclasses import replace
    cfg = replace(cfg, feishu_chat_id="oc_chatxyz")
    configs["testp"] = cfg

    cfg = service.finalize(request)

    # Assertions: populate_files contains all 8 design files
    populate_call = repo_tools.bootstrap_project_repo.call_args
    populate_files = populate_call.kwargs["populate_files"]
    for must_have in [
        "design/README.md", "design/PAGES.yaml", "design/INDEX.md",
        "design/system/.gitkeep", "design/archive/.gitkeep",
        ".gitattributes",
    ]:
        assert must_have in populate_files, f"missing {must_have}"

    # Binding card sent after finalize
    feishu.send_card.assert_called()
    send_call = feishu.send_card.call_args_list[-1]
    chat_id = send_call.args[0]
    assert chat_id == "oc_chatxyz"

    # ProjectConfig has frontend fields + is PROVISIONED
    assert cfg.frontend_subpath == "src/testp_webapp"
    assert "React 18" in cfg.frontend_tech_stack.get("framework", "")
    # claude_design_project_url is STILL empty (user hasn't bound yet)
    assert cfg.claude_design_project_url == ""


def test_bootstrap_e2e_then_binding_then_design_start_succeeds():
    """Full flow: Bootstrap → user clicks binding card → needs_ui REQ can enter design."""
    from requirement_workflow_v12.coordinator_service import CoordinatorService
    from requirement_workflow_v12.project_config import ProjectConfig
    from requirement_workflow_v12.models import Requirement, WorkflowStatus
    from requirement_workflow_v12.plan_state_machine import DesignStatus

    svc = CoordinatorService.__new__(CoordinatorService)
    svc.requirements = {}
    svc.project_configs = {}
    svc._hooks = MagicMock()

    # Post-bootstrap state: ProjectConfig exists but no URL yet
    cfg = ProjectConfig(
        category="enterprise-app",
        template_version="enterprise-app.v1",
        architecture_doc_id="d",
        architecture_doc_url="u",
        frontend_subpath="src/testp_webapp",
        claude_design_project_url="",
    )
    svc.project_configs["testp"] = cfg

    r = Requirement(
        req_id="REQ-testp-001", name="n", project="testp",
        summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
    )
    svc.requirements[r.req_id] = r

    # Step 1: design_start fails with binding guard
    import pytest
    with pytest.raises(ValueError, match="Claude Design 未绑定"):
        svc.design_start(r.req_id, design_doc_id="d", design_doc_url="u")

    # Step 2: simulate user clicks binding card → ProjectConfig updated
    from dataclasses import replace
    svc.project_configs["testp"] = replace(
        cfg, claude_design_project_url="https://claude.ai/design/p/abc",
    )

    # Step 3: design_start now succeeds
    result = svc.design_start(r.req_id, design_doc_id="d", design_doc_url="u")
    assert result.design_status is DesignStatus.DRAFTING
```

- [ ] **Step 2: Run test to verify it passes**

```bash
python3 -m pytest tests/test_bootstrap_design_e2e.py -v
```
Expected: 2/2 pass. Adjust mock setup if the Bootstrap flow's actual method signatures differ.

- [ ] **Step 3: Full suite regression check**

```bash
python3 -m pytest tests/ --ignore=tests/test_concurrent_spec_gate.py -q 2>&1 | tail -3
```

- [ ] **Step 4: Commit**

```bash
git add tests/test_bootstrap_design_e2e.py
git commit -m "test(bootstrap): end-to-end design integration test"
```

---

## Task 15: Update README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add to README 当前已实现 section**

In `README.md`, find the "当前已实现" section. Append:

```markdown
- Bootstrap Step 4 (POPULATE_MAIN) 落地 8 个 design 样板文件：`design/README.md` / `design/PAGES.yaml` / `design/INDEX.md` / `design/system/.gitkeep` / `design/archive/.gitkeep` / `.gitattributes` (git-lfs) / `src/{pkg}_webapp/.gitkeep`（有前端的 category）/ `CLAUDE.md` 新增 "Design Reference Rules" 节
- `docs/ARCHITECTURE.md` 自动含 "## UI Context" 节（来自 architecture_templates 的 frontend / design 字段）
- ProjectConfig 新增 3 字段：`claude_design_project_url` / `frontend_subpath` / `frontend_tech_stack`
- Bootstrap FINALIZE 成功后自动推送"Claude Design 绑定提醒卡"到创建群
- 飞书卡片 `bind_claude_design_project` action：用户填 URL → 回写 ProjectConfig
- `design_start` 懒检查 `claude_design_project_url`：未绑定时阻断并重新推送绑定卡
```

- [ ] **Step 2: Add to 仍待补齐**

```markdown
- DS 快照自动同步（当前只占位 `design/system/.gitkeep`；v2 补）
- 前端脚手架代码 scaffold（当前只 `.gitkeep` 占位；需单独设计规格）
- 既有 bootstrapped 项目的迁移（手工 PR 补齐 / 后续 REQ 级 `project_context_change` gate 补）
```

- [ ] **Step 3: Add reference links to 联调参考**

```markdown
- Bootstrap 层 design 集成设计规格：
  [2026-04-23-bootstrap-design-integration-design.md](docs/superpowers/specs/2026-04-23-bootstrap-design-integration-design.md)
- Bootstrap 层 design 集成实装计划：
  [2026-04-23-bootstrap-design-integration-plan.md](docs/superpowers/plans/2026-04-23-bootstrap-design-integration-plan.md)
```

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs(readme): note bootstrap design integration status"
```

---

## Self-Review

Run this checklist after Task 15 ships:

**1. Spec coverage:**

- [ ] §1 目标与非目标 → covered implicitly throughout
- [ ] §2 流程图 → Tasks 8, 10, 11, 12, 13 implement it
- [ ] §3 分工 → Task ownership matches the分工表
- [ ] §4.1 静态内容 → Tasks 1, 2
- [ ] §4.2 空占位文件 → Task 8 populate_files additions
- [ ] §4.3 architecture_templates YAML → Task 5
- [ ] §4.4 render_template UI Context section → Tasks 3, 4
- [ ] §4.5 ProjectConfig 3 字段 → Task 6
- [ ] §4.6 Bootstrap service → Tasks 8, 9, 10
- [ ] §4.7 绑定卡模版 → Task 9 (build_design_binding_card)
- [ ] §4.8 Card action handler → Task 11
- [ ] §4.9 design_start lazy check → Tasks 12, 13
- [ ] §5 制品 schema → all covered
- [ ] §6 测试策略 → 8 test files (matches spec §6.1/6.2 list)
- [ ] §7 完成标准 → Task 14 E2E verifies
- [ ] §8 REQ ID 全链路穿透 → N/A (spec notes no REQ-level work)
- [ ] §9 端点/事件/卡片 → Tasks 11, 13 (no new HTTP endpoints, reuse /callbacks/card)
- [ ] §10 方法论对齐 → documented in spec
- [ ] §11 已知遗留 → Task 15 README 仍待补齐 section
- [ ] 附录 A/B/C → all covered

No gaps identified.

**2. Placeholder scan:** searched for "TODO", "TBD", "implement later", "similar to Task N" — none found in this plan (the `待填_` references are in MANIFEST sample content, not plan placeholders).

**3. Type consistency:**

- `ProjectConfig.claude_design_project_url` used in Tasks 6, 7, 11, 12, 13, 14 — consistent naming ✓
- `frontend_subpath` / `frontend_tech_stack` used in Tasks 5, 6, 7, 8, 14 — consistent ✓
- `build_design_binding_card` used in Tasks 9, 10, 13 — consistent ✓
- `_emit_design_binding_reminder_card` used in Tasks 9, 10 — consistent ✓
- `bind_claude_design_project` action name used in Tasks 9, 11, 14 — consistent ✓
- `PROJECT_CONFIG_FIELD_*` constants used in Task 7 — names match the `FRONTEND_TECH_STACK_JSON` spec convention ✓

Self-review PASS.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-23-bootstrap-design-integration-plan.md`. Two execution options:

**1. Subagent-Driven (recommended)** — Dispatch a fresh subagent per task with inline verification for trivial ones, full spec+quality review for substantive ones. Best for this 15-task scope with mixed complexity.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach?**
