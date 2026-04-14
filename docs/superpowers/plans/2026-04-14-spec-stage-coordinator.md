# Spec 阶段 Coordinator 扩展 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the Coordinator to support a Spec stage (SPEC_DRAFTING → SPEC_LOCKED) after a requirement is APPROVED, with automatic Spec Agent and Spec Reviewer handoffs, and a 卡点1a notification card on SPEC_LOCKED.

**Architecture:** New WorkflowStatus values (SPEC_DRAFTING, SPEC_LOCKED) and Event (SPEC_START) are added to the state machine. A new `/callbacks/openclaw/spec-turn` HTTP endpoint handles `spec_start` (creates Feishu Spec doc, transitions state) and `spec_submit` (notifies Spec Reviewer). The existing `/callbacks/openclaw/review-result` endpoint is extended with a status branch: if the requirement is SPEC_DRAFTING when a review result arrives, it routes to Spec-layer logic instead of requirement-layer logic.

**Tech Stack:** Python 3.11+, lark-oapi (Feishu SDK), JSON flat-file state store, pytest

---

## File Structure

| File | Change |
|------|--------|
| `src/requirement_workflow_v12/models.py` | Add SPEC_DRAFTING, SPEC_LOCKED to WorkflowStatus; add 3 spec fields to Requirement |
| `src/requirement_workflow_v12/state_machine.py` | Add Event.SPEC_START; add 3 transitions |
| `src/requirement_workflow_v12/protocols.py` | Add AgentSpecEventPayload dataclass |
| `src/requirement_workflow_v12/config.py` | Add 3 Spec agent settings |
| `src/requirement_workflow_v12/store.py` | Load 3 spec fields in _requirement_from_payload |
| `src/requirement_workflow_v12/coordinator_service.py` | Add submit_spec_start, submit_spec_submit; branch submit_review_event_payload on SPEC_DRAFTING; extend get_agent_requirement_context |
| `src/requirement_workflow_v12/feishu_gateway.py` | Add create_spec_document |
| `src/requirement_workflow_v12/service_app.py` | Register spec-turn endpoint; add handler; add notifications (APPROVED→SpecAgent, SPEC_LOCKED card, spec_review_reject→SpecAgent); fix _save_state missing project_configs |
| `.github/workflows/staging.yml` | Add 3 env vars to .env heredoc |
| `docs/agents/spec-author/SKILL.md` | New file: Spec Author Agent skill |
| `docs/agents/spec-reviewer/SKILL.md` | New file: Spec Reviewer Agent skill |
| `tests/test_spec_stage.py` | New file: all Spec stage tests |

---

## Task 1: Data Model + State Machine

**Files:**
- Modify: `src/requirement_workflow_v12/models.py`
- Modify: `src/requirement_workflow_v12/state_machine.py`
- Create: `tests/test_spec_stage.py`

- [ ] **Step 1: Write failing state machine tests**

```python
# tests/test_spec_stage.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.models import WorkflowStatus, Requirement
from requirement_workflow_v12.state_machine import Event, apply_event


def test_spec_start_transitions_approved_to_spec_drafting():
    decision = apply_event(WorkflowStatus.APPROVED, Event.SPEC_START)
    assert decision.allowed
    assert decision.next_status == WorkflowStatus.SPEC_DRAFTING


def test_ai_review_pass_in_spec_drafting_transitions_to_spec_locked():
    decision = apply_event(WorkflowStatus.SPEC_DRAFTING, Event.AI_REVIEW_PASS)
    assert decision.allowed
    assert decision.next_status == WorkflowStatus.SPEC_LOCKED


def test_ai_review_reject_in_spec_drafting_stays_spec_drafting():
    decision = apply_event(WorkflowStatus.SPEC_DRAFTING, Event.AI_REVIEW_REJECT)
    assert decision.allowed
    assert decision.next_status == WorkflowStatus.SPEC_DRAFTING


def test_spec_start_blocked_in_non_approved_status():
    decision = apply_event(WorkflowStatus.DRAFTING, Event.SPEC_START)
    assert not decision.allowed


def test_requirement_has_spec_fields():
    req = Requirement(req_id="REQ-X-001", name="test", project="X", summary="s", creator="c")
    assert hasattr(req, "spec_document_id")
    assert hasattr(req, "spec_document_url")
    assert hasattr(req, "spec_review_summary")
    assert req.spec_document_id == ""
    assert req.spec_document_url == ""
    assert req.spec_review_summary == ""
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/daxin/work/requirement-workflow-feishu
python -m pytest tests/test_spec_stage.py -v 2>&1 | head -30
```

Expected: FAIL with "cannot import name 'SPEC_START' from 'requirement_workflow_v12.state_machine'" or AttributeError

- [ ] **Step 3: Add SPEC_DRAFTING and SPEC_LOCKED to WorkflowStatus in models.py**

In `src/requirement_workflow_v12/models.py`, add after `REQ_APPROVED = "APPROVED"` (line 36):

```python
    SPEC_DRAFTING = "SPEC_DRAFTING"
    SPEC_LOCKED = "SPEC_LOCKED"
```

- [ ] **Step 4: Add spec fields to Requirement dataclass in models.py**

In `src/requirement_workflow_v12/models.py`, add after `hifi_prototype_confirmed: bool = False` (line 110):

```python
    spec_document_id: str = ""
    spec_document_url: str = ""
    spec_review_summary: str = ""
```

- [ ] **Step 5: Add SPEC_START event and new transitions to state_machine.py**

In `src/requirement_workflow_v12/state_machine.py`, add `SPEC_START = "spec_start"` after `FINAL_REVIEW_REJECT = "final_review_reject"` (line 17):

```python
    SPEC_START = "spec_start"
```

In `src/requirement_workflow_v12/state_machine.py`, add these three entries to the TRANSITIONS dict after `(WorkflowStatus.FINAL_REVIEW, Event.FINAL_REVIEW_REJECT): WorkflowStatus.DRAFTING,` (line 37):

```python
    (WorkflowStatus.APPROVED, Event.SPEC_START): WorkflowStatus.SPEC_DRAFTING,
    (WorkflowStatus.SPEC_DRAFTING, Event.AI_REVIEW_PASS): WorkflowStatus.SPEC_LOCKED,
    (WorkflowStatus.SPEC_DRAFTING, Event.AI_REVIEW_REJECT): WorkflowStatus.SPEC_DRAFTING,
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
python -m pytest tests/test_spec_stage.py -v
```

Expected: all 5 tests PASS

- [ ] **Step 7: Run full test suite to verify no regressions**

```bash
python -m pytest tests/ -v --tb=short
```

