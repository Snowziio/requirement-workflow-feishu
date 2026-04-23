# design-brief-author Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the OpenClaw `design-brief-author` single-turn skill per `docs/superpowers/specs/2026-04-23-design-brief-author-skill-design.md`: SKILL.md + callback-schema.json (canonical skill files), the 6-file agent workspace under `deploy/openclaw/workspace/agents/design-brief-author/`, model config template, `sync_openclaw_server.sh` registration, and a coordinator-side handoff DM sender that triggers the skill after `design_start`.

**Architecture:** Mirror existing single-turn skills (`spec-transformer` pattern): YAML frontmatter SKILL.md + callback-schema.json at `docs/agents/`, symlinked into `deploy/openclaw/workspace/agents/` alongside boilerplate SOUL/AGENTS/TOOLS/USER. Coordinator's `dispatch_design_start_if_needed` gets a new side-effect that DMs the REQ creator with a handoff text the user forwards to the skill. No Python in the skill itself — skill is pure markdown instructions executed by OpenClaw's Claude Agent.

**Tech Stack:** Markdown + YAML + JSON Schema (draft-07) for skill artifacts; Python 3.11 + pytest + MagicMock for coordinator handoff + static validation tests; bash for sync script update.

**Reference:**
- Spec: `docs/superpowers/specs/2026-04-23-design-brief-author-skill-design.md`
- Pattern to mirror: `docs/agents/spec-transformer/SKILL.md` + `deploy/openclaw/workspace/agents/spec-transformer/`
- Related: `docs/agents/plan-author/SKILL.md` for "行为合同" pattern; `docs/agents/plan-author/callback-schema.json` for schema style

---

## Pre-flight

- [ ] `python3 -m pytest tests/ --ignore=tests/test_concurrent_spec_gate.py -q 2>&1 | tail -3` — green baseline (~603 pass, 8 pre-existing fails, 1 collection error).
- [ ] Read spec cover-to-cover.
- [ ] `cat docs/agents/spec-transformer/SKILL.md docs/agents/spec-transformer/callback-schema.json deploy/openclaw/workspace/agents/spec-transformer/*.md | less` to familiarize with existing skill structure.
- [ ] `git checkout -b feat/design-brief-author-skill` — new feature branch.

---

## File Structure

**New files:**
- `docs/agents/design-brief-author/SKILL.md` — canonical skill instructions
- `docs/agents/design-brief-author/callback-schema.json` — JSON schema draft-07
- `deploy/openclaw/workspace/agents/design-brief-author/SKILL.md` — symlink to canonical
- `deploy/openclaw/workspace/agents/design-brief-author/IDENTITY.md` — 6-line per-agent card
- `deploy/openclaw/workspace/agents/design-brief-author/SOUL.md` — copy from spec-transformer
- `deploy/openclaw/workspace/agents/design-brief-author/AGENTS.md` — copy from spec-transformer
- `deploy/openclaw/workspace/agents/design-brief-author/TOOLS.md` — copy from spec-transformer
- `deploy/openclaw/workspace/agents/design-brief-author/USER.md` — copy from spec-transformer
- `deploy/openclaw/agents/design-brief-author/models.json.template` — copy from spec-transformer
- `tests/test_agents_design_brief_author_skill.py` — SKILL.md + schema validation
- `tests/test_agents_design_brief_author_workspace.py` — deploy workspace structure check
- `tests/test_design_brief_handoff_dm.py` — coordinator handoff DM unit tests

**Modified files:**
- `src/requirement_workflow_v12/service_app.py` — add `_build_design_brief_author_handoff_text` + `_send_design_brief_author_handoff` + wire into `dispatch_design_start_if_needed`
- `scripts/sync_openclaw_server.sh` — add `design-brief-author` to AGENTS array + skill_for_agent case
- `deploy/openclaw/README.md` — agent id ↔ skill name table gains one row
- `README.md` — 当前已实现 / 仍待补齐 / 联调参考 sections

---

## Task 1: Create SKILL.md + callback-schema.json

**Files:**
- Create: `docs/agents/design-brief-author/SKILL.md`
- Create: `docs/agents/design-brief-author/callback-schema.json`
- Test: `tests/test_agents_design_brief_author_skill.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_agents_design_brief_author_skill.py`:

```python
"""Static validation for design-brief-author SKILL.md + callback schema."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = REPO_ROOT / "docs" / "agents" / "design-brief-author"


def test_skill_md_exists():
    assert (SKILL_DIR / "SKILL.md").is_file()


def test_skill_md_yaml_frontmatter_parses():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\n"), "SKILL.md must start with YAML frontmatter"
    end = text.index("\n---\n", 4)
    raw = text[4:end]
    fm = yaml.safe_load(raw)
    assert isinstance(fm, dict)
    assert fm["name"] == "design-brief-author"
    assert isinstance(fm.get("description"), str) and len(fm["description"]) > 20


def test_skill_md_has_hard_behavior_contract():
    """Mirror plan-author's '行为合同' pattern: first tool call must be the callback."""
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    assert "行为合同" in text
    # Must warn against fake 'generating...' toast before curl
    assert "curl" in text and "200" in text


def test_skill_md_mentions_single_turn():
    """Skill must explicitly state it's single-turn (no multi-turn dialogue)."""
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    assert "单轮" in text or "single-turn" in text.lower()


def test_skill_md_lists_design_context_endpoint():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    assert "/queries/openclaw/design-context/" in text


def test_skill_md_lists_design_callback_endpoint():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    assert "/openclaw/design-callback" in text
    assert "design_brief_submit" in text


def test_callback_schema_is_valid_draft07():
    schema_path = SKILL_DIR / "callback-schema.json"
    assert schema_path.is_file()
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert schema["$schema"] == "http://json-schema.org/draft-07/schema#"
    assert schema["title"]


def test_callback_schema_accepts_valid_payload():
    import jsonschema
    schema_path = SKILL_DIR / "callback-schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    valid = {
        "req_id": "REQ-TEST-001",
        "event": "design_brief_submit",
        "payload": {
            "brief_yaml_frontmatter": "schema_version: '1.0'\nreq_id: REQ-TEST-001\n",
            "brief_markdown_body": "# Brief\n\n## 背景\n...",
        },
    }
    jsonschema.validate(valid, schema)


def test_callback_schema_rejects_wrong_event():
    import jsonschema
    schema_path = SKILL_DIR / "callback-schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    invalid = {
        "req_id": "REQ-TEST-001",
        "event": "some_other_event",
        "payload": {
            "brief_yaml_frontmatter": "x",
            "brief_markdown_body": "y",
        },
    }
    import pytest
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(invalid, schema)


def test_callback_schema_rejects_empty_frontmatter():
    import jsonschema
    schema_path = SKILL_DIR / "callback-schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    invalid = {
        "req_id": "REQ-TEST-001",
        "event": "design_brief_submit",
        "payload": {
            "brief_yaml_frontmatter": "",
            "brief_markdown_body": "non-empty",
        },
    }
    import pytest
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(invalid, schema)


def test_callback_schema_rejects_wrong_req_id_prefix():
    import jsonschema
    schema_path = SKILL_DIR / "callback-schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    invalid = {
        "req_id": "NOTREQ-001",
        "event": "design_brief_submit",
        "payload": {
            "brief_yaml_frontmatter": "x",
            "brief_markdown_body": "y",
        },
    }
    import pytest
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(invalid, schema)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_agents_design_brief_author_skill.py -v
```
Expected: FAIL — SKILL_DIR doesn't exist yet. (If `jsonschema` not installed: `pip install --user jsonschema`.)

- [ ] **Step 3: Create callback-schema.json**

```bash
mkdir -p docs/agents/design-brief-author
```

Create `docs/agents/design-brief-author/callback-schema.json`:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "design-brief-author callback payload",
  "type": "object",
  "required": ["req_id", "event", "payload"],
  "additionalProperties": false,
  "properties": {
    "req_id": {
      "type": "string",
      "pattern": "^REQ-"
    },
    "event": {
      "const": "design_brief_submit"
    },
    "payload": {
      "type": "object",
      "required": ["brief_yaml_frontmatter", "brief_markdown_body"],
      "additionalProperties": false,
      "properties": {
        "brief_yaml_frontmatter": {
          "type": "string",
          "minLength": 1
        },
        "brief_markdown_body": {
          "type": "string",
          "minLength": 1
        }
      }
    }
  }
}
```

- [ ] **Step 4: Create SKILL.md**

Create `docs/agents/design-brief-author/SKILL.md`:

```markdown
---
name: design-brief-author
description: 设计 Brief 生成助手，APPROVED + needs_ui=true 的 REQ 进入 DESIGN_DRAFTING 后单轮生成 Brief。从 REQ 8 字段 + 项目上下文 + 现有 Page Registry 推断 expected_pages，产出 YAML+Markdown 双层 Brief，回写飞书 design docx + callback Coordinator。不做多轮对话，不替设计师拍板视觉决策。
---

# 设计 Brief 生成助手

## 存储模型

Brief 内容的**构造期 SOT 是飞书 design docx**（Coordinator 在 DESIGN_DRAFTING 开始时创建；本 skill 产出 Brief 文本后，Coordinator 通过 callback 写入 docx）。`DesignStatus → READY` 时 Coordinator 会把 Brief 归档到 GitHub `design/archive/<REQ>/BRIEF.md`。

**本 SKILL 不直接调用飞书 / GitHub**——只通过 coordinator 的 `/queries/openclaw/design-context/` 和 `/openclaw/design-callback` 端点与 Coordinator 交互；Coordinator 负责 docx 写入与后续归档。

## 启动流程

收到包含「请开始设计 Brief 生成 REQ-xxx」的消息时启动。**本 skill 是单轮批处理**（与 plan-author 的多轮不同）：拉一次 context → 一次 LLM 推理 → 一次 callback → 结束。

### Step 1：拉取 design-context（唯一合法入口）

```bash
curl -s "${COORDINATOR_BASE_URL:-http://127.0.0.1:8004}/queries/openclaw/design-context/{req_id}"
```

响应结构示例：

```json
{
  "req_id": "REQ-xxx",
  "project": "proj",
  "requirement_document_url": "https://...",
  "needs_ui": true,
  "claude_design_project_url": "https://claude.ai/design/p/abc",
  "frontend_subpath": "src/proj_webapp",
  "frontend_tech_stack": {
    "framework": "React 18 + TypeScript",
    "build": "Vite 5.x",
    "component_library": "shadcn/ui",
    "fonts": "IBM Plex (Sans/SC/Mono)"
  },
  "category": "enterprise-app",
  "architecture_doc_url": "https://...",
  "design_doc_id": "docx-xxx",
  "design_doc_url": "https://...",
  "current_pages": [],
  "prior_handoff_archive_ref": ""
}
```

