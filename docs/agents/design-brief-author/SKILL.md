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
