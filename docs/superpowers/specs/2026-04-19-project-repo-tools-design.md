# ProjectRepoTools — Tool 层解耦设计 · 2026-04-19

> **状态**：设计稿（待用户 review → 通过后调用 writing-plans 生成实施计划）
> **关联上下文**：
> - 当前实现：`src/requirement_workflow_v12/github_gateway.py`（层 4 原语）+ `spec_transform.py` / `acm_registry.py` / `coordinator_service.py` 里散落的业务调用
> - 上游依赖：无（纯架构重构，不引入新功能）
> - 下游使能：[PLANNING 阶段 brainstorming 进度快照](../../../memory/project_planning_phase_brainstorm_progress.md) —— Tool 层完成后才开始 PLANNING spec
>
> **范围**：把 Coordinator / orchestrator 里散落的 GitHub 调用收敛到一层领域动词 facade（`ProjectRepoTools`），并把状态机转移副作用显式化为钩子机制。**零新功能**，纯重构。
>
> **非范围**：不改动 `GitHubGateway` 的现有方法签名；不改状态机规则；不引入 PLANNING / Bootstrap 相关新动词（只预留接口扩展位）。

---

## 一、决策记录

为避免实施期翻案，方向性决策在此显式登记。

### 1.1 架构决策

| ID | 决策 | 取舍要点 |
|---|---|---|
| A1 | **四层分工** | 状态机（层 1）/ 编排（层 2）/ 领域 facade（层 3，新）/ HTTP 原语（层 4，现有） |
| A2 | **领域动词而非 HTTP 动词** | 层 3 API 表达业务意图（`commit_spec_artifacts`），调用方不构造 HTTP 参数 |
| A3 | **facade 返回领域对象** | `RepoRef` / `CommitRef` / `PrRef` / `ProjectContext`；调用方不触 GitHub payload |
| A4 | **现有 `GitHubGateway` 保留原貌** | 只是消费者从业务代码变成 facade；签名稳定，避免级联改动 |
| A5 | **钩子注册器显式化副作用入口** | `StateTransitionHooks` 对象持有 `on_enter` / `on_exit` 回调；所有 GitHub 操作只在钩子里触发 |
| A6 | **渐进迁移，端到端测试全程绿** | 4 步迁移，每步独立 commit / 可回滚；`test_spec_transform_e2e.py` 在每步后通过 |
| A7 | **命名中性（非"Github"前缀）** | `ProjectRepoTools` 为未来 GitLab / Gitee 实现留余地；不引入平台抽象层级 |

### 1.2 非决策（显式放弃）

| ID | 放弃 | 理由 |
|---|---|---|
| N1 | **不引入依赖注入框架** | Python 手动注入足够；`CoordinatorService.configure_*` 是注入点 |
| N2 | **不做 Repository 接口（多实现）** | 只有 GitHub 一个实现，`GitHubProjectRepoTools` 单类即可；多实现时再抽接口 |
| N3 | **不为本期 Plan / Bootstrap 动词占位** | 接口扩展位预留（A5 钩子机制），不预先声明未使用的方法 |
| N4 | **不改 `GitHubGateway` 内部** | 即使 `commit_spec_pr_files` 语义上"偏高"，保留不重构——本期目标是上层整洁，不是下层重构 |

---

## 二、架构总览

### 2.1 四层分工

```
┌─────────────────────────────────────────────────────┐
│ 层 1: spec_state_machine.py                         │
│   - 纯函数，零 I/O                                   │
│   - 事件 → Decision 对象                             │
│   - 本期不动                                         │
└────────────────────┬────────────────────────────────┘
                     │ Decision.next_status 由调用方应用
                     ↓
┌─────────────────────────────────────────────────────┐
│ 层 2: Orchestrators + Hooks                         │
│   - CoordinatorService                              │
│   - SpecTransformOrchestrator                       │
│   - StateTransitionHooks（新：统一钩子注册器）      │
│   - 业务流程编排；只调层 3                           │
└────────────────────┬────────────────────────────────┘
                     │ 领域动词调用
                     ↓
┌─────────────────────────────────────────────────────┐
│ 层 3: ProjectRepoTools（新模块 project_repo/）      │
│   领域动词 facade：                                  │
│   - fetch_project_context(project_repo)             │
│   - commit_spec_artifacts(req_id, artifacts)        │
│   - cleanup_failed_branch(project_repo, branch)     │
│   领域对象：RepoRef / CommitRef / PrRef /           │
│             ProjectContext / SpecArtifacts          │
└────────────────────┬────────────────────────────────┘
                     │ HTTP 原语调用
                     ↓
┌─────────────────────────────────────────────────────┐
│ 层 4: GitHubGateway（现有，不动）                    │
│   - create_branch / commit_files /                  │
│     open_pull_request / delete_branch /             │
│     fetch_file_sha / create_repo_from_template       │
└─────────────────────────────────────────────────────┘
```

