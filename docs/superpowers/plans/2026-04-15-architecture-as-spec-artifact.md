# ARCHITECTURE-as-Spec-Artifact Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reposition `ARCHITECTURE.yaml` from a Spec-layer *input* (fetched from GitHub at bootstrap) to a Spec-layer *output* stored in a per-project Feishu document that evolves across REQs; simultaneously tear down the GitHub bootstrap, conversational onboarding, and related fields.

**Architecture:** The Coordinator stops owning any GitHub surface. When a project's first REQ is created (single form submission, no chat Q&A), the Coordinator selects a category template shipped inside the repo, renders it, creates a per-project Feishu ARCHITECTURE doc, and registers a `ProjectConfig` holding `architecture_doc_id` / `architecture_doc_url` / `category` / `template_version`. The spec-context endpoint returns the doc URL + revision instead of YAML text; spec-author reads/writes the Feishu doc directly and reports the new revision on `spec_submit`. Concurrency is constrained to one active SPEC_DRAFTING per project.

**Tech Stack:** Python 3.11, dataclasses, `lark_oapi` (Feishu SDK), pytest, PyYAML (already transitive via templates).

**Pre-flight decisions (locked):**
- Category is a `ProjectConfig` field, NOT inside the YAML body.
- Creation form shows the category dropdown only for a project's first REQ.
- Concurrency option C: forbid overlapping `SPEC_DRAFTING` within the same project.
- P0 safety fixes (token empty-bypass, atomic state write, HMAC empty-secret) are handled in a separate follow-up plan, **not here**.

**Source spec:** `docs/superpowers/specs/2026-04-15-architecture-as-spec-artifact-design.md`

---

## File Structure (decomposition)

**Create:**
- `docs/context/architecture-templates/public-web-site.v1.yaml`
- `docs/context/architecture-templates/miniprogram.v1.yaml`
- `docs/context/architecture-templates/enterprise-bot.v1.yaml`
- `docs/context/architecture-templates/enterprise-app.v1.yaml`
- `docs/context/architecture-templates/saas-ai-automation.v1.yaml`
- `src/requirement_workflow_v12/architecture_templates.py` — template discovery + `render_template(category, project) -> (version, text)`
- `tests/test_architecture_templates.py`
- `tests/test_initialize_project.py`
- `tests/test_concurrent_spec_gate.py`

**Rewrite / modify:**
- `src/requirement_workflow_v12/project_config.py` — new `ProjectConfig` shape; remove `OnboardingState`
- `src/requirement_workflow_v12/models.py` — `Requirement`: drop `github_repo_url` / `spec_context_snapshot_sha`; add `spec_context_snapshot_revision`
- `src/requirement_workflow_v12/store.py` — update field plumbing; tolerate legacy keys
- `src/requirement_workflow_v12/coordinator_service.py` — delete `register_project_config` / `set_project_type` / `set_tech_stack` / `advance_onboarding_state` / `complete_onboarding` / `is_new_project` semantics; add `initialize_project` and `_has_concurrent_spec`
- `src/requirement_workflow_v12/spec_context.py` — drop `GitHubClient` dep; new payload fields; concurrency gate
- `src/requirement_workflow_v12/feishu_gateway.py` — add `create_architecture_document`, `write_document_text`, `fetch_document_revision`
- `src/requirement_workflow_v12/service_app.py` — remove all onboarding code (≈230 lines); route creation form through `initialize_project` on first REQ; rework spec-turn callback to use `architecture_doc_revision`
- `src/requirement_workflow_v12/protocols.py` — `CreationFormPayload` gains `category`
- `src/requirement_workflow_v12/bitable_schema.py` — remove any `github_repo_url` usage (check & strip)
- `scripts/send_openclaw_callback.py` — add `--context-token` and `--architecture-doc-revision` flags on `spec-submit` (see Task 11 errata)
- `docs/agents/spec-author/SKILL.md` — rewrite Step 1/2/4 to consume `architecture_doc_url` + revision

**Delete:**
- `src/requirement_workflow_v12/github_client.py`
- `src/requirement_workflow_v12/project_bootstrapper.py`
- `scripts/bootstrap_architecture.py`
- `tests/test_github_client.py`
- `tests/test_project_bootstrapper.py`
- `tests/test_project_onboarding.py`
- `tests/test_onboarding_conversation.py`

---

## Task Ordering Rationale

Deletion of `github_client.py` / `project_bootstrapper.py` cannot happen until every importer is rewritten, otherwise the test suite cannot be run between intermediate tasks. Therefore:

1. Data-model tasks first (Tasks 1–2): they're leaves, safe to land alone.
2. New infrastructure (Tasks 3–5): templates, render module, Feishu gateway methods — additive, nothing depends on them yet.
3. Service rewiring (Tasks 6–9): build `initialize_project`, rewrite `SpecContextBuilder`, strip onboarding from `service_app.py`, add category dropdown. After these, the legacy files are orphaned.
4. Deletion (Task 10): delete orphaned files + tests in one commit; suite must stay green.
5. Adjacent surface (Tasks 11–12): CLI flag rename; SKILL.md rewrite.
6. Regression gate (Task 13): full pytest.

---

### Task 1: Rewrite `ProjectConfig` (drop onboarding, add category + architecture doc fields)

**Files:**
- Modify: `src/requirement_workflow_v12/project_config.py`
- Modify: `src/requirement_workflow_v12/store.py:47-49,64-67` (project_configs persistence — fields only, signature same)
- Modify: `tests/test_project_config.py` (adjust existing tests to new shape)
- Modify: `tests/test_store_project_config.py` (same)
- Test: reuses `tests/test_project_config.py` + `tests/test_store_project_config.py`

- [ ] **Step 1: Write the failing tests**

Replace the entire body of `tests/test_project_config.py` with:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.project_config import ProjectConfig


def test_project_config_defaults():
    cfg = ProjectConfig(
        category="saas-ai-automation",
        template_version="saas-ai-automation.v1",
        architecture_doc_id="doc_xyz",
        architecture_doc_url="https://feishu.example/docx/doc_xyz",
    )
    assert cfg.category == "saas-ai-automation"
    assert cfg.template_version == "saas-ai-automation.v1"
    assert cfg.architecture_doc_id == "doc_xyz"
    assert cfg.architecture_doc_url == "https://feishu.example/docx/doc_xyz"
    assert cfg.tech_stack == {}
    assert cfg.design_system_doc_id is None


def test_project_config_from_dict_accepts_legacy_fields_and_ignores_them():
    cfg = ProjectConfig.from_dict({
        "category": "enterprise-bot",
        "template_version": "enterprise-bot.v1",
        "architecture_doc_id": "doc_a",
        "architecture_doc_url": "https://feishu.example/docx/doc_a",
        "tech_stack": {"language": "python"},
        # Legacy keys from pre-demolition state.json — must be ignored, not raise.
        "github_repo_url": "https://github.com/org/repo",
        "is_new_project": True,
        "architecture_yaml_initialized": True,
        "acm_registry_initialized": True,
        "onboarding_state": "COMPLETE",
    })
    assert cfg.category == "enterprise-bot"
    assert cfg.tech_stack == {"language": "python"}
    assert not hasattr(cfg, "github_repo_url")
    assert not hasattr(cfg, "onboarding_state")
```

Replace `tests/test_store_project_config.py` with:

```python
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.project_config import ProjectConfig
from requirement_workflow_v12.store import JsonStateStore


