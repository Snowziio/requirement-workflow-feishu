# 规划层实现规格（Planning Layer）

> 本文是方法论 [harness-engineering-methodology-v2.0.md](../harness-engineering-methodology-v2.0.md) §5.2 规划层的实现细节文档。
> 描述目标/使命、上下文契约、plan.md schema、状态列（DesignStatus / PlanStatus）、级联 restart、架构变更授权闸门、钩子装配与卡片模板。
>
> 完整设计论证见 [docs/superpowers/specs/2026-04-19-planning-phase-design.md](../../superpowers/specs/2026-04-19-planning-phase-design.md)。本文是实施者每日参考；设计文档是"为什么"。

---

## 零、实现状态与变更记录

| 版本 | 日期 | 关键变更 |
|---|---|---|
| v1 | 2026-04-19 | 首版设计：在 `APPROVED → SPEC_DRAFTING` 之间插入 DESIGNING + PLANNING 两阶段；`design-author` / `plan-author` 两个 sibling agent；`plan.md` 结构化多决策 + `architecture_change` 授权闸门；DesignStatus / PlanStatus / SpecStatus 三列并行；级联 restart；钩子驱动架构变更原子 apply。 |
| v1-impl | 2026-04-19 | MVP 实装落地：PlanStatus 状态机 + `commit_plan_artifacts` + `on_enter(READY)` 钩子 + plan-context / plan-callback 端点 + `/plan restart` + `/design restart` + spec-context 增加 `plan_md_content`；ARCHITECTURE.md section 匹配采用「header 行精确匹配 + 同级或更高级 header 为节边界」；design-author 未落地，DesignStatus 只提供状态机位置 + restart 级联。 |

---

## 一、目标与使命

### 1.1 核心使命

把"**怎么做的决策**"从 SPEC_DRAFTING 中剥离，分两步完成：

1. **DESIGNING**（`needs_ui=true` 时才进入）：`design-author` 与人多轮交互产出 UI/交互设计，落 `docs/specs/REQ-*/design/`
2. **PLANNING**：`plan-author` 与人多轮交互产出 `plan.md`，内含 N 个结构化 **Decision**；可选 `architecture_change` 块

下游 `spec-author` 只负责把决策**翻译**成 9 节 Spec 工程契约，不再做决策。

### 1.2 关键判定（PlanStatus == READY 时必须满足）

1. `plan.md` 已 commit 到 GitHub `main`，路径 `docs/specs/REQ-*/plan.md`
2. 若 `architecture_change != None`：`ARCHITECTURE.md` 已按 `changes[]` **原子更新**，commit message 引用本 plan；`architecture_change.authorized == true` 含授权人与时间
3. 所有 Decision 的 `chosen` 字段非空；每条 alternative 至少一条 pro / con
4. 若 `needs_ui=true`，`DesignStatus == READY` 是 PlanStatus 进入 DRAFTING 的前置条件

### 1.3 非职责（避免越界）

- **不**产出业务功能明细 / AC / API 细节 / 代码（spec-author 职责）
- **不**替代设计者；plan-author 是**引导者 + 记录者**
- **不**管项目骨架（Bootstrap 职责）
- **不**管 ARCHITECTURE.md 首次初始化，只管**增量演进**

---

## 二、上下文契约

> 遵循 [infra/context-chain-principle.md](../infra/context-chain-principle.md) 五问格式。

### 2.1 规划层消费输入

**入口**：`GET /queries/openclaw/plan-context/<req_id>`。状态门控：`requirement.status == APPROVED && plan_status ∈ {null, DRAFTING}`。

| 上下文产物 | 来源 | 性质 | 用于 |
|---|---|---|---|
| 需求文档 8 字段 | 飞书 docx | 只读 | 决策输入 |
| `needs_ui` | Bitable | 只读 | 是否跳过 DESIGNING |
| design 产物（若 needs_ui=true） | `docs/specs/REQ-*/design/` | 只读 | 决策输入（UI 决定技术选择） |
| 当前 `ARCHITECTURE.md` | GitHub 项目仓库 | 只读 | 架构约束；判断是否需 `architecture_change` |
| acm-registry 切片 | Coordinator 按技术范围过滤 | 只读 | 边界锚（supersedes 线索） |
| tech_stack / category | project_config | 只读 | 技术栈锚 |

