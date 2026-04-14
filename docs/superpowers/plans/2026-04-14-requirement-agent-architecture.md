# 需求构造 Agent 架构优化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将文档内容写入职责从 Coordinator 移交给 Author Agent，瘦身 Coordinator 至纯状态机，更新 Agent 协议（加 `completed_fields` + `field_hints`），删除 `RequirementDocumentCompiler` 和 `RequirementDocument`，输出 Author/Review Agent SKILL.md。

**Architecture:** Coordinator 只做状态转移 + 飞书通知，不持有文档内容；Author Agent 通过 `feishu_doc` skill 直写飞书文档；Agent 与 Coordinator 通过稳定 HTTP 接口对接（callback + context query）。

**Tech Stack:** Python 3.11, pytest, OpenClaw SKILL.md

---

## 文件结构

| 操作 | 文件 | 变更 |
|---|---|---|
| 修改 | `src/requirement_workflow_v12/protocols.py` | `AgentAuthorEventPayload` 增加 `completed_fields` |
| 修改 | `src/requirement_workflow_v12/coordinator_service.py` | 移除 compiler 依赖，简化 `handle_author_turn`，`get_agent_requirement_context` 加 `field_hints` |
| 修改 | `src/requirement_workflow_v12/service_app.py` | 简化 `_handle_author_turn` DM handler，移除 `sync_requirement_document` 调用 |
| 修改 | `src/requirement_workflow_v12/models.py` | 移除 `RequirementDocument`，移除 `Requirement.document`，移除 `DiscussionTurn.normalized_updates` |
| 修改 | `src/requirement_workflow_v12/store.py` | 移除 `_document_from_payload`，移除 `normalized_updates` 反序列化 |
| 修改 | `src/requirement_workflow_v12/feishu_gateway.py` | 移除 `sync_requirement_document` 及其辅助方法 |
| 修改 | `src/requirement_workflow_v12/__init__.py` | 移除 `RequirementDocument`、`RequirementDocumentCompiler` 导出 |
| **删除** | `src/requirement_workflow_v12/compiler.py` | 整文件删除 |
| 新建 | `docs/agents/requirement-author/SKILL.md` | Author Agent skill 定义 |
| 新建 | `docs/agents/requirement-reviewer/SKILL.md` | Review Agent skill 定义 |
| 修改 | `tests/test_requirement_workflow_v12.py` | 更新断言，移除 document.sections 引用，移除 sync_requirement_document stub |
| 新建 | `tests/test_agent_protocol.py` | 新增 `completed_fields` 和 `field_hints` 测试 |

---

## Task 1：Author Callback 协议扩展（加 `completed_fields`）

**Files:**
- Modify: `src/requirement_workflow_v12/protocols.py`
- Modify: `src/requirement_workflow_v12/coordinator_service.py:369-400`
- Create: `tests/test_agent_protocol.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_agent_protocol.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.coordinator_service import CoordinatorService
from requirement_workflow_v12.protocols import AgentAuthorEventPayload
from requirement_workflow_v12 import CreationRequest, WorkflowStatus


def _make_service_with_drafting_req():
    svc = CoordinatorService()
    resp = svc.create_requirement_from_group(
        CreationRequest(
            project="PROTO",
            name="协议测试",
            summary="验证 completed_fields 协议",
            creator="tester",
            creator_user_id="u1",
            creation_chat_id="c1",
        )
    )
    req = svc.get_requirement(resp.req_id)
    assert req is not None
    svc.handoff_to_author(req)
    return svc, resp.req_id


def test_author_callback_uses_completed_fields():
    svc, req_id = _make_service_with_drafting_req()
    svc.submit_author_event_payload(
        AgentAuthorEventPayload(
            req_id=req_id,
            event="author_submit",
            summary="完成了问题描述和使用场景",
            completed_fields=["问题描述", "使用场景"],
            iteration_round=1,
        )
    )
    req = svc.get_requirement(req_id)
    assert req is not None
    assert req.status == WorkflowStatus.AI_REVIEWING
    assert "问题描述" in req.completed_fields
    assert "使用场景" in req.completed_fields
    assert "输入" not in req.completed_fields


def test_author_callback_without_completed_fields_is_accepted():
    """Backward compat: completed_fields 为空列表时不报错."""
    svc, req_id = _make_service_with_drafting_req()
    svc.submit_author_event_payload(
        AgentAuthorEventPayload(
            req_id=req_id,
            event="author_submit",
            summary="完成了全部字段",
            completed_fields=[],
            iteration_round=2,
        )
    )
    req = svc.get_requirement(req_id)
    assert req is not None
    assert req.status == WorkflowStatus.AI_REVIEWING
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /Users/daxin/work/requirement-workflow-feishu
python -m pytest tests/test_agent_protocol.py -v
```

