# Project Onboarding & Context Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在第一个需求创建时自动触发项目 Onboarding，初始化 ARCHITECTURE.yaml、ACM 注册表、飞书设计系统文档等项目级上下文，确保 Spec 转化服务有完整输入。

**Architecture:** 新增 `ProjectConfig` 数据模型存储在 `CoordinatorService.project_configs`；创建群消息处理分支检测新项目并触发 3 问 Onboarding 对话；`ProjectBootstrapper` 通过 GitHub API 写文件（路径C 自动，路径B 等待用户确认）；需求创建在 bootstrap 完成前阻塞进入 DISCUSSING。

**Tech Stack:** Python 3.11, lark-oapi（飞书 SDK）, PyGithub（GitHub API）, pytest

---

## 文件结构

| 操作 | 文件 | 职责 |
|---|---|---|
| 新建 | `src/requirement_workflow_v12/project_config.py` | `ProjectConfig` dataclass + `OnboardingState` enum |
| 新建 | `src/requirement_workflow_v12/project_bootstrapper.py` | GitHub API 写文件、YAML 模板渲染 |
| 新建 | `scripts/bootstrap_architecture.py` | 路径B：AI 扫描仓库生成 ARCHITECTURE.yaml（独立运行） |
| 新建 | `tests/test_project_config.py` | ProjectConfig 序列化测试 |
| 新建 | `tests/test_project_bootstrapper.py` | bootstrap 逻辑测试（mock GitHub API） |
| 新建 | `tests/test_project_onboarding.py` | Onboarding 对话流程测试 |
| 修改 | `src/requirement_workflow_v12/models.py` | Requirement 新增 needs_ui / github_repo_url / hifi_prototype_url / hifi_prototype_confirmed |
| 修改 | `src/requirement_workflow_v12/config.py` | 新增 github_token / github_default_branch |
| 修改 | `src/requirement_workflow_v12/store.py` | 序列化/反序列化 ProjectConfig；save/load 签名扩展 |
| 修改 | `src/requirement_workflow_v12/coordinator_service.py` | project_configs 字典 + onboarding 方法 + 设计系统触发 |
| 修改 | `src/requirement_workflow_v12/service_app.py` | 创建群 Onboarding 对话分支（3 问 + 路径判断 + bootstrap 异步） |
| 修改 | `src/requirement_workflow_v12/feishu_gateway.py` | create_design_system_document / append_design_system_section |

---

## Task 1：ProjectConfig 数据模型

**Files:**
- Create: `src/requirement_workflow_v12/project_config.py`
- Create: `tests/test_project_config.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_project_config.py
from dataclasses import asdict
from requirement_workflow_v12.project_config import OnboardingState, ProjectConfig


def test_project_config_defaults():
    cfg = ProjectConfig(github_repo_url="https://github.com/org/repo", is_new_project=True, tech_stack={})
    assert cfg.architecture_yaml_initialized is False
    assert cfg.acm_registry_initialized is False
    assert cfg.design_system_doc_id is None
    assert cfg.onboarding_state == OnboardingState.COLLECTING_REPO


def test_project_config_serializable():
    cfg = ProjectConfig(
        github_repo_url="https://github.com/org/repo",
        is_new_project=False,
        tech_stack={"language": "Python", "framework": "FastAPI"},
        architecture_yaml_initialized=True,
        acm_registry_initialized=True,
        design_system_doc_id="doc_abc123",
        onboarding_state=OnboardingState.COMPLETE,
    )
    d = asdict(cfg)
    assert d["github_repo_url"] == "https://github.com/org/repo"
    assert d["tech_stack"]["language"] == "Python"
    assert d["onboarding_state"] == "COMPLETE"
```

- [ ] **Step 2: 运行确认失败**

```bash
PYTHONPATH=src python3 -m pytest tests/test_project_config.py -v
```
期望：`ModuleNotFoundError: No module named 'requirement_workflow_v12.project_config'`

- [ ] **Step 3: 实现**

```python
# src/requirement_workflow_v12/project_config.py
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class OnboardingState(str, Enum):
    COLLECTING_REPO = "COLLECTING_REPO"           # 等待用户提供 GitHub 仓库地址
    COLLECTING_PROJECT_TYPE = "COLLECTING_PROJECT_TYPE"  # 等待用户选择新项目/已有代码库
    COLLECTING_TECH_STACK = "COLLECTING_TECH_STACK"      # 等待用户提供技术栈
    WAITING_ARCH_CONFIRMATION = "WAITING_ARCH_CONFIRMATION"  # 路径B：等待用户确认脚本已运行
    BOOTSTRAPPING = "BOOTSTRAPPING"               # 正在异步 bootstrap
    COMPLETE = "COMPLETE"                         # Onboarding 完成


@dataclass
class ProjectConfig:
    github_repo_url: str
    is_new_project: bool
    tech_stack: dict[str, str]
    architecture_yaml_initialized: bool = False
    acm_registry_initialized: bool = False
    design_system_doc_id: str | None = None
    onboarding_state: OnboardingState = OnboardingState.COLLECTING_REPO

    @property
    def is_onboarding_complete(self) -> bool:
        return self.onboarding_state == OnboardingState.COMPLETE

    @classmethod
    def from_dict(cls, data: dict) -> ProjectConfig:
        return cls(
            github_repo_url=data["github_repo_url"],
            is_new_project=data.get("is_new_project", True),
            tech_stack=data.get("tech_stack", {}),
            architecture_yaml_initialized=data.get("architecture_yaml_initialized", False),
            acm_registry_initialized=data.get("acm_registry_initialized", False),
            design_system_doc_id=data.get("design_system_doc_id"),
            onboarding_state=OnboardingState(data.get("onboarding_state", OnboardingState.COLLECTING_REPO.value)),
        )
```

- [ ] **Step 4: 运行确认通过**

```bash
PYTHONPATH=src python3 -m pytest tests/test_project_config.py -v
```
期望：2 passed

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/project_config.py tests/test_project_config.py
git commit -m "feat: add ProjectConfig data model with OnboardingState enum"
```

---

## Task 2：Requirement 模型新增字段 + config.py 新增设置

**Files:**
- Modify: `src/requirement_workflow_v12/models.py`
- Modify: `src/requirement_workflow_v12/config.py`
- Modify: `tests/test_requirement_workflow_v12.py`（补充字段默认值验证）

- [ ] **Step 1: 写失败测试**

在 `tests/test_requirement_workflow_v12.py` 末尾追加：

```python
def test_requirement_new_fields_default():
    from requirement_workflow_v12.models import Requirement
    req = Requirement(req_id="REQ-X-001", name="test", project="X", summary="s", creator="u")
    assert req.needs_ui is False
    assert req.github_repo_url == ""
    assert req.hifi_prototype_url == ""
    assert req.hifi_prototype_confirmed is False


