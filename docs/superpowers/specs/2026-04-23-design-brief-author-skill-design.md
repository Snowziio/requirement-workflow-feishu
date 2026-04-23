# design-brief-author Skill 实装规格

> 本规格定义 OpenClaw 侧 `design-brief-author` 单轮 skill 的实装内容，以及 coordinator 侧为触发该 skill 所需的最小配套（handoff DM 发送）。skill 部署后，design phase 从"coordinator 已就绪、skill 待实施"进入"端到端可用"。
>
> 关联文档：
> - design-phase 规格：[2026-04-23-design-phase-design.md](./2026-04-23-design-phase-design.md) §8（本规格是其 skill 侧实装）
> - skill 结构约定：[deploy/openclaw/README.md](../../../deploy/openclaw/README.md)
> - 对标已有 skill：[docs/agents/spec-transformer/SKILL.md](../../agents/spec-transformer/SKILL.md)（单轮批处理范式）、[docs/agents/plan-author/SKILL.md](../../agents/plan-author/SKILL.md)（Brief schema / 行为合同参考）

---

## 零、变更记录

| 版本 | 日期 | 关键变更 |
|---|---|---|
| v1 | 2026-04-23 | 首版：单轮 skill 设计（拉 context → LLM 推断 pages → 组装 Brief → callback）；Brief YAML+Markdown 双层 schema；coordinator 侧加 handoff DM 发送；包含 SKILL.md / callback-schema.json / agent workspace 文件全量实装 |

---

## 一、目标与非目标

### 1.1 核心使命

在 `DesignStatus.DRAFTING` 进入时，由 coordinator 派发本 skill；skill 从 REQ 8 字段 + 项目上下文 + 现有 Page Registry **一次性推断** `expected_pages[]`，产出结构化 Brief，交回 coordinator 落到飞书 design docx + 归档 `design/archive/REQ-*/BRIEF.md`。

设计师拿到 Brief 后复制其中"首轮 Prompt"节到 Claude Design chat，外部作业。

### 1.2 非目标

- **不做多轮对话**：skill 拉 context + 产出 Brief 一次性完成；不与设计师讨论、不替其拍板视觉决策
- **不直接读写飞书/GitHub**：skill 只通过 HTTP 端点与 coordinator 交互；coordinator 负责 docx / git 落盘
- **不覆盖 `current_pages` 为空时的严格推断**：design-context 目前返回 `current_pages: []`（design-phase Minor #11），本 skill v1 把所有 expected_pages 标 `action: new`；待 coordinator 侧 Page Registry 读取补全后，skill 自然识别 new vs modify（不需改 skill）
- **不自建 handoff DM 触发路径**：coordinator 发 DM 到设计师，设计师手动把 handoff text 贴给 skill agent（同 plan-author 既有模式）；未来可引入直连 dispatch 但不在本规格范围

### 1.3 适用范围

- 仅 `needs_ui=true` REQ
- 触发时机：`DesignStatus` null → DRAFTING（由 `dispatch_design_start_if_needed` 触发）
- skill 的一次完整执行约束在 `design_start` 之后、`design_submit` 之前
- `DesignStatus.READY` 后若人工 `/design restart <req>` 级联重置，会重新进入 DRAFTING；skill 会被重新触发一次

---

## 二、流程（E2E）

