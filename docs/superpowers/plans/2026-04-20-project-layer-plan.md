# Project 层 (§5.0) + Bootstrap 流程 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地 harness 方法论 §5.0 Project 层：一次显式、幂等的 Bootstrap 流程产出 GitHub repo + Feishu ARCHITECTURE doc + Feishu 群 + Bitable 行 + 项目级上下文文件；所有 REQ 创建硬切换到 `/create project` + `/create req` 固化命令；REQ 前置校验 `PROVISIONED`；`architecture_change` 泛化为 `project_context_change` 统一 gate。

**Architecture:** 新增 Layer 2 `project_bootstrap` 模块（编排 7 步）；扩展 Layer 3 `ProjectRepoTools` 门面加 `bootstrap_project_repo` verb；Layer 4 GitHub/Feishu 原语已具备（`create_repo_from_template` / `commit_files` / `create_architecture_document` / `create_project_group`）。`ProjectConfig` 数据模型扩字段（`bootstrap_status` / `bootstrap_log` / `feishu_chat_id` 等）并在 Bitable 表加对应列。`service_app` 入口解析改为固化命令路由；`_initialize_project_for_first_req` 懒初始化路径完全删除。

**Tech Stack:** Python 3.11 / dataclasses / httpx（GitHub）/ lark-oapi（Feishu）/ pytest / MagicMock。

**Spec reference:** `docs/superpowers/specs/2026-04-20-project-layer-design.md`

---

## 前置准备（人工操作，非代码任务）

**P1. Template 仓库准备（人工）** —— 在执行本计划前完成：

- 访问 `https://github.com/Snowziio/Template-repository`，进入 **Settings** → 勾选 **"Template repository"** 开关（确保 `is_template=true`）
- 本计划 Task B2 会通过 CLI 把以下文件 populate 到 template 仓库：
  - `README.md`（说明"这是模板仓库"）
  - `LICENSE`
  - `.gitignore`（多语言宽泛 ignore）
  - `.github/workflows/ci.yml`（占位 CI）
- 若 template 仓库当前有其它内容，由人工决定是否保留或清空

**P2. Bitable `project_configs` 表字段扩展（人工）** —— 在 Task A1 运行前完成：

登录 Feishu Bitable，打开 `project_configs` 表，新增以下字段：

| 字段名 | 类型 | 说明 |
|---|---|---|
| `bootstrap_status` | 单行文本 | UNBOOTSTRAPPED / BOOTSTRAPPING / PROVISIONED / FAILED |
| `bootstrap_log_json` | 多行文本 | JSON array，记录每步执行情况 |
| `bootstrap_completed_at` | 单行文本 | ISO 时间戳 |
| `project_status` | 单行文本 | 生命周期状态（MVP 等同 bootstrap_status）|
| `feishu_chat_id` | 单行文本 | Bootstrap 创建的群 chat_id |

---

## File Structure（落地单元）

```
src/requirement_workflow_v12/
├── project_bootstrap/                      (NEW module)
│   ├── __init__.py                         (public API: ProjectBootstrapService)
│   ├── service.py                          (orchestrator; 7-step runner with resume)
│   ├── state.py                            (BootstrapStep enum + log helpers)
│   ├── types.py                            (BootstrapRequest / BootstrapResult / BootstrapStepError)
│   └── static_content.py                   (Python constants for Populate files)
├── project_repo/
│   ├── tools.py                            (MODIFY: add bootstrap_project_repo verb)
│   ├── types.py                            (MODIFY: enable RepoRef + add PopulateArtifacts)
├── project_context_apply.py                (NEW: dispatch + executor stubs for project_context_change)
├── project_config.py                       (MODIFY: +5 fields)
├── service_app.py                          (MODIFY: slash commands, remove _initialize_project_for_first_req, pre-check PROVISIONED)
├── coordinator_service.py                  (MODIFY: pre-check PROVISIONED on create_requirement_from_group)
├── github_gateway.py                       (MODIFY: +get_repo, +add_collaborator)
├── feishu_gateway.py                       (MODIFY: upsert bootstrap fields)
└── protocols.py                            (MODIFY: CreationRequest + category; new CreateProjectCommand/CreateReqCommand dataclasses)

tests/
├── test_project_bootstrap_service.py       (NEW)
├── test_project_bootstrap_state.py         (NEW)
├── test_project_bootstrap_resume.py        (NEW)
├── test_project_repo_bootstrap_verb.py     (NEW)
├── test_project_context_apply.py           (NEW)
├── test_service_app_slash_create_project.py (NEW)
├── test_service_app_slash_create_req.py    (NEW)
├── test_req_registry_append.py             (NEW)
├── test_first_req_initialization.py        (DELETE - legacy path removed)
└── (existing tests updated where needed)

bitable_project_configs_schema.json         (MODIFY: +5 fields)
docs/superpowers/methodology.md             (MODIFY: insert §5.0, bump v2.0→v2.5)
docs/superpowers/planning-harness-layer.md  (MODIFY: prereq note + rename section)
docs/superpowers/specs/2026-04-19-planning-phase-design.md (MODIFY: addendum)
docs/agents/plan-author/SKILL.md            (MODIFY: project_context_change schema)
docs/agents/plan-author/callback-schema.json (MODIFY: rename field)
docs/agents/project-bootstrap/SKILL.md      (NEW)
```

---

## Phase A: Foundation — ProjectConfig 字段 + Bitable schema

### Task A1: `ProjectConfig` 扩展新字段

**Files:**
- Modify: `src/requirement_workflow_v12/project_config.py`
- Test: `tests/test_project_config.py`

- [ ] **Step 1: Write failing test for new fields**

Append to `tests/test_project_config.py`:

```python
def test_project_config_from_dict_includes_bootstrap_fields():
    from requirement_workflow_v12.project_config import ProjectConfig

    cfg = ProjectConfig.from_dict({
        "category": "saas-ai-automation",
        "template_version": "saas-ai-automation.v1",
        "architecture_doc_id": "doc_x",
        "architecture_doc_url": "https://example/doc_x",
        "bootstrap_status": "PROVISIONED",
        "bootstrap_log": [{"step": 1, "ts": "2026-04-20T10:00:00", "status": "ok"}],
        "bootstrap_completed_at": "2026-04-20T10:15:00",
        "project_status": "PROVISIONED",
        "feishu_chat_id": "oc_chat123",
    })
    assert cfg.bootstrap_status == "PROVISIONED"
    assert cfg.bootstrap_log == [{"step": 1, "ts": "2026-04-20T10:00:00", "status": "ok"}]
    assert cfg.bootstrap_completed_at == "2026-04-20T10:15:00"
    assert cfg.project_status == "PROVISIONED"
    assert cfg.feishu_chat_id == "oc_chat123"


def test_project_config_defaults_for_new_fields():
    from requirement_workflow_v12.project_config import ProjectConfig

    cfg = ProjectConfig(
        category="saas-ai-automation",
        template_version="saas-ai-automation.v1",
        architecture_doc_id="",
        architecture_doc_url="",
    )
    assert cfg.bootstrap_status == "UNBOOTSTRAPPED"
    assert cfg.bootstrap_log == []
    assert cfg.bootstrap_completed_at is None
    assert cfg.project_status == "UNBOOTSTRAPPED"
    assert cfg.feishu_chat_id == ""
```

- [ ] **Step 2: Run test to verify failure**

```bash
cd /Users/daxin/work/requirement-workflow-feishu
python -m pytest tests/test_project_config.py::test_project_config_from_dict_includes_bootstrap_fields -v
```

Expected: FAIL with `AttributeError` or KeyError on missing field.

- [ ] **Step 3: Implement new fields in `project_config.py`**

Replace the entire file content:

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

    @classmethod
    def from_dict(cls, data: dict) -> "ProjectConfig":
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
        )
```

- [ ] **Step 4: Run tests to verify pass**

```bash
python -m pytest tests/test_project_config.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/project_config.py tests/test_project_config.py
git commit -m "feat(project-config): add bootstrap_status + feishu_chat_id fields"
```

---

### Task A2: Bitable schema JSON extension

**Files:**
- Modify: `bitable_project_configs_schema.json`
- Test: `tests/test_bitable_schema_contract.py`

- [ ] **Step 1: Read current schema**

```bash
cat bitable_project_configs_schema.json
```

Note the array of `{name, type}` entries and the existing field list.

- [ ] **Step 2: Write failing contract test**

Append to `tests/test_bitable_schema_contract.py`:

```python
def test_project_configs_schema_has_bootstrap_fields():
    import json
    from pathlib import Path

    schema_path = Path(__file__).resolve().parents[1] / "bitable_project_configs_schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    field_names = {f["name"] for f in schema["fields"]}

    expected = {
        "bootstrap_status",
        "bootstrap_log_json",
        "bootstrap_completed_at",
        "project_status",
        "feishu_chat_id",
    }
    missing = expected - field_names
    assert not missing, f"missing bitable fields: {missing}"
```

- [ ] **Step 3: Run test — verify failure**

```bash
python -m pytest tests/test_bitable_schema_contract.py::test_project_configs_schema_has_bootstrap_fields -v
```

Expected: FAIL.

- [ ] **Step 4: Add fields to `bitable_project_configs_schema.json`**

Open the file and append these entries to the `fields` array (preserve existing ones):

```json
{"name": "bootstrap_status", "type": 1},
{"name": "bootstrap_log_json", "type": 1},
{"name": "bootstrap_completed_at", "type": 1},
{"name": "project_status", "type": 1},
{"name": "feishu_chat_id", "type": 1}
```

(Type `1` is "text" in Bitable schema; confirm by reading existing text fields in the schema.)

- [ ] **Step 5: Run tests**

```bash
python -m pytest tests/test_bitable_schema_contract.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add bitable_project_configs_schema.json tests/test_bitable_schema_contract.py
git commit -m "feat(bitable): add bootstrap_* + feishu_chat_id columns to project_configs schema"
```

---

### Task A3: `feishu_gateway._project_config_to_fields` writes new fields

**Files:**
- Modify: `src/requirement_workflow_v12/feishu_gateway.py:413-426`
- Test: `tests/test_gateway_project_configs.py`

- [ ] **Step 1: Write failing test for new field mapping**

Append to `tests/test_gateway_project_configs.py`:

```python
def test_project_config_to_fields_includes_bootstrap_columns():
    import json
    from requirement_workflow_v12.feishu_gateway import FeishuGateway
    from requirement_workflow_v12.project_config import ProjectConfig

    cfg = ProjectConfig(
        category="saas-ai-automation",
        template_version="saas-ai-automation.v1",
        architecture_doc_id="doc_x",
        architecture_doc_url="https://example/doc_x",
        bootstrap_status="PROVISIONED",
        bootstrap_log=[{"step": 1, "ts": "t1", "status": "ok"}],
        bootstrap_completed_at="t-done",
        project_status="PROVISIONED",
        feishu_chat_id="oc_abc",
    )
    fields = FeishuGateway._project_config_to_fields.__func__(
        None, cfg, "myproj"  # type: ignore
    )
    assert fields["bootstrap_status"] == "PROVISIONED"
    assert json.loads(fields["bootstrap_log_json"]) == [{"step": 1, "ts": "t1", "status": "ok"}]
    assert fields["bootstrap_completed_at"] == "t-done"
    assert fields["project_status"] == "PROVISIONED"
    assert fields["feishu_chat_id"] == "oc_abc"
```

- [ ] **Step 2: Run test — verify fail**

```bash
python -m pytest tests/test_gateway_project_configs.py::test_project_config_to_fields_includes_bootstrap_columns -v
```

Expected: FAIL (KeyError / missing fields).

- [ ] **Step 3: Read existing field constants + method**

```bash
grep -n "PROJECT_CONFIG_FIELD_" src/requirement_workflow_v12/feishu_gateway.py | head -15
```

Note the existing `PROJECT_CONFIG_FIELD_*` constants.

- [ ] **Step 4: Add new field constants + update mapping method**

In `feishu_gateway.py`, near the other `PROJECT_CONFIG_FIELD_*` constants, add:

```python
PROJECT_CONFIG_FIELD_BOOTSTRAP_STATUS = "bootstrap_status"
PROJECT_CONFIG_FIELD_BOOTSTRAP_LOG_JSON = "bootstrap_log_json"
PROJECT_CONFIG_FIELD_BOOTSTRAP_COMPLETED_AT = "bootstrap_completed_at"
PROJECT_CONFIG_FIELD_PROJECT_STATUS = "project_status"
PROJECT_CONFIG_FIELD_FEISHU_CHAT_ID = "feishu_chat_id"
```

In `_project_config_to_fields` (line 413-426), append to the dict:

```python
PROJECT_CONFIG_FIELD_BOOTSTRAP_STATUS: cfg.bootstrap_status,
PROJECT_CONFIG_FIELD_BOOTSTRAP_LOG_JSON: json.dumps(
    cfg.bootstrap_log, ensure_ascii=False
),
PROJECT_CONFIG_FIELD_BOOTSTRAP_COMPLETED_AT: cfg.bootstrap_completed_at or "",
PROJECT_CONFIG_FIELD_PROJECT_STATUS: cfg.project_status,
PROJECT_CONFIG_FIELD_FEISHU_CHAT_ID: cfg.feishu_chat_id,
```

- [ ] **Step 5: Also update `list_project_configs` load path**

Find the load-side code (search `PROJECT_CONFIG_FIELD_ARCH_DOC_ID` to locate the `from_dict` loader around line 485+). Update the dict built for `ProjectConfig.from_dict(...)` to include:

```python
"bootstrap_status": self._extract_field_text(fields.get(PROJECT_CONFIG_FIELD_BOOTSTRAP_STATUS)),
"bootstrap_log": json.loads(
    self._extract_field_text(fields.get(PROJECT_CONFIG_FIELD_BOOTSTRAP_LOG_JSON)) or "[]"
),
"bootstrap_completed_at": self._extract_field_text(
    fields.get(PROJECT_CONFIG_FIELD_BOOTSTRAP_COMPLETED_AT)
) or None,
"project_status": self._extract_field_text(fields.get(PROJECT_CONFIG_FIELD_PROJECT_STATUS)),
"feishu_chat_id": self._extract_field_text(fields.get(PROJECT_CONFIG_FIELD_FEISHU_CHAT_ID)),
```

Wrap the `bootstrap_log` parse in try/except to default to `[]` on malformed JSON.

- [ ] **Step 6: Run tests to verify pass**

```bash
python -m pytest tests/test_gateway_project_configs.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/requirement_workflow_v12/feishu_gateway.py tests/test_gateway_project_configs.py
git commit -m "feat(feishu-gateway): serialize bootstrap fields on project_configs upsert"
```

---

## Phase B: Layer 4 primitive extensions + static content

### Task B1: `GitHubGateway.get_repo` + `add_collaborator` primitives

**Files:**
- Modify: `src/requirement_workflow_v12/github_gateway.py`
- Test: `tests/test_github_gateway.py`

- [ ] **Step 1: Write failing tests for `get_repo` + `add_collaborator`**

Append to `tests/test_github_gateway.py`:

```python
def test_get_repo_returns_metadata_on_200(monkeypatch):
    import httpx
    from requirement_workflow_v12.config import Settings
    from requirement_workflow_v12.github_gateway import GitHubGateway

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/repos/Snowziio/test3"
        return httpx.Response(
            200,
            json={
                "full_name": "Snowziio/test3",
                "html_url": "https://github.com/Snowziio/test3",
                "default_branch": "main",
                "is_template": False,
            },
        )

    transport = httpx.MockTransport(handler)
    settings = Settings(github_token="tok")
    client = httpx.Client(base_url="https://api.github.com", transport=transport)
    gw = GitHubGateway(settings, client=client)

    meta = gw.get_repo(owner="Snowziio", name="test3")
    assert meta["full_name"] == "Snowziio/test3"
    assert meta["default_branch"] == "main"