Expected: all existing tests PASS

- [ ] **Step 8: Commit**

```bash
git add src/requirement_workflow_v12/models.py src/requirement_workflow_v12/state_machine.py tests/test_spec_stage.py
git commit -m "feat: add SPEC_DRAFTING/SPEC_LOCKED states, SPEC_START event, and spec fields to Requirement"
```

---

## Task 2: Config + Store + _save_state Fix

**Files:**
- Modify: `src/requirement_workflow_v12/config.py`
- Modify: `src/requirement_workflow_v12/store.py`
- Modify: `src/requirement_workflow_v12/service_app.py` (only `_save_state`)

- [ ] **Step 1: Write failing tests for store round-trip and config**

Add to `tests/test_spec_stage.py`:

```python
def test_store_round_trips_spec_fields():
    import tempfile, json
    from requirement_workflow_v12.store import JsonStateStore
    from requirement_workflow_v12.models import Requirement, WorkflowStatus

    req = Requirement(req_id="REQ-S-001", name="Spec 测试", project="S", summary="s", creator="c")
    req.status = WorkflowStatus.SPEC_DRAFTING
    req.spec_document_id = "doctoken123"
    req.spec_document_url = "https://feishu.cn/docx/doctoken123"
    req.spec_review_summary = "Spec 审查通过"

    with tempfile.TemporaryDirectory() as tmpdir:
        store = JsonStateStore(f"{tmpdir}/state.json")
        store.save_snapshot({"REQ-S-001": req}, {}, {})
        reqs, _, _, _ = store.load_snapshot()
        loaded = reqs["REQ-S-001"]
        assert loaded.status == WorkflowStatus.SPEC_DRAFTING
        assert loaded.spec_document_id == "doctoken123"
        assert loaded.spec_document_url == "https://feishu.cn/docx/doctoken123"
        assert loaded.spec_review_summary == "Spec 审查通过"


def test_config_has_spec_agent_settings():
    import os
    os.environ["SPEC_AGENT_FEISHU_ID"] = "ou_spec_agent_1"
    os.environ["SPEC_REVIEWER_FEISHU_ID"] = "ou_spec_reviewer_1"
    os.environ["OPENCLAW_SPEC_AGENT_NAME"] = "我的Spec助手"
    from requirement_workflow_v12.config import Settings
    s = Settings()
    assert s.spec_agent_feishu_id == "ou_spec_agent_1"
    assert s.spec_reviewer_feishu_id == "ou_spec_reviewer_1"
    assert s.openclaw_spec_agent_name == "我的Spec助手"
    del os.environ["SPEC_AGENT_FEISHU_ID"]
    del os.environ["SPEC_REVIEWER_FEISHU_ID"]
    del os.environ["OPENCLAW_SPEC_AGENT_NAME"]
```

- [ ] **Step 2: Run new tests to verify they fail**

```bash
python -m pytest tests/test_spec_stage.py::test_store_round_trips_spec_fields tests/test_spec_stage.py::test_config_has_spec_agent_settings -v
```

Expected: FAIL

- [ ] **Step 3: Add 3 settings to config.py**

In `src/requirement_workflow_v12/config.py`, add after `github_default_branch: str = os.environ.get("GITHUB_DEFAULT_BRANCH", "main")` (line 34):

```python
    openclaw_spec_agent_name: str = os.environ.get("OPENCLAW_SPEC_AGENT_NAME", "Spec 撰写助手")
    spec_agent_feishu_id: str = os.environ.get("SPEC_AGENT_FEISHU_ID", "")
    spec_reviewer_feishu_id: str = os.environ.get("SPEC_REVIEWER_FEISHU_ID", "")
```

- [ ] **Step 4: Add spec fields to _requirement_from_payload in store.py**

In `src/requirement_workflow_v12/store.py`, in the `_requirement_from_payload` method, add after `hifi_prototype_confirmed=data.get("hifi_prototype_confirmed", False),` (after line 111):

```python
            spec_document_id=data.get("spec_document_id", ""),
            spec_document_url=data.get("spec_document_url", ""),
            spec_review_summary=data.get("spec_review_summary", ""),
```

- [ ] **Step 5: Fix _save_state in service_app.py to persist project_configs**

In `src/requirement_workflow_v12/service_app.py`, replace the `_save_state` method body (lines 1816–1821):

```python
    def _save_state(self) -> None:
        self.store.save_snapshot(
            self.service.requirements,
            self.service.active_req_by_user,
            self.service.project_groups,
            self.service.project_configs,
        )
```

- [ ] **Step 6: Run new tests to verify they pass**

```bash
python -m pytest tests/test_spec_stage.py::test_store_round_trips_spec_fields tests/test_spec_stage.py::test_config_has_spec_agent_settings -v
```

Expected: PASS

- [ ] **Step 7: Run full test suite**

```bash
python -m pytest tests/ -v --tb=short
```

Expected: all tests PASS

- [ ] **Step 8: Commit**

```bash
git add src/requirement_workflow_v12/config.py src/requirement_workflow_v12/store.py src/requirement_workflow_v12/service_app.py
git commit -m "feat: add Spec agent config settings, store spec fields round-trip, fix _save_state missing project_configs"
```

---

## Task 3: CoordinatorService Spec Methods

**Files:**
- Modify: `src/requirement_workflow_v12/protocols.py`
- Modify: `src/requirement_workflow_v12/coordinator_service.py`

- [ ] **Step 1: Write failing tests for CoordinatorService spec methods**

Add to `tests/test_spec_stage.py`:

