# Spec Context 端点与 ARCHITECTURE.yaml 注入 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Coordinator Service 新增 `/queries/openclaw/spec-context` 端点，spec-author Agent 通过它拿到需求 URL + 项目 ARCHITECTURE.yaml 原文并在后续 callback 中回证，关闭 Spec 撰写阶段上下文漂移风险。

**Architecture:** 新增 `github_client.py` 和 `spec_context.py` 两个模块；`Requirement` 加两个审计字段；扩展现有 `/callbacks/openclaw/spec-turn` 增加 context_token 校验和 architecture_commit_sha 回证；spec-author SKILL.md 改写 Step 1。

**Tech Stack:** Python 3.11+ / `dataclasses` / `urllib`（标准库，禁止新增第三方依赖）/ 现有 `JsonStateStore` 持久化层 / pytest 测试。

**设计文档**：`docs/superpowers/specs/2026-04-15-spec-context-endpoint-design.md`

---

## File Structure

### 新增文件

| 文件 | 职责 |
|------|------|
| `src/requirement_workflow_v12/github_client.py` | 封装 GitHub Contents API 调用，解析 repo_url，抛出分类异常 |
| `src/requirement_workflow_v12/spec_context.py` | 组装 spec-context payload，校验状态门禁，生成 context_token |
| `tests/test_github_client.py` | github_client 单元测试 |
| `tests/test_spec_context.py` | spec_context builder + service_app 端点集成测试 |

### 修改文件

| 文件 | 变更 |
|------|------|
| `src/requirement_workflow_v12/models.py` | `Requirement` 新增 2 字段 |
| `src/requirement_workflow_v12/store.py` | 兼容读取 2 新字段 |
| `src/requirement_workflow_v12/service_app.py` | 新增路由 + 扩展 spec-turn 校验 |
| `scripts/send_openclaw_callback.py` | 新增 `spec-context` 子命令，`spec-start` / `spec-submit` 接受 `--context-token` / `--architecture-commit-sha` 参数 |
| `docs/agents/spec-author/SKILL.md` | Step 1 改走 spec-context，禁用旁路读文档 |

---

## Task 1: Requirement 数据模型新增字段

**Files:**
- Modify: `src/requirement_workflow_v12/models.py`
- Modify: `src/requirement_workflow_v12/store.py:108-122`
- Test: `tests/test_spec_context.py`

- [ ] **Step 1：写失败测试**

追加到 `tests/test_spec_context.py`（新文件）：

```python
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.models import Requirement, WorkflowStatus
from requirement_workflow_v12.store import JsonStateStore


def test_requirement_has_spec_context_fields():
    req = Requirement(req_id="REQ-T-001", name="t", project="P", summary="s", creator="c")
    assert req.active_spec_context_token == ""
    assert req.spec_context_snapshot_sha == ""


def test_store_round_trips_spec_context_fields():
    req = Requirement(req_id="REQ-T-002", name="t", project="P", summary="s", creator="c")
    req.active_spec_context_token = "spec_ctx_REQ-T-002_1700000000_abcd"
    req.spec_context_snapshot_sha = "deadbeef1234"

    with tempfile.TemporaryDirectory() as tmpdir:
        store = JsonStateStore(f"{tmpdir}/state.json")
        store.save_snapshot({"REQ-T-002": req}, {}, {})
        reqs, _, _, _ = store.load_snapshot()
        loaded = reqs["REQ-T-002"]
        assert loaded.active_spec_context_token == "spec_ctx_REQ-T-002_1700000000_abcd"
        assert loaded.spec_context_snapshot_sha == "deadbeef1234"


def test_store_reads_legacy_snapshot_without_spec_context_fields():
    import json
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "state.json"
        path.write_text(json.dumps({
            "requirements": {
                "REQ-LEGACY-001": {
                    "req_id": "REQ-LEGACY-001",
                    "name": "legacy",
                    "project": "L",
                    "summary": "s",
                    "creator": "c",
                    "status": "APPROVED",
                }
            },
            "active_req_by_user": {},
            "project_groups": {},
            "project_configs": {},
        }, ensure_ascii=False))
        store = JsonStateStore(str(path))
        reqs, _, _, _ = store.load_snapshot()
        loaded = reqs["REQ-LEGACY-001"]
        assert loaded.active_spec_context_token == ""
        assert loaded.spec_context_snapshot_sha == ""
```

- [ ] **Step 2：运行测试确认失败**

```
pytest tests/test_spec_context.py -v
```

预期：前两个测试 `AttributeError`，第三个通过。

- [ ] **Step 3：修改 `models.py`，在 `Requirement` 的 `spec_review_summary` 之后加字段**

找到这一行（约在 `spec_review_summary: str = ""` 之后、`updated_at` 之前）：

```python
    spec_review_summary: str = ""
```

在其下方插入：

```python
    active_spec_context_token: str = ""
    spec_context_snapshot_sha: str = ""
```

- [ ] **Step 4：修改 `store.py` 的 `_requirement_from_payload`**

找到 `spec_review_summary=data.get("spec_review_summary", ""),` 一行，在其之后追加：

```python
            active_spec_context_token=data.get("active_spec_context_token", ""),
            spec_context_snapshot_sha=data.get("spec_context_snapshot_sha", ""),
```

- [ ] **Step 5：运行测试确认通过**

```
pytest tests/test_spec_context.py -v
```

预期：三个测试全部 PASS。

- [ ] **Step 6：提交**

```
git add src/requirement_workflow_v12/models.py src/requirement_workflow_v12/store.py tests/test_spec_context.py
git commit -m "feat: add spec context audit fields to Requirement model"
```

---

## Task 2: GitHubClient 模块

**Files:**
- Create: `src/requirement_workflow_v12/github_client.py`
- Create: `tests/test_github_client.py`

- [ ] **Step 1：写失败测试（解析 repo_url）**

新建 `tests/test_github_client.py`：

