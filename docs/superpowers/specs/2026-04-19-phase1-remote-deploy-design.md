# Phase 1 远端化 — staging 部署设计

> 本规格定义把 PLANNING 阶段 + SPEC_TRANSFORMING 阶段的 agent 首次部署到 OpenClaw `47.251.81.45` staging 节点，并通过一条 REQ 的完整 E2E 冒烟验证接通性。落地后，协调服务代码层的 PLANNING + SPEC_TRANSFORMING 实现将首次获得真实远端联调证据。

| 版本 | 日期 | 说明 |
|---|---|---|
| v1 | 2026-04-19 | 首版：3 个 agent 打包部署（plan-author 全新 + spec-transformer* 覆盖）+ spec-reviewer pass-callback 补丁 + 手工 E2E 冒烟 |

---

## 一、目标与范围

**staging 部署 3 个新/更新 agent，打通 1 条 REQ 的完整 E2E**：

| Agent | 动作 | 说明 |
|---|---|---|
| `plan-author` | 0 → 1 全新创建 | PLANNING 阶段 agent，SKILL.md 从 0 写 |
| `spec-transformer` | 覆盖远端 | 本仓库 S4 版本（70 行）替换远端旧版（171 行，schema 已过时）|
| `spec-transformer-reviewer` | 覆盖远端 | 本仓库 S4 版本（47 行）替换远端旧版（144 行）|
| `spec-reviewer` | SKILL.md 补丁 | 修复 AI pass 分支不主动 callback 的 gap |

**完整 E2E 链路**：

```
REQ 创建 → APPROVED
  → plan-author (新) 三段卡片：outline_submit → decisions 对话 → plan_submit
  → PlanStatus=READY（不带 architecture_change，直跳）
  → /spec start → spec-author → spec-reviewer（AI pass 现在也会 callback）
  → SPEC_DRAFTING 完成
  → spec-transformer (新版) → spec-transformer-reviewer (新版)
  → SPEC_READY_TO_MERGE
```

**不做**（刻意 out of scope）：
- design-author / DESIGNING 阶段（代码层未实现）
- plan-reviewer（设计明确：人即 reviewer）
- 自动化 smoke 脚本
- CI 集成
- Bootstrap 阶段
- production 部署
- 历史兼容性（用户明确"staging 不关注"）
- architecture_change 分支、并发多 REQ、crash 恢复（留给后续 REQ 补测）

---

## 二、产出清单

**新建**（plan-author）：

- `docs/agents/plan-author/SKILL.md` — skill 源文件，目标 150±30 行，覆盖 3 个 callback 事件 + 卡片契约
- `docs/agents/plan-author/callback-schema.json` — callback payload JSON Schema（`plan_outline_submit` / `plan_submit`）
- `deploy/openclaw/agents/plan-author/models.json.template` — 模型配置（沿用 spec-author 同款）
- `deploy/openclaw/workspace/agents/plan-author/IDENTITY.md` / `SOUL.md` / `AGENTS.md` / `TOOLS.md` / `USER.md` — workspace 文件（结构沿用 spec-author）
- `deploy/openclaw/workspace/agents/plan-author/SKILL.md` — symlink 到 `docs/agents/plan-author/SKILL.md`
- `deploy/openclaw/openclaw.json.template` 里新增 `plan-author` 条目

**修改**：

- `scripts/sync_openclaw_server.sh` — `AGENTS` 数组 + `skill_for_agent` case 表加入 `plan-author`
- `docs/agents/spec-reviewer/SKILL.md` — pass 分支显式 callback 约束（~15 行，见 §五）

**已在仓库、只需随 sync 推出去**：

- `docs/agents/spec-transformer/SKILL.md`（70 行，S4 任务 #39 产出）
- `docs/agents/spec-transformer-reviewer/SKILL.md`（47 行，S4 任务 #40 产出）
- `deploy/openclaw/workspace/agents/spec-transformer*/`（完整 workspace 已就绪）

---

## 三、plan-author SKILL.md 设计

plan-author 是 **3 段 callback 的引导者 + 记录者**——决策由人拍板，agent 不替代设计者。核心行为分三阶段，和 coordinator 的 `plan_phase` 字段严格对齐。

### 3.1 阶段 1 —— OUTLINE_PENDING（骨架提案）

**入参**：
- coordinator 钩子 `on_enter(PlanStatus.DRAFTING)` 派发 plan-author session
- agent 拉 `GET /queries/openclaw/plan-context/<req>`，得到 project_repo / ARCHITECTURE 摘要 / tech_stack / summary / approved requirement 原文