def test_get_repo_returns_none_on_404(monkeypatch):
    import httpx
    from requirement_workflow_v12.config import Settings
    from requirement_workflow_v12.github_gateway import GitHubGateway

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "Not Found"})

    transport = httpx.MockTransport(handler)
    settings = Settings(github_token="tok")
    client = httpx.Client(base_url="https://api.github.com", transport=transport)
    gw = GitHubGateway(settings, client=client)

    assert gw.get_repo(owner="Snowziio", name="missing") is None


def test_add_collaborator_posts_to_correct_endpoint():
    import httpx
    from requirement_workflow_v12.config import Settings
    from requirement_workflow_v12.github_gateway import GitHubGateway

    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["method"] = request.method
        return httpx.Response(204)

    transport = httpx.MockTransport(handler)
    settings = Settings(github_token="tok")
    client = httpx.Client(base_url="https://api.github.com", transport=transport)
    gw = GitHubGateway(settings, client=client)

    gw.add_collaborator(owner="Snowziio", name="test3", username="alice", permission="push")
    assert seen["method"] == "PUT"
    assert seen["path"] == "/repos/Snowziio/test3/collaborators/alice"
```

- [ ] **Step 2: Run — verify fail**

```bash
python -m pytest tests/test_github_gateway.py::test_get_repo_returns_metadata_on_200 -v
```

Expected: FAIL (AttributeError on `get_repo`).

- [ ] **Step 3: Implement primitives**

In `github_gateway.py`, after the `create_repo_from_template` method (around line 104), add:

```python
def get_repo(self, *, owner: str, name: str) -> dict | None:
    """GET /repos/{owner}/{name}. Returns metadata dict, or None on 404."""
    resp = self.client.get(f"/repos/{owner}/{name}")
    if resp.status_code == 404:
        return None
    data = self._unwrap(resp)
    return dict(data)

def add_collaborator(
    self, *, owner: str, name: str, username: str, permission: str = "push"
) -> None:
    """PUT /repos/{owner}/{name}/collaborators/{username}. No return on 204."""
    resp = self.client.put(
        f"/repos/{owner}/{name}/collaborators/{username}",
        json={"permission": permission},
    )
    if resp.status_code not in (201, 204):
        raise GitHubGatewayError(
            resp.status_code, f"add_collaborator failed: {resp.text}"
        )
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_github_gateway.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/github_gateway.py tests/test_github_gateway.py
git commit -m "feat(github-gateway): add get_repo + add_collaborator primitives"
```

---

### Task B2: Static content constants for Bootstrap populate

**Files:**
- Create: `src/requirement_workflow_v12/project_bootstrap/__init__.py`
- Create: `src/requirement_workflow_v12/project_bootstrap/static_content.py`
- Test: `tests/test_project_bootstrap_static_content.py`

- [ ] **Step 1: Create module skeleton**

Create empty `__init__.py`:

```bash
mkdir -p src/requirement_workflow_v12/project_bootstrap
touch src/requirement_workflow_v12/project_bootstrap/__init__.py
```

- [ ] **Step 2: Write failing test**

Create `tests/test_project_bootstrap_static_content.py`:

```python
def test_project_readme_contains_req_registry_schema_doc():
    from requirement_workflow_v12.project_bootstrap.static_content import PROJECT_README_MD

    assert "req-registry.yaml" in PROJECT_README_MD
    assert "req_id:" in PROJECT_README_MD
    assert "project:" in PROJECT_README_MD


def test_req_registry_initial_yaml_has_empty_requirements_for_project():
    from requirement_workflow_v12.project_bootstrap.static_content import render_req_registry_yaml

    text = render_req_registry_yaml(project="test3")
    assert "project: test3" in text
    assert "requirements: []" in text


def test_environments_yaml_default_is_stub():
    from requirement_workflow_v12.project_bootstrap.static_content import render_environments_yaml

    text = render_environments_yaml(category="saas-ai-automation")
    # Must be valid YAML with a top-level environments key — empty map for MVP
    import yaml
    parsed = yaml.safe_load(text)
    assert "environments" in parsed


def test_secrets_todo_md_is_category_dependent():
    from requirement_workflow_v12.project_bootstrap.static_content import render_secrets_todo

    text_saas = render_secrets_todo(category="saas-ai-automation")
    text_bot = render_secrets_todo(category="enterprise-bot")
    assert "saas-ai-automation" in text_saas or "SaaS" in text_saas
    assert "enterprise-bot" in text_bot or "Bot" in text_bot


def test_render_claude_md_substitutes_placeholders():
    from requirement_workflow_v12.project_bootstrap.static_content import render_claude_md

    text = render_claude_md(project="test3")
    assert "test3" in text
    assert "{project}" not in text  # all placeholders resolved
```

- [ ] **Step 3: Run — verify fail**

```bash
python -m pytest tests/test_project_bootstrap_static_content.py -v
```

Expected: FAIL (ImportError).

- [ ] **Step 4: Implement `static_content.py`**

Create `src/requirement_workflow_v12/project_bootstrap/static_content.py`:

```python
"""Python constants for Bootstrap Step 4 populate commit.

All per-project / per-category files rendered here. Template repo
(Snowziio/Template-repository) stays minimal and category-agnostic;
this module is the canonical source for everything that varies.
"""
from __future__ import annotations

from datetime import date

from ..architecture_templates import derive_pkg


PROJECT_README_MD = """# project/ —— 项目级索引与上下文

本目录由 Bootstrap 在项目创建时自动落盘，存放**项目级**（非 REQ 级）的索引与上下文文件。

## req-registry.yaml

项目级 REQ 索引。由 coordinator service **自动 append**（非 plan-author 产出）。

### Schema (human + AI readable)

```yaml
project: <name>                    # 与 project_configs.project 一致
requirements:
  - req_id: REQ-YYYY-MM-DD-NNN     # 需求 ID
    title: "..."                   # 需求名称
    status: DRAFTING | APPROVED | PLANNING | SPEC_DRAFTING | MERGED | ABANDONED
    plan_id: null | PLAN-YYYY-MM-DD-NNN
    spec_pr: null | 123            # GitHub PR number
    created_at: 2026-04-20T10:00:00
```

### Update rules

- 写入方：coordinator service（不是 AI agent）
- 时机：REQ 创建 / 状态变更 / plan / spec PR 产出
- 失败不阻塞 REQ 主流程，只记告警 log

## environments.yaml

项目级环境抽象（dev / staging / prod），MVP 为占位骨架，演化通道延后。

## SECRETS-TODO.md

按 category 列出需要人工填充的 GitHub Actions secrets 清单；CI 配置 workflow 会读这些 secrets。
"""


def render_req_registry_yaml(*, project: str) -> str:
    return (
        f"# project/req-registry.yaml\n"
        f"# 自动生成于 Bootstrap 阶段；格式见 project/README.md\n"
        f"project: {project}\n"
        f"requirements: []\n"
    )


def render_environments_yaml(*, category: str) -> str:
    return (
        f"# project/environments.yaml\n"
        f"# 项目级环境抽象（MVP 骨架；演化通道延后）\n"
        f"# category: {category}\n"
        f"environments:\n"
        f"  dev: {{}}\n"
        f"  staging: {{}}\n"
        f"  prod: {{}}\n"
    )


_SECRETS_CATEGORY_HINTS: dict[str, list[str]] = {
    "enterprise-app": ["DATABASE_URL", "JWT_SIGNING_KEY"],
    "enterprise-bot": ["FEISHU_APP_ID", "FEISHU_APP_SECRET"],
    "miniprogram": ["WECHAT_APP_ID", "WECHAT_APP_SECRET"],
    "public-web-site": ["ANALYTICS_TOKEN"],
    "saas-ai-automation": ["OPENAI_API_KEY", "DATABASE_URL"],
}


def render_secrets_todo(*, category: str) -> str:
    hints = _SECRETS_CATEGORY_HINTS.get(category, [])
    bullet_lines = "\n".join(f"- [ ] `{k}`" for k in hints) if hints else "- [ ] (空)"
    return (
        f"# SECRETS-TODO ({category})\n\n"
        f"以下 secrets 需在 GitHub repo Settings → Secrets and variables → Actions 中手动填充，"
        f"Bootstrap 阶段不自动注入。\n\n"
        f"{bullet_lines}\n\n"
        f"填完后可删除此文件。\n"
    )


def render_claude_md(*, project: str) -> str:
    pkg = derive_pkg(project)
    today = date.today().isoformat()
    return (
        f"# CLAUDE.md — {project}\n\n"
        f"项目包名：`{pkg}`\n\n"
        f"创建于 Bootstrap：{today}\n\n"
        f"## Conventions\n\n"
        f"（Bootstrap 占位；后续通过 REQ 的 project_context_change gate 演化）\n"
    )


def render_skill_md(*, project: str) -> str:
    pkg = derive_pkg(project)
    today = date.today().isoformat()
    return (
        f"# SKILL.md — {project}\n\n"
        f"项目包名：`{pkg}`\n\n"
        f"创建于 Bootstrap：{today}\n\n"
        f"## Project-specific agent overrides\n\n"
        f"（Bootstrap 占位；后续通过 REQ 的 project_context_change gate 演化）\n"
    )
```

- [ ] **Step 5: Run tests**

```bash
python -m pytest tests/test_project_bootstrap_static_content.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/requirement_workflow_v12/project_bootstrap/ tests/test_project_bootstrap_static_content.py
git commit -m "feat(project-bootstrap): static content constants for populate commit"
```

---

## Phase C: Layer 3 facade — `bootstrap_project_repo` verb

### Task C1: Bootstrap types (`BootstrapRequest` / `BootstrapResult`)

**Files:**
- Create: `src/requirement_workflow_v12/project_bootstrap/types.py`
- Modify: `src/requirement_workflow_v12/project_repo/types.py` (keep `RepoRef` enabled — already reserved)
- Test: `tests/test_project_bootstrap_types.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_project_bootstrap_types.py`:

```python
def test_bootstrap_request_frozen_and_has_required_fields():
    import dataclasses
    from requirement_workflow_v12.project_bootstrap.types import BootstrapRequest

    req = BootstrapRequest(
        project="test3",
        category="saas-ai-automation",
        owner_user_id="ou_123",
        creator_chat_id="chat_abc",
    )
    assert dataclasses.is_dataclass(req)
    assert req.project == "test3"
    # frozen
    try:
        req.project = "x"
        raise AssertionError("expected FrozenInstanceError")
    except dataclasses.FrozenInstanceError:
        pass


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


def test_bootstrap_step_error_preserves_step_number():
    from requirement_workflow_v12.project_bootstrap.types import BootstrapStep, BootstrapStepError

    err = BootstrapStepError(step=BootstrapStep.CREATE_REPO, message="boom")
    assert err.step == BootstrapStep.CREATE_REPO
    assert "boom" in str(err)
```

- [ ] **Step 2: Run — verify fail**

```bash
python -m pytest tests/test_project_bootstrap_types.py -v
```

Expected: FAIL (ImportError).

- [ ] **Step 3: Implement types**

Create `src/requirement_workflow_v12/project_bootstrap/types.py`:

```python
"""Domain types for the project bootstrap orchestrator."""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class BootstrapStep(IntEnum):
    VALIDATE = 1
    UPSERT_CONFIG = 2
    CREATE_REPO = 3
    POPULATE_MAIN = 4
    CREATE_ARCHITECTURE_DOC = 5
    CREATE_FEISHU_GROUP = 6
    FINALIZE = 7


@dataclass(frozen=True)
class BootstrapRequest:
    project: str
    category: str
    owner_user_id: str
    creator_chat_id: str
    github_username: str | None = None  # For add_collaborator, if known
    resume: bool = False


@dataclass(frozen=True)
class BootstrapResult:
    project: str
    github_repo_url: str
    architecture_doc_id: str
    architecture_doc_url: str
    feishu_chat_id: str
    template_version: str


class BootstrapStepError(RuntimeError):
    """Raised when a single Bootstrap step fails.

    The `step` field lets the service record which step failed in
    `bootstrap_log` so `--resume` can continue from the next step.
    """

    def __init__(self, *, step: BootstrapStep, message: str):
        super().__init__(f"Bootstrap step {step.value} ({step.name}): {message}")
        self.step = step
        self.message = message
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_project_bootstrap_types.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/project_bootstrap/types.py tests/test_project_bootstrap_types.py
git commit -m "feat(project-bootstrap): BootstrapRequest / BootstrapResult / BootstrapStep types"
```

---

### Task C2: `ProjectRepoTools.bootstrap_project_repo` verb

**Files:**
- Modify: `src/requirement_workflow_v12/project_repo/tools.py` (Protocol + impl)
- Test: `tests/test_project_repo_bootstrap_verb.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_project_repo_bootstrap_verb.py`:

```python
from unittest.mock import MagicMock

from requirement_workflow_v12.project_repo.tools import (
    GitHubProjectRepoTools,
    ProjectRepoError,
)


def _fake_gateway_happy():
    gw = MagicMock()
    gw.get_repo.return_value = None  # repo does not exist yet
    gw.create_repo_from_template.return_value = "https://github.com/Snowziio/test3"
    gw.commit_files.return_value = "commit_sha_1"
    gw.add_collaborator.return_value = None
    return gw


def test_bootstrap_project_repo_generates_and_populates_main():
    gw = _fake_gateway_happy()
    tools = GitHubProjectRepoTools(gw)

    populate_files = {
        "docs/ARCHITECTURE.md": "# arch",
        "project/README.md": "# proj readme",
        "project/req-registry.yaml": "project: test3\nrequirements: []\n",
        "project/environments.yaml": "environments:\n  dev: {}\n",
        "project/SECRETS-TODO.md": "# secrets",
        "CLAUDE.md": "# claude",
        "SKILL.md": "# skill",
    }

    result = tools.bootstrap_project_repo(
        template_owner="Snowziio",
        template_repo="Template-repository",
        new_owner="Snowziio",
        new_name="test3",
        populate_files=populate_files,
        populate_commit_message="project bootstrap: populate",
        collaborator_username="alice",
    )

    assert result.html_url == "https://github.com/Snowziio/test3"
    assert result.initial_populate_commit_sha == "commit_sha_1"
    gw.create_repo_from_template.assert_called_once()
    gw.commit_files.assert_called_once()
    gw.add_collaborator.assert_called_once_with(
        owner="Snowziio", name="test3", username="alice", permission="push"
    )


def test_bootstrap_project_repo_skips_repo_creation_when_already_exists():
    gw = MagicMock()
    gw.get_repo.return_value = {
        "html_url": "https://github.com/Snowziio/test3",
        "default_branch": "main",
    }
    gw.commit_files.return_value = "commit_sha_2"

    tools = GitHubProjectRepoTools(gw)
    result = tools.bootstrap_project_repo(
        template_owner="Snowziio",
        template_repo="Template-repository",
        new_owner="Snowziio",
        new_name="test3",
        populate_files={"CLAUDE.md": "x"},
        populate_commit_message="populate",
        collaborator_username=None,
    )
    gw.create_repo_from_template.assert_not_called()
    assert result.html_url == "https://github.com/Snowziio/test3"


def test_bootstrap_project_repo_wraps_gateway_errors():
    from requirement_workflow_v12.github_gateway import GitHubGatewayError

    gw = MagicMock()
    gw.get_repo.return_value = None
    gw.create_repo_from_template.side_effect = GitHubGatewayError(500, "boom")

    tools = GitHubProjectRepoTools(gw)
    try:
        tools.bootstrap_project_repo(
            template_owner="Snowziio",
            template_repo="Template-repository",
            new_owner="Snowziio",
            new_name="test3",
            populate_files={"CLAUDE.md": "x"},
            populate_commit_message="populate",
            collaborator_username=None,
        )
        raise AssertionError("expected ProjectRepoError")
    except ProjectRepoError as exc:
        assert "bootstrap_project_repo" in str(exc)