```python
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.github_client import (
    GitHubClient,
    GitHubAuthError,
    GitHubNotFoundError,
    GitHubTransientError,
    parse_repo_url,
)


def test_parse_repo_url_https():
    assert parse_repo_url("https://github.com/org/repo") == ("org", "repo")


def test_parse_repo_url_with_dot_git_suffix():
    assert parse_repo_url("https://github.com/org/repo.git") == ("org", "repo")


def test_parse_repo_url_with_trailing_slash():
    assert parse_repo_url("https://github.com/org/repo/") == ("org", "repo")


def test_parse_repo_url_invalid():
    import pytest
    with pytest.raises(ValueError):
        parse_repo_url("not-a-url")
```

- [ ] **Step 2：运行测试确认失败**

```
pytest tests/test_github_client.py -v
```

预期：`ModuleNotFoundError: No module named 'requirement_workflow_v12.github_client'`。

- [ ] **Step 3：创建 `github_client.py` 的解析与异常部分**

```python
from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class GitHubError(Exception):
    """Base exception for GitHub API failures."""


class GitHubAuthError(GitHubError):
    """HTTP 401 / 403 from GitHub."""


class GitHubNotFoundError(GitHubError):
    """HTTP 404 from GitHub — repo or file missing."""


class GitHubTransientError(GitHubError):
    """Network timeout, 5xx, or other recoverable failure."""


@dataclass
class FetchedFile:
    content: str
    commit_sha: str


def parse_repo_url(repo_url: str) -> Tuple[str, str]:
    """Parse https://github.com/<owner>/<repo>[.git][/] into (owner, repo)."""
    if not repo_url.startswith("https://github.com/"):
        raise ValueError(f"Not a GitHub HTTPS URL: {repo_url}")
    tail = repo_url[len("https://github.com/"):].strip("/")
    if tail.endswith(".git"):
        tail = tail[: -len(".git")]
    parts = tail.split("/")
    if len(parts) != 2 or not all(parts):
        raise ValueError(f"Cannot parse owner/repo from: {repo_url}")
    return parts[0], parts[1]


class GitHubClient:
    def __init__(self, token: str, *, timeout: float = 10.0) -> None:
        self._token = token
        self._timeout = timeout

    def fetch_file(self, repo_url: str, path: str, ref: str = "HEAD") -> FetchedFile:
        owner, repo = parse_repo_url(repo_url)
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
        if ref and ref != "HEAD":
            url += f"?ref={ref}"
        req = Request(url, headers={
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "requirement-workflow-coordinator",
        })
        try:
            with urlopen(req, timeout=self._timeout) as resp:
                body = resp.read()
        except HTTPError as exc:
            if exc.code in (401, 403):
                raise GitHubAuthError(f"GitHub auth failed ({exc.code})") from exc
            if exc.code == 404:
                raise GitHubNotFoundError(f"{path} not found in {owner}/{repo}") from exc
            if 500 <= exc.code < 600:
                raise GitHubTransientError(f"GitHub {exc.code}") from exc
            raise GitHubError(f"Unexpected GitHub HTTP {exc.code}") from exc
        except URLError as exc:
            raise GitHubTransientError(f"Network error: {exc}") from exc

        try:
            data = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GitHubError("Invalid JSON from GitHub") from exc

        encoding = data.get("encoding")
        if encoding != "base64":
            raise GitHubError(f"Unsupported encoding: {encoding}")
        content_b64 = data.get("content", "")
        try:
            content = base64.b64decode(content_b64).decode("utf-8")
        except Exception as exc:
            raise GitHubError("Failed to decode file content") from exc
        commit_sha = data.get("sha", "")
        if not commit_sha:
            raise GitHubError("GitHub response missing sha")
        return FetchedFile(content=content, commit_sha=commit_sha)
```

- [ ] **Step 4：运行测试确认解析用例通过**

```
pytest tests/test_github_client.py -v
```

预期：4 个 `parse_repo_url` 测试 PASS。

- [ ] **Step 5：补齐 fetch_file 测试**

追加到 `tests/test_github_client.py`：

```python
import base64
import json as _json
from urllib.error import HTTPError, URLError


def _fake_response(payload: dict):
    ctx = MagicMock()
    ctx.__enter__ = lambda s: MagicMock(read=MagicMock(return_value=_json.dumps(payload).encode("utf-8")))
    ctx.__exit__ = lambda s, *a: False
    return ctx


def test_fetch_file_success():
    client = GitHubClient(token="t")
    payload = {
        "encoding": "base64",
        "content": base64.b64encode(b"hello yaml").decode("ascii"),
        "sha": "abc123",
    }
    with patch("requirement_workflow_v12.github_client.urlopen", return_value=_fake_response(payload)):
        result = client.fetch_file("https://github.com/org/repo", "ARCHITECTURE.yaml")
    assert result.content == "hello yaml"
    assert result.commit_sha == "abc123"


def test_fetch_file_404_raises_not_found():
    import pytest
    client = GitHubClient(token="t")
    with patch(
        "requirement_workflow_v12.github_client.urlopen",
        side_effect=HTTPError(url="u", code=404, msg="nf", hdrs=None, fp=None),
    ):
        with pytest.raises(GitHubNotFoundError):
            client.fetch_file("https://github.com/org/repo", "missing.yaml")


def test_fetch_file_401_raises_auth_error():
    import pytest
    client = GitHubClient(token="t")
    with patch(
        "requirement_workflow_v12.github_client.urlopen",
        side_effect=HTTPError(url="u", code=401, msg="unauth", hdrs=None, fp=None),
    ):
        with pytest.raises(GitHubAuthError):
            client.fetch_file("https://github.com/org/repo", "x.yaml")


def test_fetch_file_5xx_raises_transient():
    import pytest
    client = GitHubClient(token="t")
    with patch(
        "requirement_workflow_v12.github_client.urlopen",
        side_effect=HTTPError(url="u", code=503, msg="down", hdrs=None, fp=None),
    ):
        with pytest.raises(GitHubTransientError):
            client.fetch_file("https://github.com/org/repo", "x.yaml")


def test_fetch_file_network_error_raises_transient():
    import pytest
    client = GitHubClient(token="t")
    with patch(
        "requirement_workflow_v12.github_client.urlopen",
        side_effect=URLError("connection refused"),
    ):
        with pytest.raises(GitHubTransientError):
            client.fetch_file("https://github.com/org/repo", "x.yaml")
```

