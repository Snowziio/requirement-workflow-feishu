# Plan-Wiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the PLANNING phase into the Feishu card flow so `APPROVED → Plan 撰写 → Plan READY → Spec 撰写` becomes the only path — no more direct jump from APPROVED to Spec.

**Architecture:** The PLANNING state machine, HTTP endpoints (`/openclaw/plan-context`, `/openclaw/plan-callback`), and `service.plan_submit` + GitHub-commit hook already exist. This plan **only** adds card-flow handlers + swaps the behavior of the plan-callback `plan_submit` branch from auto-commit to draft-buffering (`pending_plan_review`) + review-card push. Approval via the card then drives `service.plan_submit()` as before.

**Tech Stack:** Python 3.11, Feishu lark_oapi card v2, `pytest` + `unittest.mock.MagicMock`, append to existing `CoordinatorRuntimeApp` in `src/requirement_workflow_v12/service_app.py`.

**Reference:** Design spec at `docs/superpowers/specs/2026-04-21-plan-wiring-design.md`. MVP scope only — `architecture_change=None`; no `AUTH_PENDING`; no auto-DM on reject.

---

## Pre-flight

Before starting, confirm on a clean worktree:

- [ ] Run `pytest -q` — record the current green baseline count (there should be ~0 failures on `main`).
- [ ] `grep -n 'pending_plan_draft' src/requirement_workflow_v12/coordinator_service.py` — confirm 5 hits at lines 823, 829, 880, 904, 921. This field is used internally by `plan_submit()`; do **NOT** touch it. Our new field is `pending_plan_review`.
- [ ] Read `docs/superpowers/specs/2026-04-21-plan-wiring-design.md` once cover-to-cover.

---

## Task 1: Add `pending_plan_review` field to Requirement

**Files:**
- Modify: `src/requirement_workflow_v12/models.py` (add field ~line 134)
- Test: `tests/test_models_plan_review_field.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_models_plan_review_field.py`:
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.models import Requirement


def test_pending_plan_review_defaults_to_none():
    r = Requirement(req_id="R1", name="n", project="P", summary="s", creator="c")
    assert r.pending_plan_review is None


def test_pending_plan_review_is_independent_of_pending_plan_draft():
    r = Requirement(req_id="R1", name="n", project="P", summary="s", creator="c")
    r.pending_plan_draft = {"plan_md_content": "x"}
    r.pending_plan_review = {"plan_md_content": "y", "project_context_change": None}
    assert r.pending_plan_draft["plan_md_content"] == "x"
    assert r.pending_plan_review["plan_md_content"] == "y"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_models_plan_review_field.py -v`
Expected: `AttributeError: 'Requirement' object has no attribute 'pending_plan_review'` (test errors on first case).

- [ ] **Step 3: Add the field**

Modify `src/requirement_workflow_v12/models.py`. Find line 134:
```python
    pending_plan_draft: dict | None = None
```
Add immediately after:
```python
    pending_plan_review: dict | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_models_plan_review_field.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/models.py tests/test_models_plan_review_field.py
git commit -m "feat(models): add pending_plan_review field to Requirement"
```

---

## Task 2: Drop `needs_ui` guard from `plan_start`

**Files:**
- Modify: `src/requirement_workflow_v12/coordinator_service.py:801-805`
- Test: `tests/test_coordinator_plan.py` (append)

- [ ] **Step 1: Write the failing test**

Find the end of `tests/test_coordinator_plan.py` and append:
```python
def test_plan_start_does_not_require_design_ready_when_needs_ui_true():
    from requirement_workflow_v12.coordinator_service import CoordinatorService
    from requirement_workflow_v12.models import Requirement, WorkflowStatus
    from requirement_workflow_v12.plan_state_machine import PlanStatus, PlanPhase

    svc = CoordinatorService()
    r = Requirement(req_id="R-UI", name="n", project="P", summary="s", creator="c")
    r.status = WorkflowStatus.APPROVED
    r.needs_ui = True
    r.design_status = None  # no design flow exists yet
    svc.requirements["R-UI"] = r

    result = svc.plan_start("R-UI")

    assert result.plan_status == PlanStatus.DRAFTING
    assert result.plan_phase == PlanPhase.OUTLINE_PENDING
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_coordinator_plan.py::test_plan_start_does_not_require_design_ready_when_needs_ui_true -v`
Expected: `ValueError: plan_start requires design_status=READY when needs_ui=True, got design_status=None`.

- [ ] **Step 3: Drop the guard**

Modify `src/requirement_workflow_v12/coordinator_service.py`. Find lines 801-805:
```python
        if r.needs_ui and r.design_status != DesignStatus.READY:
            raise ValueError(
                f"plan_start requires design_status=READY when needs_ui=True, "
                f"got design_status={r.design_status}"
            )
```
Delete the whole block. Check imports — if `DesignStatus` is no longer referenced anywhere in this file, remove the import. (Run `grep -n DesignStatus src/requirement_workflow_v12/coordinator_service.py` to verify. Leave the import if any other code path uses it.)

- [ ] **Step 4: Run tests to verify**

Run: `pytest tests/test_coordinator_plan.py -v`
Expected: all previously-passing tests still pass, plus the new one.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/coordinator_service.py tests/test_coordinator_plan.py
git commit -m "refactor(coordinator): drop needs_ui/design_status coupling from plan_start"
```

---

## Task 3: Add `_build_plan_author_handoff_text` helper

**Files:**
- Modify: `src/requirement_workflow_v12/service_app.py` (insert near `_build_spec_author_handoff_text` at line 2267)
- Test: `tests/test_service_app_plan_wiring.py` (new — test fixture + first test)

- [ ] **Step 1: Create the shared test fixture file**