```

- [ ] **Step 2: Run — verify fail**

```bash
python -m pytest tests/test_project_repo_bootstrap_verb.py -v
```

Expected: FAIL (no method `bootstrap_project_repo`).

- [ ] **Step 3: Enable `RepoRef` + add return type**

Modify `src/requirement_workflow_v12/project_repo/types.py`: the existing `RepoRef` is reserved. Replace its docstring and add a new `BootstrapRepoResult`:

```python
@dataclass(frozen=True)
class RepoRef:
    """Reference to a GitHub repository (owner + name + html_url + default_branch + initial_commit_sha)."""
    owner: str
    name: str
    html_url: str
    default_branch: str
    initial_commit_sha: str


@dataclass(frozen=True)
class BootstrapRepoResult:
    """Returned by ``ProjectRepoTools.bootstrap_project_repo``.

    ``initial_populate_commit_sha`` is the sha of the Populate commit
    (Bootstrap Step 4); ``html_url`` is the URL of the newly generated
    repo regardless of whether it was created fresh or reused.
    """
    html_url: str
    default_branch: str
    initial_populate_commit_sha: str
```

- [ ] **Step 4: Add `bootstrap_project_repo` to Protocol + impl**

In `src/requirement_workflow_v12/project_repo/tools.py`, add to the `ProjectRepoTools` Protocol:

```python
def bootstrap_project_repo(
    self,
    *,
    template_owner: str,
    template_repo: str,
    new_owner: str,
    new_name: str,
    populate_files: dict[str, str],
    populate_commit_message: str,
    collaborator_username: str | None,
) -> BootstrapRepoResult: ...
```

Add import at top of the file:

```python
from .types import BootstrapRepoResult, PlanArtifacts, PlanCommitResult, PrRef, ProjectContext, SpecArtifacts
```

Add the implementation to `GitHubProjectRepoTools`:

```python
def bootstrap_project_repo(
    self,
    *,
    template_owner: str,
    template_repo: str,
    new_owner: str,
    new_name: str,
    populate_files: dict[str, str],
    populate_commit_message: str,
    collaborator_username: str | None,
) -> BootstrapRepoResult:
    try:
        existing = self._gw.get_repo(owner=new_owner, name=new_name)
        if existing is None:
            html_url = self._gw.create_repo_from_template(
                template_owner=template_owner,
                template_repo=template_repo,
                owner=new_owner,
                name=new_name,
                private=True,
                description=f"Bootstrapped project {new_name}",
            )
            default_branch = "main"
        else:
            html_url = str(existing["html_url"])
            default_branch = str(existing.get("default_branch", "main"))

        file_changes = [FileChange(path=p, content=c) for p, c in populate_files.items()]
        populate_sha = self._gw.commit_files(
            owner=new_owner,
            repo=new_name,
            branch=default_branch,
            files=file_changes,
            message=populate_commit_message,
        )

        if collaborator_username:
            self._gw.add_collaborator(
                owner=new_owner, name=new_name, username=collaborator_username, permission="push"
            )
    except GitHubGatewayError as exc:
        raise ProjectRepoError(
            f"bootstrap_project_repo failed for {new_owner}/{new_name}: {exc}",
            recoverable=False,
        ) from exc
    return BootstrapRepoResult(
        html_url=html_url,
        default_branch=default_branch,
        initial_populate_commit_sha=populate_sha,
    )
```

- [ ] **Step 5: Run tests**

```bash
python -m pytest tests/test_project_repo_bootstrap_verb.py -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/requirement_workflow_v12/project_repo/ tests/test_project_repo_bootstrap_verb.py
git commit -m "feat(project-repo): bootstrap_project_repo verb (generate + populate + collaborator)"
```

---

## Phase D: Layer 2 orchestrator — `ProjectBootstrapService`

### Task D1: Service skeleton + Step 1 (VALIDATE)

**Files:**
- Create: `src/requirement_workflow_v12/project_bootstrap/service.py`
- Create: `src/requirement_workflow_v12/project_bootstrap/state.py`
- Test: `tests/test_project_bootstrap_service.py`

- [ ] **Step 1: Write failing tests for Step 1 (validate)**

Create `tests/test_project_bootstrap_service.py`:

```python
from unittest.mock import MagicMock

import pytest

from requirement_workflow_v12.project_bootstrap.service import (
    ProjectBootstrapService,
    ValidationError,
)
from requirement_workflow_v12.project_bootstrap.types import BootstrapRequest


def _make_service(existing_projects=None):
    existing = existing_projects or {}
    repo_tools = MagicMock()
    feishu_gw = MagicMock()
    feishu_gw.list_project_configs.return_value = existing
    feishu_gw.upsert_project_config.side_effect = lambda project, cfg: cfg
    github_gw = MagicMock()
    github_gw.get_repo.return_value = None
    return ProjectBootstrapService(
        repo_tools=repo_tools,
        feishu_gateway=feishu_gw,
        github_gateway=github_gw,
        template_owner="Snowziio",
        template_repo="Template-repository",
        new_owner="Snowziio",
    ), repo_tools, feishu_gw, github_gw


def test_validate_rejects_uppercase_project_name():
    svc, *_ = _make_service()
    req = BootstrapRequest(
        project="TestProj",
        category="saas-ai-automation",
        owner_user_id="ou_1",
        creator_chat_id="c1",
    )
    with pytest.raises(ValidationError, match="name"):
        svc.validate(req)


def test_validate_rejects_short_project_name():
    svc, *_ = _make_service()
    req = BootstrapRequest(
        project="ab",  # < 3 chars
        category="saas-ai-automation",
        owner_user_id="ou_1",
        creator_chat_id="c1",
    )
    with pytest.raises(ValidationError):
        svc.validate(req)


def test_validate_rejects_unknown_category():
    svc, *_ = _make_service()
    req = BootstrapRequest(
        project="test3",
        category="no-such-category",
        owner_user_id="ou_1",
        creator_chat_id="c1",
    )
    with pytest.raises(ValidationError, match="category"):
        svc.validate(req)


def test_validate_rejects_existing_project_when_not_resuming():
    from requirement_workflow_v12.project_config import ProjectConfig

    existing = {"test3": ProjectConfig(
        category="saas-ai-automation",
        template_version="saas-ai-automation.v1",
        architecture_doc_id="",
        architecture_doc_url="",
        bootstrap_status="PROVISIONED",
    )}
    svc, *_ = _make_service(existing_projects=existing)
    req = BootstrapRequest(
        project="test3",
        category="saas-ai-automation",
        owner_user_id="ou_1",
        creator_chat_id="c1",
        resume=False,
    )
    with pytest.raises(ValidationError, match="already"):
        svc.validate(req)


def test_validate_rejects_existing_repo_name():
    svc, _, _, github_gw = _make_service()
    github_gw.get_repo.return_value = {"html_url": "https://github.com/Snowziio/test3"}
    req = BootstrapRequest(
        project="test3",
        category="saas-ai-automation",
        owner_user_id="ou_1",
        creator_chat_id="c1",
    )
    with pytest.raises(ValidationError, match="GitHub"):
        svc.validate(req)


def test_validate_accepts_valid_name_and_category():
    svc, *_ = _make_service()
    req = BootstrapRequest(
        project="test3",
        category="saas-ai-automation",
        owner_user_id="ou_1",
        creator_chat_id="c1",
    )
    svc.validate(req)  # no raise
```

- [ ] **Step 2: Run — verify fail**

```bash
python -m pytest tests/test_project_bootstrap_service.py -v
```

Expected: FAIL (ImportError).

- [ ] **Step 3: Implement `state.py`**

Create `src/requirement_workflow_v12/project_bootstrap/state.py`:

```python
"""Bootstrap log helpers: append entries + read last-completed step."""
from __future__ import annotations

from datetime import datetime, timezone

from .types import BootstrapStep


def append_log_entry(
    log: list[dict],
    *,
    step: BootstrapStep,
    status: str,
    error_msg: str | None = None,
) -> list[dict]:
    """Return a new log list with an entry appended. Does not mutate input."""
    entry = {
        "step": int(step),
        "step_name": step.name,
        "ts": datetime.now(timezone.utc).isoformat(),
        "status": status,
    }
    if error_msg is not None:
        entry["error_msg"] = error_msg
    return list(log) + [entry]


def last_completed_step(log: list[dict]) -> int:
    """Return the largest step number with status=='ok'; 0 if none."""
    completed = [e["step"] for e in log if e.get("status") == "ok"]
    return max(completed) if completed else 0
```

- [ ] **Step 4: Implement `service.py` Step 1 only (rest will fill in next tasks)**

Create `src/requirement_workflow_v12/project_bootstrap/service.py`:

```python
"""Project Bootstrap orchestrator.

Runs a 7-step flow: validate → upsert config → create repo → populate →
create arch doc → create group → finalize. Each step is idempotent and
`--resume` skips already-completed steps (based on bootstrap_log).
"""
from __future__ import annotations

import logging
import re
from dataclasses import replace

from ..architecture_templates import UnknownCategory, available_categories, render_template
from ..project_config import ProjectConfig
from .types import BootstrapRequest, BootstrapResult, BootstrapStep, BootstrapStepError


_logger = logging.getLogger(__name__)

_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{2,30}$")


class ValidationError(ValueError):
    """Raised by `validate()` on illegal inputs (Step 1)."""


class ProjectBootstrapService:
    def __init__(
        self,
        *,
        repo_tools,
        feishu_gateway,
        github_gateway,
        template_owner: str,
        template_repo: str,
        new_owner: str,
    ):
        self._repo_tools = repo_tools
        self._feishu = feishu_gateway
        self._github = github_gateway
        self._template_owner = template_owner
        self._template_repo = template_repo
        self._new_owner = new_owner

    # Step 1: VALIDATE
    def validate(self, request: BootstrapRequest) -> None:
        if not _NAME_RE.match(request.project):
            raise ValidationError(
                f"project name must match {_NAME_RE.pattern}: got {request.project!r}"
            )
        if request.category not in available_categories():
            raise ValidationError(
                f"unknown category {request.category!r}; available: {available_categories()}"
            )
        if not request.owner_user_id:
            raise ValidationError("owner_user_id is required")

        existing_configs = self._feishu.list_project_configs()
        if request.project in existing_configs and not request.resume:
            raise ValidationError(
                f"project {request.project} already exists; use --resume to continue"
            )

        existing_repo = self._github.get_repo(owner=self._new_owner, name=request.project)
        if existing_repo is not None and not request.resume:
            raise ValidationError(
                f"GitHub repo {self._new_owner}/{request.project} already exists"
            )
```

- [ ] **Step 5: Run tests**

```bash
python -m pytest tests/test_project_bootstrap_service.py -v
```

Expected: all 6 PASS.

- [ ] **Step 6: Commit**

```bash
git add src/requirement_workflow_v12/project_bootstrap/ tests/test_project_bootstrap_service.py
git commit -m "feat(project-bootstrap): service skeleton + Step 1 validate"
```

---

### Task D2: Bootstrap Step 2 — UPSERT_CONFIG

**Files:**
- Modify: `src/requirement_workflow_v12/project_bootstrap/service.py`
- Test: `tests/test_project_bootstrap_service.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_project_bootstrap_service.py`:

```python
def test_upsert_config_creates_new_row_with_bootstrapping_status():
    from requirement_workflow_v12.project_bootstrap.types import BootstrapStep

    svc, _, feishu_gw, _ = _make_service()
    req = BootstrapRequest(
        project="test3",
        category="saas-ai-automation",
        owner_user_id="ou_1",
        creator_chat_id="c1",
    )
    cfg = svc.upsert_config(req, template_version="saas-ai-automation.v1")
    assert cfg.bootstrap_status == "BOOTSTRAPPING"
    assert cfg.category == "saas-ai-automation"
    assert cfg.template_version == "saas-ai-automation.v1"
    # upsert was called
    feishu_gw.upsert_project_config.assert_called_once()
    # log has Step 2 entry
    assert any(e["step"] == int(BootstrapStep.UPSERT_CONFIG) and e["status"] == "ok"
               for e in cfg.bootstrap_log)


def test_upsert_config_preserves_existing_fields_on_resume():
    from requirement_workflow_v12.project_config import ProjectConfig
    from requirement_workflow_v12.project_bootstrap.types import BootstrapStep

    existing = ProjectConfig(
        category="saas-ai-automation",
        template_version="saas-ai-automation.v1",
        architecture_doc_id="doc_old",
        architecture_doc_url="https://old",
        bootstrap_status="BOOTSTRAPPING",
        bootstrap_log=[{"step": 2, "step_name": "UPSERT_CONFIG", "ts": "old-ts", "status": "ok"}],
    )
    svc, _, feishu_gw, _ = _make_service(existing_projects={"test3": existing})
    req = BootstrapRequest(
        project="test3",
        category="saas-ai-automation",
        owner_user_id="ou_1",
        creator_chat_id="c1",
        resume=True,
    )
    cfg = svc.upsert_config(req, template_version="saas-ai-automation.v1")
    # existing arch doc preserved
    assert cfg.architecture_doc_id == "doc_old"
    assert cfg.bootstrap_status == "BOOTSTRAPPING"
```

- [ ] **Step 2: Run — verify fail**

```bash
python -m pytest tests/test_project_bootstrap_service.py::test_upsert_config_creates_new_row_with_bootstrapping_status -v
```

Expected: FAIL (no method `upsert_config`).

- [ ] **Step 3: Implement `upsert_config`**

Add to `ProjectBootstrapService` in `service.py`:

```python
# Step 2: UPSERT_CONFIG
def upsert_config(
    self, request: BootstrapRequest, *, template_version: str
) -> ProjectConfig:
    from .state import append_log_entry

    existing = self._feishu.list_project_configs().get(request.project)
    if existing is None:
        cfg = ProjectConfig(
            category=request.category,
            template_version=template_version,
            architecture_doc_id="",
            architecture_doc_url="",
            bootstrap_status="BOOTSTRAPPING",
            project_status="BOOTSTRAPPING",
        )
    else:
        cfg = replace(
            existing,
            category=request.category,
            template_version=template_version,
            bootstrap_status="BOOTSTRAPPING",
            project_status="BOOTSTRAPPING",
        )
    new_log = append_log_entry(cfg.bootstrap_log, step=BootstrapStep.UPSERT_CONFIG, status="ok")
    cfg = replace(cfg, bootstrap_log=new_log)
    self._feishu.upsert_project_config(request.project, cfg)
    return cfg
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_project_bootstrap_service.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/project_bootstrap/service.py tests/test_project_bootstrap_service.py
git commit -m "feat(project-bootstrap): Step 2 upsert project_configs row"
```

---

### Task D3: Bootstrap Step 3-4 — CREATE_REPO + POPULATE_MAIN

**Files:**
- Modify: `src/requirement_workflow_v12/project_bootstrap/service.py`
- Test: `tests/test_project_bootstrap_service.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_project_bootstrap_service.py`:

```python
def test_create_repo_and_populate_renders_all_seven_files_and_records_sha():
    from requirement_workflow_v12.project_bootstrap.types import BootstrapStep
    from requirement_workflow_v12.project_repo.types import BootstrapRepoResult

    svc, repo_tools, feishu_gw, _ = _make_service()
    repo_tools.bootstrap_project_repo.return_value = BootstrapRepoResult(
        html_url="https://github.com/Snowziio/test3",
        default_branch="main",
        initial_populate_commit_sha="sha_xyz",
    )
    req = BootstrapRequest(
        project="test3",
        category="saas-ai-automation",
        owner_user_id="ou_1",
        creator_chat_id="c1",
        github_username="alice",
    )
    rendered_arch = "# arch for test3"

    cfg_after = svc.create_repo_and_populate(
        req,
        template_version="saas-ai-automation.v1",
        rendered_architecture_md=rendered_arch,
    )
    # Verifies bootstrap_project_repo was called with 7 populate files
    call = repo_tools.bootstrap_project_repo.call_args
    populate_files = call.kwargs["populate_files"]
    assert set(populate_files.keys()) == {
        "docs/ARCHITECTURE.md",
        "project/README.md",
        "project/req-registry.yaml",
        "project/environments.yaml",
        "project/SECRETS-TODO.md",
        "CLAUDE.md",
        "SKILL.md",
    }
    assert populate_files["docs/ARCHITECTURE.md"] == rendered_arch
    assert "project: test3" in populate_files["project/req-registry.yaml"]
    assert cfg_after.github_repo_url == "https://github.com/Snowziio/test3"
    # log has Steps 3 + 4
    step_numbers = {e["step"] for e in cfg_after.bootstrap_log}
    assert int(BootstrapStep.CREATE_REPO) in step_numbers
    assert int(BootstrapStep.POPULATE_MAIN) in step_numbers