Expected: FAIL — `AgentAuthorEventPayload` 没有 `completed_fields` 字段

- [ ] **Step 3: 更新 `AgentAuthorEventPayload`**

文件：`src/requirement_workflow_v12/protocols.py`，找到 `AgentAuthorEventPayload`：

```python
@dataclass
class AgentAuthorEventPayload:
    req_id: str
    event: str
    summary: str
    document_url: str = ""
    document_version: str = ""
    iteration_round: int | None = None
    completed_fields: list[str] = field(default_factory=list)
```

注意：`field` 来自 `dataclasses`，确认顶部已有 `from dataclasses import dataclass, field`。若无则添加。

- [ ] **Step 4: 更新 `submit_author_event_payload` 使用 `completed_fields`**

文件：`src/requirement_workflow_v12/coordinator_service.py`，找到 `submit_author_event_payload` 方法，在 `requirement.latest_writeback_at = utc_now()` 前添加：

```python
        if payload.completed_fields:
            requirement.completed_fields = list(payload.completed_fields)
            requirement.pending_fields = [
                f for f in DISCUSSION_FIELDS
                if f not in requirement.completed_fields
            ]
            if requirement.pending_fields:
                requirement.current_discussion_field = requirement.pending_fields[0]
```

- [ ] **Step 5: 运行测试，确认通过**

```bash
python -m pytest tests/test_agent_protocol.py -v
```

Expected: 2 passed

- [ ] **Step 6: 全量回归**

```bash
python -m pytest tests/ -q
```

Expected: 55+ passed, 1 warning

- [ ] **Step 7: Commit**

```bash
git add src/requirement_workflow_v12/protocols.py src/requirement_workflow_v12/coordinator_service.py tests/test_agent_protocol.py
git commit -m "feat: add completed_fields to author callback protocol"
```

---

## Task 2：Context Query 增加 `field_hints`

**Files:**
- Modify: `src/requirement_workflow_v12/coordinator_service.py:460-530`
- Modify: `tests/test_agent_protocol.py`

- [ ] **Step 1: 写失败测试（追加到 test_agent_protocol.py）**

```python
# 追加到 tests/test_agent_protocol.py

def test_context_query_returns_field_hints():
    svc, req_id = _make_service_with_drafting_req()
    context = svc.get_agent_requirement_context(
        __import__("requirement_workflow_v12.protocols", fromlist=["AgentRequirementContextQuery"]).AgentRequirementContextQuery(req_id=req_id)
    )
    assert "field_hints" in context
    hints = context["field_hints"]
    assert "输入" in hints
    assert "输出" in hints
    assert "验收标准" in hints
    assert "技术范围声明" in hints
    # 提示性文字，非空
    assert len(hints["输入"]) > 10
    assert len(hints["验收标准"]) > 10
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
python -m pytest tests/test_agent_protocol.py::test_context_query_returns_field_hints -v
```

Expected: FAIL — `field_hints` 不在返回值中

- [ ] **Step 3: 在 `coordinator_service.py` 定义常量并更新 `get_agent_requirement_context`**

在文件顶部（`LOGGER = ...` 之前）添加常量：