Create `tests/test_service_app_plan_wiring.py`:
```python
"""Tests for plan-wiring card flow in service_app."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.config import Settings
from requirement_workflow_v12.coordinator_service import CoordinatorService
from requirement_workflow_v12.models import Requirement, WorkflowStatus
from requirement_workflow_v12.plan_state_machine import PlanStatus, PlanPhase
from requirement_workflow_v12.project_config import ProjectConfig
from requirement_workflow_v12.service_app import CoordinatorRuntimeApp
from requirement_workflow_v12.store import JsonStateStore


@pytest.fixture
def app(tmp_path):
    settings = Settings(
        feishu_app_id="x", feishu_app_secret="y",
        feishu_verification_token="t", feishu_encrypt_key="",
        state_store_path=str(tmp_path / "state.json"),
        spec_trace_dir=str(tmp_path / "trace"),
        github_token="",
    )
    svc = CoordinatorService()
    store = JsonStateStore(settings.state_store_path)
    gw = MagicMock()
    gw.list_project_configs.return_value = {}
    gw.upsert_project_config.return_value = None
    gw.bitable_url.return_value = ""
    return CoordinatorRuntimeApp(
        settings=settings, store=store, service=svc, gateway=gw,
    )


def _approved_req(app, req_id="REQ-PW-1"):
    r = Requirement(
        req_id=req_id, name="Plan-Wiring Demo", project="P", summary="s", creator="c",
    )
    r.status = WorkflowStatus.APPROVED
    r.creator_user_id = "ou_alice"
    app.service.requirements[req_id] = r
    app.service.project_configs["P"] = ProjectConfig(
        category="web", template_version="v1",
        architecture_doc_id="", architecture_doc_url="",
        tech_stack={"backend": "py"}, github_repo_url="o/r",
    )
    return r


def _operator() -> dict:
    return {"open_id": "ou_alice", "name": "Alice"}


def _card_payload(action: str, req_id: str, **extra) -> dict:
    value = {"action": action, "req_id": req_id, **extra}
    return {
        "operator": _operator(),
        "context": {"open_chat_id": "oc_x", "open_message_id": "om_1"},
        "action": {"value": value, "form_value": {}},
    }


def test_build_plan_author_handoff_text_contains_agent_and_req(app):
    r = _approved_req(app)
    r.document_url = "https://feishu.example/req-doc"

    text = app._build_plan_author_handoff_text(r)

    agent_name = app.settings.openclaw_plan_author_agent_name
    assert agent_name in text
    assert r.req_id in text
    assert r.name in text
    assert "https://feishu.example/req-doc" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_service_app_plan_wiring.py::test_build_plan_author_handoff_text_contains_agent_and_req -v`
