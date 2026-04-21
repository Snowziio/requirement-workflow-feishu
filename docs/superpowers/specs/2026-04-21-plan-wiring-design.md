# Plan-Wiring 卡片流程设计

**日期**：2026-04-21
**范围**：把 APPROVED 后的卡片流程接上 Plan 阶段，让 `APPROVED → Plan 撰写 → Plan READY → Spec 撰写` 成为唯一路径。
**MVP Scope**：`architecture_change=None` 路径；不实现 `AUTH_PENDING`；仅一张终审卡；驳回采用纯状态重置（无自动 DM 唤醒）。

> **2026-04-21 methodology callout（时相分段 SOT）**：本设计中 `plan_submit` 分支目前假设"落 GitHub PR 并切换 `PlanStatus.READY`"。自 2026-04-21 方法论 §4.5 时相分段 SOT 模型落地后，实际语义调整为：plan 构造期 SOT 是**飞书 plan docx**（Coordinator 在 DRAFTING 时创建），人工通过终审卡后 `on_enter(PlanStatus.READY)` hook 从飞书冻结版**单向同步**到 GitHub `plans/<req_id>.md`（而非直接把 plan-author 回传的文本作为 GitHub 源文件）。本 spec 的卡片流程与人工闸门不变；变的是落盘目标媒介。详见 [§4.5](../../context/harness-engineering-methodology-v2.0.md#45-构造期-sot-与实施期-sot-的时相分段) 与 [planning-harness-layer §6.2](../../context/layers/planning-harness-layer.md)。

## 背景

PLANNING 阶段的状态机、CoordinatorService 方法、hook、HTTP endpoint（plan-context / plan-callback）已在 2026-04-19 落盘并实施完毕（见 `2026-04-19-planning-phase-design.md`）。但卡片流程仍停留在旧路径：APPROVED 后的 `final_review_passed` 卡片直接提供「开始 Spec 撰写」按钮，Plan 阶段在用户视角完全不可见、`plan_status` 始终为 None。本次任务把 Plan 嵌入卡片流。

## §1 整体流程与状态机修正案

### 1.1 端到端时序（test-1 场景，architecture_change=None）

```
APPROVED
  │
  ▼
final_review_passed 卡【改】— 按钮「开始 Plan 撰写」→ send_plan_author_start【新】
  │
  │ service.plan_start()  （plan_status=DRAFTING, plan_phase=OUTLINE_PENDING）
  │ gateway.send_text(plan-author handoff)
  ▼
plan-author 多轮 IM → 用户确认 outline
  │
  │ plan-author → POST /openclaw/plan-callback  event=plan_outline_submit
  │ set_plan_outline() → plan_phase=DECISIONS_IN_PROGRESS
  ▼
plan-author 决策循环 → 用户敲定终稿
  │
  │ plan-author → POST /openclaw/plan-callback  event=plan_submit【行为变更】
  │   ├─ 不再直接调 service.plan_submit
  │   ├─ 保存 pending_plan_review = {plan_md_content, project_context_change}
  │   ├─ plan_phase = FINAL_REVIEW_PENDING
  │   └─ 推送 plan_submitted_pending_review 卡【新】
  ▼
plan_submitted_pending_review 卡【新】
  ├─「通过」→ approve_plan_submit【新】
  │     └─ service.plan_submit(**pending_plan_review)
  │         └─ state DRAFTING→READY, hook 提交 GitHub Plan PR → 回填 plan_pr_url
  │     └─ 清空 pending_plan_review
  │     └─ 推送 plan_ready 卡【新】
  │
  └─「需要修改」→ reject_plan_submit【新】
        └─ 清空 pending_plan_review
        └─ plan_phase = DECISIONS_IN_PROGRESS
        └─ 用户须手动再 DM plan-author 继续（MVP：无自动唤醒）

plan_ready 卡【新】— 按钮「开始 Spec 撰写」→ send_spec_author_start【守卫收紧】
  │
  │ 守卫：plan_status == READY
  ▼
SpecContextBuilder（既有闸门 spec_context.py:62 已校验 plan_status==READY）
```

### 1.2 状态机修正

| 守卫 | 原 | 改 |
|---|---|---|
| `plan_start()` 允许条件 | `APPROVED` + (`needs_ui=False` 或 `design_status=READY`) | **仅 `APPROVED`** |
| `spec_start` 卡片层守卫 | `APPROVED` + `spec_status in {None, DRAFTING}` | 追加 `plan_status == READY` |
| `spec-context` endpoint 守卫 | 已有 `plan_status==READY` 闸门 | 不改 |

**放弃 `needs_ui` 相关耦合的原因**：当前没有 UI 设计流程，`design_status` 无人写入，引入依赖只会把 Plan 卡死。Phase 2 明确 UI 流程后再加。

## §2 卡片与 handler 细节

### 2.1 三个卡片触发点（dispatch_transition_notifications）

| trigger | 旧 | 新 | 时机 |
|---|---|---|---|
| `final_review_passed` | 「开始 Spec 撰写」 | 「开始 Plan 撰写」 | AI final review pass → APPROVED 进入时既有 |
| `plan_submitted_pending_review` | — | 「通过」/「需要修改」 | plan-callback plan_submit 分支 |
| `plan_ready` | — | 「开始 Spec 撰写」 | approve_plan_submit 成功后 |

### 2.2 Handler 变更

- **`send_plan_author_start`【新】**
  - 守卫：`status==APPROVED`
  - 动作：`service.plan_start(req_id)` → 调 `_build_plan_author_handoff_text(requirement)` → `gateway.send_text(operator, handoff_text)`
  - 错误：`plan_start` 抛 `ValueError`（已在错误状态）→ toast 报错

- **plan-callback `plan_submit` 分支【行为变更】**（service_app.py:1224-1237）
  - 原：直接调 `service.plan_submit(...)`（会推进 DRAFTING→READY 并触发 hook 提交 GitHub）
  - 新：仅把草稿缓存到 `pending_plan_review`，**不触发 state machine**：
    ```python
    requirement.pending_plan_review = {
        "plan_md_content": payload.get("plan_md_content", ""),
        "project_context_change": payload.get("project_context_change") or payload.get("architecture_change"),
        "submitted_at": utc_now().isoformat(),
    }
    requirement.plan_phase = PlanPhase.FINAL_REVIEW_PENDING
    self._save_state()
    self._dispatch_transition_notifications(requirement, trigger="plan_submitted_pending_review")
    return 200, {"req_id": req_id, "plan_status": "DRAFTING", "plan_phase": "FINAL_REVIEW_PENDING"}
    ```

- **`approve_plan_submit`【新】**
  - 守卫：`pending_plan_review is not None`；若 `project_context_change` 非空 → MVP toast 拒绝
  - 动作：
    1. `service.plan_submit(req_id, plan_md_content=pending_plan_review["plan_md_content"], project_context_change=None)`（state DRAFTING→READY；hook 写 GitHub + 清 `pending_plan_draft`）
    2. 清空 `pending_plan_review`
    3. `_save_state()`
    4. `_dispatch_transition_notifications(requirement, trigger="plan_ready")`
  - 错误：`plan_submit` 抛异常 → `pending_plan_review` 保留（不要提前清），toast 报错允许重试（见 §4.2）

- **`reject_plan_submit`【新】**
  - 守卫：`pending_plan_review is not None`
  - 动作：清空 `pending_plan_review`；`plan_phase = DECISIONS_IN_PROGRESS`；`_save_state()`
  - 无卡片推送——用户自行重新 DM plan-author（MVP 行为）

- **`send_spec_author_start`【守卫收紧】**（service_app.py:1550）
  - 追加条件：`plan_status == READY`，否则 toast「Plan 尚未 READY」

### 2.3 分层决策

`plan_ready` 卡的推送放在 `approve_plan_submit` handler 内部，**不放在 `_commit_plan_and_maybe_architecture` hook**。理由：保持 `CoordinatorService` 不依赖 `service_app` / Feishu 层，hook 只负责 GitHub 副作用。

## §3 数据流 + 字段生命周期

### 3.1 Happy-path 字段迁移表

| 时间点 | 触发 | 字段变更 | 持久化 |
|---|---|---|---|
| T0 APPROVED | requirement reviewer 通过 | `status=APPROVED`；`plan_status=None` | 既有 |
| T1 点击「开始 Plan 撰写」 | `send_plan_author_start` | — | — |
| T2 plan-author 调 `/plan-context` | GET endpoint（既有） | `plan_status=DRAFTING`；`plan_phase=OUTLINE_PENDING`（由 `plan_start()`） | 既有 |
| T3 outline 确认 | `plan_outline_submit` → `set_plan_outline` | `plan_outline=[...]`；`plan_phase=DECISIONS_IN_PROGRESS` | service_app.py:1222 |
| T4 plan-author 终稿 | `plan_submit` callback【变更】 | `pending_plan_review={...}`；`plan_phase=FINAL_REVIEW_PENDING`；`plan_status` 仍 DRAFTING | 新增 `_save_state()` |
| T5 推送审查卡 | 同 T4 尾部 | — | — |
| T6 点击「通过」 | `approve_plan_submit` | `plan_status=READY`（由 state machine）；`plan_pr_url` 写入（由 hook）；`pending_plan_review=None` | handler 内 `_save_state()` |
| T7 推送 plan_ready 卡 | 同 T6 尾部 | — | — |
| T8 点击「开始 Spec 撰写」 | `send_spec_author_start`【守卫收紧】 | — | — |
| T9 spec-author 调 `/spec-context` | 既有 | `spec_status=DRAFTING` | 既有 |

### 3.2 新增字段生命周期

- **`pending_plan_review: dict | None`**（新增字段，Requirement 上）
  - 结构：`{"plan_md_content": str, "project_context_change": dict | None, "submitted_at": iso8601}`
  - 诞生：T4。销毁：T6（通过成功后）或驳回。
  - 重入：plan-author 重试 plan_submit → 覆盖 pending，卡片可重复推送（MVP 不去重）。
  - **与既有 `pending_plan_draft` 区分**：`pending_plan_draft` 是 `service.plan_submit()` 内部的瞬时载荷（入口写入 → hook 读出 → 清空），本次不改动；`pending_plan_review` 是卡片审查阶段的持久化缓冲，命名独立避免语义重叠。

- **`plan_phase: PlanPhase | None`**
  - 写入者：`plan_start`（OUTLINE_PENDING）、`set_plan_outline`（DECISIONS_IN_PROGRESS）、plan-callback plan_submit 分支（FINAL_REVIEW_PENDING）、`approve_plan_submit`（归零或保留）、`reject_plan_submit`（回退至 DECISIONS_IN_PROGRESS）

- **`plan_pr_url: str`**：写入者 `_commit_plan_and_maybe_architecture` hook（既有）；读者 `plan_ready` 卡。

### 3.3 spec_start 守卫 diff（service_app.py:1550）

```python
# before
if requirement.status != WorkflowStatus.APPROVED or requirement.spec_status not in {None, SpecStatus.DRAFTING}:

# after
if (
    requirement.status != WorkflowStatus.APPROVED
    or requirement.spec_status not in {None, SpecStatus.DRAFTING}
    or requirement.plan_status != PlanStatus.READY
):
    plan_label = requirement.plan_status.value if requirement.plan_status else "None"
    return 200, {"toast": {"type": "error", "content": f"当前需求 Plan 尚未 READY（plan_status={plan_label}），不能启动 Spec 撰写。"}}
```

`spec_context.py:62` 已有等价守卫，这里是第二道闸（卡片层即时反馈 + endpoint 层防绕行）。

### 3.4 `_save_state()` 调用点

新增：`approve_plan_submit` 尾部、`reject_plan_submit` 尾部、plan-callback plan_submit 分支（语义变：保存的是 pending，不是终态）。

## §4 错误路径与边界

### 4.1 错误矩阵

| # | 场景 | 表现 | 恢复 |
|---|---|---|---|
| E1 | plan-callback 收 `plan_submit` 但 `plan_status != DRAFTING` | 400 `invalid_state` | plan-author 报错 |
| E2 | 「通过」时 `pending_plan_review is None` | toast「Plan 草稿不存在」 | plan-author 重新提交 |
| E3 | 「通过」时 `service.plan_submit()` 抛异常（hook GitHub 失败） | toast 报错；pending 保留；`plan_status` 仍 DRAFTING | 用户再点「通过」重试 |
| E4 | 「需要修改」时 pending 已空 | toast「无可驳回草稿」 | 无需恢复 |
| E5 | `send_spec_author_start` 但 `plan_status != READY` | toast §3.3 文案 | 等 plan_ready 卡 |
| E6 | plan-author 跳过 outline 直接 plan_submit | MVP 接受，outline 空 | 由 agent 自律 |
| E7 | `plan_ready` 卡投递失败 | 日志 warning；state 已 READY | 无自动补发，用户可 `/create req` 查询 |
| E8 | 驳回后 plan-author 不重发 | 流程停滞 | 人工 DM；MVP 不引入超时 |

### 4.2 原子性（E3）

`service.plan_submit()` 内部：state 机转 → hook 写 GitHub → `_save_state()`。若 hook 抛异常：
- **既有实现**需核实是否回滚到 DRAFTING。
- 本任务**不扩** CoordinatorService 错误语义；`approve_plan_submit` handler 层 catch 后保留 `pending_plan_review` + 返回可重试 toast。

### 4.3 边界

- 并发不同 req 点「通过」：互不影响。
- `architecture_change != None`：MVP 显式拒绝（toast）。
- state.json 重启：`pending_plan_review` 持久化，按钮仍可用。
- 同 req 多次推送 `plan_submitted_pending_review` 卡：MVP 允许共存。

## §5 测试策略

### 5.1 service_app 单测（新增 `tests/test_service_app_plan_wiring.py`）

- `test_send_plan_author_start_dispatches_dm`
- `test_send_plan_author_start_rejects_if_not_approved`
- `test_plan_callback_plan_submit_stores_pending_and_pushes_card`
- `test_approve_plan_submit_transitions_to_ready_and_clears_pending`
- `test_approve_plan_submit_rejects_if_no_pending` (E2)
- `test_approve_plan_submit_rejects_if_architecture_change_present`
- `test_reject_plan_submit_clears_pending_and_resets_phase`
- `test_send_spec_author_start_rejects_if_plan_not_ready`
- `test_send_spec_author_start_allows_when_plan_ready`

### 5.2 coordinator_service

既有测试不改。可选：`test_plan_submit_is_idempotent_when_called_twice`（文档化语义，handler 层兜底）。

### 5.3 集成

- `test_full_happy_path_approved_to_plan_ready_to_spec_drafting`：APPROVED → final_review_passed 卡 → plan handoff → outline 回调 → plan_submit 回调 → approve 卡 → plan_ready 卡 → spec handoff → spec_context 200。

### 5.4 手工 smoke（staging）

- test-2 新项目/新需求走完一次；记录每一步卡片截图。

### 5.5 不测

- plan-author agent 侧行为（归 OpenClaw skill 仓库）
- GitHub PR 实际创建（hook GitHub client 用 MagicMock）
- Feishu 卡片渲染（只验 send_card 调用参数）

## §6 Out of Scope

- `architecture_change != None` 的 Plan → Architecture 两阶段提交。
- `AUTH_PENDING` 子状态与授权卡。
- 驳回后自动 DM 唤醒 plan-author。
- 卡片幂等去重（`plan_submission_id` 版本号）。
- `needs_ui` / `design_status` 耦合。
- 超时监控、流程停滞告警。