```
REQ.status=APPROVED && needs_ui=true
   │
   ▼
approve_requirement post-hook → dispatch_design_start_if_needed
   │
   ├── gateway.create_design_document(req)  [已有]
   ├── service.design_start(req, design_doc_id, design_doc_url)  [已有]
   └── ★ NEW: gateway.send_dm 发 handoff text 给 REQ.creator_user_id
           handoff 含："请开始设计 Brief 生成 REQ-<id>"
                       +"coordinator_base_url=<url>"
           │
           ▼
   设计师看到 DM，复制贴到 design-brief-author agent 的 IM session
           │
           ▼
   skill 被激活（复用 OpenClaw IM 入口）：
     Step 1: curl GET /queries/openclaw/design-context/{req_id}
     Step 2: 内部推理（LLM）：
             - 从 requirement_summary 识别 UI-相关功能
             - 对每个 UI 功能推断：display_name / action / intent /
               key_interactions / must_cover_states
             - 若 current_pages 非空 → 区分 new/modify（v1 current_pages 总为空）
             - 根据 frontend_tech_stack → 组装 design_system_hints
             - 根据 prior_handoff_archive_ref → 组装 cross_req_references
             - 生成"首轮 Prompt"人读段，内含 claude_design_project_url
     Step 3: 组装 YAML frontmatter + Markdown body 两段
     Step 4: curl POST /openclaw/design-callback
             body: {req_id, event:design_brief_submit, payload:{brief_yaml_frontmatter, brief_markdown_body}}
     Step 5: 收到 200 才回 IM："✅ Brief 已提交到飞书 design 文档 <url>；
             请到 Claude Design <project_url> 复制首轮 Prompt 开始作业"
   │
   ▼
coordinator handle_openclaw_design_callback [已有]：
   - Requirement.pending_design_brief = {brief_yaml_frontmatter, brief_markdown_body, submitted_at}
   - gateway.write_document_text(design_doc_id, brief_markdown_body) 写飞书 docx
   - _dispatch_transition_notifications(trigger="design_brief_ready")  [已有]
   - 返回 {design_status: "DESIGN_DRAFTING"}
   │
   ▼
   设计师继续（不再涉及 skill）：
     1. 在飞书 design docx 查看完整 Brief
     2. 打开 Claude Design Project, 点 Sync now, 粘贴首轮 Prompt
     3. 多轮迭代画图
     4. Export handoff zip
     5. 回到飞书卡片上传 zip → design_submit → 终审 → DESIGN_READY
```

---

## 三、分工

| 角色 | 干什么 | 不干什么 |
|---|---|---|
| **Coordinator** | handoff DM 发送；design-context 端点（已有）；design-callback 端点（已有）；飞书 docx 写入（已有） | 不做 Brief 推断；不做 LLM 调用；不处理 skill 内部状态 |
| **design-brief-author skill**（本规格核心） | 拉 context；LLM 推断 expected_pages；组装 Brief；callback | 不做多轮对话；不直接访问飞书/GitHub；不做视觉决策 |
| **设计师（人）** | 粘 handoff 触发 skill；收到 Brief 后去 Claude Design 作业 | 不改 Brief；不维护 PAGES.yaml（coordinator 在 DESIGN_READY 时自动写） |

---

## 四、SKILL.md 内容骨架

按 `spec-transformer/SKILL.md`（70 行，单轮范式）对标，目标 ~100 行。分节：

### 4.1 Frontmatter

```yaml
---
name: design-brief-author
description: 设计 Brief 生成助手，APPROVED + needs_ui=true 的 REQ 进入 DESIGN_DRAFTING 后单轮生成 Brief。从 REQ 8 字段 + 现有 Page Registry 推断 expected_pages，产出 YAML+Markdown 双层 Brief，回写飞书 design docx + callback Coordinator。不做多轮对话，不替设计师拍板视觉决策。
---
```

### 4.2 存储模型说明（对齐 plan-author 的做法）

明确告知：Brief 的构造期 SOT = 飞书 design docx + `design/archive/<REQ>/BRIEF.md`；skill **不**直接访问飞书/GitHub，只通过 coordinator 端点。

### 4.3 启动流程（5 Steps）

每步含具体 `curl` 命令和期望的响应结构，精确到：

- **Step 1**：`curl -s "${COORDINATOR_BASE_URL}/queries/openclaw/design-context/{req_id}"`；响应结构包含 `req_id / project / requirement_document_url / needs_ui / claude_design_project_url / frontend_subpath / frontend_tech_stack / category / architecture_doc_url / design_doc_id / design_doc_url / current_pages / prior_handoff_archive_ref`
- **Step 2**：LLM 推理规则的**硬约束清单**：
  1. `expected_pages[]` 必须非空
  2. 每个 page 必须有 `display_name`（PascalCase）+ `action`（new/modify）+ `intent`（1 句）+ `key_interactions`（≥1 条）+ `must_cover_states`（≥1 条）
  3. 若 `current_pages` 非空且 `display_name` 匹配 → `action: modify` + 填 `existing_page_ref`
  4. 若 `current_pages` 为空（v1 实际情况） → 全部 `action: new`
  5. "首轮 Prompt"里必须内嵌 `claude_design_project_url`