```python
from requirement_workflow_v12.coordinator_service import CoordinatorService
from requirement_workflow_v12 import CreationRequest
from requirement_workflow_v12.protocols import AgentReviewEventPayload


def _make_approved_requirement():
    """Create a requirement and advance it all the way to APPROVED."""
    from requirement_workflow_v12.protocols import AgentReviewEventPayload
    svc = CoordinatorService()
    resp = svc.create_requirement_from_group(CreationRequest(
        project="SPEC", name="Spec测试需求", summary="s", creator="c",
        creator_user_id="u1", creation_chat_id="chat1",
    ))
    req = svc.get_requirement(resp.req_id)
    assert req is not None
    # Drive to APPROVED
    from requirement_workflow_v12.protocols import AgentAuthorEventPayload
    svc.submit_author_event_payload(AgentAuthorEventPayload(
        req_id=resp.req_id, event="author_submit", summary="done",
        completed_fields=list(req.pending_fields),
    ))
    svc.submit_review_event_payload(AgentReviewEventPayload(
        req_id=resp.req_id, event="ai_review_pass", review_summary="pass",
    ))
    req = svc.get_requirement(resp.req_id)
    assert req is not None
    svc.handle_human_confirmation(req, approved=True)
    req = svc.get_requirement(resp.req_id)
    assert req is not None
    svc.approve_requirement(req)
    req = svc.get_requirement(resp.req_id)
    assert req is not None
    assert req.status == WorkflowStatus.APPROVED
    return svc, resp.req_id


def test_submit_spec_start_transitions_to_spec_drafting():
    svc, req_id = _make_approved_requirement()
    req = svc.submit_spec_start(req_id, spec_document_id="docabc", spec_document_url="https://feishu.cn/docx/docabc")
    assert req.status == WorkflowStatus.SPEC_DRAFTING
    assert req.spec_document_id == "docabc"
    assert req.spec_document_url == "https://feishu.cn/docx/docabc"
    assert req.current_phase == "Spec 撰写"
    assert req.current_owner == "spec-agent"


def test_submit_spec_start_blocked_if_not_approved():
    svc = CoordinatorService()
    resp = svc.create_requirement_from_group(CreationRequest(
        project="SPEC2", name="n", summary="s", creator="c",
        creator_user_id="u1", creation_chat_id="c1",
    ))
    import pytest
    with pytest.raises(ValueError, match="SPEC_START"):
        svc.submit_spec_start(resp.req_id, spec_document_id="x", spec_document_url="y")


def test_submit_spec_submit_stores_summary():
    svc, req_id = _make_approved_requirement()
    svc.submit_spec_start(req_id, spec_document_id="doc1", spec_document_url="https://feishu.cn/docx/doc1")
    req = svc.submit_spec_submit(req_id, summary="Spec 初稿完成，9节均已填写")
    assert req.status == WorkflowStatus.SPEC_DRAFTING  # no state change
    assert req.spec_review_summary == "Spec 初稿完成，9节均已填写"


def test_spec_review_pass_transitions_to_spec_locked():
    svc, req_id = _make_approved_requirement()
    svc.submit_spec_start(req_id, spec_document_id="doc1", spec_document_url="https://feishu.cn/docx/doc1")
    req = svc.submit_review_event_payload(AgentReviewEventPayload(
        req_id=req_id, event="ai_review_pass", review_summary="Spec 质量达标",
    ))
    assert req.status == WorkflowStatus.SPEC_LOCKED
    assert req.spec_review_summary == "Spec 质量达标"


def test_spec_review_reject_stays_spec_drafting():
    svc, req_id = _make_approved_requirement()
    svc.submit_spec_start(req_id, spec_document_id="doc1", spec_document_url="https://feishu.cn/docx/doc1")
    req = svc.submit_review_event_payload(AgentReviewEventPayload(
        req_id=req_id, event="ai_review_reject", review_summary="API 入参缺少字段名",
    ))
    assert req.status == WorkflowStatus.SPEC_DRAFTING
    assert req.spec_review_summary == "API 入参缺少字段名"


def test_context_query_returns_spec_fields():
    from requirement_workflow_v12.protocols import AgentRequirementContextQuery
    svc, req_id = _make_approved_requirement()
    svc.submit_spec_start(req_id, spec_document_id="docXYZ", spec_document_url="https://feishu.cn/docx/docXYZ")
    ctx = svc.get_agent_requirement_context(AgentRequirementContextQuery(req_id=req_id))
    assert ctx["spec_document_id"] == "docXYZ"
    assert ctx["spec_document_url"] == "https://feishu.cn/docx/docXYZ"
    assert "spec_review_summary" in ctx
```

- [ ] **Step 2: Run new tests to verify they fail**

```bash
python -m pytest tests/test_spec_stage.py -k "spec_start or spec_submit or spec_review or spec_fields" -v 2>&1 | head -40
```

Expected: FAIL (AttributeError or ImportError)

- [ ] **Step 3: Add AgentSpecEventPayload to protocols.py**

In `src/requirement_workflow_v12/protocols.py`, add after the `AgentRequirementContextQuery` dataclass (after line 76):

```python

@dataclass
class AgentSpecEventPayload:
    req_id: str
    event: str  # "spec_start" | "spec_submit"
    summary: str
    spec_document_url: str = ""
```

- [ ] **Step 4: Add submit_spec_start to coordinator_service.py**

In `src/requirement_workflow_v12/coordinator_service.py`, add after the `approve_requirement` method (before `request_changes_after_review`):

```python
    def submit_spec_start(
        self,
        req_id: str,
        *,
        spec_document_id: str,
        spec_document_url: str,
    ) -> Requirement:
        requirement = self.requirements.get(req_id)
        if requirement is None:
            raise ValueError(f"未知需求：{req_id}")
        decision = apply_event(requirement.status, Event.SPEC_START)
        if not decision.allowed:
            raise ValueError(decision.message)
        requirement.status = decision.next_status
        requirement.spec_document_id = spec_document_id
        requirement.spec_document_url = spec_document_url
        requirement.current_phase = "Spec 撰写"
        requirement.current_owner = "spec-agent"
        requirement.current_role_label = "Spec 撰写 Agent"
        requirement.touch()
        LOGGER.info(
            "Spec start accepted req_id=%s status=%s spec_document_id=%s",
            requirement.req_id,
            requirement.status.value,
            spec_document_id,
        )
        return requirement

    def submit_spec_submit(self, req_id: str, *, summary: str) -> Requirement:
        requirement = self.requirements.get(req_id)
        if requirement is None:
            raise ValueError(f"未知需求：{req_id}")
        if requirement.status != WorkflowStatus.SPEC_DRAFTING:
            raise ValueError(
                f"spec_submit 只能在 SPEC_DRAFTING 状态执行，当前状态：{requirement.status.value}"
            )
        requirement.spec_review_summary = summary
        requirement.touch()
        LOGGER.info("Spec submit accepted req_id=%s summary=%s", req_id, summary)
        return requirement
```

- [ ] **Step 5: Add SPEC_DRAFTING branch to submit_review_event_payload in coordinator_service.py**

In `src/requirement_workflow_v12/coordinator_service.py`, in the `submit_review_event_payload` method, replace the block that starts with `if event_name == "ai_review_reject":` and ends with the final `requirement.touch()` call (roughly lines 387–420), with:

```python
        if requirement.status == WorkflowStatus.SPEC_DRAFTING:
            # Spec layer review branch
            if event_name == "ai_review_pass":
                decision = apply_event(requirement.status, Event.AI_REVIEW_PASS)
                if not decision.allowed:
                    raise ValueError(decision.message)
                requirement.status = decision.next_status
                requirement.spec_review_summary = payload.review_summary
                requirement.current_phase = "Spec 已锁定"
                requirement.current_owner = "coordinator-service"
                requirement.current_role_label = "需求协调服务"
            else:  # ai_review_reject
                decision = apply_event(requirement.status, Event.AI_REVIEW_REJECT)
                if not decision.allowed:
                    raise ValueError(decision.message)
                requirement.status = decision.next_status
                requirement.spec_review_summary = payload.review_summary
                requirement.current_phase = "Spec 撰写"
                requirement.current_owner = "spec-agent"
                requirement.current_role_label = "Spec 撰写 Agent"
        elif requirement.status == WorkflowStatus.AI_REVIEW:
            # Requirement layer review branch (original logic)
            if event_name == "ai_review_reject":
                decision = apply_event(requirement.status, Event.AI_REVIEW_REJECT)
                if not decision.allowed:
                    raise ValueError(decision.message)
                requirement.status = decision.next_status
                requirement.current_phase = "需求构造"
                requirement.current_owner = "author"
                requirement.current_role_label = "需求构造Agent"
                requirement.ai_ready = False
                requirement.human_confirmed = False
                requirement.latest_question = payload.review_summary
            elif event_name == "ai_review_pass":
                decision = apply_event(requirement.status, Event.AI_REVIEW_PASS)
                if not decision.allowed:
                    raise ValueError(decision.message)
                requirement.status = decision.next_status
                requirement.current_phase = "人工确认"
                requirement.current_owner = "human"
                requirement.current_role_label = "人工确认"
                requirement.ai_ready = True
                requirement.latest_question = "AI review 已通过，请进行人工确认。"
        else:
            raise ValueError(
                f"当前状态 {requirement.status.value} 不支持 review 事件。"
                "review callback 只能在 AI_REVIEW 或 SPEC_DRAFTING 状态使用。"
            )
```

- [ ] **Step 6: Extend get_agent_requirement_context to return spec fields**

In `src/requirement_workflow_v12/coordinator_service.py`, in the `get_agent_requirement_context` method, add these three fields to the returned dict (add after `"updated_at": requirement.updated_at.isoformat(),`):

```python
            "spec_document_id": requirement.spec_document_id,
            "spec_document_url": requirement.spec_document_url,
            "spec_review_summary": requirement.spec_review_summary,
```

- [ ] **Step 7: Run new tests to verify they pass**

```bash
python -m pytest tests/test_spec_stage.py -v
```

Expected: all tests PASS

- [ ] **Step 8: Run full test suite**

```bash
python -m pytest tests/ -v --tb=short
```

Expected: all tests PASS

- [ ] **Step 9: Commit**

```bash
git add src/requirement_workflow_v12/protocols.py src/requirement_workflow_v12/coordinator_service.py
git commit -m "feat: add CoordinatorService spec_start/spec_submit methods and SPEC_DRAFTING review branch"
```

---

## Task 4: Feishu Gateway create_spec_document

**Files:**
- Modify: `src/requirement_workflow_v12/feishu_gateway.py`

- [ ] **Step 1: Add create_spec_document method to FeishuGateway**

In `src/requirement_workflow_v12/feishu_gateway.py`, add after the `create_requirement_document` method (after line 218):

```python
    def create_spec_document(self, requirement: Requirement) -> CreatedDocument | None:
        if not self.settings.feishu_doc_folder_token:
            return None
        title = f"{requirement.req_id} {requirement.name} — 技术规格"
        LOGGER.info("Feishu create_spec_document req_id=%s title=%s", requirement.req_id, title)
        request = (
            CreateDocumentRequest.builder()
            .request_body(
                CreateDocumentRequestBody.builder()
                .folder_token(self.settings.feishu_doc_folder_token)
                .title(title)
                .build()
            )
            .build()
        )
        response = self.client.docx.v1.document.create(request)
        self._ensure_success(response, "create spec document")
        document = response.data.document
        LOGGER.info(
            "Feishu created spec document req_id=%s document_id=%s",
            requirement.req_id,
            document.document_id,
        )
        return CreatedDocument(
            document_id=document.document_id,
            document_url=f"{self.settings.feishu_base_url}/docx/{document.document_id}",
        )
```

- [ ] **Step 2: Run full test suite to verify no regressions**

```bash
python -m pytest tests/ -v --tb=short
```

Expected: all tests PASS (create_spec_document is tested indirectly via FakeGateway in Task 5)

- [ ] **Step 3: Commit**

```bash
git add src/requirement_workflow_v12/feishu_gateway.py
git commit -m "feat: add FeishuGateway.create_spec_document"
```

---

## Task 5: service_app — spec-turn Endpoint + Notifications

**Files:**
- Modify: `src/requirement_workflow_v12/service_app.py`

This task adds:
1. `/callbacks/openclaw/spec-turn` HTTP endpoint registration and handler
2. APPROVED → Spec Agent text notification (in `_dispatch_transition_notifications`)
3. SPEC_LOCKED → 卡点1a card to project group (in `_dispatch_transition_notifications`)
4. spec_review_reject → Spec Agent text notification (in `_dispatch_transition_notifications`)

- [ ] **Step 1: Write failing HTTP endpoint tests**

Add to `tests/test_spec_stage.py`:

