# PLANNING 阶段 + plan-author Agent 设计规格

> **2026-04-21 update**: 卡片流程接线已落地，详见 [2026-04-21-plan-wiring-design.md](./2026-04-21-plan-wiring-design.md)。要点：`plan_start()` 守卫放宽（不再耦合 needs_ui/design_status）；plan-callback 的 `plan_submit` 分支改为把草稿缓存进 `pending_plan_review` 并发 `plan_submitted_pending_review` 卡，仅在人工通过后才落 GitHub PR 并切换 `PlanStatus.READY`。MVP 仅支持 `architecture_change=None`；不实现 `AUTH_PENDING`；驳回为纯状态重置。
>
> 本规格定义 `APPROVED → SPEC_DRAFTING` 之间的 **DESIGNING + PLANNING** 两个新阶段，引入独立的 `design-author` / `plan-author` agent，把"怎么做"的决策从 Spec 阶段剥离出来。
>
> 关联文档：
> - 方法论：[harness-engineering-methodology-v2.0.md](../../context/harness-engineering-methodology-v2.0.md) §5 各层定义
> - 规格层实现：[spec-harness-layer.md](../../context/layers/spec-harness-layer.md)
> - 状态机 + 钩子模式：[state-machine-hook-pattern.md](../../context/infra/state-machine-hook-pattern.md)
> - Tool 层门面：[2026-04-19-project-repo-tools-design.md](./2026-04-19-project-repo-tools-design.md)

---

## 零、变更记录

| 版本 | 日期 | 关键变更 |
|---|---|---|
| v1 | 2026-04-19 | 首版：DESIGNING + PLANNING 两阶段；design-author / plan-author 两个新 agent；plan.md schema（多决策 + Optional architecture_change）；PlanStatus / DesignStatus 并列状态列；级联 restart；架构变更走授权闸门 + 钩子 apply |

---

## 一、目标与使命

### 1.1 核心使命

把"**怎么做的决策**"从 SPEC_DRAFTING 阶段剥离出来，分两步完成：

1. **DESIGNING**：当 `needs_ui = true` 时，`design-author` 与人通过 IM 多轮交互产出 UI/交互设计产物（mockup / interaction flow / 组件清单），落在 `docs/specs/REQ-*/design/` 目录
2. **PLANNING**：`plan-author` 与人通过 IM 多轮交互产出 `plan.md`——一份包含 N 个结构化 **Decision** 的决策日志，可选包含 `architecture_change` 块

下游 `spec-author` 在 SPEC_DRAFTING 阶段消费这两份产物，只负责把决策**翻译**成 9 节 Spec 工程契约，不再自己做决策。

### 1.2 关键判定（PlanStatus == READY 时必须满足）

1. `plan.md` 已 commit 到 GitHub `main`（或首个 REQ 的初始 commit），路径 `docs/specs/REQ-*/plan.md`
2. 若 `architecture_change != None`，`ARCHITECTURE.md` 已按 `changes[]` 原子更新，commit message 引用本 plan
3. 所有 Decision 的 `chosen` 字段非空；所有 alternatives 至少一条 pro 一条 con
4. 若 `needs_ui = true`，DesignStatus == READY 是 PlanStatus 进入 DRAFTING 的前置条件

### 1.3 非职责（避免越界）

- **不**产出业务功能明细 / AC / API 细节 / 代码（spec-author 职责）
- **不**替代设计者；plan-author 是**引导者 + 记录者**，决策由人拍板
- **不**决定项目骨架（Bootstrap 职责，项目生命周期一次性事件）
- **不**管 ARCHITECTURE.md 的首次初始化（Bootstrap 的 template 产物），只管**增量演进**

---

## 二、上下文契约

### 2.1 PLANNING 层消费输入

**入口**：`GET /queries/openclaw/plan-context/<req_id>` 端点。状态门控：`requirement.status == APPROVED && plan_status ∈ {null, DRAFTING}`。