def test_create_repo_skips_when_already_present_in_log():
    # If log says CREATE_REPO already ok, skip bootstrap_project_repo call
    from requirement_workflow_v12.project_config import ProjectConfig
    from requirement_workflow_v12.project_bootstrap.types import BootstrapStep
    from requirement_workflow_v12.project_repo.types import BootstrapRepoResult

    prior_log = [
        {"step": int(BootstrapStep.UPSERT_CONFIG), "step_name": "UPSERT_CONFIG", "ts": "t", "status": "ok"},
        {"step": int(BootstrapStep.CREATE_REPO), "step_name": "CREATE_REPO", "ts": "t", "status": "ok"},
        {"step": int(BootstrapStep.POPULATE_MAIN), "step_name": "POPULATE_MAIN", "ts": "t", "status": "ok"},
    ]
    existing = ProjectConfig(
        category="saas-ai-automation",
        template_version="saas-ai-automation.v1",
        architecture_doc_id="",
        architecture_doc_url="",
        bootstrap_status="BOOTSTRAPPING",
        bootstrap_log=prior_log,
        github_repo_url="https://github.com/Snowziio/test3",
    )
    svc, repo_tools, feishu_gw, _ = _make_service(existing_projects={"test3": existing})
    req = BootstrapRequest(
        project="test3",
        category="saas-ai-automation",
        owner_user_id="ou_1",
        creator_chat_id="c1",
        resume=True,
    )
    svc.create_repo_and_populate(
        req,
        template_version="saas-ai-automation.v1",
        rendered_architecture_md="# arch",
    )
    # Must NOT call repo_tools.bootstrap_project_repo — idempotent skip
    repo_tools.bootstrap_project_repo.assert_not_called()
```

- [ ] **Step 2: Run — verify fail**

```bash
python -m pytest tests/test_project_bootstrap_service.py::test_create_repo_and_populate_renders_all_seven_files_and_records_sha -v
```

Expected: FAIL (AttributeError `create_repo_and_populate`).

- [ ] **Step 3: Implement `create_repo_and_populate`**

Add to `ProjectBootstrapService`:

```python
# Steps 3 + 4: CREATE_REPO + POPULATE_MAIN
def create_repo_and_populate(
    self,
    request: BootstrapRequest,
    *,
    template_version: str,
    rendered_architecture_md: str,
) -> ProjectConfig:
    from .state import append_log_entry, last_completed_step
    from .static_content import (
        PROJECT_README_MD,
        render_claude_md,
        render_environments_yaml,
        render_req_registry_yaml,
        render_secrets_todo,
        render_skill_md,
    )

    cfg = self._feishu.list_project_configs()[request.project]
    last_step = last_completed_step(cfg.bootstrap_log)
    if last_step >= int(BootstrapStep.POPULATE_MAIN):
        _logger.info("bootstrap: skipping create_repo+populate (already completed) project=%s", request.project)
        return cfg

    populate_files = {
        "docs/ARCHITECTURE.md": rendered_architecture_md,
        "project/README.md": PROJECT_README_MD,
        "project/req-registry.yaml": render_req_registry_yaml(project=request.project),
        "project/environments.yaml": render_environments_yaml(category=request.category),
        "project/SECRETS-TODO.md": render_secrets_todo(category=request.category),
        "CLAUDE.md": render_claude_md(project=request.project),
        "SKILL.md": render_skill_md(project=request.project),
    }
    try:
        result = self._repo_tools.bootstrap_project_repo(
            template_owner=self._template_owner,
            template_repo=self._template_repo,
            new_owner=self._new_owner,
            new_name=request.project,
            populate_files=populate_files,
            populate_commit_message=f"project bootstrap: populate initial files for {request.project}",
            collaborator_username=request.github_username,
        )
    except Exception as exc:
        failed_log = append_log_entry(
            cfg.bootstrap_log, step=BootstrapStep.CREATE_REPO, status="error", error_msg=str(exc)
        )
        cfg = replace(cfg, bootstrap_log=failed_log)
        self._feishu.upsert_project_config(request.project, cfg)
        raise BootstrapStepError(step=BootstrapStep.CREATE_REPO, message=str(exc)) from exc

    log = append_log_entry(cfg.bootstrap_log, step=BootstrapStep.CREATE_REPO, status="ok")
    log = append_log_entry(log, step=BootstrapStep.POPULATE_MAIN, status="ok")
    cfg = replace(
        cfg,
        github_repo_url=result.html_url,
        github_owner_username=request.github_username or "",
        bootstrap_log=log,
    )
    self._feishu.upsert_project_config(request.project, cfg)
    return cfg
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_project_bootstrap_service.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/project_bootstrap/service.py tests/test_project_bootstrap_service.py
git commit -m "feat(project-bootstrap): Steps 3+4 create repo + populate main"
```

---

### Task D4: Bootstrap Step 5 — CREATE_ARCHITECTURE_DOC

**Files:**
- Modify: `src/requirement_workflow_v12/project_bootstrap/service.py`
- Test: `tests/test_project_bootstrap_service.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_project_bootstrap_service.py`:

```python
def test_create_architecture_doc_writes_rendered_text_to_feishu():
    from unittest.mock import MagicMock
    from requirement_workflow_v12.project_bootstrap.types import BootstrapStep
    from requirement_workflow_v12.project_config import ProjectConfig

    # seed config with repo created
    existing = ProjectConfig(
        category="saas-ai-automation",
        template_version="saas-ai-automation.v1",
        architecture_doc_id="",
        architecture_doc_url="",
        bootstrap_status="BOOTSTRAPPING",
        github_repo_url="https://github.com/Snowziio/test3",
        bootstrap_log=[
            {"step": int(s), "step_name": s.name, "ts": "t", "status": "ok"}
            for s in (BootstrapStep.UPSERT_CONFIG, BootstrapStep.CREATE_REPO, BootstrapStep.POPULATE_MAIN)
        ],
    )
    svc, _, feishu_gw, _ = _make_service(existing_projects={"test3": existing})
    feishu_gw.create_architecture_document.return_value = MagicMock(
        document_id="doc_arch", document_url="https://feishu.example/doc_arch"
    )
    feishu_gw.write_document_text.return_value = None

    req = BootstrapRequest(
        project="test3",
        category="saas-ai-automation",
        owner_user_id="ou_1",
        creator_chat_id="c1",
    )
    cfg = svc.create_architecture_doc(req, rendered_architecture_md="# arch doc content")

    assert cfg.architecture_doc_id == "doc_arch"
    assert cfg.architecture_doc_url == "https://feishu.example/doc_arch"
    feishu_gw.create_architecture_document.assert_called_once_with("test3")
    feishu_gw.write_document_text.assert_called_once_with("doc_arch", "# arch doc content")


def test_create_architecture_doc_skips_when_already_set():
    from requirement_workflow_v12.project_config import ProjectConfig
    from requirement_workflow_v12.project_bootstrap.types import BootstrapStep

    existing = ProjectConfig(
        category="saas-ai-automation",
        template_version="saas-ai-automation.v1",
        architecture_doc_id="doc_existing",
        architecture_doc_url="https://feishu.example/doc_existing",
        bootstrap_status="BOOTSTRAPPING",
        bootstrap_log=[
            {"step": int(s), "step_name": s.name, "ts": "t", "status": "ok"}
            for s in (BootstrapStep.UPSERT_CONFIG, BootstrapStep.CREATE_REPO, BootstrapStep.POPULATE_MAIN, BootstrapStep.CREATE_ARCHITECTURE_DOC)
        ],
    )
    svc, _, feishu_gw, _ = _make_service(existing_projects={"test3": existing})
    req = BootstrapRequest(
        project="test3",
        category="saas-ai-automation",
        owner_user_id="ou_1",
        creator_chat_id="c1",
        resume=True,
    )
    svc.create_architecture_doc(req, rendered_architecture_md="# arch")
    feishu_gw.create_architecture_document.assert_not_called()
```

- [ ] **Step 2: Run — verify fail**

```bash
python -m pytest tests/test_project_bootstrap_service.py::test_create_architecture_doc_writes_rendered_text_to_feishu -v
```

Expected: FAIL.

- [ ] **Step 3: Implement `create_architecture_doc`**

Add to service:

```python
# Step 5: CREATE_ARCHITECTURE_DOC
def create_architecture_doc(
    self, request: BootstrapRequest, *, rendered_architecture_md: str
) -> ProjectConfig:
    from .state import append_log_entry, last_completed_step

    cfg = self._feishu.list_project_configs()[request.project]
    if last_completed_step(cfg.bootstrap_log) >= int(BootstrapStep.CREATE_ARCHITECTURE_DOC):
        _logger.info("bootstrap: skipping create_architecture_doc (already ok) project=%s", request.project)
        return cfg

    try:
        created = self._feishu.create_architecture_document(request.project)
        if created is None:
            raise BootstrapStepError(
                step=BootstrapStep.CREATE_ARCHITECTURE_DOC,
                message="create_architecture_document returned None (missing folder token)",
            )
        self._feishu.write_document_text(created.document_id, rendered_architecture_md)
    except Exception as exc:
        failed_log = append_log_entry(
            cfg.bootstrap_log, step=BootstrapStep.CREATE_ARCHITECTURE_DOC,
            status="error", error_msg=str(exc),
        )
        cfg = replace(cfg, bootstrap_log=failed_log)
        self._feishu.upsert_project_config(request.project, cfg)
        if isinstance(exc, BootstrapStepError):
            raise
        raise BootstrapStepError(
            step=BootstrapStep.CREATE_ARCHITECTURE_DOC, message=str(exc)
        ) from exc

    new_log = append_log_entry(cfg.bootstrap_log, step=BootstrapStep.CREATE_ARCHITECTURE_DOC, status="ok")
    cfg = replace(
        cfg,
        architecture_doc_id=created.document_id,
        architecture_doc_url=created.document_url,
        bootstrap_log=new_log,
    )
    self._feishu.upsert_project_config(request.project, cfg)
    return cfg
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_project_bootstrap_service.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/project_bootstrap/service.py tests/test_project_bootstrap_service.py
git commit -m "feat(project-bootstrap): Step 5 create Feishu ARCHITECTURE doc"
```

---

### Task D5: Bootstrap Step 6 — CREATE_FEISHU_GROUP

**Files:**
- Modify: `src/requirement_workflow_v12/project_bootstrap/service.py`
- Test: `tests/test_project_bootstrap_service.py`

- [ ] **Step 1: Write failing test**

Append:

```python
def test_create_feishu_group_persists_chat_id():
    from unittest.mock import MagicMock
    from requirement_workflow_v12.project_config import ProjectConfig
    from requirement_workflow_v12.project_bootstrap.types import BootstrapStep

    prior_steps = [BootstrapStep.UPSERT_CONFIG, BootstrapStep.CREATE_REPO,
                   BootstrapStep.POPULATE_MAIN, BootstrapStep.CREATE_ARCHITECTURE_DOC]
    existing = ProjectConfig(
        category="saas-ai-automation",
        template_version="saas-ai-automation.v1",
        architecture_doc_id="doc_x",
        architecture_doc_url="https://example/doc_x",
        bootstrap_status="BOOTSTRAPPING",
        bootstrap_log=[
            {"step": int(s), "step_name": s.name, "ts": "t", "status": "ok"} for s in prior_steps
        ],
    )
    svc, _, feishu_gw, _ = _make_service(existing_projects={"test3": existing})
    feishu_gw.create_project_group.return_value = MagicMock(chat_id="oc_test3_group")

    req = BootstrapRequest(
        project="test3",
        category="saas-ai-automation",
        owner_user_id="ou_1",
        creator_chat_id="c1",
    )
    cfg = svc.create_feishu_group(req)
    assert cfg.feishu_chat_id == "oc_test3_group"
    feishu_gw.create_project_group.assert_called_once_with(
        project="test3", owner_user_id="ou_1", member_user_ids=["ou_1"]
    )


def test_create_feishu_group_skip_when_chat_id_already_set():
    from requirement_workflow_v12.project_config import ProjectConfig
    from requirement_workflow_v12.project_bootstrap.types import BootstrapStep

    prior_steps = [BootstrapStep.UPSERT_CONFIG, BootstrapStep.CREATE_REPO,
                   BootstrapStep.POPULATE_MAIN, BootstrapStep.CREATE_ARCHITECTURE_DOC,
                   BootstrapStep.CREATE_FEISHU_GROUP]
    existing = ProjectConfig(
        category="saas-ai-automation",
        template_version="saas-ai-automation.v1",
        architecture_doc_id="doc_x",
        architecture_doc_url="",
        bootstrap_status="BOOTSTRAPPING",
        feishu_chat_id="oc_existing",
        bootstrap_log=[
            {"step": int(s), "step_name": s.name, "ts": "t", "status": "ok"} for s in prior_steps
        ],
    )
    svc, _, feishu_gw, _ = _make_service(existing_projects={"test3": existing})
    req = BootstrapRequest(
        project="test3", category="saas-ai-automation",
        owner_user_id="ou_1", creator_chat_id="c1", resume=True,
    )
    svc.create_feishu_group(req)
    feishu_gw.create_project_group.assert_not_called()