def test_config_github_settings():
    import os
    os.environ["GITHUB_TOKEN"] = "ghp_test"
    os.environ["GITHUB_DEFAULT_BRANCH"] = "develop"
    from requirement_workflow_v12.config import load_settings
    settings = load_settings()
    assert settings.github_token == "ghp_test"
    assert settings.github_default_branch == "develop"
    del os.environ["GITHUB_TOKEN"]
    del os.environ["GITHUB_DEFAULT_BRANCH"]
```

- [ ] **Step 2: 运行确认失败**

```bash
PYTHONPATH=src python3 -m pytest tests/test_requirement_workflow_v12.py::test_requirement_new_fields_default tests/test_requirement_workflow_v12.py::test_config_github_settings -v
```
期望：2 failed（字段不存在）

- [ ] **Step 3: 实现 models.py**

在 `Requirement` dataclass 里，`updated_at` 字段之前追加：

```python
    needs_ui: bool = False
    github_repo_url: str = ""
    hifi_prototype_url: str = ""
    hifi_prototype_confirmed: bool = False
```

- [ ] **Step 4: 实现 config.py**

在 `Settings` dataclass 里追加：

```python
    github_token: str = os.environ.get("GITHUB_TOKEN", "")
    github_default_branch: str = os.environ.get("GITHUB_DEFAULT_BRANCH", "main")
```

- [ ] **Step 5: 运行确认通过**

```bash
PYTHONPATH=src python3 -m pytest tests/test_requirement_workflow_v12.py -v
```
期望：全部 passed（含旧测试）

- [ ] **Step 6: store.py 补充新字段反序列化**

在 `_requirement_from_payload` 方法里，`updated_at=` 那行之前追加：

```python
            needs_ui=data.get("needs_ui", False),
            github_repo_url=data.get("github_repo_url", ""),
            hifi_prototype_url=data.get("hifi_prototype_url", ""),
            hifi_prototype_confirmed=data.get("hifi_prototype_confirmed", False),
```

- [ ] **Step 7: Commit**

```bash
git add src/requirement_workflow_v12/models.py src/requirement_workflow_v12/config.py src/requirement_workflow_v12/store.py tests/test_requirement_workflow_v12.py
git commit -m "feat: add needs_ui and hifi_prototype fields to Requirement; add GitHub settings to config"
```

---

## Task 3：JsonStateStore 扩展以持久化 ProjectConfig

**Files:**
- Modify: `src/requirement_workflow_v12/store.py`
- Create: `tests/test_store_project_config.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_store_project_config.py
from tempfile import NamedTemporaryFile
from requirement_workflow_v12.store import JsonStateStore
from requirement_workflow_v12.project_config import OnboardingState, ProjectConfig


def _make_store() -> JsonStateStore:
    f = NamedTemporaryFile(suffix=".json", delete=False)
    f.close()
    return JsonStateStore(f.name)


def test_store_saves_and_loads_project_configs():
    store = _make_store()
    cfg = ProjectConfig(
        github_repo_url="https://github.com/org/repo",
        is_new_project=True,
        tech_stack={"language": "Python"},
        architecture_yaml_initialized=True,
        onboarding_state=OnboardingState.COMPLETE,
    )
    store.save_snapshot({}, {}, {}, project_configs={"PROJ": cfg})
    _, _, _, loaded = store.load_snapshot()
    assert "PROJ" in loaded
    assert loaded["PROJ"].github_repo_url == "https://github.com/org/repo"
    assert loaded["PROJ"].architecture_yaml_initialized is True
    assert loaded["PROJ"].onboarding_state == OnboardingState.COMPLETE


def test_store_loads_empty_project_configs_when_missing():
    store = _make_store()
    store.save_snapshot({}, {}, {}, project_configs={})
    _, _, _, loaded = store.load_snapshot()
    assert loaded == {}
```

- [ ] **Step 2: 运行确认失败**

```bash
PYTHONPATH=src python3 -m pytest tests/test_store_project_config.py -v
```
期望：2 failed（save_snapshot signature mismatch）

- [ ] **Step 3: 实现**

更新 `store.py` 的 import 区：

```python
from .project_config import OnboardingState, ProjectConfig
```

更新 `save_snapshot` 签名和实现：

```python
def save_snapshot(
    self,
    requirements: dict[str, Requirement],
    active_req_by_user: dict[str, str],
    project_groups: dict[str, str],
    project_configs: dict[str, ProjectConfig] | None = None,
) -> None:
    from dataclasses import asdict
    payload = {
        "requirements": {req_id: asdict(req) for req_id, req in requirements.items()},
        "active_req_by_user": active_req_by_user,
        "project_groups": project_groups,
        "project_configs": {
            name: asdict(cfg) for name, cfg in (project_configs or {}).items()
        },
    }
    self.path.write_text(json.dumps(payload, ensure_ascii=False, default=str, indent=2))
```

更新 `load_snapshot` 返回签名和实现：

```python
def load_snapshot(
    self,
) -> tuple[dict[str, Requirement], dict[str, str], dict[str, str], dict[str, ProjectConfig]]:
    if not self.path.exists():
        return {}, {}, {}, {}
    payload = json.loads(self.path.read_text())
    requirements = {
        req_id: self._requirement_from_payload(data)
        for req_id, data in payload.get("requirements", {}).items()
    }
    project_configs = {
        name: ProjectConfig.from_dict(data)
        for name, data in payload.get("project_configs", {}).items()
    }
    return (
        requirements,
        payload.get("active_req_by_user", {}),
        payload.get("project_groups", {}),
        project_configs,
    )
```

- [ ] **Step 4: 更新 service_app.py 中的 load_snapshot 调用**

找到 `service_app.py` 中 `load_snapshot` 调用处，更新解包：

```python
requirements, active_req_by_user, project_groups, project_configs = self.store.load_snapshot()
if service is None or requirements or active_req_by_user or project_groups:
    self.service.restore_snapshot(requirements, active_req_by_user, project_groups, project_configs)