```python
FIELD_HINTS: dict[str, str] = {
    "输入": "列举每个入参的字段名、类型、约束，例：license_image: File(jpg/png, max 5MB)",
    "输出": "列举每个出参的字段名、类型、示例值，例：risk_level: str('low'|'medium'|'high')",
    "验收标准": "每条写为可测试断言：Given [前置条件], When [动作], Then [期望结果]",
    "技术范围声明": "说明影响哪些模块/API/数据表，以及明确不包含什么",
}
```

在 `get_agent_requirement_context` 方法的 return 字典中添加：

```python
            "field_hints": FIELD_HINTS,
```

（放在 `"updated_at": ...` 之前）

- [ ] **Step 4: 运行测试，确认通过**

```bash
python -m pytest tests/test_agent_protocol.py -v
```

Expected: 3 passed

- [ ] **Step 5: 全量回归**

```bash
python -m pytest tests/ -q
```

Expected: 55+ passed

- [ ] **Step 6: Commit**

```bash
git add src/requirement_workflow_v12/coordinator_service.py tests/test_agent_protocol.py
git commit -m "feat: add field_hints to context query response"
```

---

## Task 3：简化 DM Handler（移除文档内容逻辑）

**Files:**
- Modify: `src/requirement_workflow_v12/service_app.py:641-685`（`_handle_author_turn` 方法）

`_handle_author_turn` 是 Coordinator 直接处理用户私聊消息的降级路径（非 Author Agent 路径）。在新架构下，用户应通过 Author Agent 构造需求，此方法简化为提示用户使用 Author Agent。

- [ ] **Step 1: 写测试（追加到 test_agent_protocol.py）**

```python
# 追加到 tests/test_agent_protocol.py
import types
import sys as _sys

def _make_runtime_app_for_dm():
    """构建最小 CoordinatorRuntimeApp，用于测试 DM handler。"""
    # stub lark_oapi 以便导入 service_app
    for mod_name in ["lark_oapi", "lark_oapi.ws", "lark_oapi.event",
                     "lark_oapi.event.callback", "lark_oapi.event.callback.model",
                     "lark_oapi.event.callback.model.p2_card_action_trigger",
                     "lark_oapi.api.im.v1.model.p2_im_message_receive_v1"]:
        if mod_name not in _sys.modules:
            _sys.modules[mod_name] = types.ModuleType(mod_name)
    from unittest.mock import MagicMock
    lark_stub = _sys.modules["lark_oapi"]
    lark_stub.EventDispatcherHandler = type("EventDispatcherHandler", (), {"builder": staticmethod(lambda *a, **kw: MagicMock())})
    lark_stub.LogLevel = type("LogLevel", (), {"INFO": "INFO"})()
    lark_stub.ws = _sys.modules["lark_oapi.ws"]
    p2_card_mod = _sys.modules["lark_oapi.event.callback.model.p2_card_action_trigger"]
    p2_card_mod.P2CardActionTrigger = object
    p2_card_mod.P2CardActionTriggerResponse = object
    p2_im_mod = _sys.modules["lark_oapi.api.im.v1.model.p2_im_message_receive_v1"]
    p2_im_mod.P2ImMessageReceiveV1 = object

    from requirement_workflow_v12.config import Settings
    from requirement_workflow_v12.service_app import CoordinatorRuntimeApp, MessageContext

    svc = CoordinatorService()
    resp = svc.create_requirement_from_group(
        CreationRequest(
            project="PROTO", name="DM测试", summary="DM handler 测试",
            creator="tester", creator_user_id="u1", creation_chat_id="c1",
        )
    )
    req = svc.get_requirement(resp.req_id)
    assert req is not None
    svc.handoff_to_author(req)
    req = svc.get_requirement(resp.req_id)
    assert req is not None
    svc.confirm_author_private_binding(req.creator_user_id, f"开始需求构造 {req.req_id}")

    app = CoordinatorRuntimeApp.__new__(CoordinatorRuntimeApp)
    app.settings = Settings(feishu_app_id="app", feishu_app_secret="secret")
    app.service = svc
    app.gateway = MagicMock()
    app.store = MagicMock()
    app._observed_creation_group_chat_id = "c1"
    app._pending_onboarding_project = {}
    app._pending_requirement_info = {}
    return app, resp.req_id, MessageContext


def test_dm_handler_redirects_to_author_agent():
    """直接私聊 Coordinator 时应提示使用 Author Agent，不处理需求内容。"""
    app, req_id, MessageContext = _make_runtime_app_for_dm()
    from requirement_workflow_v12.service_app import MessageContext as MC
    ctx = MC(chat_id="dm_chat", chat_type="p2p", user_id="u1",
             text="这个需求的输入是用户ID和密码", sender_name="Test")
    responses = app.handle_text_message(ctx)
    texts = [r.text for r in responses if hasattr(r, "text")]
    assert any("Author Agent" in t or "需求构造助手" in t or "请前往" in t for t in texts)
```

