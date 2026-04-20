# Phase 1 远端化 — staging 部署实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 plan-author（新建）+ spec-transformer / spec-transformer-reviewer（新版覆盖）+ spec-reviewer（补丁）同步到 staging OpenClaw，跑通一条 REQ 的 APPROVED → SPEC_READY_TO_MERGE 完整 E2E。

**Architecture:** 沿用现有 `scripts/sync_openclaw_server.sh` + `docs/agents/<name>/SKILL.md` 单一真相源 + workspace symlink 模式。本计划不新增部署基础设施，只增资产（plan-author）+ 把两个独立 SKILL.md 文件改成 symlink 让 S4 版本随 sync 一起推出。

**Tech Stack:** Markdown (SKILL.md)、JSON Schema (callback-schema.json)、Bash (sync 脚本)、SSH/scp（部署）、手工 IM 冒烟。

---

## 前提与不变量（所有 Task 共用）

- 工作分支：`feat/phase-1-remote`（已创建，当前在此分支）
- 不改本仓库的 Python 代码，只碰 `docs/agents/` / `deploy/openclaw/` / `scripts/sync_openclaw_server.sh`
- 每个 task 结束都独立 commit（不等后续 task）
- 冒烟之前不动远端；dry-run 先跑，肉眼核对 staging tree 再真实 sync
- **模板复用**：plan-author 的 workspace 文件（SOUL.md / AGENTS.md / USER.md / TOOLS.md）**直接复制 spec-author** 不改内容（这些是 OpenClaw 框架默认模板，agent 间不差异化）

---

## Task 1：plan-author workspace skeleton

**Files:**
- Create: `deploy/openclaw/workspace/agents/plan-author/SOUL.md`（复制 spec-author 同名文件，0 改动）
- Create: `deploy/openclaw/workspace/agents/plan-author/AGENTS.md`（同上）
- Create: `deploy/openclaw/workspace/agents/plan-author/USER.md`（同上）
- Create: `deploy/openclaw/workspace/agents/plan-author/TOOLS.md`（同上）
- Create: `deploy/openclaw/workspace/agents/plan-author/IDENTITY.md`（改内容）
- Create: `deploy/openclaw/agents/plan-author/models.json.template`（复制 spec-author 同名，0 改动）

- [ ] **Step 1: 复制 4 个通用 workspace 文件**

```bash
mkdir -p deploy/openclaw/workspace/agents/plan-author
cp deploy/openclaw/workspace/agents/spec-author/SOUL.md \
   deploy/openclaw/workspace/agents/spec-author/AGENTS.md \
   deploy/openclaw/workspace/agents/spec-author/USER.md \
   deploy/openclaw/workspace/agents/spec-author/TOOLS.md \
   deploy/openclaw/workspace/agents/plan-author/
```

- [ ] **Step 2: 写 IDENTITY.md**

创建 `deploy/openclaw/workspace/agents/plan-author/IDENTITY.md`，内容：

```markdown
# 规划助手

- 名称：规划助手
- Emoji：🧭
- 角色：APPROVED 需求进入 PLANNING 阶段后，作为"引导者 + 记录者"与人在 IM 上分三段（骨架提案 → 逐条决策 → 定稿提交）协作产出 plan.md，不替用户拍板。
- 绑定账号：plan-author
```

- [ ] **Step 3: 复制 models.json.template**

```bash
mkdir -p deploy/openclaw/agents/plan-author
cp deploy/openclaw/agents/spec-author/models.json.template \
   deploy/openclaw/agents/plan-author/models.json.template
```

- [ ] **Step 4: 验证文件就位**

```bash
ls deploy/openclaw/workspace/agents/plan-author/
# 期望 5 个文件：AGENTS.md IDENTITY.md SOUL.md TOOLS.md USER.md（SKILL.md 下 Task 2）
ls deploy/openclaw/agents/plan-author/
# 期望 1 个文件：models.json.template
```

- [ ] **Step 5: Commit**

```bash
git add deploy/openclaw/workspace/agents/plan-author/ deploy/openclaw/agents/plan-author/
git commit -m "feat(plan-author): workspace skeleton (IDENTITY + framework defaults)"
```

---

## Task 2：plan-author SKILL.md

**Files:**
- Create: `docs/agents/plan-author/SKILL.md`
- Create: `deploy/openclaw/workspace/agents/plan-author/SKILL.md` → symlink

**Context：** plan-author 是 PLANNING 阶段（PlanStatus.DRAFTING → READY）的 3 段 callback agent。Coordinator 侧已实现的 callback 入口（`service_app.py:975` `handle_openclaw_plan_callback`）只接受两个事件：`plan_outline_submit`、`plan_submit`。第二阶段"逐条决策"是纯 IM 对话，不 callback。

- [ ] **Step 1: 写 SKILL.md 主体**

创建 `docs/agents/plan-author/SKILL.md`（完整内容 ~150 行）：

```markdown
---
name: plan-author
description: 规划助手，APPROVED 需求进入 PLANNING 阶段后引导人完成结构化决策日志（plan.md）。分三段：骨架提案 → 逐条决策 → 定稿提交。不替用户拍板。
---

# 规划助手

## 启动流程

收到包含「请开始规划 REQ-xxx」的消息时启动。

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
  "requirement_summary": "...",
  "plan_phase": "outline_pending | decisions_in_progress | final_review_pending",
  "plan_outline": [] | [{"id": "D1", ...}]
}
```

