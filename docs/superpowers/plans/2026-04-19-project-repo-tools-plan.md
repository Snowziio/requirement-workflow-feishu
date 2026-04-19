# ProjectRepoTools Tool 层解耦 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把散落在 `SpecTransformOrchestrator` / `CoordinatorService` / `AcmRegistry` 里对 `GitHubGateway` 的直接调用收敛到新的领域动词 facade `ProjectRepoTools`，并把状态转移副作用显式化为 `StateTransitionHooks` 注册器；纯重构，零新功能。

**Architecture:** 四层分工：状态机（层 1，纯函数）/ 编排（层 2，orchestrator + coordinator + hooks）/ 领域 facade（层 3，新 `project_repo/` 模块）/ HTTP 原语（层 4，现有 `GitHubGateway`，不动）。四步渐进迁移，每步独立 commit，`pytest -q` 每步全绿。

**Tech Stack:** Python 3.11 / dataclasses / typing.Protocol / pytest / httpx（仅层 4 用）/ 现有 `GitHubGateway`。

**Spec 链接：** `docs/superpowers/specs/2026-04-19-project-repo-tools-design.md`（本计划的完整设计依据，阅读前先读 § 三 / § 四 / § 六 / § 十）

---

## File Structure

**新增：**
- `src/requirement_workflow_v12/project_repo/__init__.py` — 模块出口（re-export 公共符号）
- `src/requirement_workflow_v12/project_repo/types.py` — 领域对象（`ProjectContext` / `SpecArtifacts` / `CommitRef` / `PrRef` / `RepoRef`）
- `src/requirement_workflow_v12/project_repo/tools.py` — `ProjectRepoTools` Protocol + `GitHubProjectRepoTools` 实现 + `ProjectRepoError`
- `src/requirement_workflow_v12/project_repo/hooks.py` — `StateTransitionHooks` 注册器
- `tests/test_project_repo_tools.py` — 层 3 翻译层单测
- `tests/test_project_repo_hooks.py` — 钩子注册 / 触发 / 异常可观测性单测
- `docs/context/infra/state-machine-hook-pattern.md` — 架构原则（新）

**修改：**
- `src/requirement_workflow_v12/spec_transform.py` — `__init__` 改接 `tools`；`on_enter_transforming` / `_on_converged` 走 facade
- `src/requirement_workflow_v12/acm_registry.py` — 去掉 `gateway` 参数；`fetch_snapshot` 接受外部 `registry_text`
- `src/requirement_workflow_v12/coordinator_service.py` — `configure_spec_orchestrator` 参数换为 `tools`；`__init__` 实例化 hooks；`submit_checkpoint_1a_pass` 走 hooks
- `src/requirement_workflow_v12/service_app.py` — 装配层构造 `tools = GitHubProjectRepoTools(gateway)`
- `tests/test_spec_transform_e2e.py` — `_gateway_mock()` → `_tools_mock()`
- `docs/context/harness-engineering-methodology-v2.0.md` — §七 后新增"副作用职责边界"小节
- `docs/context/layers/spec-harness-layer.md` — 新增 §十一 实现与部署

**不动：**
- `src/requirement_workflow_v12/github_gateway.py` — 完全不动（层 4 原语稳定）
- `src/requirement_workflow_v12/spec_state_machine.py` — 纯函数，不动
- `docs/context/infra/context-chain-principle.md` — 并发契约未变

---

## Step 1 — 建层 3 骨架

目标：`project_repo/` 模块存在、有单测、能被外部 import；**旧业务代码路径完全不变**。Step 1 结束时 `pytest -q` 全绿，新老代码并存。

### Task 1.1: 创建模块骨架 + 领域对象 dataclass

**Files:**
- Create: `src/requirement_workflow_v12/project_repo/__init__.py`
- Create: `src/requirement_workflow_v12/project_repo/types.py`
- Test: `tests/test_project_repo_tools.py`

- [ ] **Step 1: 写失败测试 `test_domain_types_are_frozen_dataclasses`**

```python
# tests/test_project_repo_tools.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest
from dataclasses import FrozenInstanceError

from requirement_workflow_v12.project_repo.types import (
    ProjectContext, SpecArtifacts, CommitRef, PrRef, RepoRef,
)


def test_domain_types_are_frozen_dataclasses():
    ctx = ProjectContext(
        project_repo="o/r", arch_sha="a", arch_text="kind: x\n",
        registry_sha="b", registry_text="version: 3\n",
    )
    with pytest.raises(FrozenInstanceError):
        ctx.arch_sha = "mutated"  # type: ignore[misc]

    art = SpecArtifacts(
        project_repo="o/r", branch="spec/REQ-P-1", base_branch="main",
        files={"a.md": "x"}, commit_message="m", pr_title="t", pr_body="b",
    )
    assert art.files["a.md"] == "x"

    assert CommitRef(sha="s", branch="b").sha == "s"
    assert PrRef(number=1, html_url="u", head_sha="s", branch="b").number == 1
    assert RepoRef(
        owner="o", name="r", html_url="u",
        default_branch="main", initial_commit_sha="s",
    ).owner == "o"
```

- [ ] **Step 2: 运行验证失败**

Run: `pytest tests/test_project_repo_tools.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'requirement_workflow_v12.project_repo'`

- [ ] **Step 3: 实现 `types.py`**

```python
# src/requirement_workflow_v12/project_repo/types.py
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProjectContext:
    """项目当前状态的结构化快照。`fetch_project_context` 的返回值。"""
    project_repo: str
    arch_sha: str
    arch_text: str
    registry_sha: str
    registry_text: str


@dataclass(frozen=True)
class SpecArtifacts:
    """Spec 阶段四文件 + acm-registry patch 的打包。`commit_spec_artifacts` 的输入。"""
    project_repo: str
    branch: str
    base_branch: str
    files: dict[str, str]
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
    owner: str
    name: str
    html_url: str
    default_branch: str
    initial_commit_sha: str
```

- [ ] **Step 4: 实现 `__init__.py`**

```python
# src/requirement_workflow_v12/project_repo/__init__.py
from __future__ import annotations

from .types import (
    CommitRef,
    PrRef,
    ProjectContext,
    RepoRef,
    SpecArtifacts,
)

__all__ = [
    "CommitRef",
    "PrRef",
    "ProjectContext",
    "RepoRef",
    "SpecArtifacts",
]
```

- [ ] **Step 5: 运行验证通过**

Run: `pytest tests/test_project_repo_tools.py -v`
Expected: PASS (1/1)

- [ ] **Step 6: Commit**

```bash
git add src/requirement_workflow_v12/project_repo/__init__.py \
        src/requirement_workflow_v12/project_repo/types.py \
        tests/test_project_repo_tools.py
git commit -m "feat(project_repo): add domain types for tool-layer facade"
```

---

### Task 1.2: ProjectRepoError 异常 + Protocol

**Files:**
- Create: `src/requirement_workflow_v12/project_repo/tools.py`
- Modify: `src/requirement_workflow_v12/project_repo/__init__.py`
- Modify: `tests/test_project_repo_tools.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_project_repo_tools.py — 追加
from requirement_workflow_v12.project_repo.tools import (
    ProjectRepoError, ProjectRepoTools,
)


def test_project_repo_error_carries_recoverable_flag():
    err = ProjectRepoError("boom", recoverable=True)
    assert err.recoverable is True
    assert "boom" in str(err)

    default = ProjectRepoError("x")
    assert default.recoverable is False


def test_project_repo_tools_is_protocol():
    # Protocol 结构化类型：mock/duck typing 即可，无需继承
    class Dummy:
        def fetch_project_context(self, project_repo): ...
        def commit_spec_artifacts(self, req_id, artifacts): ...
        def cleanup_failed_branch(self, project_repo, branch): ...

    assert isinstance(Dummy(), ProjectRepoTools)
```