```python
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from requirement_workflow_v12.service_app import CoordinatorRuntimeApp
from requirement_workflow_v12 import Settings


class FakeGateway:
    """Minimal gateway stub for unit tests."""
    def __init__(self):
        self.sent_texts: list[tuple[str, str, str]] = []  # (receive_id, text, receive_id_type)
        self.sent_cards: list[tuple[str, dict, str]] = []  # (receive_id, card, receive_id_type)
        self.spec_doc_created: list[str] = []  # req_ids

    def update_requirement_record(self, req) -> None:
        pass

    def bitable_url(self) -> str:
        return ""

    def send_text(self, receive_id, text, receive_id_type="chat_id"):
        self.sent_texts.append((receive_id, text, receive_id_type))

    def send_card(self, receive_id, card, receive_id_type="chat_id"):
        self.sent_cards.append((receive_id, card, receive_id_type))

    def create_spec_document(self, requirement):
        self.spec_doc_created.append(requirement.req_id)
        from requirement_workflow_v12.feishu_gateway import CreatedDocument
        return CreatedDocument(
            document_id=f"spec_doc_{requirement.req_id}",
            document_url=f"https://feishu.cn/docx/spec_doc_{requirement.req_id}",
        )


def _make_app_with_approved_req():
    with TemporaryDirectory() as tmpdir:
        svc = CoordinatorService()
        resp = svc.create_requirement_from_group(CreationRequest(
            project="SPEC3", name="端到端测试", summary="s", creator="c",
            creator_user_id="u1", creation_chat_id="c1",
        ))
        req = svc.get_requirement(resp.req_id)
        assert req is not None
        from requirement_workflow_v12.protocols import AgentAuthorEventPayload
        svc.submit_author_event_payload(AgentAuthorEventPayload(
            req_id=resp.req_id, event="author_submit", summary="done",
            completed_fields=list(req.pending_fields),
        ))
        svc.submit_review_event_payload(AgentReviewEventPayload(
            req_id=resp.req_id, event="ai_review_pass", review_summary="pass",
        ))
        req = svc.get_requirement(resp.req_id)
        assert req is not None
        svc.handle_human_confirmation(req, approved=True)
        req = svc.get_requirement(resp.req_id)
        assert req is not None
        svc.approve_requirement(req)

        gateway = FakeGateway()
        app = CoordinatorRuntimeApp(
            Settings(feishu_app_id="x", feishu_app_secret="y",
                     state_store_path=f"{tmpdir}/state.json"),
            service=svc,
            gateway=gateway,
        )
        return app, resp.req_id, gateway


def test_spec_start_callback_creates_doc_and_transitions_state():
    app, req_id, gateway = _make_app_with_approved_req()
    body = json.dumps({"req_id": req_id, "event": "spec_start", "summary": "开始 Spec 撰写"}).encode()
    status, payload = app.handle_openclaw_spec_turn_callback(body)
    assert status == 200
    assert payload["ok"] is True
    assert payload["status"] == "SPEC_DRAFTING"
    assert "spec_document_id" in payload
    assert "spec_document_url" in payload
    assert "requirement_document_url" in payload
    req = app.service.get_requirement(req_id)
    assert req is not None
    assert req.status == WorkflowStatus.SPEC_DRAFTING
    assert req.spec_document_id == f"spec_doc_{req_id}"


def test_spec_start_blocked_if_not_approved():
    app, req_id, gateway = _make_app_with_approved_req()
    # First, start once
    body = json.dumps({"req_id": req_id, "event": "spec_start", "summary": "start"}).encode()
    app.handle_openclaw_spec_turn_callback(body)
    # Try to start again (now SPEC_DRAFTING, not APPROVED)
    status, payload = app.handle_openclaw_spec_turn_callback(body)
    assert status == 400


def test_spec_submit_notifies_reviewer():
    app, req_id, gateway = _make_app_with_approved_req()
    # First start
    start_body = json.dumps({"req_id": req_id, "event": "spec_start", "summary": "start"}).encode()
    app.handle_openclaw_spec_turn_callback(start_body)
    # Configure reviewer
    app.settings.spec_reviewer_feishu_id = "ou_reviewer_123"
    # Submit
    submit_body = json.dumps({
        "req_id": req_id,
        "event": "spec_submit",
        "summary": "9节已完成",
        "spec_document_url": "https://feishu.cn/docx/spec_doc",
    }).encode()
    status, payload = app.handle_openclaw_spec_turn_callback(submit_body)
    assert status == 200
    assert payload["ok"] is True
    # Verify reviewer was notified
    reviewer_texts = [t for t in gateway.sent_texts if t[0] == "ou_reviewer_123"]
    assert len(reviewer_texts) == 1
    assert req_id in reviewer_texts[0][1]


def test_review_result_on_spec_drafting_transitions_to_spec_locked():
    app, req_id, gateway = _make_app_with_approved_req()
    start_body = json.dumps({"req_id": req_id, "event": "spec_start", "summary": "start"}).encode()
    app.handle_openclaw_spec_turn_callback(start_body)

    review_body = json.dumps({
        "req_id": req_id,
        "event": "ai_review_pass",
        "review_summary": "Spec 质量达标",
    }).encode()
    status, payload = app.handle_openclaw_review_result_callback(review_body)
    assert status == 200
    req = app.service.get_requirement(req_id)
    assert req is not None
    assert req.status == WorkflowStatus.SPEC_LOCKED


def test_spec_locked_sends_notification_card_to_project_group():
    app, req_id, gateway = _make_app_with_approved_req()
    # Give requirement a project_group_id
    req = app.service.get_requirement(req_id)
    assert req is not None
    req.project_group_id = "oc_testgroup123"

    start_body = json.dumps({"req_id": req_id, "event": "spec_start", "summary": "start"}).encode()
    app.handle_openclaw_spec_turn_callback(start_body)

    review_body = json.dumps({
        "req_id": req_id,
        "event": "ai_review_pass",
        "review_summary": "Spec 质量达标",
    }).encode()
    app.handle_openclaw_review_result_callback(review_body)

    group_cards = [c for c in gateway.sent_cards if c[0] == "oc_testgroup123"]
    assert len(group_cards) >= 1
    # Card should reference both req doc and spec doc
    card_str = json.dumps(group_cards[-1][1])
    assert req_id in card_str
```

- [ ] **Step 2: Run new tests to verify they fail**

```bash
python -m pytest tests/test_spec_stage.py -k "spec_start_callback or spec_submit or spec_blocked or spec_locked or review_result_on_spec" -v 2>&1 | head -40
```

Expected: FAIL with AttributeError (handle_openclaw_spec_turn_callback not found)

- [ ] **Step 3: Register the /callbacks/openclaw/spec-turn endpoint in start_health_server**

In `src/requirement_workflow_v12/service_app.py`, in the `HealthHandler.do_POST` method, add before the `else: status, payload = 404` line:

```python
                elif self.path == "/callbacks/openclaw/spec-turn":
                    status, payload = app.handle_openclaw_spec_turn_callback(raw_body, headers=headers)
```

- [ ] **Step 4: Add handle_openclaw_spec_turn_callback method to service_app.py**

Add after `handle_openclaw_requirement_context_query` method (after line 975):