非 200 或 `ok != true` → 立即停止并报错。若 `plan_phase` 不是 `outline_pending`：说明断点续传，按当前 phase 继续（见后续 Step）。

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

**目标**：组装 plan.md + 判断 architecture_change，调 `plan_submit` callback。

1. 组装 plan.md 正文，schema 如下：

```yaml
---
schema_version: "1.0"
req_id: "REQ-xxx"
authored_by: "ou-xxx"  # 当前 session owner
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

2. 判断是否有 `architecture_change`：
   - **任一 decision 触及项目 ARCHITECTURE** 的条目（新增服务/模块/数据模型）→ 生成 change block
   - 纯业务配置决策（如限流数值、超时时长）→ 置 null

3. architecture_change 格式（如非 null）：

```json
{
  "summary": "Add session storage via Redis",
  "changes": [{
    "section_path": "## Storage",
    "before": "",
    "after": "## Storage\n\nRedis for session state with 24h TTL",
    "rationale": "D1"
  }],
  "authorized": false
}
```

4. 调 callback：

```bash
curl -s -X POST "${COORDINATOR_BASE_URL:-http://127.0.0.1:8004}/openclaw/plan-callback" \
  -H "Content-Type: application/json" \
  -d "{\"req_id\": \"{req_id}\", \"event\": \"plan_submit\", \"payload\": {\"plan_md_content\": ${plan_md_json_escaped}, \"architecture_change\": ${arch_change_json_or_null}}}"
```

200 响应：
- `"plan_status": "ready"` → 无 architecture_change，已 commit 到 repo，流程推进
- `"plan_status": "auth_pending"` → 有 architecture_change，等人通过授权卡授权

## 异常分支

**异常 1：plan-context 404** → 说明 REQ 不存在或未到 APPROVED，立即停止并通知用户。

**异常 2：plan_submit 返回 409（invalid_state）** → coordinator 状态机拒绝，大概率是 schema 校验失败。重读响应 error message，修正后重试。

**异常 3：architecture_change 被驳回（AUTH_REJECT 信号）** → coordinator 会拉回 DRAFTING 并给 reason。重新从 Phase A 拉 plan-context（此时 plan_outline 已存在），ARCHITECTURE 可能已更新，根据 reason 改写 architecture_change 块再提交。

## 硬约束

- **⚠️ 状态机驱动**：每个阶段的最终动作必须是 callback（Phase B 例外，纯对话）。仅发 IM 不 callback 会卡死流程
- **不替用户拍板**：Phase B 讨论中若人犹豫，refine 问题而不是直接替答
- **每次 wake-up 先拉 plan-context**：避免用陈旧 state
- **plan.md schema 必须自验**：提交前确保 YAML front-matter 可解析、decisions 数组非空、每条有 chosen

## 反模式

- ❌ 跳过 plan-context 直接读需求文档
- ❌ Phase A 没和人对齐就直接发 callback
- ❌ Phase B 替人拍板（"我已决定选 A"）
- ❌ Phase C callback 失败后伪装成已完成结束会话
- ❌ 在 outline 已确认后的 Phase B 又改 outline 条数
```

- [ ] **Step 2: 建 symlink**

```bash
cd deploy/openclaw/workspace/agents/plan-author
ln -s ../../../../../docs/agents/plan-author/SKILL.md SKILL.md
cd -
# 验证
ls -la deploy/openclaw/workspace/agents/plan-author/SKILL.md
# 期望输出含 `-> ../../../../../docs/agents/plan-author/SKILL.md`
```

- [ ] **Step 3: 验证行数 + 结构**

```bash
wc -l docs/agents/plan-author/SKILL.md
# 期望 150±30 行

grep -c "^## " docs/agents/plan-author/SKILL.md
# 期望 ≥ 5（启动流程 / 异常分支 / 硬约束 / 反模式 + Step 2 的子 h3）
```

- [ ] **Step 4: Commit**

```bash
git add docs/agents/plan-author/SKILL.md deploy/openclaw/workspace/agents/plan-author/SKILL.md
git commit -m "feat(plan-author): SKILL.md with 3-phase callback contract"
```

---

## Task 3：plan-author callback-schema.json

**Files:**
- Create: `docs/agents/plan-author/callback-schema.json`

**Context：** 协调服务侧 `handle_openclaw_plan_callback` (`service_app.py:975`) 的入参契约。此 schema 作为 agent 侧的自验参考，避免 400 invalid_state。

- [ ] **Step 1: 写 schema**

