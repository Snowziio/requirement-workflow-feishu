# 规格层实现设计 · 2026-04-16

> **状态**：设计稿（待用户 review → 通过后调用 writing-plans 生成实施计划）
> **关联文档**：
> - 方法论 [docs/context/harness-engineering-methodology-v2.0.md](../../context/harness-engineering-methodology-v2.0.md) §5.2 / §5.3
> - 层规格 [docs/context/layers/spec-harness-layer.md](../../context/layers/spec-harness-layer.md)
> - Epic [docs/context/epics/spec-transform-epic-2026-04.md](../../context/epics/spec-transform-epic-2026-04.md)
> - 行业对齐 [docs/context/infra/harness-engineering-industry-alignment-2026-04-16.md](../../context/infra/harness-engineering-industry-alignment-2026-04-16.md)
>
> **范围**：本文规划规格层从 `SPEC_DRAFTING` 出口到 `SPEC_LOCKED` 入口的代码侧实现，含 Coordinator 博弈编排、Computational gate、transform_trace、regression scan、acm-registry patch、spec_source_revision 冻结、spec_restart 守卫七个待落地能力。

---

## 一、决策记录

为避免后续翻案，所有方向性决策在此显式登记。每条决策的"为什么"见对应章节展开。

### 1.1 架构决策（Q1-Q7）

| ID | 决策 | 取舍要点 |
|---|---|---|
| Q1 | **Callback-driven 编排** | OpenClaw subprocess 主动回调 Coordinator；Coordinator 不轮询 |
| Q2 | **状态转换垂直切片** | 6 片，每片 = 一个端到端可演示的状态转换 |
| Q3 | **acm-registry patch 混合生成** | agent 在 `design.md ## supersedes` 声明取代关系；Coordinator 机械生成 yaml patch；Computational gate 反向校验完整性 |
| Q4 | **trace.jsonl 落 PR**（含 Risk 1 修订） | 同时本地写 + 收敛时复制到 PR；deadlock 路径只本地存 |
| Q5 | **spec_restart = slash command + 轻量** | `/spec restart REQ-X`；仅 SPEC_DRAFTING 与 SPEC_TRANSFORMING(deadlocked) 可重启；不动 GitHub PR |
| Q6 | **Computational gate 在 Coordinator 侧** | `coordinator/spec_gate.py` 纯函数；reviewer 不消耗 token 跑机械检查 |
| Q7 | **Regression scan 失败 = 直接 deadlock** | 不给"再来一轮"放水；语义级问题须人工拍板 |

### 1.2 风险修复（Risk 1-5）

| ID | 修复 | 一句话 |
|---|---|---|
| R1 | **trace 双路径落地** | 本地 `/var/spec_traces/REQ-X.jsonl` 为权威源；收敛时复制进 PR；deadlock 仅本地存 |
| R2 | **gate 软重试 ≤ 2** | 区分 format / semantic finding；format 失败软重试不计轮（同轮内最多 2 次）；semantic 失败计正轮 |
| R3 | **acm-registry 写锁 + race 重算** | Coordinator 进程内 `asyncio.Lock`；commit 前 git pull → 若 sha 变则重算 patch + 重扫 regression |
| R4 | **ARCHITECTURE 一并冻结** | 入口快照打包 `spec_source_revision + architecture_revision + acm_registry_revision + acm_active_slice` |
| R5 | **deadlock 出口 = 扩展 spec_restart** | 守卫放宽到 `SPEC_TRANSFORMING(deadlocked=True)`；同 slash command；trace 归档加 `.deadlocked` 后缀 |

### 1.3 §3 工程取舍

| ID | 决策 | 理由 |
|---|---|---|
| E1 | **Orchestrator 内存为主，无 SQLite** | 实验项目；崩溃丢内存的 REQ 由 `/spec restart` 兜底；trace 仅审计不参与恢复 |
| E2 | **Regression scan 只在 compose_patch 后扫一次** | compose_patch 毫秒级；早 fail 收益不显著；少一份代码路径少一份漂移 |
| E3 | **agents/SKILL.md 在本仓库 docs/agents 维护** | 与既有 spec-author / spec-reviewer 同款风格；远端部署由独立任务 sync |
| E4 | **不加 feature flag** | 单实例 + 无生产用户；S1-S6 全完成才进 main 即可 |