```python
    def handle_openclaw_spec_turn_callback(
        self,
        raw_body: bytes,
        *,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, object]]:
        auth_error = self._validate_openclaw_callback_auth(raw_body, headers=headers)
        if auth_error is not None:
            return auth_error
        try:
            payload = json.loads(raw_body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return 400, {"error": "invalid_json"}

        req_id = str(payload.get("req_id", "")).strip()
        event = str(payload.get("event", "")).strip()
        summary = str(payload.get("summary", "")).strip()
        spec_document_url_from_payload = str(payload.get("spec_document_url", "")).strip()

        if not req_id or not event or not summary:
            return 400, {"error": "invalid_payload", "message": "req_id、event、summary 为必填字段。"}

        supported_events = {"spec_start", "spec_submit"}
        if event not in supported_events:
            return 400, {"error": "invalid_payload", "message": f"不支持的 spec 事件：{event}。"}

        LOGGER.info("Received spec-turn callback req_id=%s event=%s", req_id, event)

        requirement = self.service.get_requirement(req_id)
        if requirement is None:
            return 404, {"error": "not_found", "message": f"未知需求：{req_id}"}

        if event == "spec_start":
            if requirement.status != WorkflowStatus.APPROVED:
                return 400, {
                    "error": "invalid_state",
                    "message": f"spec_start 只能在 APPROVED 状态执行，当前状态：{requirement.status.value}",
                }
            try:
                created_doc = self.gateway.create_spec_document(requirement)
            except Exception as exc:
                LOGGER.exception("Failed to create spec document for %s", req_id)
                return 500, {"error": "create_spec_document_failed", "message": str(exc)}

            spec_doc_id = created_doc.document_id if created_doc else ""
            spec_doc_url = created_doc.document_url if created_doc else ""

            try:
                requirement = self.service.submit_spec_start(
                    req_id,
                    spec_document_id=spec_doc_id,
                    spec_document_url=spec_doc_url,
                )
            except ValueError as exc:
                return 400, {"error": "invalid_state", "message": str(exc)}

            self._sync_requirement_outputs(requirement)
            self._save_state()
            LOGGER.info(
                "Spec start accepted req_id=%s status=%s spec_document_id=%s",
                req_id, requirement.status.value, spec_doc_id,
            )
            return 200, {
                "ok": True,
                "req_id": req_id,
                "status": requirement.status.value,
                "spec_document_id": requirement.spec_document_id,
                "spec_document_url": requirement.spec_document_url,
                "requirement_document_url": requirement.document_url,
            }

        if event == "spec_submit":
            if requirement.status != WorkflowStatus.SPEC_DRAFTING:
                return 400, {
                    "error": "invalid_state",
                    "message": f"spec_submit 只能在 SPEC_DRAFTING 状态执行，当前状态：{requirement.status.value}",
                }
            try:
                requirement = self.service.submit_spec_submit(req_id, summary=summary)
            except ValueError as exc:
                return 400, {"error": "invalid_state", "message": str(exc)}

            if spec_document_url_from_payload:
                requirement.spec_document_url = spec_document_url_from_payload

            reviewer_id = self.settings.spec_reviewer_feishu_id
            if reviewer_id:
                try:
                    self.gateway.send_text(
                        reviewer_id,
                        self._build_spec_review_handoff(requirement),
                        receive_id_type="open_id",
                    )
                except Exception as exc:
                    LOGGER.warning("Failed to notify spec reviewer req_id=%s: %s", req_id, exc)

            self._save_state()
            LOGGER.info("Spec submit accepted req_id=%s summary=%s", req_id, summary)
            return 200, {"ok": True, "message": "已通知 Spec Reviewer 开始审查"}

        return 400, {"error": "invalid_event"}
```

- [ ] **Step 5: Add _build_spec_review_handoff helper method**

Add after `_build_author_handoff_text` method (after line 1568):

```python
    def _build_spec_review_handoff(self, requirement: Requirement) -> str:
        return (
            f"请开始 Spec 审查 {requirement.req_id}\n"
            f"需求名称：{requirement.name}\n"
            f"Spec 文档：{requirement.spec_document_url or '（创建中）'}\n"
            f"需求文档：{requirement.document_url or '（待同步）'}\n\n"
            f"请按 6+2+1 维度审查，单次上报 ai_review_pass 或 ai_review_reject。"
        )
```

- [ ] **Step 6: Add spec-related triggers to _dispatch_transition_notifications and notification builders**

In `src/requirement_workflow_v12/service_app.py`, in `_dispatch_transition_notifications`, add BEFORE the existing targets loop:

```python
        # Spec Agent notification on APPROVED
        if trigger == "final_review_passed":
            spec_agent_id = self.settings.spec_agent_feishu_id
            if spec_agent_id:
                try:
                    self.gateway.send_text(
                        spec_agent_id,
                        (
                            f"请开始 Spec 撰写 {requirement.req_id}\n"
                            f"需求名称：{requirement.name}\n"
                            f"需求文档：{requirement.document_url or '（待同步）'}\n\n"
                            f"调用 spec_start callback 正式开始。"
                        ),
                        receive_id_type="open_id",
                    )
                except Exception as exc:
                    LOGGER.warning(
                        "Failed to notify spec agent for %s: %s", requirement.req_id, exc
                    )

        # Spec Agent notification on spec review reject
        if trigger == "spec_review_reject":
            spec_agent_id = self.settings.spec_agent_feishu_id
            if spec_agent_id:
                try:
                    self.gateway.send_text(
                        spec_agent_id,
                        (
                            f"Spec 审查未通过，请根据以下意见修改 {requirement.req_id}：\n\n"
                            f"{requirement.spec_review_summary}\n\n"
                            f"修改后重新调用 spec_submit 提交。"
                        ),
                        receive_id_type="open_id",
                    )
                except Exception as exc:
                    LOGGER.warning(
                        "Failed to notify spec agent for revision %s: %s", requirement.req_id, exc
                    )
```

- [ ] **Step 7: Add spec_locked and spec_review_reject to _transition_notification_content**

In `src/requirement_workflow_v12/service_app.py`, in `_transition_notification_content`, add before the final `return ("grey", "", "", "", "")` line:

```python
        if trigger == "spec_locked":
            return (
                "green",
                f"{requirement.req_id} Spec 已锁定",
                requirement.spec_review_summary or "Spec Reviewer 审查通过",
                "Spec 文档已锁定，可进入 Harness 生成阶段（卡点1a）。",
                "无需操作，流程自动继续。",
            )
        if trigger == "spec_review_reject":
            return (
                "orange",
                f"{requirement.req_id} Spec 审查未通过",
                requirement.spec_review_summary or "Spec 需要修改",
                "Spec Reviewer 判定当前文档未达到标准，已通知 Spec Agent 修改。",
                "等待 Spec Agent 修改后重新提交。",
            )
```

- [ ] **Step 8: Modify handle_openclaw_review_result_callback to use spec-aware triggers**

In `src/requirement_workflow_v12/service_app.py`, in `handle_openclaw_review_result_callback`, replace:

```python
            self._dispatch_transition_notifications(requirement, trigger=normalized_event)
```

with:

```python
            if requirement.status == WorkflowStatus.SPEC_LOCKED:
                self._dispatch_transition_notifications(requirement, trigger="spec_locked")
            elif requirement.status == WorkflowStatus.SPEC_DRAFTING and normalized_event == "ai_review_reject":
                self._dispatch_transition_notifications(requirement, trigger="spec_review_reject")
            else:
                self._dispatch_transition_notifications(requirement, trigger=normalized_event)
```

