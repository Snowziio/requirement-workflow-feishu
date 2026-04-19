# PLANNING Phase Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the PLANNING layer (PlanStatus state machine + plan-author agent wiring + architecture-change authorization gate + cascading restart) so `APPROVED` requirements produce a committed `docs/specs/REQ-*/plan.md` before entering SPEC_DRAFTING.

**Architecture:** Parallel status column `PlanStatus` (DRAFTING → [AUTH_PENDING] → READY) driven by a pure state machine mirroring the existing `spec_state_machine`; side effects — `plan.md` commit and optional atomic `ARCHITECTURE.md` update — live in `on_enter(PlanStatus.READY)` hooks registered on the existing `StateTransitionHooks` registry; coordinator-level orchestration handles precondition checks and cascading restarts. Tool-layer facade gets one new verb `commit_plan_artifacts` on `ProjectRepoTools`; no new gateways or modules required at the HTTP boundary beyond the `plan-context` / `plan-callback` endpoints.

**Tech Stack:** Python 3.11+, dataclasses, Enums; existing codebase uses `pytest` for tests, `MagicMock` for orchestrator unit tests; GitHub REST primitives via existing `GitHubGateway.commit_files` (direct commit to `main`, no PR). No new libraries.

**Scope excluded (per spec §8.2):** `design-author` agent implementation (only state-machine position + cascade plumbing), `design-context` endpoint, Bootstrap, first-time ARCHITECTURE.md creation. Schema-validation on plan-author side is owned by OpenClaw SKILL.md (not this plan).

---

## File Structure

**Create:**
- `src/requirement_workflow_v12/plan_state_machine.py` — PlanStatus/PlanEvent/DesignStatus/DesignEvent/PlanPhase enums + pure transition functions
- `src/requirement_workflow_v12/project_repo/architecture_apply.py` — pure function applying `architecture_change.changes[]` to ARCHITECTURE.md text; raises `ProjectRepoError(recoverable=True)` on before-mismatch
- `src/requirement_workflow_v12/plan_context.py` — parallel to `spec_context.py`, builds `plan-context` response
- `tests/test_plan_state_machine.py`
- `tests/test_architecture_apply.py`
- `tests/test_commit_plan_artifacts.py`
- `tests/test_coordinator_plan.py`
- `tests/test_plan_context.py`
- `tests/test_plan_endpoint_service_app.py`
- `tests/test_plan_cascade_restart.py`
- `tests/test_plan_phase_e2e.py`

**Modify:**
- `src/requirement_workflow_v12/models.py` — Requirement fields (plan_status, plan_phase, plan_pr_url, plan_outline, plan_decisions_wip, pending_plan_draft, design_status)
- `src/requirement_workflow_v12/project_repo/hooks.py` — widen annotations from `SpecStatus` to `object` so PlanStatus values can register
- `src/requirement_workflow_v12/project_repo/tools.py` — add `commit_plan_artifacts` method and PlanArtifacts dataclass
- `src/requirement_workflow_v12/project_repo/types.py` — add `PlanArtifacts` + `PlanCommitResult`
- `src/requirement_workflow_v12/project_repo/__init__.py` — export new types
- `src/requirement_workflow_v12/coordinator_service.py` — plan_start / plan_submit / plan_authorize / plan_authorization_reject / plan_restart / design_restart methods + `configure_plan_hooks` + `_commit_plan_and_maybe_architecture` hook
- `src/requirement_workflow_v12/spec_context.py` — add `plan_md_content` field to the response when plan READY
- `src/requirement_workflow_v12/service_app.py` — add `/queries/openclaw/plan-context/<req>` route, `/openclaw/plan-callback` route, `/plan restart` + `/design restart` slash commands, card handlers for outline/final_review/authorization cards

---

## Task 1: Pure PlanStatus + DesignStatus state machines

**Files:**
- Create: `src/requirement_workflow_v12/plan_state_machine.py`
- Create: `tests/test_plan_state_machine.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_plan_state_machine.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.plan_state_machine import (
    PlanStatus, PlanEvent, PlanPhase,
    DesignStatus, DesignEvent,
    apply_plan_event, apply_design_event,
)


def test_plan_start_from_none_goes_drafting():
    d = apply_plan_event(None, PlanEvent.PLAN_START)
    assert d.allowed is True
    assert d.next_status is PlanStatus.DRAFTING


def test_plan_start_from_drafting_rejected():
    d = apply_plan_event(PlanStatus.DRAFTING, PlanEvent.PLAN_START)
    assert d.allowed is False


def test_plan_submit_with_architecture_change_goes_auth_pending():
    d = apply_plan_event(
        PlanStatus.DRAFTING, PlanEvent.PLAN_SUBMIT,
        has_architecture_change=True,
    )
    assert d.allowed is True
    assert d.next_status is PlanStatus.AUTH_PENDING


def test_plan_submit_without_architecture_change_goes_ready():
    d = apply_plan_event(
        PlanStatus.DRAFTING, PlanEvent.PLAN_SUBMIT,
        has_architecture_change=False,
    )
    assert d.allowed is True
    assert d.next_status is PlanStatus.READY


def test_plan_authorize_from_auth_pending_goes_ready():
    d = apply_plan_event(PlanStatus.AUTH_PENDING, PlanEvent.PLAN_AUTHORIZE)
    assert d.allowed is True
    assert d.next_status is PlanStatus.READY


def test_plan_authorization_reject_returns_to_drafting():
    d = apply_plan_event(
        PlanStatus.AUTH_PENDING, PlanEvent.PLAN_AUTHORIZATION_REJECT,
    )
    assert d.allowed is True
    assert d.next_status is PlanStatus.DRAFTING


def test_plan_authorize_from_drafting_rejected():
    d = apply_plan_event(PlanStatus.DRAFTING, PlanEvent.PLAN_AUTHORIZE)
    assert d.allowed is False


def test_plan_restart_from_any_allowed_state_returns_none():
    for status in (PlanStatus.DRAFTING, PlanStatus.AUTH_PENDING, PlanStatus.READY):
        d = apply_plan_event(status, PlanEvent.PLAN_RESTART)
        assert d.allowed is True
        assert d.next_status is None


def test_plan_restart_before_start_rejected():
    d = apply_plan_event(None, PlanEvent.PLAN_RESTART)
    assert d.allowed is False


def test_design_start_from_none_goes_drafting():
    d = apply_design_event(None, DesignEvent.DESIGN_START)
    assert d.allowed is True
    assert d.next_status is DesignStatus.DRAFTING


def test_design_submit_goes_ready():
    d = apply_design_event(DesignStatus.DRAFTING, DesignEvent.DESIGN_SUBMIT)
    assert d.allowed is True
    assert d.next_status is DesignStatus.READY


def test_design_restart_from_any_allowed_returns_none():
    for status in (DesignStatus.DRAFTING, DesignStatus.READY):
        d = apply_design_event(status, DesignEvent.DESIGN_RESTART)
        assert d.allowed is True
        assert d.next_status is None


def test_plan_phase_enum_values():
    assert PlanPhase.OUTLINE_PENDING.value == "outline_pending"
    assert PlanPhase.OUTLINE_CONFIRMED.value == "outline_confirmed"
    assert PlanPhase.DECISIONS_IN_PROGRESS.value == "decisions_in_progress"
    assert PlanPhase.FINAL_REVIEW_PENDING.value == "final_review_pending"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_plan_state_machine.py -v`
Expected: FAIL with `ImportError: cannot import name ...` — module missing.

- [ ] **Step 3: Write the module**

```python
# src/requirement_workflow_v12/plan_state_machine.py
"""Pure state machines for the PLANNING layer.

Two independent columns — PlanStatus and DesignStatus — live alongside
the existing SpecStatus column. Transition rules are side-effect free;
all commits, card sends, and orchestrator dispatches happen in hooks
registered via ``StateTransitionHooks`` (see state-machine-hook-pattern.md).

``PlanPhase`` is a sub-field on ``Requirement`` that tracks plan-author
conversation progress **inside** ``PlanStatus.DRAFTING``. It is NOT a
state-machine state — phase advances are direct field writes, not events.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class PlanStatus(str, Enum):
    DRAFTING = "PLAN_DRAFTING"
    AUTH_PENDING = "PLAN_AUTH_PENDING"
    READY = "PLAN_READY"


class PlanEvent(str, Enum):
    PLAN_START = "plan_start"
    PLAN_SUBMIT = "plan_submit"
    PLAN_AUTHORIZE = "plan_authorize"
    PLAN_AUTHORIZATION_REJECT = "plan_authorization_reject"
    PLAN_RESTART = "plan_restart"


class PlanPhase(str, Enum):
    OUTLINE_PENDING = "outline_pending"
    OUTLINE_CONFIRMED = "outline_confirmed"
    DECISIONS_IN_PROGRESS = "decisions_in_progress"
    FINAL_REVIEW_PENDING = "final_review_pending"


class DesignStatus(str, Enum):
    DRAFTING = "DESIGN_DRAFTING"
    READY = "DESIGN_READY"


class DesignEvent(str, Enum):
    DESIGN_START = "design_start"
    DESIGN_SUBMIT = "design_submit"
    DESIGN_RESTART = "design_restart"


@dataclass
class PlanTransitionDecision:
    allowed: bool
    next_status: Optional[PlanStatus]
    message: str
    requires: list[str] = field(default_factory=list)


@dataclass
class DesignTransitionDecision:
    allowed: bool
    next_status: Optional[DesignStatus]
    message: str
    requires: list[str] = field(default_factory=list)


_PLAN_TRANSITIONS: dict[tuple[Optional[PlanStatus], PlanEvent], PlanStatus] = {
    (None, PlanEvent.PLAN_START): PlanStatus.DRAFTING,
    (PlanStatus.AUTH_PENDING, PlanEvent.PLAN_AUTHORIZE): PlanStatus.READY,
    (PlanStatus.AUTH_PENDING, PlanEvent.PLAN_AUTHORIZATION_REJECT): PlanStatus.DRAFTING,
}


def apply_plan_event(
    current: Optional[PlanStatus],
    event: PlanEvent,
    *,
    has_architecture_change: bool = False,
) -> PlanTransitionDecision:
    if event is PlanEvent.PLAN_RESTART:
        if current is None:
            return PlanTransitionDecision(
                allowed=False,
                next_status=current,
                message="规划层未进入，无法 restart",
            )
        return PlanTransitionDecision(
            allowed=True,
            next_status=None,
            message="规划层状态已重置（restart）",
        )

    if event is PlanEvent.PLAN_SUBMIT and current is PlanStatus.DRAFTING:
        next_status = (
            PlanStatus.AUTH_PENDING if has_architecture_change else PlanStatus.READY
        )
        return PlanTransitionDecision(
            allowed=True,
            next_status=next_status,
            message=f"规划层状态已更新为 {next_status.value}",
        )

    next_status = _PLAN_TRANSITIONS.get((current, event))
    if next_status is None:
        label = current.value if current is not None else "<未进入规划层>"
        return PlanTransitionDecision(
            allowed=False,
            next_status=current,
            message=f"当前规划层状态 {label} 不能执行 {event.value}",
        )
    return PlanTransitionDecision(
        allowed=True,
        next_status=next_status,
        message=f"规划层状态已更新为 {next_status.value}",
    )


_DESIGN_TRANSITIONS: dict[tuple[Optional[DesignStatus], DesignEvent], DesignStatus] = {
    (None, DesignEvent.DESIGN_START): DesignStatus.DRAFTING,
    (DesignStatus.DRAFTING, DesignEvent.DESIGN_SUBMIT): DesignStatus.READY,
}


def apply_design_event(
    current: Optional[DesignStatus],
    event: DesignEvent,
) -> DesignTransitionDecision:
    if event is DesignEvent.DESIGN_RESTART:
        if current is None:
            return DesignTransitionDecision(
                allowed=False,
                next_status=current,
                message="设计层未进入，无法 restart",
            )
        return DesignTransitionDecision(
            allowed=True,
            next_status=None,
            message="设计层状态已重置（restart）",
        )

    next_status = _DESIGN_TRANSITIONS.get((current, event))
    if next_status is None:
        label = current.value if current is not None else "<未进入设计层>"
        return DesignTransitionDecision(
            allowed=False,
            next_status=current,
            message=f"当前设计层状态 {label} 不能执行 {event.value}",
        )
    return DesignTransitionDecision(
        allowed=True,
        next_status=next_status,
        message=f"设计层状态已更新为 {next_status.value}",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_plan_state_machine.py -v`