### 2.2 本期交付范围

**建层 3 + 迁移现有调用**。涉及的代码位置：

| 现状 | 迁移后 |
|---|---|
| `spec_transform.py:142` `gateway.fetch_file_sha(..., "ARCHITECTURE.yaml")` + `:145` `gateway.fetch_file_sha(..., "acm-registry.yaml")` | `tools.fetch_project_context(project_repo)` → 返回 `ProjectContext(arch_sha, arch_text, registry_sha, registry_text)` |
| `spec_transform.py:168` `gateway.create_branch(...)` + `:321` `gateway.commit_spec_pr_files(...)` + `:360` `gateway.open_pull_request(...)` | `tools.commit_spec_artifacts(req_id, artifacts)` → 返回 `PrRef(number, html_url, head_sha, branch)` |
| `acm_registry.py:109` `self._gateway.fetch_file_sha(...)` | `tools.fetch_project_context(...)` 返回的 `registry_text` 直接用；AcmRegistry 降级为纯解析器（不再持有 gateway） |
| `spec_transform.py:???` deadlock 清理分支（如有）/ `cleanup_failed_branch` | `tools.cleanup_failed_branch(project_repo, branch)` |

---

## 三、层 3 接口规范

### 3.1 领域对象

```python
# src/requirement_workflow_v12/project_repo/types.py
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class ProjectContext:
    """结构化的项目当前状态快照。fetch_project_context 的返回值。"""
    project_repo: str               # "owner/repo"
    arch_sha: str                   # ARCHITECTURE.yaml 的 blob sha
    arch_text: str                  # 文本内容
    registry_sha: str               # acm-registry.yaml 的 blob sha
    registry_text: str              # 文本内容


@dataclass(frozen=True)
class SpecArtifacts:
    """spec-transformer 的四文件 + acm-registry patch 打包。

    commit_spec_artifacts 的输入。
    """
    project_repo: str               # "owner/repo"
    branch: str                     # "spec/REQ-P-001"
    base_branch: str                # "main" 或项目默认分支
    files: dict[str, str]           # path → text content
    commit_message: str
    pr_title: str
    pr_body: str


@dataclass(frozen=True)
class CommitRef:
    sha: str
    branch: str


@dataclass(frozen=True)
class PrRef:
    number: int
    html_url: str
    head_sha: str
    branch: str


@dataclass(frozen=True)
class RepoRef:
    """Bootstrap 返回；本期暂不使用，放这里是为 PLANNING spec 预留。"""
    owner: str
    name: str
    html_url: str
    default_branch: str
    initial_commit_sha: str
```

### 3.2 facade 接口