**行为**：
- agent 基于 requirement summary + ARCHITECTURE 初步分析需要做的决策条数
- 在 IM 和人对齐"要做的决策条数 + 每条的 title + problem"，用结构化 markdown 贴 outline
- 人回复确认 → agent 调用 callback

**出口 callback**：
```
POST /openclaw/plan-callback
{
  "req_id": "...",
  "event": "plan_outline_submit",
  "payload": {
    "outline": [
      {"id": "D1", "title": "...", "problem": "..."},
      {"id": "D2", "title": "...", "problem": "..."}
    ]
  }
}
```

### 3.2 阶段 2 —— DECISIONS_IN_PROGRESS（逐条决策）

**入参**：coordinator 接到 outline_submit 后把 plan_phase 推到 `DECISIONS_IN_PROGRESS`，IM 发 plan_decision_card

**行为**：
- agent 逐条引导每个 decision：给出 2-3 个 options + tradeoffs + 推荐
- 和人多轮讨论直到当条收敛，由人点"下一条"或文字表达
- 这一段**不走 callback**——纯 IM 对话，plan-author 内部 scratchpad 管理当前进度

**不变量**：agent 不能替人拍板；若人犹豫，refine 问题而不是替答。

### 3.3 阶段 3 —— FINAL_REVIEW_PENDING（定稿提交）

**入参**：N 条 decision 收敛后，人触发定稿（IM 按钮或文字）

**行为**：
- agent 把所有 decisions 组装成 `plan.md` 正文（schema 见下）
- 判断是否需要 `architecture_change`：若任意 decision 触及 ARCHITECTURE → 生成 change block（`section_path` / `before` / `after` / `rationale`）；否则置 null
- callback 提交

**出口 callback**：
```
POST /openclaw/plan-callback
{
  "req_id": "...",
  "event": "plan_submit",
  "payload": {
    "plan_md_content": "---\nschema_version: \"1.0\"\nreq_id: \"REQ-xxx\"\ndecisions: [...]\n---\n...",
    "architecture_change": null | {
      "summary": "...",
      "changes": [{"section_path": "## X", "before": "...", "after": "...", "rationale": "Dn"}],
      "authorized": false
    }
  }
}
```

coordinator 根据 `architecture_change` 是否存在决定分叉：
- `None` → 直跳 `PlanStatus.READY`，触发 `commit_plan_artifacts` 只提交 plan.md
- 非空 → `AUTH_PENDING`，发授权卡给人 → 人授权后推进 READY，commit 时同时写 plan.md + ARCHITECTURE.md

### 3.4 SKILL.md 结构（仿 spec-author 152 行格式）

| 段落 | 约定行数 | 内容 |
|---|---|---|
| Identity | ~15 | 你是谁 / 非你职责 / 不替人拍板 |
| Workflow 三阶段 | ~80 | 每阶段：入参、期望对话模式、callback payload 样板 |
| plan.md schema 示例 | ~30 | 结构化 decision + optional architecture_change 完整样例 |
| 异常分支 | ~15 | architecture_change 被拒 / plan-context 查询 404 / schema 校验失败 |
| Tools 引用 | ~5 | 指向 `TOOLS.md` |

### 3.5 关键约束（写进 Identity/Workflow）

1. 只负责"记录决策"，不越过"替用户拍板"
2. 每次 wake-up 先拉 plan-context（避免用陈旧 state）
3. plan.md schema 必须自验一次再 callback，否则 coordinator 会 400
4. architecture_change 被 coordinator 拉回（AUTHORIZATION_REJECT）时，agent 重新拉 ARCHITECTURE 最新版再重写 change block

---

## 四、spec-reviewer pass-callback 补丁

**问题**：当前 `docs/agents/spec-reviewer/SKILL.md`（110 行）在 **AI reject 分支**有明确 callback 指令，**AI pass 分支**却缺这一步——agent 判完 pass 就结束会话，不发 `review-result` callback，流程卡在 `AI_REVIEW` 状态。

**修复草稿**（加到 SKILL.md workflow 判决段落）：

```markdown
## Step N：输出判决 — **无论 pass 或 reject，都必须 callback**

判决完成后，**无条件**调用 review-result callback（这是硬约束，不是可选）：

- 若结论为 **reject**：
  `POST /callbacks/openclaw/review-result`
  payload: `{event: "ai_review_reject", reasons: [...], suggestions: [...]}`
- 若结论为 **pass**：
  `POST /callbacks/openclaw/review-result`
  payload: `{event: "ai_review_pass"}`

**即使 pass 分支看起来"审核结束流程可以终止"，你仍然必须发 callback**——coordinator 依赖这个信号把状态推进到 `HUMAN_CONFIRM`。遗漏会导致流程死锁，必须人工介入。

## 反模式（⚠️ 不要这样做）

- ❌ pass 时直接结束会话不 callback
- ❌ 认为"review 已完成 = 可以静默退出"
```