---

## 二、架构总览

### 2.1 状态机变化

```
                    ┌──────────────────┐
   APPROVED ───►    │  SPEC_DRAFTING   │  ◄── 现有：spec-author / reviewer 闭环（已实现）
                    └────────┬─────────┘
                             │ checkpoint_1a_pass
                             ▼
                ╔══════════════════════════════╗
                ║      SPEC_TRANSFORMING       ║   ◄── 本期新增（核心战场）
                ║  ────────────────────────    ║
                ║  Round 1..3 博弈循环          ║
                ║   transformer ──┐            ║
                ║         │       │ callback   ║
                ║         ▼       │            ║
                ║   Coordinator   │            ║
                ║   ├ Computational gate (R2)  ║
                ║   ├ append trace.jsonl (R1)  ║
                ║   └ wake reviewer            ║
                ║         │                    ║
                ║         ▼                    ║
                ║   reviewer ─────callback─────╢
                ║                              ║
                ║  converged → regression scan ║
                ║   ├ pass → ACM patch + PR    ║
                ║   └ fail → DEADLOCK 工单     ║
                ╚══════════════╤═══════════════╝
                               │ transform_converged
                               ▼
                    ┌──────────────────┐
                    │   SPEC_LOCKED    │
                    └──────────────────┘
```

`SPEC_TRANSFORMING` 是一个**带 `deadlocked: bool` 标志**的复合状态，不引入独立 DEADLOCKED 状态——因为 deadlock 在状态机层本质就是"卡在 TRANSFORMING 但博弈停了"。

### 2.2 模块布局

```
src/requirement_workflow_v12/
  spec_state_machine.py    [改] 加 SPEC_TRANSFORMING + 三个事件 + deadlocked 标志
  spec_transform.py        [新] 博弈编排 SpecTransformOrchestrator
  spec_gate.py             [新] Computational gate 纯函数
  acm_registry.py          [新] registry IO + patch 生成 + 写锁
  regression_scan.py       [新] active AC 与骨架锚的双向校验
  github_gateway.py        [改] 加 commit_spec_pr_files / delete_branch
  coordinator_service.py   [改] 加 submit_checkpoint_1a_pass / spec_restart
  service_app.py           [改] 加 /openclaw/spec-transform-callback 端点 + slash command 解析

docs/agents/
  spec-transformer/
    SKILL.md               [新] 契约权威源
    callback-schema.json   [新] payload schema 镜像
  spec-transformer-reviewer/
    SKILL.md               [新]
    callback-schema.json   [新]

tests/
  test_spec_gate.py
  test_spec_transform_orchestrator.py
  test_acm_registry.py
  test_regression_scan.py
  test_spec_state_machine_transforming.py
  test_spec_restart.py
  test_service_app_spec_transform.py
  integration/test_spec_transform_e2e.py
```

### 2.3 关键不变量

1. **`spec_source_revision` + `architecture_revision` + `acm_registry_revision` 入口冻结**
   博弈期间所有轮次拿到的项目级上下文都是 `SPEC_TRANSFORMING` onEnter 时的快照，由 Coordinator 注入 payload；agent 不主动重新拉取
2. **trace.jsonl 单向 append-only**
   所有状态机转换先 append trace 再持久化新状态；崩溃时不依赖 trace 恢复但作为审计权威源
3. **Computational gate 失败不消耗 reviewer 配额，可消耗 transformer 软重试预算**
   format 失败 ≤ 2 次软重试不计轮；semantic 失败立即计正轮
4. **acm-registry 写入串行**
   Coordinator 进程内单写锁；锁内 pull + 算 patch + 扫 regression + commit；race 重算最多 3 次否则 deadlock