| 上下文产物 | 来源 | 性质 | 用于 Decision |
|---|---|---|---|
| 需求文档 8 字段 | 飞书 docx（requirement_document_url） | 只读 | 决策输入 |
| `needs_ui` | Bitable | 只读 | 是否跳过 DESIGNING |
| design 产物（若 needs_ui=true） | `docs/specs/REQ-*/design/` | 只读 | 决策输入（UI 决定技术选择） |
| 当前 ARCHITECTURE.md | GitHub 项目仓库 | 只读 | 架构约束；决定 architecture_change 是否需要 |
| acm-registry 切片 | Coordinator 根据技术范围过滤 | 只读 | 边界锚（supersedes 线索） |
| 历史 plan.md 列表（brown-field） | GitHub `docs/specs/*/plan.md` | 只读 | 决策连续性（不重做已定决策） |
| tech_stack / category / template_version | project_config | 只读 | 技术栈锚 |

### 2.2 PLANNING 层产出

**阶段一产出（PlanStatus == DRAFTING 末态，plan_phase 的三个子态）**：

| 产物 | 载体 | 更新策略 |
|---|---|---|
| 骨架（decision titles + problems） | Coordinator state（`requirement.plan_outline`） | `plan_outline_submit` callback 写入；`outline_confirm` 事件冻结 |
| 每个 Decision 的多轮讨论 trace | Coordinator state（`requirement.plan_decisions_wip`） | 逐个 decision 对话过程中追加 |
| `plan.md` 定稿文本 | Coordinator state（`requirement.pending_plan_draft`，transient） | `plan_submit` callback 写入；最终版通过授权后落盘 |

**阶段二产出（PlanStatus == READY 末态）**：

| 产物 | 载体 | 更新策略 |
|---|---|---|
| `plan.md`（不可变） | GitHub `docs/specs/REQ-*/plan.md` | 钩子 `on_enter(READY)` 调 `project_repo_tools.commit_plan_artifacts`；首个 REQ 走 Bootstrap 的初始化 commit；后续 REQ 直接 commit |
| `ARCHITECTURE.md`（增量演进） | GitHub `ARCHITECTURE.md` | 仅当 `architecture_change != None`，同一钩子内原子 apply `changes[]` 并与 plan.md 一起 commit |
| `requirement.plan_pr_url` | Coordinator state | commit 完成后写入 |
| `requirement.plan_status` | Coordinator state | 钩子末段置 READY |

### 2.3 与其他层的边界

| 被问 | 答 |
|---|---|
| PLANNING 会读飞书 docx 吗？ | 会（需求文档）；但 plan.md 本身永远不去飞书 |
| PLANNING 会写 ARCHITECTURE 吗？ | 仅当 architecture_change 存在且授权通过；且限定于结构化 diff，不是自由编辑 |
| plan.md 会被 SPEC 反向修改吗？ | 不会；plan.md 不可变，spec-author 只读 |
| plan-author 和 design-author 能并行吗？ | 不能；DESIGNING 先完，PLANNING 才启（sequential design-first） |

---

## 三、三 Agent 分工与状态列

### 3.1 Agent 平级关系

`design-author` / `plan-author` / `spec-author` **平级**挂在 `CoordinatorService` 上，各自通过 `StateTransitionHooks` 注册 `on_enter` 回调。**没有**嵌套调用（plan-author 不调 design-author）。

| Agent | 状态列 | 产物 | 实装状态 |
|---|---|---|---|
| design-author | DesignStatus | `docs/specs/REQ-*/design/` | **本规格不实施**（待 claude design 能力落地） |
| plan-author | PlanStatus | `docs/specs/REQ-*/plan.md` | **本规格实施** |
| spec-author | SpecStatus | `docs/specs/REQ-*/spec.md` + `ac-schedule.yaml` + ... | 已实装 |

DESIGNING 阶段在本规格里**只占状态机位置 + 端点 stub**，保证 PLANNING 以"设计产物已就绪"为前提即可，不落地 design-author agent 本身。

### 3.2 三个状态列并列

```
Workflow:    INTAKE → ... → APPROVED → ... (workflow_status 保持 APPROVED 贯穿三列)
DesignStatus: None     →    None | DRAFTING | READY
PlanStatus:   None     →    None | DRAFTING | AUTH_PENDING | READY
SpecStatus:   None     →    None | DRAFTING | TRANSFORMING | LOCKED
```

**precondition（由 coordinator 统一检查）**：