```python
# src/requirement_workflow_v12/project_repo/tools.py
from __future__ import annotations
from typing import Protocol

from .types import ProjectContext, SpecArtifacts, PrRef


class ProjectRepoTools(Protocol):
    """领域动词 facade。层 2 只依赖这个 Protocol。"""

    def fetch_project_context(self, project_repo: str) -> ProjectContext:
        """一次取回项目级上下文快照（ARCHITECTURE + acm-registry）。

        内部：两次 fetch_file_sha 合并。
        失败：任一文件不存在或 API 错 → 抛 ProjectRepoError。
        """

    def commit_spec_artifacts(
        self, req_id: str, artifacts: SpecArtifacts
    ) -> PrRef:
        """产出 Spec PR：创建分支 → 原子 commit → 开 PR。

        内部：create_branch + commit_files + open_pull_request 三步串联。
        失败：任一步失败 → 尽力清理已创建的分支 → 抛 ProjectRepoError。
        """

    def cleanup_failed_branch(self, project_repo: str, branch: str) -> None:
        """删除失败的 spec 分支。幂等。

        内部：delete_branch。失败也吞异常（仅 logger.warning）。
        """


class GitHubProjectRepoTools:
    """默认实现，内部委托给 GitHubGateway。"""

    def __init__(self, gateway: "GitHubGateway"):
        self._gw = gateway

    def fetch_project_context(self, project_repo: str) -> ProjectContext:
        arch_sha, arch_text = self._gw.fetch_file_sha(
            project_repo, "main", "ARCHITECTURE.yaml"
        )
        registry_sha, registry_text = self._gw.fetch_file_sha(
            project_repo, "main", "acm-registry.yaml"
        )
        return ProjectContext(
            project_repo=project_repo,
            arch_sha=arch_sha,
            arch_text=arch_text,
            registry_sha=registry_sha,
            registry_text=registry_text,
        )

    def commit_spec_artifacts(
        self, req_id: str, artifacts: SpecArtifacts
    ) -> PrRef:
        owner, name = artifacts.project_repo.split("/", 1)
        try:
            self._gw.create_branch(
                owner=owner, repo=name,
                branch=artifacts.branch, from_branch=artifacts.base_branch,
            )
            head_sha = self._gw.commit_spec_pr_files(
                artifacts.project_repo, artifacts.branch,
                artifacts.files, artifacts.commit_message,
            )
            pr = self._gw.open_pull_request(
                owner=owner, repo=name,
                head_branch=artifacts.branch, base_branch=artifacts.base_branch,
                title=artifacts.pr_title, body=artifacts.pr_body,
            )
        except GitHubGatewayError as exc:
            self.cleanup_failed_branch(artifacts.project_repo, artifacts.branch)
            raise ProjectRepoError(
                f"commit_spec_artifacts failed for {req_id}: {exc}",
                recoverable=False,
            ) from exc
        return PrRef(
            number=pr["number"], html_url=pr["html_url"],
            head_sha=head_sha, branch=artifacts.branch,
        )


class ProjectRepoError(RuntimeError):
    """领域层错误。封装下层 GitHubGatewayError 给调用方。

    recoverable=True 表示调用方可重试（网络抖动等）；False 表示需要人工介入。
    """
    def __init__(self, message: str, *, recoverable: bool = False):
        super().__init__(message)
        self.recoverable = recoverable
```

**设计注记**：
- `SpecArtifacts` 目前缺 `project_repo` 字段；实施时补齐（由 orchestrator 调用前填入）。
- `Protocol` 而非 `ABC`：Python 结构化类型，mock 对象无需继承。
- `fetch_project_context` 当前只拿两文件；未来 PLANNING 接入后扩展字段即可，不破坏调用方。

### 3.3 错误处理契约

- **领域层外抛 `ProjectRepoError`**，封装 HTTP 细节
- **`GitHubGatewayError` 不穿透到层 2**
- 调用方处理 `ProjectRepoError.recoverable: bool` 判断是否重试

---

## 四、钩子机制

### 4.1 现状的耦合

```python
# coordinator_service.py 当前
def submit_checkpoint_1a_pass(self, req_id: str):
    cfg = self.project_configs.get(...)
    if cfg is None or not cfg.github_repo_url:
        raise ValueError(...)
    decision = apply_spec_event(...)
    r.spec_status = decision.next_status
    self.spec_orchestrator.on_enter_transforming(...)  # ← 直接方法调用
```

问题：
- 状态转移副作用（`on_enter_transforming`）和状态机应用（`apply_spec_event`）耦合在同一方法里
- 新状态（如 PLANNING）来了只能在这里堆 `if-else`
- 单测 `submit_checkpoint_1a_pass` 必须 mock 整个 orchestrator

### 4.2 目标：钩子注册器