```

- [ ] **Step 5: 运行全量测试确认通过**

```bash
PYTHONPATH=src python3 -m pytest tests/ -v
```
期望：全部 passed

- [ ] **Step 6: Commit**

```bash
git add src/requirement_workflow_v12/store.py src/requirement_workflow_v12/service_app.py tests/test_store_project_config.py
git commit -m "feat: extend JsonStateStore to persist ProjectConfig"
```

---

## Task 4：CoordinatorService 扩展 project_configs + onboarding 方法

**Files:**
- Modify: `src/requirement_workflow_v12/coordinator_service.py`
- Create: `tests/test_project_onboarding.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_project_onboarding.py
from requirement_workflow_v12.coordinator_service import CoordinatorService
from requirement_workflow_v12.project_config import OnboardingState, ProjectConfig


def _make_service() -> CoordinatorService:
    return CoordinatorService()


def test_is_new_project_when_no_config():
    svc = _make_service()
    assert svc.is_new_project("PROJ") is True


def test_is_not_new_project_when_config_exists():
    svc = _make_service()
    svc.project_configs["PROJ"] = ProjectConfig(
        github_repo_url="https://github.com/org/repo",
        is_new_project=True,
        tech_stack={},
        onboarding_state=OnboardingState.COMPLETE,
    )
    assert svc.is_new_project("PROJ") is False


def test_register_project_config():
    svc = _make_service()
    cfg = svc.register_project_config(
        project="PROJ",
        github_repo_url="https://github.com/org/repo",
        is_new_project=True,
        tech_stack={"language": "Python"},
    )
    assert cfg.github_repo_url == "https://github.com/org/repo"
    assert cfg.onboarding_state == OnboardingState.COLLECTING_PROJECT_TYPE
    assert "PROJ" in svc.project_configs


def test_advance_onboarding_state():
    svc = _make_service()
    svc.register_project_config("PROJ", "https://github.com/org/repo", True, {})
    svc.advance_onboarding_state("PROJ", OnboardingState.COLLECTING_TECH_STACK)
    assert svc.project_configs["PROJ"].onboarding_state == OnboardingState.COLLECTING_TECH_STACK


def test_complete_onboarding():
    svc = _make_service()
    svc.register_project_config("PROJ", "https://github.com/org/repo", True, {"language": "Python"})
    svc.complete_onboarding("PROJ", architecture_initialized=True, acm_initialized=True)
    cfg = svc.project_configs["PROJ"]
    assert cfg.onboarding_state == OnboardingState.COMPLETE
    assert cfg.architecture_yaml_initialized is True
    assert cfg.acm_registry_initialized is True


def test_restore_snapshot_includes_project_configs():
    svc = _make_service()
    cfg = ProjectConfig(
        github_repo_url="https://github.com/org/repo",
        is_new_project=True,
        tech_stack={},
        onboarding_state=OnboardingState.COMPLETE,
    )
    svc.restore_snapshot({}, {}, {}, {"PROJ": cfg})
    assert "PROJ" in svc.project_configs
```

- [ ] **Step 2: 运行确认失败**

```bash
PYTHONPATH=src python3 -m pytest tests/test_project_onboarding.py -v
```
期望：全部 failed（方法不存在）

- [ ] **Step 3: 实现**

在 `coordinator_service.py` 顶部 import 区追加：

```python
from .project_config import OnboardingState, ProjectConfig
```

在 `CoordinatorService.__init__` 追加：

```python
        self.project_configs: dict[str, ProjectConfig] = {}
```

在 `restore_snapshot` 方法签名和实现更新：

```python
    def restore_snapshot(
        self,
        requirements: dict[str, Requirement],
        active_req_by_user: dict[str, str],
        project_groups: dict[str, str],
        project_configs: dict[str, ProjectConfig] | None = None,
    ) -> None:
        self.requirements = requirements
        self.active_req_by_user = active_req_by_user
        self.project_groups = project_groups
        self.project_configs = project_configs or {}
```

追加新方法（在 `restore_snapshot` 之后）：

```python
    def is_new_project(self, project: str) -> bool:
        """Returns True if project has no ProjectConfig yet (onboarding not started)."""
        return project not in self.project_configs

    def get_project_config(self, project: str) -> ProjectConfig | None:
        return self.project_configs.get(project)

    def register_project_config(
        self,
        project: str,
        github_repo_url: str,
        is_new_project: bool,
        tech_stack: dict[str, str],
    ) -> ProjectConfig:
        """Called after GitHub repo URL is collected (step 1 of onboarding)."""
        cfg = ProjectConfig(
            github_repo_url=github_repo_url,
            is_new_project=is_new_project,
            tech_stack=tech_stack,
            onboarding_state=OnboardingState.COLLECTING_PROJECT_TYPE,
        )
        self.project_configs[project] = cfg
        return cfg

    def advance_onboarding_state(self, project: str, state: OnboardingState) -> None:
        cfg = self.project_configs[project]
        cfg.onboarding_state = state

    def set_tech_stack(self, project: str, tech_stack: dict[str, str]) -> None:
        self.project_configs[project].tech_stack = tech_stack

    def set_project_type(self, project: str, is_new_project: bool) -> None:
        self.project_configs[project].is_new_project = is_new_project

    def complete_onboarding(
        self,
        project: str,
        architecture_initialized: bool,
        acm_initialized: bool,
    ) -> None:
        cfg = self.project_configs[project]
        cfg.architecture_yaml_initialized = architecture_initialized
        cfg.acm_registry_initialized = acm_initialized
        cfg.onboarding_state = OnboardingState.COMPLETE

    def set_design_system_doc(self, project: str, doc_id: str) -> None:
        """Called when Feishu design system document is created for a project."""
        if project in self.project_configs:
            self.project_configs[project].design_system_doc_id = doc_id
```

- [ ] **Step 4: 运行确认通过**

```bash
PYTHONPATH=src python3 -m pytest tests/test_project_onboarding.py tests/ -v
```
期望：全部 passed

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/coordinator_service.py tests/test_project_onboarding.py
git commit -m "feat: add project_configs management to CoordinatorService"
```

---

## Task 5：ProjectBootstrapper — GitHub API 写文件（路径C）

**Files:**
- Create: `src/requirement_workflow_v12/project_bootstrapper.py`
- Create: `tests/test_project_bootstrapper.py`

- [ ] **Step 1: 安装 PyGithub**

```bash
pip3 install PyGithub
```

- [ ] **Step 2: 写失败测试**