创建 `docs/agents/plan-author/callback-schema.json`：

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "plan-author callback payload",
  "oneOf": [
    {
      "type": "object",
      "required": ["req_id", "event", "payload"],
      "properties": {
        "req_id": {"type": "string", "pattern": "^REQ-"},
        "event": {"const": "plan_outline_submit"},
        "payload": {
          "type": "object",
          "required": ["outline"],
          "properties": {
            "outline": {
              "type": "array",
              "minItems": 1,
              "items": {
                "type": "object",
                "required": ["id", "title", "problem"],
                "properties": {
                  "id": {"type": "string", "pattern": "^D[0-9]+$"},
                  "title": {"type": "string", "minLength": 1},
                  "problem": {"type": "string", "minLength": 1}
                }
              }
            }
          }
        }
      }
    },
    {
      "type": "object",
      "required": ["req_id", "event", "payload"],
      "properties": {
        "req_id": {"type": "string", "pattern": "^REQ-"},
        "event": {"const": "plan_submit"},
        "payload": {
          "type": "object",
          "required": ["plan_md_content"],
          "properties": {
            "plan_md_content": {"type": "string", "minLength": 1},
            "architecture_change": {
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
                        "required": ["section_path", "before", "after", "rationale"],
                        "properties": {
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
          }
        }
      }
    }
  ]
}
```

- [ ] **Step 2: 语法校验**

```bash
python3 -c "import json; json.load(open('docs/agents/plan-author/callback-schema.json'))"
# 期望无输出，退出码 0
```

- [ ] **Step 3: 协调服务端契约核对**

```bash
grep -n 'event == "plan_outline_submit"\|event == "plan_submit"\|payload.get("outline"\|payload.get("plan_md_content"\|payload.get("architecture_change"' src/requirement_workflow_v12/service_app.py
# 期望看到 5 行匹配：两个 event 字面量 + 三个 payload 字段
```

手工核对：以上 5 行的字段名与 Step 1 的 schema 必须一一对应。任何字段名不一致 → 改 schema（handler 是既存契约的真相源，不改 handler）。

- [ ] **Step 4: Commit**

```bash
git add docs/agents/plan-author/callback-schema.json
git commit -m "feat(plan-author): callback-schema.json (plan_outline_submit + plan_submit)"
```

---

## Task 4：openclaw.json.template 添加 plan-author 条目

**Files:**
- Modify: `deploy/openclaw/openclaw.json.template`（agents.list + bindings + accounts 三处）

**Context：** sync 脚本会渲染这份 template 后推到远端。agents.list 是 agent 定义；bindings 告诉 OpenClaw 把 feishu 账号路由到哪个 agent；accounts 是具体的 feishu appId/appSecret（这次 plan-author 还没注册自己的飞书 bot，**复用 spec-author 账号做 staging 临时方案** — 生产前再创独立 bot）。

**等等 — 复用账号会造成两个 agent 争抢消息**。staging 期间若要避免冲突：暂停 spec-author 只测 plan-author，或者给 plan-author 注册独立飞书 bot。**用户决策点 — 在此 Task 开始前确认**：
- 选项 X：staging 期间暂时给 plan-author 新建飞书 bot（耗时 ~20min 在飞书开发者后台操作，产出 appId/appSecret）
- 选项 Y：复用一个现有 bot（如 spec-author）做 staging，冒烟时人工保证只有 plan-author 被 @

**本任务假设选项 X**（独立 bot）。若选 Y，Step 2 的 accounts 改成现有账号的 appId/appSecret。

- [ ] **Step 1: 飞书 bot 注册**（若选项 X）

人工操作：飞书开发者后台创建应用"规划助手"，记录：
- App ID（类似 `cli_xxx`）
- App Secret（类似 `xxxxx`）
- Bot open_id（后续绑定）

暂不本任务实现；Task 执行人拿到后贴到 Step 2。

- [ ] **Step 2: 修改 openclaw.json.template — agents.list**

在 `"agents.list"` 数组中，`spec-author` 条目之前或之后插入：

```json
{
  "id": "plan-author",
  "name": "规划助手",
  "workspace": "/home/admin/.openclaw/workspace/agents/plan-author",
  "agentDir": "/home/admin/.openclaw/agents/plan-author/agent",
  "model": "minimax/MiniMax-M2.7",
  "identity": {
    "name": "规划助手",
    "theme": "PLANNING 阶段引导者 + 记录者，三段 IM 协作产出 plan.md",
    "emoji": "🧭"
  }
},
```

- [ ] **Step 3: 修改 openclaw.json.template — bindings**

在 `bindings` 数组尾部添加：

```json
{
  "agentId": "plan-author",
  "match": {
    "channel": "feishu",
    "accountId": "plan-author"
  }
},
```

- [ ] **Step 4: 修改 openclaw.json.template — accounts**

在 `channels.feishu.accounts` 对象中添加（用 Step 1 拿到的值）：

```json
"plan-author": {
  "appId": "cli_XXXXXX",
  "appSecret": "XXXXXX",
  "dmPolicy": "open",
  "groupPolicy": "open"
},
```

- [ ] **Step 5: JSON 语法校验**

```bash
python3 -c "import json; json.load(open('deploy/openclaw/openclaw.json.template'))"
# 期望无输出，退出码 0
```

- [ ] **Step 6: Commit**

```bash
git add deploy/openclaw/openclaw.json.template
git commit -m "feat(openclaw): register plan-author agent (staging bot)"
```

---

## Task 5：sync 脚本加入 plan-author

**Files:**
- Modify: `scripts/sync_openclaw_server.sh:29` (AGENTS 数组), `:34-43` (skill_for_agent)

- [ ] **Step 1: 修改 AGENTS 数组**

在 `scripts/sync_openclaw_server.sh:29`：

```bash
AGENTS=(ai-founder-brief ai-meeting-closeout spec-author spec-reviewer spec-transformer spec-transformer-reviewer)
```

改为：

```bash
AGENTS=(ai-founder-brief ai-meeting-closeout plan-author spec-author spec-reviewer spec-transformer spec-transformer-reviewer)
```

- [ ] **Step 2: 修改 skill_for_agent case**

在 `scripts/sync_openclaw_server.sh:34-44`，在 case 内的某个位置（如 `spec-author)` 之前）插入：

```bash
    plan-author) echo plan-author ;;