---

## 三、数据流

### 3.1 进入 SPEC_TRANSFORMING（一次性快照）

```
checkpoint_1a_pass 事件到达
  │
  ▼
Coordinator state machine: SPEC_DRAFTING → SPEC_TRANSFORMING
  │
  ▼ onEnter hook
[1] 拉飞书 Spec doc revision         → spec_source_revision
[2] 拉 scaffold 当前 ARCHITECTURE.yaml → architecture_revision (sha)
[3] 拉 scaffold 当前 acm-registry.yaml → acm_registry_revision (sha)
[4] 拉 acm-registry 中本项目 active AC → acm_active_slice
[5] 拼装 transform_context_snapshot:
    {
      req_id,
      spec_source_revision,
      architecture_revision,
      acm_registry_revision,
      acm_active_slice: [AC-001, AC-X-007, ...],
      captured_at,
    }
[6] open /var/spec_traces/REQ-{PROJECT}-{NNN}.jsonl (truncate)
    append: {event: "transform_started", snapshot, ts}
[7] GitHub 侧建 spec/REQ-{PROJECT}-{NNN} 分支（基于 main）
[8] 唤醒 transformer Round 1
```

**崩溃语义**：步骤 [1]-[6] 必须先于 [8]。若进程在 [6] 之后 [8] 之前崩溃，下次启动时检测"状态 TRANSFORMING 且 trace 只有 transform_started" → 标 deadlocked，等用户手工 `/spec restart`。

### 3.2 单轮博弈循环（Round N）

```
┌─────────────────────────────────────────────────────────────┐
│ Coordinator 唤醒 spec-transformer (Claude Code CLI subprocess)│
│   payload = snapshot + (Round ≥ 2 时附上轮 reviewer findings) │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼ transformer 输出四文件 + supersedes 声明
                          ▼ POST /openclaw/spec-transform-callback
                          ▼ event=transformer_output
                          │
                          ▼
              ┌───────────────────────┐
              │  Computational gate   │ (coordinator/spec_gate.py 纯函数)
              │  ─────────────────    │
              │  格式类:               │
              │   ① ac-schedule schema│
              │   ② tasks 正则        │
              │   ③ 路径一致性        │
              │  语义类:               │
              │   ④ Round 0 AC 回显   │
              │   ⑤ supersedes 完整性 │
              └───────────┬───────────┘
                          │
            ┌─────────────┴─────────────┐
            │                           │
       格式失败                     全部通过
            │                           │
            ▼                           ▼
   ┌──────────────────┐      trace.append({
   │ 软重试计数 < 2?   │        event: "gate_pass",
   └────┬─────────────┘        round: N, ...
        │                    })
   ┌────┴────┐                │
   是        否                ▼
   │         │       ┌──────────────────────┐
   │  trace.append({ │ 唤醒 spec-reviewer    │
   │   event:        │ payload = transformer │
   │   "round_used", │   输出 + snapshot     │
   │   reason:       └──────┬───────────────┘
   │   "format_max", │      │
   │   round: N      │      ▼ reviewer verdict + findings
   │ })              │      ▼ POST /openclaw/spec-transform-callback
   │ N += 1          │      ▼ event=reviewer_verdict
   ▼                 │      │
trace.append({       │      ▼
  event:             │  trace.append({
  "soft_retry",      │    event: "reviewer_verdict",
  round: N,          │    verdict, findings, round
  retry: K           │  })
})                   │      │
重新唤醒 transformer  │  verdict ∈ {converged, reject}
不增加轮次            │      │
                     │      ▼
                     │   converged?
                     │      │
                     │   ┌──┴──┐
                     │   是    否
                     │   │     │
                     │   │   N += 1, 唤醒 transformer Round N+1
                     │   │   (除非 N == max_rounds=3 → DEADLOCK)
                     │   ▼
                     │  进入收敛后阶段（§3.3）
                     ▼
              语义失败 → N += 1（同 reject 路径）
```