- [ ] **Step 6：运行全部 github_client 测试**

```
pytest tests/test_github_client.py -v
```

预期：全部 PASS（9 个测试）。

- [ ] **Step 7：提交**

```
git add src/requirement_workflow_v12/github_client.py tests/test_github_client.py
git commit -m "feat: add GitHubClient for fetching ARCHITECTURE.yaml via Contents API"
```

---

## Task 3: SpecContextBuilder 模块

**Files:**
- Create: `src/requirement_workflow_v12/spec_context.py`
- Modify: `tests/test_spec_context.py`

- [ ] **Step 1：追加失败测试到 `tests/test_spec_context.py`**

```python
from unittest.mock import MagicMock

from requirement_workflow_v12.github_client import (
    FetchedFile,
    GitHubAuthError,
    GitHubNotFoundError,
)
from requirement_workflow_v12.project_config import ProjectConfig
from requirement_workflow_v12.spec_context import (
    SpecContextBuilder,
    SpecContextGateError,
    SpecContextMisconfigured,
)


def _make_requirement(status: WorkflowStatus = WorkflowStatus.APPROVED) -> Requirement:
    req = Requirement(req_id="REQ-SC-001", name="n", project="P", summary="s", creator="c")
    req.status = status
    req.document_url = "https://feishu.cn/docx/tok123"
    req.needs_ui = True
    req.hifi_prototype_url = "https://figma.com/prototype"
    req.latest_review_summary = "looks good"
    return req


def _make_service(req: Requirement) -> MagicMock:
    svc = MagicMock()
    svc.get_requirement.return_value = req
    svc.project_configs = {
        "P": ProjectConfig(
            project="P",
            github_repo_url="https://github.com/org/repo",
            tech_stack={},
        )
    }
    return svc


def test_spec_context_build_success():
    req = _make_requirement()
    service = _make_service(req)
    gh = MagicMock()
    gh.fetch_file.return_value = FetchedFile(content="services: []\n", commit_sha="sha-abc")
    builder = SpecContextBuilder(service=service, github_client=gh)

    result = builder.build("REQ-SC-001")

    assert result.context["req_id"] == "REQ-SC-001"
    assert result.context["architecture_yaml"] == "services: []\n"
    assert result.context["architecture_commit_sha"] == "sha-abc"
    assert result.context["requirement_document_url"] == "https://feishu.cn/docx/tok123"
    assert result.context["needs_ui"] is True
    assert result.context["design_system_snapshot"] is None
    assert result.context["github_repo_url"] == "https://github.com/org/repo"
    assert result.context_token.startswith("spec_ctx_REQ-SC-001_")
    assert req.active_spec_context_token == result.context_token


def test_spec_context_rejects_non_approved():
    import pytest
    req = _make_requirement(status=WorkflowStatus.DRAFTING)
    service = _make_service(req)
    builder = SpecContextBuilder(service=service, github_client=MagicMock())

    with pytest.raises(SpecContextGateError):
        builder.build("REQ-SC-001")


def test_spec_context_rejects_spec_locked():
    import pytest
    req = _make_requirement(status=WorkflowStatus.SPEC_LOCKED)
    service = _make_service(req)
    builder = SpecContextBuilder(service=service, github_client=MagicMock())

    with pytest.raises(SpecContextGateError):
        builder.build("REQ-SC-001")


def test_spec_context_allows_spec_drafting():
    req = _make_requirement(status=WorkflowStatus.SPEC_DRAFTING)
    service = _make_service(req)
    gh = MagicMock()
    gh.fetch_file.return_value = FetchedFile(content="x", commit_sha="s")
    builder = SpecContextBuilder(service=service, github_client=gh)
    result = builder.build("REQ-SC-001")
    assert result.context_token


def test_spec_context_missing_project_config():
    import pytest
    req = _make_requirement()
    service = _make_service(req)
    service.project_configs = {}
    builder = SpecContextBuilder(service=service, github_client=MagicMock())
    with pytest.raises(SpecContextMisconfigured):
        builder.build("REQ-SC-001")


def test_spec_context_missing_github_repo_url():
    import pytest
    req = _make_requirement()
    service = _make_service(req)
    service.project_configs["P"] = ProjectConfig(project="P", github_repo_url="", tech_stack={})
    builder = SpecContextBuilder(service=service, github_client=MagicMock())
    with pytest.raises(SpecContextMisconfigured):
        builder.build("REQ-SC-001")


def test_spec_context_unknown_req():
    import pytest
    service = MagicMock()
    service.get_requirement.return_value = None
    builder = SpecContextBuilder(service=service, github_client=MagicMock())
    with pytest.raises(ValueError):
        builder.build("REQ-UNKNOWN")


def test_spec_context_token_overwrites_previous():
    req = _make_requirement()
    req.active_spec_context_token = "old_token"
    service = _make_service(req)
    gh = MagicMock()
    gh.fetch_file.return_value = FetchedFile(content="x", commit_sha="s")
    builder = SpecContextBuilder(service=service, github_client=gh)
    result = builder.build("REQ-SC-001")
    assert req.active_spec_context_token == result.context_token
    assert req.active_spec_context_token != "old_token"
```

- [ ] **Step 2：运行测试确认失败**

```
pytest tests/test_spec_context.py -v
```

预期：`ModuleNotFoundError` 或 `ImportError`。