```python
# tests/test_project_bootstrapper.py
from unittest.mock import MagicMock, patch
from requirement_workflow_v12.project_bootstrapper import ProjectBootstrapper


def _make_bootstrapper(token: str = "ghp_test", branch: str = "main") -> ProjectBootstrapper:
    return ProjectBootstrapper(github_token=token, default_branch=branch)


def test_render_architecture_yaml():
    b = _make_bootstrapper()
    yaml_text = b.render_architecture_yaml(
        project="risk-platform",
        tech_stack={"language": "Python", "framework": "FastAPI", "database": "PostgreSQL", "test_framework": "pytest"},
    )
    assert "project: risk-platform" in yaml_text
    assert "language: Python" in yaml_text
    assert "framework: FastAPI" in yaml_text
    assert "services: []" in yaml_text
    assert "modules: []" in yaml_text
    assert "data_models: []" in yaml_text


def test_render_acm_registry_yaml():
    b = _make_bootstrapper()
    yaml_text = b.render_acm_registry_yaml()
    assert "registry: []" in yaml_text
    assert "last_updated:" in yaml_text


def test_bootstrap_new_project_calls_github_api():
    b = _make_bootstrapper()
    mock_repo = MagicMock()
    mock_repo.get_contents.side_effect = Exception("404 Not Found")

    with patch("requirement_workflow_v12.project_bootstrapper.Github") as MockGithub:
        MockGithub.return_value.get_repo.return_value = mock_repo
        b.bootstrap_new_project(
            repo_url="https://github.com/org/repo",
            project="risk-platform",
            tech_stack={"language": "Python", "framework": "FastAPI", "database": "PostgreSQL", "test_framework": "pytest"},
        )

    assert mock_repo.create_file.call_count == 2
    calls = [call[0][0] for call in mock_repo.create_file.call_args_list]
    assert "ARCHITECTURE.yaml" in calls
    assert "spec/registry/consolidated.yaml" in calls


def test_bootstrap_skips_existing_file():
    """If ARCHITECTURE.yaml already exists, don't overwrite it."""
    b = _make_bootstrapper()
    mock_repo = MagicMock()
    existing = MagicMock()
    mock_repo.get_contents.return_value = existing  # file exists

    with patch("requirement_workflow_v12.project_bootstrapper.Github") as MockGithub:
        MockGithub.return_value.get_repo.return_value = mock_repo
        b.bootstrap_new_project(
            repo_url="https://github.com/org/repo",
            project="risk-platform",
            tech_stack={"language": "Python"},
        )

    # ARCHITECTURE.yaml exists → skip; only ACM registry created
    create_calls = [call[0][0] for call in mock_repo.create_file.call_args_list]
    assert "ARCHITECTURE.yaml" not in create_calls
```

- [ ] **Step 3: 运行确认失败**

```bash
PYTHONPATH=src python3 -m pytest tests/test_project_bootstrapper.py -v
```
期望：全部 failed（模块不存在）

- [ ] **Step 4: 实现**

```python
# src/requirement_workflow_v12/project_bootstrapper.py
from __future__ import annotations

import logging
from datetime import datetime, timezone

try:
    from github import Github, GithubException
except ImportError:  # pragma: no cover
    Github = None  # type: ignore[assignment, misc]
    GithubException = Exception  # type: ignore[assignment, misc]

LOGGER = logging.getLogger(__name__)

_ARCHITECTURE_YAML_TEMPLATE = """\
# ARCHITECTURE.yaml
# 维护者: checkpoint-handler（自动更新）+ 人工（首次建立）
# 更新策略: 每次 Impl PR 合并后更新

version: "{date}"
project: {project}

tech_stack:
  language: {language}
  framework: {framework}
  database: {database}
  test_framework: {test_framework}

services: []
modules: []
data_models: []
external_dependencies: []
"""

_ACM_REGISTRY_TEMPLATE = """\
# spec/registry/consolidated.yaml
# 维护者: checkpoint-handler（自动更新）
# 更新策略: append-only

last_updated: "{date}"

registry: []
"""


class ProjectBootstrapper:
    def __init__(self, github_token: str, default_branch: str = "main") -> None:
        self.github_token = github_token
        self.default_branch = default_branch

    def render_architecture_yaml(self, project: str, tech_stack: dict[str, str]) -> str:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return _ARCHITECTURE_YAML_TEMPLATE.format(
            date=date,
            project=project,
            language=tech_stack.get("language", ""),
            framework=tech_stack.get("framework", ""),
            database=tech_stack.get("database", ""),
            test_framework=tech_stack.get("test_framework", ""),
        )

    def render_acm_registry_yaml(self) -> str:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return _ACM_REGISTRY_TEMPLATE.format(date=date)

    def bootstrap_new_project(
        self,
        repo_url: str,
        project: str,
        tech_stack: dict[str, str],
    ) -> None:
        """Path C: create ARCHITECTURE.yaml + ACM registry in GitHub repo."""
        if Github is None:
            raise RuntimeError("PyGithub not installed. Run: pip install PyGithub")

        repo_path = self._repo_path_from_url(repo_url)
        g = Github(self.github_token)
        repo = g.get_repo(repo_path)

        arch_yaml = self.render_architecture_yaml(project, tech_stack)
        self._create_file_if_missing(
            repo,
            path="ARCHITECTURE.yaml",
            content=arch_yaml,
            commit_message="chore: initialize ARCHITECTURE.yaml (project context bootstrap)",
        )

        acm_yaml = self.render_acm_registry_yaml()
        self._create_file_if_missing(
            repo,
            path="spec/registry/consolidated.yaml",
            content=acm_yaml,
            commit_message="chore: initialize ACM registry (project context bootstrap)",
        )
        LOGGER.info("Bootstrap complete for project=%s repo=%s", project, repo_url)

    def verify_architecture_yaml_exists(self, repo_url: str) -> bool:
        """Used in path B to verify user has run the bootstrap script."""
        if Github is None:
            return False
        try:
            repo_path = self._repo_path_from_url(repo_url)
            g = Github(self.github_token)
            repo = g.get_repo(repo_path)
            repo.get_contents("ARCHITECTURE.yaml")
            return True
        except Exception:
            return False

    def _create_file_if_missing(self, repo, path: str, content: str, commit_message: str) -> None:
        try:
            repo.get_contents(path)
            LOGGER.info("File already exists, skipping: %s", path)
        except Exception:
            repo.create_file(
                path=path,
                message=commit_message,
                content=content,
                branch=self.default_branch,
            )
            LOGGER.info("Created file: %s", path)

    @staticmethod
    def _repo_path_from_url(repo_url: str) -> str:
        """'https://github.com/org/repo' → 'org/repo'"""
        return repo_url.rstrip("/").removeprefix("https://github.com/")
```

- [ ] **Step 5: 运行确认通过**

```bash
PYTHONPATH=src python3 -m pytest tests/test_project_bootstrapper.py -v
```
期望：4 passed

- [ ] **Step 6: Commit**