```

- [ ] **Step 3: 脚本语法检查**

```bash
bash -n scripts/sync_openclaw_server.sh
# 期望无输出，退出码 0
```

- [ ] **Step 4: 模拟干跑（不连接远端）**

不设 env vars 的情况下跑脚本，应该在 `require_env MINIMAX_API_KEY` 处退出（验证脚本能到执行 AGENTS 循环之前）：

```bash
bash scripts/sync_openclaw_server.sh --dry-run 2>&1 | head -5
# 期望输出 "[error] required env var MINIMAX_API_KEY is not set" 或类似
```

- [ ] **Step 5: Commit**

```bash
git add scripts/sync_openclaw_server.sh
git commit -m "feat(sync): add plan-author to AGENTS + skill_for_agent"
```

---

## Task 6：spec-transformer / spec-transformer-reviewer SKILL.md 转成 symlink

**Files:**
- Delete + Create symlink: `deploy/openclaw/workspace/agents/spec-transformer/SKILL.md`
- Delete + Create symlink: `deploy/openclaw/workspace/agents/spec-transformer-reviewer/SKILL.md`

**Context：** 当前这两个文件是独立硬拷贝（6916 / 5100 字节 ≈ 171/144 行），内容是早期版本；S4 任务 #39/#40 写的新版（70/47 行）在 `docs/agents/spec-transformer*/SKILL.md`，但没联动到 deploy 目录。本 task 改成 symlink 让新版随 sync 推出。

- [ ] **Step 1: 先确认内容差异**

```bash
diff deploy/openclaw/workspace/agents/spec-transformer/SKILL.md docs/agents/spec-transformer/SKILL.md | head -40
diff deploy/openclaw/workspace/agents/spec-transformer-reviewer/SKILL.md docs/agents/spec-transformer-reviewer/SKILL.md | head -40
```

预期有大量差异（历史遗留版本 vs S4 新版）。确认之后继续。

- [ ] **Step 2: 替换 spec-transformer SKILL.md 为 symlink**

```bash
rm deploy/openclaw/workspace/agents/spec-transformer/SKILL.md
cd deploy/openclaw/workspace/agents/spec-transformer
ln -s ../../../../../docs/agents/spec-transformer/SKILL.md SKILL.md
cd -
# 验证
ls -la deploy/openclaw/workspace/agents/spec-transformer/SKILL.md
# 期望输出 `-> ../../../../../docs/agents/spec-transformer/SKILL.md`
```

- [ ] **Step 3: 替换 spec-transformer-reviewer SKILL.md 为 symlink**

```bash
rm deploy/openclaw/workspace/agents/spec-transformer-reviewer/SKILL.md
cd deploy/openclaw/workspace/agents/spec-transformer-reviewer
ln -s ../../../../../docs/agents/spec-transformer-reviewer/SKILL.md SKILL.md
cd -
ls -la deploy/openclaw/workspace/agents/spec-transformer-reviewer/SKILL.md
```

- [ ] **Step 4: 验证解引用后的内容**

```bash
wc -l deploy/openclaw/workspace/agents/spec-transformer/SKILL.md deploy/openclaw/workspace/agents/spec-transformer-reviewer/SKILL.md
# 期望 70 / 47 行（S4 版本）
md5 deploy/openclaw/workspace/agents/spec-transformer/SKILL.md docs/agents/spec-transformer/SKILL.md
# 两个值相同
```

- [ ] **Step 5: Commit**

```bash
git add deploy/openclaw/workspace/agents/spec-transformer/SKILL.md deploy/openclaw/workspace/agents/spec-transformer-reviewer/SKILL.md
git commit -m "chore(deploy): symlink spec-transformer* SKILL.md to docs/agents source"
```

---

## Task 7：spec-reviewer pass-callback 提示强化

**Files:**
- Modify: `docs/agents/spec-reviewer/SKILL.md:73-101`

**Context：** 现版 `## 输出` 段（行 73-101）已有"⚠️ 状态机驱动硬约束"和两个 callback 分支，但 staging memory 观察到 AI pass 判决时模型仍然偶尔不发 callback（模型漂移 / 把"审查结论已形成"误判成"会话可以结束"）。本 task 不是补缺失提示，而是**强化**提示 + 显式加反模式警告。

- [ ] **Step 1: 读取现状**

```bash
sed -n '73,110p' docs/agents/spec-reviewer/SKILL.md
```

确认 `## 输出` 节现有结构。

- [ ] **Step 2: 修改 `## 输出` 段开头的硬约束**

