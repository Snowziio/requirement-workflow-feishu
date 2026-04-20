# `/create` 卡片化交互改造实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `/create project` 和 `/create req` 从 CLI flag 形式改成两阶段卡片交互（触发 → 发卡 → 用户填表 → 提交），同时收齐 ARCHITECTURE.md 种子字段、删除旧 CLI 路径、加卡片回调去重。

**Architecture:** 新增 `ProjectCreationFormPayload` + 项目卡构造器 + 提取器 + `submit_create_project` 动作分支；改造 `_build_requirement_creation_card` 让 project 字段变成下拉；`render_template` 接受 `seed` kwarg 把 `display_name/brief/tech_stack` 注入 ARCHITECTURE.md；沿用已有 `_seen_message_ids` 的 bounded `OrderedDict` 模式新增 `_seen_card_action_ids`。所有改动集中在 `service_app.py`、`protocols.py`、`architecture_templates.py` + 5 个 YAML 模板。

**Tech Stack:** Python 3.11, dataclasses, pytest, Feishu v2 card schema (`tag: form` / `select_static` / `input`), `collections.OrderedDict` LRU。

**Spec reference:** `docs/superpowers/specs/2026-04-20-create-card-flow-design.md`

---

## File Structure

**修改 / 新增清单**

| 路径 | 动作 | 责任 |
|---|---|---|
| `src/requirement_workflow_v12/protocols.py` | 修改 | 新增 `ProjectCreationFormPayload` dataclass；从 `CreationFormPayload` 移除 `category` 字段 |
| `src/requirement_workflow_v12/architecture_templates.py` | 修改 | `render_template` 新增 `seed` kwarg，注入 `{{display_name}}` / `{{brief}}` / `{{tech_stack}}` |
| `docs/context/architecture-templates/*.yaml`（5 个） | 修改 | 在 YAML 头部加 `display_name:` / `brief:` / `tech_stack_notes:` 三行，用 `{{...}}` 占位 |
| `src/requirement_workflow_v12/service_app.py` | 修改 | 所有核心改动：parser 收紧、新增 project 卡 / payload / extractor、submit branch、req 卡下拉化、category 删除、card-action dedupe |
| `tests/test_architecture_templates_seed.py` | **新增** | render_template seed 单元测试 |
| `tests/test_project_creation_card.py` | **新增** | project 卡结构 + extractor 单元测试 |
| `tests/test_service_app_card_submit_project.py` | **新增** | `submit_create_project` 集成测试（新建 / resume / PROVISIONED 拒绝 / StepError） |
| `tests/test_service_app_card_submit_req.py` | **新增** | 需求卡 project 下拉 + 无项目拒绝 + status != PROVISIONED 拒绝 |
| `tests/test_service_app_slash_create_project.py` | **改造** | 删除 flag-based 用例，新增「`/create project` → 返回卡 + 不调 Bootstrap」用例 |
| `tests/test_service_app_slash_create_req.py` | **改造** | 删除 flag-based 用例，新增「`/create req` → 返回卡」用例 |
| `tests/test_card_dedupe.py` | **新增** | `_mark_card_action_seen` + 集成去重测试 |

**非目标**：不改 `project_configs` schema、不改 `ProjectConfig` dataclass、不改 Bootstrap 内部。

---

## Task 1: `ProjectCreationFormPayload` dataclass

**Files:**
- Modify: `src/requirement_workflow_v12/protocols.py`
- Test: （数据类不需要单独测试，Task 3 用）

- [ ] **Step 1: 在 `protocols.py` 里加 dataclass**

在 `CreationFormPayload` 定义之后（大约第 51 行后）追加：

```python
@dataclass
class ProjectCreationFormPayload:
    # Required
    project: str
    category: str
    owner_user_id: str
    creator_chat_id: str
    # Optional (seed into ARCHITECTURE.md)
    display_name: str = ""
    brief: str = ""
    github_username: str = ""
    tech_stack: str = ""
```

- [ ] **Step 2: 验证 import**

Run: `python -c "from requirement_workflow_v12.protocols import ProjectCreationFormPayload; p = ProjectCreationFormPayload(project='x', category='y', owner_user_id='u', creator_chat_id='c'); print(p)"`
Expected: 打印出 dataclass 实例，不报错。

- [ ] **Step 3: Commit**

```bash
git add src/requirement_workflow_v12/protocols.py
git commit -m "feat(protocols): add ProjectCreationFormPayload dataclass

Collects required (project/category/owner/chat) and optional
(display_name/brief/github_username/tech_stack) fields submitted from
the new project-creation card. Optional fields seed ARCHITECTURE.md
via render_template(seed=...)."
```

---

## Task 2: `render_template` seed kwarg — failing test

**Files:**
- Test: `tests/test_architecture_templates_seed.py`

- [ ] **Step 1: 写失败测试**

Create `tests/test_architecture_templates_seed.py`：

```python
"""Unit tests for render_template's seed kwarg."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.architecture_templates import render_template  # noqa: E402


def test_render_template_substitutes_seed_fields():
    version, text = render_template(
        "saas-ai-automation",
        project="test5",
        seed={
            "display_name": "Test 5 Display",
            "brief": "解决 X 场景的 Y 自动化",
            "tech_stack": "FastAPI + OpenAI + PostgreSQL",
        },
    )
    assert version.startswith("saas-ai-automation.v")
    assert "Test 5 Display" in text
    assert "解决 X 场景的 Y 自动化" in text
    assert "FastAPI + OpenAI + PostgreSQL" in text
    # Existing placeholders still work
    assert "test5" in text
    assert "{pkg}" not in text
    assert "{project}" not in text


def test_render_template_seed_missing_fields_become_empty():
    version, text = render_template(
        "saas-ai-automation",
        project="test6",
        seed={"display_name": "Only Name"},
    )
    assert "Only Name" in text
    # Missing keys substitute to empty string — none of the placeholder
    # literals should leak into the final output.
    assert "{{display_name}}" not in text
    assert "{{brief}}" not in text
    assert "{{tech_stack}}" not in text


def test_render_template_no_seed_still_works():
    """Backward-compat: callers not passing seed still get a valid render."""
    version, text = render_template("saas-ai-automation", project="test7")
    assert "test7" in text
    assert "{{display_name}}" not in text
    assert "{{brief}}" not in text
    assert "{{tech_stack}}" not in text
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_architecture_templates_seed.py -v`
Expected: FAIL — `TypeError: render_template() got an unexpected keyword argument 'seed'`（或者模板里还没有占位符）。

---

## Task 3: `render_template` seed kwarg — 实现

**Files:**
- Modify: `src/requirement_workflow_v12/architecture_templates.py`

- [ ] **Step 1: 修改函数签名与替换逻辑**

把 `render_template` 函数（`architecture_templates.py:53-63`）整段替换为：

```python
def render_template(
    category: str,
    *,
    project: str,
    seed: dict[str, str] | None = None,
) -> tuple[str, str]:
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
    return version, text
```

- [ ] **Step 2: 给 5 个模板加占位符**

**所有 5 个 YAML 模板**（`docs/context/architecture-templates/{enterprise-app,enterprise-bot,miniprogram,public-web-site,saas-ai-automation}.v1.yaml`），在**第 2 行注释**「Placeholders:」那行之后紧跟下面这段（显示名 / 简述 / 用户技术栈备注），整体结构改为：

第 1-2 行保持不变：
```yaml
# Generated from template: <category>.v1
# Placeholders: {project} {pkg} {date} {{display_name}} {{brief}} {{tech_stack}}
```

然后紧跟着插入三行（在 `version: "{date}"` 之前）：
```yaml
display_name: "{{display_name}}"
brief: "{{brief}}"
tech_stack_notes: "{{tech_stack}}"
```

**具体到每个文件**，用 `Edit` 工具把第 2 行

```
# Placeholders: {project} {pkg} {date}
```

替换为

```
# Placeholders: {project} {pkg} {date} {{display_name}} {{brief}} {{tech_stack}}
display_name: "{{display_name}}"
brief: "{{brief}}"
tech_stack_notes: "{{tech_stack}}"
```

对这 5 个文件各做一次：
- `docs/context/architecture-templates/enterprise-app.v1.yaml`
- `docs/context/architecture-templates/enterprise-bot.v1.yaml`
- `docs/context/architecture-templates/miniprogram.v1.yaml`
- `docs/context/architecture-templates/public-web-site.v1.yaml`
- `docs/context/architecture-templates/saas-ai-automation.v1.yaml`

- [ ] **Step 3: 跑测试确认通过**

Run: `pytest tests/test_architecture_templates_seed.py -v`
Expected: PASS（3 条用例全通过）。

- [ ] **Step 4: 回归跑全部模板相关测试**