- [ ] **Step 3：创建 `spec_context.py`**

```python
from __future__ import annotations

import secrets
import time
from dataclasses import dataclass

from .github_client import GitHubClient
from .models import Requirement, WorkflowStatus


ARCHITECTURE_YAML_DEFAULT_PATH = "ARCHITECTURE.yaml"

SPEC_CONTEXT_ALLOWED_STATUSES = {
    WorkflowStatus.APPROVED,
    WorkflowStatus.SPEC_DRAFTING,
}


class SpecContextGateError(Exception):
    """Requirement is not in a state that permits spec-context retrieval."""

    def __init__(self, message: str, current_status: str) -> None:
        super().__init__(message)
        self.current_status = current_status


class SpecContextMisconfigured(Exception):
    """Project lacks configuration required to serve spec-context."""


@dataclass
class SpecContextResult:
    context: dict
    context_token: str


class SpecContextBuilder:
    def __init__(
        self,
        service,
        github_client: GitHubClient,
        *,
        architecture_yaml_path: str = ARCHITECTURE_YAML_DEFAULT_PATH,
    ) -> None:
        self._service = service
        self._github = github_client
        self._arch_path = architecture_yaml_path

    def build(self, req_id: str) -> SpecContextResult:
        requirement = self._service.get_requirement(req_id)
        if requirement is None:
            raise ValueError(f"未知需求：{req_id}")

        if requirement.status not in SPEC_CONTEXT_ALLOWED_STATUSES:
            raise SpecContextGateError(
                f"当前状态 {requirement.status.value} 不允许获取 spec-context",
                current_status=requirement.status.value,
            )

        project_cfg = self._service.project_configs.get(requirement.project)
        if project_cfg is None:
            raise SpecContextMisconfigured(
                f"项目 {requirement.project} 未完成 onboarding"
            )
        if not project_cfg.github_repo_url:
            raise SpecContextMisconfigured(
                f"项目 {requirement.project} 缺少 github_repo_url"
            )

        fetched = self._github.fetch_file(project_cfg.github_repo_url, self._arch_path)

        context_token = self._mint_token(req_id)
        requirement.active_spec_context_token = context_token

        context = {
            "req_id": requirement.req_id,
            "name": requirement.name,
            "project": requirement.project,
            "status": requirement.status.value,
            "needs_ui": requirement.needs_ui,
            "hifi_prototype_url": requirement.hifi_prototype_url,
            "design_system_snapshot": None,
            "requirement_document_url": requirement.document_url,
            "spec_document_url": requirement.spec_document_url,
            "spec_document_id": requirement.spec_document_id,
            "architecture_yaml": fetched.content,
            "architecture_commit_sha": fetched.commit_sha,
            "github_repo_url": project_cfg.github_repo_url,
            "latest_review_summary": requirement.latest_review_summary,
        }
        return SpecContextResult(context=context, context_token=context_token)

    @staticmethod
    def _mint_token(req_id: str) -> str:
        return f"spec_ctx_{req_id}_{int(time.time())}_{secrets.token_hex(4)}"
```

- [ ] **Step 4：运行测试确认全部通过**

```
pytest tests/test_spec_context.py -v
```

预期：11 个测试全部 PASS。

- [ ] **Step 5：提交**

```
git add src/requirement_workflow_v12/spec_context.py tests/test_spec_context.py
git commit -m "feat: add SpecContextBuilder for spec-context payload assembly"
```

---

## Task 4: spec-context HTTP 端点

**Files:**
- Modify: `src/requirement_workflow_v12/service_app.py`
- Modify: `tests/test_spec_context.py`

- [ ] **Step 1：追加集成测试**

在 `tests/test_spec_context.py` 末尾追加：

```python
import hashlib
import hmac
import json as _jsonmod
import time as _timemod
from unittest.mock import patch


def _sign(secret: str, timestamp: str, body: bytes) -> str:
    return hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()


def _make_app_with_req():
    from requirement_workflow_v12.service_app import WorkflowApp
    from requirement_workflow_v12.config import Settings

    settings = Settings(openclaw_callback_secret="shh")
    app = WorkflowApp(settings=settings)
    req = _make_requirement()
    app.service.requirements[req.req_id] = req
    app.service.project_configs["P"] = ProjectConfig(
        project="P", github_repo_url="https://github.com/org/repo", tech_stack={}
    )
    return app, req


def _post_spec_context(app, req_id: str, *, sign: bool = True):
    body = _jsonmod.dumps({"req_id": req_id}).encode()
    headers = {}
    if sign:
        ts = str(int(_timemod.time()))
        headers["X-OpenClaw-Timestamp"] = ts
        headers["X-OpenClaw-Signature"] = _sign("shh", ts, body)
    return app.handle_openclaw_spec_context_query(body, headers=headers)


def test_spec_context_endpoint_rejects_missing_auth():
    app, _ = _make_app_with_req()
    status, _ = _post_spec_context(app, "REQ-SC-001", sign=False)
    assert status == 401


def test_spec_context_endpoint_unknown_req_returns_404():
    app, _ = _make_app_with_req()
    status, payload = _post_spec_context(app, "REQ-MISSING")
    assert status == 404
    assert payload["error"] == "not_found"


def test_spec_context_endpoint_invalid_state_returns_409():
    app, req = _make_app_with_req()
    req.status = WorkflowStatus.DRAFTING
    status, payload = _post_spec_context(app, req.req_id)
    assert status == 409
    assert payload["error"] == "invalid_state"


def test_spec_context_endpoint_success():
    app, req = _make_app_with_req()
    with patch.object(app.github_client, "fetch_file",
                      return_value=FetchedFile(content="services: []\n", commit_sha="sha-xyz")):
        status, payload = _post_spec_context(app, req.req_id)
    assert status == 200
    assert payload["ok"] is True
    assert payload["context"]["architecture_yaml"] == "services: []\n"
    assert payload["context"]["architecture_commit_sha"] == "sha-xyz"
    assert payload["context_token"].startswith("spec_ctx_")
    assert req.active_spec_context_token == payload["context_token"]


def test_spec_context_endpoint_github_auth_failure_returns_502():
    app, _ = _make_app_with_req()
    with patch.object(app.github_client, "fetch_file", side_effect=GitHubAuthError("bad token")):
        status, payload = _post_spec_context(app, "REQ-SC-001")
    assert status == 502
    assert payload["error"] == "github_auth_failed"


def test_spec_context_endpoint_github_missing_file_returns_502():
    app, _ = _make_app_with_req()
    with patch.object(app.github_client, "fetch_file", side_effect=GitHubNotFoundError("nf")):
        status, payload = _post_spec_context(app, "REQ-SC-001")
    assert status == 502
    assert payload["error"] == "architecture_yaml_missing"


def test_spec_context_endpoint_misconfigured_returns_500():
    app, _ = _make_app_with_req()
    app.service.project_configs["P"].github_repo_url = ""
    status, payload = _post_spec_context(app, "REQ-SC-001")
    assert status == 500
    assert payload["error"] == "project_misconfigured"
```