- [ ] **Step 2: 运行验证失败**

Run: `pytest tests/test_project_repo_tools.py -v`
Expected: FAIL with import error on `tools.py`

- [ ] **Step 3: 实现 `tools.py` 框架**

```python
# src/requirement_workflow_v12/project_repo/tools.py
from __future__ import annotations

from typing import Protocol, runtime_checkable

from .types import PrRef, ProjectContext, SpecArtifacts


class ProjectRepoError(RuntimeError):
    """领域层错误。封装下层 GitHubGatewayError 给调用方。

    recoverable=True 表示调用方可重试（网络抖动等）；False 表示需要人工介入。
    """

    def __init__(self, message: str, *, recoverable: bool = False):
        super().__init__(message)
        self.recoverable = recoverable


@runtime_checkable
class ProjectRepoTools(Protocol):
    """领域动词 facade。层 2 只依赖这个 Protocol。"""

    def fetch_project_context(self, project_repo: str) -> ProjectContext: ...

    def commit_spec_artifacts(
        self, req_id: str, artifacts: SpecArtifacts,
    ) -> PrRef: ...

    def cleanup_failed_branch(self, project_repo: str, branch: str) -> None: ...
```

- [ ] **Step 4: 更新 `__init__.py` 导出**

```python
# src/requirement_workflow_v12/project_repo/__init__.py
from __future__ import annotations

from .tools import ProjectRepoError, ProjectRepoTools
from .types import (
    CommitRef,
    PrRef,
    ProjectContext,
    RepoRef,
    SpecArtifacts,
)

__all__ = [
    "CommitRef",
    "PrRef",
    "ProjectContext",
    "ProjectRepoError",
    "ProjectRepoTools",
    "RepoRef",
    "SpecArtifacts",
]
```

- [ ] **Step 5: 运行验证通过**

Run: `pytest tests/test_project_repo_tools.py -v`
Expected: PASS (3/3)

- [ ] **Step 6: Commit**

```bash
git add src/requirement_workflow_v12/project_repo/tools.py \
        src/requirement_workflow_v12/project_repo/__init__.py \
        tests/test_project_repo_tools.py
git commit -m "feat(project_repo): add ProjectRepoError + ProjectRepoTools Protocol"
```

---

### Task 1.3: GitHubProjectRepoTools.fetch_project_context

**Files:**
- Modify: `src/requirement_workflow_v12/project_repo/tools.py`
- Modify: `tests/test_project_repo_tools.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_project_repo_tools.py — 追加
from unittest.mock import MagicMock

from requirement_workflow_v12.github_gateway import GitHubGatewayError
from requirement_workflow_v12.project_repo.tools import GitHubProjectRepoTools


def _mock_gateway():
    gw = MagicMock()
    gw.fetch_file_sha = MagicMock(side_effect=lambda repo, ref, path: {
        "ARCHITECTURE.yaml": ("arch-sha", "kind: Architecture\n"),
        "acm-registry.yaml": ("reg-sha", "version: 3\n"),
    }[path])
    return gw


def test_fetch_project_context_combines_two_files():
    tools = GitHubProjectRepoTools(_mock_gateway())

    ctx = tools.fetch_project_context("acme/repo")

    assert ctx.project_repo == "acme/repo"
    assert ctx.arch_sha == "arch-sha"
    assert ctx.arch_text == "kind: Architecture\n"
    assert ctx.registry_sha == "reg-sha"
    assert ctx.registry_text == "version: 3\n"


def test_fetch_project_context_wraps_gateway_error():
    gw = MagicMock()
    gw.fetch_file_sha = MagicMock(
        side_effect=GitHubGatewayError(404, "not found"),
    )
    tools = GitHubProjectRepoTools(gw)

    with pytest.raises(ProjectRepoError) as exc_info:
        tools.fetch_project_context("acme/repo")
    assert "fetch_project_context" in str(exc_info.value)
    assert exc_info.value.__cause__ is not None  # from exc preserved
    assert exc_info.value.recoverable is False
```

- [ ] **Step 2: 运行验证失败**

Run: `pytest tests/test_project_repo_tools.py::test_fetch_project_context_combines_two_files -v`
Expected: FAIL — `GitHubProjectRepoTools` 未定义

- [ ] **Step 3: 实现 `GitHubProjectRepoTools.__init__` + `fetch_project_context`**

在 `src/requirement_workflow_v12/project_repo/tools.py` 末尾追加：

```python
from ..github_gateway import GitHubGateway, GitHubGatewayError


class GitHubProjectRepoTools:
    """默认实现，内部委托给 GitHubGateway。"""

    def __init__(self, gateway: "GitHubGateway"):
        self._gw = gateway

    def fetch_project_context(self, project_repo: str) -> ProjectContext:
        try:
            arch_sha, arch_text = self._gw.fetch_file_sha(
                project_repo, "main", "ARCHITECTURE.yaml",
            )
            registry_sha, registry_text = self._gw.fetch_file_sha(
                project_repo, "main", "acm-registry.yaml",
            )
        except GitHubGatewayError as exc:
            raise ProjectRepoError(
                f"fetch_project_context failed for {project_repo}: {exc}",
                recoverable=False,
            ) from exc
        return ProjectContext(
            project_repo=project_repo,
            arch_sha=arch_sha,
            arch_text=arch_text,
            registry_sha=registry_sha,
            registry_text=registry_text,
        )
```

- [ ] **Step 4: 运行验证通过**

Run: `pytest tests/test_project_repo_tools.py -v`
Expected: PASS (5/5)

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/project_repo/tools.py \
        tests/test_project_repo_tools.py
git commit -m "feat(project_repo): implement GitHubProjectRepoTools.fetch_project_context"
```

---

### Task 1.4: GitHubProjectRepoTools.cleanup_failed_branch

**Files:**
- Modify: `src/requirement_workflow_v12/project_repo/tools.py`
- Modify: `tests/test_project_repo_tools.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_project_repo_tools.py — 追加
import logging


def test_cleanup_failed_branch_delegates_to_gateway():
    gw = MagicMock()
    gw.delete_branch = MagicMock(return_value=None)
    tools = GitHubProjectRepoTools(gw)

    tools.cleanup_failed_branch("acme/repo", "spec/REQ-P-1")

    gw.delete_branch.assert_called_once_with("acme/repo", "spec/REQ-P-1")


def test_cleanup_failed_branch_swallows_gateway_error(caplog):
    gw = MagicMock()
    gw.delete_branch = MagicMock(
        side_effect=GitHubGatewayError(500, "server err"),
    )
    tools = GitHubProjectRepoTools(gw)

    with caplog.at_level(logging.WARNING):
        tools.cleanup_failed_branch("acme/repo", "spec/REQ-P-1")

    assert "cleanup_failed_branch" in caplog.text
    assert "spec/REQ-P-1" in caplog.text
```

- [ ] **Step 2: 运行验证失败**

Run: `pytest tests/test_project_repo_tools.py::test_cleanup_failed_branch_delegates_to_gateway -v`
Expected: FAIL — `cleanup_failed_branch` 未实现

- [ ] **Step 3: 实现 `cleanup_failed_branch`**

在 `GitHubProjectRepoTools` class 内追加（在 `fetch_project_context` 后）：

```python
    def cleanup_failed_branch(self, project_repo: str, branch: str) -> None:
        try:
            self._gw.delete_branch(project_repo, branch)
        except GitHubGatewayError as exc:
            _logger.warning(
                "cleanup_failed_branch could not delete %s/%s: %s",
                project_repo, branch, exc,
            )
```

文件头部添加（若尚无）：

```python
import logging