- `DesignStatus: None → DRAFTING` 要求：`workflow_status == APPROVED && needs_ui == True`
- `PlanStatus: None → DRAFTING` 要求：`workflow_status == APPROVED && (needs_ui == False || DesignStatus == READY)`
- `SpecStatus: None → DRAFTING` 要求：`PlanStatus == READY`

每个状态列自身是**纯状态机**，precondition 检查发生在 coordinator 的"能不能进入下一列"判断里，不污染状态机。

### 3.3 plan_phase 子态字段

PlanStatus == DRAFTING 期间，`Requirement.plan_phase` 字段细分对话进度（**不是独立状态**，避免状态机爆炸）：

```python
class PlanPhase(str, Enum):
    OUTLINE_PENDING = "outline_pending"         # plan-author 起草骨架中
    OUTLINE_CONFIRMED = "outline_confirmed"     # 人确认骨架，开始逐个 decision 讨论
    DECISIONS_IN_PROGRESS = "decisions_in_progress"  # 正在讨论某个 decision
    FINAL_REVIEW_PENDING = "final_review_pending"    # plan.md 定稿，等人 final approve
```

只有 `DRAFTING → AUTH_PENDING` 或 `DRAFTING → READY` 才是状态机转移；plan_phase 推进只是字段写入 + 卡片刷新。

---

## 四、plan.md Schema

### 4.1 顶层结构

```yaml
# docs/specs/REQ-xxx/plan.md 里的 YAML frontmatter + Markdown body
---
schema_version: "1.0"
req_id: "REQ-xxx"
project_id: "P"
authored_at: "2026-04-19T10:00:00Z"
authored_by: "open_id-xxx"  # plan-author agent session 所属人

decisions:
  - id: "D1"
    title: "..."
    problem: "..."
    alternatives:
      - name: "A. ..."
        summary: "..."
        pros: ["...", "..."]
        cons: ["...", "..."]
        risks: ["..."]
      - name: "B. ..."
        ...
    chosen: "A"
    rationale: "..."
    trade_offs: "..."
    constraints_referenced: ["需求文档§3.2", "ARCHITECTURE.md §Auth"]

  - id: "D2"
    ...

architecture_change:  # Optional；缺省则不走授权闸门
  summary: "引入 Redis 作为会话存储"
  changes:
    - section_path: "## 会话存储"
      before: "（占位符）待首个 REQ 决定"
      after: "使用 Redis 7.x，key 命名 `session:<user_id>`，TTL 30 分钟"
      rationale: "参考 D1"
  authorized: false          # 授权前 false
  authorized_by: null        # 授权后写入 open_id
  authorized_at: null        # 授权后写入 ISO-8601

open_questions:              # Optional；没有定论、留给实施阶段的
  - "Redis cluster 还是单实例？当前规模单实例够用，量级上去后再切"
---

# REQ-xxx Plan

（Markdown 叙事，可读版本的 decisions 归纳；给人看的，不作为下游 agent 解析入口）
```

### 4.2 Decision 结构详解

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `id` | str | yes | 稳定标识，用于 spec-author 引用（`see D1`） |
| `title` | str | yes | 一句话概括决策 |
| `problem` | str | yes | 这个 decision 要回答的问题 |
| `alternatives[]` | list | yes（至少 2 条） | 考虑过的选项，每条 ≥1 pro ≥1 con |
| `alternatives[].name` | str | yes | 以 "A. " / "B. " 等前缀开头，便于 chosen 引用 |
| `alternatives[].summary` | str | yes | 选项内容摘要 |
| `alternatives[].pros` | list[str] | yes | 至少 1 条 |
| `alternatives[].cons` | list[str] | yes | 至少 1 条 |
| `alternatives[].risks` | list[str] | no | 执行风险 |
| `chosen` | str | yes | 引用 alternative.name 的前缀字母（`"A"` / `"B"`） |
| `rationale` | str | yes | 为什么选这个 |
| `trade_offs` | str | yes | 明确承认的代价 |
| `constraints_referenced` | list[str] | no | 引用的需求/架构约束 |