- [ ] **Step 2: 运行测试，确认当前行为（可能 pass 或 fail，记录结果）**

```bash
python -m pytest tests/test_agent_protocol.py::test_dm_handler_redirects_to_author_agent -v
```

- [ ] **Step 3: 替换 `_handle_author_turn` 方法**

在 `src/requirement_workflow_v12/service_app.py` 中，找到 `def _handle_author_turn` 方法，替换为：

```python
    def _handle_author_turn(self, context: MessageContext, requirement: Requirement) -> list[OutboundMessage]:
        agent_name = self.settings.openclaw_author_agent_name
        return [
            OutboundMessage(
                receive_id=context.chat_id,
                text=(
                    f"请前往 {agent_name} 继续需求构造。\n"
                    f"在 {agent_name} 中发送：\n"
                    f"开始需求构造 {requirement.req_id}"
                ),
            )
        ]
```

同时移除同文件中已不再调用的以下方法（仅在 `_handle_author_turn` 中使用）：
- `_build_rule_based_review`
- `_question_for_field`
- `_next_discussion_field`

- [ ] **Step 4: 运行测试，确认通过**

```bash
python -m pytest tests/test_agent_protocol.py -v
```

Expected: 4 passed

- [ ] **Step 5: 全量回归**

```bash
python -m pytest tests/ -q
```

Expected: 全部通过（若有因 `_build_rule_based_review` 引用失败的测试，在此处修复）

- [ ] **Step 6: Commit**

```bash
git add src/requirement_workflow_v12/service_app.py tests/test_agent_protocol.py
git commit -m "refactor: simplify DM handler to redirect to Author Agent"
```

---

## Task 4：移除 `RequirementDocumentCompiler`

**Files:**
- Delete: `src/requirement_workflow_v12/compiler.py`
- Modify: `src/requirement_workflow_v12/coordinator_service.py`
- Modify: `src/requirement_workflow_v12/__init__.py`
- Modify: `tests/test_requirement_workflow_v12.py`

- [ ] **Step 1: 从 `coordinator_service.py` 移除所有 compiler 引用**

删除文件顶部：
```python
from .compiler import RequirementDocumentCompiler
```

将 `CoordinatorService.__init__` 中的：
```python
    def __init__(self, compiler: RequirementDocumentCompiler | None = None) -> None:
        self.compiler = compiler or RequirementDocumentCompiler()
```
改为：
```python
    def __init__(self) -> None:
```

删除 `coordinator_service.py` 中所有 `self.compiler.*` 调用行：
- `requirement.document = self.compiler.rewrite_sections(...)` 所在行
- `requirement.latest_writeback_at = requirement.document.updated_at` 所在行
- 所有 `requirement.document = self.compiler.refresh_derived_sections(...)` 行

（搜索：`grep -n "self\.compiler\|requirement\.document" src/requirement_workflow_v12/coordinator_service.py`）

- [ ] **Step 2: 运行测试，确认失败**

```bash
python -m pytest tests/ -q 2>&1 | head -30
```

Expected: 部分测试因 `document.sections` 断言失败

- [ ] **Step 3: 更新 `test_requirement_workflow_v12.py` 中的两个 document 断言测试**

找到 `test_discussion_history_is_written_to_document` 方法，替换为：