_logger = logging.getLogger(__name__)
```

- [ ] **Step 4: 运行验证通过**

Run: `pytest tests/test_project_repo_tools.py -v`
Expected: PASS (7/7)

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/project_repo/tools.py \
        tests/test_project_repo_tools.py
git commit -m "feat(project_repo): implement cleanup_failed_branch with log-and-swallow"
```

---

### Task 1.5: GitHubProjectRepoTools.commit_spec_artifacts 正常路径

**Files:**
- Modify: `src/requirement_workflow_v12/project_repo/tools.py`
- Modify: `tests/test_project_repo_tools.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_project_repo_tools.py — 追加
from requirement_workflow_v12.project_repo.types import SpecArtifacts


def _happy_artifacts():
    return SpecArtifacts(
        project_repo="acme/repo",
        branch="spec/REQ-P-1",
        base_branch="main",
        files={"docs/specs/REQ-P-1/design.md": "# Design\n"},
        commit_message="feat(spec): REQ-P-1",
        pr_title="Spec: REQ-P-1",
        pr_body="body",
    )


def test_commit_spec_artifacts_happy_path_returns_pr_ref():
    gw = MagicMock()
    gw.create_branch = MagicMock(return_value="head-sha-of-main")
    gw.commit_spec_pr_files = MagicMock(return_value="commit-sha")
    gw.open_pull_request = MagicMock(
        return_value={"number": 42, "html_url": "https://gh/pr/42"},
    )
    tools = GitHubProjectRepoTools(gw)

    pr = tools.commit_spec_artifacts("REQ-P-1", _happy_artifacts())

    assert pr.number == 42
    assert pr.html_url == "https://gh/pr/42"
    assert pr.head_sha == "commit-sha"
    assert pr.branch == "spec/REQ-P-1"
    gw.create_branch.assert_called_once_with(
        owner="acme", repo="repo",
        branch="spec/REQ-P-1", from_branch="main",
    )
    gw.commit_spec_pr_files.assert_called_once_with(
        "acme/repo", "spec/REQ-P-1",
        {"docs/specs/REQ-P-1/design.md": "# Design\n"},
        "feat(spec): REQ-P-1",
    )
    gw.open_pull_request.assert_called_once_with(
        owner="acme", repo="repo",
        head_branch="spec/REQ-P-1", base_branch="main",
        title="Spec: REQ-P-1", body="body",
    )
```

- [ ] **Step 2: 运行验证失败**

Run: `pytest tests/test_project_repo_tools.py::test_commit_spec_artifacts_happy_path_returns_pr_ref -v`
Expected: FAIL — `commit_spec_artifacts` 未实现

- [ ] **Step 3: 实现 happy path**

在 `GitHubProjectRepoTools` class 内追加：

```python
    def commit_spec_artifacts(
        self, req_id: str, artifacts: SpecArtifacts,
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
            number=int(pr["number"]),
            html_url=str(pr["html_url"]),
            head_sha=head_sha,
            branch=artifacts.branch,
        )
```

- [ ] **Step 4: 运行验证通过**

Run: `pytest tests/test_project_repo_tools.py -v`
Expected: PASS (8/8)

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/project_repo/tools.py \
        tests/test_project_repo_tools.py
git commit -m "feat(project_repo): commit_spec_artifacts happy path returns PrRef"
```

---

### Task 1.6: commit_spec_artifacts 失败回滚 + 错误包装

**Files:**
- Modify: `tests/test_project_repo_tools.py`

- [ ] **Step 1: 写失败测试（验证失败时清理分支并包装为 ProjectRepoError）**

```python
# tests/test_project_repo_tools.py — 追加
def test_commit_spec_artifacts_on_pr_failure_cleans_branch_and_raises():
    gw = MagicMock()
    gw.create_branch = MagicMock(return_value="head-sha")
    gw.commit_spec_pr_files = MagicMock(return_value="commit-sha")
    gw.open_pull_request = MagicMock(
        side_effect=GitHubGatewayError(422, "validation failed"),
    )
    gw.delete_branch = MagicMock(return_value=None)
    tools = GitHubProjectRepoTools(gw)

    with pytest.raises(ProjectRepoError) as exc_info:
        tools.commit_spec_artifacts("REQ-P-1", _happy_artifacts())

    assert "REQ-P-1" in str(exc_info.value)
    assert exc_info.value.__cause__ is not None
    assert exc_info.value.recoverable is False
    # Branch cleanup attempted exactly once with the same branch name.
    gw.delete_branch.assert_called_once_with("acme/repo", "spec/REQ-P-1")


def test_commit_spec_artifacts_on_commit_failure_cleans_branch():
    gw = MagicMock()
    gw.create_branch = MagicMock(return_value="head-sha")
    gw.commit_spec_pr_files = MagicMock(
        side_effect=GitHubGatewayError(409, "conflict"),
    )
    gw.delete_branch = MagicMock(return_value=None)
    tools = GitHubProjectRepoTools(gw)

    with pytest.raises(ProjectRepoError):
        tools.commit_spec_artifacts("REQ-P-1", _happy_artifacts())

    gw.delete_branch.assert_called_once()
```

- [ ] **Step 2: 运行验证**

Run: `pytest tests/test_project_repo_tools.py -v`
Expected: PASS (10/10) —— Task 1.5 的实现本就覆盖失败清理分支路径；若未通过则修 Task 1.5 代码

- [ ] **Step 3: Commit**

```bash
git add tests/test_project_repo_tools.py
git commit -m "test(project_repo): verify commit_spec_artifacts rollback paths"
```

---

### Task 1.7: Step 1 回归验证

**Files:** （无修改）

- [ ] **Step 1: 全量 pytest**

Run: `pytest -q`
Expected: 全绿。`project_repo/` 模块已就绪但尚无业务代码消费；`test_spec_transform_e2e.py` 仍走老路径（mock gateway）。

- [ ] **Step 2: （若有 CI lint 配置）跑 linter**

Run: `ruff check src/requirement_workflow_v12/project_repo/ tests/test_project_repo_tools.py`（项目若无 ruff 配置可跳过）
Expected: no errors

**Step 1 DoD**：`pytest -q` 全绿；`git log` 显示 6 个 commit；`git diff main -- src/requirement_workflow_v12/` 只新增 `project_repo/` 目录、不动其他。

---

## Step 2 — 迁移 SpecTransformOrchestrator

目标：orchestrator 构造函数从 `gateway=` 改为 `tools=`；所有 `self._gateway.*` 调用换为 `self._tools.*` 领域动词。`test_spec_transform_e2e.py` 的 mock 从 gateway 切到 tools。Coordinator / AcmRegistry / service_app 仍持 gateway（Step 3 再动）——所以本 Step 里 Coordinator 要"临时"构造 tools 传给 orchestrator。

### Task 2.1: 改 orchestrator 构造函数 + `on_enter_transforming` 走 fetch_project_context

**Files:**
- Modify: `src/requirement_workflow_v12/spec_transform.py:94-175`
- Modify: `src/requirement_workflow_v12/coordinator_service.py:680-690`
- Modify: `tests/test_spec_transform_e2e.py:31-77`

- [ ] **Step 1: 改造 e2e 测试 `_gateway_mock()` 为 `_tools_mock()`**

编辑 `tests/test_spec_transform_e2e.py`，**替换** `_gateway_mock` 函数：

```python
from requirement_workflow_v12.project_repo import (
    PrRef, ProjectContext,
)


def _tools_mock():
    """ProjectRepoTools mock wired for the full game."""
    tools = MagicMock()
    tools.fetch_project_context = MagicMock(return_value=ProjectContext(
        project_repo="acme/scaffold-repo",
        arch_sha="arch-sha", arch_text="kind: Architecture\n",
        registry_sha="registry-sha", registry_text=_REGISTRY_YAML,
    ))
    tools.commit_spec_artifacts = MagicMock(return_value=PrRef(
        number=42, html_url="https://gh/pr/42",
        head_sha="commit-sha", branch="spec/REQ-P-1",
    ))
    tools.cleanup_failed_branch = MagicMock(return_value=None)
    return tools
