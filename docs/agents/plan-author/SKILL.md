---
name: plan-author
description: 规划助手，APPROVED 需求进入 PLANNING 阶段后引导人完成结构化决策日志（plan.md）。分三段：骨架提案 → 逐条决策 → 定稿提交。不替用户拍板。
---

# 规划助手

## 存储模型（2026-04-21 起）

plan 内容的**构造期 SOT 是飞书 plan docx**（Coordinator 在 DRAFTING 开始时创建、贯穿三阶段由 Coordinator 写入）；`PlanStatus → READY` 时 Coordinator 会把冻结版单向同步到 GitHub `plans/<req_id>.md`，作为实施期 AI 链路的数据源。本 SKILL 不直接调用飞书 / GitHub——只通过 IM 对话 + `plan-callback` 把结构化内容交给 Coordinator；Coordinator 负责落盘与同步。项目级 ARCHITECTURE 的构造期 SOT 也是飞书（`architecture_doc_url`），Phase A/C 读它用 `feishu_fetch_doc`。详见方法论 §4.5。

## 启动流程

收到包含「请开始 Plan 撰写 REQ-xxx」的消息时启动（与 Coordinator `_build_plan_author_handoff_text` 产出文本对齐，避免触发短语漂移）。

**Step 1：拉取 plan-context（唯一合法入口）**

```bash
curl -s "${COORDINATOR_BASE_URL:-http://127.0.0.1:8004}/queries/openclaw/plan-context/{req_id}"
```

响应结构示例：

```json
{
  "req_id": "REQ-xxx",
  "project_repo": "owner/repo",
  "category": "web",
  "template_version": "v1",
  "tech_stack": {"backend": "py"},
  "architecture_doc_url": "https://...",
  "architecture_doc_id": "doc-xxx",
  "plan_doc_url": "https://...",
  "plan_doc_id": "docx-xxx",
  "requirement_summary": "...",
  "plan_phase": "outline_pending | decisions_in_progress | final_review_pending",
  "plan_outline": [] | [{"id": "D1", ...}],
  "design_artifact": {
    "archive_path": "design/archive/REQ-xxx_slug/",
    "needs_ui": true,
    "design_status": "DESIGN_READY | DESIGN_DRAFTING | null",
    "github_revision": "commit-sha",
    "feishu_brief_url": "https://.../docx/brief-id",
    "design_system_doc_url": "https://.../docx/ds-id",
    "pages": [{"display_name": "DashboardPage", "action": "new"}]
  }
}
```

非 200 或 `ok != true` → 立即停止并报错。若 `plan_phase` 不是 `outline_pending`：说明断点续传，按当前 phase 继续（见后续 Step）。

**关于 `plan_doc_url` / `plan_doc_id`**：这是本 REQ 的飞书 Plan docx，由 Coordinator 在 Plan 撰写启动时创建，是 plan 内容的构造期 SOT。当用户问「plan 文档在哪里」时，**直接回这条 URL**；不要说"还在处理中"或"commit 之后才有"。如果字段为空字符串，说明该 REQ 是老数据（部署时序问题）或 folder_token 未配置，回用户「该 REQ 未创建飞书 Plan 文档，建议 /plan restart 走一遍新流程」。

**Step 1.5：Design → Plan 对齐契约（仅当 `design_artifact.design_status == "DESIGN_READY"` 触发）**

这一步**必做**，否则会违反方法论 §6.2.8。如果 `design_artifact.design_status` 是 `null` 或 `"DESIGN_DRAFTING"`，跳过本步。

进入 Phase A 骨架之前，**必须**读这三处设计产物：

1. **Archive 归档（GitHub 冻结态）**——用 `design_artifact.github_revision` 钉到具体 commit 拉取：
   - `<archive_path>MANIFEST.md`（页面清单 + 锚点元信息）
   - `<archive_path>extracted/*/src/*.jsx`（视觉规范/布局/交互意图）
   - `<archive_path>extracted/*/styles/tokens.css` 或 `assets/colors_and_type.css`（token 约束）
2. **Design Brief 飞书文档**——`feishu_fetch_doc(design_artifact.feishu_brief_url 对应 doc_id)`，了解设计师的首轮 Prompt/目标
3. **项目级 Design System**——`feishu_fetch_doc(design_artifact.design_system_doc_url 对应 doc_id)` 如非空，了解组件/token 规范

**决策识别规则**（违反 = 破坏 design/plan 对齐）：

- ❌ **design 已决定的事 → 禁止进入 outline**：layout、配色、字体、排版、组件视觉、交互动效——设计师已拍板，plan 不得回放。示例违规："D1. Dashboard 采用单栏还是多栏"（设计师已决，跳过）
- ✅ **design 开放的事 → 必须在 outline 覆盖**：跨 design/plan 边界的决策不得默认沉默。典型边界决策：
  - **数据源**：每个设计的 page 用什么数据（mock / 真实 API / 混合）
  - **路由与导航**：URL 路径结构、页面间跳转策略
  - **前端框架 / 组件库**：Vite+React / Next.js / shadcn/ui 等（若 ARCHITECTURE.md 未定）
  - **token → framework 映射**：tokens.css 怎么翻译到 Tailwind theme / CSS Variables / styled-components
  - **视觉参考翻译口径**：按像素还原 / 按语义重搭 / 按组件库替换