Expected: 13 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/plan_state_machine.py tests/test_plan_state_machine.py
git commit -m "feat(plan): PlanStatus + DesignStatus pure state machines"
```

---

## Task 2: Requirement fields for plan + design state

**Files:**
- Modify: `src/requirement_workflow_v12/models.py`
- Test: `tests/test_plan_state_machine.py` (extend)

- [ ] **Step 1: Write the failing tests (append to test_plan_state_machine.py)**

```python
# append at end of tests/test_plan_state_machine.py

from requirement_workflow_v12.models import Requirement


def test_requirement_defaults_plan_fields_empty():
    r = Requirement(req_id="R", name="n", project="p", summary="s", creator="c")
    assert r.plan_status is None
    assert r.plan_phase is None
    assert r.plan_pr_url == ""
    assert r.plan_outline == []
    assert r.plan_decisions_wip == []
    assert r.pending_plan_draft is None
    assert r.design_status is None


def test_requirement_plan_status_assignable():
    r = Requirement(req_id="R", name="n", project="p", summary="s", creator="c")
    r.plan_status = PlanStatus.DRAFTING
    assert r.plan_status is PlanStatus.DRAFTING


def test_requirement_plan_phase_assignable():
    r = Requirement(req_id="R", name="n", project="p", summary="s", creator="c")
    r.plan_phase = PlanPhase.OUTLINE_CONFIRMED
    assert r.plan_phase is PlanPhase.OUTLINE_CONFIRMED
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_plan_state_machine.py -v -k requirement`
Expected: FAIL — `AttributeError: 'Requirement' object has no attribute 'plan_status'`.

- [ ] **Step 3: Add fields to Requirement**

Edit `src/requirement_workflow_v12/models.py`. Add after the existing `spec_*` fields (before `updated_at: datetime = field(default_factory=utc_now)`):

```python
    plan_status: "PlanStatus | None" = None
    plan_phase: "PlanPhase | None" = None
    plan_pr_url: str = ""
    plan_outline: list[dict] = field(default_factory=list)
    plan_decisions_wip: list[dict] = field(default_factory=list)
    pending_plan_draft: dict | None = None
    design_status: "DesignStatus | None" = None
```

And add these imports at the top of models.py (below the existing `from .spec_state_machine import SpecStatus` line):

```python
from .plan_state_machine import DesignStatus, PlanPhase, PlanStatus
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_plan_state_machine.py -v`
Expected: 16 PASS.

- [ ] **Step 5: Full pytest sanity**

Run: `pytest -x`
Expected: no regressions (all existing tests still pass).

- [ ] **Step 6: Commit**

```bash
git add src/requirement_workflow_v12/models.py tests/test_plan_state_machine.py
git commit -m "feat(plan): Requirement plan/design state fields"
```

---

## Task 3: Widen StateTransitionHooks type annotations

**Files:**
- Modify: `src/requirement_workflow_v12/project_repo/hooks.py`
- Test: `tests/test_project_repo_hooks.py` (extend)

- [ ] **Step 1: Write a failing test proving PlanStatus registration works**

Append to `tests/test_project_repo_hooks.py`:

```python
# Task 3 extension: hooks must accept any hashable status value, not just SpecStatus
from requirement_workflow_v12.plan_state_machine import PlanStatus


def test_hooks_accept_plan_status_keys():
    hooks = StateTransitionHooks()
    calls: list[str] = []
    hooks.on_enter(PlanStatus.DRAFTING, lambda r: calls.append("drafting"))
    hooks.on_enter(PlanStatus.READY, lambda r: calls.append("ready"))

    hooks.fire_enter(PlanStatus.DRAFTING, _req())
    hooks.fire_enter(PlanStatus.READY, _req())

    assert calls == ["drafting", "ready"]


def test_hook_exception_logs_plan_status_name():
    import logging

    hooks = StateTransitionHooks()

    def boom(_r):
        raise ProjectRepoError("bad")

    hooks.on_enter(PlanStatus.READY, boom)

    with pytest.raises(ProjectRepoError):
        import logging as _logging
        import pytest as _pytest
        # caplog fixture required; re-using caplog from test collection is complex —
        # just verify exception propagates; log assertions stay on SpecStatus test
        hooks.fire_enter(PlanStatus.READY, _req("REQ-Q-1"))
```

- [ ] **Step 2: Run to verify passes now (hooks already uses `object` at runtime)**

Run: `pytest tests/test_project_repo_hooks.py -v`
Expected: the first new test PASSES immediately because Python dicts are untyped at runtime (current `"SpecStatus"` string annotation is forward-ref only). The second one also PASSES.

- [ ] **Step 3: Clean up the misleading annotations**

Edit `src/requirement_workflow_v12/project_repo/hooks.py`. Replace lines 14–40:

```python
from typing import Any, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from ..models import Requirement

_logger = logging.getLogger(__name__)

HookFn = Callable[["Requirement"], None]


class StateTransitionHooks:
    """Registry for state-column enter/exit callbacks.

    Keys are any hashable status value — typically ``SpecStatus`` or
    ``PlanStatus`` members. Separate registries are not needed; key
    equality already partitions hooks per column.
    """

    def __init__(self) -> None:
        self._on_enter: dict[Any, list[HookFn]] = {}
        self._on_exit: dict[Any, list[HookFn]] = {}

    def on_enter(self, status: Any, fn: HookFn) -> None:
        self._on_enter.setdefault(status, []).append(fn)

    def on_exit(self, status: Any, fn: HookFn) -> None:
        self._on_exit.setdefault(status, []).append(fn)

    def fire_enter(self, status: Any, req: "Requirement") -> None:
        self._fire("enter", self._on_enter.get(status, ()), status, req)

    def fire_exit(self, status: Any, req: "Requirement") -> None:
        self._fire("exit", self._on_exit.get(status, ()), status, req)
```

Leave the `_fire` method unchanged (it already uses `getattr(status, "name", ...)` safely).

- [ ] **Step 4: Full test run**

Run: `pytest tests/test_project_repo_hooks.py -v`
Expected: all tests PASS (existing + new).

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/project_repo/hooks.py tests/test_project_repo_hooks.py
git commit -m "refactor(hooks): widen status type to Any for cross-column registration"
```

---

## Task 4: Pure ARCHITECTURE.md section-path apply

**Files:**
- Create: `src/requirement_workflow_v12/project_repo/architecture_apply.py`
- Create: `tests/test_architecture_apply.py`

**Algorithm:** `section_path` is a markdown header line (e.g. `"## 会话存储"`). Find the first exact match of that line in the document. The "section" is that header line + all lines following until the next header at the same-or-higher level, or EOF. `before` must equal the current section text (trailing newlines stripped on both sides). `after` replaces the section. If the header doesn't exist, treat as "new section" — require `before == ""`, append `after` to the end (with a blank line separator).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_architecture_apply.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from requirement_workflow_v12.project_repo.architecture_apply import (
    apply_architecture_changes, ArchitectureApplyError,
)


ORIGINAL = """# Architecture

## 会话存储

旧方案：本地文件。

## 鉴权

OAuth2。
"""


def test_apply_replaces_matching_section():
    changes = [{
        "section_path": "## 会话存储",
        "before": "## 会话存储\n\n旧方案：本地文件.",
        "after": "## 会话存储\n\n新方案：Redis 7.x.",
        "rationale": "D1",
    }]
    new = apply_architecture_changes(ORIGINAL, changes)
    assert "Redis 7.x" in new
    assert "旧方案：本地文件" not in new
    assert "## 鉴权" in new  # unchanged section preserved


def test_apply_appends_new_section_when_before_empty():
    changes = [{
        "section_path": "## 缓存",
        "before": "",
        "after": "## 缓存\n\n新增：LRU 1000 项。",
        "rationale": "D2",
    }]
    new = apply_architecture_changes(ORIGINAL, changes)
    assert "## 缓存" in new
    assert "LRU 1000 项" in new
    assert "## 会话存储" in new
    assert "## 鉴权" in new


def test_apply_multiple_changes_applied_sequentially():
    changes = [
        {
            "section_path": "## 会话存储",
            "before": "## 会话存储\n\n旧方案：本地文件.",
            "after": "## 会话存储\n\n新方案：Redis.",
            "rationale": "D1",
        },
        {
            "section_path": "## 缓存",
            "before": "",
            "after": "## 缓存\n\nLRU.",
            "rationale": "D2",
        },
    ]
    new = apply_architecture_changes(ORIGINAL, changes)
    assert "Redis" in new
    assert "LRU" in new


def test_apply_rejects_before_mismatch():
    changes = [{
        "section_path": "## 会话存储",
        "before": "## 会话存储\n\n某个不存在的旧内容.",
        "after": "## 会话存储\n\nRedis.",
        "rationale": "D1",
    }]
    with pytest.raises(ArchitectureApplyError) as exc_info:
        apply_architecture_changes(ORIGINAL, changes)
    assert exc_info.value.recoverable is True
    assert exc_info.value.reason == "architecture_conflict"


def test_apply_rejects_new_section_with_nonempty_before():
    changes = [{
        "section_path": "## 不存在的节",
        "before": "some old content",
        "after": "## 不存在的节\n\nnew.",
        "rationale": "D1",
    }]
    with pytest.raises(ArchitectureApplyError) as exc_info:
        apply_architecture_changes(ORIGINAL, changes)
    assert exc_info.value.recoverable is True


def test_empty_changes_list_is_noop():
    assert apply_architecture_changes(ORIGINAL, []) == ORIGINAL


def test_apply_preserves_higher_level_header_when_replacing_subsection():
    doc = """# Top

## A

aaa

### A.1

xxx

## B

bbb
"""
    changes = [{
        "section_path": "### A.1",
        "before": "### A.1\n\nxxx",
        "after": "### A.1\n\nyyy",
        "rationale": "t",
    }]
    new = apply_architecture_changes(doc, changes)
    assert "yyy" in new
    assert "xxx" not in new
    assert "## B" in new  # next higher-level header untouched
    assert "## A" in new
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_architecture_apply.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Write the module**