Expected: `AttributeError: 'CoordinatorRuntimeApp' object has no attribute '_build_plan_author_handoff_text'`
(May also fail earlier if `openclaw_plan_author_agent_name` isn't on Settings — if so, proceed to Step 3 which adds both.)

- [ ] **Step 3: Add `openclaw_plan_author_agent_name` to Settings if missing**

Run `grep -n openclaw_plan_author_agent_name src/requirement_workflow_v12/config.py`. If zero hits, add it.

Open `src/requirement_workflow_v12/config.py`. Find line 39:
```python
    openclaw_spec_agent_name: str = os.environ.get("OPENCLAW_SPEC_AGENT_NAME", "Spec 撰写助手")
```
Immediately after it, add:
```python
    openclaw_plan_author_agent_name: str = os.environ.get("OPENCLAW_PLAN_AUTHOR_AGENT_NAME", "Plan Author")
```
This mirrors the existing pattern (lines 29, 30, 39). No extra wiring needed — `Settings` is a dataclass whose defaults are read at instantiation.

- [ ] **Step 4: Add the helper method**

Modify `src/requirement_workflow_v12/service_app.py`. Find `_build_spec_author_handoff_text` at line 2267. Insert **above** it:
```python
    def _build_plan_author_handoff_text(self, requirement: Requirement) -> str:
        agent_name = self.settings.openclaw_plan_author_agent_name
        return (
            f"请私聊 {agent_name}，并发送以下完整上下文：\n\n"
            f"请开始 Plan 撰写 {requirement.req_id}\n"
            f"需求名称：{requirement.name}\n"
            f"需求文档：{requirement.document_url or '（待同步）'}"
        )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_service_app_plan_wiring.py::test_build_plan_author_handoff_text_contains_agent_and_req -v`
Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add src/requirement_workflow_v12/config.py src/requirement_workflow_v12/service_app.py tests/test_service_app_plan_wiring.py
git commit -m "feat(service-app): add _build_plan_author_handoff_text helper"
```

---

## Task 4: `send_plan_author_start` card action handler

**Files:**
- Modify: `src/requirement_workflow_v12/service_app.py` (insert above `send_spec_author_start` at line 1543)
- Test: `tests/test_service_app_plan_wiring.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_service_app_plan_wiring.py`:
```python
def test_send_plan_author_start_transitions_state_and_dispatches_dm(app):
    r = _approved_req(app)
    app.gateway.user_id_from_open_id = MagicMock(return_value=("ou_alice", "open_id"))

    status, resp = app._handle_card_action_payload(
        _card_payload("send_plan_author_start", r.req_id)
    )

    assert status == 200
    assert resp.get("toast", {}).get("type") == "success"
    assert r.plan_status == PlanStatus.DRAFTING
    assert r.plan_phase == PlanPhase.OUTLINE_PENDING
    app.gateway.send_text.assert_called_once()
    send_args = app.gateway.send_text.call_args
    text = send_args.args[1]
    assert "Plan 撰写" in text
    assert r.req_id in text


def test_send_plan_author_start_rejects_when_not_approved(app):
    r = _approved_req(app)
    r.status = WorkflowStatus.DRAFTING

    status, resp = app._handle_card_action_payload(
        _card_payload("send_plan_author_start", r.req_id)
    )

    assert status == 200
    assert resp.get("toast", {}).get("type") == "error"
    assert r.plan_status is None
    app.gateway.send_text.assert_not_called()


def test_send_plan_author_start_unknown_req_id_returns_error_toast(app):
    status, resp = app._handle_card_action_payload(
        _card_payload("send_plan_author_start", "NOPE")
    )
    assert status == 200
    assert resp.get("toast", {}).get("type") == "error"
    app.gateway.send_text.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_service_app_plan_wiring.py -v -k send_plan_author_start`
Expected: all three fail — the action is unrecognized, so `_handle_card_action_payload` falls through to the default `unknown_action` branch (not asserting DRAFTING on requirement, not sending DM).

- [ ] **Step 3: Add the handler**

Modify `src/requirement_workflow_v12/service_app.py`. Find line 1543:
```python
        if action_name == "send_spec_author_start":
```
Insert **above** it:
```python
        if action_name == "send_plan_author_start":
            req_id = value.get("req_id", "")
            if not req_id:
                return 200, {"toast": {"type": "error", "content": "缺少需求ID。"}}
            requirement = self.service.get_requirement(req_id)
            if requirement is None:
                return 200, {"toast": {"type": "error", "content": f"未知需求：{req_id}。"}}
            if requirement.status != WorkflowStatus.APPROVED:
                return 200, {"toast": {"type": "error", "content": f"当前需求不处于 APPROVED 阶段（status={requirement.status.value}），不能启动 Plan 撰写。"}}
            try:
                self.service.plan_start(req_id)
            except ValueError as exc:
                return 200, {"toast": {"type": "error", "content": f"Plan 启动失败：{exc}"}}
            self._save_state()
            target_user_id, receive_id_type = self._resolve_operator_receive_target(operator)
            if not target_user_id:
                return 200, {"toast": {"type": "error", "content": "无法识别当前点击人身份，请手动私聊 Plan 撰写助手。"}}
            try:
                self.gateway.send_text(
                    target_user_id,
                    self._build_plan_author_handoff_text(requirement),
                    receive_id_type=receive_id_type,
                )
            except Exception as exc:
                LOGGER.warning("Failed to send plan author handoff req_id=%s: %s", req_id, exc)
                return 200, {"toast": {"type": "error", "content": "私发失败，请手动私聊 Plan 撰写助手。"}}
            return 200, {"toast": {"type": "success", "content": "已将 Plan 撰写启动指令私发给你。"}}

```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_service_app_plan_wiring.py -v -k send_plan_author_start`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/service_app.py tests/test_service_app_plan_wiring.py
git commit -m "feat(service-app): add send_plan_author_start card handler"
```

---

## Task 5: Flip `final_review_passed` card button + content to drive Plan

**Files:**
- Modify: `src/requirement_workflow_v12/service_app.py:2503-2511` (button) and `:2577-2585` (content)
- Test: `tests/test_service_app_plan_wiring.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_service_app_plan_wiring.py`:
```python
def test_final_review_passed_card_has_plan_button(app):
    r = _approved_req(app)

    actions = app._build_transition_notification_actions(r, trigger="final_review_passed")

    assert len(actions) == 1
    assert actions[0]["value"]["action"] == "send_plan_author_start"
    assert "Plan 撰写" in actions[0]["text"]["content"]


def test_final_review_passed_card_content_mentions_plan(app):
    r = _approved_req(app)
    template, title, reason, result, next_action = app._transition_notification_content(
        r, trigger="final_review_passed"
    )
    assert "Plan" in next_action
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_service_app_plan_wiring.py -v -k final_review_passed_card`
Expected: first test fails (button still says `send_spec_author_start` / "开始 Spec 撰写"); second test fails (next_action mentions "Spec" not "Plan").

- [ ] **Step 3: Swap the button**

Modify `src/requirement_workflow_v12/service_app.py`. Find line 2503:
```python
        if trigger == "final_review_passed":
            return [
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "开始 Spec 撰写"},
                    "type": "primary",
                    "value": {"action": "send_spec_author_start", "req_id": requirement.req_id},
                },
            ]
```
Replace with:
```python
        if trigger == "final_review_passed":
            return [
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "开始 Plan 撰写"},
                    "type": "primary",
                    "value": {"action": "send_plan_author_start", "req_id": requirement.req_id},
                },
            ]
```

- [ ] **Step 4: Update the card copy**

In the same file, find line 2577:
```python
        if trigger == "final_review_passed":
            spec_agent_name = self.settings.openclaw_spec_agent_name
            return (
                "green",
                f"{requirement.req_id} 已批准通过",
                latest_review,
                "正式审查已通过，需求进入 Spec 撰写阶段。",
                f"请点击「开始 Spec 撰写」，将启动指令私发给自己后转发给 {spec_agent_name}。",
            )
```
Replace with:
```python
        if trigger == "final_review_passed":
            plan_agent_name = self.settings.openclaw_plan_author_agent_name
            return (
                "green",
                f"{requirement.req_id} 已批准通过",
                latest_review,
                "正式审查已通过，需求进入 Plan 撰写阶段。",
                f"请点击「开始 Plan 撰写」，将启动指令私发给自己后转发给 {plan_agent_name}。",
            )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_service_app_plan_wiring.py -v -k final_review_passed_card`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add src/requirement_workflow_v12/service_app.py tests/test_service_app_plan_wiring.py
git commit -m "feat(service-app): flip final_review_passed card to launch Plan 撰写"
```

---

## Task 6: Change plan-callback `plan_submit` branch to buffer draft

**Files:**
- Modify: `src/requirement_workflow_v12/service_app.py:1224-1237` (plan-callback handler)
- Test: `tests/test_plan_endpoint_service_app.py` (append new tests; **replace** existing `test_plan_callback_plan_submit_*` test if it asserts READY)

- [ ] **Step 1: Rewrite the one existing test that asserts the old semantics**