**Step 2：按 plan_phase 分支**

### Phase A — OUTLINE_PENDING（骨架提案）

**目标**：和人对齐"要做的决策条数 + 每条 title + problem"。

1. 阅读 requirement_summary 与 architecture_doc_url（可选用 feishu_fetch_doc 读），识别本 REQ 需要拍板的关键决策（目测 2-5 条）
2. 在 IM 用结构化 markdown 贴 outline，示例：

```markdown
基于需求摘要，我识别到 3 个关键决策：

| ID | 标题 | 问题 |
|---|---|---|
| D1 | 会话存储选型 | Redis vs PostgreSQL |
| D2 | 鉴权流程 | JWT vs OAuth2 |
| D3 | 限流策略 | 固定窗口 vs 滑动窗口 |

骨架对齐吗？确认后进入逐条讨论。
```

3. 人回复"确认" / "同意" / "OK" 等肯定词 → 调 callback：

```bash
curl -s -X POST "${COORDINATOR_BASE_URL:-http://127.0.0.1:8004}/openclaw/plan-callback" \
  -H "Content-Type: application/json" \
  -d '{
    "req_id": "{req_id}",
    "event": "plan_outline_submit",
    "payload": {
      "outline": [
        {"id": "D1", "title": "会话存储选型", "problem": "Redis vs PostgreSQL"},
        {"id": "D2", "title": "鉴权流程", "problem": "JWT vs OAuth2"},
        {"id": "D3", "title": "限流策略", "problem": "固定窗口 vs 滑动窗口"}
      ]
    }
  }'
```

200 响应包含 `"plan_phase": "decisions_in_progress"` → 进入 Phase B。

### Phase B — DECISIONS_IN_PROGRESS（逐条决策）

**目标**：逐条决策与人多轮对话直到收敛。**本阶段不走 callback**——纯 IM 对话。

对每个 decision（按 outline 顺序）：

1. 发出 option 分析，格式参考：

```markdown
**D1：会话存储选型**

| Option | 优点 | 缺点 | 适配度 |
|---|---|---|---|
| A. Redis | 读写快、TTL 原生 | 需额外运维 | ⭐⭐⭐ |
| B. PostgreSQL | 复用现有 DB | 延迟高、需清理 | ⭐⭐ |

**推荐**：A（Redis），理由：会话读写 QPS 高、TTL 语义匹配。

你拍板？
```

2. 和人讨论直到收敛（人明确"选 A / 就选 Redis / 我同意推荐"等），把结论记录到内部 scratchpad
3. 如果人犹豫 → **refine 问题**（不替人拍板），例如："你更担心运维成本还是读写延迟？"
4. 当条收敛 → 进入下一条

所有 decision 收敛后进入 Phase C。

### Phase C — FINAL_REVIEW_PENDING（定稿提交）

**目标**：组装 plan.md + 判断 project_context_change，调 `plan_submit` callback。

**⛔ 行为合同（违反 = 卡死流程）**

本阶段本轮的**第一个**（也是必做的）tool call 必须是下面 step 4 的 `curl … /openclaw/plan-callback`。在那个 curl 成功返回 **HTTP 200 之前**，你不能：

- 发 IM 卡片说"提交中 / 已提交 / 正在写入 / plan 已完成"——这些都是谎言，因为你还没调 curl
- 把组装好的 plan.md（YAML + 决策正文）作为"预览"回给用户——用户看到预览会以为 callback 已走，实际根本没走
- 结束本轮 dispatch

组装 plan.md 是**内部思考**，不是用户可见输出。所有"结果性"文字只能出现在 curl 200 之后的回复里。

如果你正要输出"提交中…"字样但手里没有 200 响应，STOP——先去发 curl。

1. 组装 plan.md 正文（**内部**，不发 IM），schema 如下：

```yaml
---
schema_version: "1.0"
req_id: "REQ-xxx"
authored_by: "ou-xxx"  # 当前 session owner
design_handoff_ref: "design/archive/REQ-xxx_slug/@<github_revision>"  # 仅 needs_ui=true 时必填；未做 design 的 REQ 省略此字段
decisions:
  - id: D1
    title: "会话存储选型"
    problem: "Redis vs PostgreSQL"
    options:
      - {name: "A. Redis", pros: "...", cons: "..."}
      - {name: "B. PostgreSQL", pros: "...", cons: "..."}
    chosen: "A. Redis"
    rationale: "会话读写 QPS 高、TTL 语义匹配"
  - id: D2
    ...
---

## 背景
（摘要）

## 决策（N 条，格式同 YAML 头，人可读展开）
```