- [ ] **Step 2：运行测试确认失败**

```
pytest tests/test_spec_context.py -v -k endpoint
```

预期：全部失败（`handle_openclaw_spec_context_query` / `app.github_client` 未定义）。

- [ ] **Step 3：修改 `service_app.py` — 初始化 GitHubClient 与 SpecContextBuilder**

在 `WorkflowApp.__init__` 中（找到 self.service 初始化之后的位置），追加：

```python
        import os as _os
        from .github_client import GitHubClient
        from .spec_context import SpecContextBuilder

        self.github_client = GitHubClient(token=_os.environ.get("GITHUB_TOKEN", ""))
        self._spec_context_builder = SpecContextBuilder(
            service=self.service,
            github_client=self.github_client,
            architecture_yaml_path=_os.environ.get("ARCHITECTURE_YAML_PATH", "ARCHITECTURE.yaml"),
        )
```

- [ ] **Step 4：修改 `service_app.py` — 新增 handler 方法**

在 `handle_openclaw_requirement_context_query` 方法之后、`handle_openclaw_spec_turn_callback` 方法之前，插入：

```python
    def handle_openclaw_spec_context_query(
        self,
        raw_body: bytes,
        *,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, object]]:
        from .github_client import (
            GitHubAuthError,
            GitHubNotFoundError,
            GitHubTransientError,
        )
        from .spec_context import SpecContextGateError, SpecContextMisconfigured

        auth_error = self._validate_openclaw_callback_auth(raw_body, headers=headers)
        if auth_error is not None:
            return auth_error
        try:
            payload = json.loads(raw_body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return 400, {"error": "invalid_json"}

        req_id = str(payload.get("req_id", "")).strip()
        if not req_id:
            return 400, {"error": "invalid_payload", "message": "req_id 为必填字段。"}

        if not self.github_client._token:  # GITHUB_TOKEN not configured
            return 500, {"error": "github_auth_missing", "message": "Coordinator 未配置 GITHUB_TOKEN。"}

        LOGGER.info("Received spec-context query req_id=%s", req_id)

        try:
            result = self._spec_context_builder.build(req_id)
        except ValueError as exc:
            return 404, {"error": "not_found", "message": str(exc)}
        except SpecContextGateError as exc:
            return 409, {
                "error": "invalid_state",
                "message": str(exc),
                "current_status": exc.current_status,
            }
        except SpecContextMisconfigured as exc:
            return 500, {"error": "project_misconfigured", "message": str(exc)}
        except GitHubAuthError as exc:
            LOGGER.warning("GitHub auth failed for spec-context req_id=%s: %s", req_id, exc)
            return 502, {"error": "github_auth_failed", "message": str(exc)}
        except GitHubNotFoundError as exc:
            LOGGER.error("ARCHITECTURE.yaml missing for spec-context req_id=%s: %s", req_id, exc)
            return 502, {"error": "architecture_yaml_missing", "message": str(exc)}
        except GitHubTransientError as exc:
            LOGGER.warning("GitHub transient failure for spec-context req_id=%s: %s", req_id, exc)
            return 503, {"error": "github_transient", "message": str(exc)}
        except Exception as exc:
            LOGGER.exception("Unexpected failure handling spec-context req_id=%s", req_id)
            return 500, {"error": "spec_context_failed", "message": str(exc)}

        self._save_state()

        LOGGER.info(
            "Spec-context served req_id=%s commit_sha=%s",
            req_id,
            result.context["architecture_commit_sha"],
        )
        return 200, {
            "ok": True,
            "context": result.context,
            "context_token": result.context_token,
            "expires_hint": "valid until SPEC_LOCKED or a newer token is issued",
        }
```

- [ ] **Step 5：修改 `service_app.py` — 注册路由**

找到路由分发（约在 `elif self.path == "/queries/openclaw/requirement-context":` 附近），在其后紧挨着插入：

```python
                elif self.path == "/queries/openclaw/spec-context":
                    status, payload = app.handle_openclaw_spec_context_query(raw_body, headers=headers)
```

- [ ] **Step 6：运行集成测试确认通过**

```
pytest tests/test_spec_context.py -v
```

预期：全部 PASS。

- [ ] **Step 7：回归全量测试，确保未破坏既有行为**

```
pytest tests/ -v
```

预期：全量 PASS。

- [ ] **Step 8：提交**

```
git add src/requirement_workflow_v12/service_app.py tests/test_spec_context.py
git commit -m "feat: add /queries/openclaw/spec-context endpoint"
```

---

## Task 5: spec-turn callback 增加 token + sha 校验

**Files:**
- Modify: `src/requirement_workflow_v12/service_app.py:984-1074`
- Modify: `tests/test_spec_context.py`