```bash
git add src/requirement_workflow_v12/project_bootstrapper.py tests/test_project_bootstrapper.py
git commit -m "feat: add ProjectBootstrapper with GitHub API file creation (path C)"
```

---

## Task 6：service_app.py — 创建群 Onboarding 对话分支

**Files:**
- Modify: `src/requirement_workflow_v12/service_app.py`
- Modify: `tests/test_project_onboarding.py`（追加集成测试）

- [ ] **Step 1: 写失败测试（追加到 test_project_onboarding.py）**

```python
# 追加到 tests/test_project_onboarding.py

import sys, types

# Stub lark_oapi so service_app can be imported without runtime deps
lark_stub = types.ModuleType("lark_oapi")
lark_stub.EventDispatcherHandler = object
lark_stub.LogLevel = type("LogLevel", (), {"INFO": "INFO"})()
lark_stub.ws = types.ModuleType("lark_oapi.ws")
sys.modules.setdefault("lark_oapi", lark_stub)
sys.modules.setdefault("lark_oapi.ws", lark_stub.ws)

from requirement_workflow_v12.service_app import CoordinatorRuntimeApp, MessageContext
from requirement_workflow_v12.config import Settings
from requirement_workflow_v12.project_config import OnboardingState


def _make_app() -> CoordinatorRuntimeApp:
    settings = Settings(
        feishu_app_id="app",
        feishu_app_secret="secret",
        creation_group_chat_id="creation_chat",
        github_token="ghp_test",
    )
    from unittest.mock import MagicMock
    app = CoordinatorRuntimeApp.__new__(CoordinatorRuntimeApp)
    app.settings = settings
    app.service = CoordinatorService()
    app.gateway = MagicMock()
    app.store = MagicMock()
    app._observed_creation_group_chat_id = "creation_chat"
    return app


def _ctx(text: str, user_id: str = "user1", chat_id: str = "creation_chat") -> MessageContext:
    return MessageContext(chat_id=chat_id, chat_type="group", user_id=user_id, text=text)


def test_onboarding_triggered_for_new_project():
    app = _make_app()
    responses = app.handle_text_message(_ctx("新建需求 PROJ 登录功能 用户可以用邮箱登录"))
    texts = [r.text for r in responses if hasattr(r, "text")]
    assert any("新项目" in t or "GitHub" in t for t in texts)


def test_onboarding_collects_repo_url():
    app = _make_app()
    app.handle_text_message(_ctx("新建需求 PROJ 登录功能 用户可以用邮箱登录"))
    # Now user provides GitHub URL
    responses = app.handle_text_message(_ctx("https://github.com/org/repo"))
    texts = [r.text for r in responses if hasattr(r, "text")]
    assert any("全新" in t or "代码库" in t for t in texts)
    cfg = app.service.project_configs.get("PROJ")
    assert cfg is not None
    assert cfg.github_repo_url == "https://github.com/org/repo"
    assert cfg.onboarding_state == OnboardingState.COLLECTING_PROJECT_TYPE


def test_onboarding_invalid_url_reprompts():
    app = _make_app()
    app.handle_text_message(_ctx("新建需求 PROJ 登录功能 用户可以用邮箱登录"))
    responses = app.handle_text_message(_ctx("not-a-url"))
    texts = [r.text for r in responses if hasattr(r, "text")]
    assert any("格式" in t or "github.com" in t for t in texts)
    assert "PROJ" not in app.service.project_configs
```

- [ ] **Step 2: 运行确认失败**

```bash
PYTHONPATH=src python3 -m pytest tests/test_project_onboarding.py::test_onboarding_triggered_for_new_project -v
```
期望：FAILED

- [ ] **Step 3: 实现 service_app.py 中的 Onboarding 分支**

在 `service_app.py` 顶部 import 区追加：

```python
import re
import threading
from .project_config import OnboardingState, ProjectConfig
from .project_bootstrapper import ProjectBootstrapper
```

在 `CoordinatorRuntimeApp.__init__` 末尾追加：

```python
        self._pending_onboarding_project: dict[str, str] = {}  # user_id → project name
```

替换 `_handle_creation_group_message` 方法：