- **Step 3**：Brief schema（§3 的完整 YAML + Markdown）
- **Step 4**：`curl -X POST ${COORDINATOR_BASE_URL}/openclaw/design-callback` with schema
- **Step 5**：200 后回 IM；非 200 报错不伪装成功

### 4.4 硬约束（对齐 plan-author Phase C 的行为合同）

```markdown
## ⛔ 行为合同（违反 = 卡死流程）

本 skill 本轮的**第一个**（也是必做的）tool call 必须是 Step 4 的
`curl … /openclaw/design-callback`。在那个 curl 成功返回 **HTTP 200 之前**，
你不能：

- 发 IM 说"Brief 生成中 / 已提交 / 正在写入 / 完成" —— 这些都是谎言
- 把 Brief 作为"预览"发出去 —— 用户会以为 callback 已走
- 结束本轮 session

组装 Brief 是**内部思考**，不是用户可见输出。所有"结果性"文字只能出现在 curl 200 之后。
```

### 4.5 异常分支

- `design-context` 404 / 409 → 立即停止报错
- `design-callback` 409（`invalid_state`） → 大概率 `design_status != DRAFTING`；读响应 message 报错
- `design-callback` 500 → 重试一次后报错
- `claude_design_project_url` 为空 → 懒检查应已在 `design_start` 前阻断；防御性地在 Brief 里提示"URL 未绑定，请先找管理员"

### 4.6 反模式

- ❌ 多轮和设计师讨论 expected_pages（单轮 skill，自己推断）
- ❌ 在 callback 之前 IM 发"Brief 生成中..."
- ❌ 跳过 design-context 直接读 requirement_doc URL
- ❌ 把 Brief 的 markdown_body 当成 skill 最终输出（正确是 callback body）
- ❌ 不把 `claude_design_project_url` 塞进首轮 Prompt（失去跨 REQ 一致性）

---

## 五、Brief 完整 Schema

### 5.1 Callback POST body

```json
{
  "req_id": "REQ-PROJ-007",
  "event": "design_brief_submit",
  "payload": {
    "brief_yaml_frontmatter": "<yaml string, required, non-empty>",
    "brief_markdown_body": "<markdown string, required, non-empty>"
  }
}
```

### 5.2 `brief_yaml_frontmatter` 内容

```yaml
schema_version: "1.0"
req_id: "REQ-PROJ-007"
generated_at: "2026-04-23T14:00:00+08:00"
generated_by: "design-brief-author@1.0"

expected_pages:
  - display_name: "ReportEditor"              # PascalCase，稳定标识
    action: "modify"                           # enum: new | modify
    existing_page_ref: "ReportEditor"          # required when action=modify
    intent: "增加右侧面板可折叠功能"
    key_interactions:
      - "点击折叠按钮 → 右侧面板宽度 0"
    must_cover_states: ["default", "collapsed"]
  - display_name: "ApprovalToast"
    action: "new"
    intent: "审核通过/拒绝的结果提示"
    key_interactions:
      - "3 秒自动消失"
      - "通过=绿色，拒绝=红色"
    must_cover_states: ["success", "error"]

design_system_hints:
  - "主色用 var(--brand-500)（Quant Indigo）"
  - "字体 IBM Plex Sans / SC / Mono"

cross_req_references:
  prior_archive: "design/archive/REQ-PROJ-006_xxx/"   # 空串 = 首次 REQ
  prior_summary: "<上一 REQ MANIFEST 的 bundle_inner_readme_excerpt 摘录>"
```

### 5.3 `brief_markdown_body` 内容骨架

```markdown
# Design Brief: {req_id}

## 背景
（来自 context.requirement_summary 的 2-3 段自然语言摘要）

## 本次需要交付的 pages

### 1. {display_name}（{new|修改}）
- **意图**：...
- **交互**：...; ...
- **状态覆盖**：...

### 2. ...
...

## 设计系统约束
- ...

## 前一 REQ 上下文
（如 cross_req_references.prior_summary 非空，原样贴入）

---

## 首轮 Prompt（复制此段到 Claude Design chat）

> 我要在 {project} Claude Design Project 里做这次迭代。
>
> **现有 Project URL**：{claude_design_project_url}
>
> 本次涉及：
> - {new/修改 page 1 一句话}
> - {new/修改 page 2 一句话}
> - ...
>
> 设计约束：{design_system_hints join "; "}
>
> 请先确认你能看到现有 screens。然后逐页给我出设计，不要一次出全部。
```