找到 `docs/agents/spec-reviewer/SKILL.md` 中这段：

```markdown
**⚠️ 状态机驱动硬约束:** 审查结论形成后,本次会话的**最终动作必须是执行下列 callback 之一**(二选一,不可同时发、不可都不发)。**禁止仅输出审查报告文本就结束会话**——未成功调用 callback,Coordinator 不会推进状态,流程会卡死。

callback 调用失败(非 2xx)时必须立即重试,如仍失败则在回复中明确说明"callback 上报失败"并保留现场,禁止伪装成已完成。
```

替换为：

```markdown
**⚠️ 状态机驱动硬约束（pass 和 reject 同等重要）:** 审查结论形成后,本次会话的**最终动作必须是执行下列 callback 之一**(二选一,不可同时发、不可都不发)。**禁止仅输出审查报告文本就结束会话**——未成功调用 callback,Coordinator 不会推进状态,流程会卡死。

**特别警告 — pass 分支**: 当你判断 Spec "通过"时,直觉会告诉你"审查工作完成了,可以结束了"。**这个直觉是错的**。Coordinator 依赖 `ai_review_pass` callback 信号才能把状态推到 `HUMAN_CONFIRM`。没有 callback = 流程死锁 = 人工介入。**pass 不代表结束，pass 代表要发 callback**。

callback 调用失败(非 2xx)时必须立即重试,如仍失败则在回复中明确说明"callback 上报失败"并保留现场,禁止伪装成已完成。
```

- [ ] **Step 3: 在 "## 不允许的行为" 段前插入反模式段落**

在 `docs/agents/spec-reviewer/SKILL.md` 的 `## 不允许的行为` 前面，插入新段落：

```markdown
## 反模式（⚠️ 历史 staging 观察到的真实错误）

- ❌ 判决为 pass 后，输出"审查已通过，无问题"然后结束会话，**不调用 callback**
- ❌ 认为"reject 才需要 callback，pass 可以省略"
- ❌ 认为"审查报告写完 = 工作完成"（错：状态机只认 callback）
- ❌ 两个分支都不发 callback，仅回复审查结论文本

历史数据：2026-04-15 staging REQ-test-002 round 2 观察到 AI pass 判决但 callback 未发，流程卡死，需人工手动触发。**不要重复这个错误**。
```

- [ ] **Step 4: 行数合理性检查**

```bash
wc -l docs/agents/spec-reviewer/SKILL.md
# 原 110 行 + 新增 ~15 行 + 强化段 ~3 行 ≈ 128 行
```

- [ ] **Step 5: Commit**

```bash
git add docs/agents/spec-reviewer/SKILL.md
git commit -m "fix(spec-reviewer): strengthen pass-branch callback constraint with anti-pattern examples"
```

---

## Task 8：Pre-deploy checks（前置检查）

**Files:** 无修改，只做检查

**Context：** §5.1 前置检查清单。任一项失败 → 停手排查。

- [ ] **Step 1: 协调服务本地测试绿**

```bash
pytest tests/ -q
# 期望 XXX passed, 0 failed
```

失败 → 修复后再继续。

- [ ] **Step 2: 远端没有卡在 SPEC_TRANSFORMING 的 REQ**

```bash
ssh admin@47.251.81.45 "ls ~/.openclaw/state/ 2>/dev/null; cat ~/.openclaw/runtime/tasks/*.json 2>/dev/null" | head -20
```

这个路径可能在远端不是这个位置，按实际定位。目标：确认没有 REQ 正卡在 SPEC_TRANSFORMING 状态（覆盖新版 SKILL.md 会打断它）。若发现有，暂停部署并和用户讨论。

- [ ] **Step 3: 备份远端现有 SKILL.md**

```bash
mkdir -p /tmp/staging-backup-$(date +%Y%m%d)
for agent in ai-founder-brief ai-meeting-closeout spec-author spec-reviewer spec-transformer spec-transformer-reviewer; do
  scp admin@47.251.81.45:~/.openclaw/workspace/agents/$agent/SKILL.md \
      /tmp/staging-backup-$(date +%Y%m%d)/${agent}.SKILL.md
done
ls /tmp/staging-backup-$(date +%Y%m%d)/
# 期望看到 6 个 .SKILL.md 文件
```

- [ ] **Step 4: GitHub token 写权限验证**

```bash
# 取 staging 使用的 GITHUB_TOKEN（应来自 docker-compose env 或 secret store）
# 假设变量为 $GITHUB_TOKEN
gh auth status
# 或直接用 curl 验证：
curl -s -H "Authorization: Bearer $GITHUB_TOKEN" \
  https://api.github.com/repos/<staging-project-owner>/<staging-project-repo>/contents/README.md \
  | jq '.name'
# 期望输出 "README.md"，非 null
```

<staging-project> 值由用户在执行时提供（即冒烟测试 REQ 所在项目）。

- [ ] **Step 5: Git 工作区干净**

```bash
git status --short
# 期望无输出（工作区干净）
git branch --show-current
# 期望 feat/phase-1-remote
```

- [ ] **Step 6: Commit 一个检查清单结果（可选）**

无文件改动，不需要 commit。但建议把 Step 3 备份目录写进临时笔记，方便回滚时索引。