```

并在 `_build_wired_service` 里把 `gateway = _gateway_mock()` 换成 `tools = _tools_mock()`，并调整 `configure_spec_orchestrator(github_gateway=gateway, ...)` 调用（此时 Coordinator 仍然接收 `github_gateway` —— 临时适配：在 test 里临时仍传 gateway mock，由 coordinator 内部构造真 tools 被 mock.patch 掉。更简单方案见下一步。）

- [ ] **Step 2: 运行验证失败**

Run: `pytest tests/test_spec_transform_e2e.py -v`
Expected: FAIL — 至少 `gateway.create_branch.assert_called_once()` 等断言目前失败（test 已改用 tools mock 但 orchestrator 还依赖 gateway）。

- [ ] **Step 3: 改 `SpecTransformOrchestrator.__init__`**

编辑 `src/requirement_workflow_v12/spec_transform.py`，**替换** `__init__` 签名：

```python
    def __init__(
        self,
        *,
        tools: "ProjectRepoTools",
        registry,
        feishu,
        trace_dir: Path,
        max_rounds: int = 3,
        max_soft_retries: int = 2,
        max_race_retries: int = 3,
        max_regression_retries: int = 1,
        on_deadlock=None,
        on_locked=None,
    ):
        self._tools = tools
        self._registry = registry
        # ...（其余字段保留原样）
```

文件头部 import：

```python
from .project_repo import PrRef, ProjectContext, ProjectRepoError, ProjectRepoTools, SpecArtifacts
```

- [ ] **Step 4: 改 `on_enter_transforming` 走 facade**

将 `spec_transform.py` 中 `on_enter_transforming` 方法的 `fetch_file_sha` + `create_branch` 部分替换为：

```python
    def on_enter_transforming(
        self,
        *,
        req_id: str,
        project_repo: str,
        spec_doc_id: str,
    ) -> TransformContextSnapshot:
        spec_rev = self._feishu.fetch_document_revision(spec_doc_id)
        ctx = self._tools.fetch_project_context(project_repo)
        active = self._registry.parse_active_slice(ctx.registry_text)
        snap = TransformContextSnapshot(
            req_id=req_id,
            spec_source_revision=spec_rev,
            architecture_revision=ctx.arch_sha,
            acm_registry_revision=ctx.registry_sha,
            acm_active_slice=active,
            captured_at=_dt.datetime.now(_dt.timezone.utc).isoformat(),
        )
        self._trace.reset(req_id)
        self._trace.append(req_id, {
            "event": "transform_started",
            "snapshot": {
                "spec_source_revision": snap.spec_source_revision,
                "architecture_revision": snap.architecture_revision,
                "acm_registry_revision": snap.acm_registry_revision,
                "acm_active_slice": snap.acm_active_slice,
            },
        })
        # Note: create_branch 改由 commit_spec_artifacts 统一负责；
        # 但 on_enter_transforming 需要及早建分支以便 transformer 看到空分支——
        # 因此保留这里显式开分支，通过新的 facade 方法；Step 2 临时走 tools._gw。
        # → 见 Task 2.2：把这部分挪进 commit_spec_artifacts 不再在 on_enter 建分支
        self._rounds[req_id] = RoundContext(snapshot=snap)
        return snap
```

**重要决策**：`on_enter_transforming` 里**不再**建分支（原先用来占位 `spec/REQ-X`）。分支统一由 `commit_spec_artifacts` 内部建。删除 `on_enter_transforming` 里 `self._gateway.create_branch(...)` 三行以及 `owner, repo_name = project_repo.split(...)`。

> **Why**：`commit_spec_artifacts` 已原子化建分支+commit+PR，双开分支会造成 422 冲突；e2e 测试的 `gateway.create_branch.assert_called_once()` 会迁移为 `tools.commit_spec_artifacts.assert_called_once()`。

- [ ] **Step 5: 同步修改 Coordinator 的 `configure_spec_orchestrator`**

编辑 `src/requirement_workflow_v12/coordinator_service.py:666-690`，**临时适配**：函数签名仍保留 `github_gateway`（Step 3 再改），但内部构造 tools：

```python
    def configure_spec_orchestrator(
        self,
        *,
        github_gateway,
        trace_dir,
        feishu=None,
    ) -> None:
        from .acm_registry import AcmRegistry
        from .project_repo import GitHubProjectRepoTools
        from .spec_transform import SpecTransformOrchestrator
        self._acm_registry = AcmRegistry(gateway=github_gateway)
        tools = GitHubProjectRepoTools(github_gateway)
        self.spec_orchestrator = SpecTransformOrchestrator(
            tools=tools,
            registry=self._acm_registry,
            feishu=feishu,
            trace_dir=trace_dir,
            on_deadlock=self._on_spec_deadlock,
            on_locked=self._on_spec_locked,
        )
        self.spec_orchestrator._project_repo_for = self._project_repo_for
```

在 `coordinator_service.py` 顶部补 `GitHubProjectRepoTools` 导入位置（写在 `configure_spec_orchestrator` 内的局部 import 已够用，不必顶层导入）。

- [ ] **Step 6: 修 e2e 测试：调整 `_build_wired_service` 仍传 gateway mock 给 coordinator，但 coordinator 内部会包成 tools —— 这意味着 `_tools_mock()` 路径在 Step 2 里不直接插入，需换个做法**

**重新设计**：用 `monkeypatch` 把 `GitHubProjectRepoTools` 替换成我们的 tools mock：

```python
# tests/test_spec_transform_e2e.py —— 替换 _build_wired_service
def _build_wired_service(tmp_path, monkeypatch, *, req_id="REQ-P-1", project="P"):
    svc = CoordinatorService()
    req = Requirement(req_id=req_id, name="n", project=project, summary="s", creator="c")
    req.status = WorkflowStatus.APPROVED
    req.spec_status = SpecStatus.DRAFTING
    req.spec_document_id = "doc-1"
    req.spec_document_url = "https://feishu/doc/1"
    svc.requirements[req_id] = req

    cfg = ProjectConfig(
        category="application", template_version="v1",
        architecture_doc_id="arch-doc", architecture_doc_url="https://arch",
    )
    cfg.github_repo_url = "acme/scaffold-repo"
    svc.project_configs[project] = cfg

    tools = _tools_mock()
    # Coordinator 构造的 GitHubProjectRepoTools 被替换为我们准备好的 mock
    monkeypatch.setattr(
        "requirement_workflow_v12.coordinator_service.GitHubProjectRepoTools",
        lambda gw: tools,
        raising=False,
    )
    # AcmRegistry 还持 gateway——Step 3 才解耦；这里给它一个能 fetch_file_sha 的 MagicMock
    gateway = MagicMock()
    gateway.fetch_file_sha = MagicMock(
        return_value=("registry-sha", _REGISTRY_YAML),
    )
    feishu = MagicMock()
    feishu.fetch_document_revision = MagicMock(return_value="feishu-rev-77")
    svc.configure_spec_orchestrator(
        github_gateway=gateway, trace_dir=tmp_path, feishu=feishu,
    )
    return svc, req, tools, feishu