非 200 或响应体缺关键字段 → 立即停止并报错。

**关于 `design_doc_url`**：本 REQ 的飞书 design docx，Coordinator 在 DRAFTING 启动时创建。这是设计师收到 Brief 后查看的 URL。若为空字符串，说明 folder_token 未配置或 REQ 是老数据，回用户「该 REQ 未创建飞书 design 文档，请检查 Coordinator 配置」。

**关于 `claude_design_project_url`**：跨 REQ 共享的 Claude Design Project 位置。若为空，Coordinator 懒检查应已在 `design_start` 前阻断本流程；防御性地：在 Brief 的首轮 Prompt 里显式提示"URL 未绑定，请先通过项目创建群的绑定卡填写"。

### Step 2：推断 expected_pages

根据 context 做内部 LLM 推理，**不发 IM，不问设计师**——你是单轮 skill，拿到 context 就自己推断。

推理硬约束：

1. `expected_pages[]` 必须非空。若从 `requirement_document_url` 看不出任何 UI 需求，说明 REQ 被错标 `needs_ui=true`，在 Brief 里写一条占位 page `display_name: "ReviewOrigin"`，`intent: "requirement 未声明具体 UI，请设计师确认是否确实需要 UI"`
2. 每个 page 必须包含：
   - `display_name`：PascalCase，稳定标识（例如 `AvatarUploadPage`）
   - `action`：`new` 或 `modify`
   - `existing_page_ref`：仅当 `action=modify` 时必填，值必须匹配 `current_pages[].display_name`
   - `intent`：1 句话业务意图
   - `key_interactions`：≥1 条交互事实
   - `must_cover_states`：≥1 个状态（如 `default` / `empty` / `error` / `loading` / `success`）
3. 若 `current_pages` 为空（v1 常态）→ 所有 pages 标 `action: new`
4. 若 `current_pages` 非空且 `display_name` 匹配 → `action: modify` + 填 `existing_page_ref`
5. `design_system_hints` 从 `frontend_tech_stack` 派生（≥2 条；典型：主色提示、字体提示）
6. 若 `prior_handoff_archive_ref` 非空 → `cross_req_references.prior_archive` 填它；`prior_summary` 暂留空字符串（v1 `prior_summary` 未由 coordinator 提供）

### Step 3：组装 Brief

#### `brief_yaml_frontmatter`（string）

```yaml
schema_version: "1.0"
req_id: "{req_id}"
generated_at: "{ISO8601 UTC}"
generated_by: "design-brief-author@1.0"

expected_pages:
  - display_name: "..."
    action: "new"                 # 或 "modify"
    # existing_page_ref: "..."    # 仅 modify 时
    intent: "..."
    key_interactions:
      - "..."
    must_cover_states: ["default"]
  # ... 更多 pages

design_system_hints:
  - "..."
  - "..."

cross_req_references:
  prior_archive: "{prior_handoff_archive_ref 或空串}"
  prior_summary: ""
```

#### `brief_markdown_body`（string）

```markdown
# Design Brief: {req_id}

## 背景

（来自 requirement_document_url 的 2-3 段自然语言摘要——你读 REQ docx 后自己提炼，不要直接贴原文）

## 本次需要交付的 pages

### 1. {display_name}（新增 / 修改）
- **意图**：{intent}
- **交互**：
  - {key_interactions[0]}
  - {key_interactions[1]}
- **状态覆盖**：{must_cover_states join ", "}

### 2. ...
...

## 设计系统约束

- {design_system_hints[0]}
- {design_system_hints[1]}

## 前一 REQ 上下文

（若 cross_req_references.prior_archive 非空，写一句："上一 REQ 的归档在 {path}，建议先去 Claude Design 点 Sync now 再开始。" 否则留空节或省略本节。）

---

## 首轮 Prompt（复制此段到 Claude Design chat）

> 我要在 {project} Claude Design Project 里做这次迭代。
>
> **现有 Project URL**：{claude_design_project_url}
>
> 本次涉及：
> - {expected_pages[0].action} {expected_pages[0].display_name}：{expected_pages[0].intent}
> - {expected_pages[1].action} {expected_pages[1].display_name}：{expected_pages[1].intent}
> - ...
>
> 设计约束：{design_system_hints join "; "}
>
> 请先确认你能看到现有 screens。然后逐页给我出设计，不要一次出全部。
```

### Step 4：回调 Coordinator（本轮第一个 tool call 就是它）

```bash
curl -s -X POST "${COORDINATOR_BASE_URL:-http://127.0.0.1:8004}/openclaw/design-callback" \
  -H "Content-Type: application/json" \
  -d "{\"req_id\": \"{req_id}\", \"event\": \"design_brief_submit\", \"payload\": {\"brief_yaml_frontmatter\": ${yaml_json_escaped}, \"brief_markdown_body\": ${md_json_escaped}}}"
```

### Step 5：只有 200 后才回 IM

```
✅ Brief 已提交到飞书 design 文档：{design_doc_url}
请到 Claude Design {claude_design_project_url} 复制文档末尾的"首轮 Prompt"开始作业。
```