---

## Task 9：Dry-run sync + 核对

**Files:** 无修改，只运行脚本

- [ ] **Step 1: 设置环境变量**

```bash
export MINIMAX_API_KEY="<staging-miniMax-key>"
export OPENCLAW_NODE_AUTH_TOKEN="<staging-openclaw-token>"
export NANO_BANANA_PRO_API_KEY="<staging-nano-banana-key>"
```

三个 key 从 staging 运行者本地保存的 `.env.staging`（不在仓库中）取。

- [ ] **Step 2: 跑 dry-run**

```bash
scripts/sync_openclaw_server.sh --dry-run
```

- [ ] **Step 3: 核对 staging tree 输出**

脚本会输出 "[info] staging tree ready:" 后跟文件列表。期望看到：

```
  agents/plan-author/models.json
  agents/spec-author/models.json
  agents/spec-reviewer/models.json
  agents/spec-transformer/models.json
  agents/spec-transformer-reviewer/models.json
  agents/ai-founder-brief/models.json
  agents/ai-meeting-closeout/models.json
  openclaw.json
  skills/plan-author/SKILL.md
  skills/requirement-author/SKILL.md
  skills/requirement-reviewer/SKILL.md
  skills/spec-author/SKILL.md
  skills/spec-reviewer/SKILL.md
  skills/spec-transformer/SKILL.md
  skills/spec-transformer-reviewer/SKILL.md
  workspace/agents/plan-author/AGENTS.md
  workspace/agents/plan-author/IDENTITY.md
  workspace/agents/plan-author/SKILL.md
  workspace/agents/plan-author/SOUL.md
  workspace/agents/plan-author/TOOLS.md
  workspace/agents/plan-author/USER.md
  workspace/agents/spec-author/*.md
  workspace/agents/spec-reviewer/*.md
  workspace/agents/spec-transformer/*.md
  workspace/agents/spec-transformer-reviewer/*.md
  ... (其余 2 个 agent)
```

缺失任意 plan-author 文件 → 回到 Task 1 排查 symlink / 路径问题。

- [ ] **Step 4: 确认 symlink 解引用正确**

Dry-run 会把 SKILL.md 从 symlink 解引用到真实内容。快速验证 staging tree 里的 3 个 symlink：

```bash
# 从 dry-run 输出中找到 STAGING 目录（类似 /var/folders/.../tmp.xxx），查它里面的 SKILL.md
STAGING_DIR=$(scripts/sync_openclaw_server.sh --dry-run 2>&1 | grep "staging at" | sed 's/.*staging at //')
wc -l "${STAGING_DIR}/workspace/agents/plan-author/SKILL.md"
# 期望 ~150 行（和 docs/agents/plan-author/SKILL.md 一致）
```

（注意 dry-run 完成会清理 staging，上述需要速度快或临时去掉 trap 清理；简化版：比较 md5）

```bash
md5 docs/agents/plan-author/SKILL.md
# 记下 hash；dry-run 中 staging 副本应相同
```

---

## Task 10：真实 sync + 健康检查

**Files:** 无修改，只运行脚本

- [ ] **Step 1: 执行真实 sync**

```bash
scripts/sync_openclaw_server.sh
```

期望末尾输出 `[done] sync complete`。过程中输出应包含：
- `[info] pushing openclaw.json`
- 每个 agent 的 `[info] pushing agents/<agent>/agent/models.json`
- 每个 agent 的 `[info] pushing workspace/agents/<agent>/*.md`
- 每个 agent 的 `[info] pushing skills/<skill>/SKILL.md`
- `[info] restarting openclaw-gateway.service` + 返回 active

任何 `[error]` → 停止，按 §5.6 回滚预案走。

- [ ] **Step 2: systemd 服务健康**

```bash
ssh admin@47.251.81.45 "systemctl --user status openclaw-gateway.service --no-pager | head -20"
# 期望包含 "active (running)"
```

- [ ] **Step 3: agent 目录就位**

```bash
ssh admin@47.251.81.45 "ls ~/.openclaw/workspace/agents/"
# 期望包含 plan-author（以及现有 6 个 agent）
ssh admin@47.251.81.45 "ls ~/.openclaw/workspace/agents/plan-author/"
# 期望 6 个文件：SKILL.md AGENTS.md IDENTITY.md SOUL.md TOOLS.md USER.md
```

- [ ] **Step 4: SKILL.md 双份同步 parity**

```bash
for agent_skill in "ai-founder-brief:requirement-author" "ai-meeting-closeout:requirement-reviewer" "plan-author:plan-author" "spec-author:spec-author" "spec-reviewer:spec-reviewer" "spec-transformer:spec-transformer" "spec-transformer-reviewer:spec-transformer-reviewer"; do
  agent="${agent_skill%:*}"
  skill="${agent_skill#*:}"
  echo "--- $agent vs skill/$skill ---"
  ssh admin@47.251.81.45 "diff ~/.openclaw/skills/$skill/SKILL.md ~/.openclaw/workspace/agents/$agent/SKILL.md" || echo "DIVERGENT"
done
```

每组应无输出（相同）；有 DIVERGENT → sync 脚本 bug，停下排查。