### 4.3 architecture_change 结构详解

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `summary` | str | yes | 本次架构变更的一句话描述 |
| `changes[]` | list | yes（至少 1 条） | 要改的 ARCHITECTURE 节 |
| `changes[].section_path` | str | yes | ARCHITECTURE.md 的节标题（如 `"## 会话存储"`），精确匹配 |
| `changes[].before` | str | yes | 该节当前内容（可为 `""` 如果是新增节） |
| `changes[].after` | str | yes | 该节变更后内容 |
| `changes[].rationale` | str | yes | 为什么这么改，通常引用 decisions |
| `authorized` | bool | yes | 授权闸门标记 |
| `authorized_by` | str \| null | —  | 授权者 open_id |
| `authorized_at` | str \| null | — | ISO-8601 时间戳 |

**apply 语义**：钩子按 `changes[]` 顺序应用到 ARCHITECTURE.md；每条 change 用 `section_path` 定位锚点，`before` 做 pre-apply 校验（若不匹配则抛 `ProjectRepoError(recoverable=True, reason="architecture_conflict")`，走 §6.3 的并发冲突恢复路径）；`after` 覆盖该节内容。

### 4.4 不可变性与存储

- plan.md 一旦 commit，**不可变**；任何"更新"都走 `/plan restart`（级联重置 spec）或新 REQ
- 存储路径固定 `docs/specs/REQ-<id>/plan.md`
- 首个 REQ（ARCHITECTURE 从占位符到真实）和后续 REQ（ARCHITECTURE 可能已成熟）使用**同一个 schema**——是否有 `architecture_change` 块由 plan-author 运行时判断，不是 schema 层分型

---

## 五、状态机增量

### 五.1 新枚举类型

```python
class DesignStatus(str, Enum):
    DRAFTING = "DRAFTING"
    READY = "READY"

class PlanStatus(str, Enum):
    DRAFTING = "DRAFTING"
    AUTH_PENDING = "AUTH_PENDING"
    READY = "READY"

class DesignEvent(str, Enum):
    DESIGN_START = "DESIGN_START"
    DESIGN_SUBMIT = "DESIGN_SUBMIT"           # design-author 产出完成
    DESIGN_RESTART = "DESIGN_RESTART"

class PlanEvent(str, Enum):
    PLAN_START = "PLAN_START"
    PLAN_SUBMIT = "PLAN_SUBMIT"                          # DRAFTING → AUTH_PENDING 或 READY
    PLAN_AUTHORIZE = "PLAN_AUTHORIZE"                    # AUTH_PENDING → READY
    PLAN_AUTHORIZATION_REJECT = "PLAN_AUTHORIZATION_REJECT"  # AUTH_PENDING → DRAFTING
    PLAN_RESTART = "PLAN_RESTART"

# plan_phase 字段的推进（OUTLINE_PENDING → OUTLINE_CONFIRMED → DECISIONS_IN_PROGRESS →
# FINAL_REVIEW_PENDING）由 coordinator 的 plan-callback / card handler 直接写字段，
# 不是状态机事件——plan_phase 粒度更细，不值得进入状态机。
```

### 五.2 状态转移表

**DesignStatus**：

| 前态 | 事件 | 后态 | 守卫 |
|---|---|---|---|
| None | DESIGN_START | DRAFTING | `workflow_status == APPROVED && needs_ui == True` |
| DRAFTING | DESIGN_SUBMIT | READY | — |
| 任意（非 None） | DESIGN_RESTART | None | 级联 reset PlanStatus + SpecStatus；同时清各自 transient 字段 |

**PlanStatus**：

| 前态 | 事件 | 后态 | 守卫 |
|---|---|---|---|
| None | PLAN_START | DRAFTING | `workflow_status == APPROVED && (needs_ui == False || DesignStatus == READY)` |
| DRAFTING | PLAN_SUBMIT | AUTH_PENDING | `plan_draft.architecture_change != None` |
| DRAFTING | PLAN_SUBMIT | READY | `plan_draft.architecture_change == None` |
| AUTH_PENDING | PLAN_AUTHORIZE | READY | — |
| AUTH_PENDING | PLAN_AUTHORIZATION_REJECT | DRAFTING | plan_phase 回到 `DECISIONS_IN_PROGRESS` |
| 任意（非 None） | PLAN_RESTART | None | 级联 reset SpecStatus；同时清 `plan_phase` / `pending_plan_draft` / `plan_pr_url` |

### 五.3 钩子注册

钩子机制见 [state-machine-hook-pattern.md](../../context/infra/state-machine-hook-pattern.md)。Coordinator 装配阶段注册：