## ⛔ 行为合同（违反 = 卡死流程）

本 skill 本轮的**第一个**（也是必做的）tool call 必须是 Step 4 的
`curl … /openclaw/design-callback`。在那个 curl 成功返回 **HTTP 200 之前**，你不能：

- 发 IM 说"Brief 生成中 / 已提交 / 正在写入 / 完成"——这些都是谎言
- 把 Brief 作为"预览"发给用户——用户会以为 callback 已走，实际没走
- 结束本轮 session

组装 Brief 是**内部思考**，不是用户可见输出。所有"结果性"文字只能出现在 curl 200 之后。

如果你正要输出"生成中…"字样但手里没有 200 响应，STOP——先去发 curl。

## 异常分支

**异常 1：design-context 404** → REQ 不存在或未到 DESIGN_DRAFTING。立即停止并报用户。

**异常 2：design-context 409（gate_failed / misconfigured）** → 读响应 message 转告用户，立即停止。

**异常 3：design-callback 409（invalid_state）** → 大概率 `design_status != DRAFTING`（被人工 /design restart 或竞态）。读响应 message 报错，不重试。

**异常 4：design-callback 500** → 重试一次；仍 500 则报错。

## 硬约束

- **单轮批处理**：拿到 context 就开干，不问设计师任何问题
- **不读飞书 / GitHub**：只通过 coordinator 端点
- **callback 200 之前不发 IM 结果性文字**（见"行为合同"）
- **expected_pages 非空**
- **首轮 Prompt 必须内嵌 claude_design_project_url**（跨 REQ 一致性的核心保障）

## 反模式