- [ ] **Step 5: 新版内容确认（spec-transformer* 应为 S4 短版）**

```bash
ssh admin@47.251.81.45 "wc -l ~/.openclaw/workspace/agents/spec-transformer/SKILL.md ~/.openclaw/workspace/agents/spec-transformer-reviewer/SKILL.md"
# 期望：spec-transformer 70 行，spec-transformer-reviewer 47 行（覆盖成功）
```

- [ ] **Step 6: 记录 commit sha（用于冒烟报告）**

```bash
git log --oneline -10 > /tmp/staging-backup-$(date +%Y%m%d)/deploy-commits.txt
git rev-parse HEAD
# 记住这个 sha，冒烟报告里引用
```

---

## Task 11：E2E 手工冒烟

**Files:** 无修改，测试执行

**Context：** §六 checkpoint 序列。任一 checkpoint 未按期望发生 → 停下排查，不硬推下一步。

- [ ] **Step 1: 创建测试 REQ**

在 staging Bitable 新增一行，字段建议：
- **需求名**：staging-e2e-phase1-<date>
- **项目**：<staging-project>（Task 8 Step 4 的项目）
- **摘要**：写一个简短清晰的功能需求（目标：AI review 能 pass）
- **其他字段**：按 Bitable schema 要求最小填写

记录生成的 REQ ID（Coordinator 会分配）。

- [ ] **Step 2: Checkpoints #1-2（需求层 + PLANNING 启动）**

观察两个日志源：

```bash
# 终端 1
docker logs -f requirement-workflow-coordinator 2>&1 | grep -E "REQ-|plan-context|APPROVED"
# 终端 2
ssh admin@47.251.81.45 "journalctl --user -u openclaw-gateway.service -f"
```

期望日志序列：
- `REQ-xxx DRAFTING → AI_REVIEWING → APPROVED`
- `on_enter(APPROVED)` 钩子触发，派发 plan-author session
- `GET /queries/openclaw/plan-context/REQ-xxx` 200

若 AI review 判 reject：编辑 Bitable 字段或删了重建（本 task 假设简单需求能 pass）。

- [ ] **Step 3: Checkpoints #3-4（outline 提案 + 确认）**

IM（飞书，plan-author bot 对应的私聊或群）应出现决策骨架卡片。

人在 IM 回复"确认" / 等同肯定词。

期望：协调服务日志出现 `POST /openclaw/plan-callback event=plan_outline_submit` 200。

- [ ] **Step 4: Checkpoints #5-6（决策对话 + 定稿）**

IM 多轮对话，逐个 decision 收敛。每条人拍板后进入下一条。

最后一条收敛后，plan-author 应组装 plan.md 并调 `plan_submit` callback。

期望：协调服务日志出现 `POST /openclaw/plan-callback event=plan_submit` 200。

- [ ] **Step 5: Checkpoints #7-8（READY + repo commit）**

若 plan_submit 的 `architecture_change == null`，状态应直跳 READY（跳过 AUTH_PENDING）。

期望：
- `state.json` 的 `plan_status == "ready"`
- GitHub staging project repo 出现新 commit（含 `docs/specs/REQ-xxx/plan.md`）

```bash
gh api "repos/<staging-project>/commits?path=docs/specs/REQ-xxx/plan.md" | jq '.[0].commit.message'
# 期望返回本次 commit 的 message
```

- [ ] **Step 6: Checkpoint #9（/spec start）**

在 IM 对应的群发送 `/spec start REQ-xxx`。

期望：协调服务日志出现 SPEC_DRAFTING 启动 + spec-author session 派发。

- [ ] **Step 7: Checkpoints #10-11（spec draft + AI pass callback）**

spec-author 在飞书创建 spec 文档，完成 9 节撰写，调 spec-submit callback。然后 spec-reviewer 被派发。

AI reviewer 判决 pass 后：

**关键验证点**：协调服务日志必须出现：

```
POST /callbacks/openclaw/review-result event=ai_review_pass
```

**没有出现** → §四 补丁失效，冒烟失败。选项：
- 用 `scripts/send_openclaw_callback.py review-result --event ai_review_pass` 手工兜底（本次冒烟算降级通过，但验收标准 #3 不达成）
- 回炉 `docs/agents/spec-reviewer/SKILL.md`，重新 sync 再试

- [ ] **Step 8: Checkpoints #12-14（HUMAN_CONFIRM → 转化 → 审查）**

人在 IM 点确认 → 进入 SPEC_TRANSFORMING → spec-transformer 派发 → 产出 docs/specs/REQ-xxx/{design.md, tasks.md, ac-schedule.yaml, ...} → spec-transformer-reviewer 判 converged。

期望日志序列（新版 S4 agent 首次真实跑）：
- `POST /openclaw/spec-transform-callback event=transformer_output` 200
- `POST /openclaw/spec-transform-callback event=reviewer_verdict verdict=converged` 200
- `state.json` 的 spec 状态 → `SPEC_READY_TO_MERGE`

任何 400/500 → 停下，大概率是 S4 SKILL.md 和协调服务 handler 的 schema 对不齐。对比 `docs/agents/spec-transformer/callback-schema.json` 和 `handle_openclaw_spec_turn_callback`。