```

- [ ] **Step 2: Run — verify fail**

```bash
python -m pytest tests/test_project_bootstrap_service.py::test_create_feishu_group_persists_chat_id -v
```

Expected: FAIL.

- [ ] **Step 3: Implement `create_feishu_group`**

Add to service:

```python
# Step 6: CREATE_FEISHU_GROUP
def create_feishu_group(self, request: BootstrapRequest) -> ProjectConfig:
    from .state import append_log_entry, last_completed_step

    cfg = self._feishu.list_project_configs()[request.project]
    if last_completed_step(cfg.bootstrap_log) >= int(BootstrapStep.CREATE_FEISHU_GROUP):
        return cfg

    try:
        created = self._feishu.create_project_group(
            project=request.project,
            owner_user_id=request.owner_user_id,
            member_user_ids=[request.owner_user_id],
        )
    except Exception as exc:
        failed = append_log_entry(
            cfg.bootstrap_log, step=BootstrapStep.CREATE_FEISHU_GROUP,
            status="error", error_msg=str(exc),
        )
        cfg = replace(cfg, bootstrap_log=failed)
        self._feishu.upsert_project_config(request.project, cfg)
        raise BootstrapStepError(step=BootstrapStep.CREATE_FEISHU_GROUP, message=str(exc)) from exc

    new_log = append_log_entry(cfg.bootstrap_log, step=BootstrapStep.CREATE_FEISHU_GROUP, status="ok")
    cfg = replace(cfg, feishu_chat_id=created.chat_id, bootstrap_log=new_log)
    self._feishu.upsert_project_config(request.project, cfg)
    return cfg
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_project_bootstrap_service.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/project_bootstrap/service.py tests/test_project_bootstrap_service.py
git commit -m "feat(project-bootstrap): Step 6 create Feishu project group"
```

---

### Task D6: Bootstrap Step 7 — FINALIZE + top-level `run` orchestrator

**Files:**
- Modify: `src/requirement_workflow_v12/project_bootstrap/service.py`
- Test: `tests/test_project_bootstrap_service.py`

- [ ] **Step 1: Write failing test for `run` happy path**

Append:

```python
def test_run_end_to_end_produces_provisioned_config_and_bootstrap_result():
    from unittest.mock import MagicMock
    from requirement_workflow_v12.project_bootstrap.types import BootstrapStep
    from requirement_workflow_v12.project_repo.types import BootstrapRepoResult

    svc, repo_tools, feishu_gw, _ = _make_service()
    repo_tools.bootstrap_project_repo.return_value = BootstrapRepoResult(
        html_url="https://github.com/Snowziio/test3",
        default_branch="main",
        initial_populate_commit_sha="sha1",
    )
    feishu_gw.create_architecture_document.return_value = MagicMock(
        document_id="doc_x", document_url="https://feishu.example/doc_x",
    )
    feishu_gw.write_document_text.return_value = None
    feishu_gw.create_project_group.return_value = MagicMock(chat_id="oc_test3_group")
    # Simulate upsert_project_config maintaining state across calls:
    state = {}
    def _upsert(project, cfg):
        state[project] = cfg
        return cfg
    feishu_gw.upsert_project_config.side_effect = _upsert
    feishu_gw.list_project_configs.side_effect = lambda: dict(state)

    req = BootstrapRequest(
        project="test3",
        category="saas-ai-automation",
        owner_user_id="ou_1",
        creator_chat_id="c1",
        github_username="alice",
    )
    result = svc.run(req)
    assert result.project == "test3"
    assert result.github_repo_url == "https://github.com/Snowziio/test3"
    assert result.architecture_doc_id == "doc_x"
    assert result.feishu_chat_id == "oc_test3_group"
    # final status
    final_cfg = state["test3"]
    assert final_cfg.bootstrap_status == "PROVISIONED"
    assert final_cfg.project_status == "PROVISIONED"
    assert final_cfg.bootstrap_completed_at is not None
    # all 7 steps recorded
    step_numbers = {e["step"] for e in final_cfg.bootstrap_log if e["status"] == "ok"}
    assert step_numbers == {int(s) for s in BootstrapStep}
```

- [ ] **Step 2: Run — verify fail**

```bash
python -m pytest tests/test_project_bootstrap_service.py::test_run_end_to_end_produces_provisioned_config_and_bootstrap_result -v
```

Expected: FAIL (no `run` method).

- [ ] **Step 3: Implement `finalize` + `run`**

Add to service:

```python
# Step 7: FINALIZE
def finalize(self, request: BootstrapRequest) -> ProjectConfig:
    from datetime import datetime, timezone
    from .state import append_log_entry, last_completed_step

    cfg = self._feishu.list_project_configs()[request.project]
    if cfg.bootstrap_status == "PROVISIONED":
        return cfg
    if last_completed_step(cfg.bootstrap_log) < int(BootstrapStep.CREATE_FEISHU_GROUP):
        raise BootstrapStepError(
            step=BootstrapStep.FINALIZE, message="earlier steps not complete"
        )
    new_log = append_log_entry(cfg.bootstrap_log, step=BootstrapStep.FINALIZE, status="ok")
    cfg = replace(
        cfg,
        bootstrap_status="PROVISIONED",
        project_status="PROVISIONED",
        bootstrap_completed_at=datetime.now(timezone.utc).isoformat(),
        bootstrap_log=new_log,
    )
    self._feishu.upsert_project_config(request.project, cfg)
    return cfg

# Top-level: run all 7 steps (idempotent on resume)
def run(self, request: BootstrapRequest) -> BootstrapResult:
    self.validate(request)
    template_version, rendered_arch_md = render_template(
        request.category, project=request.project
    )
    self.upsert_config(request, template_version=template_version)
    self.create_repo_and_populate(
        request,
        template_version=template_version,
        rendered_architecture_md=rendered_arch_md,
    )
    self.create_architecture_doc(request, rendered_architecture_md=rendered_arch_md)
    self.create_feishu_group(request)
    final_cfg = self.finalize(request)
    return BootstrapResult(
        project=request.project,
        github_repo_url=final_cfg.github_repo_url,
        architecture_doc_id=final_cfg.architecture_doc_id,
        architecture_doc_url=final_cfg.architecture_doc_url,
        feishu_chat_id=final_cfg.feishu_chat_id,
        template_version=template_version,
    )
```

Update `__init__.py` to export:

```python
from .service import ProjectBootstrapService, ValidationError
from .types import BootstrapRequest, BootstrapResult, BootstrapStep, BootstrapStepError

__all__ = [
    "ProjectBootstrapService",
    "ValidationError",
    "BootstrapRequest",
    "BootstrapResult",
    "BootstrapStep",
    "BootstrapStepError",
]
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_project_bootstrap_service.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/project_bootstrap/ tests/test_project_bootstrap_service.py
git commit -m "feat(project-bootstrap): Step 7 finalize + top-level run orchestrator"
```

---

### Task D7: Resume logic — failure injection in the middle

**Files:**
- Test: `tests/test_project_bootstrap_resume.py`

- [ ] **Step 1: Write resume integration test**

Create `tests/test_project_bootstrap_resume.py`:

```python
from unittest.mock import MagicMock

import pytest

from requirement_workflow_v12.project_bootstrap.service import ProjectBootstrapService
from requirement_workflow_v12.project_bootstrap.types import (
    BootstrapRequest,
    BootstrapStep,
    BootstrapStepError,
)
from requirement_workflow_v12.project_repo.types import BootstrapRepoResult


def _make_svc_with_state():
    repo_tools = MagicMock()
    feishu_gw = MagicMock()
    github_gw = MagicMock()
    state: dict = {}
    feishu_gw.list_project_configs.side_effect = lambda: dict(state)

    def _upsert(project, cfg):
        state[project] = cfg
        return cfg
    feishu_gw.upsert_project_config.side_effect = _upsert
    github_gw.get_repo.return_value = None
    svc = ProjectBootstrapService(
        repo_tools=repo_tools,
        feishu_gateway=feishu_gw,
        github_gateway=github_gw,
        template_owner="Snowziio",
        template_repo="Template-repository",
        new_owner="Snowziio",
    )
    return svc, repo_tools, feishu_gw, state


def test_run_recovers_after_failure_in_architecture_doc():
    svc, repo_tools, feishu_gw, state = _make_svc_with_state()
    repo_tools.bootstrap_project_repo.return_value = BootstrapRepoResult(
        html_url="https://github.com/Snowziio/test3",
        default_branch="main",
        initial_populate_commit_sha="sha1",
    )
    # Step 5 fails first time
    feishu_gw.create_architecture_document.side_effect = [
        RuntimeError("feishu down"),
        MagicMock(document_id="doc_x", document_url="https://feishu.example/doc_x"),
    ]
    feishu_gw.write_document_text.return_value = None
    feishu_gw.create_project_group.return_value = MagicMock(chat_id="oc_group")

    req = BootstrapRequest(
        project="test3", category="saas-ai-automation",
        owner_user_id="ou_1", creator_chat_id="c1",
    )
    with pytest.raises(BootstrapStepError) as exc_info:
        svc.run(req)
    assert exc_info.value.step == BootstrapStep.CREATE_ARCHITECTURE_DOC

    # Resume
    resume_req = BootstrapRequest(
        project="test3", category="saas-ai-automation",
        owner_user_id="ou_1", creator_chat_id="c1", resume=True,
    )
    result = svc.run(resume_req)
    assert result.architecture_doc_id == "doc_x"
    # Steps 3+4 not re-called
    assert repo_tools.bootstrap_project_repo.call_count == 1
    # Final state provisioned
    assert state["test3"].bootstrap_status == "PROVISIONED"
```

- [ ] **Step 2: Run — observe behavior**

```bash
python -m pytest tests/test_project_bootstrap_resume.py -v
```

Expected: PASS (resume logic is already implemented via `last_completed_step` checks; this test verifies the composite behavior).

If FAIL: investigate whether the existing skip checks are complete. The most likely gap is `create_repo_and_populate` not guarding on resume — verify the test's output and adjust the service method if needed.

- [ ] **Step 3: Commit**

```bash
git add tests/test_project_bootstrap_resume.py
git commit -m "test(project-bootstrap): resume after failure in arch doc step"
```

---

## Phase E: Slash command parsers + REQ creation hard-switch

### Task E1: `/create project` command parser

**Files:**
- Modify: `src/requirement_workflow_v12/service_app.py`
- Create: `tests/test_service_app_slash_create_project.py`

- [ ] **Step 1: Write failing parser test**

Create `tests/test_service_app_slash_create_project.py`:

```python
from requirement_workflow_v12.service_app import parse_create_project_command


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
    assert parse_create_project_command(
        "/create project test3 --category saas-ai-automation"
    ) is None
```

- [ ] **Step 2: Run — verify fail**

```bash
python -m pytest tests/test_service_app_slash_create_project.py -v
```

Expected: FAIL (ImportError).

- [ ] **Step 3: Implement parser**

In `service_app.py`, after the imports, add a dataclass + parser function:

```python
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class CreateProjectCommand:
    project: str
    category: str
    owner_user_id: str
    resume: bool = False


_CREATE_PROJECT_RE = re.compile(
    r"^/create\s+project\s+(?P<name>\S+)"
    r"(?:\s+--category\s+(?P<category>\S+))?"
    r"(?:\s+--owner\s+(?P<owner>\S+))?"
    r"(?P<resume>\s+--resume)?\s*$"
)


def parse_create_project_command(text: str) -> CreateProjectCommand | None:
    m = _CREATE_PROJECT_RE.match(text.strip())
    if not m:
        return None
    name = m.group("name")
    category = m.group("category") or ""
    owner = m.group("owner") or ""
    if not category or not owner:
        return None
    return CreateProjectCommand(
        project=name,
        category=category,
        owner_user_id=owner,
        resume=bool(m.group("resume")),
    )
```

(Note: there's already a `re` and dataclass import in service_app.py; reuse them.)

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_service_app_slash_create_project.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/service_app.py tests/test_service_app_slash_create_project.py
git commit -m "feat(service-app): /create project command parser"
```

---

### Task E2: `/create req` command parser

**Files:**
- Modify: `src/requirement_workflow_v12/service_app.py`
- Create: `tests/test_service_app_slash_create_req.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_service_app_slash_create_req.py`:

```python
from requirement_workflow_v12.service_app import parse_create_req_command


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
```

- [ ] **Step 2: Run — verify fail**

```bash
python -m pytest tests/test_service_app_slash_create_req.py -v
```

Expected: FAIL.

- [ ] **Step 3: Implement parser**

In `service_app.py`, add:

```python
import shlex


@dataclass(frozen=True)
class CreateReqCommand:
    project: str
    name: str
    summary: str = ""
    category: str = ""


def parse_create_req_command(text: str) -> CreateReqCommand | None:
    stripped = text.strip()
    if not stripped.startswith("/create req "):
        return None
    try:
        tokens = shlex.split(stripped)
    except ValueError:
        return None
    # ['/create', 'req', '<project>', '<name...>', '--summary', '...', '--category', '...']
    if len(tokens) < 4:
        return None
    assert tokens[:2] == ["/create", "req"]
    project = tokens[2]

    # Split positional name from flags
    positional: list[str] = []
    summary = ""
    category = ""
    i = 3
    while i < len(tokens):
        tok = tokens[i]
        if tok == "--summary" and i + 1 < len(tokens):
            summary = tokens[i + 1]; i += 2; continue
        if tok == "--category" and i + 1 < len(tokens):
            category = tokens[i + 1]; i += 2; continue
        positional.append(tok); i += 1

    if not positional:
        return None
    name = " ".join(positional)
    return CreateReqCommand(project=project, name=name, summary=summary, category=category)
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_service_app_slash_create_req.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/service_app.py tests/test_service_app_slash_create_req.py
git commit -m "feat(service-app): /create req command parser"
```

---

### Task E3: Wire `/create req` into `handle_text_message` + free-text rejection

**Files:**
- Modify: `src/requirement_workflow_v12/service_app.py:250-276` (`handle_text_message`, `_handle_creation_group_message`)
- Test: `tests/test_service_app_slash_create_req.py` (append)

- [ ] **Step 1: Write failing routing test**

Append to `tests/test_service_app_slash_create_req.py`:

```python
def test_handle_text_message_routes_create_req_command(tmp_path):
    # Reuse fixture from test_first_req_initialization style
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from unittest.mock import MagicMock, patch
    from requirement_workflow_v12.service_app import CoordinatorRuntimeApp
    from requirement_workflow_v12.config import Settings
    from requirement_workflow_v12.store import JsonStateStore
    from requirement_workflow_v12.coordinator_service import CoordinatorService
    from requirement_workflow_v12.project_config import ProjectConfig
    from requirement_workflow_v12.protocols import MessageContext

    settings = MagicMock(spec=Settings)
    settings.state_store_path = str(tmp_path / "state.json")
    settings.creation_group_chat_id = "group_c"
    settings.openclaw_callback_secret = ""
    settings.openclaw_callback_ttl_seconds = 600
    settings.github_token = ""
    settings.feishu_user_id_type = "open_id"

    gateway = MagicMock()
    gateway.list_project_configs.return_value = {
        "test3": ProjectConfig(
            category="saas-ai-automation",
            template_version="saas-ai-automation.v1",
            architecture_doc_id="doc_x",
            architecture_doc_url="https://example/doc_x",
            bootstrap_status="PROVISIONED",
            project_status="PROVISIONED",
        ),
    }
    gateway.create_requirement_record.return_value = None
    gateway.create_requirement_document.return_value = None
    gateway.create_project_group.side_effect = Exception("skip")

    service = CoordinatorService(project_configs=gateway.list_project_configs())
    store = JsonStateStore(settings.state_store_path)
    with patch.object(Settings, "validate_runtime", return_value=None):
        settings.validate_runtime = lambda: None
        app = CoordinatorRuntimeApp(
            settings=settings, store=store, service=service, gateway=gateway,
        )

    ctx = MessageContext(
        message_id="m1",
        chat_id="group_c",
        chat_type="group",
        user_id="ou_creator",
        user_name="Alice",
        text="/create req test3 会话鉴权",
    )
    messages = app.handle_text_message(ctx)
    # Should produce at least one OutboundCard/OutboundMessage; requirement now exists
    assert len(messages) >= 1
    reqs = list(service.requirements.values())
    assert any(r.project == "test3" and r.name == "会话鉴权" for r in reqs)


def test_handle_text_message_rejects_free_text_creation_in_group(tmp_path):
    # Free text with "创建需求" keyword must now return a rejection prompt (not open the form card)
    # Behavior: returns a single OutboundMessage telling user to use /create req
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from unittest.mock import MagicMock, patch
    from requirement_workflow_v12.service_app import CoordinatorRuntimeApp
    from requirement_workflow_v12.config import Settings
    from requirement_workflow_v12.store import JsonStateStore
    from requirement_workflow_v12.coordinator_service import CoordinatorService
    from requirement_workflow_v12.protocols import MessageContext

    settings = MagicMock(spec=Settings)
    settings.state_store_path = str(tmp_path / "state.json")
    settings.creation_group_chat_id = "group_c"
    settings.openclaw_callback_secret = ""
    settings.openclaw_callback_ttl_seconds = 600
    settings.github_token = ""

    service = CoordinatorService()
    store = JsonStateStore(settings.state_store_path)
    gateway = MagicMock()
    gateway.list_project_configs.return_value = {}
    with patch.object(Settings, "validate_runtime", return_value=None):
        settings.validate_runtime = lambda: None
        app = CoordinatorRuntimeApp(
            settings=settings, store=store, service=service, gateway=gateway,
        )

    ctx = MessageContext(
        message_id="m1", chat_id="group_c", chat_type="group",
        user_id="u1", user_name="Alice", text="创建需求",
    )
    messages = app.handle_text_message(ctx)
    assert len(messages) == 1
    text = getattr(messages[0], "text", "")
    assert "/create req" in text
```