**软重试边界**：软重试只在**同一轮内**发生；transformer 收到 gate findings 后立即重生成；若 Round 1 软重试 2 次都败，N 跳到 2 进 Round 2，软重试计数归零。

### 3.3 收敛后阶段（transform_converged）

```
trace.append({event: "converged", round: N})
  │
  ▼
[1] 进入 acm_registry.write_lock (asyncio.Lock)
    │
    ▼
    [1a] git pull scaffold（拿最新 acm-registry.yaml）
    [1b] 对比锁入口快照的 acm_registry_revision：
         - 不变 → 用快照内的 active_slice 计算
         - 变了 → 用最新 active_slice 重算
                 race_retry_count += 1
                 race_retry_count > 3 → deadlock(reason=acm_race_giveup)
    [1c] coordinator/acm_registry.py 生成 patch:
         - active 追加：本 REQ 的 ac-schedule 全部 AC
         - retired 标注：design.md ## supersedes 中声明的旧 AC
    [1d] coordinator/regression_scan.py 扫描:
         对 patch 后的 active AC，每条必须满足
         (在 design.md ## supersedes 中已治理) ∨ (在新骨架中有 @pytest.mark.ac 锚)
         任何未满足 → deadlock(reason=regression_failed, missing=[...])
    [1e] 读 /var/spec_traces/REQ-X.jsonl 全文进内存，作为下一步多文件 commit 的一项
    [1f] github_gateway.commit_spec_pr_files (原子多文件 commit):
         - docs/specs/REQ-X/design.md
         - docs/specs/REQ-X/tasks.md
         - docs/specs/REQ-X/ac-schedule.yaml
         - docs/specs/REQ-X/harness/...（骨架，多文件）
         - docs/specs/REQ-X/transform_trace.jsonl
         - acm-registry.yaml（patch 后整体 overwrite，单 commit）
    [1g] 开 Spec PR
  │
  ▼ 释放锁
state → SPEC_LOCKED
trace.append({event: "locked", pr_url})
飞书消息：PR 链接 + 轮次摘要
```

### 3.4 Restart 路径

```
群消息 "/spec restart REQ-PROJ-005"
  │
  ▼
service_app 解析 → coordinator.spec_restart(req_id)
  │
  ▼
守卫：spec_status ∈ {SPEC_DRAFTING, SPEC_TRANSFORMING+deadlocked: true}?
  │
  ├─ 否 → 飞书报错 "当前状态不可重启，请走 retired REQ 流程"
  │
  └─ 是 ↓
[1] 飞书 Spec 文档归档（标题加前缀 [ARCHIVED-restart-{ts}]，移到归档文件夹）
[2] /var/spec_traces/REQ-X.jsonl → /var/spec_traces/archive/REQ-X.{ts}.deadlocked.jsonl
    （SPEC_TRANSFORMING+deadlocked 时还要把 GitHub 那边的 spec 分支删掉；
      deadlocked 路径不开 PR，所以无 PR 需要 close）
[3] 重置 Bitable: spec_status=null, spec_document_url=null,
     spec_source_revision=null, ai_ready=null, human_confirmed=null,
     deadlocked=null
[4] 飞书消息：已重置，请重新点"启动 Spec 撰写"
```

---

## 四、模块决策与文件清单

### 4.1 新建模块

#### `spec_gate.py` — Computational gate
```python
@dataclass(frozen=True)
class GateFinding:
    kind: Literal["format", "semantic"]
    rule: str           # "ac_schedule_schema" / "supersedes_completeness" / ...
    detail: str

@dataclass(frozen=True)
class GateResult:
    passed: bool
    findings: list[GateFinding]
    @property
    def has_format_failure(self) -> bool: ...
    @property
    def has_semantic_failure(self) -> bool: ...

def run_gate(
    payload: TransformerOutput,
    snapshot: TransformContextSnapshot,
) -> GateResult: ...
```
- **依赖**：jsonschema、pyyaml、re、pathlib（无网络无状态）
- **测试边界**：纯函数 + golden fixtures