**验证**：staging 冒烟跑一条会被 AI 判 pass 的 REQ（简单 requirement 容易 pass），看日志是否出现 `/callbacks/openclaw/review-result` with `event=ai_review_pass`；未出现则修复失败。

---

## 五、部署流程

沿用 `scripts/sync_openclaw_server.sh` 既有 SOP，本次不新写部署脚本。

### 5.1 前置检查（~5 min）

1. `ssh admin@47.251.81.45 "ls ~/.openclaw/state/"` 确认 staging 没有 REQ 卡在 SPEC_TRANSFORMING（防止覆盖新版 SKILL.md 打断在途流程）
2. 备份远端 SKILL.md 一份到本地：`scp -r admin@47.251.81.45:~/.openclaw/workspace/agents/spec-transformer* /tmp/staging-backup-$(date +%Y%m%d)/`（sync 脚本只自动备份 openclaw.json，SKILL.md 需手动）
3. 本地 `pytest tests/ -q` 确保绿
4. `git status` 干净 + 在 `feat/phase-1-remote` 分支
5. staging `GITHUB_TOKEN` 写权限验证：`gh api repos/<staging-project>/contents/README.md` 能 200

### 5.2 改 sync 脚本

- `scripts/sync_openclaw_server.sh` 的 `AGENTS` 数组加入 `plan-author`
- `skill_for_agent` case 表加入 `plan-author → plan-author`
- 单独 commit

### 5.3 Dry-run 预演

```bash
export MINIMAX_API_KEY=... OPENCLAW_NODE_AUTH_TOKEN=... NANO_BANANA_PRO_API_KEY=...
scripts/sync_openclaw_server.sh --dry-run
```

预期输出应包含：新建 `plan-author/`、覆盖 `spec-transformer*/SKILL.md`、更新 `spec-reviewer/SKILL.md`、写入新 `openclaw.json`。逐项肉眼核对。

### 5.4 真实 sync

```bash
scripts/sync_openclaw_server.sh
```

脚本会自动：`cp -L` 解引用所有 SKILL.md symlink → tar-over-ssh → 替换远端 → `openclaw.json.bak-<ts>` 备份 → `systemctl --user restart openclaw-gateway.service`

### 5.5 部署后健康检查（~5 min）

1. `ssh admin@47.251.81.45 "systemctl --user status openclaw-gateway.service"` 看 active
2. `diff` 一对 SKILL.md 两份副本（`skills/` vs `workspace/agents/`）应为空
3. `ls ~/.openclaw/workspace/agents/` 应包含 `plan-author`
4. agent 各自 `SKILL.md` 的 md5 和本地相同

### 5.6 回滚预案

冒烟阶段若发现 SKILL.md 严重错误：
1. `ssh` 过去 `mv openclaw.json.bak-<ts> openclaw.json`（sync 脚本自动备份）
2. `scp` 第 5.1.2 步留底的 SKILL.md 覆盖回去
3. `systemctl --user restart openclaw-gateway.service`

---

## 六、E2E 手工冒烟

### 6.1 测试 REQ

在 staging Bitable 新建一条**简单需求**（内容尽量短，便于 AI review 判 pass），项目选已有 `ProjectConfig` 的 staging 项目（首选 `requirement-workflow-feishu` 本身 dogfood，或已配置的测试项目）。

### 6.2 Checkpoint 序列（15 个）