The test `test_plan_callback_plan_submit_branches_to_ready_when_no_architecture` at `tests/test_plan_endpoint_service_app.py:96-114` currently asserts `r.plan_status is PlanStatus.READY` after a `plan_submit` callback. That's the **old** semantics. Replace the entire function body with:
```python
def test_plan_callback_plan_submit_branches_to_ready_when_no_architecture(app):
    """After 2026-04-21 plan-wiring: plan_submit callback buffers into
    pending_plan_review; state remains DRAFTING until human approves via card."""
    r = _approved_req(app)
    app.service.plan_start(r.req_id)

    body = {
        "req_id": "REQ-P-1",
        "event": "plan_submit",
        "payload": {
            "plan_md_content": "---\nreq_id: REQ-P-1\n---\n",
            "architecture_change": None,
        },
    }
    status, resp = app.handle_openclaw_plan_callback(body)

    from requirement_workflow_v12.plan_state_machine import PlanStatus, PlanPhase
    assert status == 200
    assert r.plan_status is PlanStatus.DRAFTING
    assert r.plan_phase is PlanPhase.FINAL_REVIEW_PENDING
    assert r.pending_plan_review is not None
```

Also verify `test_plan_callback_unknown_event_returns_400` and `test_plan_callback_req_not_found_returns_404` still make sense — they should (the 404 path returns before the event switch, the 400 path hits the fall-through `return 400`). No edits needed there.

- [ ] **Step 2: Append the new failing tests**

At the **end** of `tests/test_plan_endpoint_service_app.py`, append:

```python
def test_plan_callback_plan_submit_buffers_draft_and_keeps_drafting(app):
    r = _approved_req(app, req_id="REQ-PB-1")
    app.service.plan_start(r.req_id)

    body = {
        "req_id": r.req_id,
        "event": "plan_submit",
        "payload": {
            "plan_md_content": "# plan\n...",
            "project_context_change": None,
        },
    }
    status, resp = app.handle_openclaw_plan_callback(body)

    assert status == 200
    from requirement_workflow_v12.plan_state_machine import PlanStatus, PlanPhase
    assert r.plan_status == PlanStatus.DRAFTING  # NOT READY — review pending
    assert r.plan_phase == PlanPhase.FINAL_REVIEW_PENDING
    assert r.pending_plan_review is not None
    assert r.pending_plan_review["plan_md_content"] == "# plan\n..."
    assert r.pending_plan_review["project_context_change"] is None
    assert "submitted_at" in r.pending_plan_review


def test_plan_callback_plan_submit_dispatches_review_notification(app):
    r = _approved_req(app, req_id="REQ-PB-2")
    app.service.plan_start(r.req_id)

    body = {
        "req_id": r.req_id,
        "event": "plan_submit",
        "payload": {"plan_md_content": "# plan", "project_context_change": None},
    }
    app.handle_openclaw_plan_callback(body)

    # Either send_card or send_text was called at least once with the review trigger
    assert app.gateway.send_card.called or app.gateway.send_text.called


def test_plan_callback_plan_submit_retry_overwrites_pending(app):
    r = _approved_req(app, req_id="REQ-PB-3")
    app.service.plan_start(r.req_id)

    app.handle_openclaw_plan_callback({
        "req_id": r.req_id, "event": "plan_submit",
        "payload": {"plan_md_content": "v1", "project_context_change": None},
    })
    first_submitted = r.pending_plan_review["submitted_at"]

    app.handle_openclaw_plan_callback({
        "req_id": r.req_id, "event": "plan_submit",
        "payload": {"plan_md_content": "v2", "project_context_change": None},
    })

    assert r.pending_plan_review["plan_md_content"] == "v2"
    # submitted_at should be re-stamped (may equal if called in same millisecond, so just assert string exists)
    assert r.pending_plan_review["submitted_at"] is not None
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_plan_endpoint_service_app.py -v -k plan_submit`
Expected: new tests fail because current handler transitions to READY and clears pending_plan_review doesn't exist on the field side (Task 1 added the field — if Task 1 is skipped these also fail on AttributeError).

- [ ] **Step 4: Rewrite the plan-callback `plan_submit` branch**

Modify `src/requirement_workflow_v12/service_app.py`. Find lines 1224-1237:
```python
            if event == "plan_submit":
                self.service.plan_submit(
                    req_id,
                    plan_md_content=payload.get("plan_md_content", ""),
                    project_context_change=(
                        payload.get("project_context_change")
                        or payload.get("architecture_change")
                    ),
                )
                self._save_state()
                return 200, {
                    "req_id": req_id,
                    "plan_status": r.plan_status.value if r.plan_status else None,
                }
```
Replace with:
```python
            if event == "plan_submit":
                if r.plan_status != PlanStatus.DRAFTING:
                    return 409, {
                        "error": "invalid_state",
                        "message": f"plan_submit requires plan_status=DRAFTING, got {r.plan_status.value if r.plan_status else 'None'}",
                    }
                r.pending_plan_review = {
                    "plan_md_content": payload.get("plan_md_content", ""),
                    "project_context_change": (
                        payload.get("project_context_change")
                        or payload.get("architecture_change")
                    ),
                    "submitted_at": utc_now().isoformat(),
                }
                r.plan_phase = PlanPhase.FINAL_REVIEW_PENDING
                self._save_state()
                self._dispatch_transition_notifications(
                    r, trigger="plan_submitted_pending_review"
                )
                return 200, {
                    "req_id": req_id,
                    "plan_status": r.plan_status.value,
                    "plan_phase": r.plan_phase.value,
                }
```