```python
# src/requirement_workflow_v12/project_repo/hooks.py
from __future__ import annotations
from typing import Callable
from ..models import Requirement
from ..spec_state_machine import SpecStatus

HookFn = Callable[[Requirement], None]


class StateTransitionHooks:
    """注册 spec 状态转移的回调。

    on_enter(status, fn): 进入 status 时触发（apply_spec_event 后）
    on_exit(status, fn):  离开 status 时触发（apply_spec_event 前）
    """

    def __init__(self) -> None:
        self._on_enter: dict[SpecStatus, list[HookFn]] = {}
        self._on_exit: dict[SpecStatus, list[HookFn]] = {}

    def on_enter(self, status: SpecStatus, fn: HookFn) -> None:
        self._on_enter.setdefault(status, []).append(fn)

    def on_exit(self, status: SpecStatus, fn: HookFn) -> None:
        self._on_exit.setdefault(status, []).append(fn)

    def fire_enter(self, status: SpecStatus, req: Requirement) -> None:
        for fn in self._on_enter.get(status, ()):
            fn(req)

    def fire_exit(self, status: SpecStatus, req: Requirement) -> None:
        for fn in self._on_exit.get(status, ()):
            fn(req)
```

### 4.3 Coordinator 使用模式

```python
# coordinator_service.py 迁移后
def __init__(self):
    ...
    self._hooks = StateTransitionHooks()

def configure_spec_orchestrator(self, *, tools, trace_dir, feishu):
    self._tools = tools
    self.spec_orchestrator = SpecTransformOrchestrator(
        tools=tools, trace_dir=trace_dir, feishu=feishu,
        on_locked=self._on_spec_locked,
        on_deadlock=self._on_spec_deadlock,
    )
    self._hooks.on_enter(
        SpecStatus.TRANSFORMING, self._on_enter_transforming
    )

def submit_checkpoint_1a_pass(self, req_id: str):
    r = self.requirements[req_id]
    cfg = self.project_configs.get(r.project)
    if cfg is None or not cfg.github_repo_url:
        raise ValueError(f"项目 {r.project} 未配置 github_repo_url")

    prev_status = r.spec_status
    decision = apply_spec_event(r.spec_status, SpecEvent.CHECKPOINT_1A_PASS)
    if not decision.allowed:
        raise ValueError(decision.message)

    self._hooks.fire_exit(prev_status, r)
    r.spec_status = decision.next_status
    self._hooks.fire_enter(r.spec_status, r)
    return r

def _on_enter_transforming(self, r: Requirement):
    self.spec_orchestrator.on_enter_transforming(
        req_id=r.req_id,
        project_repo=self._project_repo_for(r.req_id),
        spec_doc_id=r.spec_document_id,
    )
```

**收益**：
- PLANNING 来了只需 `self._hooks.on_enter(SpecStatus.PLANNING, self._on_enter_planning)`，不改 `submit_checkpoint_*` 这些通用方法
- 单测 `submit_checkpoint_1a_pass` 只需 mock `self._hooks`，不需要关心 orchestrator 内部
- 钩子顺序明确：`fire_exit → 状态应用 → fire_enter`

### 4.4 钩子异常契约

钩子函数抛异常 → **向上抛到触发方**（不吞不 log-and-continue）。理由：
- 副作用失败是真实失败，调用方（如 `submit_checkpoint_1a_pass`）需要感知
- 第一个钩子失败时后续钩子**不执行**（fail-fast）
- 调用方决定是否回滚状态（本期不做自动回滚，失败即停）

状态转移的原子性：`fire_exit` 抛异常 → 不应用新状态；`fire_enter` 抛异常 → 状态已应用但副作用失败，需要人工介入（未来可扩展补偿钩子，本期不做）。

**可观测性要求**（向上抛不等于黑盒）：
- `StateTransitionHooks.fire_enter` / `fire_exit` 在回调抛异常时 **先 log 再 re-raise**，日志字段固定：
  - `event`：`hook_exception`
  - `transition`：`enter` / `exit`
  - `status`：目标 / 离开的 SpecStatus
  - `req_id`：来自 Requirement
  - `hook_name`：`fn.__qualname__`
  - `exception`：类型 + 消息（不含完整 traceback，traceback 进 `logger.exception`）
- `ProjectRepoError` 构造时必须带 `from exc` 保留 cause chain；调用方在上层 log 时能看到完整链路
- 钩子抛出的异常类型必须是 `ProjectRepoError` 或其子类（业务钩子自己决定是否包装）；内置 Python 异常（`KeyError` 等）若来自业务 bug，允许穿透，由服务层顶部错误处理统一捕获并记录