- ❌ 多轮和设计师讨论 expected_pages（单轮 skill，自己推断）
- ❌ 在 callback 之前 IM 发"Brief 生成中..."或把 Brief 预览贴出
- ❌ 跳过 design-context 直接读 requirement_document_url（skill 不应直接访问飞书）
- ❌ 把 brief_markdown_body 当成 IM 回复的正文（正确是 callback payload）
- ❌ 省略"首轮 Prompt"节（失去对 Claude Design Project 的锚定）
- ❌ `expected_pages` 为空且不加占位 page（下游 coordinator 会把空 Brief 写进 PAGES.yaml，污染数据）
```

- [ ] **Step 5: Install jsonschema if missing**

```bash
pip install --user jsonschema 2>&1 | tail -2
```

- [ ] **Step 6: Run test to verify it passes**

```bash
python3 -m pytest tests/test_agents_design_brief_author_skill.py -v
```
Expected: 11/11 pass.

- [ ] **Step 7: Full suite regression check**

```bash
python3 -m pytest tests/ --ignore=tests/test_concurrent_spec_gate.py -q 2>&1 | tail -3
```
Expected: baseline + 11 new passes, no new failures.

- [ ] **Step 8: Commit**

```bash
git add docs/agents/design-brief-author/ tests/test_agents_design_brief_author_skill.py
git commit -m "feat(design-brief-author): SKILL.md + callback schema"
```

---

## Task 2: Create deploy workspace (symlink + per-agent workspace files)

**Files:**
- Create symlink: `deploy/openclaw/workspace/agents/design-brief-author/SKILL.md` → `../../../../docs/agents/design-brief-author/SKILL.md`
- Create: `deploy/openclaw/workspace/agents/design-brief-author/IDENTITY.md`
- Copy: `deploy/openclaw/workspace/agents/design-brief-author/{SOUL,AGENTS,TOOLS,USER}.md` (from spec-transformer)
- Test: `tests/test_agents_design_brief_author_workspace.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_agents_design_brief_author_workspace.py`:

```python
"""Verify the deploy workspace for design-brief-author agent."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = REPO_ROOT / "deploy" / "openclaw" / "workspace" / "agents" / "design-brief-author"


def test_workspace_directory_exists():
    assert WORKSPACE.is_dir()


def test_skill_md_is_symlink_to_docs_agents():
    skill_path = WORKSPACE / "SKILL.md"
    assert skill_path.is_symlink(), "SKILL.md in workspace must be a symlink"
    target = os.readlink(skill_path)
    # Target should reference docs/agents/design-brief-author/SKILL.md
    assert "docs/agents/design-brief-author/SKILL.md" in target


def test_identity_md_exists_and_has_skill_name():
    identity = WORKSPACE / "IDENTITY.md"
    assert identity.is_file()
    text = identity.read_text(encoding="utf-8")
    assert "design-brief-author" in text
    # Should mention single-turn or 单轮
    assert "单轮" in text or "single-turn" in text.lower()


def test_boilerplate_files_exist():
    for name in ["SOUL.md", "AGENTS.md", "TOOLS.md", "USER.md"]:
        path = WORKSPACE / name
        assert path.is_file(), f"{name} missing from workspace"
        # Non-trivial content
        assert len(path.read_text(encoding="utf-8")) > 100, f"{name} too small"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_agents_design_brief_author_workspace.py -v
```
Expected: FAIL — directory doesn't exist.

- [ ] **Step 3: Create directory + symlink**

```bash
mkdir -p deploy/openclaw/workspace/agents/design-brief-author
cd deploy/openclaw/workspace/agents/design-brief-author
ln -s ../../../../docs/agents/design-brief-author/SKILL.md SKILL.md
ls -la SKILL.md  # verify symlink exists
cd "$OLDPWD"
```

- [ ] **Step 4: Create IDENTITY.md**

Create `deploy/openclaw/workspace/agents/design-brief-author/IDENTITY.md`:

```markdown
# 设计 Brief 生成助手

- 名称：设计 Brief 生成助手
- Emoji：🎨
- 角色：APPROVED + needs_ui=true REQ 进入 DESIGN_DRAFTING 时单轮生成 Brief。从 REQ 8 字段 + 项目上下文推断 expected_pages，回写飞书 design docx，不做多轮对话。
- 绑定账号：design-brief-author
```

- [ ] **Step 5: Copy boilerplate files from spec-transformer**

```bash
cp deploy/openclaw/workspace/agents/spec-transformer/SOUL.md \
   deploy/openclaw/workspace/agents/design-brief-author/SOUL.md

cp deploy/openclaw/workspace/agents/spec-transformer/AGENTS.md \
   deploy/openclaw/workspace/agents/design-brief-author/AGENTS.md

cp deploy/openclaw/workspace/agents/spec-transformer/TOOLS.md \
   deploy/openclaw/workspace/agents/design-brief-author/TOOLS.md

cp deploy/openclaw/workspace/agents/spec-transformer/USER.md \
   deploy/openclaw/workspace/agents/design-brief-author/USER.md
```

- [ ] **Step 6: Run test to verify it passes**

```bash
python3 -m pytest tests/test_agents_design_brief_author_workspace.py -v
```
Expected: 4/4 pass.

- [ ] **Step 7: Full suite regression check**

```bash
python3 -m pytest tests/ --ignore=tests/test_concurrent_spec_gate.py -q 2>&1 | tail -3
```

- [ ] **Step 8: Commit**

```bash
git add deploy/openclaw/workspace/agents/design-brief-author/ tests/test_agents_design_brief_author_workspace.py
git commit -m "feat(design-brief-author): deploy workspace (symlink + boilerplate + IDENTITY)"
```

---

## Task 3: models.json.template + sync script + README updates

**Files:**
- Copy: `deploy/openclaw/agents/design-brief-author/models.json.template`
- Modify: `scripts/sync_openclaw_server.sh`
- Modify: `deploy/openclaw/README.md`

- [ ] **Step 1: Write the test (append to workspace test file)**

Append to `tests/test_agents_design_brief_author_workspace.py`:

```python


def test_models_json_template_exists():
    path = REPO_ROOT / "deploy" / "openclaw" / "agents" / "design-brief-author" / "models.json.template"
    assert path.is_file()
    import json
    content = json.loads(path.read_text(encoding="utf-8"))
    # Must have providers key (same shape as other agents)
    assert "providers" in content


def test_sync_script_registers_design_brief_author():
    script = REPO_ROOT / "scripts" / "sync_openclaw_server.sh"
    assert script.is_file()
    text = script.read_text(encoding="utf-8")
    # Must be in the AGENTS array
    assert "design-brief-author" in text
    # Must be in the skill_for_agent case mapping
    assert "design-brief-author) echo design-brief-author" in text


def test_deploy_readme_lists_design_brief_author():
    readme = REPO_ROOT / "deploy" / "openclaw" / "README.md"
    assert readme.is_file()
    text = readme.read_text(encoding="utf-8")
    assert "design-brief-author" in text
```

- [ ] **Step 2: Run tests to see fail**

```bash
python3 -m pytest tests/test_agents_design_brief_author_workspace.py -v
```
Expected: 3 new tests FAIL.

- [ ] **Step 3: Copy models.json.template**

```bash
mkdir -p deploy/openclaw/agents/design-brief-author
cp deploy/openclaw/agents/spec-transformer/models.json.template \
   deploy/openclaw/agents/design-brief-author/models.json.template
```

- [ ] **Step 4: Update `scripts/sync_openclaw_server.sh`**

Open `scripts/sync_openclaw_server.sh`. Find the `AGENTS=(...)` line:

```bash
AGENTS=(ai-founder-brief ai-meeting-closeout plan-author spec-author spec-reviewer spec-transformer spec-transformer-reviewer)
```

Change to:

```bash
AGENTS=(ai-founder-brief ai-meeting-closeout plan-author spec-author spec-reviewer spec-transformer spec-transformer-reviewer design-brief-author)
```

Find the `skill_for_agent()` case block. After `spec-transformer-reviewer) echo spec-transformer-reviewer ;;` (or wherever the last entry is), add:

```bash
    design-brief-author) echo design-brief-author ;;
```

Use the Read tool to check the actual current structure of the case block before editing.

- [ ] **Step 5: Update `deploy/openclaw/README.md`**

Find the agent id ↔ skill name table (after "Agent id ↔ skill name:"). Add a row at the end:

```markdown
| `design-brief-author`       | `design-brief-author`      |
```

Also in the "## What's in this directory" doc comment (the code block showing structure), this pattern is already generic — no edit needed.

At the bottom in "## Out of scope" or similar section, add a note:

```markdown
As of 2026-04-23 the `design-brief-author` agent is registered here. See
`docs/superpowers/specs/2026-04-23-design-brief-author-skill-design.md` for
the skill's single-turn interaction model and `docs/agents/design-brief-author/`
for the canonical SKILL.md.
```

- [ ] **Step 6: Verify sync script syntax**

```bash
bash -n scripts/sync_openclaw_server.sh && echo "syntax OK"
```
Expected: `syntax OK`.

- [ ] **Step 7: Run tests**

```bash
python3 -m pytest tests/test_agents_design_brief_author_workspace.py -v
```
Expected: 7/7 pass.

- [ ] **Step 8: Full suite regression check**

```bash
python3 -m pytest tests/ --ignore=tests/test_concurrent_spec_gate.py -q 2>&1 | tail -3
```

- [ ] **Step 9: Commit**

```bash
git add deploy/openclaw/agents/design-brief-author/ scripts/sync_openclaw_server.sh deploy/openclaw/README.md tests/test_agents_design_brief_author_workspace.py
git commit -m "feat(design-brief-author): register agent in sync script + README + models config"
```

---

## Task 4: Coordinator — _build_design_brief_author_handoff_text helper

**Files:**
- Modify: `src/requirement_workflow_v12/service_app.py`
- Test: `tests/test_design_brief_handoff_dm.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_design_brief_handoff_dm.py`:

```python
"""Unit tests for design-brief-author handoff DM helpers."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.models import Requirement, WorkflowStatus