```python
# design-author 侧
hooks.on_enter(DesignStatus.DRAFTING, _dispatch_design_author)
hooks.on_exit(DesignStatus.DRAFTING, _persist_design_artifacts)

# plan-author 侧
hooks.on_enter(PlanStatus.DRAFTING, _dispatch_plan_author)
hooks.on_enter(PlanStatus.AUTH_PENDING, _show_authorization_card)
hooks.on_enter(PlanStatus.READY, _commit_plan_and_maybe_architecture)
#                 ^ 这个钩子是架构变更落地的核心事务

# restart 级联（不在状态机里，在 coordinator 编排）
hooks.on_exit(PlanStatus, _cascade_reset_spec_on_plan_restart)
hooks.on_exit(DesignStatus, _cascade_reset_plan_and_spec_on_design_restart)
```

### 五.4 级联 restart 编排

`/plan restart` 和 `/design restart` 命令由 coordinator 处理，**不是状态机原子**：

```python
def plan_restart(req_id):
    req = self.requirements[req_id]
    artifacts_to_clear = self._enumerate_plan_downstream_artifacts(req)
    # 弹确认卡片，列出将清理的产物（plan_pr_url, spec_pr_url, spec_trace 等）
    if not self._prompt_user_confirm(req, artifacts_to_clear):
        return
    # 先清下游（原子按列）
    self._fire_transition(req, PlanEvent.PLAN_RESTART)  # 清 plan 列
    self._cascade_reset_spec(req)                        # 清 spec 列
    self._audit("plan_restart_cascade", req_id, artifacts_to_clear)
```

---

## 六、架构变更 apply 事务

### 六.1 事务边界

钩子 `_commit_plan_and_maybe_architecture`（挂在 `on_enter(PlanStatus.READY)`）是架构变更落地的**原子事务边界**：

```python
def _commit_plan_and_maybe_architecture(self, req: Requirement) -> None:
    plan_draft = req.pending_plan_draft
    project_repo = self._project_repo_for(req.req_id)
    try:
        result = self._tools.commit_plan_artifacts(
            project_repo=project_repo,
            req_id=req.req_id,
            plan_md_content=plan_draft.to_markdown(),
            architecture_changes=plan_draft.architecture_change,  # 可为 None
        )
        req.plan_pr_url = result.pr_url
        req.pending_plan_draft = None  # transient 清除
    except ProjectRepoError:
        # fail-fast：状态机保持 PlanStatus == READY 之前的态（STALE 状态由 hook re-raise 传播）
        raise
```

### 六.2 commit_plan_artifacts 契约

`ProjectRepoTools` facade 新增方法（见 [2026-04-19-project-repo-tools-design.md](./2026-04-19-project-repo-tools-design.md) 的门面契约扩展）：

```python
def commit_plan_artifacts(
    self,
    project_repo: RepoRef,
    req_id: str,
    plan_md_content: str,
    architecture_changes: ArchitectureChange | None,
) -> PlanCommitResult:
    """
    原子事务：
      1. 若 architecture_changes != None，按 changes[] 校验 before 匹配，生成 new ARCHITECTURE.md 内容
      2. 在一个 git commit 中同时写 plan.md + (可选) ARCHITECTURE.md
      3. 首个 REQ 直接 commit 到 main（走 Bootstrap 初始化通道）
      4. 后续 REQ commit 到 main（plan.md 不需要 PR review——人的 review 在 PLAN_AUTHORIZE 阶段已完成）
      5. 失败：不留半成品（清本地 branch），raise ProjectRepoError
    """
```

### 六.3 before 不匹配的恢复策略

如果钩子发现 `architecture_changes[i].before` 与仓库当前 ARCHITECTURE 对应 section 不匹配（典型场景：PLANNING 阶段有其他 REQ 并发 commit 改了 ARCHITECTURE），钩子：

1. 抛 `ProjectRepoError(recoverable=True, reason="architecture_conflict")`
2. Coordinator 捕获 → 把 PlanStatus 拉回 `DRAFTING`（相当于 `PLAN_AUTHORIZATION_REJECT`）
3. plan-author session 被 wake up，收到 reason，拉取最新 ARCHITECTURE 后重新起草 architecture_change 块
4. 人再次 authorize → 再次 commit → 成功为止