### 5.4 `callback-schema.json`（JSON schema draft-07）

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "design-brief-author callback payload",
  "type": "object",
  "required": ["req_id", "event", "payload"],
  "properties": {
    "req_id": {"type": "string", "pattern": "^REQ-"},
    "event": {"const": "design_brief_submit"},
    "payload": {
      "type": "object",
      "required": ["brief_yaml_frontmatter", "brief_markdown_body"],
      "properties": {
        "brief_yaml_frontmatter": {"type": "string", "minLength": 1},
        "brief_markdown_body": {"type": "string", "minLength": 1}
      }
    }
  }
}
```

---

## 六、Coordinator 配套：handoff DM 发送

### 6.1 现状

`dispatch_design_start_if_needed`（`service_app.py`）已做：创建 design docx + 调 `service.design_start`。**缺**：通知设计师去激活 skill。

### 6.2 新增

在 `dispatch_design_start_if_needed` 成功调 `design_start` 之后、return 之前，追加：

```python
try:
    _send_design_brief_author_handoff(app, requirement)
except Exception as exc:
    LOGGER.warning(
        "design-brief-author handoff DM failed req_id=%s: %s",
        requirement.req_id, exc,
    )
```

新增 top-level 函数 `_send_design_brief_author_handoff(app, requirement)`：

```python
def _send_design_brief_author_handoff(app, requirement) -> None:
    """发 DM 给 REQ 创建者，内含可直接转发给 design-brief-author agent 的 handoff text。"""
    user_id = requirement.creator_user_id
    if not user_id:
        LOGGER.info(
            "skip design-brief-author handoff: no creator_user_id req_id=%s",
            requirement.req_id,
        )
        return
    text = _build_design_brief_author_handoff_text(requirement)
    app.gateway.send_text(user_id, text, receive_id_type="user_id")


def _build_design_brief_author_handoff_text(requirement) -> str:
    base_url = os.environ.get("COORDINATOR_BASE_URL", "http://127.0.0.1:8004")
    return (
        f"请开始设计 Brief 生成 {requirement.req_id}\n"
        f"\n"
        f"COORDINATOR_BASE_URL={base_url}\n"
        f"（把本消息原样转发给 design-brief-author agent，它会单轮完成 Brief 生成。）"
    )
```

### 6.3 测试

单元测试：
- `_build_design_brief_author_handoff_text` 含 req_id + "请开始设计 Brief 生成"
- `_send_design_brief_author_handoff` 在 `creator_user_id` 为空时 skip（不 send）
- `_send_design_brief_author_handoff` 在 `creator_user_id` 非空时调 `gateway.send_text`
- `dispatch_design_start_if_needed` 流程中该 DM 发送失败不影响 `design_start` 成功

---

## 七、部署侧：workspace 文件 + sync 配置

### 7.1 `docs/agents/design-brief-author/`

- `SKILL.md` — §4 骨架的具体文本（~100 行）
- `callback-schema.json` — §5.4 JSON schema

### 7.2 `deploy/openclaw/workspace/agents/design-brief-author/`

- `SKILL.md` → **symlink** to `../../../../docs/agents/design-brief-author/SKILL.md`
- `IDENTITY.md`（6 行，per-agent 独特内容）：

```markdown
# 设计 Brief 生成助手

- 名称：设计 Brief 生成助手
- Emoji：🎨
- 角色：APPROVED + needs_ui=true REQ 进入 DESIGN_DRAFTING 时单轮生成 Brief。从 REQ 8 字段 + 项目上下文推断 expected_pages，回写飞书 design docx，不做多轮对话。
- 绑定账号：design-brief-author
```

- `SOUL.md` / `AGENTS.md` / `TOOLS.md` / `USER.md` — copy boilerplate from `spec-transformer/` 对应文件（这些跨 agent 复用，几乎不变）

### 7.3 `deploy/openclaw/agents/design-brief-author/models.json.template`

Copy 自 `spec-transformer/models.json.template`（MiniMax M2.5/M2.7 标准配置；单轮 skill 不需要特殊模型）。

### 7.4 `scripts/sync_openclaw_server.sh` 更新

两处：

```bash
# AGENTS 数组追加
AGENTS=(... spec-transformer-reviewer design-brief-author)