def _req(**kw) -> Requirement:
    defaults = dict(
        req_id="REQ-PROJ-007",
        name="头像审核",
        project="proj",
        summary="用户上传头像走审核",
        creator="u1",
        creator_user_id="ou_designer",
        status=WorkflowStatus.APPROVED,
        needs_ui=True,
    )
    defaults.update(kw)
    return Requirement(**defaults)


def test_build_handoff_text_contains_req_id_and_trigger_phrase():
    from requirement_workflow_v12.service_app import _build_design_brief_author_handoff_text
    text = _build_design_brief_author_handoff_text(_req())
    assert "REQ-PROJ-007" in text
    assert "请开始设计 Brief 生成" in text


def test_build_handoff_text_includes_coordinator_base_url_env():
    from requirement_workflow_v12.service_app import _build_design_brief_author_handoff_text
    with patch.dict(os.environ, {"COORDINATOR_BASE_URL": "https://staging.example.com"}):
        text = _build_design_brief_author_handoff_text(_req())
        assert "https://staging.example.com" in text


def test_build_handoff_text_has_default_base_url_when_env_missing():
    from requirement_workflow_v12.service_app import _build_design_brief_author_handoff_text
    # Clear env if present
    env = {k: v for k, v in os.environ.items() if k != "COORDINATOR_BASE_URL"}
    with patch.dict(os.environ, env, clear=True):
        text = _build_design_brief_author_handoff_text(_req())
        assert "COORDINATOR_BASE_URL=" in text
        # Should have a non-empty default (either 127.0.0.1 or some fallback)
        assert "http" in text