这个重试循环**不在状态机里**，由 coordinator 编排；状态机只负责单次转移。

---

## 七、端点与回调

### 7.1 新端点

**`GET /queries/openclaw/plan-context/<req_id>`**

返回 PLANNING 层消费输入（见 §2.1 表）。状态门控：`plan_status ∈ {None, DRAFTING}`。

**`POST /openclaw/plan-callback`**

plan-author 的 callback 入口（agent → coordinator），区分 `event` 字段：

```json
{
  "req_id": "REQ-xxx",
  "event": "plan_outline_submit | plan_submit",
  "payload": {
    // outline_submit:
    "outline": [{"id": "D1", "title": "...", "problem": "..."}],
    // plan_submit:
    "plan_md_content": "...",         // 整份 plan.md YAML+Markdown
    "architecture_change": {...} | null
  }
}
```

> `plan_outline_confirm` / `plan_authorize` / `plan_authorization_reject` 是**人 → coordinator** 方向（卡片按钮），不走 plan-callback；由 card-handler 直接派发对应的 `PlanEvent`。

### 7.2 扩展已有端点

**`GET /queries/openclaw/spec-context/<req_id>`** 增加 `plan_md_content` 字段（spec-author 消费）：

```json
{
  "requirement_document_url": "...",
  // ... 现有字段
  "plan_md_content": "<yaml frontmatter + markdown>",
  "plan_decision_ids": ["D1", "D2", ...]        // 便于 spec-author 引用
}
```

### 7.3 新卡片

| 卡片名 | 触发点 | 按钮 |
|---|---|---|
| `plan_outline_card` | `plan_outline_submit` callback 到达 | `confirm_outline` / `request_changes`（回 plan-author） |
| `plan_decision_card` | 每个 decision 进入多轮讨论时 | 对话式交互（由 plan-author 在内部管理），不是按钮触发状态转移 |
| `plan_final_review_card` | `plan_submit` callback 到达，`architecture_change == None` | `approve_plan` → `PLAN_SUBMIT` 事件 |
| `plan_authorization_card` | `on_enter(AUTH_PENDING)` 钩子触发 | `authorize` / `reject` → `PLAN_AUTHORIZE` / `PLAN_AUTHORIZATION_REJECT` 事件 |
| `plan_restart_confirm_card` | `/plan restart` 命令触发 | `confirm` / `cancel`；列出将被清理的下游产物 |

### 7.4 spec-author 消费 plan.md 的 prompt 变更

spec-author 的 SKILL.md 增加消费规则（**不改 9 节模板**）：

> 当 `plan_md_content` 非空时：
> - 阅读 plan.md，理解已做决策；对应 9 节里的相关段落**引用 decision_id**（"参见 D1"），不要重新推理
> - 严禁在 spec 里提出与 plan 冲突的替代方案
> - plan 的 `open_questions` 必须在 spec 的"开放问题"节中保留并标注 `from plan`
> - `architecture_change` 已通过钩子 apply 到 ARCHITECTURE.md；spec 只消费 ARCHITECTURE 当前态，不再描述变更本身

---

## 八、实施范围声明

### 8.1 本规格实施

| 子系统 | 状态 |
|---|---|
| `PlanStatus` 枚举 + Requirement 字段 + 状态机 | 落地 |
| `plan-author` agent：SKILL.md + callback schema | 落地（skill 在 OpenClaw 仓库） |
| `plan-context` 端点 + plan-callback 端点 | 落地 |
| 5 张新卡片 + handler | 落地 |
| `commit_plan_artifacts` 门面方法 + 原子事务 | 落地 |
| `on_enter(PlanStatus.READY)` 钩子 + 架构 apply | 落地 |
| 级联 restart coordinator 编排 | 落地 |
| `spec-context` 扩展 `plan_md_content` | 落地 |
| spec-author SKILL.md prompt 增补 | 落地（skill 在 OpenClaw 仓库） |

### 8.2 本规格**不**实施（留作后续）