#### `spec_transform.py` — 博弈编排
```python
class SpecTransformOrchestrator:
    def __init__(self, gateway: GitHubGateway, registry: AcmRegistry,
                 trace_dir: Path, max_rounds: int = 3, max_soft_retries: int = 2)

    async def on_enter_transforming(self, req_id: str) -> TransformContextSnapshot: ...
    async def handle_transformer_output(self, req_id, payload) -> NextAction: ...
    async def handle_reviewer_verdict(self, req_id, verdict, findings) -> NextAction: ...
    async def _on_converged(self, req_id) -> None: ...
    async def _to_deadlock(self, req_id, reason) -> None: ...

NextAction = Literal["soft_retry_transformer", "wake_reviewer",
                     "wake_transformer_next_round", "deadlock", "converged"]
```
- **状态**：内存中 `req_id → RoundContext`（轮次 / 软重试计数 / snapshot 引用）；崩溃丢失由 `/spec restart` 兜底（决策 E1）
- **测试边界**：注入 mock gateway / mock registry，断言 trace 序列与 NextAction

#### `acm_registry.py` — 注册表 IO + patch
```python
class AcmRegistry:
    def __init__(self, gateway: GitHubGateway):
        self._lock = asyncio.Lock()

    async def fetch_snapshot(self, project_repo) -> tuple[str, RegistryDoc]: ...
    async def active_ac_slice(self, project_repo: str) -> list[AcEntry]: ...

    def compose_patch(
        self,
        current: RegistryDoc,
        new_acs: list[AcScheduleEntry],
        supersedes: list[SupersedeDecl],
        req_id: str,
    ) -> RegistryDoc: ...

    @asynccontextmanager
    async def write_lock(self) -> AsyncIterator[None]: ...
```
- **测试边界**：fetch/compose 纯函数测；write_lock 用 asyncio 单元测保证互斥

#### `regression_scan.py` — 回归扫描
```python
@dataclass(frozen=True)
class RegressionResult:
    passed: bool
    missing: list[str]   # AC IDs neither superseded nor anchored

def scan(
    active_slice: list[AcEntry],
    supersedes_decl: list[SupersedeDecl],
    harness_files: dict[str, str],   # path -> content
) -> RegressionResult: ...
```

### 4.2 改造模块

#### `spec_state_machine.py`
- 新增事件：`SPEC_RESTART`（守卫：`DRAFTING ∪ TRANSFORMING(deadlocked=True)`）
  注：`TRANSFORM_CONVERGED` / `TRANSFORM_DEADLOCK` 已存在
- 新增字段（在 SpecState 上）：`deadlocked: bool = False`、`transform_context_snapshot: TransformContextSnapshot | None`
- 转换表：
  - `SPEC_TRANSFORMING + TRANSFORM_DEADLOCK → SPEC_TRANSFORMING(deadlocked=True)`（不离开状态，只置标志）
  - `{DRAFTING, TRANSFORMING(deadlocked)} + SPEC_RESTART → null`

#### `github_gateway.py`
- 新增方法：
  ```python
  async def commit_spec_pr_files(
      self, repo, branch, files: dict[str, str], message: str,
  ) -> str:  # commit sha
      """既有 commit_files 的语义化 wrapper；多文件原子 commit"""

  async def get_file_sha_and_content(self, repo, ref, path) -> tuple[str, str]: ...
  async def delete_branch(self, repo, branch) -> None: ...
  ```
- 不改既有方法签名

#### `coordinator_service.py`
- 新增方法：
  - `submit_checkpoint_1a_pass(req_id) -> SpecState`（驱动 DRAFTING → TRANSFORMING；触发 `orchestrator.on_enter_transforming`）
  - `spec_restart(req_id) -> SpecState`（守卫 + 归档 + 重置）
- 注入：`SpecTransformOrchestrator` + `AcmRegistry`