- [ ] **Step 1：追加失败测试**

在 `tests/test_spec_context.py` 末尾追加：

```python
def _post_spec_turn(app, body_dict: dict, *, sign: bool = True):
    body = _jsonmod.dumps(body_dict).encode()
    headers = {}
    if sign:
        ts = str(int(_timemod.time()))
        headers["X-OpenClaw-Timestamp"] = ts
        headers["X-OpenClaw-Signature"] = _sign("shh", ts, body)
    return app.handle_openclaw_spec_turn_callback(body, headers=headers)


def test_spec_start_rejects_missing_context_token():
    app, req = _make_app_with_req()
    req.active_spec_context_token = "spec_ctx_REQ-SC-001_1_aaaa"
    status, payload = _post_spec_turn(app, {
        "req_id": req.req_id, "event": "spec_start", "summary": "go",
    })
    assert status == 400
    assert payload["error"] == "missing_context_token"


def test_spec_start_rejects_stale_context_token():
    app, req = _make_app_with_req()
    req.active_spec_context_token = "spec_ctx_CURRENT"
    status, payload = _post_spec_turn(app, {
        "req_id": req.req_id, "event": "spec_start", "summary": "go",
        "context_token": "spec_ctx_OLD",
    })
    assert status == 409
    assert payload["error"] == "stale_context_token"


def test_spec_submit_rejects_missing_commit_sha():
    app, req = _make_app_with_req()
    req.status = WorkflowStatus.SPEC_DRAFTING
    req.active_spec_context_token = "tok"
    status, payload = _post_spec_turn(app, {
        "req_id": req.req_id, "event": "spec_submit", "summary": "done",
        "context_token": "tok",
    })
    assert status == 400
    assert payload["error"] == "missing_commit_sha"


def test_spec_submit_writes_sha_and_clears_token():
    app, req = _make_app_with_req()
    req.status = WorkflowStatus.SPEC_DRAFTING
    req.active_spec_context_token = "tok"
    status, payload = _post_spec_turn(app, {
        "req_id": req.req_id, "event": "spec_submit", "summary": "done",
        "context_token": "tok",
        "architecture_commit_sha": "sha-locked",
    })
    assert status == 200
    assert req.spec_context_snapshot_sha == "sha-locked"
    assert req.active_spec_context_token == ""
    assert req.status == WorkflowStatus.SPEC_LOCKED
```

- [ ] **Step 2：运行测试确认失败**

```
pytest tests/test_spec_context.py -v -k "spec_start_rejects or spec_submit"
```

预期：4 个失败（token / sha 校验未实现）。

- [ ] **Step 3：修改 `handle_openclaw_spec_turn_callback`**

在该方法内，`requirement = self.service.get_requirement(req_id)` 之后、`if event == "spec_start":` 之前，插入 token + sha 提取与校验：

```python
        context_token = str(payload.get("context_token", "")).strip()
        architecture_commit_sha = str(payload.get("architecture_commit_sha", "")).strip()

        if not context_token:
            return 400, {
                "error": "missing_context_token",
                "message": "必须先调 /queries/openclaw/spec-context 获取 context_token。",
            }
        if (
            requirement.active_spec_context_token
            and context_token != requirement.active_spec_context_token
        ):
            return 409, {
                "error": "stale_context_token",
                "message": "context_token 已过期，请重新调 spec-context。",
            }
```

然后在 `if event == "spec_submit":` 分支里，`if requirement.status != WorkflowStatus.SPEC_DRAFTING:` 校验之后、`try: requirement = self.service.submit_spec_submit(...)` 之前，插入：

```python
            if not architecture_commit_sha:
                return 400, {
                    "error": "missing_commit_sha",
                    "message": "spec_submit 必须回传 architecture_commit_sha。",
                }
```

在 `self._save_state()` 之前（spec_submit 分支内，`submit_spec_submit` 调用之后），追加：

```python
            requirement.spec_context_snapshot_sha = architecture_commit_sha
            requirement.active_spec_context_token = ""
```

- [ ] **Step 4：运行全量测试**

```
pytest tests/ -v
```

预期：全部 PASS。如有旧测试因为缺少 `context_token` 字段失败，按下一步处理。

- [ ] **Step 5：修复旧 spec-turn 测试（如需要）**

如果旧测试（`test_spec_stage.py` 等）直接构造 spec_start/submit payload 却没有 context_token，需要给它们加上 token 并预设 requirement.active_spec_context_token。对每个失败用例：
1. 在断言前设置 `req.active_spec_context_token = "test_tok"`
2. payload 加 `"context_token": "test_tok"`
3. spec_submit payload 额外加 `"architecture_commit_sha": "test_sha"`

再跑：

```
pytest tests/ -v
```

预期：全部 PASS。

- [ ] **Step 6：提交**

```
git add src/requirement_workflow_v12/service_app.py tests/test_spec_context.py tests/test_spec_stage.py
git commit -m "feat: enforce context_token and commit_sha in spec-turn callback"
```

---

## Task 6: send_openclaw_callback.py CLI 扩展

**Files:**
- Modify: `scripts/send_openclaw_callback.py`

- [ ] **Step 1：在 `CONTEXT_QUERY_ENDPOINT` 常量之后追加新端点常量**

```python
SPEC_CONTEXT_QUERY_ENDPOINT = "/queries/openclaw/spec-context"
```

- [ ] **Step 2：添加 payload 构造函数**

在 `build_context_query_payload` 之后：

```python
def build_spec_context_query_payload(args: argparse.Namespace) -> Dict[str, Any]:
    return {"req_id": args.req_id}
```

- [ ] **Step 3：修改 `build_spec_start_payload` / `build_spec_submit_payload` 支持新参数**

替换 `build_spec_start_payload` 为：