```

并在每个 test 函数签名加 `monkeypatch` 参数；把 `gateway.create_branch.assert_called_once()` 改为 `tools.fetch_project_context.assert_called_once_with("acme/scaffold-repo")`。

> **重要提示**：此时 `monkeypatch.setattr` 目标模块需要先 `import GitHubProjectRepoTools` 到 `coordinator_service` 顶层——修改 `coordinator_service.py` 顶部 imports（非局部 import），让 monkeypatch 能生效：
>
> ```python
> # coordinator_service.py 顶部
> from .project_repo import GitHubProjectRepoTools
> ```
>
> 并把 `configure_spec_orchestrator` 里局部 import 去掉。

- [ ] **Step 7: 运行 e2e 测试验证**

Run: `pytest tests/test_spec_transform_e2e.py::test_one_round_converged_locks_spec_with_audit_fields -v`
Expected: 仍然 FAIL —— 但错误点前进：现在会在 `_on_converged` 里调用 `commit_spec_pr_files` 等老 gateway 方法（Task 2.2 迁移）

- [ ] **Step 8: （保持测试红）Commit 中间态**

不要 commit 到中间态。继续 Task 2.2。

---

### Task 2.2: 迁移 `_on_converged` 到 `commit_spec_artifacts`

**Files:**
- Modify: `src/requirement_workflow_v12/spec_transform.py:261-377`
- Modify: `tests/test_spec_transform_e2e.py`

- [ ] **Step 1: 替换 `_on_converged` 中 commit + PR 部分**

编辑 `spec_transform.py` 的 `_on_converged`，**找到** `files = self._compose_pr_files(...)` 之后的 `commit_spec_pr_files` + `open_pull_request` 两段，**替换为**：

```python
                files = self._compose_pr_files(req_id, payload, patched)
                trace_digest = _compute_trace_digest(self._trace.read_all(req_id))
                source_revision = ctx.snapshot.spec_source_revision
                pr_body = (
                    f"Spec PR for {req_id}.\n\n"
                    f"spec_source_revision={source_revision} | "
                    f"transform_round={ctx.round_index} | "
                    f"transform_trace_digest={trace_digest}"
                )
                artifacts = SpecArtifacts(
                    project_repo=project_repo,
                    branch=f"spec/{req_id}",
                    base_branch="main",
                    files=files,
                    commit_message=f"feat(spec): {req_id}",
                    pr_title=f"Spec: {req_id}",
                    pr_body=pr_body,
                )
                try:
                    pr_ref = self._tools.commit_spec_artifacts(req_id, artifacts)
                    committed = True
                    break
                except ProjectRepoError as exc:
                    msg = str(exc).lower()
                    if "mismatch" in msg and race_attempt < self._max_race_retries - 1:
                        ctx.race_retry_count += 1
                        self._trace.append(req_id, {
                            "event": "acm_race_retry",
                            "attempt": race_attempt + 1,
                        })
                        continue
                    self._trace.append(req_id, {
                        "event": "github_commit_failed",
                        "error": str(exc),
                    })
                    self._rounds.pop(req_id, None)
                    if self._on_deadlock_cb is not None:
                        self._on_deadlock_cb(req_id, "github_commit_failed")
                    return "deadlock"
```

**删除** `_on_converged` 末尾（race 循环之外）的整段 `owner, repo_name = ...` + `pr = self._gateway.open_pull_request(...)` 六行：由 `pr_ref` 取代。把 `self._trace.append(req_id, {"event": "locked", "pr_url": pr.get("html_url")})` 改为 `self._trace.append(req_id, {"event": "locked", "pr_url": pr_ref.html_url})`，`on_locked` 回调里用 `pr_ref.html_url`。

> **Why 保留 race retry**：`commit_spec_artifacts` 内部吞了 `GitHubGatewayError` 并转成 `ProjectRepoError`，错误信息里保留了原 `mismatch` 关键字（因 f-string 包含 `{exc}`）。test 用 `ProjectRepoError` + 错误字符串判断 race。

- [ ] **Step 2: 运行 e2e**

Run: `pytest tests/test_spec_transform_e2e.py -v`
Expected: `test_one_round_converged_locks_spec_with_audit_fields` PASS；其余 2 个 PASS。若未通过，读 trace 里的 `commit_spec_artifacts.assert_called_once()` 断言：要把 e2e 测试原先 `gateway.commit_spec_pr_files.assert_called_once()` 改为 `tools.commit_spec_artifacts.assert_called_once()`，`gateway.open_pull_request.assert_called_once()` 整行删除。

- [ ] **Step 3: 跑完整 pytest**

Run: `pytest -q`
Expected: 全绿

- [ ] **Step 4: Commit（Task 2.1 + 2.2 合并一次 commit，因中间态不绿）**

```bash
git add src/requirement_workflow_v12/spec_transform.py \
        src/requirement_workflow_v12/coordinator_service.py \
        tests/test_spec_transform_e2e.py
git commit -m "refactor(spec_transform): migrate orchestrator to ProjectRepoTools facade"
```

**Step 2 DoD**：`pytest -q` 全绿；`grep -n "_gateway" src/requirement_workflow_v12/spec_transform.py` 零命中；e2e 测试 mock 全部走 `ProjectRepoTools` 接口。

---

## Step 3 — 迁移 CoordinatorService + AcmRegistry + service_app

目标：把"临时适配"干掉。`AcmRegistry` 不再持 gateway；`configure_spec_orchestrator` 签名换为 `tools=`；`service_app.py` 在装配处构造 `GitHubProjectRepoTools`。

### Task 3.1: AcmRegistry 降级为纯解析器

**Files:**
- Modify: `src/requirement_workflow_v12/acm_registry.py:37-113`
- Modify: `src/requirement_workflow_v12/spec_transform.py` (`_on_converged` 里 `fetch_snapshot` 调用)
- Modify: `tests/` 中涉及 `AcmRegistry(gateway=...)` 的用例

- [ ] **Step 1: Grep 找出所有 `AcmRegistry` 实例化点**

Run: `grep -rn "AcmRegistry(" src/ tests/`
Expected: 列出所有调用点（预期：`coordinator_service.py`、`spec_transform.py` 里 `fetch_snapshot` 的调用、`tests/test_acm_registry*.py`）

- [ ] **Step 2: 改 `AcmRegistry.__init__` 去掉 gateway 参数**

```python
# acm_registry.py
class AcmRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()

    # 删除 fetch_snapshot 方法（由上层 fetch_project_context 提供）
    # 或保留但改签名：
    def parse_snapshot(self, registry_text: str) -> tuple[str, RegistryDoc]:
        """Parse registry text to (no-op sha placeholder, RegistryDoc).
        sha 由调用方持有——此方法只负责解析。
        """
        raise NotImplementedError(
            "Use parse() + pass registry_sha from ProjectContext explicitly.",
        )
```

**决策**：彻底删 `fetch_snapshot`；在 `spec_transform.py:_on_converged` 里改为每次 race 循环重新调用 `self._tools.fetch_project_context(project_repo)` 拿最新 `registry_sha/text`。

- [ ] **Step 3: 改 `_on_converged` 的 race 循环**

编辑 `spec_transform.py:_on_converged`：把原 `current_sha, current_doc = self._registry.fetch_snapshot(project_repo)` 替换为：

```python
                fresh_ctx = self._tools.fetch_project_context(project_repo)
                current_sha = fresh_ctx.registry_sha
                current_doc = self._registry.parse(fresh_ctx.registry_text)
```

> **Why**：race retry 必须每轮重新拉 registry；原 `fetch_snapshot` 内部就在做这事。现在把这步挪到 orchestrator，`AcmRegistry` 保持纯函数。

- [ ] **Step 4: 改 `CoordinatorService.configure_spec_orchestrator`**

```python
    def configure_spec_orchestrator(
        self,
        *,
        tools: "ProjectRepoTools",
        trace_dir,
        feishu=None,
    ) -> None:
        from .acm_registry import AcmRegistry
        from .spec_transform import SpecTransformOrchestrator
        self._acm_registry = AcmRegistry()
        self.spec_orchestrator = SpecTransformOrchestrator(
            tools=tools,
            registry=self._acm_registry,
            feishu=feishu,
            trace_dir=trace_dir,
            on_deadlock=self._on_spec_deadlock,
            on_locked=self._on_spec_locked,
        )
        self.spec_orchestrator._project_repo_for = self._project_repo_for