单测要求：`test_project_repo_hooks.py` 验证"钩子异常时日志字段齐全"。

---

## 五、模块结构

```
src/requirement_workflow_v12/
├── project_repo/                  ← 新模块
│   ├── __init__.py                ← 导出 ProjectRepoTools / 领域对象
│   ├── tools.py                   ← Protocol + GitHubProjectRepoTools 实现
│   ├── types.py                   ← 领域对象 dataclass
│   └── hooks.py                   ← StateTransitionHooks
├── coordinator_service.py         ← 改造：调用 tools 而非 gateway，注册钩子
├── spec_transform.py              ← 改造：持有 tools 而非 gateway
├── acm_registry.py                ← 改造：降级为纯解析器，不持 gateway
├── github_gateway.py              ← 不动
└── ...（其他文件不动）

tests/
├── test_project_repo_tools.py     ← 新：层 3 ↔ 层 4 翻译正确性
├── test_project_repo_hooks.py     ← 新：钩子注册/触发
├── test_spec_transform_e2e.py     ← 改造：mock ProjectRepoTools 而非 mock gateway
└── ...（其他测试不动）
```

---

## 六、迁移计划

四步增量，每步独立 commit，每步之后 `pytest -q` 必须全绿。

### Step 1：建层 3 骨架（约 1 小时）
- 新增 `project_repo/types.py`、`project_repo/tools.py`、`project_repo/hooks.py`
- `GitHubProjectRepoTools` 实现 `fetch_project_context` / `commit_spec_artifacts` / `cleanup_failed_branch`
- 新增 `tests/test_project_repo_tools.py`：mock gateway 测翻译正确性
- **旧路径不变**，新层与旧路径并存
- **验收**：新单测绿；现有测试全部照常

### Step 2：迁 SpecTransformOrchestrator（约 1.5 小时）
- `SpecTransformOrchestrator.__init__(self, tools: ProjectRepoTools, ...)` 替代 `github_gateway: GitHubGateway`
- 所有 `self._gateway.*` 调用换为 `self._tools.*` 领域动词
- `test_spec_transform_e2e.py` 的 `_gateway_mock()` 改为 `_tools_mock()` —— 返回 `ProjectContext` / `PrRef` 等领域对象
- **验收**：e2e 测试全绿；现有 orchestrator 单测全绿

### Step 3：迁 CoordinatorService + AcmRegistry（约 1.5 小时）
- `AcmRegistry.__init__` 去掉 `gateway` 参数；`fetch_snapshot` 改为消费外部传入的 `registry_text`（或接受 `ProjectContext`）
- `CoordinatorService.configure_spec_orchestrator` 签名从 `github_gateway=` 改为 `tools=`
- `service_app.py` 的启动装配同步修改（工厂函数构造 `tools = GitHubProjectRepoTools(gateway)`）
- **验收**：e2e 绿；启动 staging 容器 smoke test 绿

### Step 4：钩子显式化（约 1 小时）
- 新增 `StateTransitionHooks` 并在 `CoordinatorService.__init__` 实例化
- `submit_checkpoint_1a_pass` / 其他状态转移方法插入 `fire_exit` / `fire_enter`
- `configure_spec_orchestrator` 改为注册钩子而非直接持有 orchestrator
- 新增 `tests/test_project_repo_hooks.py`
- **验收**：新单测绿；e2e 绿；`submit_checkpoint_1a_pass` 单测用 mock hooks 跑通

### 回滚策略
- 每步一个独立 commit，回滚单步 = `git revert <sha>`
- Step 2/3 如出问题可回到 Step 1（新层存在但无人用），不影响生产

---

## 七、测试策略

### 7.1 测试金字塔