```python
def build_spec_start_payload(args: argparse.Namespace) -> Dict[str, Any]:
    payload = {
        "req_id": args.req_id,
        "event": "spec_start",
        "summary": args.summary,
    }
    if getattr(args, "context_token", None):
        payload["context_token"] = args.context_token
    if getattr(args, "architecture_commit_sha", None):
        payload["architecture_commit_sha"] = args.architecture_commit_sha
    return payload
```

替换 `build_spec_submit_payload` 为：

```python
def build_spec_submit_payload(args: argparse.Namespace) -> Dict[str, Any]:
    payload = {
        "req_id": args.req_id,
        "event": "spec_submit",
        "summary": args.summary,
        "spec_document_url": args.spec_document_url or "",
    }
    if getattr(args, "context_token", None):
        payload["context_token"] = args.context_token
    if getattr(args, "architecture_commit_sha", None):
        payload["architecture_commit_sha"] = args.architecture_commit_sha
    return payload
```

- [ ] **Step 4：在 argparse 子命令注册处新增 `spec-context` 子命令，并给 `spec-start` / `spec-submit` 加新参数**

找到定义 `spec-start` 子命令的位置，为其 `add_argument` 追加：

```python
    spec_start_parser.add_argument("--context-token", default=None)
    spec_start_parser.add_argument("--architecture-commit-sha", default=None)
```

对 `spec-submit` 子命令同样追加两行。

在 `fetch-context` 子命令定义之后，新增 `spec-context` 子命令：

```python
    spec_context_parser = subparsers.add_parser("spec-context", help="query spec-context for a requirement")
    spec_context_parser.add_argument("--req-id", required=True)
```

- [ ] **Step 5：在命令分发逻辑中添加 spec-context 路由**

找到类似 `elif args.command == "fetch-context":` 的分支，后面加：

```python
    elif args.command == "spec-context":
        payload = build_spec_context_query_payload(args)
        endpoint = SPEC_CONTEXT_QUERY_ENDPOINT
```

- [ ] **Step 6：冒烟测试 — 启动一个临时 WorkflowApp 验证脚本能发出请求**

创建临时测试脚本 `/tmp/smoke_spec_context.py`：

```python
import subprocess
import sys
out = subprocess.run(
    [sys.executable, "scripts/send_openclaw_callback.py", "--help"],
    capture_output=True, text=True,
)
assert out.returncode == 0
assert "spec-context" in out.stdout
print("OK")
```

运行：

```
python3 /tmp/smoke_spec_context.py
```

预期：打印 `OK`。

- [ ] **Step 7：提交**

```
git add scripts/send_openclaw_callback.py
git commit -m "feat: add spec-context subcommand and context_token flags to callback CLI"
```

---

## Task 7: spec-author SKILL.md 改写

**Files:**
- Modify: `docs/agents/spec-author/SKILL.md`

- [ ] **Step 1：重写 Step 1**

用以下内容替换整个 `## 启动流程` 节（从 "## 启动流程" 到 "**Step 2**" 的上一行）：

```markdown
## 启动流程

收到包含「请开始 Spec 撰写 REQ-xxx」的消息时启动。

**Step 1**：调 `/queries/openclaw/spec-context` 拉取项目级上下文

```bash
python3 /home/admin/.openclaw/bin/send_openclaw_callback.py \
  --base-url "${COORDINATOR_BASE_URL:-http://127.0.0.1:8004}" \
  --secret "${OPENCLAW_CALLBACK_SECRET:-}" \
  --req-id "{req_id}" \
  spec-context
```

从响应中**必须**记录以下字段供后续步骤使用：

- `context_token`：所有后续 spec-turn callback 必须回传此 token，否则会被 Coordinator 拒绝
- `context.architecture_commit_sha`：Spec 提交时必须原样回传
- `context.requirement_document_url`：**唯一**允许的需求文档来源
- `context.architecture_yaml`：项目架构快照原文，用于撰写 8.2「项目级上下文消费声明」子节
- `context.needs_ui` / `context.design_system_snapshot`：UI 约束判断依据
- `context.spec_document_url` / `context.spec_document_id`：若非空，说明已执行过 spec_start，断点续写

响应结构示例：

```json
{
  "ok": true,
  "context": {
    "req_id": "REQ-xxx",
    "status": "APPROVED",
    "requirement_document_url": "https://feishu.cn/docx/...",
    "architecture_yaml": "services: [...]\n...",
    "architecture_commit_sha": "abc123",
    "needs_ui": true,
    "design_system_snapshot": null,
    "spec_document_url": "",
    "spec_document_id": ""
  },
  "context_token": "spec_ctx_REQ-xxx_1700000000_a8f2"
}
```

⚠️ **失败处理**：

- `status=409 invalid_state` → 需求不在可写 Spec 的状态，向用户报错并停止
- `status=502 architecture_yaml_missing` → 项目未跑 bootstrap，向用户报错并停止
- `status=502/503 github_*` → 稍后重试，不得绕过端点直读 GitHub

**Step 1b**：根据 `context.status` 决定是否调 spec_start

- **若 `status == "APPROVED"` 且 `context.spec_document_url` 为空**：调 spec_start

```bash
python3 /home/admin/.openclaw/bin/send_openclaw_callback.py \
  --base-url "${COORDINATOR_BASE_URL:-http://127.0.0.1:8004}" \
  --secret "${OPENCLAW_CALLBACK_SECRET:-}" \
  --req-id "{req_id}" \
  spec-start \
  --summary "开始 Spec 撰写" \
  --context-token "{context_token}" \
  --architecture-commit-sha "{architecture_commit_sha}"
```

  响应返回 `spec_document_id` / `spec_document_url`，记录备用。

- **若 `status == "SPEC_DRAFTING"`（断点续写）**：跳过 spec_start，直接用 `context.spec_document_id` / `context.spec_document_url`。
```

- [ ] **Step 2：Step 2 仅调整文字，明确要求使用 spec-context 返回的 URL**

替换现有 Step 2 整段为：