#### `service_app.py`
- 新增端点：`POST /openclaw/spec-transform-callback`
  - 校验 OpenClaw 签名（复用既有鉴权）
  - 解析 `event ∈ {transformer_output, reviewer_verdict}`
  - 派发到 orchestrator；返回 `next_action` 给 OpenClaw
- 改造端点：群消息处理器加 slash command 解析 `^/spec\s+restart\s+(REQ-\S+)$`

### 4.3 OpenClaw 侧契约（本仓库 docs/agents 维护，远端部署独立任务）

| 文件 | 内容 |
|---|---|
| `docs/agents/spec-transformer/SKILL.md` | 启动流程 + spec-transform-callback 子命令调用 + Round 0 AC 回显硬约束 + TransformerOutput schema |
| `docs/agents/spec-transformer/callback-schema.json` | `event=transformer_output` 的 JSON schema |
| `docs/agents/spec-transformer-reviewer/SKILL.md` | 启动流程 + 五维度 verdict + findings 结构 |
| `docs/agents/spec-transformer-reviewer/callback-schema.json` | `event=reviewer_verdict` 的 JSON schema |

**远端部署边界**：本仓库 docs/agents 是契约权威源；远端 OpenClaw workspace 的 `agents/<id>/SKILL.md` + `skills/<id>/SKILL.md` 双份由部署任务从本仓库 sync（参见项目记忆 `reference_openclaw_skill_dual_sync`）。

---

## 五、6 条状态转换垂直切片

按依赖图排序。每片都是端到端可演示（即使下游还没全打通）。

| 切片 # | 状态转换 / 入口事件 | 落地范围 | 演示判据 | 依赖 |
|---|---|---|---|---|
| **S1** | `null → SPEC_DRAFTING`（已实现，仅校验） | 跑既有 `submit_spec_start` + 测试覆盖检查 | 现有 e2e 测试通过 | 无 |
| **S2** | `SPEC_DRAFTING + SPEC_RESTART → null` | 新建：slash command 解析 + 守卫 + 归档/重置；spec_state_machine 加 SPEC_RESTART 事件 | 群里发 `/spec restart REQ-X` → Bitable 状态归零 + 飞书 doc 标 ARCHIVED | S1 |
| **S3** | `SPEC_DRAFTING + checkpoint_1a_pass → SPEC_TRANSFORMING`（onEnter snapshot） | 新建：`SPEC_TRANSFORMING` 状态 + onEnter hook（拉 ARCHITECTURE/acm-registry sha → snapshot → trace.jsonl 首行 `transform_started`）+ 建 GitHub spec 分支 | 模拟 1a pass → trace.jsonl 出现且 snapshot 字段齐全 + GitHub 上 spec 分支可见 | S1, github_gateway 既有 create_branch |
| **S4** | `SPEC_TRANSFORMING` 内单轮博弈（transformer→gate→reviewer→callback） | 新建：spec_gate.py + spec_transform.py 单轮逻辑 + service_app callback 端点 + agents/ 两份 SKILL.md + callback-schema.json | mock transformer/reviewer subprocess → 一轮收敛路径跑通 + trace 内 `gate_pass` `reviewer_verdict` 事件齐全 | S3 |
| **S5** | 软重试 + 多轮 + deadlock 路径 | 扩 spec_transform.py：软重试计数 / max_rounds 计数 / TRANSFORM_DEADLOCK 转换 / deadlocked 标志 + 扩 SPEC_RESTART 守卫到 deadlocked | 三类 deadlock 都能跑出：① reviewer 3 轮 reject ② 软重试 2 次后正轮再失败 3 轮 ③ 崩溃恢复（清内存模拟）→ 自动 deadlock | S4 |
| **S6** | `SPEC_TRANSFORMING + transform_converged → SPEC_LOCKED`（acm-registry patch + regression scan + Spec PR） | 新建：acm_registry.py + regression_scan.py + github_gateway.commit_spec_pr_files + write_lock 内重算路径 | 一轮收敛路径 → Spec PR 自动开 + acm-registry.yaml 和 trace.jsonl 都在 PR 文件列表 + regression fail 走 deadlock | S4, S5 |