```

把顶部 `from .project_repo import GitHubProjectRepoTools` 移到本方法里或改为 `ProjectRepoTools` Protocol 的类型注解（Protocol 不必运行时导入，用 `if TYPE_CHECKING`）。

- [ ] **Step 5: 改 `service_app.py` 装配层**

编辑 `src/requirement_workflow_v12/service_app.py:121-131`：

```python
        if settings.github_token:
            from pathlib import Path
            from .github_gateway import GitHubGateway
            from .project_repo import GitHubProjectRepoTools
            github_gateway = GitHubGateway(settings)
            tools = GitHubProjectRepoTools(github_gateway)
            trace_dir = Path(settings.spec_trace_dir)
            trace_dir.mkdir(parents=True, exist_ok=True)
            self.service.configure_spec_orchestrator(
                tools=tools,
                trace_dir=trace_dir,
                feishu=self.gateway,
            )
```

- [ ] **Step 6: 更新 e2e 测试**

`tests/test_spec_transform_e2e.py` 里 `_build_wired_service` 现在可以直接传 tools mock，去掉 monkeypatch：

```python
def _build_wired_service(tmp_path, *, req_id="REQ-P-1", project="P"):
    svc = CoordinatorService()
    # ...（req / cfg 部分不变）
    tools = _tools_mock()
    feishu = MagicMock()
    feishu.fetch_document_revision = MagicMock(return_value="feishu-rev-77")
    svc.configure_spec_orchestrator(
        tools=tools, trace_dir=tmp_path, feishu=feishu,
    )
    return svc, req, tools, feishu
```

恢复所有测试函数签名为不带 `monkeypatch`。

- [ ] **Step 7: 更新其他测试**

Run: `grep -rn "AcmRegistry(" tests/`
对每个调用点：`AcmRegistry(gateway=xxx)` → `AcmRegistry()`；涉及 `fetch_snapshot` 的直接单测改为注入 `registry_text` 手写。

- [ ] **Step 8: 运行全量 pytest**

Run: `pytest -q`
Expected: 全绿

- [ ] **Step 9: Staging smoke test（手动）**

```bash
docker compose -f staging/docker-compose.yml up -d --build
curl -fsS http://localhost:<port>/healthz
```
Expected: `200 OK`。（这一步非自动化，实施者自行确认。）

- [ ] **Step 10: Commit**

```bash
git add src/requirement_workflow_v12/acm_registry.py \
        src/requirement_workflow_v12/spec_transform.py \
        src/requirement_workflow_v12/coordinator_service.py \
        src/requirement_workflow_v12/service_app.py \
        tests/
git commit -m "refactor: drop gateway from AcmRegistry; wire ProjectRepoTools at app boundary"
```

**Step 3 DoD**：`grep -n "gateway" src/requirement_workflow_v12/{coordinator_service,spec_transform,acm_registry}.py` 只剩注释或无命中；`service_app.py` 是唯一构造 `GitHubProjectRepoTools` 的地方；staging 健康检查绿。

---

## Step 4 — 钩子显式化

目标：`StateTransitionHooks` 落地；`submit_checkpoint_1a_pass` 走 `fire_exit`/`fire_enter`；`on_enter_transforming` 从直调变成钩子回调注册。

### Task 4.1: StateTransitionHooks 骨架 + 注册 / 触发单测

**Files:**
- Create: `src/requirement_workflow_v12/project_repo/hooks.py`
- Modify: `src/requirement_workflow_v12/project_repo/__init__.py`
- Create: `tests/test_project_repo_hooks.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_project_repo_hooks.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from unittest.mock import MagicMock

import pytest

from requirement_workflow_v12.models import Requirement
from requirement_workflow_v12.project_repo import StateTransitionHooks
from requirement_workflow_v12.project_repo.tools import ProjectRepoError
from requirement_workflow_v12.spec_state_machine import SpecStatus


def _req(req_id="REQ-P-1"):
    return Requirement(
        req_id=req_id, name="n", project="P", summary="s", creator="c",
    )


def test_fire_enter_runs_hooks_in_registration_order():
    hooks = StateTransitionHooks()
    calls: list[str] = []
    hooks.on_enter(SpecStatus.TRANSFORMING, lambda r: calls.append("a"))
    hooks.on_enter(SpecStatus.TRANSFORMING, lambda r: calls.append("b"))

    hooks.fire_enter(SpecStatus.TRANSFORMING, _req())

    assert calls == ["a", "b"]


def test_fire_exit_runs_only_exit_hooks():
    hooks = StateTransitionHooks()
    enter_calls, exit_calls = [], []
    hooks.on_enter(SpecStatus.DRAFTING, lambda r: enter_calls.append("e"))
    hooks.on_exit(SpecStatus.DRAFTING, lambda r: exit_calls.append("x"))

    hooks.fire_exit(SpecStatus.DRAFTING, _req())

    assert enter_calls == []
    assert exit_calls == ["x"]


def test_fire_unknown_status_is_noop():
    hooks = StateTransitionHooks()
    hooks.fire_enter(SpecStatus.LOCKED, _req())  # no registered hook
```

- [ ] **Step 2: 运行验证失败**

Run: `pytest tests/test_project_repo_hooks.py -v`
Expected: FAIL — `StateTransitionHooks` 未定义

- [ ] **Step 3: 实现 `hooks.py`**

```python
# src/requirement_workflow_v12/project_repo/hooks.py
from __future__ import annotations

import logging
from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from ..models import Requirement
    from ..spec_state_machine import SpecStatus

_logger = logging.getLogger(__name__)

HookFn = Callable[["Requirement"], None]


class StateTransitionHooks:
    """Spec 状态转移副作用注册器。

    on_enter(status, fn): 进入 status 时触发（apply_spec_event 之后）
    on_exit(status, fn):  离开 status 时触发（apply_spec_event 之前）

    契约：回调抛异常 → fail-fast，先 log 再 re-raise；后续钩子不执行。
    """

    def __init__(self) -> None:
        self._on_enter: dict["SpecStatus", list[HookFn]] = {}
        self._on_exit: dict["SpecStatus", list[HookFn]] = {}

    def on_enter(self, status: "SpecStatus", fn: HookFn) -> None:
        self._on_enter.setdefault(status, []).append(fn)

    def on_exit(self, status: "SpecStatus", fn: HookFn) -> None:
        self._on_exit.setdefault(status, []).append(fn)

    def fire_enter(self, status: "SpecStatus", req: "Requirement") -> None:
        self._fire("enter", self._on_enter.get(status, ()), status, req)

    def fire_exit(self, status: "SpecStatus", req: "Requirement") -> None:
        self._fire("exit", self._on_exit.get(status, ()), status, req)

    def _fire(
        self,
        transition: str,
        fns: "tuple[HookFn, ...] | list[HookFn]",
        status: "SpecStatus",
        req: "Requirement",
    ) -> None:
        for fn in fns:
            try:
                fn(req)
            except Exception as exc:
                _logger.exception(
                    "hook_exception event=%s transition=%s status=%s "
                    "req_id=%s hook_name=%s exception=%s",
                    "hook_exception", transition, status.name if hasattr(status, "name") else status,
                    req.req_id, getattr(fn, "__qualname__", repr(fn)),
                    f"{type(exc).__name__}: {exc}",
                )
                raise
```

- [ ] **Step 4: 更新 `__init__.py`**

```python
# src/requirement_workflow_v12/project_repo/__init__.py
from __future__ import annotations