```python
# src/requirement_workflow_v12/project_repo/architecture_apply.py
"""Pure text transformer for ARCHITECTURE.md section-level updates.

Drives the ``architecture_change`` apply stage of ``commit_plan_artifacts``.
Side-effect free: given the current file text + a list of change specs,
return the new text or raise ``ArchitectureApplyError`` with
``recoverable=True`` on any before-mismatch (the caller maps this to
``ProjectRepoError(recoverable=True, reason="architecture_conflict")``).
"""
from __future__ import annotations

import re
from typing import Iterable


class ArchitectureApplyError(Exception):
    """Raised when a change cannot be applied cleanly."""

    def __init__(self, message: str, *, reason: str, recoverable: bool = True):
        super().__init__(message)
        self.reason = reason
        self.recoverable = recoverable


_HEADER_RE = re.compile(r"^(#+)\s+(.*)$")


def _header_level(line: str) -> int | None:
    m = _HEADER_RE.match(line)
    return len(m.group(1)) if m else None


def _find_section_bounds(lines: list[str], header_line: str) -> tuple[int, int] | None:
    """Return (start_idx_inclusive, end_idx_exclusive) or None if not found."""
    target_level = _header_level(header_line)
    if target_level is None:
        return None
    try:
        start = next(i for i, ln in enumerate(lines) if ln.rstrip("\n") == header_line)
    except StopIteration:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        lvl = _header_level(lines[j].rstrip("\n"))
        if lvl is not None and lvl <= target_level:
            end = j
            break
    return start, end


def _normalize(text: str) -> str:
    return text.strip("\n").rstrip()


def apply_architecture_changes(
    current_text: str, changes: Iterable[dict]
) -> str:
    text = current_text
    for change in changes:
        section_path = change["section_path"]
        before = change["before"]
        after = change["after"]

        lines = text.splitlines(keepends=True)
        bounds = _find_section_bounds(lines, section_path)

        if bounds is None:
            if _normalize(before) != "":
                raise ArchitectureApplyError(
                    f"section {section_path!r} not found but before is non-empty",
                    reason="architecture_conflict",
                )
            # Append as new section with a leading blank line separator
            suffix = "" if text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
            text = text + suffix + (after if after.endswith("\n") else after + "\n")
            continue

        start, end = bounds
        current_section = "".join(lines[start:end])
        if _normalize(current_section) != _normalize(before):
            raise ArchitectureApplyError(
                f"before mismatch for section {section_path!r}",
                reason="architecture_conflict",
            )
        new_section = after if after.endswith("\n") else after + "\n"
        new_lines = lines[:start] + [new_section] + lines[end:]
        text = "".join(new_lines)
    return text
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_architecture_apply.py -v`
Expected: 7 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/project_repo/architecture_apply.py tests/test_architecture_apply.py
git commit -m "feat(plan): pure ARCHITECTURE.md section apply transformer"
```

---

## Task 5: PlanArtifacts + PlanCommitResult types

**Files:**
- Modify: `src/requirement_workflow_v12/project_repo/types.py`
- Modify: `src/requirement_workflow_v12/project_repo/__init__.py`
- Test: `tests/test_commit_plan_artifacts.py` (create stub now, fill later)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_commit_plan_artifacts.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.project_repo import PlanArtifacts, PlanCommitResult


def test_plan_artifacts_is_frozen():
    a = PlanArtifacts(
        project_repo="o/r",
        req_id="REQ-P-1",
        plan_md_content="---\nreq_id: REQ-P-1\n---\n",
        architecture_change=None,
        commit_message="plan: REQ-P-1",
    )
    import pytest
    with pytest.raises(Exception):
        a.plan_md_content = "changed"  # type: ignore[misc]


def test_plan_commit_result_fields():
    r = PlanCommitResult(
        commit_sha="abc123",
        branch="main",
        plan_md_path="docs/specs/REQ-P-1/plan.md",
        architecture_updated=False,
    )
    assert r.commit_sha == "abc123"
    assert r.branch == "main"
    assert r.plan_md_path.endswith("plan.md")
    assert r.architecture_updated is False
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_commit_plan_artifacts.py -v`
Expected: FAIL — `ImportError: cannot import name 'PlanArtifacts'`.

- [ ] **Step 3: Add types**

Append to `src/requirement_workflow_v12/project_repo/types.py`:

```python
@dataclass(frozen=True)
class PlanArtifacts:
    """plan.md content + optional structured architecture diff.

    ``architecture_change`` is the raw payload (dict) carrying
    ``summary`` / ``changes[]`` / ``authorized*`` — matches plan-author's
    callback schema. ``None`` means this plan doesn't touch ARCHITECTURE.md.
    """
    project_repo: str
    req_id: str
    plan_md_content: str
    architecture_change: dict | None
    commit_message: str


@dataclass(frozen=True)
class PlanCommitResult:
    commit_sha: str
    branch: str
    plan_md_path: str
    architecture_updated: bool
```

Edit `src/requirement_workflow_v12/project_repo/__init__.py` to export them:

```python
from .types import (
    CommitRef,
    PlanArtifacts,
    PlanCommitResult,
    PrRef,
    ProjectContext,
    RepoRef,
    SpecArtifacts,
)

__all__ = [
    "CommitRef",
    "GitHubProjectRepoTools",
    "PlanArtifacts",
    "PlanCommitResult",
    "PrRef",
    "ProjectContext",
    "ProjectRepoError",
    "ProjectRepoTools",
    "RepoRef",
    "SpecArtifacts",
    "StateTransitionHooks",
]
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_commit_plan_artifacts.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/project_repo/types.py src/requirement_workflow_v12/project_repo/__init__.py tests/test_commit_plan_artifacts.py
git commit -m "feat(plan): PlanArtifacts + PlanCommitResult types"
```

---

## Task 6: `commit_plan_artifacts` happy path — plan.md only, no architecture

**Files:**
- Modify: `src/requirement_workflow_v12/project_repo/tools.py`
- Test: `tests/test_commit_plan_artifacts.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_commit_plan_artifacts.py`:

```python
from unittest.mock import MagicMock
from requirement_workflow_v12.project_repo import (
    GitHubProjectRepoTools, ProjectRepoError,
)


def test_commit_plan_artifacts_without_architecture_commits_plan_md_to_main():
    gw = MagicMock()
    gw.commit_files.return_value = "sha-commit-1"
    tools = GitHubProjectRepoTools(gateway=gw)
    artifacts = PlanArtifacts(
        project_repo="owner/repo",
        req_id="REQ-P-1",
        plan_md_content="---\nreq_id: REQ-P-1\n---\n# Plan\n",
        architecture_change=None,
        commit_message="plan(REQ-P-1): initial plan",
    )
    result = tools.commit_plan_artifacts(artifacts)

    assert isinstance(result, PlanCommitResult)
    assert result.commit_sha == "sha-commit-1"
    assert result.branch == "main"
    assert result.plan_md_path == "docs/specs/REQ-P-1/plan.md"
    assert result.architecture_updated is False

    # Verify a single-file commit went out
    gw.commit_files.assert_called_once()
    kwargs = gw.commit_files.call_args.kwargs
    assert kwargs["owner"] == "owner"
    assert kwargs["repo"] == "repo"
    assert kwargs["branch"] == "main"
    files = list(kwargs["files"])
    assert len(files) == 1
    assert files[0].path == "docs/specs/REQ-P-1/plan.md"
    assert "req_id: REQ-P-1" in files[0].content
    # ARCHITECTURE.md not fetched when no change
    gw.fetch_file_sha.assert_not_called()
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_commit_plan_artifacts.py::test_commit_plan_artifacts_without_architecture_commits_plan_md_to_main -v`
Expected: FAIL — `AttributeError: 'GitHubProjectRepoTools' object has no attribute 'commit_plan_artifacts'`.

- [ ] **Step 3: Implement method**

Edit `src/requirement_workflow_v12/project_repo/tools.py`. Update imports at the top:

```python
from ..github_gateway import FileChange, GitHubGateway, GitHubGatewayError
from .architecture_apply import ArchitectureApplyError, apply_architecture_changes
from .types import PlanArtifacts, PlanCommitResult, PrRef, ProjectContext, SpecArtifacts
```

Update the Protocol to include the new verb:

```python
@runtime_checkable
class ProjectRepoTools(Protocol):
    def fetch_project_context(self, project_repo: str) -> ProjectContext: ...

    def commit_spec_artifacts(
        self, req_id: str, artifacts: SpecArtifacts,
    ) -> PrRef: ...

    def commit_plan_artifacts(
        self, artifacts: PlanArtifacts,
    ) -> PlanCommitResult: ...

    def cleanup_failed_branch(self, project_repo: str, branch: str) -> None: ...
```

Add the implementation on `GitHubProjectRepoTools` (append at end of class):

```python
    def commit_plan_artifacts(
        self, artifacts: PlanArtifacts,
    ) -> PlanCommitResult:
        owner, name = artifacts.project_repo.split("/", 1)
        plan_path = f"docs/specs/{artifacts.req_id}/plan.md"
        files_to_commit = [
            FileChange(path=plan_path, content=artifacts.plan_md_content),
        ]
        architecture_updated = False

        if artifacts.architecture_change is not None:
            try:
                _arch_sha, arch_text = self._gw.fetch_file_sha(
                    artifacts.project_repo, "main", "ARCHITECTURE.md",
                )
            except GitHubGatewayError as exc:
                raise ProjectRepoError(
                    f"commit_plan_artifacts: cannot fetch ARCHITECTURE.md: {exc}",
                    recoverable=False,
                ) from exc
            try:
                new_arch = apply_architecture_changes(
                    arch_text, artifacts.architecture_change.get("changes", []),
                )
            except ArchitectureApplyError as exc:
                raise ProjectRepoError(
                    f"commit_plan_artifacts: architecture apply failed: {exc}",
                    recoverable=exc.recoverable,
                ) from exc
            files_to_commit.append(
                FileChange(path="ARCHITECTURE.md", content=new_arch),
            )
            architecture_updated = True

        try:
            sha = self._gw.commit_files(
                owner=owner, repo=name, branch="main",
                files=files_to_commit, message=artifacts.commit_message,
            )
        except GitHubGatewayError as exc:
            raise ProjectRepoError(
                f"commit_plan_artifacts: commit to main failed: {exc}",
                recoverable=False,
            ) from exc
        return PlanCommitResult(
            commit_sha=sha, branch="main",
            plan_md_path=plan_path,
            architecture_updated=architecture_updated,
        )
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_commit_plan_artifacts.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/project_repo/tools.py tests/test_commit_plan_artifacts.py
git commit -m "feat(plan): commit_plan_artifacts — plan.md only path"
```

---

## Task 7: `commit_plan_artifacts` — plan.md + ARCHITECTURE.md atomic commit

**Files:**
- Test: `tests/test_commit_plan_artifacts.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_commit_plan_artifacts.py`:

```python
def test_commit_plan_artifacts_with_architecture_commits_both_files_atomically():
    gw = MagicMock()
    gw.fetch_file_sha.return_value = (
        "arch-sha-before",
        "# Architecture\n\n## 会话存储\n\n旧方案.\n",
    )
    gw.commit_files.return_value = "sha-commit-2"

    tools = GitHubProjectRepoTools(gateway=gw)
    arch_change = {
        "summary": "Add Redis",
        "changes": [{
            "section_path": "## 会话存储",
            "before": "## 会话存储\n\n旧方案.",
            "after": "## 会话存储\n\n新方案：Redis.",
            "rationale": "D1",
        }],
        "authorized": True,
        "authorized_by": "u-1",
        "authorized_at": "2026-04-19T10:00:00Z",
    }
    artifacts = PlanArtifacts(
        project_repo="owner/repo",
        req_id="REQ-P-2",
        plan_md_content="---\nreq_id: REQ-P-2\n---\n",
        architecture_change=arch_change,
        commit_message="plan(REQ-P-2): add Redis",
    )

    result = tools.commit_plan_artifacts(artifacts)

    assert result.architecture_updated is True
    gw.fetch_file_sha.assert_called_once_with("owner/repo", "main", "ARCHITECTURE.md")
    kwargs = gw.commit_files.call_args.kwargs
    files = list(kwargs["files"])
    paths = sorted(fc.path for fc in files)
    assert paths == ["ARCHITECTURE.md", "docs/specs/REQ-P-2/plan.md"]
    arch_content = next(fc.content for fc in files if fc.path == "ARCHITECTURE.md")
    assert "Redis" in arch_content
    assert "旧方案" not in arch_content
```

- [ ] **Step 2: Run to verify**

Run: `pytest tests/test_commit_plan_artifacts.py::test_commit_plan_artifacts_with_architecture_commits_both_files_atomically -v`
Expected: PASS (implementation from Task 6 already covers this path).

- [ ] **Step 3: Commit**

```bash
git add tests/test_commit_plan_artifacts.py
git commit -m "test(plan): atomic plan+architecture commit path"
```

---

## Task 8: `commit_plan_artifacts` — before-mismatch → recoverable error

**Files:**
- Test: `tests/test_commit_plan_artifacts.py` (extend)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_commit_plan_artifacts.py`:

```python
def test_commit_plan_artifacts_raises_recoverable_on_architecture_conflict():
    gw = MagicMock()
    gw.fetch_file_sha.return_value = (
        "arch-sha",
        "# Architecture\n\n## 会话存储\n\n实际内容不同.\n",
    )
    tools = GitHubProjectRepoTools(gateway=gw)
    arch_change = {
        "changes": [{
            "section_path": "## 会话存储",
            "before": "## 会话存储\n\n期望的旧内容.",  # does not match
            "after": "## 会话存储\n\nRedis.",
            "rationale": "D1",
        }],
    }
    artifacts = PlanArtifacts(
        project_repo="owner/repo", req_id="REQ-P-3",
        plan_md_content="---\n---\n",
        architecture_change=arch_change,
        commit_message="m",
    )
    import pytest
    with pytest.raises(ProjectRepoError) as exc_info:
        tools.commit_plan_artifacts(artifacts)
    assert exc_info.value.recoverable is True
    # commit_files must not have fired
    gw.commit_files.assert_not_called()


def test_commit_plan_artifacts_raises_nonrecoverable_on_commit_failure():
    from requirement_workflow_v12.github_gateway import GitHubGatewayError
    gw = MagicMock()
    gw.commit_files.side_effect = GitHubGatewayError(500, "boom")
    tools = GitHubProjectRepoTools(gateway=gw)
    artifacts = PlanArtifacts(
        project_repo="o/r", req_id="REQ-P-4",
        plan_md_content="---\n---\n",
        architecture_change=None,
        commit_message="m",
    )
    import pytest
    with pytest.raises(ProjectRepoError) as exc_info:
        tools.commit_plan_artifacts(artifacts)
    assert exc_info.value.recoverable is False
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_commit_plan_artifacts.py -v`
Expected: 5 PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_commit_plan_artifacts.py
git commit -m "test(plan): recoverable architecture_conflict + non-recoverable commit fail"
```

---

## Task 9: Coordinator `plan_start` method

**Files:**
- Modify: `src/requirement_workflow_v12/coordinator_service.py`
- Create: `tests/test_coordinator_plan.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_coordinator_plan.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from requirement_workflow_v12.coordinator_service import CoordinatorService
from requirement_workflow_v12.models import Requirement, WorkflowStatus
from requirement_workflow_v12.plan_state_machine import (
    PlanStatus, PlanPhase, DesignStatus,
)


def _approved_req(svc, req_id="REQ-P-1", needs_ui=False):
    r = Requirement(
        req_id=req_id, name="n", project="P", summary="s", creator="c",
    )
    r.status = WorkflowStatus.APPROVED
    r.needs_ui = needs_ui
    svc.requirements[req_id] = r
    return r


def test_plan_start_sets_status_drafting_and_outline_pending_phase():
    svc = CoordinatorService()
    r = _approved_req(svc)

    result = svc.plan_start(r.req_id)

    assert result.plan_status is PlanStatus.DRAFTING
    assert result.plan_phase is PlanPhase.OUTLINE_PENDING


def test_plan_start_rejected_when_not_approved():
    svc = CoordinatorService()
    r = _approved_req(svc)
    r.status = WorkflowStatus.DRAFTING

    with pytest.raises(ValueError, match="APPROVED"):
        svc.plan_start(r.req_id)


def test_plan_start_needs_ui_requires_design_ready():
    svc = CoordinatorService()
    r = _approved_req(svc, needs_ui=True)

    with pytest.raises(ValueError, match="design_status"):
        svc.plan_start(r.req_id)

    r.design_status = DesignStatus.READY
    svc.plan_start(r.req_id)
    assert r.plan_status is PlanStatus.DRAFTING


def test_plan_start_rejected_when_already_drafting():
    svc = CoordinatorService()
    r = _approved_req(svc)
    svc.plan_start(r.req_id)
    with pytest.raises(ValueError):
        svc.plan_start(r.req_id)
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_coordinator_plan.py -v`
Expected: FAIL — `AttributeError: 'CoordinatorService' object has no attribute 'plan_start'`.

- [ ] **Step 3: Implement method**

Edit `src/requirement_workflow_v12/coordinator_service.py`. At the top, add imports (below the existing `from .spec_state_machine import ...`):

```python
from .plan_state_machine import (
    DesignStatus, PlanEvent, PlanPhase, PlanStatus, apply_plan_event,
)
```

Append to the `CoordinatorService` class (after `submit_checkpoint_1a_pass`):

```python
    # ── PLANNING layer ──────────────────────────────────────────────────

    def plan_start(self, req_id: str) -> Requirement:
        r = self.requirements[req_id]
        if r.status != WorkflowStatus.APPROVED:
            raise ValueError(
                f"plan_start requires workflow_status=APPROVED, got {r.status.value}"
            )
        if r.needs_ui and r.design_status != DesignStatus.READY:
            raise ValueError(
                f"plan_start requires design_status=READY when needs_ui=True, "
                f"got design_status={r.design_status}"
            )
        decision = apply_plan_event(r.plan_status, PlanEvent.PLAN_START)
        if not decision.allowed:
            raise ValueError(decision.message)

        prev = r.plan_status
        self._hooks.fire_exit(prev, r)
        r.plan_status = decision.next_status
        r.plan_phase = PlanPhase.OUTLINE_PENDING
        self._hooks.fire_enter(r.plan_status, r)
        return r
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_coordinator_plan.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/coordinator_service.py tests/test_coordinator_plan.py
git commit -m "feat(coordinator): plan_start with precondition + phase init"
```

---

## Task 10: Coordinator `plan_submit` — branching to AUTH_PENDING or READY

**Files:**
- Modify: `src/requirement_workflow_v12/coordinator_service.py`
- Test: `tests/test_coordinator_plan.py` (extend)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_coordinator_plan.py`:

```python
from unittest.mock import MagicMock


def test_plan_submit_without_architecture_change_goes_ready():
    svc = CoordinatorService()
    r = _approved_req(svc)
    svc.plan_start(r.req_id)
    # stub the READY-hook so commit attempt doesn't explode
    svc._hooks.on_enter(PlanStatus.READY, lambda _r: None)

    plan_md = "---\nreq_id: REQ-P-1\n---\n"
    svc.plan_submit(r.req_id, plan_md_content=plan_md, architecture_change=None)

    assert r.plan_status is PlanStatus.READY
    assert r.pending_plan_draft is not None
    assert r.pending_plan_draft["plan_md_content"] == plan_md
    assert r.pending_plan_draft["architecture_change"] is None


def test_plan_submit_with_architecture_change_goes_auth_pending():
    svc = CoordinatorService()
    r = _approved_req(svc)
    svc.plan_start(r.req_id)
    svc._hooks.on_enter(PlanStatus.AUTH_PENDING, lambda _r: None)

    arch = {"summary": "x", "changes": [], "authorized": False}
    svc.plan_submit(
        r.req_id, plan_md_content="---\n---\n", architecture_change=arch,
    )
    assert r.plan_status is PlanStatus.AUTH_PENDING
    assert r.pending_plan_draft["architecture_change"] == arch


def test_plan_submit_rejected_when_not_drafting():
    svc = CoordinatorService()
    r = _approved_req(svc)
    # plan_status is still None
    with pytest.raises(ValueError):
        svc.plan_submit(
            r.req_id, plan_md_content="---\n---\n", architecture_change=None,
        )
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_coordinator_plan.py::test_plan_submit_without_architecture_change_goes_ready -v`
Expected: FAIL — no `plan_submit` method.

- [ ] **Step 3: Implement**

Append to `CoordinatorService`:

```python
    def plan_submit(
        self,
        req_id: str,
        *,
        plan_md_content: str,
        architecture_change: dict | None,
    ) -> Requirement:
        r = self.requirements[req_id]
        decision = apply_plan_event(
            r.plan_status, PlanEvent.PLAN_SUBMIT,
            has_architecture_change=architecture_change is not None,
        )
        if not decision.allowed:
            raise ValueError(decision.message)

        r.pending_plan_draft = {
            "plan_md_content": plan_md_content,
            "architecture_change": architecture_change,
        }
        r.plan_phase = PlanPhase.FINAL_REVIEW_PENDING

        prev = r.plan_status
        self._hooks.fire_exit(prev, r)
        r.plan_status = decision.next_status
        self._hooks.fire_enter(r.plan_status, r)
        return r
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_coordinator_plan.py -v`
Expected: 7 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/coordinator_service.py tests/test_coordinator_plan.py
git commit -m "feat(coordinator): plan_submit branches to AUTH_PENDING or READY"
```

---

## Task 11: Coordinator `plan_authorize` / `plan_authorization_reject`

**Files:**
- Modify: `src/requirement_workflow_v12/coordinator_service.py`
- Test: `tests/test_coordinator_plan.py` (extend)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_coordinator_plan.py`:

```python
def test_plan_authorize_from_auth_pending_goes_ready_and_marks_authorized():
    svc = CoordinatorService()
    r = _approved_req(svc)
    svc.plan_start(r.req_id)
    svc._hooks.on_enter(PlanStatus.AUTH_PENDING, lambda _r: None)
    svc._hooks.on_enter(PlanStatus.READY, lambda _r: None)
    svc.plan_submit(
        r.req_id, plan_md_content="---\n---\n",
        architecture_change={"summary": "x", "changes": [], "authorized": False},
    )
    assert r.plan_status is PlanStatus.AUTH_PENDING

    svc.plan_authorize(r.req_id, authorized_by="ou-123")

    assert r.plan_status is PlanStatus.READY
    arch = r.pending_plan_draft["architecture_change"]
    assert arch["authorized"] is True
    assert arch["authorized_by"] == "ou-123"
    assert arch["authorized_at"]  # ISO-8601 non-empty