- [ ] **Step 2: Run — verify fail**

```bash
python -m pytest tests/test_service_app_slash_create_req.py -v
```

Expected: FAIL.

- [ ] **Step 3: Replace `_handle_creation_group_message` + add handler**

In `service_app.py:271-276`, replace the whole `_handle_creation_group_message` method with:

```python
def _handle_creation_group_message(self, context: MessageContext) -> list[OutboundMessage | OutboundCard]:
    # Free-text "创建需求" entry is deprecated — hard switch to /create req
    text = context.text.strip()
    cmd = parse_create_req_command(text)
    if cmd is not None:
        return self._handle_create_req_command(cmd, context)
    if "创建需求" in context.text or "新建需求" in context.text:
        return [OutboundMessage(
            receive_id=context.chat_id,
            text=(
                "REQ 创建已改用固化命令：\n"
                "`/create req <project> <name>` （可选 --summary / --category）\n"
                "示例：`/create req test3 会话鉴权改造 --summary \"支持JWT\"`"
            ),
        )]
    return []
```

Add `_handle_create_req_command`:

```python
def _handle_create_req_command(
    self, cmd: "CreateReqCommand", context: MessageContext,
) -> list[OutboundMessage | OutboundCard]:
    existing = self.service.project_configs.get(cmd.project)
    if existing is None:
        return [OutboundMessage(
            receive_id=context.chat_id,
            text=f"项目 {cmd.project} 不存在。请先 `/create project <name> --category <c> --owner <uid>`。",
        )]
    if existing.bootstrap_status != "PROVISIONED":
        return [OutboundMessage(
            receive_id=context.chat_id,
            text=f"项目 {cmd.project} 当前状态 {existing.bootstrap_status}，未完成 Bootstrap，无法创建 REQ。",
        )]
    if cmd.category and cmd.category != existing.category:
        return [OutboundMessage(
            receive_id=context.chat_id,
            text=(
                f"category 不一致：命令中 {cmd.category!r} 与项目 {cmd.project} 实际 "
                f"{existing.category!r} 冲突，拒绝创建"
            ),
        )]
    from .protocols import CreationFormPayload
    payload = CreationFormPayload(
        project=cmd.project,
        name=cmd.name,
        summary=cmd.summary or cmd.name,
        creator=context.user_name or context.user_id,
        creator_user_id=context.user_id,
        creation_chat_id=context.chat_id,
        needs_ui=False,
        category=existing.category,
    )
    request, _, req_id = self._create_requirement_from_form(payload)
    self._provision_requirement_after_creation(request, req_id)
    return [OutboundMessage(
        receive_id=context.chat_id,
        text=f"{req_id} 已创建（project={cmd.project}, name={cmd.name}）。",
    )]
```

Also update `handle_text_message` to detect `/create req` at group scope (it's already flowing through `_handle_creation_group_message`, but ensure `_is_creation_group_message` returns True; check current logic).

Look at `_is_creation_group_message` (grep to find it). Make sure `/create req ...` enters `_handle_creation_group_message`. If `_is_creation_group_message` only triggers on creation group chat_id, that's fine — the routing already picks it up.

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_service_app_slash_create_req.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/service_app.py tests/test_service_app_slash_create_req.py
git commit -m "feat(service-app): wire /create req + reject legacy 创建需求 free-text"
```

---

### Task E4: Delete `_initialize_project_for_first_req` + update `_provision_requirement_after_creation`

**Files:**
- Modify: `src/requirement_workflow_v12/service_app.py:319-360`
- Delete: `tests/test_first_req_initialization.py`
- Modify: `tests/test_coordinator_plan.py` / `tests/test_service_app_spec_transform.py` if they depend on legacy init path

- [ ] **Step 1: Search for callers of `_initialize_project_for_first_req`**

```bash
cd /Users/daxin/work/requirement-workflow-feishu
grep -rn "_initialize_project_for_first_req" src/ tests/
```

- [ ] **Step 2: Remove the method and its call site**

In `service_app.py:319-345`, **delete** the entire `_initialize_project_for_first_req` method (25 lines).

In `_provision_requirement_after_creation` (around line 347-360), **replace** the block that calls `_initialize_project_for_first_req`:

```python
def _provision_requirement_after_creation(self, request: CreationRequest, req_id: str) -> None:
    form_payload = self._pending_form_payloads.pop(req_id, None)
    if form_payload is not None:
        existing = self.service.project_configs.get(form_payload.project)
        if existing is None:
            LOGGER.warning(
                "REQ %s created but project %s missing from project_configs — this "
                "shouldn't happen after Bootstrap; skipping project-init",
                req_id, form_payload.project,
            )
        elif form_payload.category and form_payload.category != existing.category:
            LOGGER.warning(
                "Form supplied mismatched category for existing project %s: got %s, have %s",
                form_payload.project, form_payload.category, existing.category,
            )
    # ... keep the rest of the method (project group + bitable + document creation)
```

- [ ] **Step 3: Delete legacy test file**

```bash
git rm tests/test_first_req_initialization.py
```

- [ ] **Step 4: Run full test suite to find broken references**

```bash
python -m pytest tests/ -x 2>&1 | head -80
```

If other tests reference `_initialize_project_for_first_req` or rely on the lazy initialization behavior, they need updating. For each:
- Pre-seed `service.project_configs` with a PROVISIONED `ProjectConfig` in the test fixture
- Remove assertions on `gateway.create_architecture_document.assert_called_once_with(...)`

Example fix pattern if you find a broken test: replace:
```python
assert cfg.template_version == "saas-ai-automation.v1"
```
with a test fixture that pre-populates the config.

- [ ] **Step 5: Run tests again**

```bash
python -m pytest tests/ -v 2>&1 | tail -40
```

Expected: green.

- [ ] **Step 6: Commit**

```bash
git add -u src/requirement_workflow_v12/service_app.py tests/
git commit -m "refactor(service-app): remove _initialize_project_for_first_req lazy init (superseded by Bootstrap)"
```

---

### Task E5: `/create project` routing + Bootstrap wire-up in service_app

**Files:**
- Modify: `src/requirement_workflow_v12/service_app.py`
- Test: `tests/test_service_app_slash_create_project.py` (append)

- [ ] **Step 1: Write failing routing test**

Append to `tests/test_service_app_slash_create_project.py`:

```python
def test_handle_text_message_routes_create_project_triggers_bootstrap(tmp_path, monkeypatch):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from unittest.mock import MagicMock, patch
    from requirement_workflow_v12.service_app import CoordinatorRuntimeApp
    from requirement_workflow_v12.config import Settings
    from requirement_workflow_v12.store import JsonStateStore
    from requirement_workflow_v12.coordinator_service import CoordinatorService
    from requirement_workflow_v12.protocols import MessageContext
    from requirement_workflow_v12.project_bootstrap.types import BootstrapResult

    settings = MagicMock(spec=Settings)
    settings.state_store_path = str(tmp_path / "state.json")
    settings.creation_group_chat_id = "group_c"
    settings.openclaw_callback_secret = ""
    settings.openclaw_callback_ttl_seconds = 600
    settings.github_token = "tok"
    settings.github_template_owner = "Snowziio"
    settings.github_template_repo = "Template-repository"
    settings.github_org_owner = "Snowziio"

    bootstrap_svc = MagicMock()
    bootstrap_svc.run.return_value = BootstrapResult(
        project="test3",
        github_repo_url="https://github.com/Snowziio/test3",
        architecture_doc_id="doc_x",
        architecture_doc_url="https://feishu.example/doc_x",
        feishu_chat_id="oc_test3",
        template_version="saas-ai-automation.v1",
    )

    service = CoordinatorService()
    store = JsonStateStore(settings.state_store_path)
    gateway = MagicMock()
    gateway.list_project_configs.return_value = {}
    with patch.object(Settings, "validate_runtime", return_value=None):
        settings.validate_runtime = lambda: None
        app = CoordinatorRuntimeApp(
            settings=settings, store=store, service=service, gateway=gateway,
            project_bootstrap_service=bootstrap_svc,
        )

    ctx = MessageContext(
        message_id="m1", chat_id="group_c", chat_type="group",
        user_id="ou_alice", user_name="Alice",
        text="/create project test3 --category saas-ai-automation --owner ou_alice",
    )
    messages = app.handle_text_message(ctx)
    bootstrap_svc.run.assert_called_once()
    call_kwargs = bootstrap_svc.run.call_args.args[0]
    assert call_kwargs.project == "test3"
    assert call_kwargs.category == "saas-ai-automation"
    assert call_kwargs.owner_user_id == "ou_alice"
    # Should reply with success message
    assert any("test3" in getattr(m, "text", "") for m in messages)
```

- [ ] **Step 2: Run — verify fail**

```bash
python -m pytest tests/test_service_app_slash_create_project.py::test_handle_text_message_routes_create_project_triggers_bootstrap -v
```

Expected: FAIL (no `project_bootstrap_service` arg / no handler).

- [ ] **Step 3: Add settings fields + wire into `CoordinatorRuntimeApp`**

In `config.py`, add to `Settings`:

```python
github_template_owner: str = os.environ.get("GITHUB_TEMPLATE_OWNER", "Snowziio")
github_template_repo: str = os.environ.get("GITHUB_TEMPLATE_REPO", "Template-repository")
github_org_owner: str = os.environ.get("GITHUB_ORG_OWNER", "Snowziio")
```

In `service_app.py`, add to `CoordinatorRuntimeApp.__init__`:

```python
def __init__(
    self,
    *,
    settings: Settings,
    store: JsonStateStore,
    service: CoordinatorService,
    gateway,
    project_bootstrap_service=None,
    **kwargs,
):
    ...  # existing init
    self._project_bootstrap_service = project_bootstrap_service
```

Add handler to `handle_text_message` routing (between `handle_slash_command` and `_handle_creation_group_message`):

```python
cmd_project = parse_create_project_command(text)
if cmd_project is not None:
    return self._handle_create_project_command(cmd_project, context)
```

Add `_handle_create_project_command`:

```python
def _handle_create_project_command(
    self, cmd: "CreateProjectCommand", context: MessageContext,
) -> list[OutboundMessage | OutboundCard]:
    if self._project_bootstrap_service is None:
        return [OutboundMessage(
            receive_id=context.chat_id,
            text="Bootstrap 服务未启用；请联系运维检查 settings.github_token 配置",
        )]
    from .project_bootstrap.types import BootstrapRequest
    from .project_bootstrap.service import ValidationError
    from .project_bootstrap.types import BootstrapStepError
    req = BootstrapRequest(
        project=cmd.project,
        category=cmd.category,
        owner_user_id=cmd.owner_user_id,
        creator_chat_id=context.chat_id,
        resume=cmd.resume,
    )
    try:
        result = self._project_bootstrap_service.run(req)
    except ValidationError as exc:
        return [OutboundMessage(
            receive_id=context.chat_id,
            text=f"Bootstrap 校验失败：{exc}",
        )]
    except BootstrapStepError as exc:
        return [OutboundMessage(
            receive_id=context.chat_id,
            text=(
                f"Bootstrap 中断于 Step {int(exc.step)} ({exc.step.name})：{exc.message}\n"
                f"可使用 `/create project {cmd.project} --category {cmd.category} "
                f"--owner {cmd.owner_user_id} --resume` 续跑"
            ),
        )]
    self._save_state()
    return [OutboundMessage(
        receive_id=context.chat_id,
        text=(
            f"项目 {result.project} 已就绪：\n"
            f"- Repo: {result.github_repo_url}\n"
            f"- ARCHITECTURE: {result.architecture_doc_url}\n"
            f"- 群 chat_id: {result.feishu_chat_id}\n"
            f"可开始用 `/create req {result.project} <name>` 创建需求。"
        ),
    )]
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_service_app_slash_create_project.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/ tests/test_service_app_slash_create_project.py
git commit -m "feat(service-app): /create project routes into ProjectBootstrapService"
```

---

## Phase F: `project_context_change` unified gate

### Task F1: `project_context_apply` dispatcher with artifact executors

**Files:**
- Create: `src/requirement_workflow_v12/project_context_apply.py`
- Test: `tests/test_project_context_apply.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_project_context_apply.py`:

```python
import pytest

from requirement_workflow_v12.project_context_apply import (
    ProjectContextApplyError,
    apply_project_context_change,
)


def test_dispatch_architecture_executor_returns_updated_files():
    original = {"ARCHITECTURE.md": "## Storage\n\nTBD\n"}
    change = {
        "summary": "Add Redis storage",
        "changes": [
            {
                "artifact": "architecture",
                "section_path": "## Storage",
                "before": "## Storage\n\nTBD\n",
                "after": "## Storage\n\nRedis 24h TTL\n",
                "rationale": "D1",
            },
        ],
    }
    updated = apply_project_context_change(original_files=original, change=change)
    assert "Redis 24h TTL" in updated["ARCHITECTURE.md"]


def test_environments_and_skill_md_executors_are_noop_stubs_that_log(caplog):
    original = {
        "project/environments.yaml": "environments:\n  dev: {}\n",
        "SKILL.md": "# x\n",
    }
    change = {
        "summary": "Add staging env + update SKILL",
        "changes": [
            {"artifact": "environments", "section_path": "staging", "before": "", "after": "...", "rationale": "D2"},
            {"artifact": "skill_md", "section_path": "## Testing", "before": "", "after": "...", "rationale": "D3"},
        ],
    }
    with caplog.at_level("WARNING"):
        updated = apply_project_context_change(original_files=original, change=change)
    # Stubs do not modify
    assert updated["project/environments.yaml"] == "environments:\n  dev: {}\n"
    assert updated["SKILL.md"] == "# x\n"
    warnings = " ".join(r.message for r in caplog.records)
    assert "environments" in warnings
    assert "skill_md" in warnings


def test_dispatch_rejects_unknown_artifact():
    with pytest.raises(ProjectContextApplyError, match="unknown artifact"):
        apply_project_context_change(
            original_files={},
            change={"summary": "x", "changes": [{"artifact": "mystery", "section_path": "", "before": "", "after": "", "rationale": "D"}]},
        )
```

- [ ] **Step 2: Run — verify fail**

```bash
python -m pytest tests/test_project_context_apply.py -v
```

Expected: FAIL.

- [ ] **Step 3: Implement `project_context_apply.py`**

Create `src/requirement_workflow_v12/project_context_apply.py`:

```python
"""Unified dispatcher for project_context_change gate.

Each ``changes[].artifact`` routes to a dedicated executor. MVP
implements the ``architecture`` executor fully; ``environments`` and
``skill_md`` are logged stubs that preserve the original content.
"""
from __future__ import annotations

import logging

from .project_repo.architecture_apply import (
    ArchitectureApplyError,
    apply_architecture_changes,
)


_logger = logging.getLogger(__name__)


class ProjectContextApplyError(ValueError):
    """Raised when a change block is malformed or unroutable."""