**依赖图**：
```
S1 ── S2
   └── S3 ── S4 ── S5
              └── S6
```

S2 与 S3 可并行；S5 与 S6 都依赖 S4 但相互独立可并行。

---

## 六、失败模式总表

| 场景 | 触发点 | 状态机行为 | trace 事件 | 用户可见 |
|---|---|---|---|---|
| transformer subprocess 崩溃 | callback 超时（默认 5min） | TRANSFORM_DEADLOCK，deadlocked=true | `subprocess_timeout` | 飞书工单 |
| reviewer subprocess 崩溃 | 同上 | 同上 | 同上 | 同上 |
| Computational gate 格式失败 ≤ 2 次 | gate findings.kind=format | 不计轮，软重试 | `soft_retry` | 无 |
| Computational gate 格式失败 = 3 次 | 同上累积满 | 计正轮，进 round N+1（或 deadlock） | `round_used(reason=format_max)` | 飞书摘要 |
| Computational gate 语义失败 | gate findings.kind=semantic | 计正轮，回 transformer | `round_used(reason=semantic)` | 飞书摘要 |
| Reviewer reject | verdict=reject | 计正轮，回 transformer | `reviewer_verdict(reject)` | 飞书摘要 |
| Reviewer 3 轮全 reject | round_used == max_rounds | DEADLOCK | `deadlock(reason=max_rounds)` | 工单 |
| 收敛后 regression scan fail | scan.passed=False | DEADLOCK | `regression_failed` + missing AC 列表 | 工单 |
| acm-registry race（pull 后 sha 变） | write_lock 内 sha 比对 | 重算 patch + 重扫 + 提交；连续 race 3 次后 DEADLOCK | `acm_race_retry` / `acm_race_giveup` | 工单（giveup 时） |
| GitHub commit 失败 | gateway 抛 GitHubGatewayError | 不进 LOCKED；状态留 TRANSFORMING、deadlocked=true | `github_commit_failed` | 工单 |
| Coordinator 进程崩溃 | 内存 RoundContext 丢失 | 下次有事件进来时检测"状态 TRANSFORMING 但 orchestrator 无记录" → deadlocked=true | （无 trace，启动后补一行 `recovery_deadlock`） | 工单 |
| 飞书 doc / ARCHITECTURE revision 中途变了 | onEnter snapshot 之后 | 我们不主动重对比——入口冻结后博弈期间认快照为权威 | 无 | 无 |

---

## 七、测试策略

### 7.1 单元测试（per slice 落地时同步写）

| 切片 | 测试文件 | 关键 case |
|---|---|---|
| S2 | `test_spec_restart.py` | slash command 解析 / 守卫拒绝非法状态 / 归档副作用 |
| S3 | `test_spec_state_machine_transforming.py` + `test_spec_transform_onenter.py` | snapshot 字段完整 / GitHub 分支创建 / trace 首行格式 |
| S4 | `test_spec_gate.py` + `test_spec_transform_orchestrator.py`（单轮） | 5 类 gate rule 各 pass/fail / 单轮收敛路径 / callback 端点鉴权 |
| S5 | `test_spec_transform_orchestrator.py`（多轮） | 软重试计数 / max_rounds deadlock / subprocess 超时 / 崩溃恢复 deadlock |
| S6 | `test_acm_registry.py` + `test_regression_scan.py` + `test_spec_transform_converged.py` | patch 计算 / 写锁互斥 / race 重算 / regression fail / commit_spec_pr_files 原子性 |

### 7.2 集成测试（S6 完工时一次性跑）

`tests/integration/test_spec_transform_e2e.py`
- 真 Claude Code CLI subprocess（spec-transformer + reviewer，用 docs/agents/ 下 SKILL.md）
- 临时 git repo 模拟 scaffold（不打真 GitHub）
- 临时飞书 mock（用既有 fixture）
- 三条路径：① 一轮收敛 → SPEC_LOCKED + PR 文件齐全 ② 3 轮 reject → DEADLOCK + 工单 ③ regression fail → DEADLOCK