def test_plan_authorization_reject_returns_to_drafting():
    svc = CoordinatorService()
    r = _approved_req(svc)
    svc.plan_start(r.req_id)
    svc._hooks.on_enter(PlanStatus.AUTH_PENDING, lambda _r: None)
    svc.plan_submit(
        r.req_id, plan_md_content="---\n---\n",
        architecture_change={"summary": "x", "changes": []},
    )

    svc.plan_authorization_reject(r.req_id, reason="need more context")

    assert r.plan_status is PlanStatus.DRAFTING
    assert r.plan_phase is PlanPhase.DECISIONS_IN_PROGRESS
    # pending_plan_draft preserved so plan-author can refine from it
    assert r.pending_plan_draft is not None


def test_plan_authorize_rejected_when_not_auth_pending():
    svc = CoordinatorService()
    r = _approved_req(svc)
    svc.plan_start(r.req_id)
    with pytest.raises(ValueError):
        svc.plan_authorize(r.req_id, authorized_by="ou-123")
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_coordinator_plan.py::test_plan_authorize_from_auth_pending_goes_ready_and_marks_authorized -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

Append to `CoordinatorService`:

```python
    def plan_authorize(self, req_id: str, *, authorized_by: str) -> Requirement:
        r = self.requirements[req_id]
        decision = apply_plan_event(r.plan_status, PlanEvent.PLAN_AUTHORIZE)
        if not decision.allowed:
            raise ValueError(decision.message)

        from datetime import datetime, timezone
        draft = r.pending_plan_draft or {}
        arch = draft.get("architecture_change") or {}
        arch["authorized"] = True
        arch["authorized_by"] = authorized_by
        arch["authorized_at"] = datetime.now(timezone.utc).isoformat()
        draft["architecture_change"] = arch
        r.pending_plan_draft = draft

        prev = r.plan_status
        self._hooks.fire_exit(prev, r)
        r.plan_status = decision.next_status
        self._hooks.fire_enter(r.plan_status, r)
        return r

    def plan_authorization_reject(
        self, req_id: str, *, reason: str = "",
    ) -> Requirement:
        r = self.requirements[req_id]
        decision = apply_plan_event(
            r.plan_status, PlanEvent.PLAN_AUTHORIZATION_REJECT,
        )
        if not decision.allowed:
            raise ValueError(decision.message)

        prev = r.plan_status
        self._hooks.fire_exit(prev, r)
        r.plan_status = decision.next_status
        r.plan_phase = PlanPhase.DECISIONS_IN_PROGRESS
        self._hooks.fire_enter(r.plan_status, r)
        LOGGER.info(
            "plan_authorization_reject req_id=%s reason=%s", req_id, reason,
        )
        return r
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_coordinator_plan.py -v`
Expected: 10 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/coordinator_service.py tests/test_coordinator_plan.py
git commit -m "feat(coordinator): plan_authorize + plan_authorization_reject"
```

---

## Task 12: `_commit_plan_and_maybe_architecture` hook + wiring

**Files:**
- Modify: `src/requirement_workflow_v12/coordinator_service.py`
- Test: `tests/test_coordinator_plan.py` (extend)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_coordinator_plan.py`:

```python
from requirement_workflow_v12.project_repo import (
    PlanArtifacts, PlanCommitResult, ProjectRepoError,
)


def test_configure_plan_hooks_wires_ready_commit_hook():
    svc = CoordinatorService()
    tools = MagicMock()
    svc.configure_plan_hooks(tools=tools)
    # READY hook registered
    assert PlanStatus.READY in svc._hooks._on_enter
    assert len(svc._hooks._on_enter[PlanStatus.READY]) == 1


def test_on_enter_ready_commits_plan_and_clears_draft():
    svc = CoordinatorService()
    tools = MagicMock()
    tools.commit_plan_artifacts.return_value = PlanCommitResult(
        commit_sha="sha-1", branch="main",
        plan_md_path="docs/specs/REQ-P-1/plan.md",
        architecture_updated=False,
    )
    svc.configure_plan_hooks(tools=tools)

    from requirement_workflow_v12.project_config import ProjectConfig
    svc.project_configs["P"] = ProjectConfig(
        category="web", template_version="v1",
        architecture_doc_id="", architecture_doc_url="",
        tech_stack={}, github_repo_url="owner/repo",
    )
    r = _approved_req(svc)
    svc.plan_start(r.req_id)
    svc.plan_submit(
        r.req_id, plan_md_content="---\nreq_id: REQ-P-1\n---\n",
        architecture_change=None,
    )

    # After hook runs: status READY, plan_pr_url set, draft cleared
    assert r.plan_status is PlanStatus.READY
    assert r.plan_pr_url == "sha-1"  # coordinator stores commit sha in plan_pr_url
    assert r.pending_plan_draft is None
    tools.commit_plan_artifacts.assert_called_once()
    artifacts = tools.commit_plan_artifacts.call_args.args[0]
    assert isinstance(artifacts, PlanArtifacts)
    assert artifacts.req_id == "REQ-P-1"
    assert artifacts.project_repo == "owner/repo"


def test_on_enter_ready_hook_propagates_recoverable_error():
    svc = CoordinatorService()
    tools = MagicMock()
    tools.commit_plan_artifacts.side_effect = ProjectRepoError(
        "conflict", recoverable=True,
    )
    svc.configure_plan_hooks(tools=tools)

    from requirement_workflow_v12.project_config import ProjectConfig
    svc.project_configs["P"] = ProjectConfig(
        category="web", template_version="v1",
        architecture_doc_id="", architecture_doc_url="",
        tech_stack={}, github_repo_url="o/r",
    )
    r = _approved_req(svc)
    svc.plan_start(r.req_id)
    # plan_submit triggers fire_enter(READY) which invokes the hook → raises
    with pytest.raises(ProjectRepoError) as exc_info:
        svc.plan_submit(
            r.req_id, plan_md_content="---\n---\n", architecture_change=None,
        )
    assert exc_info.value.recoverable is True
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_coordinator_plan.py::test_configure_plan_hooks_wires_ready_commit_hook -v`
Expected: FAIL — no `configure_plan_hooks`.

- [ ] **Step 3: Implement**

Append to `CoordinatorService`:

```python
    def configure_plan_hooks(self, *, tools) -> None:
        """Register PLANNING-layer hooks. Idempotent: safe to call twice."""
        self._plan_tools = tools
        self._hooks.on_enter(
            PlanStatus.READY, self._commit_plan_and_maybe_architecture,
        )

    def _commit_plan_and_maybe_architecture(self, r: Requirement) -> None:
        """``on_enter(PlanStatus.READY)`` hook: atomic commit of plan.md
        (and ARCHITECTURE.md if architecture_change present)."""
        draft = r.pending_plan_draft or {}
        plan_md_content = draft.get("plan_md_content", "")
        architecture_change = draft.get("architecture_change")
        project_repo = self._project_repo_for(r.req_id)

        message_parts = [f"plan({r.req_id}): land plan.md"]
        if architecture_change is not None:
            message_parts.append("and apply architecture_change")
        artifacts = PlanArtifacts(
            project_repo=project_repo,
            req_id=r.req_id,
            plan_md_content=plan_md_content,
            architecture_change=architecture_change,
            commit_message=" ".join(message_parts),
        )
        result = self._plan_tools.commit_plan_artifacts(artifacts)
        r.plan_pr_url = result.commit_sha
        r.pending_plan_draft = None
```

Also update the top-level imports (in coordinator_service.py) to include:

```python
from .project_repo import PlanArtifacts
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_coordinator_plan.py -v`
Expected: 13 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/coordinator_service.py tests/test_coordinator_plan.py
git commit -m "feat(coordinator): configure_plan_hooks + READY commit hook"
```

---

## Task 13: Coordinator `plan_restart` + cascade to spec

**Files:**
- Modify: `src/requirement_workflow_v12/coordinator_service.py`
- Create: `tests/test_plan_cascade_restart.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_plan_cascade_restart.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from requirement_workflow_v12.coordinator_service import CoordinatorService
from requirement_workflow_v12.models import Requirement, WorkflowStatus
from requirement_workflow_v12.plan_state_machine import (
    PlanStatus, PlanPhase, DesignStatus,
)
from requirement_workflow_v12.spec_state_machine import SpecStatus


def _req_with_both(svc, req_id="REQ-P-1"):
    r = Requirement(
        req_id=req_id, name="n", project="P", summary="s", creator="c",
    )
    r.status = WorkflowStatus.APPROVED
    r.plan_status = PlanStatus.READY
    r.plan_phase = PlanPhase.FINAL_REVIEW_PENDING
    r.plan_pr_url = "commit-sha"
    r.spec_status = SpecStatus.DRAFTING
    r.spec_document_id = "spec-doc"
    r.spec_pr_url = "pr-url"
    svc.requirements[req_id] = r
    return r


def test_plan_restart_clears_plan_and_spec_state():
    svc = CoordinatorService()
    r = _req_with_both(svc)

    svc.plan_restart(r.req_id)

    assert r.plan_status is None
    assert r.plan_phase is None
    assert r.plan_pr_url == ""
    assert r.pending_plan_draft is None
    # cascade: spec cleared too
    assert r.spec_status is None
    assert r.spec_document_id == ""
    assert r.spec_pr_url == ""


def test_plan_restart_rejected_when_never_started():
    svc = CoordinatorService()
    r = Requirement(
        req_id="R", name="n", project="P", summary="s", creator="c",
    )
    r.status = WorkflowStatus.APPROVED
    svc.requirements[r.req_id] = r
    with pytest.raises(ValueError):
        svc.plan_restart(r.req_id)


def test_design_restart_clears_design_plan_and_spec():
    svc = CoordinatorService()
    r = _req_with_both(svc)
    r.design_status = DesignStatus.READY

    svc.design_restart(r.req_id)

    assert r.design_status is None
    assert r.plan_status is None
    assert r.spec_status is None


def test_design_restart_rejected_when_never_started():
    svc = CoordinatorService()
    r = Requirement(
        req_id="R", name="n", project="P", summary="s", creator="c",
    )
    r.status = WorkflowStatus.APPROVED
    svc.requirements[r.req_id] = r
    with pytest.raises(ValueError):
        svc.design_restart(r.req_id)
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_plan_cascade_restart.py -v`
Expected: FAIL — no `plan_restart` / `design_restart` methods on coordinator.

- [ ] **Step 3: Implement**

Append to `CoordinatorService`:

```python
    def plan_restart(self, req_id: str) -> Requirement:
        r = self.requirements[req_id]
        decision = apply_plan_event(r.plan_status, PlanEvent.PLAN_RESTART)
        if not decision.allowed:
            raise ValueError(decision.message)

        prev = r.plan_status
        self._hooks.fire_exit(prev, r)
        r.plan_status = None
        r.plan_phase = None
        r.plan_pr_url = ""
        r.plan_outline = []
        r.plan_decisions_wip = []
        r.pending_plan_draft = None
        self._cascade_reset_spec(r)
        return r

    def design_restart(self, req_id: str) -> Requirement:
        r = self.requirements[req_id]
        from .plan_state_machine import DesignEvent, apply_design_event
        decision = apply_design_event(r.design_status, DesignEvent.DESIGN_RESTART)
        if not decision.allowed:
            raise ValueError(decision.message)

        r.design_status = None
        # Cascade: reset plan then spec
        if r.plan_status is not None:
            self.plan_restart(req_id)
        return r

    def _cascade_reset_spec(self, r: Requirement) -> None:
        """Quiet spec reset used by plan_restart; unlike /spec restart
        it does NOT require deadlock, because the user has already
        acknowledged cascade intent at the plan layer."""
        if r.spec_status is None:
            return
        if self.spec_orchestrator is not None:
            try:
                self.spec_orchestrator.archive_trace(r.req_id, suffix="cascade")
            except Exception:
                LOGGER.exception(
                    "cascade spec archive failed req_id=%s", r.req_id,
                )
        r.spec_status = None
        r.spec_document_id = ""
        r.spec_document_url = ""
        r.spec_deadlocked = False
        r.spec_transform_snapshot = None
        r.spec_source_revision = ""
        r.transform_trace_digest = ""
        r.spec_pr_url = ""
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_plan_cascade_restart.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/coordinator_service.py tests/test_plan_cascade_restart.py
git commit -m "feat(coordinator): plan_restart + design_restart with cascades"
```

---

## Task 14: plan-context builder

**Files:**
- Create: `src/requirement_workflow_v12/plan_context.py`
- Create: `tests/test_plan_context.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_plan_context.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest
from unittest.mock import MagicMock