```python
    def test_discussion_history_is_recorded_in_state(self) -> None:
        """Author Agent 写文档；Coordinator 只记录 discussion_history 状态。"""
        from requirement_workflow_v12.protocols import AgentAuthorEventPayload
        self.service.submit_author_event_payload(
            AgentAuthorEventPayload(
                req_id=self.req_id,
                event="author_submit",
                summary="问题描述已明确，但仍需补充使用场景。",
                completed_fields=["问题描述"],
                iteration_round=1,
            )
        )
        req = self.service.get_requirement(self.req_id)
        assert req is not None
        self.assertEqual(req.current_round, 1)
        self.assertIn("问题描述", req.completed_fields)
        self.assertNotIn("问题描述", req.pending_fields)
```

找到 `test_human_review_history_records_dual_review` 方法，将其中的 `requirement.document.sections["人工Review结论"]` 断言替换为：

```python
        self.assertTrue(len(requirement.human_review_history) > 0)
        self.assertTrue(requirement.human_review_history[-1].approved)
```

- [ ] **Step 4: 从 `__init__.py` 移除导出**

在 `src/requirement_workflow_v12/__init__.py` 中删除：
```python
from .compiler import RequirementDocumentCompiler
```
以及 `__all__` 中的 `"RequirementDocumentCompiler"` 条目。

- [ ] **Step 5: 删除 `compiler.py`**

```bash
rm /Users/daxin/work/requirement-workflow-feishu/src/requirement_workflow_v12/compiler.py
```

- [ ] **Step 6: 从测试导入中移除 `AuthorTurnResult`（仅在 compiler 路径下使用）**

在 `tests/test_requirement_workflow_v12.py` 中，如果 `AuthorTurnResult` 不再被其他测试使用，从 import 中移除：
```python
AuthorTurnResult,
```
（搜索：`grep -n "AuthorTurnResult" tests/test_requirement_workflow_v12.py`，若有残留调用则按下一步处理）

- [ ] **Step 7: 运行测试，确认通过**

```bash
python -m pytest tests/ -q
```

Expected: 全部通过

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "refactor: remove RequirementDocumentCompiler and document content from Coordinator"
```

---

## Task 5：移除 `RequirementDocument` 数据模型

**Files:**
- Modify: `src/requirement_workflow_v12/models.py`
- Modify: `src/requirement_workflow_v12/store.py`
- Modify: `src/requirement_workflow_v12/__init__.py`
- Modify: `src/requirement_workflow_v12/coordinator_service.py`（移除 `AuthorTurnResult.updates`）

- [ ] **Step 1: 写失败测试（追加到 test_agent_protocol.py）**

```python
def test_requirement_has_no_document_field():
    """Requirement 不再持有文档内容副本。"""
    svc, req_id = _make_service_with_drafting_req()
    req = svc.get_requirement(req_id)
    assert req is not None
    assert not hasattr(req, "document") or req.document is None


def test_discussion_turn_has_no_normalized_updates():
    """DiscussionTurn 不再存储字段值。"""
    from requirement_workflow_v12.models import DiscussionTurn
    turn = DiscussionTurn(round_number=1, focused_field="问题描述", user_input="test")
    assert not hasattr(turn, "normalized_updates")
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
python -m pytest tests/test_agent_protocol.py::test_requirement_has_no_document_field tests/test_agent_protocol.py::test_discussion_turn_has_no_normalized_updates -v
```

Expected: FAIL

- [ ] **Step 3: 从 `models.py` 移除 `RequirementDocument` 和相关字段**

在 `src/requirement_workflow_v12/models.py` 中：

1. 删除整个 `RequirementDocument` dataclass（约第 78-85 行）
2. 删除 `Requirement` 中的 `document: RequirementDocument | None = None` 字段
3. 删除 `DiscussionTurn` 中的 `normalized_updates: dict[str, str] = field(default_factory=dict)` 字段

- [ ] **Step 4: 更新 `store.py`**

在 `src/requirement_workflow_v12/store.py` 中：

1. 从 import 中移除 `RequirementDocument`
2. 删除 `_document_from_payload` 方法（约第 124-131 行）
3. 在 `_requirement_from_payload` 中，删除：
   ```python
   document_payload = data.get("document")
   ```
   和
   ```python
   document=self._document_from_payload(document_payload) if document_payload else None,
   ```
4. 在 `_discussion_turn_from_payload` 中，删除：
   ```python
   normalized_updates=data.get("normalized_updates", {}),
   ```

- [ ] **Step 5: 从 `coordinator_service.py` 移除 `AuthorTurnResult`**

`AuthorTurnResult` 只在已简化的 `_handle_author_turn`（DM 降级路径）中用到，现在该方法不再使用它，可以删除。

在 `coordinator_service.py` 中删除：
```python
@dataclass
class AuthorTurnResult:
    updates: dict[str, str]
    next_question: str
    current_field_completed: bool = True
    next_field: str | None = None