| 子系统 | 原因 |
|---|---|
| `design-author` agent | 等 claude design 能力落地；本规格只占状态机位置和端点 stub |
| DesignStatus 完整钩子 | 同上；本规格只定义枚举和状态转移规则，不挂钩子 |
| Bootstrap（项目骨架首次生成） | 项目生命周期事件，和 PLANNING 正交；memory 单独登记 |
| 首个 REQ 的 ARCHITECTURE 首次初始化 | Bootstrap 子问题 |
| `design-context` 端点 | claude design 落地时再设计 |

### 8.3 受影响但不本规格修改

| 子系统 | 影响 | 何时处理 |
|---|---|---|
| `project_pending_state_migration`（state.json 迁移） | 新增 `plan_status` / `plan_phase` / `plan_pr_url` 字段，需要迁移 | 本规格实施中用默认值（None）兜底；迁移脚本 Phase 后议 |
| `architecture_doc_url` 持久化风险 | PLANNING 会触发 ARCHITECTURE 写入，放大这个 risk | 本规格不处理，memory 已登记 |
| `needs_ui` 两阶段流程 | DESIGNING 是实装它的第一步 | 本规格只提供状态机位置，完整实装在 design-author 落地时 |

---

## 九、验收

### 9.1 单元 / 集成测试清单

1. `PlanStatus` 状态机转移表全覆盖（包括非法转移拒绝）
2. `plan-author` 三阶段 callback 的 payload 验证
3. `commit_plan_artifacts` 原子性：模拟 GitHub 写入失败 → ARCHITECTURE 和 plan.md 都不落盘
4. `architecture_change` `before` 不匹配 → `recoverable=True` 错误 → PlanStatus 回 DRAFTING
5. 级联 restart：`/plan restart` 后 SpecStatus 确实被清；`/design restart` 后 Plan + Spec 都被清
6. 端到端：`APPROVED → PLAN_START → DRAFTING (outline → decisions → final) → AUTH_PENDING → AUTHORIZE → READY → ARCHITECTURE.md 和 plan.md 都 committed`
7. spec-context 端点在 PlanStatus == READY 后返回 `plan_md_content` 非空
8. `needs_ui=False` 的 REQ 跳过 DESIGNING：`PLAN_START` 守卫直接通过
9. `architecture_change == None` 的 REQ 跳过 AUTH_PENDING：`PLAN_SUBMIT` 直接到 READY

### 9.2 观察性

钩子异常日志格式遵循 [state-machine-hook-pattern.md](../../context/infra/state-machine-hook-pattern.md) §契约摘要：`event=hook_exception transition=enter status=PLAN_READY req_id=<id> hook_name=_commit_plan_and_maybe_architecture exception=<repr>`。

---

## 十、非目标声明（避免过度设计）

- **不**做 plan-reviewer agent（人即 reviewer）
- **不**做 decision graph / dependency tracking（YAGNI，未来有实际需求再加）
- **不**做 green-field / brown-field schema 分型（语义事实由 `architecture_change` 存在与否承载）
- **不**做 partial authorization（架构变更整块授权）
- **不**做 plan.md 跨 REQ 合并 / 版本链（不可变 per-REQ，依赖后续分析工具做聚合）
- **不**把 Bootstrap 作为 PLANNING 子状态（项目生命周期事件，独立处理）

---

## 附录 A：与 Tool 层重构的衔接

本规格依赖 2026-04-19 已落地的 Tool 层重构（`ProjectRepoTools` facade + `StateTransitionHooks`）。新增的 `commit_plan_artifacts` 方法加在 `GitHubProjectRepoTools` 上，遵循相同的 `ProjectRepoError` 错误模型和原子事务约定。`on_enter(PlanStatus.READY)` 钩子通过 `CoordinatorService._hooks` 注册，复用现有基础设施。

---

## Addendum: 2026-04-20 schema 升级

`architecture_change` payload 字段已重命名为 `project_context_change`，信封内
`changes[]` 新增 `artifact` 字段（值域 `architecture` / `environments` / `skill_md`）。
MVP 只实现 `architecture` 执行器；其他 artifact 是 stub。

向后兼容：无存量数据（test2 硬废弃），无兼容负担。新 plan-author 产物直接用
`project_context_change`；读取端对在途回调保留临时 shim
（`payload.get("project_context_change") or payload.get("architecture_change")`）。

详见：[docs/superpowers/specs/2026-04-20-project-layer-design.md](2026-04-20-project-layer-design.md)