def apply_project_context_change(
    *, original_files: dict[str, str], change: dict
) -> dict[str, str]:
    """Return a new dict of {path: content} with all artifact executors applied.

    ``change`` is the payload from plan_submit.project_context_change —
    includes ``changes[]`` and ``summary``. Unknown artifact values
    raise ``ProjectContextApplyError``.
    """
    changes = change.get("changes") or []
    updated = dict(original_files)
    arch_changes = []
    for entry in changes:
        artifact = entry.get("artifact")
        if artifact == "architecture":
            arch_changes.append(entry)
        elif artifact == "environments":
            _logger.warning(
                "project_context_change: environments executor is a stub (MVP); ignoring change section_path=%s",
                entry.get("section_path"),
            )
        elif artifact == "skill_md":
            _logger.warning(
                "project_context_change: skill_md executor is a stub (MVP); ignoring change section_path=%s",
                entry.get("section_path"),
            )
        else:
            raise ProjectContextApplyError(f"unknown artifact: {artifact!r}")

    if arch_changes:
        arch_path = "ARCHITECTURE.md"
        arch_text = updated.get(arch_path, "")
        try:
            updated[arch_path] = apply_architecture_changes(arch_text, arch_changes)
        except ArchitectureApplyError as exc:
            raise ProjectContextApplyError(
                f"architecture apply failed: {exc}"
            ) from exc
    return updated
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_project_context_apply.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/project_context_apply.py tests/test_project_context_apply.py
git commit -m "feat(project-context): unified project_context_change dispatcher with artifact stubs"
```

---

### Task F2: Migrate plan callback + `commit_plan_artifacts` to `project_context_change`

**Files:**
- Modify: `src/requirement_workflow_v12/service_app.py:975-1002` (`handle_openclaw_plan_callback`)
- Modify: `src/requirement_workflow_v12/project_repo/tools.py:117-165` (`commit_plan_artifacts`)
- Modify: `src/requirement_workflow_v12/project_repo/types.py` (`PlanArtifacts`)
- Modify: `docs/agents/plan-author/callback-schema.json`
- Modify: `docs/agents/plan-author/SKILL.md`
- Test: `tests/test_commit_plan_artifacts.py`
- Test: `tests/test_plan_endpoint_service_app.py`

- [ ] **Step 1: Read current `PlanArtifacts`**

Already seen — `architecture_change: dict | None` in `types.py:82`.

- [ ] **Step 2: Update failing test**

In `tests/test_commit_plan_artifacts.py`, add:

```python
def test_commit_plan_artifacts_accepts_project_context_change_envelope():
    from unittest.mock import MagicMock
    from requirement_workflow_v12.project_repo.tools import GitHubProjectRepoTools
    from requirement_workflow_v12.project_repo.types import PlanArtifacts

    gw = MagicMock()
    gw.fetch_file_sha.return_value = ("sha_old", "## Storage\n\nTBD\n")
    gw.commit_files.return_value = "commit_new"
    tools = GitHubProjectRepoTools(gw)

    artifacts = PlanArtifacts(
        project_repo="Snowziio/test3",
        req_id="REQ-2026-04-20-001",
        plan_md_content="# plan",
        project_context_change={
            "summary": "Add Redis",
            "changes": [{
                "artifact": "architecture",
                "section_path": "## Storage",
                "before": "## Storage\n\nTBD\n",
                "after": "## Storage\n\nRedis 24h TTL\n",
                "rationale": "D1",
            }],
        },
        commit_message="plan(REQ-1): land plan.md and apply arch",
    )
    result = tools.commit_plan_artifacts(artifacts)
    assert result.architecture_updated is True
    # commit_files called with 2 file changes
    file_changes = gw.commit_files.call_args.kwargs["files"]
    paths = [fc.path for fc in file_changes]
    assert "ARCHITECTURE.md" in paths
    assert "docs/specs/REQ-2026-04-20-001/plan.md" in paths
```

Keep existing tests passing: `PlanArtifacts(..., architecture_change=None, ...)` should still work — we'll add backward aliasing in implementation.

- [ ] **Step 3: Run — verify fail**

```bash
python -m pytest tests/test_commit_plan_artifacts.py::test_commit_plan_artifacts_accepts_project_context_change_envelope -v
```

Expected: FAIL (TypeError — unexpected kwarg).

- [ ] **Step 4: Update `PlanArtifacts` — add `project_context_change` field, drop `architecture_change`**

In `src/requirement_workflow_v12/project_repo/types.py:72-83`, replace:

```python
@dataclass(frozen=True)
class PlanArtifacts:
    """plan.md content + optional project_context_change envelope.

    ``project_context_change`` carries the unified payload with
    ``summary`` / ``changes[]`` (each with artifact/section_path/
    before/after/rationale). ``None`` means the plan doesn't touch
    project-level context.
    """
    project_repo: str
    req_id: str
    plan_md_content: str
    project_context_change: dict | None
    commit_message: str
```

- [ ] **Step 5: Rewrite `commit_plan_artifacts`**

Replace `commit_plan_artifacts` in `tools.py:117-165` with:

```python
def commit_plan_artifacts(
    self, artifacts: PlanArtifacts,
) -> PlanCommitResult:
    from ..project_context_apply import (
        ProjectContextApplyError,
        apply_project_context_change,
    )
    owner, name = artifacts.project_repo.split("/", 1)
    plan_path = f"docs/specs/{artifacts.req_id}/plan.md"
    files_to_commit = [FileChange(path=plan_path, content=artifacts.plan_md_content)]
    architecture_updated = False

    if artifacts.project_context_change is not None:
        try:
            _arch_sha, arch_text = self._gw.fetch_file_sha(
                artifacts.project_repo, "main", "ARCHITECTURE.md",
            )
        except GitHubGatewayError as exc:
            raise ProjectRepoError(
                f"commit_plan_artifacts: cannot fetch ARCHITECTURE.md: {exc}",
                recoverable=False,
            ) from exc
        try:
            updated_files = apply_project_context_change(
                original_files={"ARCHITECTURE.md": arch_text},
                change=artifacts.project_context_change,
            )
        except ProjectContextApplyError as exc:
            raise ProjectRepoError(
                f"commit_plan_artifacts: project_context_change apply failed: {exc}",
                recoverable=False,
            ) from exc
        new_arch = updated_files.get("ARCHITECTURE.md")
        if new_arch is not None and new_arch != arch_text:
            files_to_commit.append(FileChange(path="ARCHITECTURE.md", content=new_arch))
            architecture_updated = True

    try:
        sha = self._gw.commit_files(
            owner=owner, repo=name, branch="main",
            files=files_to_commit, message=artifacts.commit_message,
        )
    except GitHubGatewayError as exc:
        raise ProjectRepoError(
            f"commit_plan_artifacts: commit to main failed: {exc}",
            recoverable=False,
        ) from exc
    return PlanCommitResult(
        commit_sha=sha, branch="main",
        plan_md_path=plan_path,
        architecture_updated=architecture_updated,
    )
```

- [ ] **Step 6: Fix callers**

```bash
grep -rn "architecture_change" src/ tests/
```

For each hit, rename to `project_context_change`. Expect hits in:
- `service_app.py:995` (plan callback)
- `coordinator_service.py` (possibly in plan_submit)
- Any test that builds a `PlanArtifacts` directly

In `service_app.py:991-996` (handle_openclaw_plan_callback), replace:

```python
if event == "plan_submit":
    self.service.plan_submit(
        req_id,
        plan_md_content=payload.get("plan_md_content", ""),
        project_context_change=payload.get("project_context_change") or payload.get("architecture_change"),
    )
```

(The `or payload.get("architecture_change")` is a **read-side shim** only for any in-flight plan-author calls; plan-author itself will be updated in Task F3.)

In `coordinator_service.py`, find `plan_submit` method signature — replace the keyword arg name:

```bash
grep -n "architecture_change" src/requirement_workflow_v12/coordinator_service.py
```

Rename both parameter and internal field propagation. The `plan_md` flow in state_machine must also stop referencing `architecture_change`.

- [ ] **Step 7: Run all tests**

```bash
python -m pytest tests/ -x 2>&1 | tail -60
```

Fix any remaining `architecture_change` references in tests by renaming the kwarg. All tests should pass.

- [ ] **Step 8: Update plan-author callback schema**

In `docs/agents/plan-author/callback-schema.json`, change:

```json
"architecture_change": { ... }
```

to:

```json
"project_context_change": {
  "oneOf": [
    {"type": "null"},
    {
      "type": "object",
      "required": ["summary", "changes"],
      "properties": {
        "summary": {"type": "string"},
        "changes": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["artifact", "section_path", "before", "after", "rationale"],
            "properties": {
              "artifact": {"enum": ["architecture", "environments", "skill_md"]},
              "section_path": {"type": "string"},
              "before": {"type": "string"},
              "after": {"type": "string"},
              "rationale": {"type": "string"}
            }
          }
        },
        "authorized": {"type": "boolean"}
      }
    }
  ]
}
```

- [ ] **Step 9: Update plan-author SKILL.md**

In `docs/agents/plan-author/SKILL.md`, find the `architecture_change` JSON example (around line 141-152) and change to `project_context_change` matching the new schema.

- [ ] **Step 10: Commit**

```bash
git add -u src/ tests/ docs/agents/plan-author/
git commit -m "feat(plan): generalize architecture_change to project_context_change unified envelope"
```

---

## Phase G: req-registry auto-append

### Task G1: Append REQ row to `project/req-registry.yaml` on creation

**Files:**
- Create: `src/requirement_workflow_v12/req_registry.py`
- Modify: `src/requirement_workflow_v12/service_app.py` (in `_provision_requirement_after_creation`)
- Test: `tests/test_req_registry_append.py`

- [ ] **Step 1: Write failing test for registry append function**

Create `tests/test_req_registry_append.py`:

```python
import pytest

from requirement_workflow_v12.req_registry import (
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
```

- [ ] **Step 2: Run — verify fail**

```bash
python -m pytest tests/test_req_registry_append.py -v
```

Expected: FAIL.

- [ ] **Step 3: Implement `req_registry.py`**

Create `src/requirement_workflow_v12/req_registry.py`:

```python
"""Project-level req-registry.yaml append helper.

Non-gate, best-effort: when the registry can't be updated, log a
warning and continue — REQ creation must not be blocked by a repo
failure.
"""
from __future__ import annotations

import logging

import yaml

from .github_gateway import FileChange, GitHubGatewayError


_logger = logging.getLogger(__name__)


class RegistryAppendError(RuntimeError):
    """Raised when the registry cannot be parsed or updated (hard path)."""


def render_registry_with_new_req(
    *,
    original_text: str,
    req_id: str,
    title: str,
    status: str,
    created_at: str,
) -> str:
    try:
        data = yaml.safe_load(original_text) or {}
    except yaml.YAMLError as exc:
        raise RegistryAppendError(f"registry yaml unparseable: {exc}") from exc
    if not isinstance(data, dict):
        raise RegistryAppendError("registry root must be a dict")
    reqs = data.get("requirements") or []
    reqs.append({
        "req_id": req_id,
        "title": title,
        "status": status,
        "plan_id": None,
        "spec_pr": None,
        "created_at": created_at,
    })
    data["requirements"] = reqs
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)


def append_req_to_registry(
    *,
    github_gateway,
    project_repo: str,
    req_id: str,
    title: str,
    status: str,
    created_at: str,
    swallow_errors: bool = True,
) -> None:
    owner, name = project_repo.split("/", 1)
    try:
        _sha, original = github_gateway.fetch_file_sha(
            project_repo, "main", "project/req-registry.yaml"
        )
        new_text = render_registry_with_new_req(
            original_text=original,
            req_id=req_id,
            title=title,
            status=status,
            created_at=created_at,
        )
        github_gateway.commit_files(
            owner=owner, repo=name, branch="main",
            files=[FileChange(path="project/req-registry.yaml", content=new_text)],
            message=f"req-registry: append {req_id}",
        )
    except (GitHubGatewayError, RegistryAppendError) as exc:
        if swallow_errors:
            _logger.warning(
                "req-registry append failed for %s (non-blocking): %s", req_id, exc
            )
            return
        raise
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_req_registry_append.py -v
```

Expected: PASS.

- [ ] **Step 5: Wire into `_provision_requirement_after_creation`**

In `service_app.py`, at the end of `_provision_requirement_after_creation` (just before the final LOGGER.info), add:

```python
existing = self.service.project_configs.get(request.project)
if existing and existing.github_repo_url and self._github_gateway is not None:
    from .req_registry import append_req_to_registry
    from datetime import datetime, timezone
    owner_name = existing.github_repo_url.rsplit("/", 2)[-2:]
    project_repo = "/".join(owner_name)
    append_req_to_registry(
        github_gateway=self._github_gateway,
        project_repo=project_repo,
        req_id=req_id,
        title=requirement.name if requirement else req_id,
        status="DRAFTING",
        created_at=datetime.now(timezone.utc).isoformat(),
        swallow_errors=True,
    )
```

(Ensure `_github_gateway` is stored in `__init__` — it likely is already under a different name; grep for `self.github_gateway` or similar.)

- [ ] **Step 6: Run full tests**

```bash
python -m pytest tests/ -x 2>&1 | tail -20
```

Expected: green.

- [ ] **Step 7: Commit**

```bash
git add src/requirement_workflow_v12/req_registry.py src/requirement_workflow_v12/service_app.py tests/test_req_registry_append.py
git commit -m "feat(req-registry): auto-append row to project/req-registry.yaml on REQ creation"
```

---

## Phase H: Documentation

### Task H1: Methodology v2.0 → v2.5 insert §5.0 Project layer

**Files:**
- Modify: `docs/superpowers/methodology.md` (OR `docs/context/harness-engineering-methodology-v2.0.md` — grep to confirm path)

- [ ] **Step 1: Locate the methodology file**

```bash
find /Users/daxin/work/requirement-workflow-feishu/docs -name "*methodology*" -type f
```

- [ ] **Step 2: Read current §5 section numbering**

```bash
grep -n "^## §5\|^### §5" docs/context/harness-engineering-methodology-v2.0.md | head -10
```

- [ ] **Step 3: Insert §5.0 Project layer section**

Open the methodology file. Before the current `§5.1 Requirement 层` heading, insert:

```markdown
## §5.0 Project 层（Bootstrap）

### 5.0.1 定位

Project 层是 harness 方法论的**项目生命周期层**，位于 Requirement / Planning / Spec 之前。

所有 REQ 必须挂靠在一个状态为 `PROVISIONED` 的 Project 上；项目创建通过 `/create project` 固化命令触发 Bootstrap 流程。

### 5.0.2 状态机

`UNBOOTSTRAPPED → BOOTSTRAPPING → PROVISIONED → ARCHIVED → DECOMMISSIONED`

MVP 只实现前三态；archive / decommission Phase 2。

### 5.0.3 Bootstrap 7 步

1. VALIDATE 校验输入 2. UPSERT_CONFIG 写 project_configs 3. CREATE_REPO 从 Template 仓库生成 4. POPULATE_MAIN 写入 per-project 文件 5. CREATE_ARCHITECTURE_DOC 建 Feishu doc 6. CREATE_FEISHU_GROUP 建群 7. FINALIZE 标记 PROVISIONED

每步幂等，`--resume` 可从任意断点续跑。

### 5.0.4 项目级上下文演化

Project 级 artifact（ARCHITECTURE / environments / skill_md）的后续变更由 REQ 驱动：plan-author 在 Planning 阶段通过统一的 `project_context_change` 信封提交变更，走授权闸门后落盘。