```python
    def _handle_creation_group_message(self, context: MessageContext) -> list[OutboundMessage | OutboundCard]:
        # Check if user is mid-onboarding
        pending_project = self._pending_onboarding_project.get(context.user_id)
        if pending_project:
            return self._handle_onboarding_reply(context, pending_project)

        if "创建需求" not in context.text:
            return []

        self._observed_creation_group_chat_id = context.chat_id
        parsed = self._parse_creation_command(context.text)
        if parsed is None:
            return [OutboundMessage(
                receive_id=context.chat_id,
                text="格式：新建需求 [项目名] [需求名] [简述] 或 创建需求 [项目名] [需求名] [简述]（可加 --ui 标记）",
            )]

        project, name, summary, needs_ui = parsed

        if self.service.is_new_project(project):
            self._pending_onboarding_project[context.user_id] = project
            # Store partial requirement info for later creation
            self._pending_requirement_info: dict = getattr(self, "_pending_requirement_info", {})
            self._pending_requirement_info[context.user_id] = {
                "project": project, "name": name, "summary": summary,
                "needs_ui": needs_ui, "creator": context.sender_name,
                "creator_user_id": context.user_id, "creation_chat_id": context.chat_id,
            }
            return [OutboundMessage(
                receive_id=context.chat_id,
                text=(
                    f"检测到 {project} 是新项目，需要先完成项目初始化（3 个问题）。\n\n"
                    "问题 1/3：GitHub 仓库地址？\n（格式：https://github.com/org/repo）"
                ),
            )]

        # Existing project → normal creation flow
        return [
            OutboundCard(
                receive_id=context.chat_id,
                card=self._build_requirement_creation_card(context),
            )
        ]

    def _parse_creation_command(self, text: str) -> tuple[str, str, str, bool] | None:
        """Parse '新建需求 PROJ 需求名 简述 [--ui]' or '创建需求 ...'"""
        needs_ui = "--ui" in text
        text = text.replace("--ui", "").strip()
        pattern = r"(?:新建需求|创建需求)\s+(\S+)\s+(\S+)\s+(.+)"
        m = re.match(pattern, text.strip())
        if not m:
            return None
        return m.group(1), m.group(2), m.group(3).strip(), needs_ui

    def _handle_onboarding_reply(self, context: MessageContext, project: str) -> list[OutboundMessage]:
        cfg = self.service.project_configs.get(project)
        state = cfg.onboarding_state if cfg else OnboardingState.COLLECTING_REPO
        text = context.text.strip()

        if state == OnboardingState.COLLECTING_REPO or cfg is None:
            return self._onboarding_collect_repo(context, project, text)

        if state == OnboardingState.COLLECTING_PROJECT_TYPE:
            return self._onboarding_collect_project_type(context, project, text)

        if state == OnboardingState.COLLECTING_TECH_STACK:
            return self._onboarding_collect_tech_stack(context, project, text)

        if state == OnboardingState.WAITING_ARCH_CONFIRMATION:
            return self._onboarding_wait_arch_confirmation(context, project, text)

        return []

    def _onboarding_collect_repo(self, context: MessageContext, project: str, text: str) -> list[OutboundMessage]:
        if not re.match(r"https://github\.com/[\w.-]+/[\w.-]+", text):
            return [OutboundMessage(
                receive_id=context.chat_id,
                text="格式不正确，请提供 GitHub 仓库地址（https://github.com/org/repo）",
            )]
        self.service.register_project_config(project, text, True, {})
        return [OutboundMessage(
            receive_id=context.chat_id,
            text=(
                "问题 2/3：全新项目还是已有代码库？\n"
                "A. 全新项目（从零开始，无现有代码）\n"
                "B. 已有代码库（需先运行初始化脚本）"
            ),
        )]

    def _onboarding_collect_project_type(self, context: MessageContext, project: str, text: str) -> list[OutboundMessage]:
        upper = text.upper()
        if "A" in upper or "全新" in upper:
            self.service.set_project_type(project, is_new_project=True)
        elif "B" in upper or "已有" in upper or "代码" in upper:
            self.service.set_project_type(project, is_new_project=False)
        else:
            return [OutboundMessage(
                receive_id=context.chat_id,
                text="请回复 A（全新项目）或 B（已有代码库）",
            )]
        self.service.advance_onboarding_state(project, OnboardingState.COLLECTING_TECH_STACK)
        return [OutboundMessage(
            receive_id=context.chat_id,
            text="问题 3/3：技术栈？\n（如：Python/FastAPI/PostgreSQL/pytest）",
        )]

    def _onboarding_collect_tech_stack(self, context: MessageContext, project: str, text: str) -> list[OutboundMessage]:
        tech_stack = self._parse_tech_stack(text)
        self.service.set_tech_stack(project, tech_stack)
        cfg = self.service.project_configs[project]

        if not cfg.is_new_project:
            self.service.advance_onboarding_state(project, OnboardingState.WAITING_ARCH_CONFIRMATION)
            cfg_url = cfg.github_repo_url
            return [OutboundMessage(
                receive_id=context.chat_id,
                text=(
                    "已有代码库需先生成架构快照，请运行：\n\n"
                    f"  python scripts/bootstrap_architecture.py --repo {cfg_url}\n\n"
                    "完成后回复「初始化完成」继续。"
                ),
            )]

        # New project → async bootstrap
        self.service.advance_onboarding_state(project, OnboardingState.BOOTSTRAPPING)
        threading.Thread(
            target=self._run_bootstrap_new_project,
            args=(context, project),
            daemon=True,
        ).start()
        return [OutboundMessage(
            receive_id=context.chat_id,
            text="信息收集完成，正在初始化项目上下文，请稍候…",
        )]

    def _onboarding_wait_arch_confirmation(self, context: MessageContext, project: str, text: str) -> list[OutboundMessage]:
        if "初始化完成" not in text and "完成" not in text:
            return [OutboundMessage(
                receive_id=context.chat_id,
                text="请运行完脚本后回复「初始化完成」",
            )]
        cfg = self.service.project_configs[project]
        bootstrapper = self._make_bootstrapper()
        if not bootstrapper.verify_architecture_yaml_exists(cfg.github_repo_url):
            return [OutboundMessage(
                receive_id=context.chat_id,
                text="未检测到 ARCHITECTURE.yaml，请确认脚本运行成功后重试。",
            )]
        self.service.advance_onboarding_state(project, OnboardingState.BOOTSTRAPPING)
        threading.Thread(
            target=self._run_bootstrap_existing_project,
            args=(context, project),
            daemon=True,
        ).start()
        return [OutboundMessage(
            receive_id=context.chat_id,
            text="已确认，正在完成剩余初始化（ACM 注册表）…",
        )]

    def _run_bootstrap_new_project(self, context: MessageContext, project: str) -> None:
        cfg = self.service.project_configs[project]
        try:
            bootstrapper = self._make_bootstrapper()
            bootstrapper.bootstrap_new_project(
                repo_url=cfg.github_repo_url,
                project=project,
                tech_stack=cfg.tech_stack,
            )
            self.service.complete_onboarding(project, architecture_initialized=True, acm_initialized=True)
        except Exception as exc:
            LOGGER.error("Bootstrap failed for project=%s: %s", project, exc)
            self.gateway.send_text(context.chat_id, f"项目初始化失败：{exc}\n请检查 GitHub 权限后重试。")
            return
        finally:
            self._save_state()
            self._pending_onboarding_project.pop(context.user_id, None)

        self._finish_onboarding(context, project)

    def _run_bootstrap_existing_project(self, context: MessageContext, project: str) -> None:
        cfg = self.service.project_configs[project]
        try:
            bootstrapper = self._make_bootstrapper()
            # Only create ACM registry; ARCHITECTURE.yaml already exists
            from github import Github
            repo_path = bootstrapper._repo_path_from_url(cfg.github_repo_url)
            g = Github(self.settings.github_token)
            repo = g.get_repo(repo_path)
            acm_yaml = bootstrapper.render_acm_registry_yaml()
            bootstrapper._create_file_if_missing(
                repo,
                path="spec/registry/consolidated.yaml",
                content=acm_yaml,
                commit_message="chore: initialize ACM registry",
            )
            self.service.complete_onboarding(project, architecture_initialized=True, acm_initialized=True)
        except Exception as exc:
            LOGGER.error("Bootstrap (existing) failed for project=%s: %s", project, exc)
            self.gateway.send_text(context.chat_id, f"ACM 注册表初始化失败：{exc}")
            return
        finally:
            self._save_state()
            self._pending_onboarding_project.pop(context.user_id, None)

        self._finish_onboarding(context, project)

    def _finish_onboarding(self, context: MessageContext, project: str) -> None:
        req_info = getattr(self, "_pending_requirement_info", {}).get(context.user_id)
        if req_info is None:
            return
        self.gateway.send_text(
            context.chat_id,
            f"{project} 初始化完成 ✓\n"
            "· ARCHITECTURE.yaml 已就绪\n"
            "· ACM 注册表已就绪（spec/registry/consolidated.yaml）\n\n"
            "正在创建需求，稍后通知 Author 进入讨论…",
        )
        # Create the requirement and provision it
        from .protocols import CreationRequest
        request = CreationRequest(
            project=req_info["project"],
            name=req_info["name"],
            summary=req_info["summary"],
            creator=req_info["creator"],
            creator_user_id=req_info["creator_user_id"],
            creation_chat_id=req_info["creation_chat_id"],
        )
        response = self.service.create_requirement_from_group(request)
        requirement = self.service.get_requirement(response.req_id)
        if requirement:
            requirement.needs_ui = req_info.get("needs_ui", False)
            requirement.github_repo_url = self.service.project_configs[project].github_repo_url
        self._save_state()
        threading.Thread(
            target=self._provision_requirement_after_creation,
            args=(request, response.req_id),
            daemon=True,
        ).start()
        self._pending_requirement_info.pop(context.user_id, None)

    def _make_bootstrapper(self) -> ProjectBootstrapper:
        return ProjectBootstrapper(
            github_token=self.settings.github_token,
            default_branch=self.settings.github_default_branch,
        )

    @staticmethod
    def _parse_tech_stack(text: str) -> dict[str, str]:
        """Parse 'Python/FastAPI/PostgreSQL/pytest' into dict."""
        parts = [p.strip() for p in re.split(r"[/,；;、]", text) if p.strip()]
        keys = ["language", "framework", "database", "test_framework"]
        return {keys[i]: parts[i] for i in range(min(len(keys), len(parts)))}
```