def test_build_handoff_text_instructs_to_forward():
    """Handoff text should tell the user to forward the message to the agent."""
    from requirement_workflow_v12.service_app import _build_design_brief_author_handoff_text
    text = _build_design_brief_author_handoff_text(_req())
    assert "design-brief-author" in text
    # Must clearly tell human what to do
    assert "转发" in text or "forward" in text.lower() or "粘贴" in text or "贴给" in text
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_design_brief_handoff_dm.py -v
```
Expected: FAIL — `_build_design_brief_author_handoff_text` doesn't exist.

- [ ] **Step 3: Add the helper to service_app.py**

Open `src/requirement_workflow_v12/service_app.py`. Verify `import os` is at top (it was added in previous rounds; if not, add it).

Find `dispatch_design_start_if_needed` (top-level function near the top of the file). AFTER that function, add:

```python
def _build_design_brief_author_handoff_text(requirement) -> str:
    """Handoff text the Coordinator DMs to the REQ creator after design_start.

    The user forwards/pastes this text to the design-brief-author agent in IM,
    which uses the trigger phrase and COORDINATOR_BASE_URL to start the skill.
    """
    base_url = os.environ.get("COORDINATOR_BASE_URL", "http://127.0.0.1:8004")
    return (
        f"请开始设计 Brief 生成 {requirement.req_id}\n"
        f"\n"
        f"COORDINATOR_BASE_URL={base_url}\n"
        f"\n"
        f"（请把本消息原样转发/粘贴给 design-brief-author agent，"
        f"它会单轮完成 Brief 生成并写入飞书 design 文档。）"
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m pytest tests/test_design_brief_handoff_dm.py -v
```
Expected: 4/4 pass.

- [ ] **Step 5: Full suite regression check**

```bash
python3 -m pytest tests/ --ignore=tests/test_concurrent_spec_gate.py -q 2>&1 | tail -3
```

- [ ] **Step 6: Commit**

```bash
git add src/requirement_workflow_v12/service_app.py tests/test_design_brief_handoff_dm.py
git commit -m "feat(coordinator): _build_design_brief_author_handoff_text helper"
```

---

## Task 5: Coordinator — _send_design_brief_author_handoff + wire into dispatch_design_start_if_needed

**Files:**
- Modify: `src/requirement_workflow_v12/service_app.py`
- Test: `tests/test_design_brief_handoff_dm.py` (append)

- [ ] **Step 1: Append failing tests**

Append to `tests/test_design_brief_handoff_dm.py`:

```python


def test_send_handoff_skips_when_creator_user_id_empty():
    from requirement_workflow_v12.service_app import _send_design_brief_author_handoff
    app = MagicMock()
    app.gateway = MagicMock()
    r = _req(creator_user_id="")
    _send_design_brief_author_handoff(app, r)
    app.gateway.send_text.assert_not_called()


def test_send_handoff_calls_send_text_when_creator_user_id_present():
    from requirement_workflow_v12.service_app import _send_design_brief_author_handoff
    app = MagicMock()
    app.gateway = MagicMock()
    r = _req(creator_user_id="ou_designer_123")
    _send_design_brief_author_handoff(app, r)
    app.gateway.send_text.assert_called_once()
    kwargs = app.gateway.send_text.call_args.kwargs
    args = app.gateway.send_text.call_args.args
    # Receive id is ou_designer_123 (positional arg 0 or kwarg receive_id)
    receive_id = args[0] if args else kwargs.get("receive_id")
    assert receive_id == "ou_designer_123"
    # Text contains trigger phrase
    text = args[1] if len(args) > 1 else kwargs.get("text")
    assert "REQ-PROJ-007" in text
    # receive_id_type kwarg should be user_id
    assert kwargs.get("receive_id_type") == "user_id"


def test_send_handoff_swallows_gateway_failure():
    """Gateway errors must not propagate (best-effort)."""
    from requirement_workflow_v12.service_app import _send_design_brief_author_handoff
    app = MagicMock()
    app.gateway = MagicMock()
    app.gateway.send_text.side_effect = RuntimeError("feishu 500")
    r = _req()
    # Must not raise
    _send_design_brief_author_handoff(app, r)


def test_dispatch_design_start_triggers_handoff_dm():
    """dispatch_design_start_if_needed must call _send_design_brief_author_handoff
    after a successful design_start."""
    from requirement_workflow_v12.service_app import dispatch_design_start_if_needed
    from requirement_workflow_v12.project_config import ProjectConfig
    app = MagicMock()
    app.service = MagicMock()
    cfg = ProjectConfig(
        category="enterprise-app",
        template_version="enterprise-app.v1",
        architecture_doc_id="d",
        architecture_doc_url="u",
        claude_design_project_url="https://claude.ai/design/p/abc",
    )
    app.service.project_configs = {"proj": cfg}
    app.service.design_start = MagicMock()
    app.gateway = MagicMock()
    created_doc = MagicMock(document_id="d-1", document_url="https://feishu/d/1")
    app.gateway.create_design_document.return_value = created_doc

    r = _req()

    dispatch_design_start_if_needed(app, r)

    # Handoff DM should have been sent
    app.gateway.send_text.assert_called_once()


def test_dispatch_design_start_handoff_failure_does_not_break_flow():
    """Even if the handoff DM fails, dispatch must not raise."""
    from requirement_workflow_v12.service_app import dispatch_design_start_if_needed
    from requirement_workflow_v12.project_config import ProjectConfig
    app = MagicMock()
    app.service = MagicMock()
    cfg = ProjectConfig(
        category="enterprise-app",
        template_version="enterprise-app.v1",
        architecture_doc_id="d",
        architecture_doc_url="u",
        claude_design_project_url="https://claude.ai/design/p/abc",
    )
    app.service.project_configs = {"proj": cfg}
    app.service.design_start = MagicMock()
    app.gateway = MagicMock()
    created_doc = MagicMock(document_id="d-1", document_url="https://feishu/d/1")
    app.gateway.create_design_document.return_value = created_doc
    # Make send_text blow up
    app.gateway.send_text.side_effect = RuntimeError("feishu send failed")

    r = _req()

    # Must not raise
    dispatch_design_start_if_needed(app, r)
```

- [ ] **Step 2: Run tests to see fail**

```bash
python3 -m pytest tests/test_design_brief_handoff_dm.py -v
```
Expected: 5 new tests FAIL — `_send_design_brief_author_handoff` doesn't exist + dispatch doesn't call it.

- [ ] **Step 3: Add _send_design_brief_author_handoff**

In `src/requirement_workflow_v12/service_app.py`, AFTER `_build_design_brief_author_handoff_text` (added in Task 4), add:

```python
def _send_design_brief_author_handoff(app, requirement) -> None:
    """Send the handoff DM to the REQ creator. Best-effort — never raises."""
    user_id = getattr(requirement, "creator_user_id", "")
    if not user_id:
        LOGGER.info(
            "skip design-brief-author handoff: no creator_user_id req_id=%s",
            requirement.req_id,
        )
        return
    try:
        text = _build_design_brief_author_handoff_text(requirement)
        app.gateway.send_text(user_id, text, receive_id_type="user_id")
        LOGGER.info(
            "sent design-brief-author handoff DM req_id=%s user_id=%s",
            requirement.req_id, user_id,
        )
    except Exception as exc:
        LOGGER.warning(
            "design-brief-author handoff DM failed req_id=%s user_id=%s: %s",
            requirement.req_id, user_id, exc,
        )
```

- [ ] **Step 4: Wire into dispatch_design_start_if_needed**

Find `dispatch_design_start_if_needed` in `service_app.py`. After the `app.service.design_start(...)` call succeeds (inside the existing try block, after the call returns cleanly), add:

```python
        _send_design_brief_author_handoff(app, requirement)
```

Be careful where: the call goes INSIDE the `try` that wraps `design_start`, but AFTER `design_start` has returned (not raised). Look at the current structure — `design_start` is called, then in the existing code the function ends. Add the `_send_design_brief_author_handoff` call right after the `design_start` call (before any except clause).

The resulting structure should look like (sketch; adapt to actual code):

```python
    try:
        app.service.design_start(
            requirement.req_id,
            design_doc_id=created.document_id,
            design_doc_url=created.document_url,
        )
        _send_design_brief_author_handoff(app, requirement)
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
```

The handoff call is INSIDE the success path (after `design_start` returns without raising); if `design_start` raises, we skip the handoff (binding guard failure has its own card flow via `_emit_binding_card_for_guard_failure`).

- [ ] **Step 5: Run tests**

```bash
python3 -m pytest tests/test_design_brief_handoff_dm.py -v
```
Expected: 9/9 pass.

- [ ] **Step 6: Full suite regression check**

```bash
python3 -m pytest tests/ --ignore=tests/test_concurrent_spec_gate.py -q 2>&1 | tail -3
```

Note: existing `tests/test_design_auto_start_on_approve.py` tests may now see `send_text` called — verify assertions still hold. Likely OK since those tests use MagicMock gateways that absorb extra calls.

- [ ] **Step 7: Commit**

```bash
git add src/requirement_workflow_v12/service_app.py tests/test_design_brief_handoff_dm.py
git commit -m "feat(coordinator): send design-brief-author handoff DM after design_start"
```

---

## Task 6: README update

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add to 当前已实现 section**

Find `## 当前已实现` in `README.md`. At the end of its bullet list, append:

```markdown
- OpenClaw skill `design-brief-author` 单轮批处理 agent：`docs/agents/design-brief-author/SKILL.md` + callback-schema；deploy 侧 `deploy/openclaw/workspace/agents/design-brief-author/` 全量 workspace；已注册到 `scripts/sync_openclaw_server.sh`
- Coordinator `dispatch_design_start_if_needed` 在 design_start 成功后自动发 handoff DM 给 REQ 创建者，内含触发 skill 的文本（`请开始设计 Brief 生成 REQ-xxx` + `COORDINATOR_BASE_URL`）
```

- [ ] **Step 2: Add to 仍待补齐 section**

Append to `## 仍待补齐`:

```markdown
- design-brief-author skill 的真实联调（sync 到 staging → 创建 needs_ui=true REQ → 验证 Brief 写入飞书 design docx + callback 成功）
- handoff DM 当前是"让用户手工转发给 agent"模式；v2 可探索 coordinator 直连 agent IM session 的 dispatch
- design-context 的 `current_pages` 仍 stub 为空（design-phase Minor #11）；补全后 skill 可自动识别 new vs modify
```

- [ ] **Step 3: Add reference links to 联调参考**

Append to `## 联调参考`:

```markdown
- design-brief-author skill 设计规格：
  [2026-04-23-design-brief-author-skill-design.md](docs/superpowers/specs/2026-04-23-design-brief-author-skill-design.md)
- design-brief-author skill 实装计划：
  [2026-04-23-design-brief-author-skill-plan.md](docs/superpowers/plans/2026-04-23-design-brief-author-skill-plan.md)
- SKILL.md 源：[docs/agents/design-brief-author/SKILL.md](docs/agents/design-brief-author/SKILL.md)
```

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs(readme): note design-brief-author skill implementation"
```

---

## Self-Review

After Task 6 ships, run:

**1. Spec coverage:**

- [ ] §1.1 使命：skill 从 context 推断 expected_pages → Task 1 (SKILL.md Step 2)
- [ ] §1.2 非目标：单轮、不读飞书/GitHub、不覆盖空 current_pages — all stated in SKILL.md
- [ ] §2 流程：dispatch → handoff DM → skill → callback → coordinator → 设计师 → Task 5 (dispatch wiring) + Task 1 (skill flow)
- [ ] §3 分工：no code change, documented in spec
- [ ] §4 SKILL.md 骨架 → Task 1
- [ ] §5 Brief schema → Task 1 (SKILL.md Step 3 + callback-schema.json)
- [ ] §6 Coordinator handoff DM → Tasks 4, 5
- [ ] §7 Deploy 侧文件 → Tasks 2, 3
- [ ] §8 测试 → Tasks 1, 2, 3, 4, 5 (all have TDD tests)
- [ ] §9 完成标准 → all tasks contribute
- [ ] §10 已知遗留 → Task 6 README 仍待补齐
- [ ] 附录 A 文件变更 → maps 1:1 to Tasks 1-6

No gaps.

**2. Placeholder scan:** searched for "TBD", "TODO", "implement later", "similar to Task N" — none found.

**3. Type consistency:**

- `_build_design_brief_author_handoff_text(requirement)` used in Tasks 4, 5 — consistent signature
- `_send_design_brief_author_handoff(app, requirement)` used in Tasks 5 — consistent
- `dispatch_design_start_if_needed` already exists and modified once — unchanged signature
- `send_text(receive_id, text, receive_id_type=...)` matches FeishuGateway API

Self-review PASS.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-23-design-brief-author-skill-plan.md`. 6 tasks, ~700 lines of artifacts total (much of which is boilerplate copy / mechanical).

**Recommended**: Subagent-Driven execution (fresh agent per task; inline verify for trivial ones, full dispatch for complex).