Add the imports at the top of the file if missing. Check:
```bash
grep -n 'from .plan_state_machine' src/requirement_workflow_v12/service_app.py
grep -n 'utc_now' src/requirement_workflow_v12/service_app.py
```
If `PlanStatus, PlanPhase` are not imported, add: `from .plan_state_machine import PlanStatus, PlanPhase`. If `utc_now` is not imported, add: `from .models import utc_now` (the helper is defined in `models.py`).

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_plan_endpoint_service_app.py -v -k plan_submit`
Expected: 3 new passed + any rewritten existing passes.

Then run: `pytest tests/test_plan_endpoint_service_app.py tests/test_coordinator_plan.py tests/test_service_app_plan_wiring.py -v`
Expected: full green on these three files.

- [ ] **Step 6: Commit**

```bash
git add src/requirement_workflow_v12/service_app.py tests/test_plan_endpoint_service_app.py
git commit -m "feat(service-app): plan-callback plan_submit buffers to pending_plan_review"
```

---

## Task 7: `plan_submitted_pending_review` notification trigger

**Files:**
- Modify: `src/requirement_workflow_v12/service_app.py` — `_transition_notification_content` (~line 2532) and `_build_transition_notification_actions` (~line 2467)
- Test: `tests/test_service_app_plan_wiring.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_service_app_plan_wiring.py`:
```python
def test_plan_submitted_pending_review_content_and_actions(app):
    r = _approved_req(app)

    template, title, reason, result, next_action = app._transition_notification_content(
        r, trigger="plan_submitted_pending_review"
    )
    assert title  # non-empty
    assert "Plan" in title
    assert "审查" in result or "审查" in next_action

    actions = app._build_transition_notification_actions(r, trigger="plan_submitted_pending_review")
    action_names = {a["value"]["action"] for a in actions}
    assert action_names == {"approve_plan_submit", "reject_plan_submit"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_service_app_plan_wiring.py -v -k plan_submitted_pending_review`
Expected: fails — trigger falls through to the grey `("grey", "", "", "", "")` default; actions list is empty.

- [ ] **Step 3: Add content branch**

Modify `src/requirement_workflow_v12/service_app.py`. In `_transition_notification_content`, find the final `return ("grey", "", "", "", "")` at approximately line 2627. Insert **above** it:
```python
        if trigger == "plan_submitted_pending_review":
            return (
                "indigo",
                f"{requirement.req_id} Plan 已提交，待审查",
                "Plan Author 已完成 plan.md 终稿提交。",
                "Plan 文档已进入最终审查阶段，等待需求提出者裁决。",
                "请 review plan.md 内容后，点击「通过」提交 PR，或「需要修改」驳回重写。",
            )
```

- [ ] **Step 4: Add action buttons**

In the same file, in `_build_transition_notification_actions` (between `spec_review_reject` at line 2521 and the final `return []`), insert:
```python
        if trigger == "plan_submitted_pending_review":
            return [
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "通过"},
                    "type": "primary",
                    "value": {"action": "approve_plan_submit", "req_id": requirement.req_id},
                },
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "需要修改"},
                    "type": "default",
                    "value": {"action": "reject_plan_submit", "req_id": requirement.req_id},
                },
            ]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_service_app_plan_wiring.py -v -k plan_submitted_pending_review`
Expected: passed.

- [ ] **Step 6: Commit**

```bash
git add src/requirement_workflow_v12/service_app.py tests/test_service_app_plan_wiring.py
git commit -m "feat(service-app): add plan_submitted_pending_review notification"
```

---

## Task 8: `approve_plan_submit` card handler

**Files:**
- Modify: `src/requirement_workflow_v12/service_app.py` (new handler block near the other plan/spec handlers)
- Test: `tests/test_service_app_plan_wiring.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_service_app_plan_wiring.py`:
```python
def _seed_pending_review(app, r, *, with_acc=False):
    """Drive a requirement to plan_status=DRAFTING + pending_plan_review set."""
    app.service.plan_start(r.req_id)
    r.plan_phase = PlanPhase.FINAL_REVIEW_PENDING
    r.pending_plan_review = {
        "plan_md_content": "# plan\n...",
        "project_context_change": {"foo": "bar"} if with_acc else None,
        "submitted_at": "2026-04-21T00:00:00+00:00",
    }
    return r


def test_approve_plan_submit_transitions_to_ready_and_clears_pending(app):
    r = _seed_pending_review(app, _approved_req(app))

    # Stub the hook's tool to prevent real GitHub calls; see configure_plan_hooks.
    class _StubTools:
        def commit_plan_artifacts(self, artifacts):
            from requirement_workflow_v12.project_repo import PlanCommitResult
            return PlanCommitResult(commit_sha="https://github.com/o/r/pull/1")
    app.service.configure_plan_hooks(tools=_StubTools())

    status, resp = app._handle_card_action_payload(
        _card_payload("approve_plan_submit", r.req_id)
    )

    assert status == 200
    assert resp.get("toast", {}).get("type") == "success"
    assert r.plan_status == PlanStatus.READY
    assert r.pending_plan_review is None
    assert r.plan_pr_url == "https://github.com/o/r/pull/1"


def test_approve_plan_submit_rejects_if_no_pending(app):
    r = _approved_req(app)
    app.service.plan_start(r.req_id)  # plan_phase=OUTLINE_PENDING, no pending review

    status, resp = app._handle_card_action_payload(
        _card_payload("approve_plan_submit", r.req_id)
    )

    assert status == 200
    assert resp.get("toast", {}).get("type") == "error"
    assert r.plan_status == PlanStatus.DRAFTING


def test_approve_plan_submit_rejects_architecture_change(app):
    r = _seed_pending_review(app, _approved_req(app), with_acc=True)

    status, resp = app._handle_card_action_payload(
        _card_payload("approve_plan_submit", r.req_id)
    )

    assert status == 200
    assert resp.get("toast", {}).get("type") == "error"
    assert r.plan_status == PlanStatus.DRAFTING
    assert r.pending_plan_review is not None  # retained