```

同时删除 `handle_author_turn` 方法（接受 `AuthorTurnResult` 参数的那个，约第 293-330 行）——该方法已不再被调用。

- [ ] **Step 6: 从 `__init__.py` 移除 `RequirementDocument` 和 `AuthorTurnResult` 导出**

```python
# 删除这些行：
from .models import (
    ...
    RequirementDocument,
    ...
)
# __all__ 中删除：
"RequirementDocument",
"AuthorTurnResult",
```

- [ ] **Step 7: 运行测试，确认通过**

```bash
python -m pytest tests/ -q
```

Expected: 全部通过

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "refactor: remove RequirementDocument model and DiscussionTurn.normalized_updates"
```

---

## Task 6：移除 `sync_requirement_document`

**Files:**
- Modify: `src/requirement_workflow_v12/feishu_gateway.py`
- Modify: `src/requirement_workflow_v12/service_app.py`
- Modify: `tests/test_requirement_workflow_v12.py`（移除所有 `sync_requirement_document` stub）

- [ ] **Step 1: 从 `feishu_gateway.py` 删除相关方法**

删除以下方法及其 lark_oapi import（若仅被这些方法使用）：
- `sync_requirement_document`（第 234-274 行）
- `_list_block_children`（第 279-297 行）
- `_build_requirement_blocks`（第 299-307 行）
- `_heading_block`（第 309-314 行）
- `_text_block`（第 316-317 行）

保留：`_rich_text`、`_text_element`（仍被 `append_design_decision_to_doc` 使用）

同时检查 lark_oapi 的 import 列表，移除不再使用的：
- `BatchDeleteDocumentBlockChildrenRequest`
- `BatchDeleteDocumentBlockChildrenRequestBody`
- `GetDocumentBlockChildrenRequest`

- [ ] **Step 2: 从 `service_app.py` 移除 `sync_requirement_document` 调用**

搜索并删除所有 `gateway.sync_requirement_document(requirement)` 调用行：

```bash
grep -n "sync_requirement_document" src/requirement_workflow_v12/service_app.py
```

每处调用直接删除该行（它只是写文档，不影响流程）。

- [ ] **Step 3: 清理测试文件中的 stub**

在 `tests/test_requirement_workflow_v12.py` 中，所有 `FakeGateway` 类里的：
```python
def sync_requirement_document(self, requirement) -> None:
    return None
```
全部删除（使用编辑器批量替换，或手动逐一删除）。

验证没有漏掉：
```bash
grep -n "sync_requirement_document" tests/test_requirement_workflow_v12.py
```

Expected: 无输出

- [ ] **Step 4: 运行测试，确认通过**

```bash
python -m pytest tests/ -q
```

Expected: 全部通过

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: remove sync_requirement_document from Coordinator and gateway"
```

---

## Task 7：写 Agent SKILL.md 文件

**Files:**
- Create: `docs/agents/requirement-author/SKILL.md`
- Create: `docs/agents/requirement-reviewer/SKILL.md`

这两个文件是部署到 OpenClaw 的 skill 定义，不是 Python，无单元测试。

- [ ] **Step 1: 创建目录并写 Author Agent SKILL.md**

```bash
mkdir -p docs/agents/requirement-author
```

文件内容 `docs/agents/requirement-author/SKILL.md`：

```markdown
---
name: requirement-author
description: 需求构造助手，协助需求提出者逐字段完善需求文档，完成后上报 Coordinator。收到「开始需求构造 REQ-xxx」时激活。
---