### 2.2 规划层产出物

| 产物 | 路径 | 落盘时机 | 后置消费者 |
|---|---|---|---|
| `plan.md`（结构化多决策） | `docs/specs/REQ-*/plan.md` | `on_enter(PlanStatus.READY)` 原子 commit | spec-author（输入） |
| `ARCHITECTURE.md` 增量补丁 | 项目仓库根 `ARCHITECTURE.md` | 同上，同一 commit | 所有下游层 |
| DesignStatus / PlanStatus 状态字段 | Coordinator `Requirement` | 每次转移 | `/spec status` CLI / 飞书卡片 |

---

## 三、plan.md 文件格式

YAML frontmatter + markdown 正文，机器可解析。

```yaml
---
schema_version: "1.0"
req_id: "REQ-xxx"
created_at: "2026-04-19T10:00:00+08:00"
plan_phase: "FINAL"  # OUTLINE_PENDING / OUTLINE_CONFIRMED / DECISIONS_IN_PROGRESS / FINAL_REVIEW_PENDING / FINAL

decisions:
  - id: "D1"
    title: "会话存储选型"
    problem: "需要持久化用户-Agent 会话..."
    alternatives:
      - name: "A. Redis + 过期策略"
        summary: "..."
        pros: ["低延迟", "现有实例"]
        cons: ["TTL 到期数据丢失"]
        risks: ["Redis 单点"]
      - name: "B. Postgres JSONB"
        summary: "..."
        pros: ["持久", "可查询"]
        cons: ["写入慢"]
        risks: []
    chosen: "A"
    rationale: "本需求会话短时有效，低延迟优先于持久性"
    trade_offs: "牺牲长期可审计性换取交互流畅度"
    constraints_referenced: ["需求文档§3.2 会话时长"]

  - id: "D2"
    title: "..."
    # ... 同上结构

architecture_change:  # Optional - 为 null 表示本 REQ 不动架构
  summary: "新增 Redis 会话存储组件"
  changes:
    - section_path: "## 会话存储"
      before: "（原内容，null 表示新增节）"
      after: "（新章节内容）"
      rationale: "支撑 D1 选型"
  authorized: false           # 初始 false，经人工授权后变 true
  authorized_by: null         # feishu user_id
  authorized_at: null         # ISO 8601

open_questions:
  - "D1 的 Redis 容量规划在 Spec 阶段再定"
---

# plan.md 正文（可选的人读友好摘要）

## 决策总览

- **D1** 会话存储 → A (Redis)
- **D2** ...

## D1 详情
...
```

**字段语义**：
- `decisions[].id`：REQ 内全局唯一；spec-author 在 design.md 引用 `决策来源: plan.md#D1`
- `architecture_change == None` 表示本 plan 纯需求性决策，不改 ARCHITECTURE。在此情况下 PlanStatus 跳过 AUTH_PENDING 直达 READY
- `architecture_change.changes[].before == null` 表示新增节；`after == null` 表示删除节；两者都有表示替换

---

## 四、状态列并行模型

三列状态独立演进，Coordinator 按 precondition 阻塞下游：

```
WorkflowStatus:   CREATED → ... → APPROVED ────────────────→ SPEC_IN_PROGRESS → ...
DesignStatus:                     null → DRAFTING → READY  (仅 needs_ui=true)
PlanStatus:                       null → DRAFTING → [AUTH_PENDING →] READY
SpecStatus:                       null                        → DRAFTING → TRANSFORMING → LOCKED
                                        ↑ DesignStatus=READY   ↑ PlanStatus=READY
                                           才进入                才进入
```

### 4.1 DesignStatus 状态机

```python
class DesignStatus(str, Enum):
    DRAFTING = "DRAFTING"
    READY = "READY"

class DesignEvent(str, Enum):
    DESIGN_START = "DESIGN_START"        # APPROVED + needs_ui=true 自动触发
    DESIGN_SUBMIT = "DESIGN_SUBMIT"      # design-author 提交产物
    DESIGN_RESTART = "DESIGN_RESTART"    # /design restart；级联重置 Plan + Spec
```

### 4.2 PlanStatus 状态机