详见 `docs/superpowers/specs/2026-04-20-project-layer-design.md`.
```

Also bump the version marker at the top of the file from `v2.0` to `v2.5` and append a changelog entry referencing 2026-04-20.

- [ ] **Step 4: Commit**

```bash
git add docs/context/harness-engineering-methodology-v2.0.md
git commit -m "docs(methodology): insert §5.0 Project layer (bump to v2.5)"
```

---

### Task H2: Update planning-harness-layer + plan-author SKILL cross-references

**Files:**
- Modify: `docs/superpowers/planning-harness-layer.md` (OR `docs/context/layers/planning-harness-layer.md` — check path)
- Modify: `docs/agents/plan-author/SKILL.md`
- Create: `docs/agents/project-bootstrap/SKILL.md`

- [ ] **Step 1: Find planning-harness-layer.md**

```bash
find /Users/daxin/work/requirement-workflow-feishu/docs -name "planning-harness-layer*"
```

- [ ] **Step 2: Add prerequisite note to planning-harness-layer.md**

At the top of the document, after the H1 heading, insert:

```markdown
> **前置依赖**：本层依赖 **§5.0 Project 层 Bootstrap** 已完成。REQ 只能挂靠在
> `project_configs.bootstrap_status == PROVISIONED` 的项目上；非 PROVISIONED
> 状态下 coordinator 会直接拒绝 `/create req` 命令。
>
> **schema 变更**：`architecture_change` 已在 2026-04-20 泛化为
> `project_context_change`（统一 gate，支持多个 artifact）。见
> `docs/superpowers/specs/2026-04-20-project-layer-design.md`.
```

- [ ] **Step 3: Add addendum to planning-phase design spec**

At the end of `docs/superpowers/specs/2026-04-19-planning-phase-design.md`, append:

```markdown
---

## Addendum: 2026-04-20 schema 升级

`architecture_change` payload 字段已重命名为 `project_context_change`，信封内
`changes[]` 新增 `artifact` 字段（值域 `architecture` / `environments` / `skill_md`）。
MVP 只实现 `architecture` 执行器；其他 artifact 是 stub。

向后兼容：无存量数据（test2 硬废弃），无兼容负担。新 plan-author 产物直接用
`project_context_change`。

详见：`docs/superpowers/specs/2026-04-20-project-layer-design.md`
```

- [ ] **Step 4: Create project-bootstrap SKILL.md placeholder**

Create `docs/agents/project-bootstrap/SKILL.md`:

```markdown
---
name: project-bootstrap
description: 项目引导助手（MVP 由 coordinator CLI 驱动；后续可 agent 化）。将 /create project 固化命令接到 7 步 Bootstrap 流程。
---

# Project Bootstrap 助手

## MVP 实现

MVP 阶段 Project Bootstrap **由 coordinator 直接执行**（`ProjectBootstrapService.run`），
不通过 AI agent。本文件作为后续 agent 化的占位：当 Bootstrap 需要决策（如
environments/CI 选型）时，再扩展为 agent 驱动。

## 当前流程

1. 用户在创建群发 `/create project <name> --category <c> --owner <uid>`
2. coordinator 解析 → `BootstrapRequest` → `ProjectBootstrapService.run`
3. 7 步流程见 `src/requirement_workflow_v12/project_bootstrap/service.py`
4. 失败时用户发 `--resume` 续跑

## 后续扩展方向（Phase 2）

- environments.yaml 的 category 默认骨架细化（按技术栈差异化）
- SECRETS 清单自动补全（按 CI 需要的具体 key）
- CI workflow 的 category-aware 渲染（不同 category 不同 lint/test/deploy）
```

- [ ] **Step 5: Commit**

```bash
git add docs/
git commit -m "docs(planning+bootstrap): cross-reference §5.0 Project layer from planning layer; add project-bootstrap SKILL placeholder"
```

---

## Phase I: End-to-end integration

### Task I1: Integration test: `/create project` → PROVISIONED → `/create req` → req-registry updated

**Files:**
- Create: `tests/test_project_layer_e2e.py`

- [ ] **Step 1: Write e2e test**

Create `tests/test_project_layer_e2e.py`:

```python
"""End-to-end integration: Bootstrap → REQ creation → registry append.

Uses MagicMock gateway boundaries; verifies the full happy-path
without hitting real GitHub/Feishu. Real-world smoke is a manual
step (see `docs/superpowers/plans/2026-04-20-project-layer-plan.md`
Phase J — smoke task).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from unittest.mock import MagicMock, patch


def test_e2e_bootstrap_then_create_req_appends_registry(tmp_path):
    from requirement_workflow_v12.service_app import CoordinatorRuntimeApp
    from requirement_workflow_v12.config import Settings
    from requirement_workflow_v12.store import JsonStateStore
    from requirement_workflow_v12.coordinator_service import CoordinatorService
    from requirement_workflow_v12.protocols import MessageContext
    from requirement_workflow_v12.project_bootstrap.service import ProjectBootstrapService
    from requirement_workflow_v12.project_bootstrap.types import BootstrapResult

    settings = MagicMock(spec=Settings)
    settings.state_store_path = str(tmp_path / "state.json")
    settings.creation_group_chat_id = "group_c"
    settings.openclaw_callback_secret = ""
    settings.openclaw_callback_ttl_seconds = 600
    settings.github_token = "tok"
    settings.github_template_owner = "Snowziio"
    settings.github_template_repo = "Template-repository"
    settings.github_org_owner = "Snowziio"
    settings.feishu_user_id_type = "open_id"

    # Gateway composite: Feishu + project_configs state + github primitives
    state = {}
    gateway = MagicMock()
    gateway.list_project_configs.side_effect = lambda: dict(state)
    gateway.upsert_project_config.side_effect = lambda p, cfg: state.__setitem__(p, cfg) or cfg
    gateway.create_architecture_document.return_value = MagicMock(
        document_id="doc_test3", document_url="https://feishu.example/doc_test3"
    )
    gateway.write_document_text.return_value = None
    gateway.create_project_group.return_value = MagicMock(chat_id="oc_test3_group")
    gateway.create_requirement_record.return_value = None
    gateway.create_requirement_document.return_value = None
    gateway.fetch_file_sha.return_value = ("sha_old", "project: test3\nrequirements: []\n")
    gateway.commit_files.return_value = "sha_new"

    # Bootstrap service: fake repo_tools layer
    repo_tools = MagicMock()
    from requirement_workflow_v12.project_repo.types import BootstrapRepoResult
    repo_tools.bootstrap_project_repo.return_value = BootstrapRepoResult(
        html_url="https://github.com/Snowziio/test3",
        default_branch="main",
        initial_populate_commit_sha="pop_sha",
    )
    github_gw_mock = MagicMock()
    github_gw_mock.get_repo.return_value = None
    bootstrap_svc = ProjectBootstrapService(
        repo_tools=repo_tools,
        feishu_gateway=gateway,
        github_gateway=github_gw_mock,
        template_owner="Snowziio",
        template_repo="Template-repository",
        new_owner="Snowziio",
    )

    service = CoordinatorService()
    store = JsonStateStore(settings.state_store_path)

    with patch.object(Settings, "validate_runtime", return_value=None):
        settings.validate_runtime = lambda: None
        app = CoordinatorRuntimeApp(
            settings=settings, store=store, service=service, gateway=gateway,
            project_bootstrap_service=bootstrap_svc,
        )
        # wire github gateway for req-registry append
        app._github_gateway = gateway

    # Step 1: /create project
    ctx_bootstrap = MessageContext(
        message_id="m1", chat_id="group_c", chat_type="group",
        user_id="ou_alice", user_name="Alice",
        text="/create project test3 --category saas-ai-automation --owner ou_alice",
    )
    msgs = app.handle_text_message(ctx_bootstrap)
    assert any("已就绪" in getattr(m, "text", "") for m in msgs)

    # Confirm project is PROVISIONED
    cfg = state["test3"]
    assert cfg.bootstrap_status == "PROVISIONED"
    # Sync coordinator service with post-bootstrap state
    service.project_configs["test3"] = cfg

    # Step 2: /create req
    ctx_req = MessageContext(
        message_id="m2", chat_id="group_c", chat_type="group",
        user_id="ou_alice", user_name="Alice",
        text="/create req test3 会话鉴权改造",
    )
    msgs2 = app.handle_text_message(ctx_req)
    assert any("REQ-" in getattr(m, "text", "") for m in msgs2)

    reqs = list(service.requirements.values())
    assert len(reqs) == 1
    assert reqs[0].project == "test3"

    # req-registry append called (via gateway.commit_files)
    # There will be multiple commit_files calls (bootstrap populate + registry append)
    # Just verify at least one went to project/req-registry.yaml
    registry_calls = [
        c for c in gateway.commit_files.call_args_list
        if any(fc.path == "project/req-registry.yaml" for fc in c.kwargs.get("files", []))
    ]
    assert len(registry_calls) == 1
```

- [ ] **Step 2: Run — observe behavior**

```bash
python -m pytest tests/test_project_layer_e2e.py -v
```

Expected: PASS (or minor setup issues to fix; expect 1-2 iterations on fixture wiring).

If the e2e test reveals integration gaps, fix them inline with minimal code changes rather than mocking harder.

- [ ] **Step 3: Commit**

```bash
git add tests/test_project_layer_e2e.py
git commit -m "test(project-layer): e2e bootstrap → REQ create → registry append"
```

---

## Phase J: Real smoke (manual — outside pytest)

### Task J1: Configure real GitHub token + populate Template-repository

**Files:**
- (Manual) GitHub Settings
- (Manual) Template-repository content push

- [ ] **Step 1: Verify `Snowziio/Template-repository` has `is_template=true`**

In browser: https://github.com/Snowziio/Template-repository/settings → confirm "Template repository" checkbox is ticked. If not, tick it. (This is a 30-second manual check.)

- [ ] **Step 2: Push minimal template content**

Clone Template-repository locally and push the 4 files listed in spec §4.1:

```bash
cd /tmp && rm -rf Template-repository && \
  git clone git@github.com:Snowziio/Template-repository.git && \
  cd Template-repository && \
  cat > README.md <<'EOF'
# Template Repository

此仓库是 Snowziio harness 流程的项目模板。
通过 `/create project` 命令会以本仓库为蓝本生成新项目。

详见：`docs/superpowers/specs/2026-04-20-project-layer-design.md`
EOF
  cat > .gitignore <<'EOF'
# Python
__pycache__/
*.py[cod]
*.egg-info/
.venv/

# Node
node_modules/
dist/
.next/

# Go
bin/
vendor/

# IDE
.vscode/
.idea/
.DS_Store
EOF
  mkdir -p .github/workflows && cat > .github/workflows/ci.yml <<'EOF'
name: CI
on:
  push:
    branches: [main]
  pull_request:

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: echo "Lint step (placeholder — project to fill in based on stack)"

  test:
    runs-on: ubuntu-latest
    needs: lint
    steps:
      - uses: actions/checkout@v4
      - run: echo "Test step (placeholder — project to fill in based on stack)"
EOF
  git add -A && git commit -m "feat: minimal template skeleton (README + gitignore + CI placeholder)" && git push origin main
```

- [ ] **Step 3: Verify with `get_repo` probe**

From a Python shell inside the repo venv:

```bash
cd /Users/daxin/work/requirement-workflow-feishu
python -c "
import os
from requirement_workflow_v12.github_gateway import GitHubGateway
from requirement_workflow_v12.config import Settings
s = Settings(github_token=os.environ['GITHUB_TOKEN'])
with GitHubGateway(s) as gw:
    r = gw.get_repo(owner='Snowziio', name='Template-repository')
    print('is_template:', r.get('is_template'))
"
```

Expected: `is_template: True`.

- [ ] **Step 4: Commit this plan's reference to manual setup done**

No git commit — this is a check-the-box task. Proceed once verified.

---

### Task J2: Real smoke — create `test3` end-to-end

**Files:**
- (Runtime) OpenClaw coordinator on remote server
- (Runtime) Feishu group `group_c`

- [ ] **Step 1: Restart coordinator service with new code deployed**

```bash
# Deploy latest code to remote (use existing deploy script, e.g. the sync pattern from Phase 1)
scripts/sync_openclaw_server.sh  # or whatever the deploy script is
# Restart coordinator service on remote
ssh admin@47.251.81.45 "systemctl --user restart coordinator.service && systemctl --user status coordinator.service"
```

- [ ] **Step 2: In Feishu creation group, send `/create project test3 --category saas-ai-automation --owner <your_open_id>`**

Expected reply card: `项目 test3 已就绪 ... Repo: https://github.com/Snowziio/test3 ...`

- [ ] **Step 3: Verify in GitHub**

```bash
gh repo view Snowziio/test3 --web
```

Confirm:
- `docs/ARCHITECTURE.md` exists and contains `category: saas-ai-automation`
- `project/req-registry.yaml` contains `project: test3` and `requirements: []`
- `project/environments.yaml` / `project/SECRETS-TODO.md` / `CLAUDE.md` / `SKILL.md` all present

- [ ] **Step 4: Verify in Bitable**

Open Feishu Bitable `project_configs` table. Confirm the `test3` row has:
- `bootstrap_status = PROVISIONED`
- `github_repo_url = https://github.com/Snowziio/test3`
- `feishu_chat_id = oc_...`
- `architecture_doc_id` populated

- [ ] **Step 5: Send `/create req test3 会话鉴权冒烟`**

Expected reply: `REQ-2026-04-XX-001 已创建（project=test3, name=会话鉴权冒烟）`.

- [ ] **Step 6: Verify registry updated**

```bash
gh api /repos/Snowziio/test3/contents/project/req-registry.yaml --jq '.content' | base64 -d
```

Expected: one `req_id` entry in `requirements:` list.

- [ ] **Step 7: Commit a note-of-completion**

```bash
cd /Users/daxin/work/requirement-workflow-feishu
# No code changes; just a marker commit with empty --allow-empty if preferred, or skip.
git log -1 --oneline  # sanity check — nothing to commit
```

---

## Self-Review

(Run this checklist after completing the plan — do not dispatch subagent.)

**1. Spec coverage:**

| Spec section | Implemented in task |
|---|---|
| §1.1-1.3 Goals / non-goals | (documented in methodology H1) |
| §2 State machine + ProjectConfig fields | A1, A2, A3 |
| §3.1 /create project trigger | E1, E5 |
| §3.2 Bootstrap 7 steps | D1-D6 |
| §3.3 Failure/resume | D7 |
| §3.4 GitHub Generate API mechanism | B1 (get_repo), C2 (bootstrap_project_repo) |
| §4 Template repo + populate | B2 (static_content), J1 (manual populate) |
| §5.1 /create req command | E2, E3 |
| §5.2 Free-text deprecation | E3 |
| §5.3 Pre-check PROVISIONED | E3 |
| §5.4 Remove _initialize_project_for_first_req | E4 |
| §5.5 req-registry auto-append | G1 |
| §6 project_context_change unified gate | F1, F2 |
| §7 Governance defaults | E1, E2, E5 (uniqueness checks; no-gating default) |
| §8 MVP scope | all phases |
| §9 Code structure | matches File Structure section above |
| §10 Tests | interleaved per task |
| §11 Docs | H1, H2 |
| §13 Open questions | (deferred to writing-plans follow-ups; flagged in H2 addendum) |

**Gaps found during self-review:** none — every spec clause has a task.

**2. Placeholder scan:**
- No "TBD" / "TODO" / "later" in task steps
- All code steps contain complete code
- All test steps include the actual test code
- No "similar to Task N" references

**3. Type consistency:**
- `BootstrapRequest` field names consistent across all tasks (`project` / `category` / `owner_user_id` / `creator_chat_id` / `github_username` / `resume`)
- `BootstrapStep` enum values consistent (`VALIDATE=1, UPSERT_CONFIG=2, CREATE_REPO=3, POPULATE_MAIN=4, CREATE_ARCHITECTURE_DOC=5, CREATE_FEISHU_GROUP=6, FINALIZE=7`)
- `BootstrapResult` fields (`project / github_repo_url / architecture_doc_id / architecture_doc_url / feishu_chat_id / template_version`) consistent
- `PlanArtifacts.project_context_change` replaces `architecture_change` everywhere (Task F2 removes both callers + schema)
- `project_context_change.changes[].artifact` values consistent (`architecture` / `environments` / `skill_md`)

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-20-project-layer-plan.md`.

Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