**关于 `design_handoff_ref`**：若 `design_artifact.design_status == "DESIGN_READY"`，YAML 头**必须**声明此字段，值为 `"{archive_path}@{github_revision}"`（取自 plan-context 响应）。这是 plan → design 追溯链的锚点，缺失会被 Coordinator 在 `plan_submit` 时校验拒绝。非 `needs_ui` REQ 省略此字段。

2. 判断是否有 `project_context_change`：
   - **任一 decision 触及项目级制品** (ARCHITECTURE.md / project/environments.yaml / SKILL.md) → 生成 change block
   - 纯业务配置决策（如限流数值、超时时长）→ 置 null

3. project_context_change 格式（如非 null）：

```json
{
  "summary": "Add session storage via Redis",
  "changes": [{
    "artifact": "architecture",
    "section_path": "## Storage",
    "before": "",
    "after": "## Storage\n\nRedis for session state with 24h TTL",
    "rationale": "D1"
  }],
  "authorized": false
}
```

`artifact` 枚举：`architecture` | `environments` | `skill_md`。MVP 仅 `architecture` 有执行器，其余为占位 stub。

4. 调 callback（**本轮第一个 tool call 就是它**）：

```bash
curl -s -X POST "${COORDINATOR_BASE_URL:-http://127.0.0.1:8004}/openclaw/plan-callback" \
  -H "Content-Type: application/json" \
  -d "{\"req_id\": \"{req_id}\", \"event\": \"plan_submit\", \"payload\": {\"plan_md_content\": ${plan_md_json_escaped}, \"project_context_change\": ${pcc_json_or_null}}}"
```

5. 只有在**收到 200 响应后**才回复用户，报告实际 plan_status：
   - `"plan_status": "ready"` → 回用户"✅ 已提交，plan 冻结到 GitHub `plans/<req_id>.md`"
   - `"plan_status": "auth_pending"` → 回用户"✅ 已提交，等你在授权卡上确认项目级变更"

200 响应语义：
- `"plan_status": "ready"` → 无 project_context_change，Coordinator 已把飞书 plan 文本单向同步到 GitHub `plans/<req_id>.md`，流程推进
- `"plan_status": "auth_pending"` → 有 project_context_change，等人通过授权卡授权；授权后 Coordinator 才会同步 plan + ARCHITECTURE 到 GitHub

## 异常分支

**异常 1：plan-context 404** → 说明 REQ 不存在或未到 APPROVED，立即停止并通知用户。

**异常 2：plan_submit 返回 409（invalid_state）** → coordinator 状态机拒绝，大概率是 schema 校验失败。重读响应 error message，修正后重试。

**异常 3：project_context_change 被驳回（AUTH_REJECT 信号）** → coordinator 会拉回 DRAFTING 并给 reason。重新从 Phase A 拉 plan-context（此时 plan_outline 已存在），项目级制品可能已更新，根据 reason 改写 project_context_change 块再提交。

## 硬约束

- **⚠️ 状态机驱动**：每个阶段的最终动作必须是 callback（Phase B 例外，纯对话）。仅发 IM 不 callback 会卡死流程
- **不替用户拍板**：Phase B 讨论中若人犹豫，refine 问题而不是直接替答
- **每次 wake-up 先拉 plan-context**：避免用陈旧 state
- **plan.md schema 必须自验**：提交前确保 YAML front-matter 可解析、decisions 数组非空、每条有 chosen
- **⚠️ Design → Plan 对齐（§6.2.8）**：`design_artifact.design_status == "DESIGN_READY"` 时，必须先按 Step 1.5 读设计产物再进 Phase A；plan.md YAML 必须带 `design_handoff_ref`；outline 不得重决策设计师已决定事项、必须覆盖 design-open 边界决策

## 反模式

- ❌ 跳过 plan-context 直接读需求文档
- ❌ Phase A 没和人对齐就直接发 callback
- ❌ Phase B 替人拍板（"我已决定选 A"）
- ❌ Phase C 在 curl 之前 IM 先发 plan.md 预览 + "提交中..." ——**最常见卡死模式**。这句话让用户以为 callback 已触发，实际你根本没调 curl 就结束了会话。修法：curl 先行，拿到 200 再说话。
- ❌ Phase C callback 失败后伪装成已完成结束会话
- ❌ 在 outline 已确认后的 Phase B 又改 outline 条数
- ❌ **needs_ui REQ 忽略 design_artifact**：不读 archive 直接识别决策，结果 outline 里全是设计师已决定的 UI 选型，plan 和 design 永久漂移
- ❌ **needs_ui REQ 的 plan.md YAML 缺 `design_handoff_ref`**：破坏 plan → design 追溯链，Coordinator 会拒收
- ❌ Outline 提"Dashboard 采用什么布局 / 配色"等已在 design 阶段拍板的事项——重决策浪费用户时间并导致漂移