def test_approve_plan_submit_retains_pending_on_service_error(app):
    r = _seed_pending_review(app, _approved_req(app))

    class _FailingTools:
        def commit_plan_artifacts(self, artifacts):
            raise RuntimeError("github down")
    app.service.configure_plan_hooks(tools=_FailingTools())

    status, resp = app._handle_card_action_payload(
        _card_payload("approve_plan_submit", r.req_id)
    )

    assert status == 200
    assert resp.get("toast", {}).get("type") == "error"
    assert r.pending_plan_review is not None  # user can retry
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_service_app_plan_wiring.py -v -k approve_plan_submit`
Expected: all four fail — action is unrecognized.

- [ ] **Step 3: Add the handler**

Modify `src/requirement_workflow_v12/service_app.py`. Find the inserted `send_plan_author_start` block (above the line that says `if action_name == "send_spec_author_start":`). Immediately after the `send_plan_author_start` block, insert:
```python
        if action_name == "approve_plan_submit":
            req_id = value.get("req_id", "")
            if not req_id:
                return 200, {"toast": {"type": "error", "content": "缺少需求ID。"}}
            requirement = self.service.get_requirement(req_id)
            if requirement is None:
                return 200, {"toast": {"type": "error", "content": f"未知需求：{req_id}。"}}
            pending = requirement.pending_plan_review
            if not pending:
                return 200, {"toast": {"type": "error", "content": "Plan 草稿不存在，请让 Plan Author 重新提交。"}}
            if pending.get("project_context_change"):
                return 200, {"toast": {"type": "error", "content": "MVP 暂不支持 architecture_change 的 Plan 提交，请联系维护者。"}}
            try:
                self.service.plan_submit(
                    req_id,
                    plan_md_content=pending.get("plan_md_content", ""),
                    project_context_change=None,
                )
            except Exception as exc:
                LOGGER.exception("approve_plan_submit failed req_id=%s", req_id)
                return 200, {"toast": {"type": "error", "content": f"Plan 提交失败：{exc}；可再次点击重试。"}}
            requirement.pending_plan_review = None
            self._save_state()
            self._dispatch_transition_notifications(requirement, trigger="plan_ready")
            return 200, {"toast": {"type": "success", "content": "Plan 已通过并提交至 GitHub。"}}

```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_service_app_plan_wiring.py -v -k approve_plan_submit`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/service_app.py tests/test_service_app_plan_wiring.py
git commit -m "feat(service-app): add approve_plan_submit card handler"
```

---

## Task 9: `reject_plan_submit` card handler

**Files:**
- Modify: `src/requirement_workflow_v12/service_app.py` (insert below `approve_plan_submit`)
- Test: `tests/test_service_app_plan_wiring.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_service_app_plan_wiring.py`:
```python
def test_reject_plan_submit_clears_pending_and_resets_phase(app):
    r = _seed_pending_review(app, _approved_req(app))
    assert r.plan_phase == PlanPhase.FINAL_REVIEW_PENDING

    status, resp = app._handle_card_action_payload(
        _card_payload("reject_plan_submit", r.req_id)
    )

    assert status == 200
    assert resp.get("toast", {}).get("type") == "success"
    assert r.pending_plan_review is None
    assert r.plan_phase == PlanPhase.DECISIONS_IN_PROGRESS
    assert r.plan_status == PlanStatus.DRAFTING  # unchanged


def test_reject_plan_submit_rejects_if_no_pending(app):
    r = _approved_req(app)
    app.service.plan_start(r.req_id)

    status, resp = app._handle_card_action_payload(
        _card_payload("reject_plan_submit", r.req_id)
    )

    assert status == 200
    assert resp.get("toast", {}).get("type") == "error"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_service_app_plan_wiring.py -v -k reject_plan_submit`
Expected: both fail — action unrecognized.

- [ ] **Step 3: Add the handler**

Modify `src/requirement_workflow_v12/service_app.py`. Immediately after the `approve_plan_submit` block added in Task 8, insert:
```python
        if action_name == "reject_plan_submit":
            req_id = value.get("req_id", "")
            if not req_id:
                return 200, {"toast": {"type": "error", "content": "缺少需求ID。"}}
            requirement = self.service.get_requirement(req_id)
            if requirement is None:
                return 200, {"toast": {"type": "error", "content": f"未知需求：{req_id}。"}}
            if not requirement.pending_plan_review:
                return 200, {"toast": {"type": "error", "content": "无可驳回的 Plan 草稿。"}}
            requirement.pending_plan_review = None
            requirement.plan_phase = PlanPhase.DECISIONS_IN_PROGRESS
            self._save_state()
            return 200, {"toast": {"type": "success", "content": "已驳回 Plan 草稿；请重新私聊 Plan Author 修改。"}}