def test_store_round_trips_project_config():
    cfg = ProjectConfig(
        category="public-web-site",
        template_version="public-web-site.v1",
        architecture_doc_id="doc_pw",
        architecture_doc_url="https://feishu.example/docx/doc_pw",
        tech_stack={"language": "python"},
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        store = JsonStateStore(f"{tmpdir}/state.json")
        store.save_snapshot({}, {}, {}, {"MyProj": cfg})
        _, _, _, loaded = store.load_snapshot()
        assert loaded["MyProj"].category == "public-web-site"
        assert loaded["MyProj"].architecture_doc_id == "doc_pw"
        assert loaded["MyProj"].tech_stack == {"language": "python"}


def test_store_ignores_legacy_project_config_fields():
    import json
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "state.json"
        path.write_text(json.dumps({
            "requirements": {},
            "active_req_by_user": {},
            "project_groups": {},
            "project_configs": {
                "LegacyProj": {
                    "category": "miniprogram",
                    "template_version": "miniprogram.v1",
                    "architecture_doc_id": "doc_l",
                    "architecture_doc_url": "https://feishu.example/docx/doc_l",
                    "github_repo_url": "https://github.com/org/legacy",
                    "onboarding_state": "COMPLETE",
                }
            },
        }, ensure_ascii=False))
        store = JsonStateStore(str(path))
        _, _, _, loaded = store.load_snapshot()
        assert loaded["LegacyProj"].category == "miniprogram"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src python -m pytest tests/test_project_config.py tests/test_store_project_config.py -v`
Expected: FAIL — current `ProjectConfig` signature requires `github_repo_url` / `is_new_project`.

- [ ] **Step 3: Rewrite `project_config.py`**

Replace the full content of `src/requirement_workflow_v12/project_config.py` with:

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

    @classmethod
    def from_dict(cls, data: dict) -> "ProjectConfig":
        return cls(
            category=data["category"],
            template_version=data["template_version"],
            architecture_doc_id=data["architecture_doc_id"],
            architecture_doc_url=data["architecture_doc_url"],
            tech_stack=data.get("tech_stack", {}),
            design_system_doc_id=data.get("design_system_doc_id"),
        )
```

- [ ] **Step 4: Update `store.py` import**

Edit `src/requirement_workflow_v12/store.py:17` — change:

```python
from .project_config import OnboardingState, ProjectConfig
```

to:

```python
from .project_config import ProjectConfig
```

(store.py serialization already uses `asdict`/`from_dict` so no further change there; `OnboardingState` is unused in the rest of store.py.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `PYTHONPATH=src python -m pytest tests/test_project_config.py tests/test_store_project_config.py -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add src/requirement_workflow_v12/project_config.py src/requirement_workflow_v12/store.py tests/test_project_config.py tests/test_store_project_config.py
git commit -m "refactor(project_config): replace onboarding fields with category+architecture doc pointers"
```

**Note:** Suite is *not green* overall yet — `coordinator_service.py` and `service_app.py` still import the removed symbols. That is fixed in Task 6 / Task 8. Don't run the full suite until Task 10.

---

### Task 2: Rewrite `Requirement` snapshot field

**Files:**
- Modify: `src/requirement_workflow_v12/models.py:78-118` (field definitions)
- Modify: `src/requirement_workflow_v12/store.py:109,116` (legacy keys read)
- Modify: `tests/test_spec_context.py:1-55` (existing tests use old field name)

- [ ] **Step 1: Update the existing test for renamed field**

Edit `tests/test_spec_context.py` — replace the three top-of-file tests (lines 11–54) with:

```python
def test_requirement_has_spec_context_fields():
    req = Requirement(req_id="REQ-T-001", name="t", project="P", summary="s", creator="c")
    assert req.active_spec_context_token == ""
    assert req.spec_context_snapshot_revision == ""


def test_store_round_trips_spec_context_fields():
    req = Requirement(req_id="REQ-T-002", name="t", project="P", summary="s", creator="c")
    req.active_spec_context_token = "spec_ctx_REQ-T-002_1700000000_abcd"
    req.spec_context_snapshot_revision = "rev-20260415-001"

    with tempfile.TemporaryDirectory() as tmpdir:
        store = JsonStateStore(f"{tmpdir}/state.json")
        store.save_snapshot({"REQ-T-002": req}, {}, {})
        reqs, _, _, _ = store.load_snapshot()
        loaded = reqs["REQ-T-002"]
        assert loaded.active_spec_context_token == "spec_ctx_REQ-T-002_1700000000_abcd"
        assert loaded.spec_context_snapshot_revision == "rev-20260415-001"


def test_store_reads_legacy_snapshot_without_spec_context_fields():
    import json
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "state.json"
        path.write_text(json.dumps({
            "requirements": {
                "REQ-LEGACY-001": {
                    "req_id": "REQ-LEGACY-001",
                    "name": "legacy",
                    "project": "L",
                    "summary": "s",
                    "creator": "c",
                    "status": "APPROVED",
                    "spec_context_snapshot_sha": "deadbeef",
                    "github_repo_url": "https://github.com/org/legacy",
                }
            },
            "active_req_by_user": {},
            "project_groups": {},
            "project_configs": {},
        }, ensure_ascii=False))
        store = JsonStateStore(str(path))
        reqs, _, _, _ = store.load_snapshot()
        loaded = reqs["REQ-LEGACY-001"]
        assert loaded.active_spec_context_token == ""
        assert loaded.spec_context_snapshot_revision == ""
        assert not hasattr(loaded, "github_repo_url")
        assert not hasattr(loaded, "spec_context_snapshot_sha")
```

Also **delete** the rest of the file (lines 57 onward — they depend on `github_client` which we are removing). A fresh `test_spec_context.py` will be written in Task 7.

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src python -m pytest tests/test_spec_context.py -v`
Expected: FAIL — `Requirement` has no attribute `spec_context_snapshot_revision`.

- [ ] **Step 3: Edit `models.py` — drop two fields, add one**

In `src/requirement_workflow_v12/models.py`, inside the `Requirement` dataclass (around lines 109–118), remove:

```python
    github_repo_url: str = ""
    ...
    spec_context_snapshot_sha: str = ""
```

Add (place next to `active_spec_context_token`):

```python
    spec_context_snapshot_revision: str = ""
```

Final fragment should read:

```python
    spec_document_id: str = ""
    spec_document_url: str = ""
    spec_review_summary: str = ""
    active_spec_context_token: str = ""
    spec_context_snapshot_revision: str = ""
    updated_at: datetime = field(default_factory=utc_now)
```

- [ ] **Step 4: Edit `store.py` — drop legacy reads, add new field**

In `src/requirement_workflow_v12/store.py:109-116`, replace the block:

```python
            needs_ui=data.get("needs_ui", False),
            github_repo_url=data.get("github_repo_url", ""),
            hifi_prototype_url=data.get("hifi_prototype_url", ""),
            hifi_prototype_confirmed=data.get("hifi_prototype_confirmed", False),
            spec_document_id=data.get("spec_document_id", ""),
            spec_document_url=data.get("spec_document_url", ""),
            spec_review_summary=data.get("spec_review_summary", ""),
            active_spec_context_token=data.get("active_spec_context_token", ""),
            spec_context_snapshot_sha=data.get("spec_context_snapshot_sha", ""),
```

with:

```python
            needs_ui=data.get("needs_ui", False),
            hifi_prototype_url=data.get("hifi_prototype_url", ""),
            hifi_prototype_confirmed=data.get("hifi_prototype_confirmed", False),
            spec_document_id=data.get("spec_document_id", ""),
            spec_document_url=data.get("spec_document_url", ""),
            spec_review_summary=data.get("spec_review_summary", ""),
            active_spec_context_token=data.get("active_spec_context_token", ""),
            spec_context_snapshot_revision=data.get("spec_context_snapshot_revision", ""),
```

(Legacy `github_repo_url` / `spec_context_snapshot_sha` keys in old state.json are silently ignored.)

- [ ] **Step 5: Run test to verify it passes**

Run: `PYTHONPATH=src python -m pytest tests/test_spec_context.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add src/requirement_workflow_v12/models.py src/requirement_workflow_v12/store.py tests/test_spec_context.py
git commit -m "refactor(models): replace Requirement.spec_context_snapshot_sha with revision; drop github_repo_url"
```

---

### Task 3: Ship the five category templates

**Files:**
- Create: `docs/context/architecture-templates/public-web-site.v1.yaml`
- Create: `docs/context/architecture-templates/miniprogram.v1.yaml`
- Create: `docs/context/architecture-templates/enterprise-bot.v1.yaml`
- Create: `docs/context/architecture-templates/enterprise-app.v1.yaml`
- Create: `docs/context/architecture-templates/saas-ai-automation.v1.yaml`

These are data assets only. Renderer + tests arrive in Task 4.

- [ ] **Step 1: Create `public-web-site.v1.yaml`**

```yaml
# Generated from template: public-web-site.v1
# Placeholders: {project} {pkg} {date}
version: "{date}"
project: "{project}"
category: public-web-site
status: bootstrap

tech_stack:
  frontend: "React + TypeScript"
  backend: "FastAPI (Python 3.11)"
  database: "PostgreSQL"
  cdn: "CloudFront"
  deployment: "single-host Docker Compose"

modules:
  - name: "{pkg}_web"
    description: "面向 C 端的 H5/SSR 前端页面。"
    repo_path: "src/{pkg}/web"
    public_api: []
    status: bootstrap
  - name: "{pkg}_api"
    description: "对外 REST API 服务。"
    repo_path: "src/{pkg}/api"
    public_api: []
    status: bootstrap
  - name: "{pkg}_worker"
    description: "轻量异步任务处理。"
    repo_path: "src/{pkg}/worker"
    public_api: []
    status: bootstrap

services: []
data_models: []
external_dependencies:
  - "浏览器静态资源 CDN"
  - "SMTP / 短信网关（如有通知场景）"
```

- [ ] **Step 2: Create `miniprogram.v1.yaml`**

```yaml
# Generated from template: miniprogram.v1
# Placeholders: {project} {pkg} {date}
version: "{date}"
project: "{project}"
category: miniprogram
status: bootstrap

tech_stack:
  client: "微信小程序 (原生框架)"
  backend: "FastAPI (Python 3.11)"
  database: "PostgreSQL"
  deployment: "single-host Docker Compose"

modules:
  - name: "{pkg}_miniapp"
    description: "小程序端页面与业务逻辑。"
    repo_path: "src/{pkg}/miniapp"
    public_api: []
    status: bootstrap
  - name: "{pkg}_api"
    description: "小程序后端 REST API。"
    repo_path: "src/{pkg}/api"
    public_api: []
    status: bootstrap
  - name: "{pkg}_wx_gateway"
    description: "微信登录 / 支付 / 消息回调封装。"
    repo_path: "src/{pkg}/wx_gateway"
    public_api: []
    status: bootstrap

services: []
data_models: []
external_dependencies:
  - "微信开放平台 OpenAPI"
```

- [ ] **Step 3: Create `enterprise-bot.v1.yaml`**

```yaml
# Generated from template: enterprise-bot.v1
# Placeholders: {project} {pkg} {date}
version: "{date}"
project: "{project}"
category: enterprise-bot
status: bootstrap

tech_stack:
  platform: "飞书 / 企微 Bot"
  backend: "FastAPI (Python 3.11)"
  database: "PostgreSQL"
  deployment: "single-host Docker Compose"

modules:
  - name: "{pkg}_bot_gateway"
    description: "IM 事件订阅与消息下发。"
    repo_path: "src/{pkg}/bot_gateway"
    public_api: []
    status: bootstrap
  - name: "{pkg}_intent_router"
    description: "消息意图识别与指令分发。"
    repo_path: "src/{pkg}/intent_router"
    public_api: []
    status: bootstrap
  - name: "{pkg}_skills"
    description: "Bot 可执行的业务技能集合。"
    repo_path: "src/{pkg}/skills"
    public_api: []
    status: bootstrap
  - name: "{pkg}_store"
    description: "对话状态与业务数据持久化。"
    repo_path: "src/{pkg}/store"
    public_api: []
    status: bootstrap

services: []
data_models: []
external_dependencies:
  - "飞书 OpenAPI / 企微 API"
```

- [ ] **Step 4: Create `enterprise-app.v1.yaml`**

```yaml
# Generated from template: enterprise-app.v1
# Placeholders: {project} {pkg} {date}
version: "{date}"
project: "{project}"
category: enterprise-app
status: bootstrap

tech_stack:
  frontend: "React + TypeScript (内网访问)"
  backend: "FastAPI (Python 3.11)"
  database: "PostgreSQL"
  auth: "企业 SSO（OIDC / SAML）"
  deployment: "single-host Docker Compose"

modules:
  - name: "{pkg}_webapp"
    description: "企业内部管理 Web 前端。"
    repo_path: "src/{pkg}/webapp"
    public_api: []
    status: bootstrap
  - name: "{pkg}_api"
    description: "业务 REST API。"
    repo_path: "src/{pkg}/api"
    public_api: []
    status: bootstrap
  - name: "{pkg}_auth"
    description: "SSO 接入与会话管理。"
    repo_path: "src/{pkg}/auth"
    public_api: []
    status: bootstrap

services: []
data_models: []
external_dependencies:
  - "企业 SSO"
  - "企业邮件 / IM 通知渠道"
```

- [ ] **Step 5: Create `saas-ai-automation.v1.yaml`**

```yaml
# Generated from template: saas-ai-automation.v1
# Placeholders: {project} {pkg} {date}
version: "{date}"
project: "{project}"
category: saas-ai-automation
status: bootstrap

tech_stack:
  backend: "FastAPI (Python 3.11)"
  llm: "Anthropic API (claude-sonnet-4-6)"
  database: "PostgreSQL"
  queue: "轻量进程内异步队列"
  deployment: "single-host Docker Compose"

modules:
  - name: "{pkg}_saas_connectors"
    description: "对接外部 SaaS 工具的适配器集合。"
    repo_path: "src/{pkg}/saas_connectors"
    public_api: []
    status: bootstrap
  - name: "{pkg}_ai_pipeline"
    description: "基于 LLM 的数据抽取 / 生成 / 增强流水线。"
    repo_path: "src/{pkg}/ai_pipeline"
    public_api: []
    status: bootstrap
  - name: "{pkg}_automation_engine"
    description: "工作流编排与自动化触发。"
    repo_path: "src/{pkg}/automation_engine"
    public_api: []
    status: bootstrap
  - name: "{pkg}_webhook_gateway"
    description: "外部事件接入与回调分发。"
    repo_path: "src/{pkg}/webhook_gateway"
    public_api: []
    status: bootstrap

services: []
data_models: []
external_dependencies:
  - "对接 SaaS 工具 OpenAPI"
  - "Anthropic API"
```

- [ ] **Step 6: Commit**

```bash
git add docs/context/architecture-templates/
git commit -m "feat(templates): add five ARCHITECTURE.yaml category templates (v1)"
```

---

### Task 4: Implement `architecture_templates.py` renderer

**Files:**
- Create: `src/requirement_workflow_v12/architecture_templates.py`
- Create: `tests/test_architecture_templates.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_architecture_templates.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from requirement_workflow_v12.architecture_templates import (
    UnknownCategory,
    available_categories,
    derive_pkg,
    render_template,
)


def test_available_categories_covers_five():
    cats = available_categories()
    assert set(cats) == {
        "public-web-site",
        "miniprogram",
        "enterprise-bot",
        "enterprise-app",
        "saas-ai-automation",
    }


@pytest.mark.parametrize("raw,expected", [
    ("MyApp", "my_app"),
    ("my-proj", "my_proj"),
    ("HARNESS", "harness"),
    ("Hello World 2", "hello_world_2"),
    ("已有项目", "已有项目"),  # non-ascii kept, non-alnum→_
])
def test_derive_pkg(raw, expected):
    assert derive_pkg(raw) == expected


def test_render_template_substitutes_placeholders():
    version, text = render_template("saas-ai-automation", project="MyApp")
    assert version == "saas-ai-automation.v1"
    assert "{pkg}" not in text
    assert "{project}" not in text
    assert "{date}" not in text
    assert "my_app" in text
    assert 'project: "MyApp"' in text
    assert "category: saas-ai-automation" in text


def test_render_template_unknown_category_raises():
    with pytest.raises(UnknownCategory):
        render_template("nonexistent", project="MyApp")


def test_render_template_picks_highest_v_number(tmp_path, monkeypatch):
    # Shadow the built-in templates dir with a fake one containing two versions.
    fake_dir = tmp_path / "architecture-templates"
    fake_dir.mkdir()
    (fake_dir / "miniprogram.v1.yaml").write_text("v1: {project}", encoding="utf-8")
    (fake_dir / "miniprogram.v2.yaml").write_text("v2: {project}", encoding="utf-8")
    from requirement_workflow_v12 import architecture_templates as mod
    monkeypatch.setattr(mod, "TEMPLATE_DIR", fake_dir)
    version, text = render_template("miniprogram", project="X")
    assert version == "miniprogram.v2"
    assert text == "v2: X"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src python -m pytest tests/test_architecture_templates.py -v`
Expected: FAIL with `ModuleNotFoundError: architecture_templates`.

- [ ] **Step 3: Implement the renderer**

Create `src/requirement_workflow_v12/architecture_templates.py`:

```python
from __future__ import annotations

import re
from datetime import date
from pathlib import Path


class UnknownCategory(Exception):
    """Requested category has no template on disk."""


TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "docs" / "context" / "architecture-templates"

_VERSION_RE = re.compile(r"^(?P<category>[a-z0-9\-]+)\.v(?P<num>\d+)\.yaml$")


def available_categories() -> list[str]:
    cats: set[str] = set()
    if not TEMPLATE_DIR.exists():
        return []
    for entry in TEMPLATE_DIR.iterdir():
        m = _VERSION_RE.match(entry.name)
        if m:
            cats.add(m.group("category"))
    return sorted(cats)


def _latest_template_path(category: str) -> tuple[str, Path]:
    best: tuple[int, Path] | None = None
    if not TEMPLATE_DIR.exists():
        raise UnknownCategory(f"template dir missing: {TEMPLATE_DIR}")
    for entry in TEMPLATE_DIR.iterdir():
        m = _VERSION_RE.match(entry.name)
        if not m or m.group("category") != category:
            continue
        num = int(m.group("num"))
        if best is None or num > best[0]:
            best = (num, entry)
    if best is None:
        raise UnknownCategory(f"no template for category: {category}")
    num, path = best
    return f"{category}.v{num}", path


def derive_pkg(project: str) -> str:
    """CamelCase-split, lowercase, and replace runs of non-alphanumeric-unicode chars with '_'."""
    with_underscores = re.sub(r"(?<=[a-z])(?=[A-Z])", "_", project)
    lowered = with_underscores.strip().lower()
    return re.sub(r"[^\w]+", "_", lowered, flags=re.UNICODE).strip("_")


def render_template(category: str, *, project: str) -> tuple[str, str]:
    version, path = _latest_template_path(category)
    raw = path.read_text(encoding="utf-8")
    pkg = derive_pkg(project)
    today = date.today().isoformat()
    text = (
        raw.replace("{pkg}", pkg)
           .replace("{project}", project)
           .replace("{date}", today)
    )
    return version, text
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src python -m pytest tests/test_architecture_templates.py -v`
Expected: PASS (5+ parametrized tests).

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/architecture_templates.py tests/test_architecture_templates.py
git commit -m "feat(architecture_templates): add category template renderer"
```

---

### Task 5: Feishu gateway — ARCHITECTURE doc primitives

**Files:**
- Modify: `src/requirement_workflow_v12/feishu_gateway.py` (append three methods after `create_spec_document` near line 246)
- Create: `tests/test_feishu_architecture_doc.py`

The methods wrap three Feishu OpenAPI capabilities:

1. `create_architecture_document(project)` — wraps the same `docx.v1.document.create` the spec-doc creator uses, returns `CreatedDocument`.
2. `write_document_text(document_id, content)` — appends a single plain-text block (entire YAML as one preformatted block). Keeps writeback symmetric with how spec-author will rewrite.
3. `fetch_document_revision(document_id)` — returns the current document `revision_id` via the `raw_content` endpoint. If unavailable (the SDK may not expose it in early versions), return the current Unix epoch millis as `ts-<millis>` fallback.

- [ ] **Step 1: Write the failing test**

Create `tests/test_feishu_architecture_doc.py`:

```python
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def test_create_architecture_document_calls_docx_api():
    from requirement_workflow_v12.feishu_gateway import FeishuGateway

    gateway = FeishuGateway.__new__(FeishuGateway)
    gateway.settings = MagicMock(
        feishu_doc_folder_token="folder_xyz",
        feishu_base_url="https://feishu.example",
    )
    fake_document = MagicMock(document_id="doc_arch_1")
    response = MagicMock(
        code=0,
        msg="ok",
        data=MagicMock(document=fake_document),
    )
    response.success.return_value = True
    gateway.client = MagicMock()
    gateway.client.docx.v1.document.create.return_value = response

    result = gateway.create_architecture_document("MyProj")
    assert result is not None
    assert result.document_id == "doc_arch_1"
    assert result.document_url.endswith("/docx/doc_arch_1")


def test_create_architecture_document_without_folder_returns_none():
    from requirement_workflow_v12.feishu_gateway import FeishuGateway
    gateway = FeishuGateway.__new__(FeishuGateway)
    gateway.settings = MagicMock(feishu_doc_folder_token="")
    assert gateway.create_architecture_document("Anything") is None


def test_write_document_text_creates_block():
    from requirement_workflow_v12.feishu_gateway import FeishuGateway

    gateway = FeishuGateway.__new__(FeishuGateway)
    gateway.settings = MagicMock()
    response = MagicMock(code=0, msg="ok")
    response.success.return_value = True
    gateway.client = MagicMock()
    gateway.client.docx.v1.document_block_children.create.return_value = response

    gateway.write_document_text("doc_arch_1", "version: 2026-04-15\nproject: MyProj")
    gateway.client.docx.v1.document_block_children.create.assert_called_once()


def test_fetch_document_revision_returns_string():
    from requirement_workflow_v12.feishu_gateway import FeishuGateway

    gateway = FeishuGateway.__new__(FeishuGateway)
    gateway.settings = MagicMock()
    response = MagicMock(code=0, msg="ok")
    response.success.return_value = True
    response.data = MagicMock(revision_id=42)
    gateway.client = MagicMock()
    gateway.client.docx.v1.document.raw_content.return_value = response

    rev = gateway.fetch_document_revision("doc_arch_1")
    assert rev == "rev-42"


def test_fetch_document_revision_falls_back_when_api_unavailable():
    from requirement_workflow_v12.feishu_gateway import FeishuGateway

    gateway = FeishuGateway.__new__(FeishuGateway)
    gateway.settings = MagicMock()
    gateway.client = MagicMock()
    gateway.client.docx.v1.document.raw_content.side_effect = AttributeError("no raw_content")

    rev = gateway.fetch_document_revision("doc_arch_1")
    assert rev.startswith("ts-") and rev[3:].isdigit()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src python -m pytest tests/test_feishu_architecture_doc.py -v`
Expected: FAIL — methods do not exist.

- [ ] **Step 3: Implement the three methods**

In `src/requirement_workflow_v12/feishu_gateway.py`, after `create_spec_document` (after line 246), add:

```python
    def create_architecture_document(self, project: str) -> CreatedDocument | None:
        if not self.settings.feishu_doc_folder_token:
            return None
        title = f"{project} 架构快照 ARCHITECTURE"
        LOGGER.info("Feishu create_architecture_document project=%s title=%s", project, title)
        request = (
            CreateDocumentRequest.builder()
            .request_body(
                CreateDocumentRequestBody.builder()
                .folder_token(self.settings.feishu_doc_folder_token)
                .title(title)
                .build()
            )
            .build()
        )
        response = self.client.docx.v1.document.create(request)
        self._ensure_success(response, "create architecture document")
        document = response.data.document
        LOGGER.info(
            "Feishu created architecture document project=%s document_id=%s",
            project,
            document.document_id,
        )
        return CreatedDocument(
            document_id=document.document_id,
            document_url=f"{self.settings.feishu_base_url}/docx/{document.document_id}",
        )

    def write_document_text(self, document_id: str, content: str) -> None:
        """Append the given text as a single code-like block to the document."""
        LOGGER.info(
            "Feishu write_document_text document_id=%s content_bytes=%d",
            document_id,
            len(content.encode("utf-8")),
        )
        block = (
            Block.builder()
            .block_type(self.BLOCK_TYPE_TEXT)
            .text(self._rich_text(content))
            .build()
        )
        request = (
            CreateDocumentBlockChildrenRequest.builder()
            .document_id(document_id)
            .block_id(document_id)
            .request_body(
                CreateDocumentBlockChildrenRequestBody.builder()
                .children([block])
                .build()
            )
            .build()
        )
        response = self.client.docx.v1.document_block_children.create(request)
        self._ensure_success(response, "write document text")

    def fetch_document_revision(self, document_id: str) -> str:
        """Return a revision marker for the document.

        Uses the raw_content endpoint's revision_id when available; otherwise
        falls back to a wall-clock timestamp marker so the Coordinator always
        has something to persist for auditing.
        """
        import time as _time
        try:
            response = self.client.docx.v1.document.raw_content(document_id)
            self._ensure_success(response, "fetch document revision")
            revision_id = getattr(response.data, "revision_id", None)
            if revision_id is not None:
                return f"rev-{revision_id}"
        except Exception as exc:  # pragma: no cover - SDK variance
            LOGGER.warning(
                "Failed to query revision for document_id=%s, falling back to timestamp: %s",
                document_id,
                exc,
            )
        return f"ts-{int(_time.time() * 1000)}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src python -m pytest tests/test_feishu_architecture_doc.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/feishu_gateway.py tests/test_feishu_architecture_doc.py
git commit -m "feat(feishu_gateway): add architecture doc create/write/revision primitives"
```

---

### Task 6: CoordinatorService — `initialize_project` + `_has_concurrent_spec` + remove legacy onboarding methods

**Files:**
- Modify: `src/requirement_workflow_v12/coordinator_service.py:1-115`
- Create: `tests/test_initialize_project.py`
- Create: `tests/test_concurrent_spec_gate.py`

Two capabilities land here because they both consume `ProjectConfig` and `requirements.values()`, and both are rule-based methods on the Coordinator service:

1. `initialize_project(project, category, architecture_doc_id, architecture_doc_url, template_version, tech_stack) -> ProjectConfig` — registers `ProjectConfig` exactly once. Raises `ValueError` if already present. Does **not** touch Feishu itself (Feishu call happens in `service_app.py` which then passes the resulting ids in here).

2. `_has_concurrent_spec(project, exclude_req_id) -> bool` — scans `self.requirements` for any REQ with matching `project`, `status == SPEC_DRAFTING`, and `req_id != exclude_req_id`.

Also remove the now-dead methods: `is_new_project`, `register_project_config`, `advance_onboarding_state`, `set_tech_stack`, `set_project_type`, `complete_onboarding`. Keep `get_project_config` and `set_design_system_doc` / `should_create_design_system`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_initialize_project.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from requirement_workflow_v12.coordinator_service import CoordinatorService
from requirement_workflow_v12.project_config import ProjectConfig


def test_initialize_project_registers_config():
    svc = CoordinatorService()
    cfg = svc.initialize_project(
        project="MyProj",
        category="saas-ai-automation",
        template_version="saas-ai-automation.v1",
        architecture_doc_id="doc_xyz",
        architecture_doc_url="https://feishu.example/docx/doc_xyz",
        tech_stack={"backend": "FastAPI"},
    )
    assert isinstance(cfg, ProjectConfig)
    assert svc.project_configs["MyProj"] is cfg
    assert cfg.category == "saas-ai-automation"
    assert cfg.tech_stack == {"backend": "FastAPI"}


def test_initialize_project_rejects_duplicate():
    svc = CoordinatorService()
    svc.initialize_project(
        project="MyProj",
        category="miniprogram",
        template_version="miniprogram.v1",
        architecture_doc_id="doc_a",
        architecture_doc_url="https://feishu.example/docx/doc_a",
        tech_stack={},
    )
    with pytest.raises(ValueError, match="already initialized"):
        svc.initialize_project(
            project="MyProj",
            category="miniprogram",
            template_version="miniprogram.v1",
            architecture_doc_id="doc_b",
            architecture_doc_url="https://feishu.example/docx/doc_b",
            tech_stack={},
        )
```

Create `tests/test_concurrent_spec_gate.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.coordinator_service import CoordinatorService
from requirement_workflow_v12.models import Requirement, WorkflowStatus


def _req(req_id: str, project: str, status: WorkflowStatus) -> Requirement:
    r = Requirement(req_id=req_id, name="n", project=project, summary="s", creator="c")
    r.status = status
    return r


def test_has_concurrent_spec_false_when_alone():
    svc = CoordinatorService()
    svc.requirements["R1"] = _req("R1", "ProjA", WorkflowStatus.SPEC_DRAFTING)
    assert svc._has_concurrent_spec("ProjA", exclude_req_id="R1") is False


def test_has_concurrent_spec_true_when_sibling_drafting():
    svc = CoordinatorService()
    svc.requirements["R1"] = _req("R1", "ProjA", WorkflowStatus.SPEC_DRAFTING)
    svc.requirements["R2"] = _req("R2", "ProjA", WorkflowStatus.APPROVED)
    assert svc._has_concurrent_spec("ProjA", exclude_req_id="R2") is True


def test_has_concurrent_spec_ignores_other_projects():
    svc = CoordinatorService()
    svc.requirements["R1"] = _req("R1", "ProjA", WorkflowStatus.SPEC_DRAFTING)
    svc.requirements["R2"] = _req("R2", "ProjB", WorkflowStatus.APPROVED)
    assert svc._has_concurrent_spec("ProjB", exclude_req_id="R2") is False


def test_has_concurrent_spec_ignores_locked_siblings():
    svc = CoordinatorService()
    svc.requirements["R1"] = _req("R1", "ProjA", WorkflowStatus.SPEC_LOCKED)
    assert svc._has_concurrent_spec("ProjA", exclude_req_id="R2") is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src python -m pytest tests/test_initialize_project.py tests/test_concurrent_spec_gate.py -v`
Expected: FAIL — `initialize_project` and `_has_concurrent_spec` do not exist; also `CoordinatorService` import may currently fail because it still imports `OnboardingState`.

- [ ] **Step 3: Rewrite the onboarding section of `coordinator_service.py`**

Edit `src/requirement_workflow_v12/coordinator_service.py`:

Replace line 7:

```python
from .project_config import OnboardingState, ProjectConfig
```

with:

```python
from .project_config import ProjectConfig
```

Replace the whole block from line 60 (`# ── Project onboarding ───`) through line 112 (end of `should_create_design_system`) with:

```python
    # ── Project initialization ────────────────────────────────────────────

    def get_project_config(self, project: str) -> ProjectConfig | None:
        return self.project_configs.get(project)

    def initialize_project(
        self,
        *,
        project: str,
        category: str,
        template_version: str,
        architecture_doc_id: str,
        architecture_doc_url: str,
        tech_stack: dict[str, str],
    ) -> ProjectConfig:
        if project in self.project_configs:
            raise ValueError(f"project already initialized: {project}")
        cfg = ProjectConfig(
            category=category,
            template_version=template_version,
            architecture_doc_id=architecture_doc_id,
            architecture_doc_url=architecture_doc_url,
            tech_stack=dict(tech_stack),
        )
        self.project_configs[project] = cfg
        return cfg

    def set_design_system_doc(self, project: str, doc_id: str) -> None:
        if project in self.project_configs:
            self.project_configs[project].design_system_doc_id = doc_id

    def should_create_design_system(self, project: str) -> bool:
        cfg = self.project_configs.get(project)
        if cfg is None:
            return False
        return cfg.design_system_doc_id is None

    def _has_concurrent_spec(self, project: str, *, exclude_req_id: str) -> bool:
        for req in self.requirements.values():
            if (
                req.project == project
                and req.req_id != exclude_req_id
                and req.status == WorkflowStatus.SPEC_DRAFTING
            ):
                return True
        return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src python -m pytest tests/test_initialize_project.py tests/test_concurrent_spec_gate.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/coordinator_service.py tests/test_initialize_project.py tests/test_concurrent_spec_gate.py
git commit -m "feat(coordinator): add initialize_project + _has_concurrent_spec; remove onboarding methods"
```

**Note:** Full test suite still not green — `service_app.py` still imports removed symbols. Fixed in Task 8.

---

### Task 7: Rewrite `SpecContextBuilder` (drop GitHubClient, new payload, concurrency gate)

**Files:**
- Rewrite: `src/requirement_workflow_v12/spec_context.py`
- Create (append): `tests/test_spec_context.py` — add new builder tests below the field-level tests already updated in Task 2

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_spec_context.py` (after the three round-trip tests updated in Task 2):

```python
from unittest.mock import MagicMock

import pytest

from requirement_workflow_v12.coordinator_service import CoordinatorService
from requirement_workflow_v12.models import WorkflowStatus
from requirement_workflow_v12.project_config import ProjectConfig
from requirement_workflow_v12.spec_context import (
    ConcurrentSpecInProgress,
    SpecContextBuilder,
    SpecContextGateError,
    SpecContextMisconfigured,
)


def _svc_with_req(req_id="REQ-1", project="ProjA", status=WorkflowStatus.APPROVED) -> CoordinatorService:
    svc = CoordinatorService()
    from requirement_workflow_v12.models import Requirement
    r = Requirement(req_id=req_id, name="n", project=project, summary="s", creator="c")
    r.status = status
    r.document_url = "https://feishu.example/docx/req_doc"
    r.latest_review_summary = "ready"
    svc.requirements[req_id] = r
    svc.project_configs[project] = ProjectConfig(
        category="saas-ai-automation",
        template_version="saas-ai-automation.v1",
        architecture_doc_id="doc_arch",
        architecture_doc_url="https://feishu.example/docx/doc_arch",
        tech_stack={"backend": "FastAPI"},
    )
    return svc


def test_build_returns_payload_with_new_fields():
    svc = _svc_with_req()
    gateway = MagicMock()
    gateway.fetch_document_revision.return_value = "rev-7"
    builder = SpecContextBuilder(service=svc, gateway=gateway)

    result = builder.build("REQ-1")

    ctx = result.context
    assert ctx["architecture_doc_url"] == "https://feishu.example/docx/doc_arch"
    assert ctx["architecture_doc_revision"] == "rev-7"
    assert ctx["template_version"] == "saas-ai-automation.v1"
    assert ctx["category"] == "saas-ai-automation"
    assert ctx["requirement_document_url"] == "https://feishu.example/docx/req_doc"
    assert "architecture_yaml" not in ctx
    assert "architecture_commit_sha" not in ctx
    assert "github_repo_url" not in ctx
    assert result.context_token.startswith("spec_ctx_REQ-1_")
    assert svc.requirements["REQ-1"].active_spec_context_token == result.context_token


def test_build_rejects_wrong_status():
    svc = _svc_with_req(status=WorkflowStatus.DRAFTING)
    builder = SpecContextBuilder(service=svc, gateway=MagicMock())
    with pytest.raises(SpecContextGateError):
        builder.build("REQ-1")


def test_build_rejects_when_project_not_initialized():
    svc = _svc_with_req()
    svc.project_configs.clear()
    builder = SpecContextBuilder(service=svc, gateway=MagicMock())
    with pytest.raises(SpecContextMisconfigured):
        builder.build("REQ-1")


def test_build_rejects_concurrent_spec_in_same_project():
    svc = _svc_with_req()
    from requirement_workflow_v12.models import Requirement
    other = Requirement(req_id="REQ-2", name="n", project="ProjA", summary="s", creator="c")
    other.status = WorkflowStatus.SPEC_DRAFTING
    svc.requirements["REQ-2"] = other
    gateway = MagicMock()
    gateway.fetch_document_revision.return_value = "rev-1"
    builder = SpecContextBuilder(service=svc, gateway=gateway)
    with pytest.raises(ConcurrentSpecInProgress):
        builder.build("REQ-1")


def test_build_allows_same_req_in_spec_drafting():
    svc = _svc_with_req(status=WorkflowStatus.SPEC_DRAFTING)
    gateway = MagicMock()
    gateway.fetch_document_revision.return_value = "rev-9"
    builder = SpecContextBuilder(service=svc, gateway=gateway)
    result = builder.build("REQ-1")
    assert result.context["status"] == "SPEC_DRAFTING"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src python -m pytest tests/test_spec_context.py -v`
Expected: FAIL — `ConcurrentSpecInProgress` undefined; builder signature still takes `github_client`.

- [ ] **Step 3: Rewrite `spec_context.py`**

Replace the full content of `src/requirement_workflow_v12/spec_context.py`:

```python
from __future__ import annotations

import secrets
import time
from dataclasses import dataclass

from .models import WorkflowStatus


SPEC_CONTEXT_ALLOWED_STATUSES = {
    WorkflowStatus.APPROVED,
    WorkflowStatus.SPEC_DRAFTING,
}


class SpecContextGateError(Exception):
    """Requirement is not in a state that permits spec-context retrieval."""

    def __init__(self, message: str, current_status: str) -> None:
        super().__init__(message)
        self.current_status = current_status


class SpecContextMisconfigured(Exception):
    """Project has no ProjectConfig — initialize_project never ran."""


class ConcurrentSpecInProgress(Exception):
    """Another REQ in the same project currently holds SPEC_DRAFTING."""


@dataclass
class SpecContextResult:
    context: dict
    context_token: str


class SpecContextBuilder:
    def __init__(self, service, gateway) -> None:
        self._service = service
        self._gateway = gateway

    def build(self, req_id: str) -> SpecContextResult:
        requirement = self._service.get_requirement(req_id)
        if requirement is None:
            raise ValueError(f"未知需求：{req_id}")

        if requirement.status not in SPEC_CONTEXT_ALLOWED_STATUSES:
            raise SpecContextGateError(
                f"当前状态 {requirement.status.value} 不允许获取 spec-context",
                current_status=requirement.status.value,
            )

        project_cfg = self._service.project_configs.get(requirement.project)
        if project_cfg is None:
            raise SpecContextMisconfigured(
                f"项目 {requirement.project} 尚未初始化 ProjectConfig"
            )

        if self._service._has_concurrent_spec(
            requirement.project, exclude_req_id=req_id
        ):
            raise ConcurrentSpecInProgress(
                f"项目 {requirement.project} 已有另一条需求处于 SPEC_DRAFTING，请先等待其锁定。"
            )

        revision = self._gateway.fetch_document_revision(project_cfg.architecture_doc_id)

        context_token = self._mint_token(req_id)
        requirement.active_spec_context_token = context_token

        context = {
            "req_id": requirement.req_id,
            "name": requirement.name,
            "project": requirement.project,
            "category": project_cfg.category,
            "status": requirement.status.value,
            "needs_ui": requirement.needs_ui,
            "hifi_prototype_url": requirement.hifi_prototype_url,
            "design_system_snapshot": None,
            "requirement_document_url": requirement.document_url,
            "architecture_doc_url": project_cfg.architecture_doc_url,
            "architecture_doc_revision": revision,
            "template_version": project_cfg.template_version,
            "spec_document_url": requirement.spec_document_url,
            "spec_document_id": requirement.spec_document_id,
            "latest_review_summary": requirement.latest_review_summary,
        }
        return SpecContextResult(context=context, context_token=context_token)

    @staticmethod
    def _mint_token(req_id: str) -> str:
        return f"spec_ctx_{req_id}_{int(time.time())}_{secrets.token_hex(4)}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src python -m pytest tests/test_spec_context.py -v`
Expected: PASS (all 8 tests — 3 round-trip + 5 builder).

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/spec_context.py tests/test_spec_context.py
git commit -m "refactor(spec_context): drop GitHub dep; return feishu doc url+revision; add concurrency gate"
```

---

### Task 8: Strip onboarding + GitHub from `service_app.py`; rewire spec-turn callback

**Files:**
- Modify: `src/requirement_workflow_v12/service_app.py` (extensive)
- Modify: `tests/test_requirement_workflow_v12.py` if any test touches removed surface (check grep below)

This is the largest task. It removes ≈230 lines and rewires ≈40.

- [ ] **Step 1: Remove dead imports**

Edit `src/requirement_workflow_v12/service_app.py:19-20`:

```python
from .project_bootstrapper import ProjectBootstrapper
from .project_config import OnboardingState, ProjectConfig
```

Replace with:

```python
from .project_config import ProjectConfig
```

Edit `src/requirement_workflow_v12/service_app.py:102-112` (constructor):

Replace:

```python
        self._pending_onboarding_project: dict[str, str] = {}   # user_id → project
        self._pending_requirement_info: dict[str, dict] = {}    # user_id → creation args

        from .github_client import GitHubClient
        from .spec_context import SpecContextBuilder

        self.github_client = GitHubClient(token=self.settings.github_token)
        self._spec_context_builder = SpecContextBuilder(
            service=self.service,
            github_client=self.github_client,
        )
```

with:

```python
        from .spec_context import SpecContextBuilder

        self._spec_context_builder = SpecContextBuilder(
            service=self.service,
            gateway=self.gateway,
        )
```

(`_pending_requirement_info` is also dropped — it only fed `_finish_onboarding`. The existing creation-form path does not need it.)

- [ ] **Step 2: Remove `_handle_creation_group_message` onboarding branch**

Edit `src/requirement_workflow_v12/service_app.py:223-259`. Replace the function body with:

```python
    def _handle_creation_group_message(self, context: MessageContext) -> list[OutboundMessage | OutboundCard]:
        if "创建需求" not in context.text and "新建需求" not in context.text:
            return []

        self._observed_creation_group_chat_id = context.chat_id
        # A freeform command never takes the initialization path — project
        # category must be selected via the form, so always render the card.
        return [OutboundCard(receive_id=context.chat_id, card=self._build_requirement_creation_card(context))]
```

(The previous code parsed `创建需求 <project> <name> <summary>` directly into a `CreationRequest` for existing projects. That path is redundant — the card form already covers the same inputs and is the only surface that can carry the category dropdown cleanly. Dropping it simplifies the entry.)

- [ ] **Step 3: Delete all onboarding helpers**

Edit `src/requirement_workflow_v12/service_app.py:261-457`. Delete the entire span containing:

- the `# ── Onboarding conversation ───` comment
- `_parse_creation_command`, `_parse_tech_stack`
- `_handle_onboarding_reply`
- `_onboarding_collect_repo`, `_onboarding_collect_project_type`, `_onboarding_collect_tech_stack`, `_onboarding_wait_arch_confirmation`
- `_run_bootstrap_new_project`, `_run_bootstrap_existing_project`
- `_finish_onboarding`
- `_make_bootstrapper`

After deletion the next surviving method should be `_create_requirement_from_form` (was at line 459).

- [ ] **Step 4: Remove the spec-context query's GitHub-specific error handling**

Edit `src/requirement_workflow_v12/service_app.py:995-1062`. Replace the method body with:

```python
    def handle_openclaw_spec_context_query(
        self,
        raw_body: bytes,
        *,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, object]]:
        from .spec_context import (
            ConcurrentSpecInProgress,
            SpecContextGateError,
            SpecContextMisconfigured,
        )

        auth_error = self._validate_openclaw_callback_auth(raw_body, headers=headers)
        if auth_error is not None:
            return auth_error
        try:
            payload = json.loads(raw_body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return 400, {"error": "invalid_json"}

        req_id = str(payload.get("req_id", "")).strip()
        if not req_id:
            return 400, {"error": "invalid_payload", "message": "req_id 为必填字段。"}

        LOGGER.info("Received spec-context query req_id=%s", req_id)

        try:
            result = self._spec_context_builder.build(req_id)
        except ValueError as exc:
            return 404, {"error": "not_found", "message": str(exc)}
        except SpecContextGateError as exc:
            return 409, {
                "error": "invalid_state",
                "message": str(exc),
                "current_status": exc.current_status,
            }
        except ConcurrentSpecInProgress as exc:
            return 409, {"error": "concurrent_spec_in_progress", "message": str(exc)}
        except SpecContextMisconfigured as exc:
            return 500, {"error": "project_not_initialized", "message": str(exc)}
        except Exception as exc:
            LOGGER.exception("Unexpected failure handling spec-context req_id=%s", req_id)
            return 500, {"error": "spec_context_failed", "message": str(exc)}

        self._save_state()

        LOGGER.info(
            "Spec-context served req_id=%s doc_revision=%s",
            req_id,
            result.context["architecture_doc_revision"],
        )
        return 200, {
            "ok": True,
            "context": result.context,
            "context_token": result.context_token,
            "expires_hint": "valid until SPEC_LOCKED or a newer token is issued",
        }
```

- [ ] **Step 5: Rewire spec-turn callback to use `architecture_doc_revision`**

Edit `src/requirement_workflow_v12/service_app.py:1064-1179`. Inside that method, change:

Line 1097 from:

```python
        architecture_commit_sha = str(payload.get("architecture_commit_sha", "")).strip()
```

to:

```python
        architecture_doc_revision = str(payload.get("architecture_doc_revision", "")).strip()
```

Line 1158–1162 from:

```python
            if not architecture_commit_sha:
                return 400, {
                    "error": "missing_commit_sha",
                    "message": "spec_submit 必须回传 architecture_commit_sha。",
                }
```

to:

```python
            if not architecture_doc_revision:
                return 400, {
                    "error": "missing_doc_revision",
                    "message": "spec_submit 必须回传 architecture_doc_revision。",
                }
```

Line 1171 from:

```python
            requirement.spec_context_snapshot_sha = architecture_commit_sha
```

to:

```python
            requirement.spec_context_snapshot_revision = architecture_doc_revision
```

- [ ] **Step 6: Guard `spec_start` with the same concurrency check**

Still in `handle_openclaw_spec_turn_callback`, find the `if event == "spec_start":` branch (around line 1113). Immediately after the existing `invalid_state` check (currently verifying `status == APPROVED`), insert:

```python
            if self.service._has_concurrent_spec(
                requirement.project, exclude_req_id=req_id
            ):
                return 409, {
                    "error": "concurrent_spec_in_progress",
                    "message": (
                        f"项目 {requirement.project} 已有另一条需求处于 SPEC_DRAFTING，"
                        "请先等待其锁定。"
                    ),
                }
```

- [ ] **Step 7: Run the existing workflow / spec tests to confirm no regressions in un-refactored surface**

Run: `PYTHONPATH=src python -m pytest tests/test_requirement_workflow_v12.py tests/test_spec_stage.py tests/test_agent_protocol.py tests/test_bitable_schema_contract.py tests/test_ui_design_system.py -v`
Expected: PASS. If any test exercises the removed `_handle_onboarding_reply` or `register_project_config`, update that test to use `initialize_project` directly, or delete it if the coverage is now redundant with Task 6's new tests.

**Likely hits:** `test_requirement_workflow_v12.py` may reference `service.register_project_config`. If so, replace the call with:

```python
service.initialize_project(
    project="P",
    category="saas-ai-automation",
    template_version="saas-ai-automation.v1",
    architecture_doc_id="doc_t",
    architecture_doc_url="https://feishu.example/docx/doc_t",
    tech_stack={},
)
```

Run grep first to know:

```bash
grep -n "register_project_config\|advance_onboarding_state\|set_tech_stack\|set_project_type\|complete_onboarding\|is_new_project\|github_repo_url\|OnboardingState" tests/test_requirement_workflow_v12.py tests/test_spec_stage.py
```

Adjust only the tests returned by that grep. Leave other tests untouched.

- [ ] **Step 8: Commit**

```bash
git add src/requirement_workflow_v12/service_app.py tests/
git commit -m "refactor(service_app): remove onboarding+bootstrap paths; spec-context uses feishu doc revision"
```

---

### Task 9: Add category dropdown to creation form + first-REQ initialization path

**Files:**
- Modify: `src/requirement_workflow_v12/protocols.py` (add `category` field to `CreationFormPayload`)
- Modify: `src/requirement_workflow_v12/service_app.py` (creation card body, form extraction, first-REQ branch of `_provision_requirement_after_creation`)

- [ ] **Step 1: Add `category` to `CreationFormPayload`**

Edit `src/requirement_workflow_v12/protocols.py:39-49`. Change the dataclass to:

```python
@dataclass
class CreationFormPayload:
    project: str
    name: str
    summary: str
    creator: str
    creator_user_id: str
    creation_chat_id: str
    background_links: str = ""
    priority: str = ""
    expected_due_date: str = ""
    needs_ui: bool = False
    category: str = ""
```

- [ ] **Step 2: Write failing integration test**

Create `tests/test_first_req_initialization.py`:

```python
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def _make_app_with_stub_gateway(tmp_path):
    from requirement_workflow_v12.service_app import CoordinatorRuntimeApp
    from requirement_workflow_v12.config import Settings
    from requirement_workflow_v12.store import JsonStateStore
    from requirement_workflow_v12.coordinator_service import CoordinatorService

    settings = MagicMock(spec=Settings)
    settings.state_store_path = str(tmp_path / "state.json")
    settings.creation_group_chat_id = "group_c"
    settings.openclaw_callback_secret = ""
    settings.openclaw_callback_ttl_seconds = 600
    settings.github_token = ""

    gateway = MagicMock()
    gateway.create_architecture_document.return_value = MagicMock(
        document_id="doc_arch",
        document_url="https://feishu.example/docx/doc_arch",
    )
    gateway.write_document_text.return_value = None
    gateway.create_project_group.side_effect = Exception("skip")
    gateway.create_requirement_record.return_value = None
    gateway.create_requirement_document.return_value = None

    service = CoordinatorService()
    store = JsonStateStore(settings.state_store_path)

    with patch.object(Settings, "validate_runtime", return_value=None):
        settings.validate_runtime = lambda: None
        app = CoordinatorRuntimeApp(
            settings=settings,
            store=store,
            service=service,
            gateway=gateway,
        )
    return app, gateway, service


def test_first_req_creates_architecture_doc_and_project_config(tmp_path):
    app, gateway, service = _make_app_with_stub_gateway(tmp_path)

    from requirement_workflow_v12.protocols import CreationFormPayload

    payload = CreationFormPayload(
        project="MyProj",
        name="first req",
        summary="kickoff",
        creator="Alice",
        creator_user_id="u1",
        creation_chat_id="group_c",
        needs_ui=False,
        category="saas-ai-automation",
    )

    request, _, req_id = app._create_requirement_from_form(payload)
    app._provision_requirement_after_creation(request, req_id)

    cfg = service.project_configs["MyProj"]
    assert cfg.category == "saas-ai-automation"
    assert cfg.template_version == "saas-ai-automation.v1"
    assert cfg.architecture_doc_id == "doc_arch"
    gateway.create_architecture_document.assert_called_once_with("MyProj")
    gateway.write_document_text.assert_called_once()
    written_text = gateway.write_document_text.call_args.args[1]
    assert "category: saas-ai-automation" in written_text
    assert "my_proj" in written_text


def test_second_req_does_not_recreate_architecture_doc(tmp_path):
    app, gateway, service = _make_app_with_stub_gateway(tmp_path)
    service.initialize_project(
        project="MyProj",
        category="miniprogram",
        template_version="miniprogram.v1",
        architecture_doc_id="doc_existing",
        architecture_doc_url="https://feishu.example/docx/doc_existing",
        tech_stack={},
    )

    from requirement_workflow_v12.protocols import CreationFormPayload

    payload = CreationFormPayload(
        project="MyProj",
        name="second req",
        summary="more work",
        creator="Bob",
        creator_user_id="u2",
        creation_chat_id="group_c",
        needs_ui=False,
        category="",  # empty because form hides the dropdown after the first REQ
    )

    request, _, req_id = app._create_requirement_from_form(payload)
    app._provision_requirement_after_creation(request, req_id)

    gateway.create_architecture_document.assert_not_called()
    gateway.write_document_text.assert_not_called()
    assert service.project_configs["MyProj"].architecture_doc_id == "doc_existing"


def test_first_req_without_category_raises(tmp_path):
    app, _, _ = _make_app_with_stub_gateway(tmp_path)
    from requirement_workflow_v12.protocols import CreationFormPayload
    import pytest as _pytest

    payload = CreationFormPayload(
        project="NewProj",
        name="x",
        summary="y",
        creator="c",
        creator_user_id="u",
        creation_chat_id="group_c",
        category="",
    )
    with _pytest.raises(ValueError, match="category is required"):
        app._initialize_project_for_first_req(payload)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `PYTHONPATH=src python -m pytest tests/test_first_req_initialization.py -v`
Expected: FAIL — `_initialize_project_for_first_req` does not exist; form does not carry `category`.

- [ ] **Step 4: Extract `category` from the form**

Edit `src/requirement_workflow_v12/service_app.py:1378-1389` (inside `_extract_creation_form_payload`). After the existing `needs_ui` extraction, add:

```python
        category = self._normalize_form_value(form_value.get("category"))
```

Include `category=category` in the `CreationFormPayload(...)` construction at the end of the method.

- [ ] **Step 5: Add the category dropdown to the card (only when project is unknown)**

Edit `_build_requirement_creation_card` (~line 1491). Change its signature first — the method needs to know whether the project is already initialized. Update the signature:

```python
    def _build_requirement_creation_card(self, context: MessageContext) -> dict[str, object]:
        known_projects = sorted(self.service.project_configs.keys())
        show_category_field = True  # shown until user types a known project; see below
        category_options = [
            {"text": {"tag": "plain_text", "content": "公开 Web 站点"}, "value": "public-web-site"},
            {"text": {"tag": "plain_text", "content": "小程序"}, "value": "miniprogram"},
            {"text": {"tag": "plain_text", "content": "企业内 Bot / Agent"}, "value": "enterprise-bot"},
            {"text": {"tag": "plain_text", "content": "企业内部应用"}, "value": "enterprise-app"},
            {"text": {"tag": "plain_text", "content": "SaaS AI 自动化"}, "value": "saas-ai-automation"},
        ]
```

Then inside the existing `elements` list, immediately after the `summary` multiline input (around line 1531, after that closing `},`), insert:

```python
                            {
                                "tag": "select_static",
                                "name": "category",
                                "required": False,
                                "width": "fill",
                                "label": {
                                    "tag": "plain_text",
                                    "content": (
                                        "项目类目（首次为该项目创建需求时必填；"
                                        f"已注册的项目：{', '.join(known_projects) or '（无）'}"
                                        "，已有项目可留空）"
                                    ),
                                },
                                "placeholder": {"tag": "plain_text", "content": "选择项目类目"},
                                "options": category_options,
                            },
```

(Because Feishu form fields cannot be dynamically shown/hidden based on another field's value, the UX compromise is: always render the dropdown; label tells the user when to fill it. Server validates: first REQ → `category` required; second REQ → `category` must either match the existing `ProjectConfig.category` or be empty.)

- [ ] **Step 6: Add `_initialize_project_for_first_req` helper + wire it into provisioning**

In `src/requirement_workflow_v12/service_app.py`, add a new method (place it just above `_provision_requirement_after_creation`, around line 487):

```python
    def _initialize_project_for_first_req(self, payload: CreationFormPayload) -> None:
        from .architecture_templates import UnknownCategory, render_template

        if not payload.category:
            raise ValueError(
                "category is required when creating the first requirement for a project"
            )
        try:
            template_version, rendered = render_template(
                payload.category, project=payload.project
            )
        except UnknownCategory as exc:
            raise ValueError(f"未知类目：{payload.category}") from exc

        created = self.gateway.create_architecture_document(payload.project)
        if created is None:
            raise RuntimeError("failed to create ARCHITECTURE feishu document (missing folder token)")
        self.gateway.write_document_text(created.document_id, rendered)

        tech_stack: dict[str, str] = {}
        for line in rendered.splitlines():
            if line.startswith("  ") and ":" in line and not line.startswith("   "):
                continue  # skip nested; we intentionally keep tech_stack empty here
        # tech_stack stays empty; the YAML itself contains the real values.
        self.service.initialize_project(
            project=payload.project,
            category=payload.category,
            template_version=template_version,
            architecture_doc_id=created.document_id,
            architecture_doc_url=created.document_url,
            tech_stack=tech_stack,
        )
```

Then in `_provision_requirement_after_creation` (around line 487), at the very top of the method body (before the `requirement = self.service.get_requirement(req_id)` line), insert the initialization branch. But the method does not currently receive the form `payload`; only `CreationRequest` and `req_id`. Adjust:

Change the call site in `_handle_card_action_payload` (line ~1199) from:

```python
            request, _, req_id = self._create_requirement_from_form(form_payload)
            threading.Thread(
                target=self._provision_requirement_after_creation,
                args=(request, req_id),
                daemon=True,
            ).start()
```

to:

```python
            request, _, req_id = self._create_requirement_from_form(form_payload)
            # First REQ for this project → initialize ARCHITECTURE doc before async provisioning.
            if form_payload.project not in self.service.project_configs:
                try:
                    self._initialize_project_for_first_req(form_payload)
                    self._save_state()
                except Exception as exc:
                    LOGGER.exception(
                        "Project initialization failed for %s: %s", form_payload.project, exc
                    )
                    return 200, {"toast": {"type": "error", "content": f"项目初始化失败：{exc}"}}
            else:
                # Second-or-later REQ — category field, if provided, must not conflict.
                existing = self.service.project_configs[form_payload.project]
                if form_payload.category and form_payload.category != existing.category:
                    return 200, {"toast": {
                        "type": "error",
                        "content": (
                            f"项目 {form_payload.project} 已注册为 {existing.category}，"
                            "与本次选择不一致。如需变更请联系管理员。"
                        ),
                    }}
            threading.Thread(
                target=self._provision_requirement_after_creation,
                args=(request, req_id),
                daemon=True,
            ).start()
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `PYTHONPATH=src python -m pytest tests/test_first_req_initialization.py -v`
Expected: PASS (3 tests).

- [ ] **Step 8: Commit**

```bash
git add src/requirement_workflow_v12/protocols.py src/requirement_workflow_v12/service_app.py tests/test_first_req_initialization.py
git commit -m "feat(creation): add category dropdown + first-REQ architecture doc initialization"
```

---

### Task 10: Delete the orphaned GitHub / bootstrap / onboarding surface

By this task, nothing in `src/` imports the deleted symbols. Verify before deletion, then drop the files + their tests in a single commit.

**Files:**
- Delete: `src/requirement_workflow_v12/github_client.py`
- Delete: `src/requirement_workflow_v12/project_bootstrapper.py`
- Delete: `scripts/bootstrap_architecture.py`
- Delete: `tests/test_github_client.py`
- Delete: `tests/test_project_bootstrapper.py`
- Delete: `tests/test_project_onboarding.py`
- Delete: `tests/test_onboarding_conversation.py`

- [ ] **Step 1: Verify no remaining imports**

Run:

```bash
grep -rn "github_client\|project_bootstrapper\|ProjectBootstrapper\|GitHubClient\|bootstrap_architecture" src/ scripts/ tests/
```

Expected output: empty, or lines only within the files about to be deleted. If anything else matches, fix that file before proceeding.

- [ ] **Step 2: Delete the files**

```bash
git rm src/requirement_workflow_v12/github_client.py
git rm src/requirement_workflow_v12/project_bootstrapper.py
git rm scripts/bootstrap_architecture.py
git rm tests/test_github_client.py
git rm tests/test_project_bootstrapper.py
git rm tests/test_project_onboarding.py
git rm tests/test_onboarding_conversation.py
```

- [ ] **Step 3: Run the full test suite**

Run: `PYTHONPATH=src python -m pytest -v`
Expected: ALL PASS. No collection errors.

- [ ] **Step 4: Commit**

```bash
git commit -m "refactor: delete GitHub bootstrap + onboarding surface"
```

---

### Task 11: Add CLI flags on `spec-submit` — `send_openclaw_callback.py`

**Files:**
- Modify: `scripts/send_openclaw_callback.py` (flag + payload builder)

**Note (errata, 2026-04-15):** The original draft of this task assumed `--architecture-commit-sha` already existed on `spec-submit` and needed renaming, and that `scripts/run_spec_context_smoke.py` had a `REQUIRED_CONTEXT_FIELDS` constant. Neither was true on the starting branch. The actual work is an **addition** of two new flags, and the smoke-script update is a no-op.

- [ ] **Step 1: Add the two new CLI flags**

Edit `scripts/send_openclaw_callback.py`. In the `spec-submit` subparser, register two new flags and include their values in the payload builder:

- argparse: add `--context-token` and `--architecture-doc-revision` (both optional, default `""`)
- payload: `build_spec_submit_payload` must emit `context_token` and `architecture_doc_revision` keys (empty string when not provided)

- [ ] **Step 2: (No-op) smoke-script contract**

`scripts/run_spec_context_smoke.py` has no `REQUIRED_CONTEXT_FIELDS` constant. Skip this step; the smoke script doesn't need changes for this plan.

- [ ] **Step 3: Run targeted CLI sanity check**

Run: `PYTHONPATH=src python scripts/send_openclaw_callback.py spec-submit --req-id REQ-X --summary s --context-token t --architecture-doc-revision rev-1 --dry-run 2>&1 | head -20`

(If `--dry-run` does not exist, just run `--help` on the subcommand and confirm the flag appears.)

Expected: flag name present in help text; no argparse error.

- [ ] **Step 4: Commit**

```bash
git add scripts/send_openclaw_callback.py scripts/run_spec_context_smoke.py
git commit -m "refactor(scripts): add --architecture-doc-revision / --context-token flags to spec-submit"
```

---

### Task 12: Rewrite `spec-author` SKILL.md for the Feishu-doc-based architecture context

**Files:**
- Rewrite: `docs/agents/spec-author/SKILL.md`

The agent now reads `architecture_doc_url` via `feishu_fetch_doc`, produces an updated YAML, writes it back via `feishu_update_doc`, and reports the new `architecture_doc_revision` on submit.

- [ ] **Step 1: Rewrite the file**

Replace the content of `docs/agents/spec-author/SKILL.md` with:

```markdown
---
name: spec-author
description: Spec 撰写助手，按 9 节模板撰写技术规格文档，并演化项目级 ARCHITECTURE 飞书文档。收到「请开始 Spec 撰写 REQ-xxx」时激活。
---

# Spec 撰写助手

## 启动流程

收到包含「请开始 Spec 撰写 REQ-xxx」的消息时启动。

**Step 1：通过 spec-context 拉取项目级上下文**（唯一合法入口）

```bash
python3 /home/admin/.openclaw/bin/send_openclaw_callback.py \
  --base-url "${COORDINATOR_BASE_URL:-http://127.0.0.1:8004}" \
  --secret "${OPENCLAW_CALLBACK_SECRET:-}" \
  spec-context \
  --req-id "{req_id}"
```

响应结构：

```json
{
  "ok": true,
  "context": {
    "req_id": "...",
    "name": "...",
    "project": "...",
    "category": "saas-ai-automation",
    "status": "APPROVED | SPEC_DRAFTING",
    "needs_ui": true,
    "requirement_document_url": "https://feishu.../doc_req",
    "architecture_doc_url": "https://feishu.../doc_arch",
    "architecture_doc_revision": "rev-7",
    "template_version": "saas-ai-automation.v1",
    "spec_document_url": "",
    "spec_document_id": "",
    "latest_review_summary": "...",
    "design_system_snapshot": null
  },
  "context_token": "spec_ctx_REQ-xxx_..._xxxx"
}
```

**必须保存** `context_token`。`architecture_doc_revision` 是进入时的 revision，最终回传时必须是**写回后**的新 revision。

若返回 `ok != true` 或 HTTP 非 200：立即停止。若错误码为 `concurrent_spec_in_progress`：通知用户稍后重试，不得自行循环轮询。

**Step 1b：按 status 分支**

- **`APPROVED` 且 `spec_document_url` 为空**：调 spec_start，**必须回传 context_token**：

```bash
python3 /home/admin/.openclaw/bin/send_openclaw_callback.py \
  --base-url "${COORDINATOR_BASE_URL:-http://127.0.0.1:8004}" \
  --secret "${OPENCLAW_CALLBACK_SECRET:-}" \
  --req-id "{req_id}" \
  spec-start \
  --summary "开始 Spec 撰写" \
  --context-token "{context_token}"
```

- **`SPEC_DRAFTING`（断点续写）**：直接使用 spec-context 返回的 `spec_document_id` / `spec_document_url`，跳过 spec_start。

**Step 2：读取需求文档与当前 ARCHITECTURE 快照**

- 用 `feishu_fetch_doc` 读取 `requirement_document_url` 获取需求 8 字段。
- 用 `feishu_fetch_doc` 读取 `architecture_doc_url` 获取项目当前 ARCHITECTURE YAML 文本（作为背景信息与增量合并底本）。

**禁止**用其它途径（GitHub、缓存副本、人工贴入）获取 ARCHITECTURE。

**Step 3：逐节撰写 Spec**

每节完成后用 `feishu_update_doc` 写入 spec 文档（doc_token = `spec_document_id`）。9 节顺序：

1. 背景与目标（对应需求：问题描述 + 使用场景）
2. API 入参定义（对应需求：输入，含字段名 + 类型 + 约束）
3. API 出参定义（对应需求：输出，含字段名 + 类型 + 示例值）
4. 异常处理与边界条件（对应需求：边界）
5. 测试策略（对应需求：验收标准，每条 AC → Given/When/Then）
6. 性能与可用性指标（对应需求：非功能要求，必须含量化数值）
7. 实现范围（对应需求：技术范围声明，明确 in/out of scope）
8. 架构设计（见下方子节要求）
9. 数据模型（新增或变更的表结构；无变更时填「无」）

### 架构设计节（第 8 节）必须包含以下 4 个子节：

**8.1 顶层架构背景**：说明本需求涉及哪些已有服务/模块，变更属于新增/扩展/改造。

**8.2 项目级上下文消费声明**（必填，不得为空）：

| 上下文产物 | 版本/来源 | 影响本 Spec 的哪些判断 |
|-----------|---------|----------------------|
| ARCHITECTURE YAML | `architecture_doc_url` 进入时 revision `{architecture_doc_revision}` | 架构接合点选择、复用模块确认 |
| latest_review_summary | Coordinator state（spec-context 响应） | 需求层遗留问题闭环 |
| 设计系统快照 | 若 `needs_ui=true` 且 `design_system_snapshot=null`：显式标注「UI 约束需人工确认」 | UI 字段规格 |

本子节必须**引用 Step 2 读到的 YAML 原文**做分析，严禁凭空猜测架构。

**8.3 关键架构决策**：每条含"决策 + 依据 + 影响"三要素。

**8.4 存储与数据流设计**：输入来源 → 处理层 → 存储 → 输出方式。

**Step 3b：演化 ARCHITECTURE YAML（Spec 的核心产出之一）**

- 基于 Step 2 读到的当前 YAML 与本次 Spec 的 8.3 / 8.4，识别本 REQ 引入的架构增量：
  - 新增 / 修改的模块
  - 新增 / 修改的服务
  - 新增 / 修改的数据模型
  - 新增的外部依赖
- 在本地合并：原 YAML + 增量 → 新版 YAML。保留原有条目，仅新增/修订增量涉及部分。
- 调 `feishu_update_doc` 将新版 YAML 覆盖写回 `architecture_doc_url`（doc_token = `architecture_doc_id`）。
- 写回完成后，**调 spec-context 再次读取**获取**写后的 `architecture_doc_revision`**，保留供 Step 4 回传。

**Step 4：9 节均完成且 ARCHITECTURE 已写回后调 spec_submit**

**必须回传 context_token 与写后 architecture_doc_revision**：

```bash
python3 /home/admin/.openclaw/bin/send_openclaw_callback.py \
  --base-url "${COORDINATOR_BASE_URL:-http://127.0.0.1:8004}" \
  --secret "${OPENCLAW_CALLBACK_SECRET:-}" \
  --req-id "{req_id}" \
  spec-submit \
  --summary "Spec 初稿完成，9节均已填写；ARCHITECTURE 已演化" \
  --spec-document-url "{spec_document_url}" \
  --context-token "{context_token}" \
  --architecture-doc-revision "{post_write_revision}"
```

缺失任一参数或 token 失效 → Coordinator 返回 400/409，必须重新从 Step 1 拉取上下文后再提交。

## 不允许的行为

- **不得跳过 Step 1 spec-context**：绕过 Coordinator 直接操作飞书属严重违规
- **不得凭空伪造 context_token 或 architecture_doc_revision**：必须使用端点响应的原值
- **不得用 `feishu_fetch_doc` 读取上述两条 URL 以外的文档**（包括其他 Spec 文档、其他项目的 ARCHITECTURE）
- **不得用 GitHub / 本地副本读取 ARCHITECTURE**：项目级 ARCHITECTURE 的唯一来源是 `architecture_doc_url`
- **不得自行创建飞书文档**（`feishu_create_doc` 禁止调用，spec 文档由 spec_start 创建，ARCHITECTURE 文档由 Coordinator 在首条 REQ 时创建）
- **不得直接操作 Bitable**
- 不修改需求文档（只读）
- 不跳过任何节（9 节全部必须非空）
- 不得把 ARCHITECTURE 演化放到 Step 3 之前（必须先读原文再增量合并；覆盖写前确保未漏既有模块）
```

- [ ] **Step 2: Commit**

```bash
git add docs/agents/spec-author/SKILL.md
git commit -m "docs(spec-author): switch SKILL.md to feishu architecture doc + revision round-trip"
```

---

### Task 13: Full regression gate + stale-scan cleanup

**Files:**
- No source changes (cleanup pass)

- [ ] **Step 1: Search for any remaining stale references**

Run:

```bash
grep -rn "github_repo_url\|architecture_yaml\|architecture_commit_sha\|spec_context_snapshot_sha\|OnboardingState\|is_new_project\|_pending_onboarding\|_make_bootstrapper\|acm_registry_initialized\|architecture_yaml_initialized" src/ scripts/ tests/ docs/agents/ docs/superpowers/plans/
```

Expected: zero matches in `src/`, `scripts/`, `tests/`, `docs/agents/`. Matches in the plan/spec docs themselves are fine (historical text).

If matches appear in code paths, fix them. Typical survivors: a comment, or a reference inside `bitable_schema.py`.

Specifically check `src/requirement_workflow_v12/bitable_schema.py`:

```bash
grep -n "github_repo_url\|architecture_yaml_initialized\|acm_registry_initialized" src/requirement_workflow_v12/bitable_schema.py
```

If any field refers to these, remove it and rerun `tests/test_bitable_schema_contract.py`.

- [ ] **Step 2: Run the full test suite**

Run: `PYTHONPATH=src python -m pytest -v`
Expected: ALL PASS. No skips unrelated to the ones already present. No collection errors.

- [ ] **Step 3: Verify import sanity**

Run: `PYTHONPATH=src python -c "from requirement_workflow_v12.service_app import CoordinatorRuntimeApp; print('ok')"`
Expected: `ok` and no `ImportError`.

- [ ] **Step 4: If stale refs were fixed, commit the cleanup**

```bash
git add -u
git commit -m "chore: remove remaining references to deleted GitHub/onboarding surface" || echo "nothing to commit"
```

---

## Self-review (run after writing, before handing off)

**1. Spec coverage**

| Spec section | Covered by |
|---|---|
| §5.1 ProjectConfig changes | Task 1 |
| §5.2 Requirement field rename + drops | Task 2 |
| §5.3 OnboardingState removal | Tasks 1 (enum drop) + 6 (method deletion) + 8 (service_app cleanup) + 10 (final file deletes) |
| §6 Category templates (location + 5 files + placeholder rules) | Tasks 3 + 4 |
| §7 Creation form category dropdown (first-REQ-only UX) | Task 9 |
| §8.1 First REQ workflow | Task 9 |
| §8.2 Subsequent REQ | Task 9 |
| §8.3 Spec write consuming architecture_doc_url | Tasks 7 + 12 |
| §8.4 Concurrency option C | Tasks 6 + 7 + 8 (spec_start guard) |
| §9 spec-context payload rework | Task 7 |
| §9.3 spec-turn callback field rename | Task 8 |
| §10 Error codes | Tasks 7 + 8 |
| §11.1–11.4 demolition + new code | Tasks 1/2/6/7/8/9/10 |
| §11 CLI flag rename | Task 11 |
| §14 Unit + integration tests | Tasks 1–9, 13 |
| §15 Phase 2 seam | N/A (non-goal) |

No uncovered requirement within scope. Migration (§12) is out-of-scope for this plan per the user's instruction to decide after execution.

**2. Placeholders**

Scanned: no "TBD" / "fill in" / "similar to Task N" / bare "add appropriate error handling". All code steps include the code. All commands include expected output.

**3. Type consistency**

- `ProjectConfig(category=..., template_version=..., architecture_doc_id=..., architecture_doc_url=..., tech_stack=..., design_system_doc_id=...)` — same across Tasks 1, 6, 7, 9.
- `CoordinatorService.initialize_project(*, project, category, template_version, architecture_doc_id, architecture_doc_url, tech_stack)` — same across Tasks 6, 9, tests in 9.
- `SpecContextBuilder(service, gateway)` — same across Tasks 7, 8.
- `FeishuGateway.create_architecture_document(project)`, `write_document_text(document_id, content)`, `fetch_document_revision(document_id) -> str` — same across Tasks 5, 7, 9.
- `render_template(category, *, project) -> tuple[version, text]` — same across Tasks 4 and 9.
- `Requirement.spec_context_snapshot_revision: str` — same across Tasks 2, 8.
- Payload keys (`architecture_doc_url`, `architecture_doc_revision`, `template_version`, `category`) — same across Tasks 7, 8, 11, 12.

No drift.