```markdown
**Step 2**：使用 `feishu_fetch_doc` 读取需求文档。

- doc_token 必须从 Step 1 响应的 `context.requirement_document_url` 中提取
- **禁止**使用其他来源（聊天历史、用户提供的 URL、搜索结果）的 doc_token
- **禁止**调用 `feishu_fetch_doc` 读取非需求文档的飞书文档

提取完成的 8 字段内容用于后续 Spec 撰写。
```

- [ ] **Step 3：Step 4 spec_submit 增加 token + sha 回传要求**

替换原 Step 4：

```markdown
**Step 4**：9 节均完成后调 spec_submit callback：

```bash
python3 /home/admin/.openclaw/bin/send_openclaw_callback.py \
  --base-url "${COORDINATOR_BASE_URL:-http://127.0.0.1:8004}" \
  --secret "${OPENCLAW_CALLBACK_SECRET:-}" \
  --req-id "{req_id}" \
  spec-submit \
  --summary "Spec 初稿完成，9节均已填写" \
  --spec-document-url "{spec_document_url}" \
  --context-token "{context_token}" \
  --architecture-commit-sha "{architecture_commit_sha}"
```

⚠️ `--context-token` 和 `--architecture-commit-sha` 必须分别等于 Step 1 拿到的同名字段。若缺失，Coordinator 返回 `missing_context_token` / `missing_commit_sha`。
```

- [ ] **Step 4：在「不允许的行为」节追加两条**

在现有列表末尾追加：

```markdown
- **不得绕过 spec-context 端点**：所有需求文档内容必须经由 Step 1 的响应取 URL，禁止直接向用户/聊天历史索要 doc_token
- **不得伪造 context_token / architecture_commit_sha**：必须原样回传 Step 1 响应里的字段
- **不得使用 `feishu_fetch_doc` 读取项目 ARCHITECTURE.yaml**：架构原文由 Coordinator 从 GitHub 拉取并通过 `context.architecture_yaml` 返回
```

- [ ] **Step 5：验证 SKILL.md 可读性**

```
python3 -c "import pathlib; print(pathlib.Path('docs/agents/spec-author/SKILL.md').read_text()[:500])"
```

预期：前 500 字符打印成功，无语法错误。

- [ ] **Step 6：提交**

```
git add docs/agents/spec-author/SKILL.md
git commit -m "docs: rewrite spec-author SKILL to enforce spec-context gate"
```

---

## Task 8: 端到端冒烟验证

**Files:**
- Create: `scripts/run_spec_context_smoke.py`

- [ ] **Step 1：创建冒烟脚本**

```python
#!/usr/bin/env python3
"""Local smoke test for spec-context endpoint.

Prereq: GITHUB_TOKEN set in env; a project 'P' onboarded with a real
github_repo_url containing ARCHITECTURE.yaml; a requirement in APPROVED.
"""
import os
import sys
import subprocess

req_id = os.environ.get("SMOKE_REQ_ID")
if not req_id:
    print("Set SMOKE_REQ_ID to an APPROVED requirement id", file=sys.stderr)
    sys.exit(1)

out = subprocess.run([
    sys.executable, "scripts/send_openclaw_callback.py",
    "--base-url", os.environ.get("COORDINATOR_BASE_URL", "http://127.0.0.1:8004"),
    "--secret", os.environ["OPENCLAW_CALLBACK_SECRET"],
    "--req-id", req_id,
    "spec-context",
], capture_output=True, text=True)

print("STDOUT:", out.stdout)
print("STDERR:", out.stderr)
if out.returncode != 0:
    sys.exit(out.returncode)

import json
# Script prints JSON response line — parse last line as JSON
payload = json.loads(out.stdout.strip().splitlines()[-1])
assert payload.get("ok") is True, f"spec-context failed: {payload}"
assert "context_token" in payload
assert payload["context"]["architecture_yaml"]
assert payload["context"]["architecture_commit_sha"]
print(f"OK — token={payload['context_token']} sha={payload['context']['architecture_commit_sha'][:8]}")
```

- [ ] **Step 2：在本地启动 Coordinator（另一个终端）**

```
python3 -m requirement_workflow_v12.service_app
```

- [ ] **Step 3：运行冒烟脚本**

```
GITHUB_TOKEN=ghp_xxx \
OPENCLAW_CALLBACK_SECRET=... \
SMOKE_REQ_ID=REQ-xxx \
python3 scripts/run_spec_context_smoke.py
```

预期：打印 `OK — token=... sha=...`。

如 GitHub 凭证或 req_id 不可用，记录为"需要在远端部署后跑"，提交冒烟脚本但不阻塞计划完成。

- [ ] **Step 4：提交**

```
git add scripts/run_spec_context_smoke.py
git commit -m "chore: add local smoke script for spec-context endpoint"
```

---

## Self-Review Checklist

- [x] Spec §3.1 组件（github_client / spec_context / models / store / service_app / SKILL / CLI）全部对应到 Task 1-7
- [x] Spec §3.2 数据流在 Task 3 + Task 4 覆盖
- [x] Spec §3.3 三层防绕过：文字约束（Task 7）/ token 握手（Task 4+5）/ sha 回证（Task 5）
- [x] Spec §4 错误映射：spec-context 错误（Task 4）/ spec-turn 新错误（Task 5）全部测试覆盖
- [x] Spec §5 状态门禁：Task 3 的 `SPEC_CONTEXT_ALLOWED_STATUSES` 实现
- [x] Spec §7 测试策略：单元测试（Task 2/3）+ 集成测试（Task 4/5）+ 回归（Task 4 Step 7）+ 冒烟（Task 8）
- [x] 无占位符 / TODO
- [x] 字段 / 方法名跨 task 一致：`active_spec_context_token` / `spec_context_snapshot_sha` / `SpecContextBuilder.build` / `GitHubClient.fetch_file`
- [x] 每个 task 都以提交结尾，符合 frequent commits 原则