```python
class PlanStatus(str, Enum):
    DRAFTING = "DRAFTING"
    AUTH_PENDING = "AUTH_PENDING"   # 仅当 plan.architecture_change != None
    READY = "READY"

class PlanEvent(str, Enum):
    PLAN_START = "PLAN_START"
    PLAN_SUBMIT = "PLAN_SUBMIT"
    PLAN_AUTHORIZE = "PLAN_AUTHORIZE"
    PLAN_AUTHORIZATION_REJECT = "PLAN_AUTHORIZATION_REJECT"
    PLAN_RESTART = "PLAN_RESTART"    # /plan restart；级联重置 Spec
```

**注意**：`plan_phase`（OUTLINE_PENDING / OUTLINE_CONFIRMED / DECISIONS_IN_PROGRESS / FINAL_REVIEW_PENDING）**不是**状态机事件，而是 DRAFTING 子状态的字段推进，由 plan-author 回调/卡片 handler 直接写 Requirement 字段，不走 apply_event。

### 4.3 precondition 强制

在 Coordinator 写 `SpecStatus = DRAFTING` 之前检查：

```python
if req.needs_ui and req.design_status != DesignStatus.READY:
    raise PreconditionError("design_not_ready")
if req.plan_status != PlanStatus.READY:
    raise PreconditionError("plan_not_ready")
```

---

## 五、三阶段交互模式（plan-author）

plan-author 分三阶段与人协作；每阶段通过 IM 卡片驱动：

| 阶段 | Agent 职责 | 用户动作 | 状态 |
|---|---|---|---|
| **骨架（OUTLINE）** | 读需求 + ARCHITECTURE + design，列出本 REQ 需要做的 N 个决策标题 | 卡片按钮确认/调整骨架 | `plan_phase = OUTLINE_PENDING → OUTLINE_CONFIRMED` |
| **深入（DECISIONS_IN_PROGRESS）** | 逐个 decision 多轮对话：提出 alternatives → 人选 → 追问细节 → 写入 plan.md | 对话 + 拍板 | `plan_phase = DECISIONS_IN_PROGRESS` |
| **定稿（FINAL）** | 汇总成完整 plan.md；若涉及架构变更，产出 `architecture_change` 块 | 卡片按钮确认 / 打回 | `plan_phase = FINAL_REVIEW_PENDING`；确认后 `PLAN_SUBMIT` |

骨架阶段避免"一来就写细节"的浪费，先对齐决策清单；深入阶段保证每个选择都有 alternatives 可审计。

---

## 六、架构变更授权闸门

### 6.1 AUTH_PENDING 条件

`PLAN_SUBMIT` 时若 `plan.architecture_change != None`：
- 状态机 → `AUTH_PENDING`
- `on_enter(AUTH_PENDING)` 钩子推送授权卡片到创建群，展示 before/after diff + rationale + changes[] 数量
- 两个按钮：**授权** / **驳回**

### 6.2 授权后的原子 apply

`on_enter(PlanStatus.READY)` 钩子（同一事务内）：

1. 读取当前 `ARCHITECTURE.md` + SHA（GitHub）
2. 按 `architecture_change.changes[]` 依次 apply section patch
3. 生成新 `ARCHITECTURE.md` 内容
4. 生成 `plan.md` 内容（内嵌 `authorized_by` / `authorized_at`）
5. **原子 commit**：两文件一个 commit，message 引用本 REQ + plan
6. 任何一步失败 → 整体回滚 + 转移失败（钩子抛 `ProjectRepoError(recoverable=True, reason="architecture_conflict")`）
7. 回滚路径：coordinator 把 PlanStatus 退回 AUTH_PENDING，推送失败卡片让人决定重试 / 驳回 / restart

### 6.3 驳回路径

`PLAN_AUTHORIZATION_REJECT` → PlanStatus 退回 DRAFTING，`plan_phase = FINAL_REVIEW_PENDING`，plan-author 被重新拉起带上驳回意见。

---

## 七、级联 restart 语义

| 命令 | 重置列 | 确认卡片要点 |
|---|---|---|
| `/spec restart <req>` | SpecStatus → null | 仅重置 Spec |
| `/plan restart <req>` | PlanStatus → null，**级联** SpecStatus → null | "将同时丢弃 Spec；继续？" |
| `/design restart <req>` | DesignStatus → null，**级联** PlanStatus → null，**级联** SpecStatus → null | "将同时丢弃 Plan + Spec；继续？" |