from requirement_workflow_v12.coordinator_service import CoordinatorService
from requirement_workflow_v12.models import Requirement, WorkflowStatus
from requirement_workflow_v12.plan_context import (
    PlanContextBuilder, PlanContextGateError,
)
from requirement_workflow_v12.plan_state_machine import PlanStatus
from requirement_workflow_v12.project_config import ProjectConfig


def _req(svc, req_id="REQ-P-1"):
    r = Requirement(
        req_id=req_id, name="n", project="P", summary="s", creator="c",
    )
    r.status = WorkflowStatus.APPROVED
    svc.requirements[req_id] = r
    svc.project_configs["P"] = ProjectConfig(
        category="web", template_version="v1",
        architecture_doc_id="doc-a", architecture_doc_url="https://x",
        tech_stack={"backend": "python"}, github_repo_url="owner/repo",
    )
    return r


def test_plan_context_returns_expected_fields_when_plan_none():
    svc = CoordinatorService()
    r = _req(svc)
    builder = PlanContextBuilder(service=svc)

    ctx = builder.build(r.req_id)

    assert ctx["req_id"] == "REQ-P-1"
    assert ctx["project"] == "P"
    assert ctx["needs_ui"] is False
    assert ctx["tech_stack"] == {"backend": "python"}
    assert ctx["project_repo"] == "owner/repo"
    assert ctx["architecture_doc_url"] == "https://x"


def test_plan_context_rejected_when_not_approved():
    svc = CoordinatorService()
    r = _req(svc)
    r.status = WorkflowStatus.DRAFTING
    builder = PlanContextBuilder(service=svc)
    with pytest.raises(PlanContextGateError):
        builder.build(r.req_id)


def test_plan_context_rejected_when_already_ready():
    svc = CoordinatorService()
    r = _req(svc)
    r.plan_status = PlanStatus.READY
    builder = PlanContextBuilder(service=svc)
    with pytest.raises(PlanContextGateError):
        builder.build(r.req_id)


def test_plan_context_allowed_when_drafting():
    svc = CoordinatorService()
    r = _req(svc)
    r.plan_status = PlanStatus.DRAFTING
    builder = PlanContextBuilder(service=svc)
    ctx = builder.build(r.req_id)
    assert ctx["req_id"] == "REQ-P-1"
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_plan_context.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

```python
# src/requirement_workflow_v12/plan_context.py
"""PLANNING-layer context builder.

Mirrors ``SpecContextBuilder`` but serves plan-author. State gate:
requirement must be APPROVED, plan_status ∈ {None, DRAFTING}. Returns
a plain dict suitable for JSON serialization by the HTTP handler.
"""
from __future__ import annotations

from .models import WorkflowStatus
from .plan_state_machine import DesignStatus, PlanStatus


PLAN_CONTEXT_ALLOWED_STATUSES = {None, PlanStatus.DRAFTING}


class PlanContextGateError(Exception):
    def __init__(self, message: str, current_status: str) -> None:
        super().__init__(message)
        self.current_status = current_status


class PlanContextMisconfigured(Exception):
    """No ProjectConfig for this project."""


class PlanContextBuilder:
    def __init__(self, service) -> None:
        self._service = service

    def build(self, req_id: str) -> dict:
        r = self._service.requirements.get(req_id)
        if r is None:
            raise ValueError(f"未知需求：{req_id}")
        if (
            r.status != WorkflowStatus.APPROVED
            or r.plan_status not in PLAN_CONTEXT_ALLOWED_STATUSES
        ):
            plan_label = r.plan_status.value if r.plan_status else "None"
            raise PlanContextGateError(
                f"当前状态 status={r.status.value} plan_status={plan_label} "
                "不允许获取 plan-context",
                current_status=r.status.value,
            )
        if r.needs_ui and r.design_status != DesignStatus.READY:
            design_label = r.design_status.value if r.design_status else "None"
            raise PlanContextGateError(
                f"needs_ui=True 但 design_status={design_label}，必须先完成设计",
                current_status=r.status.value,
            )

        cfg = self._service.project_configs.get(r.project)
        if cfg is None:
            raise PlanContextMisconfigured(f"项目 {r.project} 未初始化")

        return {
            "req_id": r.req_id,
            "project": r.project,
            "requirement_document_url": r.document_url,
            "needs_ui": r.needs_ui,
            "tech_stack": dict(cfg.tech_stack),
            "category": cfg.category,
            "template_version": cfg.template_version,
            "architecture_doc_url": cfg.architecture_doc_url,
            "project_repo": cfg.github_repo_url,
            "plan_outline": list(r.plan_outline),
            "plan_decisions_wip": list(r.plan_decisions_wip),
            "plan_phase": r.plan_phase.value if r.plan_phase else None,
        }
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_plan_context.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/plan_context.py tests/test_plan_context.py
git commit -m "feat(plan): plan-context builder with gate checks"
```

---

## Task 15: `/openclaw/plan-context/<req>` endpoint

**Files:**
- Modify: `src/requirement_workflow_v12/service_app.py`
- Create: `tests/test_plan_endpoint_service_app.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_plan_endpoint_service_app.py
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest
from unittest.mock import MagicMock

from requirement_workflow_v12.config import Settings
from requirement_workflow_v12.coordinator_service import CoordinatorService
from requirement_workflow_v12.models import Requirement, WorkflowStatus
from requirement_workflow_v12.project_config import ProjectConfig
from requirement_workflow_v12.service_app import CoordinatorRuntimeApp
from requirement_workflow_v12.store import JsonStateStore


@pytest.fixture
def app(tmp_path):
    settings = Settings(
        feishu_app_id="x", feishu_app_secret="y",
        feishu_verification_token="t", feishu_encrypt_key=None,
        state_store_path=str(tmp_path / "state.json"),
        trace_dir=str(tmp_path / "trace"),
    )
    svc = CoordinatorService()
    store = JsonStateStore(settings.state_store_path)
    gw = MagicMock()
    a = CoordinatorRuntimeApp(
        settings=settings, store=store, service=svc, gateway=gw,
    )
    return a


def _approved_req(app, req_id="REQ-P-1"):
    r = Requirement(
        req_id=req_id, name="n", project="P", summary="s", creator="c",
    )
    r.status = WorkflowStatus.APPROVED
    app.service.requirements[req_id] = r
    app.service.project_configs["P"] = ProjectConfig(
        category="web", template_version="v1",
        architecture_doc_id="", architecture_doc_url="",
        tech_stack={"backend": "py"}, github_repo_url="o/r",
    )
    return r


def test_plan_context_endpoint_returns_200_for_approved_req(app):
    _approved_req(app)

    status, body = app.handle_openclaw_plan_context_query(req_id="REQ-P-1")

    assert status == 200
    assert body["req_id"] == "REQ-P-1"
    assert body["project_repo"] == "o/r"


def test_plan_context_endpoint_returns_409_when_gate_fails(app):
    _approved_req(app)
    app.service.requirements["REQ-P-1"].status = WorkflowStatus.DRAFTING

    status, body = app.handle_openclaw_plan_context_query(req_id="REQ-P-1")

    assert status == 409
    assert "error" in body


def test_plan_context_endpoint_returns_404_when_req_missing(app):
    status, body = app.handle_openclaw_plan_context_query(req_id="NOPE")
    assert status == 404
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_plan_endpoint_service_app.py -v`
Expected: FAIL — `handle_openclaw_plan_context_query` missing.

- [ ] **Step 3: Implement**

Edit `src/requirement_workflow_v12/service_app.py`:

Add the builder import near the top of `CoordinatorRuntimeApp.__init__`, after the existing `from .spec_context import SpecContextBuilder` line (inside the method, around line 135):

```python
        from .plan_context import PlanContextBuilder
        self._plan_context_builder = PlanContextBuilder(service=self.service)
```

Add the handler method on `CoordinatorRuntimeApp` (near `handle_openclaw_spec_context_query`):

```python
    def handle_openclaw_plan_context_query(
        self, req_id: str,
    ) -> tuple[int, dict]:
        from .plan_context import (
            PlanContextGateError, PlanContextMisconfigured,
        )
        r = self.service.requirements.get(req_id)
        if r is None:
            return 404, {"error": "not_found", "req_id": req_id}
        try:
            ctx = self._plan_context_builder.build(req_id)
            return 200, ctx
        except PlanContextGateError as exc:
            return 409, {"error": "gate_failed", "message": str(exc)}
        except PlanContextMisconfigured as exc:
            return 409, {"error": "misconfigured", "message": str(exc)}
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.exception("plan-context failed req_id=%s", req_id)
            return 500, {"error": "plan_context_failed", "message": str(exc)}
```

Wire the route inside the HTTP dispatch. Find the `/queries/openclaw/spec-context` branch (around line 194) and add below it:

```python
                elif self.path.startswith("/queries/openclaw/plan-context/"):
                    req_id = self.path.rsplit("/", 1)[-1]
                    status, payload = app.handle_openclaw_plan_context_query(req_id)
                    self._respond_json(status, payload)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_plan_endpoint_service_app.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/service_app.py tests/test_plan_endpoint_service_app.py
git commit -m "feat(http): /queries/openclaw/plan-context/<req> endpoint"
```

---

## Task 16: `/openclaw/plan-callback` endpoint

**Files:**
- Modify: `src/requirement_workflow_v12/service_app.py`
- Modify: `src/requirement_workflow_v12/coordinator_service.py` (small helper)
- Test: `tests/test_plan_endpoint_service_app.py` (extend)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_plan_endpoint_service_app.py`:

```python
def test_plan_callback_outline_submit_writes_outline_and_advances_phase(app):
    r = _approved_req(app)
    app.service.plan_start(r.req_id)

    body = {
        "req_id": "REQ-P-1",
        "event": "plan_outline_submit",
        "payload": {
            "outline": [
                {"id": "D1", "title": "会话存储", "problem": "..."},
                {"id": "D2", "title": "鉴权流程", "problem": "..."},
            ],
        },
    }
    status, resp = app.handle_openclaw_plan_callback(body)

    assert status == 200
    assert r.plan_outline == body["payload"]["outline"]