- [ ] **Step 4: 运行确认通过**

```bash
PYTHONPATH=src python3 -m pytest tests/test_project_onboarding.py -v
```
期望：全部 passed

- [ ] **Step 5: 全量测试**

```bash
PYTHONPATH=src python3 -m pytest tests/ -v
```
期望：全部 passed

- [ ] **Step 6: Commit**

```bash
git add src/requirement_workflow_v12/service_app.py tests/test_project_onboarding.py
git commit -m "feat: add project onboarding 3-question flow to creation group handler"
```

---

## Task 7：UI 设计系统 Create / Append 触发逻辑

**Files:**
- Modify: `src/requirement_workflow_v12/feishu_gateway.py`
- Modify: `src/requirement_workflow_v12/service_app.py`
- Create: `tests/test_ui_design_system.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_ui_design_system.py
from unittest.mock import MagicMock
from requirement_workflow_v12.coordinator_service import CoordinatorService
from requirement_workflow_v12.project_config import OnboardingState, ProjectConfig


def _make_service_with_project(project: str = "PROJ") -> CoordinatorService:
    svc = CoordinatorService()
    svc.project_configs[project] = ProjectConfig(
        github_repo_url="https://github.com/org/repo",
        is_new_project=True,
        tech_stack={},
        onboarding_state=OnboardingState.COMPLETE,
    )
    return svc


def test_should_create_design_system_when_first_ui_requirement_approved():
    svc = _make_service_with_project("PROJ")
    assert svc.should_create_design_system("PROJ") is True


def test_should_not_create_design_system_when_already_exists():
    svc = _make_service_with_project("PROJ")
    svc.project_configs["PROJ"].design_system_doc_id = "existing_doc_id"
    assert svc.should_create_design_system("PROJ") is False


def test_should_not_create_design_system_when_no_project_config():
    svc = CoordinatorService()
    assert svc.should_create_design_system("UNKNOWN") is False
```

- [ ] **Step 2: 运行确认失败**

```bash
PYTHONPATH=src python3 -m pytest tests/test_ui_design_system.py -v
```
期望：3 failed

- [ ] **Step 3: 实现 coordinator_service.py**

追加方法：

```python
    def should_create_design_system(self, project: str) -> bool:
        """True if project has config but no design system doc yet."""
        cfg = self.project_configs.get(project)
        if cfg is None:
            return False
        return cfg.design_system_doc_id is None
```

- [ ] **Step 4: 实现 feishu_gateway.py**

在 `FeishuGateway` 类中追加两个方法（在 `update_requirement_record` 之后）：

```python
    def create_design_system_document(self, project: str) -> str:
        """Create a new Feishu doc for the project design system. Returns doc_id."""
        title = f"{project} 设计系统"
        LOGGER.info("Creating design system document for project=%s", project)
        request = (
            CreateDocumentRequest.builder()
            .request_body(
                CreateDocumentRequestBody.builder()
                .title(title)
                .folder_token(self.settings.feishu_doc_folder_token)
                .build()
            )
            .build()
        )
        response = self.client.docx.v1.document.create(request)
        if not response.success():
            raise RuntimeError(f"Failed to create design system document: {response.msg}")
        doc_id = response.data.document.document_id
        LOGGER.info("Created design system document doc_id=%s project=%s", doc_id, project)
        return doc_id

    def append_design_decision_to_doc(self, doc_id: str, req_id: str, content: str) -> None:
        """Append a design decision block to the design system document."""
        LOGGER.info("Appending design decision to doc_id=%s req_id=%s", doc_id, req_id)
        text_content = f"[{req_id}] {content}"
        block = (
            Block.builder()
            .block_type(self.BLOCK_TYPE_TEXT)
            .text(
                Text.builder()
                .elements([
                    TextElement.builder()
                    .text_run(TextRun.builder().content(text_content).build())
                    .build()
                ])
                .build()
            )
            .build()
        )
        request = (
            CreateDocumentBlockChildrenRequest.builder()
            .document_id(doc_id)
            .block_id(doc_id)
            .request_body(
                CreateDocumentBlockChildrenRequestBody.builder()
                .children([block])
                .build()
            )
            .build()
        )
        response = self.client.docx.v1.document_block_children.create(request)
        if not response.success():
            LOGGER.warning("Failed to append design decision: %s", response.msg)
```

- [ ] **Step 5: 在 service_app.py 中触发设计系统创建**

找到 `_handle_formal_review_decision` 方法中处理 `approved=True` 且状态变为 APPROVED 的部分，在 `_sync_requirement_outputs` 之后追加：

```python
        # Create design system document for first UI requirement
        if approved and requirement.status == WorkflowStatus.APPROVED and requirement.needs_ui:
            if self.service.should_create_design_system(requirement.project):
                try:
                    doc_id = self.gateway.create_design_system_document(requirement.project)
                    self.service.set_design_system_doc(requirement.project, doc_id)
                    self._save_state()
                    LOGGER.info("Design system document created for project=%s doc_id=%s", requirement.project, doc_id)
                except Exception as exc:
                    LOGGER.warning("Failed to create design system document: %s", exc)
```