### 7.3 线上联调（部署任务 #22 范围）

- 真 OpenClaw 远端
- 真 GitHub
- 一个 staging REQ 跑通端到端

### 7.4 不在测试覆盖范围（明确划界）

- 多 Coordinator 实例并发（项目目前单实例）
- 网络抖动重试（让 OS / httpx 默认行为兜底）
- GitHub 限流（API 调用低频）
- trace.jsonl 文件锁（单 Coordinator 进程 + per-REQ 文件路径不会冲突）

---

## 八、实施排期与跨片协议

### 8.1 排期

```
S1（基线测试 / 0.5d）
 │
 ├─ S2（restart slash command / 1d）          ← 与 S3 可并行
 │
 └─ S3（SPEC_TRANSFORMING + snapshot / 1d）
     │
     └─ S4（单轮博弈 + agents/SKILL.md / 2d）
         │
         ├─ S5（软重试 / 多轮 / deadlock / 1.5d）   ← 与 S6 可并行
         │
         └─ S6（acm-registry + regression + PR / 2d）
                 │
                 └─ 集成测试 + e2e 真 subprocess / 1d
                         │
                         └─ #22 远端部署 + 线上联调 / 0.5d
```

**总预估**：8.5d 顺跑；并行后约 7d。人天为参考值，非承诺。

### 8.2 推进策略

| 阶段 | 分支 | PR 颗粒度 |
|---|---|---|
| S1-S6 | 每片一分支 `spec/transform/sN-<slice-name>` | 一片一 PR；S1 可并入 S2 PR |
| 集成测试 | 与 S6 同分支追加 commit | 不单开 |
| 部署联调 | 不动代码；新建 deploy/playbook | 单独 PR |

**回滚**：每片落地后跑既有 `tests/`（确保需求层未受影响）+ 新加测试；任何片失败不进下一片。S6 完成前不部署到 staging。

**feature flag**：决策 E4——不加。

### 8.3 跨片接口冻结清单

为避免后片翻前片：

| 接口 | 冻结于 | 后续切片只能扩不能改 |
|---|---|---|
| `TransformContextSnapshot` 字段集 | S3 完工 | S4-S6 |
| `TransformerOutput` schema | S4 完工 | S5-S6 |
| `GateFinding.kind / rule` 枚举 | S4 完工 | S5-S6 |
| trace.jsonl 事件 schema | 每片新增事件时同步更新 `agents/.../callback-schema.json` 镜像 | 永远向后兼容 |

### 8.4 文档同步点

| 时机 | 文档 |
|---|---|
| S3 完工 | `docs/context/layers/spec-harness-layer.md` §五补 SPEC_TRANSFORMING onEnter 实现细节 |
| S4 完工 | `docs/agents/spec-transformer{,-reviewer}/SKILL.md` 首版落地 |
| S6 完工 | 删 `docs/context/epics/spec-transform-epic-2026-04.md`（按 epic 自身完成承诺） |
| 部署完成 | 项目记忆 `project_spec_concurrency_protocol_not_implemented` 更新（本期已部分落地：A+C 弱版混合） |

---

## 九、未决项（不阻塞启动，留后续判断）

1. **崩溃恢复策略升级**——当前由 `/spec restart` 兜底；若实验后发现 Coordinator 重启频次显著影响实验节奏，再考虑 trace.jsonl 回放或 SQLite 持久化（决策 E1 的回退路径）
2. **多 Coordinator 实例并发**——当前架构假定单实例；若需横向扩展，acm-registry 写锁需升级为分布式锁（GitHub 侧乐观并发或 Redis lock）
3. **OpenClaw subprocess 超时阈值**——当前临时定 5min，需实验后根据 Claude Code CLI 实际处理时间调
4. **deadlock 工单飞书消息格式**——当前规划"贴 trace 末尾 N 行 + 缺失 AC 列表"，N 与卡片样式留实施时确定