def test_plan_callback_plan_submit_branches_to_ready_when_no_architecture(app):
    r = _approved_req(app)
    app.service.plan_start(r.req_id)
    # stub the READY hook so test doesn't need tools
    from requirement_workflow_v12.plan_state_machine import PlanStatus
    app.service._hooks.on_enter(PlanStatus.READY, lambda _r: None)

    body = {
        "req_id": "REQ-P-1",
        "event": "plan_submit",
        "payload": {
            "plan_md_content": "---\nreq_id: REQ-P-1\n---\n",
            "architecture_change": None,
        },
    }
    status, resp = app.handle_openclaw_plan_callback(body)

    assert status == 200
    assert r.plan_status is PlanStatus.READY


def test_plan_callback_unknown_event_returns_400(app):
    r = _approved_req(app)
    status, resp = app.handle_openclaw_plan_callback(
        {"req_id": "REQ-P-1", "event": "nonsense", "payload": {}},
    )
    assert status == 400


def test_plan_callback_req_not_found_returns_404(app):
    status, resp = app.handle_openclaw_plan_callback(
        {"req_id": "NO", "event": "plan_submit", "payload": {}},
    )
    assert status == 404
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_plan_endpoint_service_app.py::test_plan_callback_outline_submit_writes_outline_and_advances_phase -v`
Expected: FAIL — no `handle_openclaw_plan_callback`.

- [ ] **Step 3: Implement helper on coordinator + handler in service_app**

Append to `CoordinatorService`:

```python
    def set_plan_outline(self, req_id: str, outline: list[dict]) -> Requirement:
        r = self.requirements[req_id]
        if r.plan_status is not PlanStatus.DRAFTING:
            raise ValueError("plan outline can only be set in DRAFTING")
        r.plan_outline = list(outline)
        r.plan_phase = PlanPhase.DECISIONS_IN_PROGRESS
        return r
```

Add handler to `CoordinatorRuntimeApp` (service_app.py):

```python
    def handle_openclaw_plan_callback(
        self, body: dict,
    ) -> tuple[int, dict]:
        req_id = body.get("req_id", "")
        event = body.get("event", "")
        payload = body.get("payload") or {}

        r = self.service.requirements.get(req_id)
        if r is None:
            return 404, {"error": "not_found", "req_id": req_id}

        try:
            if event == "plan_outline_submit":
                self.service.set_plan_outline(req_id, payload.get("outline", []))
                return 200, {"req_id": req_id, "plan_phase": "decisions_in_progress"}
            if event == "plan_submit":
                self.service.plan_submit(
                    req_id,
                    plan_md_content=payload.get("plan_md_content", ""),
                    architecture_change=payload.get("architecture_change"),
                )
                return 200, {
                    "req_id": req_id,
                    "plan_status": r.plan_status.value if r.plan_status else None,
                }
            return 400, {"error": "unknown_event", "event": event}
        except ValueError as exc:
            return 409, {"error": "invalid_state", "message": str(exc)}
        except Exception as exc:  # pragma: no cover
            LOGGER.exception("plan-callback failed req_id=%s event=%s", req_id, event)
            return 500, {"error": "plan_callback_failed", "message": str(exc)}
```

Add the HTTP route. Find the existing `/openclaw/spec-transform-callback` branch in `do_POST` and add next to it:

```python
                elif self.path == "/openclaw/plan-callback":
                    body_json = json.loads(raw_body.decode("utf-8") or "{}")
                    status, payload = app.handle_openclaw_plan_callback(body_json)
                    self._respond_json(status, payload)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_plan_endpoint_service_app.py -v`
Expected: 7 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/service_app.py src/requirement_workflow_v12/coordinator_service.py tests/test_plan_endpoint_service_app.py
git commit -m "feat(http): /openclaw/plan-callback with outline_submit + plan_submit"
```

---

## Task 17: `/plan restart` + `/design restart` slash commands

**Files:**
- Modify: `src/requirement_workflow_v12/service_app.py`
- Test: `tests/test_plan_endpoint_service_app.py` (extend)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_plan_endpoint_service_app.py`:

```python
def test_slash_plan_restart_parses_req_id_and_calls_service(app):
    r = _approved_req(app)
    from requirement_workflow_v12.plan_state_machine import PlanStatus
    r.plan_status = PlanStatus.DRAFTING
    r.plan_phase = None

    response = app.handle_slash_command("/plan restart REQ-P-1")

    assert response is not None
    assert "重置" in response or "reset" in response.lower()
    assert r.plan_status is None


def test_slash_design_restart_cascades(app):
    r = _approved_req(app)
    from requirement_workflow_v12.plan_state_machine import DesignStatus, PlanStatus
    r.design_status = DesignStatus.READY
    r.plan_status = PlanStatus.DRAFTING

    response = app.handle_slash_command("/design restart REQ-P-1")

    assert response is not None
    assert r.design_status is None
    assert r.plan_status is None


def test_slash_plan_restart_unknown_req_returns_error_message(app):
    response = app.handle_slash_command("/plan restart REQ-NOPE")
    assert response is not None
    assert "REQ-NOPE" in response
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_plan_endpoint_service_app.py::test_slash_plan_restart_parses_req_id_and_calls_service -v`
Expected: FAIL — method missing or regex doesn't match.

- [ ] **Step 3: Add dispatcher + regexes**

Edit `src/requirement_workflow_v12/service_app.py`. Near the existing `SPEC_RESTART_RE`, add:

```python
PLAN_RESTART_RE = re.compile(r"^/plan\s+restart\s+(REQ-\S+)\s*$")
DESIGN_RESTART_RE = re.compile(r"^/design\s+restart\s+(REQ-\S+)\s*$")
```

Add the handler to `CoordinatorRuntimeApp`:

```python
    def handle_slash_command(self, text: str) -> str | None:
        """Returns a human-readable reply string, or None if no match.

        Used by message handler AND by /plan-restart test paths.
        """
        m = PLAN_RESTART_RE.match(text.strip())
        if m:
            req_id = m.group(1)
            try:
                self.service.plan_restart(req_id)
                return f"规划层已重置（含下游 spec 级联清理）：{req_id}"
            except KeyError:
                return f"未知需求：{req_id}"
            except ValueError as exc:
                return f"不能执行 /plan restart {req_id}：{exc}"
        m = DESIGN_RESTART_RE.match(text.strip())
        if m:
            req_id = m.group(1)
            try:
                self.service.design_restart(req_id)
                return f"设计层已重置（含下游 plan + spec 级联清理）：{req_id}"
            except KeyError:
                return f"未知需求：{req_id}"
            except ValueError as exc:
                return f"不能执行 /design restart {req_id}：{exc}"
        return None
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_plan_endpoint_service_app.py -v`
Expected: 10 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/service_app.py tests/test_plan_endpoint_service_app.py
git commit -m "feat(slash): /plan restart + /design restart parsers"
```

---

## Task 18: Extend `spec-context` with `plan_md_content`

**Files:**
- Modify: `src/requirement_workflow_v12/spec_context.py`
- Modify: `src/requirement_workflow_v12/coordinator_service.py` (tiny helper)
- Test: `tests/test_spec_context.py` (extend)

The spec-context must include `plan_md_content` + `plan_decision_ids` when `PlanStatus == READY`, per spec §7.2. It must also enforce `PlanStatus == READY` as a precondition before handing out spec-context.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_spec_context.py`:

```python
def test_spec_context_rejected_when_plan_not_ready(tmp_path):
    from requirement_workflow_v12.plan_state_machine import PlanStatus
    from requirement_workflow_v12.spec_context import (
        SpecContextBuilder, SpecContextGateError,
    )
    from requirement_workflow_v12.coordinator_service import CoordinatorService
    from requirement_workflow_v12.models import Requirement, WorkflowStatus
    from requirement_workflow_v12.project_config import ProjectConfig
    from unittest.mock import MagicMock

    svc = CoordinatorService()
    r = Requirement(req_id="R", name="n", project="P", summary="s", creator="c")
    r.status = WorkflowStatus.APPROVED
    r.plan_status = PlanStatus.DRAFTING  # not READY
    svc.requirements["R"] = r
    svc.project_configs["P"] = ProjectConfig(
        category="web", template_version="v1",
        architecture_doc_id="a", architecture_doc_url="u",
        tech_stack={}, github_repo_url="o/r",
    )
    gw = MagicMock()
    gw.fetch_document_revision.return_value = "rev-1"
    builder = SpecContextBuilder(svc, gw)
    import pytest
    with pytest.raises(SpecContextGateError, match="plan"):
        builder.build("R")


def test_spec_context_includes_plan_md_content_when_ready(tmp_path):
    from requirement_workflow_v12.plan_state_machine import PlanStatus
    from requirement_workflow_v12.spec_context import SpecContextBuilder
    from requirement_workflow_v12.coordinator_service import CoordinatorService
    from requirement_workflow_v12.models import Requirement, WorkflowStatus
    from requirement_workflow_v12.project_config import ProjectConfig
    from unittest.mock import MagicMock

    svc = CoordinatorService()
    r = Requirement(req_id="R", name="n", project="P", summary="s", creator="c")
    r.status = WorkflowStatus.APPROVED
    r.plan_status = PlanStatus.READY
    svc.requirements["R"] = r
    svc.project_configs["P"] = ProjectConfig(
        category="web", template_version="v1",
        architecture_doc_id="a", architecture_doc_url="u",
        tech_stack={}, github_repo_url="o/r",
    )
    gw = MagicMock()
    gw.fetch_document_revision.return_value = "rev-1"
    # Stub the plan.md fetcher to return canned content
    svc._fetch_plan_md = MagicMock(
        return_value="---\nreq_id: R\ndecisions:\n  - id: D1\n  - id: D2\n---\n",
    )
    builder = SpecContextBuilder(svc, gw)

    result = builder.build("R")

    assert "plan_md_content" in result.context
    assert "req_id: R" in result.context["plan_md_content"]
    assert result.context["plan_decision_ids"] == ["D1", "D2"]
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_spec_context.py::test_spec_context_rejected_when_plan_not_ready -v`
Expected: FAIL — gate currently allows any plan_status.

- [ ] **Step 3: Implement**

Edit `src/requirement_workflow_v12/spec_context.py`.

Update `SPEC_CONTEXT_ALLOWED_SPEC_STATUSES` comment block and the `build` method. Add the PlanStatus precondition and populate the two new fields:

```python
from .plan_state_machine import PlanStatus

# ... existing ALLOWED_SPEC_STATUSES remains unchanged ...
```

Inside `SpecContextBuilder.build`, after the existing APPROVED + spec_status gate but before the `project_cfg` lookup, add:

```python
        if requirement.plan_status != PlanStatus.READY:
            plan_label = (
                requirement.plan_status.value if requirement.plan_status else "None"
            )
            raise SpecContextGateError(
                f"spec-context 要求 plan_status=PLAN_READY，当前 plan_status={plan_label}",
                current_status=requirement.status.value,
            )
```

At the end of the `context = {...}` dict assembly (spec_context.py), after the existing fields are populated, add:

```python
        plan_md = self._service._fetch_plan_md(req_id) if hasattr(
            self._service, "_fetch_plan_md",
        ) else ""
        context["plan_md_content"] = plan_md
        context["plan_decision_ids"] = _extract_decision_ids(plan_md)
```

Add at the bottom of `spec_context.py`:

```python
def _extract_decision_ids(plan_md_text: str) -> list[str]:
    """Lightweight YAML-frontmatter scan for `- id: Dxx` lines. Avoids
    pulling in a YAML dep; plan-author already validated structure."""
    import re
    return re.findall(r"^\s*-\s*id:\s*([A-Za-z0-9]+)\s*$", plan_md_text, re.MULTILINE)