from .hooks import StateTransitionHooks
from .tools import GitHubProjectRepoTools, ProjectRepoError, ProjectRepoTools
from .types import (
    CommitRef,
    PrRef,
    ProjectContext,
    RepoRef,
    SpecArtifacts,
)

__all__ = [
    "CommitRef",
    "GitHubProjectRepoTools",
    "PrRef",
    "ProjectContext",
    "ProjectRepoError",
    "ProjectRepoTools",
    "RepoRef",
    "SpecArtifacts",
    "StateTransitionHooks",
]
```

- [ ] **Step 5: 运行验证通过**

Run: `pytest tests/test_project_repo_hooks.py -v`
Expected: PASS (3/3)

- [ ] **Step 6: Commit**

```bash
git add src/requirement_workflow_v12/project_repo/hooks.py \
        src/requirement_workflow_v12/project_repo/__init__.py \
        tests/test_project_repo_hooks.py
git commit -m "feat(project_repo): add StateTransitionHooks registry"
```

---

### Task 4.2: 钩子异常可观测性契约

**Files:**
- Modify: `tests/test_project_repo_hooks.py`

- [ ] **Step 1: 写失败测试 — 异常时日志字段齐全 + fail-fast**

```python
# tests/test_project_repo_hooks.py — 追加
import logging


def test_hook_exception_is_logged_with_required_fields(caplog):
    hooks = StateTransitionHooks()

    def boom(_req):
        raise ProjectRepoError("disk full", recoverable=False)

    hooks.on_enter(SpecStatus.TRANSFORMING, boom)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(ProjectRepoError) as exc_info:
            hooks.fire_enter(SpecStatus.TRANSFORMING, _req("REQ-X-9"))

    # cause chain preserved by caller (re-raise bare)
    assert "disk full" in str(exc_info.value)

    # Required structured fields: event/transition/status/req_id/hook_name/exception
    text = caplog.text
    assert "hook_exception" in text
    assert "transition=enter" in text
    assert "TRANSFORMING" in text
    assert "REQ-X-9" in text
    assert "boom" in text  # hook_name
    assert "ProjectRepoError" in text
    assert "disk full" in text


def test_hook_exception_is_fail_fast(caplog):
    hooks = StateTransitionHooks()
    calls: list[str] = []

    def first(_r): raise ProjectRepoError("halt")
    def second(_r): calls.append("should-not-run")

    hooks.on_enter(SpecStatus.TRANSFORMING, first)
    hooks.on_enter(SpecStatus.TRANSFORMING, second)

    with pytest.raises(ProjectRepoError):
        hooks.fire_enter(SpecStatus.TRANSFORMING, _req())

    assert calls == []  # second hook不执行
```

- [ ] **Step 2: 运行**

Run: `pytest tests/test_project_repo_hooks.py -v`
Expected: PASS（Task 4.1 的实现已覆盖）；若断言失败，调整 `_fire` 的 logger 消息字段

- [ ] **Step 3: Commit**

```bash
git add tests/test_project_repo_hooks.py
git commit -m "test(project_repo): verify hook-exception observability contract"
```

---

### Task 4.3: CoordinatorService 持有 hooks + 改 submit_checkpoint_1a_pass

**Files:**
- Modify: `src/requirement_workflow_v12/coordinator_service.py:__init__、configure_spec_orchestrator、submit_checkpoint_1a_pass、_project_repo_for`
- Modify: `tests/test_spec_transform_e2e.py`（验证 hooks 正确触发）

- [ ] **Step 1: 写失败测试：`on_enter TRANSFORMING` 被触发一次**

```python
# tests/test_spec_transform_e2e.py — 追加
def test_submit_checkpoint_1a_pass_fires_on_enter_transforming_hook(tmp_path):
    svc, req, tools, _feishu = _build_wired_service(tmp_path)

    svc.submit_checkpoint_1a_pass("REQ-P-1")

    # hook 触发 on_enter_transforming（进而调 fetch_project_context）
    tools.fetch_project_context.assert_called_once_with("acme/scaffold-repo")
    assert req.spec_status is SpecStatus.TRANSFORMING
```

- [ ] **Step 2: 运行**

Run: `pytest tests/test_spec_transform_e2e.py::test_submit_checkpoint_1a_pass_fires_on_enter_transforming_hook -v`
Expected: PASS（现有实现已满足）——这个测试作为锚点防止 Task 4.3 重构回归

- [ ] **Step 3: 改 `CoordinatorService.__init__`**

在 `coordinator_service.py` 的 `CoordinatorService.__init__` 里追加：

```python
        from .project_repo import StateTransitionHooks
        self._hooks = StateTransitionHooks()
```

- [ ] **Step 4: 改 `configure_spec_orchestrator` 注册钩子**

```python
    def configure_spec_orchestrator(
        self,
        *,
        tools: "ProjectRepoTools",
        trace_dir,
        feishu=None,
    ) -> None:
        from .acm_registry import AcmRegistry
        from .spec_state_machine import SpecStatus
        from .spec_transform import SpecTransformOrchestrator
        self._acm_registry = AcmRegistry()
        self.spec_orchestrator = SpecTransformOrchestrator(
            tools=tools,
            registry=self._acm_registry,
            feishu=feishu,
            trace_dir=trace_dir,
            on_deadlock=self._on_spec_deadlock,
            on_locked=self._on_spec_locked,
        )
        self.spec_orchestrator._project_repo_for = self._project_repo_for
        self._hooks.on_enter(
            SpecStatus.TRANSFORMING, self._on_enter_transforming_hook,
        )

    def _on_enter_transforming_hook(self, r: "Requirement") -> None:
        self.spec_orchestrator.on_enter_transforming(
            req_id=r.req_id,
            project_repo=self._project_repo_for(r.req_id),
            spec_doc_id=r.spec_document_id,
        )
```

- [ ] **Step 5: 改 `submit_checkpoint_1a_pass` 走 hooks**

```python
    def submit_checkpoint_1a_pass(self, req_id: str) -> Requirement:
        r = self.requirements[req_id]
        cfg = self.project_configs.get(r.project)
        if cfg is None or not cfg.github_repo_url:
            raise ValueError(f"项目 {r.project} 未配置 github_repo_url")
        decision = apply_spec_event(r.spec_status, SpecEvent.CHECKPOINT_1A_PASS)
        if not decision.allowed:
            raise ValueError(decision.message)

        prev_status = r.spec_status
        self._hooks.fire_exit(prev_status, r)
        r.spec_status = decision.next_status
        self._hooks.fire_enter(r.spec_status, r)
        return r
```

- [ ] **Step 6: 运行 pytest**

Run: `pytest -q`
Expected: 全绿。特别是 `test_one_round_converged_locks_spec_with_audit_fields` / `test_three_round_deadlock_sets_spec_deadlocked_flag` / `test_regression_retry_then_pass_locks_spec` / `test_submit_checkpoint_1a_pass_fires_on_enter_transforming_hook` 均 PASS。

- [ ] **Step 7: Commit**

```bash
git add src/requirement_workflow_v12/coordinator_service.py \
        tests/test_spec_transform_e2e.py