| 层 | 测试文件 | 覆盖 | 替身 | 数量级 |
|---|---|---|---|---|
| 层 1 纯函数 | `test_spec_state_machine*.py`（现有） | 状态机规则 | 无 | 不变 |
| 层 2 编排 | `test_spec_transform_e2e.py`（改造） | orchestrator / coordinator 编排 | mock `ProjectRepoTools` | mock 量从 ~20 行降到 ~5 行 |
| 层 3 翻译 | `test_project_repo_tools.py`（新） | 领域动词 → gateway 调用正确性 | mock `GitHubGateway` | 约 4-6 个测试 |
| 层 3 钩子 | `test_project_repo_hooks.py`（新） | 注册 + 触发顺序 | 无 | 约 3-4 个测试 |
| 层 4 HTTP | —— | GitHub 原语 | 略 | 不在本期范围（现有 gateway 已有覆盖） |

### 7.2 关键测试用例

**层 3 翻译层**：
- `fetch_project_context` 两次 fetch 失败一次 → 抛 `ProjectRepoError`
- `commit_spec_artifacts` 在 `open_pull_request` 失败时调用 `cleanup_failed_branch`
- `cleanup_failed_branch` 在 gateway 抛异常时只 log 不抛

**层 3 钩子**：
- `on_enter` 注册多个回调 → `fire_enter` 按注册顺序触发
- 钩子函数抛异常 → 第一个异常向上抛出，后续钩子不执行（契约见 § 4.4）
- `fire_exit` 的 status 参数是**离开前的** status

**层 2 e2e**（改造后）：
- 原 `test_one_round_converged_locks_spec_with_audit_fields` 走通，mock tools 返回预设 `PrRef`
- 原 `test_three_round_deadlock_sets_spec_deadlocked_flag` 走通，mock tools 不被调用到 `commit_spec_artifacts`

---

## 八、风险与对策

| 风险 | 对策 |
|---|---|
| **AcmRegistry 降级影响并发写锁语义**（R3 已有对策） | AcmRegistry 降级后只管解析；并发写锁逻辑上移到 `commit_spec_artifacts` 或独立 `registry_writer` |
| **SpecArtifacts 缺 project_repo 字段** | Step 2 定义时就补全，orchestrator 调用前填入 |
| **Step 3 装配层修改遗漏** | `service_app.py` 改完跑 staging smoke test 验证 |
| **PLANNING 来了 tools 要扩方法** | facade 本身就是扩展点；新动词独立 PR 追加，不影响现有 |

---

## 九、验收标准

### 9.1 代码层面
- [ ] `project_repo/` 模块存在且内容符合 § 5 结构
- [ ] 业务代码（coordinator / orchestrator / acm_registry）**零**直接 `gateway.*` 调用
- [ ] `GitHubGateway` 方法签名未变，`git blame` 显示无改动
- [ ] `StateTransitionHooks` 被 `CoordinatorService` 持有并使用

### 9.2 测试层面
- [ ] `pytest -q` 全绿
- [ ] 新增 `test_project_repo_tools.py` / `test_project_repo_hooks.py` 覆盖 § 7.2 列出的关键用例
- [ ] e2e 测试的 mock 代码从 mock gateway 转为 mock tools

### 9.3 运行层面
- [ ] staging 部署启动，`/healthz` 绿
- [ ] staging 环境重跑一次已验证过的完整 spec-transform 链路（REQ-test2-002 级别），行为一致

### 9.4 文档层面
- [ ] 按 § 10 "文档同步计划"分发内容到对应文档
- [ ] 新模块 docstring 符合现有注释风格

---

## 十、文档同步计划（实施完成后执行）

实施完成并通过验收后，按下述分发把内容填进对应文档。**不要把所有细节塞进一个文件**。每个文件只承载属于它的内容。

### 10.1 内容归属原则

| 内容性质 | 归属文件 | 判断标准 |
|---|---|---|
| **架构原则**（跨项目复用的设计智慧） | `docs/context/infra/` | "其他项目/未来演进也会用到" |
| **方法论契约**（工作流和职责约束） | `docs/context/harness-engineering-methodology-v2.0.md` | "约束 agent / 状态机行为的公共规则" |
| **层实现细节**（特定层的工程选择） | `docs/context/layers/spec-harness-layer.md` | "实施这一层时需要知道的具体做法" |
| **本次设计记录**（历史决策 + trade-off） | 本 spec 文件（不动） | "为什么当时这么选" —— 审计用 |

### 10.2 具体分发任务