Run: `pytest tests/test_architecture_templates.py tests/test_architecture_templates_seed.py -v`
Expected: 所有已有测试仍 PASS。

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/architecture_templates.py \
        docs/context/architecture-templates/*.yaml \
        tests/test_architecture_templates_seed.py
git commit -m "feat(architecture-templates): seed kwarg for display_name/brief/tech_stack

render_template now accepts seed={display_name, brief, tech_stack}
and substitutes {{...}} placeholders. Missing seed keys render to
empty string. All 5 category templates gain three top-level fields
(display_name, brief, tech_stack_notes) populated from the seed."
```

---

## Task 4: `/create project` parser 收紧 — 失败测试

**Files:**
- Modify: `tests/test_service_app_slash_create_project.py`

- [ ] **Step 1: 改 `test_service_app_slash_create_project.py` 头部用例**

把 `test_parse_create_project_happy_path`、`test_parse_create_project_resume_flag`、`test_parse_create_project_missing_owner_is_allowed`、`test_parse_create_project_missing_category_is_allowed`（现有 4 条 flag 基础用例）整体**替换**为下面 3 条：

```python
def test_parse_create_project_matches_bare_command():
    cmd = parse_create_project_command("/create project")
    assert cmd is not None


def test_parse_create_project_matches_with_trailing_whitespace():
    cmd = parse_create_project_command("/create project   ")
    assert cmd is not None


def test_parse_create_project_rejects_trailing_args():
    """Tightened: any trailing arg (project name, flag) is no longer accepted."""
    assert parse_create_project_command("/create project test3") is None
    assert parse_create_project_command(
        "/create project test3 --category saas-ai-automation"
    ) is None
    assert parse_create_project_command("/create project --category x") is None
```

保留 `test_parse_create_project_returns_none_for_other_text`，但把 `"/create req test3 foo"` 那条断言照旧。

- [ ] **Step 2: 跑改后的测试确认失败**

Run: `pytest tests/test_service_app_slash_create_project.py::test_parse_create_project_rejects_trailing_args -v`
Expected: FAIL — 当前正则允许 `project test3` 带任意尾部，parser 会返回非 None。

---

## Task 5: `/create project` parser 收紧 — 实现

**Files:**
- Modify: `src/requirement_workflow_v12/service_app.py`

- [ ] **Step 1: 收紧 `_CREATE_PROJECT_RE` 并简化 `CreateProjectCommand`**

把 `src/requirement_workflow_v12/service_app.py` 第 72-107 行（`CreateProjectCommand` dataclass + 正则 + `parse_create_project_command`）替换为：

```python
@dataclass(frozen=True)
class CreateProjectCommand:
    """Marker object: `/create project` with no args was received.

    Card-based flow: the actual form values come later via
    _handle_card_action_payload(action_name='submit_create_project').
    """


_CREATE_PROJECT_RE = re.compile(r"^/create\s+project\s*$")

# Categories supported by Bootstrap. Keep in sync with
# project_bootstrap.static_content._SECRETS_CATEGORY_HINTS.
KNOWN_PROJECT_CATEGORIES: tuple[str, ...] = (
    "enterprise-app",
    "enterprise-bot",
    "miniprogram",
    "public-web-site",
    "saas-ai-automation",
)


def parse_create_project_command(text: str) -> CreateProjectCommand | None:
    if not _CREATE_PROJECT_RE.match(text.strip()):
        return None
    return CreateProjectCommand()
```

- [ ] **Step 2: 跑测试确认通过**

Run: `pytest tests/test_service_app_slash_create_project.py::test_parse_create_project_rejects_trailing_args tests/test_service_app_slash_create_project.py::test_parse_create_project_matches_bare_command tests/test_service_app_slash_create_project.py::test_parse_create_project_matches_with_trailing_whitespace tests/test_service_app_slash_create_project.py::test_parse_create_project_returns_none_for_other_text -v`
Expected: 4 条全 PASS。

（其他 flag-based 用例此时会 fail，下一个任务处理它们。）

---

## Task 6: `/create req` parser 收紧

**Files:**
- Modify: `src/requirement_workflow_v12/service_app.py`
- Modify: `tests/test_service_app_slash_create_req.py`

- [ ] **Step 1: 改测试**

先看一眼现有 `tests/test_service_app_slash_create_req.py` 都有哪些用例：

```bash
grep -nE "^def test_" tests/test_service_app_slash_create_req.py
```

把所有「带参数也能解析成功」的用例（例如 `test_parse_create_req_happy_path` 之类）替换为：

```python
def test_parse_create_req_matches_bare_command():
    cmd = parse_create_req_command("/create req")
    assert cmd is not None


def test_parse_create_req_rejects_trailing_args():
    assert parse_create_req_command("/create req test3 foo") is None
    assert parse_create_req_command("/create req test3 foo --summary bar") is None
    assert parse_create_req_command("/create req --project x") is None


def test_parse_create_req_returns_none_for_other_text():
    assert parse_create_req_command("随便聊聊") is None
    assert parse_create_req_command("/create project test3") is None
```

- [ ] **Step 2: 改 `parse_create_req_command` 与 `CreateReqCommand`**

把 `service_app.py` 第 110-154 行（`CreateReqCommand` + `parse_create_req_command`）替换为：

```python
@dataclass(frozen=True)
class CreateReqCommand:
    """Marker: `/create req` with no args was received."""


_CREATE_REQ_RE = re.compile(r"^/create\s+req\s*$")


def parse_create_req_command(text: str) -> CreateReqCommand | None:
    if not _CREATE_REQ_RE.match(text.strip()):
        return None
    return CreateReqCommand()
```

另外删除顶部 `import shlex`（它只被旧的 `parse_create_req_command` 使用，改完后会变成未引用；跑 `grep -n "^import shlex\|\bshlex\." src/requirement_workflow_v12/service_app.py` 确认没别处在用再删）。

- [ ] **Step 3: 跑测试确认通过**

Run: `pytest tests/test_service_app_slash_create_req.py::test_parse_create_req_matches_bare_command tests/test_service_app_slash_create_req.py::test_parse_create_req_rejects_trailing_args tests/test_service_app_slash_create_req.py::test_parse_create_req_returns_none_for_other_text -v`
Expected: 3 条 PASS。

---

## Task 7: 项目卡构造器 + 提取器 — 失败测试

**Files:**
- Create: `tests/test_project_creation_card.py`

- [ ] **Step 1: 写测试**

Create `tests/test_project_creation_card.py`：

```python
"""Unit tests for _build_project_creation_card and _extract_project_form_payload."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.service_app import (  # noqa: E402
    CoordinatorRuntimeApp,
    KNOWN_PROJECT_CATEGORIES,
    MessageContext,
)
from requirement_workflow_v12.config import Settings
from requirement_workflow_v12.store import JsonStateStore
from requirement_workflow_v12.coordinator_service import CoordinatorService


def _make_app(tmp_path):
    settings = MagicMock(spec=Settings)
    settings.state_store_path = str(tmp_path / "state.json")
    settings.creation_group_chat_id = "group_c"
    settings.openclaw_callback_secret = ""
    settings.openclaw_callback_ttl_seconds = 600
    settings.github_token = ""
    settings.feishu_user_id_type = "open_id"
    settings.github_template_owner = "Snowziio"
    settings.github_template_repo = "Template-repository"
    settings.github_org_owner = "Snowziio"
    service = CoordinatorService()
    store = JsonStateStore(settings.state_store_path)
    gateway = MagicMock()
    gateway.list_project_configs.return_value = {}
    with patch.object(Settings, "validate_runtime", return_value=None):
        settings.validate_runtime = lambda: None
        app = CoordinatorRuntimeApp(
            settings=settings, store=store, service=service, gateway=gateway,
        )
    return app


def test_project_card_has_required_fields(tmp_path):
    app = _make_app(tmp_path)
    ctx = MessageContext(
        message_id="m1", chat_id="oc_chat", chat_type="p2p",
        user_id="ou_alice", sender_name="Alice", text="/create project",
    )
    card = app._build_project_creation_card(ctx)
    form = card["body"]["elements"][0]
    assert form["tag"] == "form"
    names = [e.get("name") for e in form["elements"] if isinstance(e, dict)]
    # Required
    assert "project" in names
    assert "category" in names
    # Optional
    for optional in ("display_name", "brief", "github_username", "tech_stack"):
        assert optional in names, f"missing optional field {optional!r}"


def test_project_card_category_dropdown_has_all_known_categories(tmp_path):
    app = _make_app(tmp_path)
    ctx = MessageContext(
        message_id="m1", chat_id="oc_chat", chat_type="p2p",
        user_id="ou_alice", sender_name="Alice", text="/create project",
    )
    card = app._build_project_creation_card(ctx)
    form = card["body"]["elements"][0]
    category = next(e for e in form["elements"] if e.get("name") == "category")
    assert category["tag"] == "select_static"
    option_values = {o["value"] for o in category["options"]}
    assert option_values == set(KNOWN_PROJECT_CATEGORIES)


def test_project_card_submit_button_has_correct_action(tmp_path):
    app = _make_app(tmp_path)
    ctx = MessageContext(
        message_id="m1", chat_id="oc_chat_x", chat_type="group",
        user_id="ou_alice", sender_name="Alice", text="/create project",
    )
    card = app._build_project_creation_card(ctx)
    form = card["body"]["elements"][0]
    submit = next(e for e in form["elements"] if e.get("tag") == "button")
    assert submit["form_action_type"] == "submit"
    behavior = submit["behaviors"][0]
    assert behavior["type"] == "callback"
    assert behavior["value"]["action"] == "submit_create_project"
    # creator_chat_id is carried through the card for the submit handler.
    assert behavior["value"]["creator_chat_id"] == "oc_chat_x"


def test_extract_project_form_payload_happy_path(tmp_path):
    app = _make_app(tmp_path)
    payload = {
        "operator": {"open_id": "ou_alice"},
        "context": {"open_chat_id": "oc_chat_x"},
        "action": {
            "value": {"action": "submit_create_project", "creator_chat_id": "oc_chat_x"},
            "form_value": {
                "project": "  test5 ",
                "category": "saas-ai-automation",
                "display_name": "Test 5",
                "brief": "解决 X",
                "github_username": "alice",
                "tech_stack": "FastAPI",
            },
        },
    }
    form = app._extract_project_form_payload(
        payload, user_id="ou_alice", user_name="Alice",
    )
    assert form is not None
    assert form.project == "test5"  # trimmed
    assert form.category == "saas-ai-automation"
    assert form.owner_user_id == "ou_alice"
    assert form.creator_chat_id == "oc_chat_x"
    assert form.display_name == "Test 5"
    assert form.brief == "解决 X"
    assert form.github_username == "alice"
    assert form.tech_stack == "FastAPI"


def test_extract_project_form_payload_optional_fields_default_empty(tmp_path):
    app = _make_app(tmp_path)
    payload = {
        "operator": {"open_id": "ou_alice"},
        "context": {"open_chat_id": "oc_chat_x"},
        "action": {
            "value": {"action": "submit_create_project", "creator_chat_id": "oc_chat_x"},
            "form_value": {"project": "test5", "category": "saas-ai-automation"},
        },
    }
    form = app._extract_project_form_payload(
        payload, user_id="ou_alice", user_name="Alice",
    )
    assert form is not None
    assert form.display_name == ""
    assert form.brief == ""
    assert form.github_username == ""
    assert form.tech_stack == ""


def test_extract_project_form_payload_returns_none_if_required_missing(tmp_path):
    app = _make_app(tmp_path)
    payload = {
        "operator": {"open_id": "ou_alice"},
        "context": {"open_chat_id": "oc_chat_x"},
        "action": {
            "value": {"action": "submit_create_project"},
            "form_value": {"project": "", "category": ""},
        },
    }
    assert app._extract_project_form_payload(
        payload, user_id="ou_alice", user_name="Alice",
    ) is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_project_creation_card.py -v`
Expected: FAIL — `AttributeError: 'CoordinatorRuntimeApp' object has no attribute '_build_project_creation_card'`。

---

## Task 8: 项目卡构造器 + 提取器 — 实现

**Files:**
- Modify: `src/requirement_workflow_v12/service_app.py`

- [ ] **Step 1: 更新 import**

在 `service_app.py` 顶部的 `from .protocols import (...)` 里追加 `ProjectCreationFormPayload`：

```python
from .protocols import (
    AgentAuthorEventPayload,
    AgentRequirementContextQuery,
    AgentReviewEventPayload,
    AuthorStartBinding,
    CreationFormPayload,
    CreationRequest,
    ProjectCreationFormPayload,
)
```

- [ ] **Step 2: 添加 `_build_project_creation_card` 方法**

在 `_build_requirement_creation_card` 方法之前（约 `service_app.py:1763` 上方）插入：

```python
    def _build_project_creation_card(self, context: MessageContext) -> dict[str, object]:
        category_options = [
            {"text": {"tag": "plain_text", "content": label}, "value": value}
            for label, value in (
                ("企业内部应用", "enterprise-app"),
                ("企业内 Bot / Agent", "enterprise-bot"),
                ("小程序", "miniprogram"),
                ("公开 Web 站点", "public-web-site"),
                ("SaaS AI 自动化", "saas-ai-automation"),
            )
        ]
        return {
            "schema": "2.0",
            "config": {"wide_screen_mode": True},
            "header": {
                "template": "green",
                "title": {"tag": "plain_text", "content": "新建项目"},
                "subtitle": {"tag": "plain_text", "content": "填写项目基本信息 · 提交后自动跑 Bootstrap 并生成 ARCHITECTURE.md"},
            },
            "body": {
                "elements": [
                    {
                        "tag": "form",
                        "name": "project_create_form",
                        "elements": [
                            {
                                "tag": "input",
                                "name": "project",
                                "required": True,
                                "width": "fill",
                                "label": {"tag": "plain_text", "content": "项目代号（必填，小写字母开头，2-30 位）"},
                                "placeholder": {"tag": "plain_text", "content": "例如 test5 / payment-core"},
                            },
                            {
                                "tag": "select_static",
                                "name": "category",
                                "required": True,
                                "width": "fill",
                                "label": {"tag": "plain_text", "content": "项目类目（必填）"},
                                "placeholder": {"tag": "plain_text", "content": "选择项目类目"},
                                "options": category_options,
                            },
                            {
                                "tag": "input",
                                "name": "display_name",
                                "required": False,
                                "width": "fill",
                                "label": {"tag": "plain_text", "content": "项目显示名（选填）"},
                                "placeholder": {"tag": "plain_text", "content": "例如 测试项目 5"},
                            },
                            {
                                "tag": "input",
                                "name": "brief",
                                "required": False,
                                "width": "fill",
                                "input_type": "multiline_text",
                                "max_length": 500,
                                "label": {"tag": "plain_text", "content": "项目简述（选填，会写进 ARCHITECTURE.md）"},
                                "placeholder": {"tag": "plain_text", "content": "一两句话描述项目做什么"},
                            },
                            {
                                "tag": "input",
                                "name": "github_username",
                                "required": False,
                                "width": "fill",
                                "label": {"tag": "plain_text", "content": "GitHub 用户名（选填，会加为 repo collaborator）"},
                                "placeholder": {"tag": "plain_text", "content": "例如 alice"},
                            },
                            {
                                "tag": "input",
                                "name": "tech_stack",
                                "required": False,
                                "width": "fill",
                                "input_type": "multiline_text",
                                "max_length": 500,
                                "label": {"tag": "plain_text", "content": "技术栈备注（选填，会写进 ARCHITECTURE.md）"},
                                "placeholder": {"tag": "plain_text", "content": "例如 FastAPI + PostgreSQL + Redis"},
                            },
                            {
                                "tag": "button",
                                "name": "submit_create_project",
                                "text": {"tag": "plain_text", "content": "提交"},
                                "type": "primary_filled",
                                "form_action_type": "submit",
                                "behaviors": [
                                    {
                                        "type": "callback",
                                        "value": {
                                            "action": "submit_create_project",
                                            "creator_chat_id": context.chat_id,
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                ]
            },
        }
```

- [ ] **Step 3: 添加 `_extract_project_form_payload` 方法**

在 `_extract_creation_form_payload`（约 `service_app.py:1626`）**之后**插入：

```python
    def _extract_project_form_payload(
        self,
        payload: dict[str, object],
        *,
        user_id: str,
        user_name: str,
    ) -> ProjectCreationFormPayload | None:
        action = payload.get("action", {}) or {}
        value = self._extract_callback_value(action)
        form_value = action.get("form_value") or payload.get("form_value") or {}
        if not isinstance(form_value, dict):
            form_value = {}

        project = self._normalize_form_value(form_value.get("project"))
        category = self._normalize_form_value(form_value.get("category"))
        if not project or not category:
            return None

        context = payload.get("context", {}) or {}
        creator_chat_id = (
            self._normalize_form_value(value.get("creator_chat_id"))
            or self._normalize_form_value(context.get("open_chat_id"))
        )
        return ProjectCreationFormPayload(
            project=project,
            category=category,
            owner_user_id=user_id,
            creator_chat_id=creator_chat_id,
            display_name=self._normalize_form_value(form_value.get("display_name")),
            brief=self._normalize_form_value(form_value.get("brief")),
            github_username=self._normalize_form_value(form_value.get("github_username")),
            tech_stack=self._normalize_form_value(form_value.get("tech_stack")),
        )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_project_creation_card.py -v`
Expected: 6 条全 PASS。

---

## Task 9: `_handle_create_project_command` 改为返回卡

**Files:**
- Modify: `src/requirement_workflow_v12/service_app.py`
- Modify: `tests/test_service_app_slash_create_project.py`

- [ ] **Step 1: 更新 handler 调用方（`handle_text_message`）**

在 `service_app.py` 中找到（约第 420 行）：

```python
        project_cmd = parse_create_project_command(text)
        if project_cmd is not None:
            return self._handle_create_project_command(project_cmd, context)
```

保持不变（这里只把 parser 返回的 marker 传进去）。同理 `parse_create_req_command` 的分支。

同时把 `handle_text_message` 里**先前** `handle_slash_command(text)` 返回 `None` 的裸 `/create`（既不 project 也不 req）兜底文本加到这里：在 `req_cmd = parse_create_req_command(text)` 分支之后追加：

```python
        if text.strip() in {"/create", "/create "}:
            return [OutboundMessage(
                receive_id=context.chat_id,
                text="请用 `/create project` 或 `/create req`",
            )]
```

- [ ] **Step 2: 重写 `_handle_create_project_command`**

把 `service_app.py` 第 493-556 行（整个 `_handle_create_project_command` 方法）**替换**为：

```python
    def _handle_create_project_command(
        self, cmd: "CreateProjectCommand", context: MessageContext,
    ) -> list[OutboundMessage | OutboundCard]:
        if self._project_bootstrap_service is None:
            return [OutboundMessage(
                receive_id=context.chat_id,
                text="Bootstrap 服务未启用；请联系运维检查 settings.github_token 配置",
            )]
        return [OutboundCard(
            receive_id=context.chat_id,
            card=self._build_project_creation_card(context),
        )]
```

- [ ] **Step 3: 更新已有集成测试**

在 `tests/test_service_app_slash_create_project.py` 里：

- **删除**以下 flag-based 集成用例：
  - `test_handle_text_message_routes_create_project_triggers_bootstrap`
  - `test_handle_create_project_owner_defaults_to_sender`
  - `test_handle_create_project_missing_category_lists_choices`
  - `test_handle_create_project_works_in_p2p_dm`
  - `test_handle_create_project_works_in_arbitrary_group`
  - `test_handle_create_project_strips_at_mention_prefix`
  - `test_handle_create_project_strips_multiple_at_mention_prefixes`
  - `test_handle_create_project_invalid_category_lists_choices`

- **保留**：
  - `test_on_message_receive_dedupes_by_message_id`
  - `test_on_message_receive_still_allows_distinct_message_ids`
  - `test_mark_message_seen_evicts_oldest_when_full`
  - parser-level 用例（Task 4 已改）

但由于这些 dedupe 测试会收到 `/create project --category ...` 文本，现在 parser 已经不匹配那种文本，它们会走到别的分支。把 dedupe 测试里的文本换成裸 `/create project`：

```python
def test_on_message_receive_dedupes_by_message_id(tmp_path):
    app, bootstrap_svc = _make_app(tmp_path)
    event = _fake_receive_event(
        message_id="msg_dup_42",
        chat_id="oc_abc",
        text="/create project",
    )
    app._on_message_receive(event)
    app._on_message_receive(event)
    # Bootstrap is NOT invoked by the slash command anymore; the command
    # only renders a card. Dedupe is now measured by card sends.
    card_sends = [
        c for c in app.gateway.send_card.call_args_list
    ] if hasattr(app.gateway, "send_card") else []
    assert len(card_sends) == 1 or app.gateway.send_text.call_count == 0
    # 关键断言：Bootstrap 一次都不应该被调用
    bootstrap_svc.run.assert_not_called()
```

同理把 `test_on_message_receive_still_allows_distinct_message_ids` 中的 `/create project ... --resume` 文本换成两条裸命令：

```python
def test_on_message_receive_still_allows_distinct_message_ids(tmp_path):
    app, bootstrap_svc = _make_app(tmp_path)
    app._on_message_receive(_fake_receive_event(
        message_id="msg_a", chat_id="oc_abc", text="/create project",
    ))
    app._on_message_receive(_fake_receive_event(
        message_id="msg_b", chat_id="oc_abc", text="/create project",
    ))
    # 两条独立消息都会发卡，但都不会调 Bootstrap
    bootstrap_svc.run.assert_not_called()
```

追加两条新用例：

```python
def test_handle_create_project_bare_command_returns_card(tmp_path):
    """`/create project` (no flags) returns the project creation card, does NOT run Bootstrap."""
    from requirement_workflow_v12.service_app import MessageContext, OutboundCard

    app, bootstrap_svc = _make_app(tmp_path)
    ctx = MessageContext(
        message_id="m1", chat_id="oc_chat_x", chat_type="p2p",
        user_id="ou_alice", sender_name="Alice", text="/create project",
    )
    msgs = app.handle_text_message(ctx)
    bootstrap_svc.run.assert_not_called()
    assert len(msgs) == 1
    assert isinstance(msgs[0], OutboundCard)
    card = msgs[0].card
    form = card["body"]["elements"][0]
    assert form["tag"] == "form"


def test_handle_create_project_bare_command_in_group(tmp_path):
    from requirement_workflow_v12.service_app import MessageContext, OutboundCard

    app, bootstrap_svc = _make_app(tmp_path)
    ctx = MessageContext(
        message_id="m1", chat_id="oc_group_y", chat_type="group",
        user_id="ou_bob", sender_name="Bob", text="/create project",
    )
    msgs = app.handle_text_message(ctx)
    bootstrap_svc.run.assert_not_called()
    assert isinstance(msgs[0], OutboundCard)
    assert msgs[0].receive_id == "oc_group_y"
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_service_app_slash_create_project.py -v`
Expected: 所有剩余用例 PASS。

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/protocols.py \
        src/requirement_workflow_v12/service_app.py \
        tests/test_project_creation_card.py \
        tests/test_service_app_slash_create_project.py \
        tests/test_service_app_slash_create_req.py
git commit -m "feat(service-app): /create project returns card, not Bootstrap

The slash command is now a pure UI trigger: bare '/create project' renders
the new creation card. Parser rejects all trailing args. Old CLI flag
users must re-learn: fill the card, submit. Flag-based integration tests
deleted (path no longer exists)."
```

---

## Task 10: `submit_create_project` 处理分支 — 失败测试

**Files:**
- Create: `tests/test_service_app_card_submit_project.py`

- [ ] **Step 1: 写测试**

Create `tests/test_service_app_card_submit_project.py`：

```python
"""Integration tests for the submit_create_project card-action branch."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.service_app import CoordinatorRuntimeApp  # noqa: E402
from requirement_workflow_v12.config import Settings  # noqa: E402
from requirement_workflow_v12.store import JsonStateStore  # noqa: E402
from requirement_workflow_v12.coordinator_service import CoordinatorService  # noqa: E402
from requirement_workflow_v12.project_bootstrap.types import (  # noqa: E402
    BootstrapRequest,
    BootstrapResult,
    BootstrapStep,
    BootstrapStepError,
)
from requirement_workflow_v12.project_config import ProjectConfig  # noqa: E402


def _make_app(tmp_path, *, project_configs=None):
    settings = MagicMock(spec=Settings)
    settings.state_store_path = str(tmp_path / "state.json")
    settings.creation_group_chat_id = "group_c"
    settings.openclaw_callback_secret = ""
    settings.openclaw_callback_ttl_seconds = 600
    settings.github_token = ""
    settings.feishu_user_id_type = "open_id"
    settings.github_template_owner = "Snowziio"
    settings.github_template_repo = "Template-repository"
    settings.github_org_owner = "Snowziio"
    bootstrap_svc = MagicMock()
    bootstrap_svc.run.return_value = BootstrapResult(
        project="test5",
        github_repo_url="https://github.com/Snowziio/test5",
        architecture_doc_id="doc_x",
        architecture_doc_url="https://feishu.example/doc_x",
        feishu_chat_id="oc_test5",
        template_version="saas-ai-automation.v1",
    )
    service = CoordinatorService()
    store = JsonStateStore(settings.state_store_path)
    gateway = MagicMock()
    gateway.list_project_configs.return_value = project_configs or {}
    with patch.object(Settings, "validate_runtime", return_value=None):
        settings.validate_runtime = lambda: None
        app = CoordinatorRuntimeApp(
            settings=settings, store=store, service=service, gateway=gateway,
            project_bootstrap_service=bootstrap_svc,
        )
    return app, bootstrap_svc


def _submit_payload(**form_overrides):
    form_value = {
        "project": "test5",
        "category": "saas-ai-automation",
        "display_name": "Test 5",
        "brief": "测试简述",
        "github_username": "alice",
        "tech_stack": "FastAPI",
        **form_overrides,
    }
    return {
        "operator": {"open_id": "ou_alice", "name": "Alice"},
        "context": {"open_chat_id": "oc_chat_x", "open_message_id": "om_card_1"},
        "action": {
            "value": {"action": "submit_create_project", "creator_chat_id": "oc_chat_x"},
            "form_value": form_value,
        },
    }


def test_submit_new_project_runs_bootstrap_without_resume(tmp_path):
    app, bootstrap_svc = _make_app(tmp_path)
    status, resp = app._handle_card_action_payload(_submit_payload())
    assert status == 200
    bootstrap_svc.run.assert_called_once()
    req: BootstrapRequest = bootstrap_svc.run.call_args.args[0]
    assert req.project == "test5"
    assert req.category == "saas-ai-automation"
    assert req.owner_user_id == "ou_alice"
    assert req.creator_chat_id == "oc_chat_x"
    assert req.resume is False
    assert req.github_username == "alice"
    # Toast shows success
    assert resp.get("toast", {}).get("type") == "success"


def test_submit_existing_nonprovisioned_project_resumes(tmp_path):
    existing = ProjectConfig(
        category="saas-ai-automation",
        template_version="saas-ai-automation.v1",
        architecture_doc_id="",
        architecture_doc_url="",
        bootstrap_status="BOOTSTRAPPING",
        project_status="BOOTSTRAPPING",
    )
    app, bootstrap_svc = _make_app(tmp_path, project_configs={"test5": existing})
    status, _ = app._handle_card_action_payload(_submit_payload())
    assert status == 200
    bootstrap_svc.run.assert_called_once()
    req = bootstrap_svc.run.call_args.args[0]
    assert req.resume is True


def test_submit_existing_provisioned_project_rejected(tmp_path):
    existing = ProjectConfig(
        category="saas-ai-automation",
        template_version="saas-ai-automation.v1",
        architecture_doc_id="doc",
        architecture_doc_url="url",
        bootstrap_status="PROVISIONED",
        project_status="PROVISIONED",
    )
    app, bootstrap_svc = _make_app(tmp_path, project_configs={"test5": existing})
    status, resp = app._handle_card_action_payload(_submit_payload())
    assert status == 200
    bootstrap_svc.run.assert_not_called()
    # A toast error is returned, and a text reply is sent to the chat.
    toast = resp.get("toast", {})
    assert toast.get("type") in ("error", "info")
    # The gateway should have sent a rejection text to creator_chat_id.
    app.gateway.send_text.assert_called()
    text = app.gateway.send_text.call_args.args[1]
    assert "/create req" in text
    assert "test5" in text


def test_submit_bootstrap_step_error_reports_step(tmp_path):
    app, bootstrap_svc = _make_app(tmp_path)
    bootstrap_svc.run.side_effect = BootstrapStepError(
        step=BootstrapStep.CREATE_REPO, message="rate limited",
    )
    status, resp = app._handle_card_action_payload(_submit_payload())
    assert status == 200
    app.gateway.send_text.assert_called()
    text = app.gateway.send_text.call_args.args[1]
    assert "CREATE_REPO" in text
    assert "rate limited" in text
    assert "/create project" in text  # retry hint


def test_submit_invalid_form_returns_toast_error(tmp_path):
    app, bootstrap_svc = _make_app(tmp_path)
    payload = _submit_payload(project="", category="")
    status, resp = app._handle_card_action_payload(payload)
    assert status == 200
    bootstrap_svc.run.assert_not_called()
    assert resp.get("toast", {}).get("type") == "error"


def test_submit_passes_seed_to_bootstrap_via_architecture_md(tmp_path):
    """Seed fields from the card should drive render_template's seed kwarg."""
    app, bootstrap_svc = _make_app(tmp_path)
    # Intercept the render_template call indirectly: Bootstrap stub receives
    # the full BootstrapRequest; we exposed the seed via its own attribute.
    status, _ = app._handle_card_action_payload(_submit_payload())
    assert status == 200
    req: BootstrapRequest = bootstrap_svc.run.call_args.args[0]
    assert req.architecture_seed == {
        "display_name": "Test 5",
        "brief": "测试简述",
        "tech_stack": "FastAPI",
    }
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_service_app_card_submit_project.py -v`
Expected: FAIL — `_handle_card_action_payload` 返回「未识别的卡片动作」info toast；也没有 `architecture_seed` 字段。

---

## Task 11: `submit_create_project` 分支 — 实现

**Files:**
- Modify: `src/requirement_workflow_v12/service_app.py`
- Modify: `src/requirement_workflow_v12/project_bootstrap/types.py`
- Modify: `src/requirement_workflow_v12/project_bootstrap/service.py`

- [ ] **Step 1: 给 `BootstrapRequest` 加 `architecture_seed` 字段**

先看一眼当前 `BootstrapRequest`：

```bash
grep -nA 15 "class BootstrapRequest" src/requirement_workflow_v12/project_bootstrap/types.py
```

在它的字段清单里（`resume` 之后）追加：

```python
    architecture_seed: dict[str, str] = field(default_factory=dict)
```

顶部如有需要加 `from dataclasses import dataclass, field`（如果 `field` 没 import）。

- [ ] **Step 2: 让 `ProjectBootstrapService.run` 把 seed 传给 `render_template`**

把 `service.py:306-310` 的：

```python
    def run(self, request: BootstrapRequest) -> BootstrapResult:
        self.validate(request)
        template_version, rendered_arch_md = render_template(
            request.category, project=request.project
        )
```

改为：

```python
    def run(self, request: BootstrapRequest) -> BootstrapResult:
        self.validate(request)
        template_version, rendered_arch_md = render_template(
            request.category,
            project=request.project,
            seed=request.architecture_seed or None,
        )
```

- [ ] **Step 3: 在 `_handle_card_action_payload` 里添加分支**

在 `service_app.py` 的 `_handle_card_action_payload` 方法里，`submit_create_requirement` 分支**之前**（约 line 1462）插入：

```python
        if action_name == "submit_create_project":
            form = self._extract_project_form_payload(
                payload, user_id=user_id, user_name=user_name,
            )
            if form is None:
                return 200, {"toast": {"type": "error", "content": "项目代号 / 类目为必填字段。"}}
            if not re.match(r"^[a-z][a-z0-9-]{1,30}$", form.project):
                self.gateway.send_text(
                    form.creator_chat_id,
                    f"项目代号格式不合法：{form.project!r}（需小写字母开头、2-30 位、仅含 a-z 0-9 -）",
                )
                return 200, {"toast": {"type": "error", "content": "项目代号格式不合法。"}}
            if form.category not in KNOWN_PROJECT_CATEGORIES:
                return 200, {"toast": {"type": "error", "content": f"未知类目：{form.category}"}}
            if self._project_bootstrap_service is None:
                return 200, {"toast": {"type": "error", "content": "Bootstrap 服务未启用。"}}

            existing = self.service.project_configs.get(form.project)
            if existing is not None and existing.bootstrap_status == "PROVISIONED":
                self.gateway.send_text(
                    form.creator_chat_id,
                    f"项目 {form.project} 已经完成 Bootstrap，请用 `/create req` 创建需求。",
                )
                return 200, {"toast": {"type": "info", "content": "项目已完成 Bootstrap。"}}

            resume = existing is not None and existing.bootstrap_status != "PROVISIONED"

            from .project_bootstrap.types import BootstrapRequest, BootstrapStepError
            from .project_bootstrap.service import ValidationError
            req = BootstrapRequest(
                project=form.project,
                category=form.category,
                owner_user_id=form.owner_user_id,
                creator_chat_id=form.creator_chat_id,
                resume=resume,
                github_username=form.github_username,
                architecture_seed={
                    "display_name": form.display_name,
                    "brief": form.brief,
                    "tech_stack": form.tech_stack,
                },
            )
            try:
                result = self._project_bootstrap_service.run(req)
            except ValidationError as exc:
                self.gateway.send_text(
                    form.creator_chat_id, f"Bootstrap 校验失败：{exc}",
                )
                return 200, {"toast": {"type": "error", "content": str(exc)}}
            except BootstrapStepError as exc:
                self.gateway.send_text(
                    form.creator_chat_id,
                    (
                        f"Bootstrap 中断于 Step {int(exc.step)} ({exc.step.name})：{exc.message}\n"
                        f"请重新 `/create project`，填同样的项目代号即可自动续跑。"
                    ),
                )
                return 200, {"toast": {"type": "error", "content": f"Bootstrap 失败：Step {exc.step.name}"}}
            self._save_state()
            self.gateway.send_text(
                form.creator_chat_id,
                (
                    f"项目 {result.project} 已就绪：\n"
                    f"- Repo: {result.github_repo_url}\n"
                    f"- ARCHITECTURE: {result.architecture_doc_url}\n"
                    f"- 群 chat_id: {result.feishu_chat_id}\n"
                    f"可开始用 `/create req` 创建需求。"
                ),
            )
            return 200, {"toast": {"type": "success", "content": f"项目 {result.project} 已就绪。"}}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_service_app_card_submit_project.py -v`
Expected: 6 条全 PASS。

- [ ] **Step 5: 回归跑 Bootstrap 测试**

Run: `pytest tests/test_project_bootstrap_service.py tests/test_project_bootstrap_types.py tests/test_project_bootstrap_resume.py -v`
Expected: 现有 Bootstrap 测试 PASS。`architecture_seed` 新增字段默认为空 dict，不影响旧路径。

- [ ] **Step 6: Commit**

```bash
git add src/requirement_workflow_v12/service_app.py \
        src/requirement_workflow_v12/project_bootstrap/types.py \
        src/requirement_workflow_v12/project_bootstrap/service.py \
        tests/test_service_app_card_submit_project.py
git commit -m "feat(service-app): submit_create_project card-action branch

Handles project-card submits: validate form, check project_configs for
auto-resume vs PROVISIONED rejection, build BootstrapRequest with
architecture_seed from optional form fields, and invoke Bootstrap.
StepError replies mention the step name and point to /create project
for retry (auto-resume kicks in on same slug)."
```

---

## Task 12: 需求卡 project 字段改下拉 — 失败测试

**Files:**
- Create: `tests/test_service_app_card_submit_req.py`

- [ ] **Step 1: 写测试**

Create `tests/test_service_app_card_submit_req.py`：

```python
"""Tests for the refactored requirement creation card (project dropdown, no category)."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.service_app import (  # noqa: E402
    CoordinatorRuntimeApp,
    MessageContext,
    OutboundCard,
    OutboundMessage,
)
from requirement_workflow_v12.config import Settings  # noqa: E402
from requirement_workflow_v12.store import JsonStateStore  # noqa: E402
from requirement_workflow_v12.coordinator_service import CoordinatorService  # noqa: E402
from requirement_workflow_v12.project_config import ProjectConfig  # noqa: E402


def _provisioned(category="saas-ai-automation"):
    return ProjectConfig(
        category=category,
        template_version="x.v1",
        architecture_doc_id="d",
        architecture_doc_url="u",
        bootstrap_status="PROVISIONED",
        project_status="PROVISIONED",
    )


def _bootstrapping():
    return ProjectConfig(
        category="saas-ai-automation",
        template_version="x.v1",
        architecture_doc_id="",
        architecture_doc_url="",
        bootstrap_status="BOOTSTRAPPING",
        project_status="BOOTSTRAPPING",
    )


def _make_app(tmp_path, project_configs):
    settings = MagicMock(spec=Settings)
    settings.state_store_path = str(tmp_path / "state.json")
    settings.creation_group_chat_id = "group_c"
    settings.openclaw_callback_secret = ""
    settings.openclaw_callback_ttl_seconds = 600
    settings.github_token = ""
    settings.feishu_user_id_type = "open_id"
    settings.github_template_owner = "Snowziio"
    settings.github_template_repo = "Template-repository"
    settings.github_org_owner = "Snowziio"
    service = CoordinatorService()
    store = JsonStateStore(settings.state_store_path)
    gateway = MagicMock()
    gateway.list_project_configs.return_value = project_configs
    with patch.object(Settings, "validate_runtime", return_value=None):
        settings.validate_runtime = lambda: None
        app = CoordinatorRuntimeApp(
            settings=settings, store=store, service=service, gateway=gateway,
        )
    return app


def test_req_card_project_is_select_static_with_provisioned_options(tmp_path):
    app = _make_app(tmp_path, {
        "test3": _provisioned(),
        "test4": _provisioned(),
        "test_bootstrapping": _bootstrapping(),
    })
    ctx = MessageContext(
        message_id="m1", chat_id="oc_x", chat_type="p2p",
        user_id="ou_alice", sender_name="Alice", text="/create req",
    )
    card = app._build_requirement_creation_card(ctx)
    form = card["body"]["elements"][0]
    project_field = next(e for e in form["elements"] if e.get("name") == "project")
    assert project_field["tag"] == "select_static"
    option_values = {o["value"] for o in project_field["options"]}
    # Only PROVISIONED projects listed
    assert option_values == {"test3", "test4"}


def test_req_card_omits_category_field(tmp_path):
    app = _make_app(tmp_path, {"test3": _provisioned()})
    ctx = MessageContext(
        message_id="m1", chat_id="oc_x", chat_type="p2p",
        user_id="ou_alice", sender_name="Alice", text="/create req",
    )
    card = app._build_requirement_creation_card(ctx)
    form = card["body"]["elements"][0]
    names = [e.get("name") for e in form["elements"] if isinstance(e, dict)]
    assert "category" not in names


def test_create_req_with_no_provisioned_projects_rejects_without_card(tmp_path):
    app = _make_app(tmp_path, {})
    ctx = MessageContext(
        message_id="m1", chat_id="oc_x", chat_type="p2p",
        user_id="ou_alice", sender_name="Alice", text="/create req",
    )
    msgs = app.handle_text_message(ctx)
    # Only a text reply, no card
    assert all(not isinstance(m, OutboundCard) for m in msgs)
    text = "\n".join(getattr(m, "text", "") for m in msgs if isinstance(m, OutboundMessage))
    assert "/create project" in text


def test_create_req_with_only_bootstrapping_project_rejects_without_card(tmp_path):
    app = _make_app(tmp_path, {"test_bb": _bootstrapping()})
    ctx = MessageContext(
        message_id="m1", chat_id="oc_x", chat_type="p2p",
        user_id="ou_alice", sender_name="Alice", text="/create req",
    )
    msgs = app.handle_text_message(ctx)
    assert all(not isinstance(m, OutboundCard) for m in msgs)


def test_submit_requirement_rejects_bootstrapping_project(tmp_path):
    """If the selected project's status regressed to non-PROVISIONED, reject the submit."""
    app = _make_app(tmp_path, {"test_bb": _bootstrapping()})
    payload = {
        "operator": {"open_id": "ou_alice", "name": "Alice"},
        "context": {"open_chat_id": "oc_x", "open_message_id": "om_1"},
        "action": {
            "value": {"action": "submit_create_requirement", "creation_chat_id": "oc_x"},
            "form_value": {
                "project": "test_bb",
                "name": "some req",
                "summary": "some summary",
            },
        },
    }
    status, resp = app._handle_card_action_payload(payload)
    assert status == 200
    assert resp.get("toast", {}).get("type") == "error"
    # No requirement was created
    assert len(app.service.requirements) == 0
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_service_app_card_submit_req.py -v`
Expected: FAIL — `project` 字段目前是 `input`（不是 `select_static`），`category` 仍在，无 PROVISIONED 项目时仍然发卡。

---

## Task 13: 需求卡改造 + `_handle_create_req_command` 重写 — 实现

**Files:**
- Modify: `src/requirement_workflow_v12/service_app.py`
- Modify: `src/requirement_workflow_v12/protocols.py`

- [ ] **Step 1: 改 `_build_requirement_creation_card`**

把 `service_app.py:1763-1914` 的方法整体替换为（主要改动：project → select_static，删 category select 和它上面那段说明 div）：

```python
    def _build_requirement_creation_card(self, context: MessageContext) -> dict[str, object]:
        provisioned_projects = sorted(
            name for name, cfg in self.service.project_configs.items()
            if cfg.bootstrap_status == "PROVISIONED"
        )
        project_options = [
            {"text": {"tag": "plain_text", "content": name}, "value": name}
            for name in provisioned_projects
        ]
        return {
            "schema": "2.0",
            "config": {"wide_screen_mode": True},
            "header": {
                "template": "blue",
                "title": {"tag": "plain_text", "content": "新建需求"},
                "subtitle": {"tag": "plain_text", "content": "提交后自动生成 REQ ID · 创建文档 · 写入表格 · 通知项目群"},
            },
            "body": {
                "elements": [
                    {
                        "tag": "form",
                        "name": "requirement_create_form",
                        "elements": [
                            {
                                "tag": "select_static",
                                "name": "project",
                                "required": True,
                                "width": "fill",
                                "label": {"tag": "plain_text", "content": "项目（必填）"},
                                "placeholder": {"tag": "plain_text", "content": "选择已就绪的项目"},
                                "options": project_options,
                            },
                            {
                                "tag": "input",
                                "name": "name",
                                "required": True,
                                "width": "fill",
                                "label": {"tag": "plain_text", "content": "需求名称"},
                                "placeholder": {"tag": "plain_text", "content": "例如 多轮需求构造工作流"},
                            },
                            {
                                "tag": "input",
                                "name": "summary",
                                "required": True,
                                "width": "fill",
                                "input_type": "multiline_text",
                                "max_length": 500,
                                "label": {"tag": "plain_text", "content": "需求简述"},
                                "placeholder": {"tag": "plain_text", "content": "要解决什么问题，期望得到什么结果"},
                            },
                            {
                                "tag": "input",
                                "name": "background_links",
                                "width": "fill",
                                "input_type": "multiline_text",
                                "max_length": 1000,
                                "label": {"tag": "plain_text", "content": "背景材料链接（选填）"},
                                "placeholder": {"tag": "plain_text", "content": "多个链接请换行"},
                            },
                            {
                                "tag": "column_set",
                                "horizontal_spacing": "8px",
                                "columns": [
                                    {
                                        "tag": "column",
                                        "width": "weighted",
                                        "weight": 1,
                                        "elements": [
                                            {"tag": "div", "text": {"tag": "plain_text", "content": "优先级"}},
                                            {
                                                "tag": "select_static",
                                                "name": "priority",
                                                "placeholder": {"tag": "plain_text", "content": "选填"},
                                                "options": [
                                                    {"text": {"tag": "plain_text", "content": "P0 紧急"}, "value": "P0"},
                                                    {"text": {"tag": "plain_text", "content": "P1 高"}, "value": "P1"},
                                                    {"text": {"tag": "plain_text", "content": "P2 普通"}, "value": "P2"},
                                                ],
                                            },
                                        ],
                                    },
                                    {
                                        "tag": "column",
                                        "width": "weighted",
                                        "weight": 1,
                                        "elements": [
                                            {"tag": "div", "text": {"tag": "plain_text", "content": "期望完成时间"}},
                                            {
                                                "tag": "date_picker",
                                                "name": "expected_due_date",
                                                "placeholder": {"tag": "plain_text", "content": "选填"},
                                            },
                                        ],
                                    },
                                    {
                                        "tag": "column",
                                        "width": "weighted",
                                        "weight": 1,
                                        "elements": [
                                            {"tag": "div", "text": {"tag": "plain_text", "content": "需要 UI 设计"}},
                                            {
                                                "tag": "select_static",
                                                "name": "needs_ui",
                                                "placeholder": {"tag": "plain_text", "content": "选填"},
                                                "options": [
                                                    {"text": {"tag": "plain_text", "content": "是"}, "value": "yes"},
                                                    {"text": {"tag": "plain_text", "content": "否"}, "value": "no"},
                                                ],
                                            },
                                        ],
                                    },
                                ],
                            },
                            {
                                "tag": "button",
                                "name": "submit_create_requirement",
                                "text": {"tag": "plain_text", "content": "提交"},
                                "type": "primary_filled",
                                "form_action_type": "submit",
                                "behaviors": [
                                    {
                                        "type": "callback",
                                        "value": {
                                            "action": "submit_create_requirement",
                                            "creation_chat_id": context.chat_id,
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                ]
            },
        }
```

- [ ] **Step 2: 重写 `_handle_create_req_command`**

把 `service_app.py:448-491` 的旧实现（整段）**替换**为：

```python
    def _handle_create_req_command(
        self, cmd: "CreateReqCommand", context: MessageContext,
    ) -> list[OutboundMessage | OutboundCard]:
        provisioned = [
            name for name, cfg in self.service.project_configs.items()
            if cfg.bootstrap_status == "PROVISIONED"
        ]
        if not provisioned:
            return [OutboundMessage(
                receive_id=context.chat_id,
                text="尚无已注册（PROVISIONED）的项目，请先 `/create project`。",
            )]
        return [OutboundCard(
            receive_id=context.chat_id,
            card=self._build_requirement_creation_card(context),
        )]
```

- [ ] **Step 3: 改 `_extract_creation_form_payload` 删 category**

把 `service_app.py:1626-1661` 的 `_extract_creation_form_payload` 方法替换为（删 `category` 字段读取 + 从 `CreationFormPayload` 构造里移除）：

```python
    def _extract_creation_form_payload(
        self,
        payload: dict[str, object],
        *,
        user_id: str,
        user_name: str,
    ) -> CreationFormPayload | None:
        action = payload.get("action", {}) or {}
        value = self._extract_callback_value(action)
        form_value = action.get("form_value") or payload.get("form_value") or {}
        if not isinstance(form_value, dict):
            form_value = {}

        project = self._normalize_form_value(form_value.get("project"))
        name = self._normalize_form_value(form_value.get("name"))
        summary = self._normalize_form_value(form_value.get("summary"))
        if not project or not name or not summary:
            return None

        creation_chat_id = (
            self._normalize_form_value(value.get("creation_chat_id"))
            or self._observed_creation_group_chat_id
        )
        needs_ui_raw = self._normalize_form_value(form_value.get("needs_ui")).lower()
        needs_ui = needs_ui_raw in ("yes", "true", "1", "是", "需要")
        return CreationFormPayload(
            project=project,
            name=name,
            summary=summary,
            creator=user_name or user_id,
            creator_user_id=user_id,
            creation_chat_id=creation_chat_id,
            background_links=self._normalize_form_value(form_value.get("background_links")),
            priority=self._normalize_form_value(form_value.get("priority")),
            expected_due_date=self._normalize_form_value(form_value.get("expected_due_date")),
            needs_ui=needs_ui,
        )
```

- [ ] **Step 4: 从 `CreationFormPayload` dataclass 里删 category**

`src/requirement_workflow_v12/protocols.py` 里 `CreationFormPayload` 的字段清单（约 line 39-50）删掉最后一行 `category: str = ""`：

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
```

- [ ] **Step 5: 清理其他 `category` 引用**

跑 `grep -n "CreationFormPayload\|\.category\b\|form_payload\.category" src/requirement_workflow_v12/service_app.py` 找到剩余引用：

- `service_app.py:610-614` 有一段 `form_payload.category` 比对逻辑，整段删掉（不再有 category 可比对）。
- `_handle_create_req_command` 旧版里 `cmd.category` 的用法在 Step 2 替换时已一起删除。
- 搜索测试目录：`grep -rn "CreationFormPayload" tests/ | grep category` 确认不再有 test 用 category 字段构造。

- [ ] **Step 6: 在 `submit_create_requirement` 分支里加 status 校验**

找到 `_handle_card_action_payload` 里 `submit_create_requirement` 分支（约 line 1462），在 `form_payload = ...` 下面加：

```python
            if action_name == "submit_create_requirement":
                form_payload = self._extract_creation_form_payload(payload, user_id=user_id, user_name=user_name)
                if form_payload is None:
                    return 200, {"toast": {"type": "error", "content": "创建表单字段不完整，请补充项目、名称和简述。"}}
                project_cfg = self.service.project_configs.get(form_payload.project)
                if project_cfg is None or project_cfg.bootstrap_status != "PROVISIONED":
                    status_label = project_cfg.bootstrap_status if project_cfg else "不存在"
                    return 200, {"toast": {"type": "error", "content": f"项目 {form_payload.project} 当前状态 {status_label}，无法新建需求。"}}
                request, _, req_id = self._create_requirement_from_form(form_payload)
                ...
```

其余 `threading.Thread(...)` / `return 200, {"toast": ...}` 保持不变。

- [ ] **Step 7: 跑测试确认通过**

Run: `pytest tests/test_service_app_card_submit_req.py -v`
Expected: 5 条全 PASS。

- [ ] **Step 8: Commit**

```bash
git add src/requirement_workflow_v12/service_app.py \
        src/requirement_workflow_v12/protocols.py \
        tests/test_service_app_card_submit_req.py
git commit -m "feat(service-app): req card uses project dropdown, no category

- _build_requirement_creation_card now renders project as select_static
  populated from PROVISIONED project_configs; category field removed
- /create req with no PROVISIONED projects replies 'use /create project'
  instead of sending an empty dropdown
- submit_create_requirement now validates project's bootstrap_status
  before accepting the submit
- CreationFormPayload drops the category field (project-level decision)"
```

---

## Task 14: 卡片回调去重 — 失败测试

**Files:**
- Create: `tests/test_card_dedupe.py`

- [ ] **Step 1: 写测试**

Create `tests/test_card_dedupe.py`：

```python
"""Tests for card-action callback dedupe (_seen_card_action_ids)."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.service_app import CoordinatorRuntimeApp  # noqa: E402
from requirement_workflow_v12.config import Settings  # noqa: E402
from requirement_workflow_v12.store import JsonStateStore  # noqa: E402
from requirement_workflow_v12.coordinator_service import CoordinatorService  # noqa: E402
from requirement_workflow_v12.project_bootstrap.types import BootstrapResult  # noqa: E402


def _make_app(tmp_path):
    settings = MagicMock(spec=Settings)
    settings.state_store_path = str(tmp_path / "state.json")
    settings.creation_group_chat_id = "group_c"
    settings.openclaw_callback_secret = ""
    settings.openclaw_callback_ttl_seconds = 600
    settings.github_token = ""
    settings.feishu_user_id_type = "open_id"
    settings.github_template_owner = "Snowziio"
    settings.github_template_repo = "Template-repository"
    settings.github_org_owner = "Snowziio"
    bootstrap_svc = MagicMock()
    bootstrap_svc.run.return_value = BootstrapResult(
        project="test5",
        github_repo_url="u", architecture_doc_id="d", architecture_doc_url="ud",
        feishu_chat_id="oc", template_version="x.v1",
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
    return app, bootstrap_svc


def test_mark_card_action_seen_returns_true_then_false():
    # Method-level unit test: helper is bounded LRU, first sight is True
    from requirement_workflow_v12.service_app import CoordinatorRuntimeApp
    app = CoordinatorRuntimeApp.__new__(CoordinatorRuntimeApp)
    import collections
    app._seen_card_action_ids = collections.OrderedDict()
    app._seen_card_action_ids_max = 3
    assert app._mark_card_action_seen("om_1", "submit_create_project") is True
    assert app._mark_card_action_seen("om_1", "submit_create_project") is False
    # distinct message → new
    assert app._mark_card_action_seen("om_2", "submit_create_project") is True
    # distinct action on same message → new
    assert app._mark_card_action_seen("om_1", "human_confirm_yes") is True


def test_mark_card_action_seen_bounded_lru():
    from requirement_workflow_v12.service_app import CoordinatorRuntimeApp
    import collections
    app = CoordinatorRuntimeApp.__new__(CoordinatorRuntimeApp)
    app._seen_card_action_ids = collections.OrderedDict()
    app._seen_card_action_ids_max = 2
    app._mark_card_action_seen("a", "x")
    app._mark_card_action_seen("b", "x")
    app._mark_card_action_seen("c", "x")  # evicts ('a','x')
    # ('a','x') was evicted → looks new again
    assert app._mark_card_action_seen("a", "x") is True


def test_handle_card_action_dedupes_same_payload_twice(tmp_path):
    app, bootstrap_svc = _make_app(tmp_path)
    payload = {
        "operator": {"open_id": "ou_alice", "name": "Alice"},
        "context": {"open_chat_id": "oc_x", "open_message_id": "om_card_99"},
        "action": {
            "value": {"action": "submit_create_project", "creator_chat_id": "oc_x"},
            "form_value": {
                "project": "test5",
                "category": "saas-ai-automation",
                "display_name": "", "brief": "", "github_username": "", "tech_stack": "",
            },
        },
    }
    app._handle_card_action_payload(payload)
    app._handle_card_action_payload(payload)
    # Bootstrap must have been called ONLY once despite two identical callbacks
    bootstrap_svc.run.assert_called_once()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_card_dedupe.py -v`
Expected: FAIL — `AttributeError: ... has no attribute '_mark_card_action_seen'`。

---

## Task 15: 卡片回调去重 — 实现

**Files:**
- Modify: `src/requirement_workflow_v12/service_app.py`

- [ ] **Step 1: 在 `__init__` 里加 LRU 容器**

在 `CoordinatorRuntimeApp.__init__` 里（紧接 `self._seen_message_ids_max = 1024` 后面，约 line 226）追加：

```python
        # Feishu can re-deliver the same card action (at-least-once) — dedupe
        # by (open_message_id, action_name). Same structure as _seen_message_ids.
        self._seen_card_action_ids: collections.OrderedDict[tuple[str, str], None] = collections.OrderedDict()
        self._seen_card_action_ids_max = 1024
```

- [ ] **Step 2: 加 `_mark_card_action_seen` 辅助方法**

在 `_mark_message_seen` 方法（约 line 386）**之后**插入：

```python
    def _mark_card_action_seen(self, open_message_id: str, action_name: str) -> bool:
        """Returns True if (message_id, action) is new; False if already seen."""
        key = (open_message_id, action_name)
        if key in self._seen_card_action_ids:
            return False
        self._seen_card_action_ids[key] = None
        while len(self._seen_card_action_ids) > self._seen_card_action_ids_max:
            self._seen_card_action_ids.popitem(last=False)
        return True
```

- [ ] **Step 3: 在 `_handle_card_action_payload` 入口加去重**

在 `_handle_card_action_payload` 方法（约 line 1449）前面几行里，紧接 `action_name = value.get("action")`（约 line 1457）**之后**插入：

```python
        context = payload.get("context", {}) or {}
        open_message_id = context.get("open_message_id", "") or ""
        if open_message_id and action_name and not self._mark_card_action_seen(open_message_id, str(action_name)):
            LOGGER.info(
                "Dropping duplicate card action open_message_id=%s action=%s",
                open_message_id, action_name,
            )
            return 200, {"toast": {"type": "info", "content": "已处理，跳过重复回调。"}}
```

（注意：下面已有一处 `operator = payload.get("operator", {}) or {}`，不要重复声明 context。如果已经有 `context = ...` 那行，就别再加。）

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_card_dedupe.py -v`
Expected: 3 条全 PASS。

- [ ] **Step 5: 回归跑全部 card 相关测试**

Run: `pytest tests/test_service_app_card_submit_project.py tests/test_service_app_card_submit_req.py tests/test_card_dedupe.py tests/test_project_creation_card.py -v`
Expected: 全部 PASS。

- [ ] **Step 6: Commit**

```bash
git add src/requirement_workflow_v12/service_app.py tests/test_card_dedupe.py
git commit -m "feat(service-app): dedupe card-action callbacks by open_message_id+action

Feishu delivers card actions at-least-once. Paired with the new
submit_create_project branch (non-idempotent from the user's
perspective — duplicate Bootstrap runs send confusing messages),
re-deliveries need rejecting at the edge. Bounded OrderedDict LRU
capped at 1024 entries, same pattern as _seen_message_ids."
```

---

## Task 16: 清理 creation-group 旧引导文案

**Files:**
- Modify: `src/requirement_workflow_v12/service_app.py`

- [ ] **Step 1: 更新 `_handle_creation_group_message` 文案**

把 `service_app.py:435-446` 里「创建需求」「新建需求」关键字响应的旧引导文本：

```python
            return [OutboundMessage(
                receive_id=context.chat_id,
                text=(
                    "REQ 创建已改用固化命令：\n"
                    "`/create req <project> <name>` （可选 --summary / --category）\n"
                    "示例：`/create req test3 会话鉴权改造 --summary \"支持JWT\"`"
                ),
            )]
```

替换为：

```python
            return [OutboundMessage(
                receive_id=context.chat_id,
                text=(
                    "REQ 创建已改用卡片：\n"
                    "直接发送 `/create req`，在弹出的卡片里选项目、填名称和简述。"
                ),
            )]
```

- [ ] **Step 2: 跑全部 service_app 相关测试**

Run: `pytest tests/ -k "service_app" -v`
Expected: 全部 PASS。

- [ ] **Step 3: Commit**

```bash
git add src/requirement_workflow_v12/service_app.py
git commit -m "docs(service-app): point creation-group hint to the new /create req card"
```

---

## Task 17: 全量回归与冒烟准备

**Files:** 无改动，仅验证。

- [ ] **Step 1: 跑整个测试库**

Run: `pytest -q`
Expected: 全部测试 PASS（预期数量比之前多出约 20 条：新增的 card / dedupe / seed 相关）。

- [ ] **Step 2: 关键 grep 检查**

Run: `grep -nE "\-\-category|\-\-owner|\-\-resume|\-\-summary" src/requirement_workflow_v12/service_app.py`
Expected: 无输出（旧 CLI flag 路径已彻底删除）。

Run: `grep -n "category" src/requirement_workflow_v12/protocols.py`
Expected: 无输出。

Run: `grep -nE "\{\{display_name\}\}|\{\{brief\}\}|\{\{tech_stack\}\}" docs/context/architecture-templates/*.yaml | wc -l`
Expected: `15`（5 个模板 × 3 个占位符）。

- [ ] **Step 3: 本地手动校验卡片 JSON 能被飞书渲染**

在 REPL 或小脚本中：

```python
from requirement_workflow_v12.service_app import CoordinatorRuntimeApp, MessageContext
# Use the test helper from tests/test_project_creation_card.py::_make_app
# or construct one manually; then:
import json
ctx = MessageContext(message_id="m", chat_id="oc", chat_type="p2p",
                     user_id="ou", sender_name="n", text="/create project")
print(json.dumps(app._build_project_creation_card(ctx), ensure_ascii=False, indent=2)[:1000])
```

Expected: 合法 JSON，顶层有 `schema`, `body.elements[0].tag == "form"`，表单字段名清单完整。

- [ ] **Step 4: Commit final（若 Step 2 发现残留 flag 或 category 字段则先修）**

```bash
git status
# 若仍有未提交 diff：
git add -A
git commit -m "chore: final cleanup after /create card-flow rollout"
```

---

## Task 18: 冒烟验证清单（部署后人工执行）

**Files:** 无代码改动。由用户在 staging / production 手工执行。

- [ ] **Step 1: 部署 staging**

按项目现有部署流程（通常是 `sync-project-configs-schema` 等 workflow）触发 staging redeploy。

- [ ] **Step 2: `/create project` 首次流**

1. 在任意 chat（DM 或群）里发 `/create project`。
2. 期望：机器人回一张「新建项目」卡片，带必填 project / category 字段和 4 个可选字段。
3. 在卡里填 `test5` + `saas-ai-automation` + 显示名 / 简述 / tech stack，提交。
4. 期望：Bootstrap 跑完，回一条「项目 test5 已就绪」文本消息，包含 github_repo_url、architecture_doc_url、feishu_chat_id。
5. 检查 `docs/ARCHITECTURE.md` 在 Snowziio/test5 里是否正确渲染了 `display_name` / `brief` / `tech_stack_notes` 字段。

- [ ] **Step 3: 同项目重复提交（BOOTSTRAPPING → resume）**

1. 模拟 Step 4 在 create_feishu_group 阶段出错（例如临时撤销 bot 权限后再恢复）。
2. 再次 `/create project`，填同样的 `test5` / `saas-ai-automation` 提交。
3. 期望：resume=True 静默续跑，仍得到成功消息。

- [ ] **Step 4: 已 PROVISIONED 项目重复提交（拒绝）**

1. 在 Step 2 成功后再 `/create project`，填 `test5`。
2. 期望：文本消息「项目 test5 已经完成 Bootstrap，请用 `/create req` 创建需求。」

- [ ] **Step 5: `/create req` 流**

1. 发 `/create req`。
2. 期望：卡片出现，project 字段是下拉，选项里能看到 `test5`（以及之前 PROVISIONED 的 test3/test4）。
3. 选 `test5` + 填名称 / 简述，提交。
4. 期望：toast 成功；几秒后 bitable 新增记录，project 群里新增 REQ 消息，req-registry.yaml 有新条目。

- [ ] **Step 6: `/create` 无参提示**

1. 发 `/create`。
2. 期望：文本「请用 `/create project` 或 `/create req`」。

- [ ] **Step 7: 把冒烟结果更新到 memory**

如果 Step 2-6 全通过，把本次 card-flow 功能从「pending」挪到「landed」（用户侧在 MEMORY 里 / 项目 notes 里记一笔）。

---

## Self-Review 摘要

本计划已覆盖 spec 所有章节：

**§1 架构与数据流**
- 入口正则收紧 → Task 5、6
- 项目卡 / 需求卡构造 → Task 8、13
- submit 处理 → Task 11、13
- render_template seed → Task 3

**§2 错误处理 & 边界**
- 必填校验 → Task 8 (extractor) / Task 11 (handler)
- 项目代号正则 → Task 11 Step 3
- 已 PROVISIONED 拒绝 / resume=True → Task 11 Step 3
- BootstrapStepError 文案 → Task 11 Step 3
- 需求卡 status 校验 → Task 13 Step 6
- 无 PROVISIONED 项目直接回文本 → Task 13 Step 2
- 幂等：`_seen_card_action_ids` → Task 14、15

**§3 测试 & 交付**
- `test_project_creation_card.py` → Task 7
- `test_service_app_card_submit_project.py` → Task 10
- `test_service_app_card_submit_req.py` → Task 12
- 改造 `test_service_app_slash_create_project.py` → Task 4、9
- 改造 `test_service_app_slash_create_req.py` → Task 6
- `test_card_dedupe.py` → Task 14
- ARCHITECTURE 模板占位 → Task 3 Step 2
- 冒烟清单 → Task 18