# 需求构造助手

## 启动流程

收到包含「开始需求构造 REQ-xxx」的消息时启动。消息中应包含：
- `context_query_url`：Coordinator 上下文查询接口
- `callback_url`：Coordinator callback 接口
- 飞书文档直接链接

**Step 1**：GET {context_query_url}

响应中获取：
- `document_id`：飞书文档 token（用于 feishu_doc 工具）
- `document_url`：文档链接
- `pending_fields`：待填写字段列表
- `completed_fields`：已完成字段列表
- `field_hints`：各字段格式提示

**Step 2**：`feishu_doc { "action": "read", "doc_token": "{document_id}" }`

了解当前文档内容，跳过已完成字段。

**Step 3**：从 `pending_fields[0]` 开始，逐字段与用户沟通。

## 每轮交互规则

1. 每次只聚焦一个字段，明确告知用户「现在我们来完善【字段名】」
2. 用户回复后，整合内容写入文档：
   ```
   feishu_doc {
     "action": "write",
     "doc_token": "{document_id}",
     "content": "<完整 9 节 markdown>"
   }
   ```
3. 向用户确认写入内容，然后进入下一个字段
4. 不跳过字段，除非用户明确说「先跳过」

## 文档格式（每次 write 使用完整结构）

```markdown
# {req_id} {name}

## 需求概览
{summary}

## 问题描述
{content}

## 使用场景
{content}

## 输入
{content}

## 输出
{content}

## 边界
{content}

## 验收标准
{content}

## 非功能要求
{content}

## 技术范围声明
{content}
```

## 字段格式提示（从 field_hints 读取，引导用，非强制）

- **输入**：列举每个入参的字段名、类型、约束，例：`license_image: File(jpg/png, max 5MB)`
- **输出**：列举每个出参的字段名、类型、示例值
- **验收标准**：每条写为可测试断言，例：`Given 有效图片，When 提交，Then 返回 200 含 risk_level`
- **技术范围声明**：说明影响哪些模块/API/数据表，明确不包含什么
- 其余字段（问题描述、使用场景、边界、非功能要求）：清晰自然语言即可

## 完成标准

所有 `pending_fields` 均已填写后，询问用户：「所有字段已完成，是否确认提交审查？」

用户确认后：

```
POST {callback_url}/callbacks/openclaw/author-turn
Content-Type: application/json

{
  "req_id": "{req_id}",
  "event": "author_submit",
  "summary": "<本轮完成字段和要点摘要>",
  "completed_fields": ["{field1}", "{field2}", ...所有已完成字段],
  "iteration_round": {current_round}
}
```

## 不允许的行为

- 不创建新文档（只操作 context_query 返回的 document_id）
- 不修改「需求概览」节的内容（由 Coordinator 写入，保持原样）
- 不推进审查状态（状态由 Coordinator 管理）
- 不在 callback 前修改字段 event 名称（必须是 `author_submit`）
```

- [ ] **Step 2: 创建目录并写 Review Agent SKILL.md**

```bash
mkdir -p docs/agents/requirement-reviewer
```

文件内容 `docs/agents/requirement-reviewer/SKILL.md`：

```markdown
---
name: requirement-reviewer
description: 需求审查助手，按 8 项维度审查需求文档质量，单次上报 pass/reject 结论，不与用户多轮沟通。
---

# 需求审查助手

## 启动流程

收到包含 `req_id` 和文档信息的审查请求时启动。

**Step 1**：`feishu_doc { "action": "read", "doc_token": "{document_id}" }`

**Step 2**：GET {context_query_url} 获取 `completed_fields`、`pending_fields`、历史 `latest_review_summary`

**Step 3**：按 8 项维度逐一检查（见下方定义）

## 8 项审查维度

### 阻断维度（任一不通过 → reject）

**维度 1：字段完整性**
所有 8 个字段（问题描述、使用场景、输入、输出、边界、验收标准、非功能要求、技术范围声明）均非「待补充」且有实质内容。
不通过：指出空缺字段名。