- [ ] **Step 9: Checkpoint #15（merge）**

人触发 GitHub PR merge。记录 PR URL。

- [ ] **Step 10: 冒烟报告**

创建 `docs/superpowers/reports/2026-04-19-phase1-smoke.md`，记录：
- REQ ID + Bitable 链接
- 部署 commit sha（Task 10 Step 6）
- 15 checkpoint 实际状态（绿/黄/红）
- §7.2 验收 5 条 AND 自评
- 任何意外行为 + 后续 action item

Commit 这份报告：

```bash
git add docs/superpowers/reports/2026-04-19-phase1-smoke.md
git commit -m "docs(report): Phase 1 staging smoke test results"
```

---

## Task 12：完成收尾

**Files:** 无修改，只做收尾

- [ ] **Step 1: 最终测试绿**

```bash
pytest tests/ -q
# 期望 XXX passed（本计划没改 Python 代码，不应有回归）
```

- [ ] **Step 2: 更新 TaskCreate #22**

通过任务系统把 `#22. 部署 spec-transformer / reviewer 到远端 OpenClaw` 标记 completed。

- [ ] **Step 3: 更新 memory**

创建或更新 `/Users/daxin/.claude/projects/-Users-daxin-work-requirement-workflow-feishu/memory/` 下一条新 project memory：

```markdown
---
name: Phase 1 远端化 staging 部署完成
description: 2026-04-19 plan-author + spec-transformer(S4) + spec-transformer-reviewer(S4) 部署 staging；spec-reviewer pass-callback 加固；一条 REQ 跑通 APPROVED → SPEC_READY_TO_MERGE
type: project
---

2026-04-19 完成。

**覆盖范围：** plan-author 首次部署；spec-transformer / spec-transformer-reviewer 覆盖成 S4 版本（deploy/openclaw/workspace/agents/ 里的 SKILL.md 从独立文件改为 symlink 到 docs/agents/）；spec-reviewer pass-callback 强化 + 反模式示例。

**How to apply：** 后续 spec-transformer* 的 SKILL.md 修订只改 docs/agents/，不要再碰 deploy/ 目录下的文件（它是 symlink）。验收报告在 docs/superpowers/reports/2026-04-19-phase1-smoke.md。

**未覆盖：** architecture_change 分支、design-author、多 REQ 并发 — 留给后续 REQ 回归补测。
```

然后在 MEMORY.md 索引中加一行指针。

- [ ] **Step 4: 分支完成流程**

用 `superpowers:finishing-a-development-branch` skill 处理 `feat/phase-1-remote` 分支（选择合并 / PR / 保留）。

---

## 自检（已在此计划结束前手工走过一遍）

**1. Spec 覆盖：**
- §一 目标与范围 → 全部 12 个 Task 的组合覆盖完整 E2E
- §二 产出清单 → Task 1-7 涵盖所有新建/修改
- §三 plan-author SKILL.md 设计 → Task 2 的 SKILL.md 主体按 3 阶段分段
- §四 spec-reviewer 补丁 → Task 7
- §五 部署流程 → Task 8-10
- §六 E2E 手工冒烟 → Task 11
- §七 风险与验收 → Task 11 Step 10 报告对齐 5 条验收 AND
- **已知 gap**：§五 5.1.2 "人工部分独立 bot 注册" 需要用户在 Task 4 Step 1 介入，非 agentic。Plan 内已标红。

**2. Placeholder 扫描：**
- 无 TBD/TODO；`<staging-project>` 和 `<date>` 等是占位参数，执行时由运行者填入，非 plan 缺口。
- Task 4 有一个决策分支（选项 X vs Y），假设 X 并在 Step 2/4 给出 Y 的 fallback。

**3. 类型/命名一致性：**
- callback event 名称：`plan_outline_submit` / `plan_submit` — 跨 Task 2 / Task 3 / Task 11 全部一致（与 `service_app.py:987-991` 对齐）
- 路径：`docs/agents/plan-author/` / `deploy/openclaw/workspace/agents/plan-author/` — 全部 Task 一致
- Symlink 路径：`../../../../../docs/agents/<name>/SKILL.md`（5 级 `../`）——和现有 spec-reviewer/spec-author 路径一致（参考 `ls -la deploy/openclaw/workspace/agents/spec-reviewer/SKILL.md`）

---

## 执行提示

本计划共 12 个 Task，估算执行时间：
- Task 1-7（写资产）：2-3 小时（含 plan-author SKILL.md 首版起草时间最长）
- Task 8-10（部署）：30-60 分钟
- Task 11（E2E 冒烟）：2-4 小时（取决于 AI review 是否一次过 + plan-author 首版是否需要热修）
- Task 12（收尾）：15 分钟

**执行模式建议**：subagent-driven-development。原因：
- Task 2（SKILL.md 150 行起草）是独立 creative 任务，适合隔离 subagent
- Task 4-7 是独立修改，彼此不耦合
- Task 8-11 是部署/冒烟，各 Task 内部有顺序依赖，但 Task 之间可切割

**中断点**：
- Task 4 Step 1（飞书 bot 注册）必须人工
- Task 8 Step 2（在途 REQ 检查）必须人工判决
- Task 11 全程必须人工