- [ ] **Step 9: Add spec_locked to the _build_transition_notification_card targets logic**

The existing `_dispatch_transition_notifications` sends cards to both `project_group_id` and `creator_user_id`. For `spec_locked`, we only want to send to `project_group_id` (it's an informational card, not an action card for the creator). Modify by wrapping the creator_user_id append:

In `_dispatch_transition_notifications`, change the targets-building block to:

```python
        targets: list[tuple[str, str]] = []
        if self._is_feishu_chat_id(requirement.project_group_id):
            targets.append((requirement.project_group_id, "chat_id"))
        if requirement.creator_user_id and trigger not in {"spec_locked", "spec_review_reject"}:
            targets.append((requirement.creator_user_id, self.settings.feishu_user_id_type))
```

- [ ] **Step 10: Add spec document link to the notification card for spec_locked**

In `_build_transition_notification_card`, add spec_document_url to the links after the existing links:

```python
        if hasattr(requirement, "spec_document_url") and requirement.spec_document_url and trigger == "spec_locked":
            links.append(f"[查看 Spec 文档]({requirement.spec_document_url})")
```

- [ ] **Step 11: Run all spec tests**

```bash
python -m pytest tests/test_spec_stage.py -v
```

Expected: all tests PASS

- [ ] **Step 12: Run full test suite**

```bash
python -m pytest tests/ -v --tb=short
```

Expected: all tests PASS

- [ ] **Step 13: Commit**

```bash
git add src/requirement_workflow_v12/service_app.py
git commit -m "feat: add spec-turn endpoint, spec notifications (APPROVED→Spec Agent, SPEC_LOCKED card, reject→revision)"
```

---

## Task 6: SKILL.md Files + staging.yml

**Files:**
- Create: `docs/agents/spec-author/SKILL.md`
- Create: `docs/agents/spec-reviewer/SKILL.md`
- Modify: `.github/workflows/staging.yml`

- [ ] **Step 1: Create docs/agents/spec-author/SKILL.md**

```bash
mkdir -p /Users/daxin/work/requirement-workflow-feishu/docs/agents/spec-author
```

Write file `docs/agents/spec-author/SKILL.md`:

```markdown
---
name: spec-author
description: Spec 撰写助手，按 9 节模板撰写技术规格文档，完成后上报 Coordinator。收到「请开始 Spec 撰写 REQ-xxx」时激活。
---

# Spec 撰写助手

## 启动流程

收到包含「请开始 Spec 撰写 REQ-xxx」的消息时启动。

**Step 1**：调 spec_start callback（不得跳过此步骤）

```bash
python3 /home/admin/.openclaw/bin/send_openclaw_callback.py \
  --req-id "{req_id}" \
  spec-start \
  --summary "开始 Spec 撰写"
```

响应结构为 `{"ok": true, "spec_document_id": "...", "spec_document_url": "...", "requirement_document_url": "..."}`。

从响应中获取：
- `spec_document_id`：Spec 飞书文档 token（用于写入 Spec）
- `spec_document_url`：Spec 文档 URL
- `requirement_document_url`：需求文档 URL（用于读取 8 字段）

> **项目级上下文消费声明**：本 Agent 消费 `spec_document_id`（Spec 文档写入）、`requirement_document_url`（需求 8 字段来源）。ARCHITECTURE.yaml 通过 fetch-context 返回的 `architecture_yaml_url` 获取，用于「架构设计」节的项目级上下文消费声明。

**Step 2**：使用 `feishu_fetch_doc` 读取需求文档（doc_token = `{requirement_document_url 中的 token}`），提取 8 个字段内容。

**Step 3**：逐节撰写 Spec（每节完成后 `feishu_update_doc` 写入完整文档）：

按以下 9 节顺序逐节填写：
1. 背景与目标（对应需求：问题描述 + 使用场景）
2. API 入参定义（对应需求：输入，必须包含字段名 + 类型 + 约束）
3. API 出参定义（对应需求：输出，必须包含字段名 + 类型 + 示例值）
4. 异常处理与边界条件（对应需求：边界）
5. 测试策略（对应需求：验收标准，每条 AC → Given/When/Then 格式）
6. 性能与可用性指标（对应需求：非功能要求，必须含量化数值）
7. 实现范围（对应需求：技术范围声明，明确 in/out of scope）
8. 架构设计（见下方子节要求）
9. 数据模型（新增或变更的表结构；无变更时填「无」）

### 架构设计节（第 8 节）必须包含以下 4 个子节：

**8.1 顶层架构背景**：参考 ARCHITECTURE.yaml，说明本需求涉及哪些已有服务/模块，变更属于新增/扩展/改造。

**8.2 项目级上下文消费声明**（必填，不得为空）：

| 上下文产物 | 版本/来源 | 影响本 Spec 的哪些判断 |
|-----------|---------|----------------------|
| ARCHITECTURE.yaml | {版本或日期} | 架构接合点选择、复用模块确认 |
| ACM 注册表（历史约束） | {快照日期} | 兼容性分析 |

**8.3 关键架构决策**：每条含"决策 + 依据 + 影响"三要素。

**8.4 存储与数据流设计**：输入来源 → 处理层 → 存储 → 输出方式。

**Step 4**：9 节均完成后调 spec_submit callback：

```bash
python3 /home/admin/.openclaw/bin/send_openclaw_callback.py \
  --req-id "{req_id}" \
  spec-submit \
  --summary "Spec 初稿完成，9节均已填写" \
  --spec-document-url "{spec_document_url}"
```

## 不允许的行为

- 不修改需求文档（只读）
- 不跳过任何节（9节全部必须非空）
- 不跳过 spec_start 步骤（必须先调 callback 拿到文档 token）
- 「项目级上下文消费声明」子节不得为空
- 「数据模型」节无数据库变更时填「无」，不得省略
```

- [ ] **Step 2: Create docs/agents/spec-reviewer/SKILL.md**

```bash
mkdir -p /Users/daxin/work/requirement-workflow-feishu/docs/agents/spec-reviewer
```

Write file `docs/agents/spec-reviewer/SKILL.md`:

```markdown
---
name: spec-reviewer
description: Spec 审查助手，按 6+2+1 维度审查 Spec 文档质量，单次上报 pass/reject 结论，不与用户多轮沟通。
---

# Spec 审查助手

## 启动流程

收到包含 `req_id` 和 Spec 文档信息的审查请求时启动。

**Step 1**：查询需求上下文（不得跳过此步骤）

```bash
python3 /home/admin/.openclaw/bin/send_openclaw_callback.py --req-id "{req_id}" fetch-context
```

从 `context` 中获取：
- `spec_document_id`：Spec 文档 token
- `document_url`：需求文档 URL
- `spec_review_summary`：上次审查结论（若有，参考历史问题是否已修正）

> **项目级上下文消费声明**：本 Agent 消费 `spec_document_id`（Spec 文档读取）、`document_url`（需求文档对照）、`spec_review_summary`（历史问题追踪）。不消费 ARCHITECTURE.yaml（架构一致性由 Spec 文档内的「项目级上下文消费声明」子节声明）。

**Step 2**：使用 `feishu_fetch_doc` 读取 Spec 文档（doc_token = `{spec_document_id}`）和需求文档。

**Step 3**：按 6+2+1 维度逐一检查（见下方定义）。

## 6+2+1 审查维度

### 阻断维度（任一不通过则 reject）

**维度 1：需求字段全覆盖**
9节均非空，且每节能与需求文档对应字段对应。
不通过：列出空缺节名。

**维度 2：API 具体性**
入参/出参有字段名 + 类型，无「返回成功」等模糊描述。
不通过：指出模糊描述位置。

**维度 3：测试用例与 AC 对齐**
每条需求验收标准有对应测试用例（Given/When/Then 格式）。
不通过：标出未覆盖的 AC。

**维度 4：实现范围无歧义**
「实现范围」节明确哪些模块改/不改，无「可能涉及」类表述。
不通过：指出模糊描述。

**维度 5：数据模型存在性**
涉及存储变更的需求必须有表/模型定义；否则填「无」。
不通过：指出缺失位置。

**维度 6：内部一致性**
API 入参与测试用例中使用的字段名一致，无矛盾。
不通过：指出具体冲突点。

**维度 7（上下文消费声明完整性）**
「架构设计」节中「项目级上下文消费声明」子节非空，至少列出 ARCHITECTURE.yaml 的消费记录。
不通过：说明该子节为空或缺失，要求补充。

### 警告维度（不通过记入 weak_fields，仍可 pass）

**维度 8：性能指标量化**
非功能要求有具体数字（P99 < Xs / QPS > N / 可用性 99.x%）。
不通过：记入 weak_fields。

**维度 9：风险点识别**
至少一个技术风险 + 应对策略。
不通过：记入 weak_fields。

## 输出

审查完成后，发送 callback：

**通过（ai_review_pass）**：

```bash
python3 /home/admin/.openclaw/bin/send_openclaw_callback.py \
  --req-id "{req_id}" \
  review-event \
  --event ai_review_pass \
  --summary "<整体结论一句话，含通过原因>"
```

**未通过（ai_review_reject）**：

```bash
python3 /home/admin/.openclaw/bin/send_openclaw_callback.py \
  --req-id "{req_id}" \
  review-event \
  --event ai_review_reject \
  --summary "<整体结论一句话，含具体问题>"
```

## 不允许的行为

- 不修改任何文档
- 不与用户多轮沟通（单次审查，直接上报）
- 不跳过上下文读取步骤
- event 只能是 `ai_review_pass` 或 `ai_review_reject`
```

- [ ] **Step 3: Add 3 env vars to staging.yml**

In `.github/workflows/staging.yml`, add after the `STATE_STORE_PATH` line inside the `.env` heredoc:

```yaml
            OPENCLAW_SPEC_AGENT_NAME=${{ secrets.OPENCLAW_SPEC_AGENT_NAME || 'Spec 撰写助手' }}
            SPEC_AGENT_FEISHU_ID=${{ secrets.SPEC_AGENT_FEISHU_ID }}
            SPEC_REVIEWER_FEISHU_ID=${{ secrets.SPEC_REVIEWER_FEISHU_ID }}
```

- [ ] **Step 4: Add spec-turn and spec-reviewer modes to send_openclaw_callback.py (documentation note)**

The server-side script at `/home/admin/.openclaw/bin/send_openclaw_callback.py` needs `spec-start` and `spec-submit` sub-commands. The implementation mirrors the existing `author-ready` and `review-event` commands:

```
spec-start: POST /callbacks/openclaw/spec-turn with {"req_id": ..., "event": "spec_start", "summary": ...}
spec-submit: POST /callbacks/openclaw/spec-turn with {"req_id": ..., "event": "spec_submit", "summary": ..., "spec_document_url": ...}
```

This is updated on the server separately (not in this repo). Refer to existing `author-ready`/`review-event` modes as the pattern.

- [ ] **Step 5: Run full test suite**

```bash
python -m pytest tests/ -v --tb=short
```

Expected: all tests PASS

- [ ] **Step 6: Commit all remaining files**

```bash
git add docs/agents/spec-author/SKILL.md docs/agents/spec-reviewer/SKILL.md .github/workflows/staging.yml
git commit -m "feat: add spec-author and spec-reviewer SKILL.md; add Spec agent env vars to staging.yml"
```

---

## Self-Review Checklist

After all tasks complete, verify against spec:

| Spec Requirement | Implemented In |
|----------------|---------------|
| SPEC_DRAFTING / SPEC_LOCKED status values | Task 1 models.py |
| SPEC_START event + 3 transitions | Task 1 state_machine.py |
| spec_document_id / spec_document_url / spec_review_summary on Requirement | Task 1 models.py |
| 3 new Settings fields | Task 2 config.py |
| spec fields load/save in store | Task 2 store.py |
| _save_state persists project_configs | Task 2 service_app.py |
| submit_spec_start transitions APPROVED→SPEC_DRAFTING | Task 3 coordinator_service.py |
| submit_spec_submit stores summary (no state change) | Task 3 coordinator_service.py |
| review-result branches on SPEC_DRAFTING status | Task 3 coordinator_service.py |
| context query returns spec fields | Task 3 coordinator_service.py |
| create_spec_document creates Feishu doc | Task 4 feishu_gateway.py |
| /callbacks/openclaw/spec-turn endpoint | Task 5 service_app.py |
| spec_start handler: create doc + transition | Task 5 service_app.py |
| spec_submit handler: notify reviewer | Task 5 service_app.py |
| APPROVED → spec agent notification | Task 5 service_app.py |
| SPEC_LOCKED → 卡点1a card to project group | Task 5 service_app.py |
| spec_review_reject → spec agent revision notification | Task 5 service_app.py |
| spec-author SKILL.md (9-section template) | Task 6 |
| spec-reviewer SKILL.md (6+2+1 dimensions) | Task 6 |
| staging.yml 3 new env vars | Task 6 |