实现细节：coordinator 侧组合事件分发，状态机本身只处理自列 `*_RESTART` 事件（保持纯函数）；确认卡片由 coordinator 编排，不进状态机。

---

## 八、钩子装配

复用 [infra/state-machine-hook-pattern.md](../infra/state-machine-hook-pattern.md) 模式。装配阶段（`configure_plan_hooks`）注册：

```python
hooks.on_enter(DesignStatus.DRAFTING, _dispatch_design_author)
hooks.on_enter(DesignStatus.READY,    _notify_design_ready)

hooks.on_enter(PlanStatus.DRAFTING,     _dispatch_plan_author)
hooks.on_enter(PlanStatus.AUTH_PENDING, _show_authorization_card)
hooks.on_enter(PlanStatus.READY,        _commit_plan_and_maybe_architecture)

hooks.on_exit(PlanStatus.READY, _notify_spec_precondition_met)
```

`_commit_plan_and_maybe_architecture` 通过 `ProjectRepoTools.commit_plan_artifacts(req_id, plan_md, architecture_md_or_none)` 下钻到 Tool 层——见 [docs/superpowers/specs/2026-04-19-project-repo-tools-design.md](../../superpowers/specs/2026-04-19-project-repo-tools-design.md) § 4。

---

## 九、卡片模板清单

| 卡片 | 触发点 | 按钮 |
|---|---|---|
| 规划启动提醒 | `on_enter(PlanStatus.DRAFTING)` | （无，仅通知） |
| 骨架确认卡 | plan-author 回调 `plan_outline_submit` | 确认 / 调整（文本回复） |
| 决策进度卡 | 每条 decision 定稿（plan-author 回调） | 继续下一条 / 回看修改 |
| 定稿预览卡 | plan-author 回调 `plan_draft_ready` | 确认定稿（`PLAN_SUBMIT`） / 打回 |
| **架构授权卡** | `on_enter(PlanStatus.AUTH_PENDING)` | **授权** / **驳回** |
| 架构 apply 失败卡 | `on_enter(READY)` 钩子异常 | 重试 / `/plan restart` |
| 设计启动提醒 | `on_enter(DesignStatus.DRAFTING)`（needs_ui=true） | （无） |
| 设计定稿卡 | design-author 回调 | 确认 / 打回 |

---

## 十、与规格层的接口契约

spec-author 在 SPEC_DRAFTING 阶段消费 plan.md，**不再做决策**：

- 每条 design.md 条目必须指明 `决策来源: plan.md#D<id>`（或 `本层工程翻译` 用于纯实现细节）
- `design.md` / `tasks.md` / `ac-schedule.yaml` 内所有选型必须可追溯到一条 Decision
- 若 spec-author 发现决策缺失或与需求冲突，触发 `spec_deadlocked=true`，coordinator 推人工卡片（决定 `/plan restart` 或手工补 Decision 后 `/spec restart`）

---

## 十一、端点清单（实现阶段补全）

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/queries/openclaw/plan-context/<req>` | plan-author 拉上下文 |
| GET | `/queries/openclaw/design-context/<req>` | design-author 拉上下文 |
| POST | `/openclaw/plan-callback` | plan-author 回写骨架 / decision / draft |
| POST | `/openclaw/design-callback` | design-author 回写 design 产物 |
| POST | `/cards/plan-authorize` | 架构授权卡按钮处理（user→coordinator） |
| POST | `/cards/plan-outline-confirm` | 骨架确认（user→coordinator） |
| CLI | `/plan restart <req>` | 级联重置 |
| CLI | `/design restart <req>` | 级联重置 |

---

## 十二、已知遗留（实施时登记到 session memory）

- design-author 的具体产物格式待 Phase 2 第一次真实 needs_ui=true REQ 落地时收敛；当前设计文档留空 `docs/specs/REQ-*/design/` 目录结构，不强制 schema
- `ARCHITECTURE.md` 的 section_path 匹配算法（header-based vs line-range）实施阶段再定
- plan-author / design-author 的 SKILL.md 位于 OpenClaw 仓库，遵循 skills+workspace 双份同步约束（见 `reference_openclaw_skill_dual_sync.md`）
- spec-context 的 `_fetch_plan_md(req_id)` 默认返回空串，生产环境需替换成从 GitHub 拉 `docs/specs/<req>/plan.md` 的实现（留给下一次部署迭代处理）