**A. 新增 `docs/context/infra/state-machine-hook-pattern.md`**
- 覆盖：纯状态机 + 钩子机制的架构原则、适用场景、反模式
- 来源：本 spec § 2.1 / § 4.2 / § 4.4
- 不含：facade 接口细节（那是特定实现，不是原则）

**B. 更新 `docs/context/harness-engineering-methodology-v2.0.md`**
- 位置：§七并发写回契约 之后，新增一小节"副作用职责边界"
- 覆盖：Coordinator 的 GitHub 操作只在钩子里触发；状态机本身不允许 I/O
- 仅补一段话 + 指回 `infra/state-machine-hook-pattern.md`
- 不含：类名、模块路径、代码示例

**C. 更新 `docs/context/layers/spec-harness-layer.md`**
- 位置：§十一 实现与部署（若无则新增）
- 覆盖：
  - `project_repo/` 模块的职责边界（一段话）
  - 领域动词清单（表格形式，不含完整签名）
  - 指回本 spec 文件看完整 API
- 不含：决策 trade-off、迁移步骤、self-review 细节

**D. 不改的文件（明确列出避免误动）**
- `docs/context/infra/context-chain-principle.md` —— 并发写回契约未变
- 所有其他 `docs/superpowers/specs/*.md` —— 历史 spec 保留原貌

### 10.3 文档更新的验收

- [ ] A/B/C 三个文件更新完成且 `git diff` 可审
- [ ] 三处更新**互不重复**内容（同一句话不出现在两个文件里）
- [ ] 每处更新都有**单向链接**指向本 spec 作为完整参考
- [ ] 本 spec 文件**不改**（作为不可变历史记录）

---

## 十一、后续衔接

Tool 层 spec 完成并实施后，下一步按顺序：

1. **PLANNING 阶段 spec**（基于本 spec 的 facade 扩展 Plan / Bootstrap 动词）
   - 设计进度已在 `memory/project_planning_phase_brainstorm_progress.md` 快照
   - facade 新增：`commit_plan` / `bootstrap_project` / `fetch_historical_plans` / `apply_architecture_change`
2. **Spec 结构自适应**（green-field vs brown-field）
3. **req-registry** 建设（见 memory 中"项目引导层"方向）

本 spec 完成后，这些后续工作的 GitHub 操作都走干净的 facade 路径。

---

## 附录 A：领域对象命名理由

| 对象 | 不叫什么 | 叫什么 | 理由 |
|---|---|---|---|
| `ProjectContext` | `ArchAndRegistry`、`GitHubFetchResult` | `ProjectContext` | 表达"项目当前状态的结构化快照"，不暴露获取方式 |
| `SpecArtifacts` | `CommitRequest`、`FourFilePayload` | `SpecArtifacts` | 表达领域含义（Spec 阶段的产物集合），不暴露底层是 commit |
| `PrRef` | `GitHubPrResponse` | `PrRef` | 轻量引用对象，仅供定位后续操作 |
| `RepoRef` | `RepoInfo`、`GitHubRepo` | `RepoRef` | 同上，未来 Bootstrap 用 |

## 附录 B：重构前后 call-graph 对比

**重构前**（当前）：
```
service_app.py
  └─ CoordinatorService
      ├─ (直调) GitHubGateway.fetch_file_sha
      └─ SpecTransformOrchestrator
          ├─ GitHubGateway.fetch_file_sha
          ├─ GitHubGateway.create_branch
          ├─ GitHubGateway.commit_spec_pr_files
          ├─ GitHubGateway.open_pull_request
          └─ AcmRegistry
              └─ GitHubGateway.fetch_file_sha
```

**重构后**：
```
service_app.py
  └─ CoordinatorService
      ├─ ProjectRepoTools (protocol)          ← 新
      ├─ StateTransitionHooks                  ← 新
      └─ SpecTransformOrchestrator
          ├─ ProjectRepoTools.fetch_project_context
          ├─ ProjectRepoTools.commit_spec_artifacts
          ├─ ProjectRepoTools.cleanup_failed_branch
          └─ AcmRegistry                       ← 降级为纯解析器
              (接收 registry_text，不持 gateway)

GitHubProjectRepoTools (impl)
  └─ GitHubGateway (未改动)
```