**维度 2：输入结构化**
「输入」包含具体参数（字段名 + 类型/格式），而非纯自然语言描述（如「用户上传一张图」）。
不通过：说明需要参数化，给出示例格式。

**维度 3：输出结构化**
「输出」包含返回字段名 + 类型，而非「返回成功信息」等模糊描述。
不通过：同上。

**维度 4：验收标准可测试**
每条验收标准为条件-动作-期望结构（Given/When/Then 或等价形式），无纯自然语言目标（如「系统应快速响应」）。
不通过：标出不可测条目，说明如何改写。

**维度 7：技术范围声明存在性**
「技术范围声明」非空，包含明确的模块/API/数据表信息。
不通过：说明这是 Spec 生成的必要输入。

**维度 8：内部一致性**
「输入」中定义的字段与「验收标准」中使用的字段自洽，无矛盾描述。
不通过：指出具体冲突点。

### 警告维度（不通过 → 记入 weak_fields，仍可 pass）

**维度 5：边界覆盖**
包含至少一个异常/错误/边界情况描述。
不通过：记入 weak_fields。

**维度 6：非功能量化**
若有性能/可用性声明，包含可量化指标（P99 < Xs，99.9%）。
不通过：记入 weak_fields。

## 输出

```
POST {callback_url}/callbacks/openclaw/review-result
Content-Type: application/json

{
  "req_id": "{req_id}",
  "event": "ai_review_pass" | "ai_review_reject",
  "review_summary": "<整体结论一句话，含具体问题或通过原因>",
  "weak_fields": ["非功能要求"],
  "document_url": "{document_url}"
}
```

## 不允许的行为

- 不修改需求文档
- 不与用户多轮沟通（单次审查，直接上报）
- 不推进人工确认或正式审查（event 只能是 `ai_review_pass` 或 `ai_review_reject`）
- 不猜测缺失信息（按实际内容审查，有疑问记入 review_summary）
```

- [ ] **Step 3: Commit**

```bash
git add docs/agents/
git commit -m "docs: add Author Agent and Review Agent SKILL.md definitions"
```

---

## Task 8：全量验证

- [ ] **Step 1: 完整测试套件**

```bash
cd /Users/daxin/work/requirement-workflow-feishu
python -m pytest tests/ -v 2>&1 | tail -20
```

Expected: 全部 passed，1 warning（已知线程告警，不影响功能）

- [ ] **Step 2: 确认删除的 symbol 不再出现**

```bash
grep -rn "RequirementDocument\|RequirementDocumentCompiler\|sync_requirement_document\|normalized_updates\|AuthorTurnResult\|_build_rule_based_review\|compiler\.py" \
  src/requirement_workflow_v12/ tests/ \
  --include="*.py" | grep -v __pycache__
```

Expected: 无输出（若有残留，逐一修复）

- [ ] **Step 3: 确认 SKILL.md 文件完整**

```bash
ls docs/agents/requirement-author/SKILL.md docs/agents/requirement-reviewer/SKILL.md
wc -l docs/agents/requirement-author/SKILL.md docs/agents/requirement-reviewer/SKILL.md
```

Expected: 两个文件存在，各 > 50 行

- [ ] **Step 4: Push**

```bash
git push origin main
```

---

## 自检清单

### Spec 覆盖检查

| Spec 要求 | 覆盖任务 |
|---|---|
| §1a context query 加 `field_hints` | Task 2 |
| §1b author callback 加 `completed_fields`，移除 `normalized_updates` | Task 1 |
| §1c review callback 不变 | 无需改动 |
| §2 移除 `sync_requirement_document` | Task 6 |
| §2 移除 `Requirement.document` | Task 5 |
| §2 移除 `RequirementDocumentCompiler` | Task 4 |
| §2 简化 `handle_author_turn` | Task 4 + 5 |
| §2 文档三元数据节移出文档 | Task 4（测试断言更新） |
| §3 Author Agent SKILL.md | Task 7 |
| §4 Review Agent SKILL.md（8 维度） | Task 7 |