```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_service_app_plan_wiring.py -v -k reject_plan_submit`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/service_app.py tests/test_service_app_plan_wiring.py
git commit -m "feat(service-app): add reject_plan_submit card handler"
```

---

## Task 10: `plan_ready` notification trigger

**Files:**
- Modify: `src/requirement_workflow_v12/service_app.py` — `_transition_notification_content` + `_build_transition_notification_actions`
- Test: `tests/test_service_app_plan_wiring.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_service_app_plan_wiring.py`:
```python
def test_plan_ready_content_and_actions(app):
    r = _approved_req(app)
    r.plan_status = PlanStatus.READY
    r.plan_pr_url = "https://github.com/o/r/pull/42"

    template, title, reason, result, next_action = app._transition_notification_content(
        r, trigger="plan_ready"
    )
    assert "READY" in title or "已提交" in title or "Plan" in title
    assert "Spec" in next_action

    actions = app._build_transition_notification_actions(r, trigger="plan_ready")
    action_names = {a["value"]["action"] for a in actions}
    assert action_names == {"send_spec_author_start"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_service_app_plan_wiring.py -v -k plan_ready`
Expected: fails — trigger falls through to grey default.

- [ ] **Step 3: Add content branch**

In `_transition_notification_content`, add above the final grey return:
```python
        if trigger == "plan_ready":
            spec_agent_name = self.settings.openclaw_spec_agent_name
            return (
                "green",
                f"{requirement.req_id} Plan 已通过",
                f"Plan PR：{requirement.plan_pr_url or '（创建中）'}",
                "Plan 已合并至项目仓库，需求进入 Spec 撰写阶段。",
                f"请点击「开始 Spec 撰写」，将启动指令私发给自己后转发给 {spec_agent_name}。",
            )
```

- [ ] **Step 4: Add action button**

In `_build_transition_notification_actions`, add above the final `return []`:
```python
        if trigger == "plan_ready":
            return [
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "开始 Spec 撰写"},
                    "type": "primary",
                    "value": {"action": "send_spec_author_start", "req_id": requirement.req_id},
                },
            ]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_service_app_plan_wiring.py -v -k plan_ready`
Expected: passed.

- [ ] **Step 6: Commit**

```bash
git add src/requirement_workflow_v12/service_app.py tests/test_service_app_plan_wiring.py
git commit -m "feat(service-app): add plan_ready notification with Spec button"
```

---

## Task 11: Tighten `send_spec_author_start` guard

**Files:**
- Modify: `src/requirement_workflow_v12/service_app.py:1550` (existing `send_spec_author_start` guard)
- Test: `tests/test_service_app_plan_wiring.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_service_app_plan_wiring.py`:
```python
def test_send_spec_author_start_rejects_when_plan_not_ready(app):
    r = _approved_req(app)
    # plan_status is still None — Plan never ran

    status, resp = app._handle_card_action_payload(
        _card_payload("send_spec_author_start", r.req_id)
    )

    assert status == 200
    assert resp.get("toast", {}).get("type") == "error"
    assert "Plan" in resp["toast"]["content"] or "plan" in resp["toast"]["content"]
    app.gateway.send_text.assert_not_called()


def test_send_spec_author_start_allows_when_plan_ready(app):
    r = _approved_req(app)
    r.plan_status = PlanStatus.READY

    status, resp = app._handle_card_action_payload(
        _card_payload("send_spec_author_start", r.req_id)
    )

    assert status == 200
    assert resp.get("toast", {}).get("type") == "success"
    app.gateway.send_text.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_service_app_plan_wiring.py -v -k send_spec_author_start`
Expected: first test fails (current code allows spec start without Plan); second passes only if current code allowed it (it does).

- [ ] **Step 3: Tighten the guard**

Modify `src/requirement_workflow_v12/service_app.py:1550`. Current:
```python
            if requirement.status != WorkflowStatus.APPROVED or requirement.spec_status not in {None, SpecStatus.DRAFTING}:
                spec_label = requirement.spec_status.value if requirement.spec_status else "None"
                return 200, {"toast": {"type": "error", "content": f"当前需求不处于 Spec 撰写阶段（status={requirement.status.value} spec_status={spec_label}）。"}}
```
Replace with:
```python
            if (
                requirement.status != WorkflowStatus.APPROVED
                or requirement.spec_status not in {None, SpecStatus.DRAFTING}
                or requirement.plan_status != PlanStatus.READY
            ):
                spec_label = requirement.spec_status.value if requirement.spec_status else "None"
                plan_label = requirement.plan_status.value if requirement.plan_status else "None"
                return 200, {"toast": {"type": "error", "content": f"当前需求不处于 Spec 撰写阶段（status={requirement.status.value} spec_status={spec_label} plan_status={plan_label}）。Plan 未 READY，不能启动 Spec 撰写。"}}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_service_app_plan_wiring.py -v -k send_spec_author_start`
Expected: both pass.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/service_app.py tests/test_service_app_plan_wiring.py
git commit -m "feat(service-app): gate send_spec_author_start on plan_status=READY"
```

---

## Task 12: End-to-end happy-path integration test

**Files:**
- Test: `tests/test_service_app_plan_wiring_e2e.py` (new)

- [ ] **Step 1: Write the E2E test**