# skill_for_agent case 追加
case "$1" in
  ...
  design-brief-author) echo design-brief-author ;;
esac
```

### 7.5 `deploy/openclaw/README.md` 更新

agent id ↔ skill name 表新增一行：

```
| `design-brief-author`       | `design-brief-author`      |
```

---

## 八、测试策略

### 8.1 静态验证（CI 可跑）

- `tests/test_agents_design_brief_author_skill.py`（新）：
  - SKILL.md 存在且 YAML frontmatter 可解析（`yaml.safe_load` 得到 `name` / `description`）
  - SKILL.md 包含硬约束关键词（"行为合同"、"callback … 之前不得 …"）
  - callback-schema.json 是合法的 JSON schema draft-07
  - 用一份人工手写的合法 Brief payload 对 schema 验证通过
  - 用一份缺字段 / 错 event 的非法 payload 验证失败

- `tests/test_agents_design_brief_author_workspace.py`（新）：
  - `deploy/openclaw/workspace/agents/design-brief-author/SKILL.md` 是 symlink，目标指向 `docs/agents/...`
  - 其余 5 个 md 文件存在

- `tests/test_design_brief_handoff_dm.py`（新）：
  - `_build_design_brief_author_handoff_text` 单元测试
  - `_send_design_brief_author_handoff` 单元测试（mock gateway）
  - `dispatch_design_start_if_needed` 集成测试（handoff DM 被调用 + 失败不阻塞）

### 8.2 部署后联调（手跑，不 CI）

1. 运行 `scripts/sync_openclaw_server.sh --dry-run` 确认无报错
2. 实跑 `scripts/sync_openclaw_server.sh` 推到 staging
3. 在飞书创建一个 `needs_ui=true` 的测试 REQ，走到 APPROVED
4. 观察 creator 是否收到 handoff DM
5. 手动把 DM 转发给 design-brief-author agent
6. 观察：
   - 飞书 design docx 是否出现 Brief 内容
   - `Requirement.pending_design_brief` 是否写入（查状态快照）
   - 项目群是否收到 `design_brief_ready` 卡片（design-phase Task 24 实装）
7. 验证 `scripts/run_openclaw_smoke.py` 或手工 curl 对 callback 端点的响应

---

## 九、完成标准 & 失败回退

### 9.1 完成标准

- `docs/agents/design-brief-author/SKILL.md` 和 `callback-schema.json` 已提交
- `deploy/openclaw/workspace/agents/design-brief-author/` 全量 6 文件已提交（含 SKILL.md symlink）
- `deploy/openclaw/agents/design-brief-author/models.json.template` 已提交
- `scripts/sync_openclaw_server.sh` 更新已提交
- `deploy/openclaw/README.md` agent 表更新已提交
- coordinator 侧 `_send_design_brief_author_handoff` + `_build_design_brief_author_handoff_text` 已实装且单元测试通过
- 全量 pytest 无新 regression

### 9.2 失败回退

| 失败点 | 行为 |
|---|---|
| handoff DM 发送失败 | log warning，不阻塞 `dispatch_design_start_if_needed` |
| skill 拉 context 失败（404/409） | skill 本地 stop，回 IM 报错；coordinator 无影响 |
| skill 产出 Brief 不合规（YAML parse 失败 / 字段缺失） | coordinator callback handler 当前是宽松接收（只存字符串），**不做 schema 校验**；本规格不引入严格校验（YAGNI，人工审查飞书 docx 时会发现） |
| skill 产出重复 callback | coordinator 覆盖 `pending_design_brief`（幂等） |
| `/design restart` 级联回 DRAFTING | 重新触发 dispatch + handoff DM；skill 再跑一次生成新 Brief 覆盖 |

---

## 十、已知遗留 / 未来演进

- **`current_pages` v1 总为空**：design-phase Minor #11 — `DesignContextBuilder._load_pages_registry_slice` 返回 `[]`。skill 当前对所有 page 标 `action: new`。后续补 coordinator 侧 Page Registry 读取能力后，skill 自动识别 modify（不需改 skill）
- **`prior_handoff_archive_ref` 同上**：`_find_prior_archive` 返回 ""。后续补后 skill 的 `cross_req_references.prior_summary` 才有内容
- **handoff DM 为手工转发模式**：设计师需把 DM 复制给 agent，v2 可改为 coordinator 直接 ping agent 的 IM session ID（需 OpenClaw 侧暴露 session 激活 API）
- **callback payload 无严格 schema 校验**：coordinator 侧当前是宽松接收；未来可在 `handle_openclaw_design_callback` 里加 jsonschema 验证，防止 skill 产出错 schema 污染 pending_design_brief
- **无 Brief 质量评估**：v1 完全信赖 skill 的 LLM 推断质量；未来可引入 `design-brief-reviewer` skill 做 inferential 审查（同 spec-reviewer / spec-transformer-reviewer 的二元模式），但会破坏"单轮"简洁性，暂不做
- **单元测试仅覆盖静态验证**：skill 的实际 LLM 推断质量无法在 CI 验证，只能靠 §8.2 人工联调 + 实际使用反馈迭代

---

## 附录 A：文件变更总览

| 文件 | 动作 | 规模 |
|---|---|---|
| `docs/agents/design-brief-author/SKILL.md` | 新建 | ~100 行 |
| `docs/agents/design-brief-author/callback-schema.json` | 新建 | ~30 行 |
| `deploy/openclaw/workspace/agents/design-brief-author/SKILL.md` | 新建（symlink） | 1 行 |
| `deploy/openclaw/workspace/agents/design-brief-author/IDENTITY.md` | 新建 | 6 行 |
| `deploy/openclaw/workspace/agents/design-brief-author/SOUL.md` | 复制自 spec-transformer | ~35 行 |
| `deploy/openclaw/workspace/agents/design-brief-author/AGENTS.md` | 复制自 spec-transformer | ~210 行 |
| `deploy/openclaw/workspace/agents/design-brief-author/TOOLS.md` | 复制自 spec-transformer | ~40 行 |
| `deploy/openclaw/workspace/agents/design-brief-author/USER.md` | 复制自 spec-transformer | ~17 行 |
| `deploy/openclaw/agents/design-brief-author/models.json.template` | 复制自 spec-transformer | ~15 行 |
| `scripts/sync_openclaw_server.sh` | 修改（+2 行） | +2 行 |
| `deploy/openclaw/README.md` | 修改（+1 行表格行） | +1 行 |
| `src/requirement_workflow_v12/service_app.py` | 修改（新增 handoff helper + 调用） | +~30 行 |
| `tests/test_agents_design_brief_author_skill.py` | 新建 | ~80 行 |
| `tests/test_agents_design_brief_author_workspace.py` | 新建 | ~40 行 |
| `tests/test_design_brief_handoff_dm.py` | 新建 | ~80 行 |
| `README.md` | 修改（已实现 / 仍待补齐 节） | +~8 行 |

**总估量**：~700 行（多半是 skill SKILL.md 核心文本 + boilerplate 复制）。

---

## 附录 B：SKILL.md 的"首轮 Prompt"实际片段示例

（给 skill 实施者一个可参照的生成目标样例）

```markdown
## 首轮 Prompt（复制此段到 Claude Design chat）

> 我要在 investment-assistant Claude Design Project 里做这次迭代。
>
> **现有 Project URL**：https://claude.ai/design/p/abc123
>
> 本次涉及：
> - 新增 AvatarUploadPage：头像上传 + 本地裁剪 + 提交审核
> - 新增 AvatarReviewListPage：管理员查看待审列表
> - 新增 AvatarReviewDetailPage：详情页预览 + 通过/拒绝按钮
> - 新增 AvatarApprovalToast：审核结果 toast（success/error 两态）
>
> 设计约束：主色用 var(--brand-500)（Quant Indigo）; 字体 IBM Plex Sans / SC / Mono
>
> 请先确认你能看到现有 screens。然后逐页给我出设计，不要一次出全部。
```

（此样例对应的 expected_pages YAML 在 §5.2 有完整结构；设计师粘上面一段到 Claude Design 即可开始第一页的讨论。）