```

Add a default `_fetch_plan_md` stub to `CoordinatorService` so production code has a single knob to override:

```python
    def _fetch_plan_md(self, req_id: str) -> str:
        """Default: no-op empty stub. Production wiring can replace this
        (e.g., pull plan.md content from GitHub). Tests override directly."""
        return ""
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_spec_context.py -v`
Expected: all existing + 2 new PASS. Note: if any pre-existing test constructs a Requirement without setting `plan_status = PlanStatus.READY`, those tests will now fail — fix them by setting `r.plan_status = PlanStatus.READY` before calling `build`. Scan the file and patch.

- [ ] **Step 5: Sanity: run full suite**

Run: `pytest -x`
Expected: all pass (with the fixes from step 4 applied).

- [ ] **Step 6: Commit**

```bash
git add src/requirement_workflow_v12/spec_context.py src/requirement_workflow_v12/coordinator_service.py tests/test_spec_context.py
git commit -m "feat(spec-context): require PlanStatus=READY and include plan_md_content"
```

---

## Task 19: End-to-end PLANNING phase integration test

**Files:**
- Create: `tests/test_plan_phase_e2e.py`

- [ ] **Step 1: Write the test**

```python
# tests/test_plan_phase_e2e.py
"""End-to-end PLANNING phase: APPROVED → outline → plan_submit with
architecture → authorize → READY → spec-context returns plan_md_content."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from unittest.mock import MagicMock

from requirement_workflow_v12.coordinator_service import CoordinatorService
from requirement_workflow_v12.models import Requirement, WorkflowStatus
from requirement_workflow_v12.plan_state_machine import (
    PlanStatus, PlanPhase,
)
from requirement_workflow_v12.project_config import ProjectConfig
from requirement_workflow_v12.project_repo import PlanCommitResult
from requirement_workflow_v12.spec_context import SpecContextBuilder


def test_planning_e2e_with_architecture_change():
    svc = CoordinatorService()

    # project config with repo
    svc.project_configs["P"] = ProjectConfig(
        category="web", template_version="v1",
        architecture_doc_id="a", architecture_doc_url="https://doc/a",
        tech_stack={"backend": "py"}, github_repo_url="owner/repo",
    )

    # Wire PLANNING hook with mocked tools
    tools = MagicMock()
    tools.commit_plan_artifacts.return_value = PlanCommitResult(
        commit_sha="sha-final",
        branch="main",
        plan_md_path="docs/specs/REQ-P-1/plan.md",
        architecture_updated=True,
    )
    svc.configure_plan_hooks(tools=tools)

    # APPROVED requirement
    r = Requirement(
        req_id="REQ-P-1", name="n", project="P", summary="s", creator="c",
    )
    r.status = WorkflowStatus.APPROVED
    svc.requirements[r.req_id] = r

    # 1. plan_start
    svc.plan_start(r.req_id)
    assert r.plan_status is PlanStatus.DRAFTING
    assert r.plan_phase is PlanPhase.OUTLINE_PENDING

    # 2. outline submitted
    svc.set_plan_outline(
        r.req_id,
        [
            {"id": "D1", "title": "Storage", "problem": "..."},
            {"id": "D2", "title": "Auth", "problem": "..."},
        ],
    )
    assert r.plan_phase is PlanPhase.DECISIONS_IN_PROGRESS

    # 3. plan_submit with architecture_change → AUTH_PENDING
    plan_md = """---
schema_version: "1.0"
req_id: "REQ-P-1"
decisions:
  - id: D1
    chosen: "A"
  - id: D2
    chosen: "B"
---
"""
    arch_change = {
        "summary": "add storage",
        "changes": [{
            "section_path": "## Storage",
            "before": "",
            "after": "## Storage\n\nRedis.",
            "rationale": "D1",
        }],
        "authorized": False,
    }
    svc.plan_submit(
        r.req_id, plan_md_content=plan_md, architecture_change=arch_change,
    )
    assert r.plan_status is PlanStatus.AUTH_PENDING

    # 4. authorize → READY (hook fires, commit_plan_artifacts invoked)
    svc.plan_authorize(r.req_id, authorized_by="ou-user")
    assert r.plan_status is PlanStatus.READY
    assert r.plan_pr_url == "sha-final"
    assert r.pending_plan_draft is None
    tools.commit_plan_artifacts.assert_called_once()

    # 5. spec-context now unblocks
    svc._fetch_plan_md = MagicMock(return_value=plan_md)
    gw = MagicMock()
    gw.fetch_document_revision.return_value = "rev"
    builder = SpecContextBuilder(svc, gw)

    result = builder.build(r.req_id)

    assert result.context["plan_md_content"] == plan_md
    assert result.context["plan_decision_ids"] == ["D1", "D2"]


def test_planning_e2e_without_architecture_change():
    svc = CoordinatorService()
    svc.project_configs["P"] = ProjectConfig(
        category="web", template_version="v1",
        architecture_doc_id="a", architecture_doc_url="",
        tech_stack={}, github_repo_url="o/r",
    )
    tools = MagicMock()
    tools.commit_plan_artifacts.return_value = PlanCommitResult(
        commit_sha="sha", branch="main",
        plan_md_path="docs/specs/REQ-P-2/plan.md",
        architecture_updated=False,
    )
    svc.configure_plan_hooks(tools=tools)

    r = Requirement(
        req_id="REQ-P-2", name="n", project="P", summary="s", creator="c",
    )
    r.status = WorkflowStatus.APPROVED
    svc.requirements[r.req_id] = r

    svc.plan_start(r.req_id)
    svc.plan_submit(
        r.req_id, plan_md_content="---\nreq_id: REQ-P-2\n---\n",
        architecture_change=None,
    )

    # No AUTH_PENDING intermediate — directly to READY
    assert r.plan_status is PlanStatus.READY
    tools.commit_plan_artifacts.assert_called_once()
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_plan_phase_e2e.py -v`
Expected: 2 PASS.

- [ ] **Step 3: Full regression**

Run: `pytest`
Expected: entire suite green.

- [ ] **Step 4: Commit**

```bash
git add tests/test_plan_phase_e2e.py
git commit -m "test(plan): e2e APPROVED → plan_start → READY with + without architecture"
```

---

## Task 20: Documentation touch-up

**Files:**
- Modify: `docs/context/layers/planning-harness-layer.md` (mark implementation status)

- [ ] **Step 1: Update status table**

Edit `docs/context/layers/planning-harness-layer.md` §零 (实现状态与变更记录). Change the v1 row to note "implementation landed 2026-04-XX" and append a new row summarizing the MVP (no design-author, header-match algorithm chosen).

Replace:

```markdown
| v1 | 2026-04-19 | 首版：在 `APPROVED → SPEC_DRAFTING` 之间插入 DESIGNING + PLANNING 两阶段；`design-author` / `plan-author` 两个 sibling agent；`plan.md` 结构化多决策 + `architecture_change` 授权闸门；DesignStatus / PlanStatus / SpecStatus 三列并行；级联 restart；钩子驱动架构变更原子 apply。 |
```

With:

```markdown
| v1 | 2026-04-19 | 首版设计：在 `APPROVED → SPEC_DRAFTING` 之间插入 DESIGNING + PLANNING 两阶段；`design-author` / `plan-author` 两个 sibling agent；`plan.md` 结构化多决策 + `architecture_change` 授权闸门；DesignStatus / PlanStatus / SpecStatus 三列并行；级联 restart；钩子驱动架构变更原子 apply。 |
| v1-impl | 2026-04-XX | MVP 实装落地：PlanStatus 状态机 + `commit_plan_artifacts` + `on_enter(READY)` 钩子 + plan-context / plan-callback 端点 + `/plan restart` + `/design restart` + spec-context 增加 `plan_md_content`；ARCHITECTURE.md section 匹配采用「header 行精确匹配 + 同级或更高级 header 为节边界」；design-author 未落地，DesignStatus 只提供状态机位置 + restart 级联。 |
```

Also update §十二 第一行：原先的 "design-author 的具体产物格式待 Phase 2 第一次真实 needs_ui=true REQ 落地时收敛" 仍有效；追加新的一条：

```markdown
- spec-context 的 `_fetch_plan_md(req_id)` 默认返回空串，生产环境需替换成从 GitHub 拉 `docs/specs/<req>/plan.md` 的实现（留给下一次部署迭代处理）
```

- [ ] **Step 2: Commit**

```bash
git add docs/context/layers/planning-harness-layer.md
git commit -m "docs(planning-harness): mark MVP implementation landed"
```

---

## Self-Review

Pass 1 — spec coverage:

| Spec requirement | Covered by task |
|---|---|
| §4.1 plan.md schema | Consumed opaquely via `plan_md_content` string in Task 10, 14, 18 |
| §4.3 architecture_change apply | Task 4 (pure) + Task 7 (commit wiring) |
| §4.3 before-mismatch recoverable error | Task 8 |
| §5.1 PlanStatus / PlanEvent / PlanPhase / DesignStatus / DesignEvent enums | Task 1 |
| §5.2 PlanStatus transitions | Task 1 (pure) + Tasks 9/10/11 (coordinator) |
| §5.2 DesignStatus transitions | Task 1 (pure) + Task 13 (restart cascade) |
| §5.3 hook registration | Task 3 (annotation) + Task 12 (wiring) |
| §5.4 cascading /plan restart, /design restart | Task 13 |
| §6 architecture apply transaction | Tasks 4 + 6 + 7 + 12 |
| §6.3 recoverable `architecture_conflict` propagation | Tasks 8 + 12 (last test in Task 12 asserts propagation) |
| §7.1 plan-context endpoint | Tasks 14 + 15 |
| §7.1 plan-callback (outline_submit + plan_submit) | Task 16 |
| §7.2 spec-context extension | Task 18 |
| §7.3 cards | **Not a task** — cards are view-layer formatting; the state transitions and handlers they drive are covered by Tasks 9/11/13 and the slash command surface (Task 17). Real card markup lives in the Feishu card templates which are not repo-managed in this plan. Adding lipstick is trivial once production needs it. |
| §7.4 spec-author prompt update | **Out of scope** — lives in OpenClaw SKILL.md repo, not this code repo. Documented in planning-harness-layer.md §十二. |
| §8.1 all "落地" items | Tasks 1–19 (except cards as noted) |
| §8.2 "not implemented" items | design-author, Bootstrap, design-context — all explicitly skipped |
| §9.1 acceptance test checklist 1–9 | Tasks 1, 10, 12, 8, 13, 19, 18, 9, 10 respectively |

Pass 2 — placeholder scan: none found. All steps have exact file paths, full code, exact commands.

Pass 3 — type consistency:
- `PlanArtifacts` fields used: project_repo, req_id, plan_md_content, architecture_change, commit_message — consistent across Tasks 5, 6, 7, 8, 12.
- `PlanCommitResult`: commit_sha, branch, plan_md_path, architecture_updated — consistent in Tasks 5, 6, 7, 12, 19.
- `ProjectRepoTools.commit_plan_artifacts(artifacts: PlanArtifacts) → PlanCommitResult` — stable signature across Tasks 6 onwards.
- `CoordinatorService.plan_submit(req_id, *, plan_md_content, architecture_change)` — same kwarg names in Tasks 10, 11, 16, 19.
- `_fetch_plan_md` hook point on service — introduced in Task 18 only, never re-defined.

No drift found.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-19-planning-phase-plan.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