| # | 触发 | 期望状态 | 观察手段 |
|---|---|---|---|
| 1 | Bitable 新建行 | DRAFTING → AI_REVIEWING → APPROVED（若简单）| 日志 + Bitable 字段 |
| 2 | `on_enter(APPROVED)` | PLANNING 钩子触发 → plan-author 拉 plan-context | 日志 `/queries/openclaw/plan-context/<req>` |
| 3 | plan-author 发 outline | IM 收到决策骨架提案 | IM 可见 |
| 4 | 人点确认 outline | `plan_outline_submit` callback → `plan_phase=DECISIONS_IN_PROGRESS` | 日志 + `state.json` |
| 5 | 逐条决策对话 | IM 多轮 Q&A，每条收敛 | IM 可见 |
| 6 | plan-author 提交 plan.md | `plan_submit` callback（无 architecture_change）| 日志 |
| 7 | coordinator 分叉 | `PlanStatus=READY`（直跳）| `state.json` |
| 8 | `on_enter(READY)` | `commit_plan_artifacts` 把 plan.md 提交到 project_repo | GitHub commit |
| 9 | `/spec start REQ-xxx` | SPEC_DRAFTING 启动 → spec-author 派发 | 日志 |
| 10 | spec-author 出 draft | spec-reviewer 派发 | 日志 |
| 11 | AI review 判决 | **pass → 显式 callback（验证 §四 补丁）** | 日志 `/callbacks/openclaw/review-result` with `event=ai_review_pass` |
| 12 | HUMAN_CONFIRM | 人点"确认" | IM 可见 |
| 13 | `on_enter(SPEC_TRANSFORMING)` | spec-transformer 派发 | 日志 |
| 14 | spec-transformer-reviewer 判决 | 若 pass → `SPEC_READY_TO_MERGE` | `state.json` |
| 15 | 人触发 merge | SPEC PR 合入 | GitHub |

### 6.3 观察工具

- 协调服务日志：`docker logs -f requirement-workflow-coordinator`（staging docker-compose 容器）
- OpenClaw 日志：`ssh admin@47.251.81.45 "journalctl --user -u openclaw-gateway.service -f"`
- 状态快照：`ssh admin@47.251.81.45 "cat ~/.openclaw/state/requirements.json | jq '.\"REQ-xxx\"'"`（路径冒烟时确认）

### 6.4 停止条件

任何 checkpoint 未按期望发生，暂停排查；不硬推后续步骤。

---

## 七、风险与验收

### 7.1 风险

| # | 风险 | 处理方式 |
|---|---|---|
| R1 | plan-author SKILL.md 首版行为偏差（不按 3 段 callback 走）| 冒烟发现 → 热修 SKILL.md + re-sync；§三 阶段契约已明确，首版必然要迭代 |
| R2 | 覆盖后的 spec-transformer SKILL.md 与协调服务 callback schema 对不上 | 本仓库 `docs/agents/spec-transformer/callback-schema.json` 是唯一真相源；deploy 前 grep 确认 schema 字段和 `handle_openclaw_transformer_callback` 一致 |
| R3 | spec-reviewer pass 补丁失效（agent 仍然不 callback）| 用 `scripts/send_openclaw_callback.py review-result --event ai_review_pass` 手工兜底 + 回炉 SKILL.md |
| R4 | staging 在途 REQ 被覆盖打断 | §5.1 前置检查阻断：若有 REQ 在 SPEC_TRANSFORMING 则暂停部署 |
| R5 | OpenClaw gateway 重启失败 | sync 脚本自动备份 `openclaw.json.bak-*`；手工 `systemctl restart`；SKILL.md 回滚靠 §5.1.2 的本地留底 |
| R6 | `commit_plan_artifacts` 对 staging 项目仓库无写权限 | §5.1.5 前置验证 `GITHUB_TOKEN` repo scope |

### 7.2 验收标准（5 条 AND）

1. **部署成功**：`ls ~/.openclaw/workspace/agents/` 含 `plan-author`；4 个相关 agent 的 `diff skills/ workspace/agents/` 均为空
2. **E2E 打穿**：§六 冒烟跑到 `SPEC_READY_TO_MERGE`，checkpoint 全部绿
3. **AI reviewer pass 自动 callback**：checkpoint #11 看到 `ai_review_pass` callback 且**没有**手工发 `send_openclaw_callback.py`
4. **Artifacts 真实落地**：`docs/specs/REQ-xxx/plan.md` 和 `docs/specs/REQ-xxx/{supersedes.yaml, tasks.md, ARCHITECTURE.md, ...}` 在 staging 项目 repo 中可见
5. **无人工 hack**：全程无需直连远端改状态、无需手动触发 callback

### 7.3 刻意 out of scope

- architecture_change 分支（留给第二条 REQ 回归补测）
- design-author / DESIGNING 阶段行为
- 并发多 REQ
- 故障恢复 / crash restart 演练
- automated smoke 脚本化

---

## 八、后续工作（非本 spec 范围）

- Phase 1 冒烟跑通后，补第二条 REQ（带 architecture_change）回归 AUTH_PENDING 闸门
- DESIGNING 阶段代码层 + design-author agent 部署（独立 spec）
- Bootstrap 层设计（见 memory `project_bootstrap_plan_design_direction.md`）
- spec-transformer callback-schema 真相源集中化（本仓库 vs OpenClaw 仓库去重）