- [ ] **Step 6: 运行全量测试**

```bash
PYTHONPATH=src python3 -m pytest tests/ -v
```
期望：全部 passed

- [ ] **Step 7: Commit**

```bash
git add src/requirement_workflow_v12/coordinator_service.py src/requirement_workflow_v12/feishu_gateway.py src/requirement_workflow_v12/service_app.py tests/test_ui_design_system.py
git commit -m "feat: trigger design system document creation on first UI requirement APPROVED"
```

---

## Task 8：scripts/bootstrap_architecture.py（路径B 独立脚本）

**Files:**
- Create: `scripts/bootstrap_architecture.py`

- [ ] **Step 1: 实现**

```python
#!/usr/bin/env python3
"""
Path B bootstrap script: scan existing GitHub repo and generate ARCHITECTURE.yaml.

Usage:
    python scripts/bootstrap_architecture.py --repo https://github.com/org/repo [--branch main] [--token TOKEN]

Requires ANTHROPIC_API_KEY and GITHUB_TOKEN env vars (or --token flag).
"""
from __future__ import annotations

import argparse
import os
import sys

try:
    import anthropic
except ImportError:
    print("ERROR: anthropic package not installed. Run: pip install anthropic")
    sys.exit(1)

try:
    from github import Github
except ImportError:
    print("ERROR: PyGithub not installed. Run: pip install PyGithub")
    sys.exit(1)

SYSTEM_PROMPT = """\
You are a technical architect. Given a GitHub repository's directory tree and key file excerpts,
generate an ARCHITECTURE.yaml file following this exact schema:

version: "YYYY-MM-DD"
project: {project_name}

tech_stack:
  language: ...
  framework: ...
  database: ...
  test_framework: ...

services:
  - name: ...
    description: ...
    repo_path: ...
    public_interfaces:
      - method: GET/POST/PUT/DELETE
        path: /api/...
        introduced_in: UNKNOWN

modules:
  - name: ...
    description: ...
    repo_path: ...
    public_api:
      - function: ...
        input: "..."
        output: "..."
    status: stable

data_models:
  - name: ...
    description: ...
    columns:
      id: "UUID, primary key"

external_dependencies: []

Only include what you can confidently infer from the code. Leave lists empty if uncertain.
Output ONLY the YAML, no explanation.
"""


def get_repo_context(repo, branch: str) -> str:
    """Fetch directory tree + key file excerpts."""
    lines = []
    try:
        contents = repo.get_contents("", ref=branch)
        tree_items = []
        while contents:
            item = contents.pop(0)
            tree_items.append(item.path)
            if item.type == "dir" and item.path.count("/") < 2:
                contents.extend(repo.get_contents(item.path, ref=branch))
        lines.append("## Directory Tree\n" + "\n".join(tree_items[:150]))
    except Exception as e:
        lines.append(f"## Directory Tree\nError: {e}")

    # Try to read key files
    key_paths = ["README.md", "pyproject.toml", "requirements.txt", "package.json"]
    for path in key_paths:
        try:
            f = repo.get_contents(path, ref=branch)
            text = f.decoded_content.decode("utf-8", errors="replace")[:2000]
            lines.append(f"## {path}\n{text}")
        except Exception:
            pass

    return "\n\n".join(lines)


def generate_architecture_yaml(repo_context: str, project_name: str) -> str:
    client = anthropic.Anthropic()
    message = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": f"Project name: {project_name}\n\n{repo_context}",
        }],
    )
    return message.content[0].text.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate ARCHITECTURE.yaml from existing GitHub repo")
    parser.add_argument("--repo", required=True, help="GitHub repo URL (https://github.com/org/repo)")
    parser.add_argument("--branch", default="main", help="Branch to scan (default: main)")
    parser.add_argument("--token", default=os.environ.get("GITHUB_TOKEN", ""), help="GitHub token")
    parser.add_argument("--output", default="ARCHITECTURE.yaml", help="Output file path")
    args = parser.parse_args()

    github_token = args.token or os.environ.get("GITHUB_TOKEN", "")
    if not github_token:
        print("ERROR: GitHub token required. Set GITHUB_TOKEN env var or use --token")
        sys.exit(1)

    repo_path = args.repo.rstrip("/").removeprefix("https://github.com/")
    project_name = repo_path.split("/")[-1]

    print(f"Scanning repo: {args.repo} (branch: {args.branch})")
    g = Github(github_token)
    repo = g.get_repo(repo_path)

    print("Fetching repository context...")
    context = get_repo_context(repo, args.branch)

    print("Generating ARCHITECTURE.yaml with Claude...")
    yaml_content = generate_architecture_yaml(context, project_name)

    print("\n--- Generated ARCHITECTURE.yaml ---")
    print(yaml_content)
    print("-----------------------------------\n")

    confirm = input("Commit this to GitHub? [y/N] ").strip().lower()
    if confirm != "y":
        # Save locally
        with open(args.output, "w") as f:
            f.write(yaml_content)
        print(f"Saved locally to {args.output}. Review and commit manually.")
        return

    try:
        existing = repo.get_contents("ARCHITECTURE.yaml", ref=args.branch)
        repo.update_file(
            path="ARCHITECTURE.yaml",
            message="chore: update ARCHITECTURE.yaml (bootstrap from existing codebase)",
            content=yaml_content,
            sha=existing.sha,
            branch=args.branch,
        )
        print("Updated ARCHITECTURE.yaml in GitHub.")
    except Exception:
        repo.create_file(
            path="ARCHITECTURE.yaml",
            message="chore: initialize ARCHITECTURE.yaml (bootstrap from existing codebase)",
            content=yaml_content,
            branch=args.branch,
        )
        print("Created ARCHITECTURE.yaml in GitHub.")

    print("Done. You can now reply 「初始化完成」 in the Feishu creation group.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add scripts/bootstrap_architecture.py
git commit -m "feat: add bootstrap_architecture.py script for path B (existing repo AI scan)"
```

---

## Task 9：全量验证 + 推送

- [ ] **Step 1: 全量测试**

```bash
PYTHONPATH=src python3 -m pytest tests/ -v --tb=short
```
期望：全部 passed

- [ ] **Step 2: Push**

```bash
git push origin main
```

- [ ] **Step 3: 验证部署环境（在服务器上）**

```bash
# 确认新环境变量已配置
echo $GITHUB_TOKEN

# 拉取最新代码并重启服务
git pull origin main
# 按现有部署方式重启 coordinator service
```