git commit -m "refactor(coordinator): route checkpoint_1a_pass side-effect through hooks"
```

**Step 4 DoD**：`pytest -q` 全绿；`coordinator_service.py:submit_checkpoint_1a_pass` 不再直接调 `self.spec_orchestrator.on_enter_transforming`；`self._hooks` 在 `__init__` 被实例化；`test_project_repo_hooks.py` 覆盖异常观测性契约。

---

## Step 5 — 文档同步（Spec § 十 分发计划）

**重要契约**：三个目标文件互不重复、每处都链回本 spec。**本 spec 文件不改**。

### Task 5.1: 新增 `docs/context/infra/state-machine-hook-pattern.md`

**Files:**
- Create: `docs/context/infra/state-machine-hook-pattern.md`

- [ ] **Step 1: 写新文件**

内容大纲（一次成稿）：

1. **原则**：纯状态机 + 显式钩子 = 可测 + 可扩展
2. **适用场景**：状态转移需副作用（I/O / 外部系统）且数量会增长
3. **反模式**：在 `apply_event` 附近 `if next_status == X: do_effect()`
4. **契约摘要**：
   - `fire_exit` 早于状态应用，`fire_enter` 晚于状态应用
   - 钩子失败 = 转移失败（fail-fast）
   - 异常必须 log + re-raise，不得吞
5. **与 Coordinator 的关系**：通过 `StateTransitionHooks` 注册；不假设 orchestrator 存在
6. **参考实现**：指向本 spec `docs/superpowers/specs/2026-04-19-project-repo-tools-design.md` § 4

**不含**：类名、模块路径、代码示例（那些属 layers 文档）

- [ ] **Step 2: Commit**

```bash
git add docs/context/infra/state-machine-hook-pattern.md
git commit -m "docs(infra): add state-machine-hook-pattern architectural principle"
```

---

### Task 5.2: 更新 `docs/context/harness-engineering-methodology-v2.0.md`

**Files:**
- Modify: `docs/context/harness-engineering-methodology-v2.0.md`

- [ ] **Step 1: 定位 §七 并发写回契约 末尾，新增一小节 "副作用职责边界"**

内容（~120 字一段）：

> Coordinator 侧所有对 GitHub 等外部系统的写入（commit、PR、分支）一律在状态机转移的 `on_enter`/`on_exit` 钩子里触发；状态机本身保持纯函数不做 I/O。新状态接入时通过 `StateTransitionHooks.on_enter` 注册回调，而非在 `submit_checkpoint_*` 里堆 if/else。参见 `docs/context/infra/state-machine-hook-pattern.md` 与 `docs/superpowers/specs/2026-04-19-project-repo-tools-design.md` § 4。

**不含**：类名、代码示例、迁移步骤

- [ ] **Step 2: Commit**

```bash
git add docs/context/harness-engineering-methodology-v2.0.md
git commit -m "docs(methodology): add side-effect boundary note pointing to hook pattern"
```

---

### Task 5.3: 更新 `docs/context/layers/spec-harness-layer.md`

**Files:**
- Modify: `docs/context/layers/spec-harness-layer.md`

- [ ] **Step 1: 在末尾新增 §十一 实现与部署**

内容：

```markdown
## §十一 实现与部署

### project_repo/ 模块职责

`src/requirement_workflow_v12/project_repo/` 是 Spec 层对外部 Git 托管平台的领域 facade。Coordinator / SpecTransformOrchestrator / AcmRegistry 不直接调用 `GitHubGateway`；所有外部写入走 facade 的领域动词。`AcmRegistry` 是纯解析器，不持有 gateway。

### 领域动词清单

| 动词 | 输入 | 输出 | 何时调用 |
|---|---|---|---|
| `fetch_project_context` | `project_repo` | `ProjectContext`（ARCHITECTURE + acm-registry 的 sha/text） | `on_enter_transforming` 快照；race retry 刷新 |
| `commit_spec_artifacts` | `req_id`, `SpecArtifacts` | `PrRef` | `_on_converged` commit Spec PR |
| `cleanup_failed_branch` | `project_repo`, `branch` | `None`（幂等） | `commit_spec_artifacts` 内部失败回滚 |

完整 API 签名、错误语义、设计 trade-off 见：`docs/superpowers/specs/2026-04-19-project-repo-tools-design.md` § 3。

### 状态转移副作用

`CoordinatorService` 在 `__init__` 持有一个 `StateTransitionHooks` 实例，`configure_spec_orchestrator` 阶段向其注册 `on_enter(SpecStatus.TRANSFORMING, ...)` 回调。状态转移方法（如 `submit_checkpoint_1a_pass`）只管 `fire_exit → apply_spec_event → fire_enter`。架构原则参见 `docs/context/infra/state-machine-hook-pattern.md`。
```

**不含**：决策 trade-off / 迁移步骤 / self-review 细节

- [ ] **Step 2: Commit**

```bash
git add docs/context/layers/spec-harness-layer.md
git commit -m "docs(layer): document project_repo/ verbs and hook wiring in spec-harness"
```

---

### Task 5.4: 文档分发验收

- [ ] **Step 1: 验证互不重复**

Run: `diff <(cat docs/context/infra/state-machine-hook-pattern.md) <(cat docs/context/harness-engineering-methodology-v2.0.md)` —— 不等
比对三份新/改文档的段落，确认同一句话不出现在两处以上。

- [ ] **Step 2: 验证单向链接**

Run: `grep -l "2026-04-19-project-repo-tools-design.md" docs/context/infra/state-machine-hook-pattern.md docs/context/harness-engineering-methodology-v2.0.md docs/context/layers/spec-harness-layer.md`
Expected: 三个文件都命中

- [ ] **Step 3: 验证本 spec 未改**

Run: `git log --oneline docs/superpowers/specs/2026-04-19-project-repo-tools-design.md`
Expected: 只显示 Step 0 之前已有的 commit (`8d530be`, `ba29a1b`)，无新 commit

---

## 最终验收

### 代码验收（对应 Spec § 9.1）

- [ ] `grep -rn "gateway\." src/requirement_workflow_v12/{coordinator_service,spec_transform,acm_registry}.py` 零命中（或只剩注释）
- [ ] `git diff main -- src/requirement_workflow_v12/github_gateway.py` 无改动
- [ ] `project_repo/` 目录包含 `__init__.py` / `types.py` / `tools.py` / `hooks.py`
- [ ] `CoordinatorService._hooks` 字段存在且在 `__init__` 实例化

### 测试验收（Spec § 9.2）

- [ ] `pytest -q` 全绿
- [ ] `tests/test_project_repo_tools.py` ≥ 6 个用例（fetch_project_context 2 个 + cleanup 2 个 + commit_spec_artifacts 3 个）
- [ ] `tests/test_project_repo_hooks.py` ≥ 4 个用例（含异常观测性契约）
- [ ] `tests/test_spec_transform_e2e.py` mock 用 `ProjectRepoTools`，不再 mock gateway

### 运行验收（Spec § 9.3）

- [ ] staging 部署成功，`/healthz` 200
- [ ] staging 环境跑一次 `REQ-test2-002` 级别的完整 spec-transform 链路，行为与重构前一致

### 文档验收（Spec § 9.4 + § 10.3）

- [ ] `docs/context/infra/state-machine-hook-pattern.md` 存在
- [ ] `docs/context/harness-engineering-methodology-v2.0.md` §七后新增小节
- [ ] `docs/context/layers/spec-harness-layer.md` 新增 §十一
- [ ] 本 spec 文件未改
- [ ] 三处更新互不重复，都链回本 spec

---

## Model Selection 建议（for subagent-driven-development）

| Task | 性质 | 推荐 model |
|---|---|---|
| 1.1 / 1.2 / 4.1 | 骨架 / dataclass / 简单类 | cheap |
| 1.3–1.6 | 翻译层 TDD（明确 spec，单文件） | cheap |
| 2.1 / 2.2 | 跨文件改造 + mock 调整 | standard |
| 3.1 | 多文件联动改造（AcmRegistry + orchestrator + app） | standard |
| 4.3 | 钩子接入 + e2e 回归 | standard |
| 5.1–5.3 | 文档撰写，需判断归属 | standard |

---

## 回滚策略

每个 Step 末尾一次 commit。回滚 Step N：`git revert <sha_range>` 即可。Step 1 独立存在（新模块无人用），即使后续 Step 回滚也不留废代码——可以单独保留或整体回滚。