Create `tests/test_service_app_plan_wiring_e2e.py`:
```python
"""End-to-end: APPROVED → Plan 撰写 → Plan READY → Spec 撰写 handoff."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.config import Settings
from requirement_workflow_v12.coordinator_service import CoordinatorService
from requirement_workflow_v12.models import Requirement, WorkflowStatus
from requirement_workflow_v12.plan_state_machine import PlanStatus, PlanPhase
from requirement_workflow_v12.project_repo import PlanCommitResult
from requirement_workflow_v12.project_config import ProjectConfig
from requirement_workflow_v12.service_app import CoordinatorRuntimeApp
from requirement_workflow_v12.store import JsonStateStore


class _StubTools:
    def commit_plan_artifacts(self, artifacts):
        return PlanCommitResult(commit_sha=f"https://github.com/o/r/pull/1")


def _operator() -> dict:
    return {"open_id": "ou_alice", "name": "Alice"}


def _card(action: str, req_id: str) -> dict:
    return {
        "operator": _operator(),
        "context": {"open_chat_id": "oc_x", "open_message_id": "om_e2e"},
        "action": {"value": {"action": action, "req_id": req_id}, "form_value": {}},
    }


def test_full_happy_path_approved_to_spec_handoff(tmp_path):
    settings = Settings(
        feishu_app_id="x", feishu_app_secret="y",
        feishu_verification_token="t", feishu_encrypt_key="",
        state_store_path=str(tmp_path / "state.json"),
        spec_trace_dir=str(tmp_path / "trace"),
        github_token="",
    )
    svc = CoordinatorService()
    store = JsonStateStore(settings.state_store_path)
    gw = MagicMock()
    gw.list_project_configs.return_value = {}
    gw.upsert_project_config.return_value = None
    gw.bitable_url.return_value = ""

    app = CoordinatorRuntimeApp(
        settings=settings, store=store, service=svc, gateway=gw,
    )
    app.service.configure_plan_hooks(tools=_StubTools())

    # Seed an APPROVED requirement on a known project.
    r = Requirement(
        req_id="REQ-E2E", name="E2E Plan-Wire", project="P", summary="s", creator="c",
    )
    r.status = WorkflowStatus.APPROVED
    r.creator_user_id = "ou_alice"
    svc.requirements["REQ-E2E"] = r
    svc.project_configs["P"] = ProjectConfig(
        category="web", template_version="v1",
        architecture_doc_id="", architecture_doc_url="",
        tech_stack={"backend": "py"}, github_repo_url="o/r",
    )

    # T1: Click "开始 Plan 撰写".
    status, resp = app._handle_card_action_payload(_card("send_plan_author_start", "REQ-E2E"))
    assert status == 200 and resp["toast"]["type"] == "success"
    assert r.plan_status == PlanStatus.DRAFTING
    assert r.plan_phase == PlanPhase.OUTLINE_PENDING

    # T2: plan-author /plan-context check — gate already passes at endpoint, smoke-skip here.

    # T3: Plan-author submits outline.
    svc.set_plan_outline("REQ-E2E", outline=[{"id": "D1", "title": "decision 1"}])
    assert r.plan_phase == PlanPhase.DECISIONS_IN_PROGRESS

    # T4: Plan-author POST /openclaw/plan-callback event=plan_submit.
    status, resp = app.handle_openclaw_plan_callback({
        "req_id": "REQ-E2E",
        "event": "plan_submit",
        "payload": {"plan_md_content": "# plan\nD1", "project_context_change": None},
    })
    assert status == 200
    assert r.plan_status == PlanStatus.DRAFTING  # still drafting!
    assert r.plan_phase == PlanPhase.FINAL_REVIEW_PENDING
    assert r.pending_plan_review is not None

    # T6: User clicks "通过".
    status, resp = app._handle_card_action_payload(_card("approve_plan_submit", "REQ-E2E"))
    assert status == 200 and resp["toast"]["type"] == "success"
    assert r.plan_status == PlanStatus.READY
    assert r.pending_plan_review is None
    assert r.plan_pr_url == "https://github.com/o/r/pull/1"

    # T8: User clicks "开始 Spec 撰写".
    gw.send_text.reset_mock()
    status, resp = app._handle_card_action_payload(_card("send_spec_author_start", "REQ-E2E"))
    assert status == 200
    assert resp["toast"]["type"] == "success"
    gw.send_text.assert_called()
    text = gw.send_text.call_args.args[1]
    assert "Spec 撰写" in text
    assert "REQ-E2E" in text
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/test_service_app_plan_wiring_e2e.py -v`
Expected: 1 passed.

- [ ] **Step 3: Run full test suite**

Run: `pytest -q`
Expected: full green (no regressions vs. the Pre-flight baseline).

- [ ] **Step 4: Commit**

```bash
git add tests/test_service_app_plan_wiring_e2e.py
git commit -m "test(service-app): E2E plan-wiring APPROVED → Plan READY → Spec 撰写"
```

---

## Task 13: Documentation cross-reference

**Files:**
- Modify: `docs/superpowers/specs/2026-04-19-planning-phase-design.md` (add cross-link note at top, if section exists)
- Modify: `docs/methodology/harness-engineering-methodology.md` (update PLANNING §5.x to note card-flow wiring landed)

- [ ] **Step 1: Add a top note to the PLANNING design spec**

Open `docs/superpowers/specs/2026-04-19-planning-phase-design.md`. Under the top frontmatter/title, add a callout:
```markdown
> **2026-04-21 update**: card-flow wiring landed — see `2026-04-21-plan-wiring-design.md`. The `plan_start()` guard was loosened (no longer couples to `needs_ui`/`design_status`); the plan-callback `plan_submit` branch now buffers into `pending_plan_review` and only commits on human approval via the `plan_submitted_pending_review` card.
```

- [ ] **Step 2: Update methodology doc**

Open `docs/methodology/harness-engineering-methodology.md`. Find the PLANNING section (search: "PLANNING 阶段" or "§5.2"). Add a bullet at the end of that section:
```markdown
- **卡片流程落地（2026-04-21）**：APPROVED → `final_review_passed` 卡（「开始 Plan 撰写」）→ plan-author IM 多轮 → plan-callback `plan_submit` 缓存草稿 → `plan_submitted_pending_review` 卡「通过/需要修改」→ Plan READY + GitHub PR → `plan_ready` 卡「开始 Spec 撰写」。MVP 仅支持 `architecture_change=None`；不实现 `AUTH_PENDING`；驳回为纯状态重置。
```

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-04-19-planning-phase-design.md docs/methodology/harness-engineering-methodology.md
git commit -m "docs: cross-link plan-wiring design into PLANNING spec + methodology"
```

---

## Post-flight

- [ ] Run the full suite once more: `pytest -q`. Compare to Pre-flight baseline; zero regressions required.
- [ ] `grep -rn "pending_plan_review" src/ tests/` — confirm reads/writes only in: `models.py` (declaration), `service_app.py` (plan-callback handler, approve_plan_submit, reject_plan_submit), and the three test files.
- [ ] `grep -rn "pending_plan_draft" src/ tests/` — confirm the 5 hits in `coordinator_service.py` remain untouched (Task 2 only changed `plan_start`, not `plan_submit`'s internal carrier).
- [ ] Verify the card flow by reading the relevant sections of `service_app.py` once, top-to-bottom, making sure the flow matches §1.1 of the spec.
- [ ] Flag to user: **staging smoke** — `/create req` on a fresh project should now route through the Plan flow. Propose to the user but do not execute staging changes from the plan.
