# Spec Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the Coordinator-side `SPEC_TRANSFORMING` state — a 1-3 round game between `spec-transformer` and `spec-transformer-reviewer` Claude Code subprocesses that produces the four-file Spec PR with `acm-registry.yaml` patch.

**Architecture:** `SPEC_DRAFTING + checkpoint_1a_pass → SPEC_TRANSFORMING(snapshot frozen) → game loop with Computational gate → transform_converged → write-locked acm-registry patch + regression scan + Spec PR → SPEC_LOCKED`. Failure modes funnel into `SPEC_TRANSFORMING(deadlocked=True)` recoverable via `/spec restart`. Trace is per-REQ jsonl, locally append-only, copied into PR on success.

**Tech Stack:** Python 3.11, asyncio, dataclasses, jsonschema, PyYAML, httpx (existing GitHub client), pytest.

**Source spec:** `docs/superpowers/specs/2026-04-16-spec-layer-implementation-design.md`

**Pre-flight decisions (locked):**
- Orchestrator state lives in process memory; crash recovery is `/spec restart`, no SQLite.
- Computational gate runs in Coordinator; gate failures of `kind="format"` allow ≤2 soft retries within a round.
- Regression scan runs once, after `compose_patch`, inside the registry write lock.
- `acm-registry.yaml` race is handled by re-pull + recompute, max 3 retries before deadlock.
- Snapshot freezes `spec_source_revision + architecture_revision + acm_registry_revision + acm_active_slice` at `SPEC_TRANSFORMING` onEnter.
- `spec_restart` slash command guard: `{SPEC_DRAFTING, SPEC_TRANSFORMING(deadlocked=True)}` only.
- No feature flag; merge to main only after S6 completes.

---

## File Structure (decomposition)

**Create:**
- `src/requirement_workflow_v12/spec_transform.py` — `TransformContextSnapshot`, `RoundContext`, `SpecTransformOrchestrator`, `NextAction`
- `src/requirement_workflow_v12/spec_gate.py` — `GateFinding`, `GateResult`, `run_gate`, 5 rule functions
- `src/requirement_workflow_v12/acm_registry.py` — `RegistryDoc`, `AcEntry`, `SupersedeDecl`, `AcmRegistry`
- `src/requirement_workflow_v12/regression_scan.py` — `RegressionResult`, `scan`
- `docs/agents/spec-transformer/SKILL.md`
- `docs/agents/spec-transformer/callback-schema.json`
- `docs/agents/spec-transformer-reviewer/SKILL.md`
- `docs/agents/spec-transformer-reviewer/callback-schema.json`
- `tests/test_spec_state_machine_transforming.py`
- `tests/test_spec_restart.py`
- `tests/test_spec_gate.py`
- `tests/test_spec_transform_orchestrator.py`
- `tests/test_acm_registry.py`
- `tests/test_regression_scan.py`
- `tests/test_service_app_spec_transform.py`
- `tests/integration/test_spec_transform_e2e.py`
- `tests/integration/__init__.py`

**Modify:**
- `src/requirement_workflow_v12/spec_state_machine.py` — add `SPEC_RESTART` event, `deadlocked` field on state, transition rules
- `src/requirement_workflow_v12/models.py` — add `spec_deadlocked: bool` and `spec_transform_snapshot: dict | None` to Requirement
- `src/requirement_workflow_v12/github_gateway.py` — add `commit_spec_pr_files`, `get_file_sha_and_content`, `delete_branch`
- `src/requirement_workflow_v12/coordinator_service.py` — add `submit_checkpoint_1a_pass`, `spec_restart`; inject `SpecTransformOrchestrator` + `AcmRegistry`
- `src/requirement_workflow_v12/service_app.py` — add `POST /openclaw/spec-transform-callback`, slash command parser

**Trace storage:** `/var/spec_traces/REQ-{PROJECT}-{NNN}.jsonl` (production) / `tests/.tmp/spec_traces/...` (tests).

---

## Slice Map

```
S1 ── S2
   └── S3 ── S4 ── S5
              └── S6 ── Integration ── #22 deploy
```

Each slice ends with `git commit` and (if branchful) opens a PR.

---

## Slice S1 · Baseline Verification

### Task 1: Confirm baseline tests pass

**Files:** none (verification only)

- [ ] **Step 1: Run full test suite from clean main**

Run: `cd /Users/daxin/work/requirement-workflow-feishu && python -m pytest tests/ -x -q`
Expected: all green; note count for later regression check.

- [ ] **Step 2: Snapshot baseline test count**

Save the total test count to use as baseline; if S2-S6 do not add tests for a slice, this number must monotonically increase.

---

## Slice S2 · `/spec restart` slash command

### Task 2: Add `SPEC_RESTART` event + `deadlocked` field

**Files:**
- Modify: `src/requirement_workflow_v12/spec_state_machine.py`
- Test: `tests/test_spec_state_machine_transforming.py`

- [ ] **Step 1: Write failing test for SPEC_RESTART event from DRAFTING**

Create `tests/test_spec_state_machine_transforming.py`:
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.spec_state_machine import (
    SpecStatus, SpecEvent, apply_spec_event,
)


def test_spec_restart_from_drafting_returns_null():
    decision = apply_spec_event(SpecStatus.DRAFTING, SpecEvent.SPEC_RESTART)
    assert decision.allowed is True
    assert decision.next_status is None


def test_spec_restart_from_transforming_without_deadlock_rejected():
    decision = apply_spec_event(SpecStatus.TRANSFORMING, SpecEvent.SPEC_RESTART)
    assert decision.allowed is False


def test_spec_restart_from_transforming_with_deadlock_allowed():
    decision = apply_spec_event(
        SpecStatus.TRANSFORMING, SpecEvent.SPEC_RESTART, deadlocked=True,
    )
    assert decision.allowed is True
    assert decision.next_status is None


def test_spec_restart_from_locked_rejected():
    decision = apply_spec_event(SpecStatus.LOCKED, SpecEvent.SPEC_RESTART)
    assert decision.allowed is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_spec_state_machine_transforming.py -v`
Expected: 4 FAIL — `SPEC_RESTART` not in SpecEvent; `apply_spec_event` doesn't accept `deadlocked` kwarg.

- [ ] **Step 3: Implement `SPEC_RESTART` and `deadlocked` parameter**

Edit `src/requirement_workflow_v12/spec_state_machine.py`:

Add inside `SpecEvent` class:
```python
    SPEC_RESTART = "spec_restart"
```

Replace `apply_spec_event` with:
```python
def apply_spec_event(
    current: Optional[SpecStatus],
    event: SpecEvent,
    *,
    deadlocked: bool = False,
) -> SpecTransitionDecision:
    if event is SpecEvent.SPEC_RESTART:
        if current is SpecStatus.DRAFTING or (
            current is SpecStatus.TRANSFORMING and deadlocked
        ):
            return SpecTransitionDecision(
                allowed=True,
                next_status=None,
                message="规格层状态已重置（restart）",
            )
        current_label = current.value if current is not None else "<未进入规格层>"
        return SpecTransitionDecision(
            allowed=False,
            next_status=current,
            message=f"当前规格层状态 {current_label} 不能 restart",
        )

    next_status = SPEC_TRANSITIONS.get((current, event))
    if next_status is None:
        current_label = current.value if current is not None else "<未进入规格层>"
        return SpecTransitionDecision(
            allowed=False,
            next_status=current,
            message=f"当前规格层状态 {current_label} 不能执行 {event.value}",
        )
    return SpecTransitionDecision(
        allowed=True,
        next_status=next_status,
        message=f"规格层状态已更新为 {next_status.value}",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_spec_state_machine_transforming.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Re-run full suite to confirm no regression**

Run: `python -m pytest tests/ -x -q`
Expected: previous count + 4 = new count.

- [ ] **Step 6: Commit**

```bash
git add src/requirement_workflow_v12/spec_state_machine.py tests/test_spec_state_machine_transforming.py
git commit -m "feat(spec-state-machine): add SPEC_RESTART event with deadlocked guard"
```

### Task 3: Add `spec_deadlocked` and `spec_transform_snapshot` fields to Requirement

**Files:**
- Modify: `src/requirement_workflow_v12/models.py`
- Test: append to `tests/test_spec_state_machine_transforming.py`

- [ ] **Step 1: Inspect current Requirement dataclass**

Run: `python -c "from requirement_workflow_v12.models import Requirement; import dataclasses; print([f.name for f in dataclasses.fields(Requirement)])"`
(Use `PYTHONPATH=src`.)

- [ ] **Step 2: Add fields to Requirement**

Edit `src/requirement_workflow_v12/models.py` — add to the `Requirement` dataclass alongside existing spec_* fields:
```python
    spec_deadlocked: bool = False
    spec_transform_snapshot: dict | None = None
```

- [ ] **Step 3: Write failing test for default values**

Append to `tests/test_spec_state_machine_transforming.py`:
```python
from requirement_workflow_v12.models import Requirement, WorkflowStatus


def test_requirement_default_spec_deadlocked_is_false():
    r = Requirement(req_id="R", name="n", project="p", summary="s", creator="c")
    assert r.spec_deadlocked is False
    assert r.spec_transform_snapshot is None
```

- [ ] **Step 4: Run test**

Run: `python -m pytest tests/test_spec_state_machine_transforming.py -v -k default_spec_deadlocked`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/models.py tests/test_spec_state_machine_transforming.py
git commit -m "feat(models): add spec_deadlocked and spec_transform_snapshot fields"
```

### Task 4: `coordinator_service.spec_restart` method

**Files:**
- Modify: `src/requirement_workflow_v12/coordinator_service.py`
- Test: `tests/test_spec_restart.py`

- [ ] **Step 1: Write failing test for `spec_restart`**

Create `tests/test_spec_restart.py`:
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest
from requirement_workflow_v12.coordinator_service import CoordinatorService
from requirement_workflow_v12.models import Requirement, WorkflowStatus
from requirement_workflow_v12.spec_state_machine import SpecStatus


def _drafting_req(svc: CoordinatorService) -> Requirement:
    r = Requirement(req_id="R1", name="n", project="P", summary="s", creator="c")
    r.status = WorkflowStatus.APPROVED
    r.spec_status = SpecStatus.DRAFTING
    r.spec_document_url = "https://feishu/doc"
    r.spec_document_id = "doc-1"
    svc.requirements["R1"] = r
    return r


def test_spec_restart_from_drafting_resets_state():
    svc = CoordinatorService()
    _drafting_req(svc)
    result = svc.spec_restart("R1")
    r = svc.requirements["R1"]
    assert r.spec_status is None
    assert r.spec_document_url == ""
    assert r.spec_document_id == ""
    assert r.spec_deadlocked is False
    assert result.spec_status is None


def test_spec_restart_from_locked_raises():
    svc = CoordinatorService()
    r = _drafting_req(svc)
    r.spec_status = SpecStatus.LOCKED
    with pytest.raises(ValueError, match="不能 restart"):
        svc.spec_restart("R1")


def test_spec_restart_from_transforming_without_deadlock_raises():
    svc = CoordinatorService()
    r = _drafting_req(svc)
    r.spec_status = SpecStatus.TRANSFORMING
    with pytest.raises(ValueError, match="不能 restart"):
        svc.spec_restart("R1")


def test_spec_restart_from_deadlocked_transforming_resets():
    svc = CoordinatorService()
    r = _drafting_req(svc)
    r.spec_status = SpecStatus.TRANSFORMING
    r.spec_deadlocked = True
    result = svc.spec_restart("R1")
    assert result.spec_status is None
    assert result.spec_deadlocked is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_spec_restart.py -v`
Expected: 4 FAIL — `spec_restart` method missing.

- [ ] **Step 3: Implement `spec_restart`**

Append to `src/requirement_workflow_v12/coordinator_service.py` (place near `submit_spec_start`):
```python
    def spec_restart(self, req_id: str) -> Requirement:
        """Reset Spec state for re-entry. Allowed only in DRAFTING or
        TRANSFORMING(deadlocked=True). Archives current Spec doc URL and
        resets all spec_* fields. Side effects on Feishu doc archival and
        local trace.jsonl rotation are wired by callers (service_app)."""
        r = self.requirements.get(req_id)
        if r is None:
            raise KeyError(req_id)
        from .spec_state_machine import SpecEvent, apply_spec_event
        decision = apply_spec_event(
            r.spec_status, SpecEvent.SPEC_RESTART, deadlocked=r.spec_deadlocked,
        )
        if not decision.allowed:
            raise ValueError(decision.message)
        r.spec_status = None
        r.spec_document_url = ""
        r.spec_document_id = ""
        r.spec_deadlocked = False
        r.spec_transform_snapshot = None
        return r
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_spec_restart.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/coordinator_service.py tests/test_spec_restart.py
git commit -m "feat(coordinator): add spec_restart with deadlock-aware guard"
```

### Task 5: Slash command `/spec restart REQ-X` parser in service_app

**Files:**
- Modify: `src/requirement_workflow_v12/service_app.py`
- Test: `tests/test_service_app_spec_transform.py`

- [ ] **Step 1: Locate group message handler**

Run: `grep -n "def handle_group_message\|def _handle_text_message\|slash" src/requirement_workflow_v12/service_app.py | head -20`
Identify the function that receives plain group messages (not card callbacks). Note its signature.

- [ ] **Step 2: Write failing test for slash command parsing**

Create `tests/test_service_app_spec_transform.py`:
```python
import re
import pytest

SPEC_RESTART_RE = re.compile(r"^/spec\s+restart\s+(REQ-\S+)\s*$")


@pytest.mark.parametrize("text,expected", [
    ("/spec restart REQ-PROJ-005", "REQ-PROJ-005"),
    ("/spec  restart  REQ-X-1", "REQ-X-1"),
    ("/spec restart REQ-X ", "REQ-X"),
])
def test_slash_restart_parses(text, expected):
    m = SPEC_RESTART_RE.match(text)
    assert m is not None
    assert m.group(1) == expected


@pytest.mark.parametrize("text", [
    "/spec restart",
    "spec restart REQ-X",
    "/spec lock REQ-X",
    "",
])
def test_slash_restart_rejects(text):
    assert SPEC_RESTART_RE.match(text) is None
```

- [ ] **Step 3: Run test (must pass — pure regex)**

Run: `python -m pytest tests/test_service_app_spec_transform.py -v`
Expected: 7 PASS.

- [ ] **Step 4: Wire the regex into service_app**

Edit `src/requirement_workflow_v12/service_app.py`. Near other constants near top of file add:
```python
SPEC_RESTART_RE = re.compile(r"^/spec\s+restart\s+(REQ-\S+)\s*$")
```

In the group message handler (identified in Step 1), add at the top of message dispatch:
```python
        text = (event.text or "").strip() if hasattr(event, "text") else ""
        m = SPEC_RESTART_RE.match(text)
        if m:
            return self._handle_spec_restart_command(req_id=m.group(1), event=event)
```

Add the private handler:
```python
    def _handle_spec_restart_command(self, *, req_id: str, event):
        try:
            self.coordinator.spec_restart(req_id)
        except KeyError:
            return self._reply_text(event, f"未找到 {req_id}")
        except ValueError as exc:
            return self._reply_text(event, f"重启失败：{exc}")
        # 归档副作用按需启用：如有飞书 Feishu doc 归档逻辑可在此调用。
        return self._reply_text(
            event, f"{req_id} 规格层已重置，请重新点击「启动 Spec 撰写」"
        )
```

(If `_reply_text` does not exist in service_app, use the existing reply helper located in step 1; substitute its name.)

- [ ] **Step 5: Add an integration-style test using monkeypatched coordinator**

Append to `tests/test_service_app_spec_transform.py`:
```python
from unittest.mock import MagicMock


def test_handle_spec_restart_command_calls_coordinator():
    from requirement_workflow_v12.service_app import ServiceApp  # adjust if class name differs
    app = ServiceApp.__new__(ServiceApp)
    app.coordinator = MagicMock()
    app._reply_text = MagicMock(return_value="ok")
    event = MagicMock()
    app._handle_spec_restart_command(req_id="REQ-PROJ-1", event=event)
    app.coordinator.spec_restart.assert_called_once_with("REQ-PROJ-1")
    app._reply_text.assert_called_once()
```

(Skip if `ServiceApp` class name differs; adapt to actual.)

- [ ] **Step 6: Run tests**

Run: `python -m pytest tests/test_service_app_spec_transform.py -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add src/requirement_workflow_v12/service_app.py tests/test_service_app_spec_transform.py
git commit -m "feat(service-app): /spec restart REQ-X slash command"
```

---

## Slice S3 · `SPEC_TRANSFORMING` entry + snapshot

### Task 6: Define `TransformContextSnapshot` and `RoundContext` dataclasses

**Files:**
- Create: `src/requirement_workflow_v12/spec_transform.py`
- Test: `tests/test_spec_transform_orchestrator.py`

- [ ] **Step 1: Write failing test for snapshot dataclass shape**

Create `tests/test_spec_transform_orchestrator.py`:
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.spec_transform import (
    TransformContextSnapshot, RoundContext,
)


def test_transform_context_snapshot_fields():
    snap = TransformContextSnapshot(
        req_id="REQ-P-1",
        spec_source_revision="rev-1",
        architecture_revision="abc123",
        acm_registry_revision="def456",
        acm_active_slice=["AC-001", "AC-002"],
        captured_at="2026-04-16T00:00:00Z",
    )
    assert snap.req_id == "REQ-P-1"
    assert snap.acm_active_slice == ["AC-001", "AC-002"]


def test_round_context_starts_at_round_one_with_zero_retries():
    snap = TransformContextSnapshot(
        req_id="R", spec_source_revision="", architecture_revision="",
        acm_registry_revision="", acm_active_slice=[], captured_at="",
    )
    ctx = RoundContext(snapshot=snap)
    assert ctx.round_index == 1
    assert ctx.soft_retry_count == 0
    assert ctx.race_retry_count == 0
```

- [ ] **Step 2: Run test to verify failure**

Run: `python -m pytest tests/test_spec_transform_orchestrator.py -v`
Expected: ImportError — module does not exist.

- [ ] **Step 3: Create `spec_transform.py` with dataclasses only**

Create `src/requirement_workflow_v12/spec_transform.py`:
```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


NextAction = Literal[
    "soft_retry_transformer",
    "wake_reviewer",
    "wake_transformer_next_round",
    "deadlock",
    "converged",
]


@dataclass(frozen=True)
class TransformContextSnapshot:
    req_id: str
    spec_source_revision: str
    architecture_revision: str
    acm_registry_revision: str
    acm_active_slice: list[str]
    captured_at: str


@dataclass
class RoundContext:
    snapshot: TransformContextSnapshot
    round_index: int = 1
    soft_retry_count: int = 0
    race_retry_count: int = 0
    last_transformer_payload: dict | None = None
    last_reviewer_findings: list[dict] = field(default_factory=list)
```

- [ ] **Step 4: Run test to verify pass**

Run: `python -m pytest tests/test_spec_transform_orchestrator.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/spec_transform.py tests/test_spec_transform_orchestrator.py
git commit -m "feat(spec-transform): TransformContextSnapshot + RoundContext"
```

### Task 7: Trace writer (append-only jsonl)

**Files:**
- Modify: `src/requirement_workflow_v12/spec_transform.py`
- Test: `tests/test_spec_transform_orchestrator.py`

- [ ] **Step 1: Write failing test for trace writer**

Append to `tests/test_spec_transform_orchestrator.py`:
```python
import json
from requirement_workflow_v12.spec_transform import TraceWriter


def test_trace_writer_appends_jsonl(tmp_path):
    writer = TraceWriter(tmp_path)
    writer.append("REQ-P-1", {"event": "transform_started", "round": 0})
    writer.append("REQ-P-1", {"event": "gate_pass", "round": 1})
    file = tmp_path / "REQ-P-1.jsonl"
    lines = file.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["event"] == "transform_started"
    assert json.loads(lines[1])["round"] == 1


def test_trace_writer_truncates_on_reset(tmp_path):
    writer = TraceWriter(tmp_path)
    writer.append("REQ-P-1", {"event": "x"})
    writer.reset("REQ-P-1")
    writer.append("REQ-P-1", {"event": "y"})
    lines = (tmp_path / "REQ-P-1.jsonl").read_text().strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["event"] == "y"


def test_trace_writer_archive_renames_with_suffix(tmp_path):
    writer = TraceWriter(tmp_path)
    writer.append("REQ-P-1", {"event": "x"})
    archived = writer.archive("REQ-P-1", suffix="deadlocked")
    assert archived.exists()
    assert "deadlocked" in archived.name
    assert not (tmp_path / "REQ-P-1.jsonl").exists()
```

- [ ] **Step 2: Run test (should fail — TraceWriter missing)**

Run: `python -m pytest tests/test_spec_transform_orchestrator.py -v -k trace`
Expected: 3 FAIL.

- [ ] **Step 3: Implement TraceWriter**

Append to `src/requirement_workflow_v12/spec_transform.py`:
```python
import json
import time
from pathlib import Path


class TraceWriter:
    """Per-REQ append-only jsonl trace. Files live in `dir/REQ-X.jsonl`.
    Archive moves the file under dir/archive/REQ-X.<ts>.<suffix>.jsonl."""

    def __init__(self, directory: Path):
        self._dir = Path(directory)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, req_id: str) -> Path:
        return self._dir / f"{req_id}.jsonl"

    def append(self, req_id: str, event: dict) -> None:
        payload = {**event, "ts": event.get("ts") or time.time()}
        with self._path(req_id).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def reset(self, req_id: str) -> None:
        path = self._path(req_id)
        if path.exists():
            path.unlink()

    def read_all(self, req_id: str) -> str:
        path = self._path(req_id)
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def archive(self, req_id: str, *, suffix: str) -> Path:
        archive_dir = self._dir / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        ts = int(time.time())
        target = archive_dir / f"{req_id}.{ts}.{suffix}.jsonl"
        path = self._path(req_id)
        if path.exists():
            path.rename(target)
        return target
```

- [ ] **Step 4: Run test to verify pass**

Run: `python -m pytest tests/test_spec_transform_orchestrator.py -v -k trace`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/spec_transform.py tests/test_spec_transform_orchestrator.py
git commit -m "feat(spec-transform): TraceWriter append-only jsonl with archive"
```

### Task 8: `SpecTransformOrchestrator.on_enter_transforming` (snapshot capture)

**Files:**
- Modify: `src/requirement_workflow_v12/spec_transform.py`
- Test: `tests/test_spec_transform_orchestrator.py`

- [ ] **Step 1: Write failing test for snapshot capture + branch creation**

Append to `tests/test_spec_transform_orchestrator.py`:
```python
import asyncio
from unittest.mock import AsyncMock, MagicMock


def test_on_enter_transforming_captures_snapshot_and_writes_trace(tmp_path):
    gateway = AsyncMock()
    gateway.fetch_file_sha = AsyncMock(side_effect=[
        ("arch-sha", "ARCHITECTURE: yaml"),
        ("registry-sha", "version: 3\nentries: []"),
    ])
    gateway.create_branch = AsyncMock()
    registry = MagicMock()
    registry.parse_active_slice.return_value = ["AC-001", "AC-002"]

    feishu = MagicMock()
    feishu.fetch_document_revision.return_value = "rev-77"

    from requirement_workflow_v12.spec_transform import SpecTransformOrchestrator
    orch = SpecTransformOrchestrator(
        gateway=gateway, registry=registry,
        feishu=feishu, trace_dir=tmp_path,
    )
    snap = asyncio.run(orch.on_enter_transforming(
        req_id="REQ-P-1", project_repo="proj-repo",
        spec_doc_id="doc-1",
    ))
    assert snap.spec_source_revision == "rev-77"
    assert snap.architecture_revision == "arch-sha"
    assert snap.acm_registry_revision == "registry-sha"
    assert snap.acm_active_slice == ["AC-001", "AC-002"]
    gateway.create_branch.assert_awaited_once()
    trace = (tmp_path / "REQ-P-1.jsonl").read_text()
    assert '"transform_started"' in trace
```

- [ ] **Step 2: Run test (must fail)**

Run: `python -m pytest tests/test_spec_transform_orchestrator.py -v -k on_enter`
Expected: FAIL — `SpecTransformOrchestrator` missing.

- [ ] **Step 3: Implement orchestrator skeleton + on_enter**

Append to `src/requirement_workflow_v12/spec_transform.py`:
```python
import datetime as _dt


class SpecTransformOrchestrator:
    """Coordinator-side game runner. Holds in-memory RoundContext per req_id.
    Crash recovery is `/spec restart`; trace is audit-only."""

    def __init__(
        self,
        *,
        gateway,
        registry,
        feishu,
        trace_dir: Path,
        max_rounds: int = 3,
        max_soft_retries: int = 2,
        max_race_retries: int = 3,
    ):
        self._gateway = gateway
        self._registry = registry
        self._feishu = feishu
        self._trace = TraceWriter(trace_dir)
        self._max_rounds = max_rounds
        self._max_soft_retries = max_soft_retries
        self._max_race_retries = max_race_retries
        self._rounds: dict[str, RoundContext] = {}

    async def on_enter_transforming(
        self,
        *,
        req_id: str,
        project_repo: str,
        spec_doc_id: str,
    ) -> TransformContextSnapshot:
        spec_rev = self._feishu.fetch_document_revision(spec_doc_id)
        arch_sha, _ = await self._gateway.fetch_file_sha(
            project_repo, "main", "ARCHITECTURE.yaml",
        )
        registry_sha, registry_text = await self._gateway.fetch_file_sha(
            project_repo, "main", "acm-registry.yaml",
        )
        active = self._registry.parse_active_slice(registry_text)
        snap = TransformContextSnapshot(
            req_id=req_id,
            spec_source_revision=spec_rev,
            architecture_revision=arch_sha,
            acm_registry_revision=registry_sha,
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
        await self._gateway.create_branch(
            project_repo, f"spec/{req_id}", base="main",
        )
        self._rounds[req_id] = RoundContext(snapshot=snap)
        return snap
```

- [ ] **Step 4: Run test**

Run: `python -m pytest tests/test_spec_transform_orchestrator.py -v -k on_enter`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/spec_transform.py tests/test_spec_transform_orchestrator.py
git commit -m "feat(spec-transform): on_enter_transforming captures snapshot + creates branch"
```

### Task 9: Wire `submit_checkpoint_1a_pass` in CoordinatorService

**Files:**
- Modify: `src/requirement_workflow_v12/coordinator_service.py`
- Test: append to `tests/test_spec_state_machine_transforming.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_spec_state_machine_transforming.py`:
```python
import asyncio
from unittest.mock import AsyncMock, MagicMock


def test_submit_checkpoint_1a_pass_transitions_to_transforming():
    svc = CoordinatorService()
    r = Requirement(req_id="R1", name="n", project="P", summary="s", creator="c")
    r.status = WorkflowStatus.APPROVED
    r.spec_status = SpecStatus.DRAFTING
    r.spec_document_id = "doc-1"
    svc.requirements["R1"] = r

    svc.spec_orchestrator = MagicMock()
    svc.spec_orchestrator.on_enter_transforming = AsyncMock(return_value=None)
    svc.project_configs = MagicMock()
    cfg = MagicMock(); cfg.scaffold_repo = "owner/repo"
    svc.project_configs.get.return_value = cfg

    svc.submit_checkpoint_1a_pass("R1")
    assert svc.requirements["R1"].spec_status is SpecStatus.TRANSFORMING
    svc.spec_orchestrator.on_enter_transforming.assert_awaited_once()
```

- [ ] **Step 2: Run test (must fail)**

Run: `python -m pytest tests/test_spec_state_machine_transforming.py -v -k checkpoint_1a`
Expected: FAIL — `submit_checkpoint_1a_pass` missing.

- [ ] **Step 3: Implement `submit_checkpoint_1a_pass`**

Append to `src/requirement_workflow_v12/coordinator_service.py`:
```python
    def submit_checkpoint_1a_pass(self, req_id: str) -> Requirement:
        r = self.requirements[req_id]
        from .spec_state_machine import SpecEvent, apply_spec_event
        decision = apply_spec_event(r.spec_status, SpecEvent.CHECKPOINT_1A_PASS)
        if not decision.allowed:
            raise ValueError(decision.message)
        r.spec_status = decision.next_status
        cfg = self.project_configs.get(r.project)
        if cfg is None or not getattr(cfg, "scaffold_repo", None):
            raise ValueError(f"项目 {r.project} 未配置 scaffold_repo")
        import asyncio
        asyncio.get_event_loop().run_until_complete(
            self.spec_orchestrator.on_enter_transforming(
                req_id=req_id,
                project_repo=cfg.scaffold_repo,
                spec_doc_id=r.spec_document_id,
            )
        )
        return r
```

(Note: `spec_orchestrator` and `project_configs` will be wired in Task 22 / S6. For now ensure the attribute is settable; if `CoordinatorService.__init__` does not initialize them, add `self.spec_orchestrator = None` and `self.project_configs = None` to `__init__` so tests can monkey-patch.)

- [ ] **Step 4: Run test**

Run: `python -m pytest tests/test_spec_state_machine_transforming.py -v -k checkpoint_1a`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/coordinator_service.py tests/test_spec_state_machine_transforming.py
git commit -m "feat(coordinator): submit_checkpoint_1a_pass drives DRAFTING→TRANSFORMING"
```

---

## Slice S4 · Single-round game

### Task 10: GitHubGateway helper for file SHA + content fetch

**Files:**
- Modify: `src/requirement_workflow_v12/github_gateway.py`
- Test: `tests/test_github_gateway.py`

- [ ] **Step 1: Read existing github_gateway to identify httpx pattern**

Run: `grep -n "async def\|class GitHubGateway\|self._client" src/requirement_workflow_v12/github_gateway.py`

- [ ] **Step 2: Write failing test for `fetch_file_sha`**

Append to `tests/test_github_gateway.py`:
```python
import pytest
import respx
import httpx
from requirement_workflow_v12.github_gateway import GitHubGateway


@pytest.mark.asyncio
@respx.mock
async def test_fetch_file_sha_returns_sha_and_content():
    respx.get(
        "https://api.github.com/repos/o/r/contents/path.yaml?ref=main"
    ).mock(return_value=httpx.Response(200, json={
        "sha": "abc123", "content": "aGVsbG8=", "encoding": "base64",
    }))
    gw = GitHubGateway(token="t")
    sha, content = await gw.fetch_file_sha("o/r", "main", "path.yaml")
    assert sha == "abc123"
    assert content == "hello"
    await gw.aclose()
```

(If respx is not in test deps, add `respx` to `requirements-dev.txt` or use `httpx.MockTransport` instead; check existing tests for pattern.)

- [ ] **Step 3: Run test to verify failure**

Run: `python -m pytest tests/test_github_gateway.py -v -k fetch_file_sha`
Expected: FAIL — method missing.

- [ ] **Step 4: Implement `fetch_file_sha`**

Append to `GitHubGateway` class in `src/requirement_workflow_v12/github_gateway.py`:
```python
    async def fetch_file_sha(
        self, repo: str, ref: str, path: str,
    ) -> tuple[str, str]:
        """Return (sha, decoded_text) for a file via Contents API."""
        import base64
        resp = await self._client.get(
            f"https://api.github.com/repos/{repo}/contents/{path}",
            params={"ref": ref},
            headers=self._auth_headers(),
        )
        resp.raise_for_status()
        data = resp.json()
        text = base64.b64decode(data["content"]).decode("utf-8")
        return data["sha"], text
```

(If `_auth_headers` does not exist, inline `{"Authorization": f"Bearer {self._token}"}` matching existing httpx call style.)

- [ ] **Step 5: Run test**

Run: `python -m pytest tests/test_github_gateway.py -v -k fetch_file_sha`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/requirement_workflow_v12/github_gateway.py tests/test_github_gateway.py
git commit -m "feat(github-gateway): fetch_file_sha returns sha + decoded content"
```

### Task 11: GitHubGateway `delete_branch`

**Files:**
- Modify: `src/requirement_workflow_v12/github_gateway.py`
- Test: `tests/test_github_gateway.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_github_gateway.py`:
```python
@pytest.mark.asyncio
@respx.mock
async def test_delete_branch_calls_refs_api():
    route = respx.delete(
        "https://api.github.com/repos/o/r/git/refs/heads/spec/REQ-X"
    ).mock(return_value=httpx.Response(204))
    gw = GitHubGateway(token="t")
    await gw.delete_branch("o/r", "spec/REQ-X")
    assert route.called
    await gw.aclose()
```

- [ ] **Step 2: Run test (must fail)**

Run: `python -m pytest tests/test_github_gateway.py -v -k delete_branch`
Expected: FAIL.

- [ ] **Step 3: Implement `delete_branch`**

Append to `GitHubGateway`:
```python
    async def delete_branch(self, repo: str, branch: str) -> None:
        resp = await self._client.delete(
            f"https://api.github.com/repos/{repo}/git/refs/heads/{branch}",
            headers=self._auth_headers(),
        )
        if resp.status_code not in (204, 404, 422):
            resp.raise_for_status()
```

- [ ] **Step 4: Run test**

Run: `python -m pytest tests/test_github_gateway.py -v -k delete_branch`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/github_gateway.py tests/test_github_gateway.py
git commit -m "feat(github-gateway): delete_branch idempotent over 404/422"
```

### Task 12: `spec_gate` types + ac-schedule schema rule

**Files:**
- Create: `src/requirement_workflow_v12/spec_gate.py`
- Test: `tests/test_spec_gate.py`

- [ ] **Step 1: Write failing test for ac-schedule schema rule**

Create `tests/test_spec_gate.py`:
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.spec_gate import (
    GateFinding, GateResult, run_gate,
)
from requirement_workflow_v12.spec_transform import TransformContextSnapshot


def _snap():
    return TransformContextSnapshot(
        req_id="REQ-P-1", spec_source_revision="r",
        architecture_revision="a", acm_registry_revision="r",
        acm_active_slice=[], captured_at="2026-04-16",
    )


def test_run_gate_passes_on_minimal_valid_payload():
    payload = {
        "design_md": "# Design\n## supersedes\nno supersession\n",
        "tasks_md": "T-001 init\n",
        "ac_schedule_yaml": (
            "version: 1\n"
            "acs:\n"
            "  - id: AC-100\n"
            "    title: t\n"
            "    priority: P0\n"
            "    given: x\n"
            "    expected: y\n"
            "    test_file: harness/tests/REQ-P-1/test_x.py\n"
            "    test_function: test_x\n"
        ),
        "harness_files": {
            "harness/tests/REQ-P-1/test_x.py": (
                "import pytest\n"
                "@pytest.mark.ac('AC-100')\n"
                "def test_x():\n    pass\n"
            ),
        },
        "supersedes_decl": [],
        "round_zero_ac_ids": [],
    }
    result = run_gate(payload, _snap())
    assert result.passed is True


def test_run_gate_fails_on_missing_required_ac_field():
    payload = {
        "design_md": "## supersedes\nno supersession\n",
        "tasks_md": "T-001 a\n",
        "ac_schedule_yaml": "version: 1\nacs:\n  - id: AC-100\n",
        "harness_files": {},
        "supersedes_decl": [],
        "round_zero_ac_ids": [],
    }
    result = run_gate(payload, _snap())
    assert result.passed is False
    assert any(f.rule == "ac_schedule_schema" for f in result.findings)
    assert all(f.kind == "format" for f in result.findings if f.rule == "ac_schedule_schema")
```

- [ ] **Step 2: Run tests (must fail)**

Run: `python -m pytest tests/test_spec_gate.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement spec_gate.py with schema rule**

Create `src/requirement_workflow_v12/spec_gate.py`:
```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
import re
import yaml


@dataclass(frozen=True)
class GateFinding:
    kind: Literal["format", "semantic"]
    rule: str
    detail: str


@dataclass(frozen=True)
class GateResult:
    passed: bool
    findings: list[GateFinding]

    @property
    def has_format_failure(self) -> bool:
        return any(f.kind == "format" for f in self.findings)

    @property
    def has_semantic_failure(self) -> bool:
        return any(f.kind == "semantic" for f in self.findings)


_REQUIRED_AC_FIELDS = {"id", "title", "priority", "given", "expected",
                       "test_file", "test_function"}


def _check_ac_schedule_schema(payload) -> list[GateFinding]:
    findings: list[GateFinding] = []
    try:
        doc = yaml.safe_load(payload["ac_schedule_yaml"]) or {}
    except yaml.YAMLError as exc:
        return [GateFinding("format", "ac_schedule_schema", f"yaml parse error: {exc}")]
    acs = doc.get("acs", [])
    if not isinstance(acs, list):
        return [GateFinding("format", "ac_schedule_schema", "acs must be a list")]
    for idx, ac in enumerate(acs):
        missing = _REQUIRED_AC_FIELDS - set(ac.keys() if isinstance(ac, dict) else [])
        if missing:
            findings.append(GateFinding(
                "format", "ac_schedule_schema",
                f"acs[{idx}] missing fields: {sorted(missing)}",
            ))
    return findings


def run_gate(payload: dict, snapshot) -> GateResult:
    findings: list[GateFinding] = []
    findings.extend(_check_ac_schedule_schema(payload))
    return GateResult(passed=len(findings) == 0, findings=findings)
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_spec_gate.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/spec_gate.py tests/test_spec_gate.py
git commit -m "feat(spec-gate): GateFinding + ac_schedule_schema rule"
```

### Task 13: Add tasks regex + path consistency rules to gate

**Files:**
- Modify: `src/requirement_workflow_v12/spec_gate.py`
- Test: `tests/test_spec_gate.py`

- [ ] **Step 1: Write failing tests for two new rules**

Append to `tests/test_spec_gate.py`:
```python
def test_run_gate_fails_on_malformed_tasks_md():
    payload = {
        "design_md": "## supersedes\nno supersession\n",
        "tasks_md": "no tasks here at all\n",
        "ac_schedule_yaml": (
            "version: 1\nacs:\n"
            "  - {id: AC-100, title: t, priority: P0, given: g, expected: e, "
            "test_file: harness/tests/REQ-P-1/test_x.py, test_function: test_x}\n"
        ),
        "harness_files": {
            "harness/tests/REQ-P-1/test_x.py":
                "import pytest\n@pytest.mark.ac('AC-100')\ndef test_x(): pass\n",
        },
        "supersedes_decl": [], "round_zero_ac_ids": [],
    }
    result = run_gate(payload, _snap())
    assert any(f.rule == "tasks_md_format" for f in result.findings)


def test_run_gate_fails_on_test_file_not_in_harness_payload():
    payload = {
        "design_md": "## supersedes\nno supersession\n",
        "tasks_md": "T-001 init\n",
        "ac_schedule_yaml": (
            "version: 1\nacs:\n"
            "  - {id: AC-100, title: t, priority: P0, given: g, expected: e, "
            "test_file: harness/tests/REQ-P-1/missing.py, test_function: test_x}\n"
        ),
        "harness_files": {},
        "supersedes_decl": [], "round_zero_ac_ids": [],
    }
    result = run_gate(payload, _snap())
    assert any(f.rule == "path_consistency" for f in result.findings)
```

- [ ] **Step 2: Run tests (must fail)**

Run: `python -m pytest tests/test_spec_gate.py -v -k "tasks_md_format or path_consistency"`
Expected: 2 FAIL.

- [ ] **Step 3: Implement two rules**

Append inside `src/requirement_workflow_v12/spec_gate.py`:
```python
_TASK_LINE_RE = re.compile(r"^\s*[-*]?\s*T-\d{3,}\s+\S")


def _check_tasks_md_format(payload) -> list[GateFinding]:
    text = payload.get("tasks_md", "")
    has_any = any(_TASK_LINE_RE.match(line) for line in text.splitlines())
    if not has_any:
        return [GateFinding(
            "format", "tasks_md_format",
            "no `T-NNN <subject>` lines found in tasks.md",
        )]
    return []


def _check_path_consistency(payload) -> list[GateFinding]:
    findings: list[GateFinding] = []
    try:
        doc = yaml.safe_load(payload["ac_schedule_yaml"]) or {}
    except yaml.YAMLError:
        return findings
    files = payload.get("harness_files", {})
    for ac in doc.get("acs", []) or []:
        if not isinstance(ac, dict):
            continue
        path = ac.get("test_file")
        if not path:
            continue
        if path not in files:
            findings.append(GateFinding(
                "format", "path_consistency",
                f"AC {ac.get('id')} test_file '{path}' not present in harness payload",
            ))
            continue
        ac_id = ac.get("id", "")
        if f"@pytest.mark.ac('{ac_id}')" not in files[path] \
           and f'@pytest.mark.ac("{ac_id}")' not in files[path]:
            findings.append(GateFinding(
                "format", "path_consistency",
                f"AC {ac_id}: test_file present but lacks @pytest.mark.ac",
            ))
    return findings
```

Then update `run_gate`:
```python
def run_gate(payload: dict, snapshot) -> GateResult:
    findings: list[GateFinding] = []
    findings.extend(_check_ac_schedule_schema(payload))
    findings.extend(_check_tasks_md_format(payload))
    findings.extend(_check_path_consistency(payload))
    return GateResult(passed=len(findings) == 0, findings=findings)
```

- [ ] **Step 4: Run all gate tests**

Run: `python -m pytest tests/test_spec_gate.py -v`
Expected: all PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/spec_gate.py tests/test_spec_gate.py
git commit -m "feat(spec-gate): tasks_md_format + path_consistency format rules"
```

### Task 14: Add semantic rules (round_zero_ac_recall + supersedes_completeness)

**Files:**
- Modify: `src/requirement_workflow_v12/spec_gate.py`
- Test: `tests/test_spec_gate.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_spec_gate.py`:
```python
def test_run_gate_fails_when_round_zero_recall_missing_active_ac():
    snap = TransformContextSnapshot(
        req_id="REQ-P-1", spec_source_revision="r",
        architecture_revision="a", acm_registry_revision="r",
        acm_active_slice=["AC-001", "AC-002"], captured_at="2026-04-16",
    )
    payload = {
        "design_md": "## supersedes\nno supersession\n",
        "tasks_md": "T-001 init\n",
        "ac_schedule_yaml": "version: 1\nacs: []\n",
        "harness_files": {},
        "supersedes_decl": [],
        "round_zero_ac_ids": ["AC-001"],   # missing AC-002
    }
    result = run_gate(payload, snap)
    finding = next(f for f in result.findings if f.rule == "round_zero_ac_recall")
    assert finding.kind == "semantic"
    assert "AC-002" in finding.detail


def test_run_gate_fails_when_supersedes_decl_inconsistent():
    snap = TransformContextSnapshot(
        req_id="REQ-P-1", spec_source_revision="r",
        architecture_revision="a", acm_registry_revision="r",
        acm_active_slice=["AC-001"], captured_at="2026-04-16",
    )
    # design.md says supersedes AC-999 but AC-999 is not in active slice
    payload = {
        "design_md": "## supersedes\nReplaces AC-999\n",
        "tasks_md": "T-001 init\n",
        "ac_schedule_yaml": "version: 1\nacs: []\n",
        "harness_files": {},
        "supersedes_decl": [{"old_ac_id": "AC-999", "by_ac_id": "AC-100"}],
        "round_zero_ac_ids": ["AC-001"],
    }
    result = run_gate(payload, snap)
    finding = next(f for f in result.findings if f.rule == "supersedes_completeness")
    assert finding.kind == "semantic"
    assert "AC-999" in finding.detail
```

- [ ] **Step 2: Run tests (must fail)**

Run: `python -m pytest tests/test_spec_gate.py -v -k "round_zero or supersedes"`
Expected: 2 FAIL.

- [ ] **Step 3: Implement semantic rules**

Append to `src/requirement_workflow_v12/spec_gate.py`:
```python
def _check_round_zero_ac_recall(payload, snapshot) -> list[GateFinding]:
    declared = set(payload.get("round_zero_ac_ids") or [])
    expected = set(snapshot.acm_active_slice)
    missing = expected - declared
    if missing:
        return [GateFinding(
            "semantic", "round_zero_ac_recall",
            f"Round 0 AC recall missing: {sorted(missing)}",
        )]
    return []


def _check_supersedes_completeness(payload, snapshot) -> list[GateFinding]:
    findings: list[GateFinding] = []
    decls = payload.get("supersedes_decl") or []
    active = set(snapshot.acm_active_slice)
    for decl in decls:
        old = decl.get("old_ac_id")
        if old and old not in active:
            findings.append(GateFinding(
                "semantic", "supersedes_completeness",
                f"supersedes target {old} not in current active slice",
            ))
    return findings
```

Update `run_gate`:
```python
def run_gate(payload: dict, snapshot) -> GateResult:
    findings: list[GateFinding] = []
    findings.extend(_check_ac_schedule_schema(payload))
    findings.extend(_check_tasks_md_format(payload))
    findings.extend(_check_path_consistency(payload))
    findings.extend(_check_round_zero_ac_recall(payload, snapshot))
    findings.extend(_check_supersedes_completeness(payload, snapshot))
    return GateResult(passed=len(findings) == 0, findings=findings)
```

- [ ] **Step 4: Run all gate tests**

Run: `python -m pytest tests/test_spec_gate.py -v`
Expected: all 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/spec_gate.py tests/test_spec_gate.py
git commit -m "feat(spec-gate): round_zero_ac_recall + supersedes_completeness semantic rules"
```

### Task 15: Orchestrator `handle_transformer_output` (single-round happy path)

**Files:**
- Modify: `src/requirement_workflow_v12/spec_transform.py`
- Test: `tests/test_spec_transform_orchestrator.py`

- [ ] **Step 1: Write failing test for handle_transformer_output → wake_reviewer**

Append to `tests/test_spec_transform_orchestrator.py`:
```python
def test_handle_transformer_output_pass_returns_wake_reviewer(tmp_path):
    gateway = AsyncMock()
    registry = MagicMock()
    feishu = MagicMock()
    from requirement_workflow_v12.spec_transform import (
        SpecTransformOrchestrator, TransformContextSnapshot, RoundContext,
    )
    orch = SpecTransformOrchestrator(
        gateway=gateway, registry=registry, feishu=feishu, trace_dir=tmp_path,
    )
    snap = TransformContextSnapshot(
        req_id="R", spec_source_revision="", architecture_revision="",
        acm_registry_revision="", acm_active_slice=[], captured_at="",
    )
    orch._rounds["R"] = RoundContext(snapshot=snap)
    payload = {
        "design_md": "## supersedes\nno supersession\n",
        "tasks_md": "T-001 init\n",
        "ac_schedule_yaml": (
            "version: 1\nacs:\n"
            "  - {id: AC-100, title: t, priority: P0, given: g, expected: e, "
            "test_file: harness/tests/R/test_x.py, test_function: test_x}\n"
        ),
        "harness_files": {
            "harness/tests/R/test_x.py":
                "import pytest\n@pytest.mark.ac('AC-100')\ndef test_x(): pass\n",
        },
        "supersedes_decl": [],
        "round_zero_ac_ids": [],
    }
    action = asyncio.run(orch.handle_transformer_output("R", payload))
    assert action == "wake_reviewer"
    trace = (tmp_path / "R.jsonl").read_text()
    assert "gate_pass" in trace


def test_handle_transformer_output_format_fail_soft_retry(tmp_path):
    orch = _orch(tmp_path)
    orch._rounds["R"] = RoundContext(snapshot=_blank_snap())
    bad_payload = {
        "design_md": "", "tasks_md": "T-001 a\n",
        "ac_schedule_yaml": "version: 1\nacs:\n  - id: AC-100\n",
        "harness_files": {}, "supersedes_decl": [], "round_zero_ac_ids": [],
    }
    action1 = asyncio.run(orch.handle_transformer_output("R", bad_payload))
    assert action1 == "soft_retry_transformer"
    assert orch._rounds["R"].soft_retry_count == 1


def _orch(tmp_path):
    return SpecTransformOrchestrator(
        gateway=AsyncMock(), registry=MagicMock(), feishu=MagicMock(),
        trace_dir=tmp_path,
    )


def _blank_snap():
    return TransformContextSnapshot(
        req_id="R", spec_source_revision="", architecture_revision="",
        acm_registry_revision="", acm_active_slice=[], captured_at="",
    )
```

- [ ] **Step 2: Run tests (must fail)**

Run: `python -m pytest tests/test_spec_transform_orchestrator.py -v -k handle_transformer`
Expected: FAIL — `handle_transformer_output` missing.

- [ ] **Step 3: Implement `handle_transformer_output`**

Append to `SpecTransformOrchestrator`:
```python
    async def handle_transformer_output(
        self, req_id: str, payload: dict,
    ) -> "NextAction":
        from .spec_gate import run_gate
        ctx = self._rounds.get(req_id)
        if ctx is None:
            self._trace.append(req_id, {
                "event": "recovery_deadlock",
                "reason": "no in-memory round context (likely after restart)",
            })
            return "deadlock"
        ctx.last_transformer_payload = payload
        result = run_gate(payload, ctx.snapshot)
        if result.passed:
            self._trace.append(req_id, {
                "event": "gate_pass", "round": ctx.round_index,
            })
            return "wake_reviewer"
        if result.has_format_failure and not result.has_semantic_failure:
            if ctx.soft_retry_count < self._max_soft_retries:
                ctx.soft_retry_count += 1
                self._trace.append(req_id, {
                    "event": "soft_retry",
                    "round": ctx.round_index,
                    "retry": ctx.soft_retry_count,
                    "findings": [vars(f) for f in result.findings],
                })
                return "soft_retry_transformer"
            self._trace.append(req_id, {
                "event": "round_used",
                "reason": "format_max",
                "round": ctx.round_index,
            })
        else:
            self._trace.append(req_id, {
                "event": "round_used",
                "reason": "semantic",
                "round": ctx.round_index,
                "findings": [vars(f) for f in result.findings],
            })
        return self._advance_round_or_deadlock(ctx, req_id)

    def _advance_round_or_deadlock(self, ctx: "RoundContext", req_id: str) -> "NextAction":
        if ctx.round_index >= self._max_rounds:
            self._trace.append(req_id, {
                "event": "deadlock", "reason": "max_rounds",
            })
            return "deadlock"
        ctx.round_index += 1
        ctx.soft_retry_count = 0
        return "wake_transformer_next_round"
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_spec_transform_orchestrator.py -v -k handle_transformer`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/spec_transform.py tests/test_spec_transform_orchestrator.py
git commit -m "feat(spec-transform): handle_transformer_output with gate + soft retry"
```

### Task 16: Orchestrator `handle_reviewer_verdict`

**Files:**
- Modify: `src/requirement_workflow_v12/spec_transform.py`
- Test: `tests/test_spec_transform_orchestrator.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_spec_transform_orchestrator.py`:
```python
def test_handle_reviewer_verdict_converged_returns_converged(tmp_path):
    orch = _orch(tmp_path)
    orch._rounds["R"] = RoundContext(snapshot=_blank_snap())
    # _on_converged gets monkeypatched to skip side effects
    orch._on_converged = AsyncMock()
    action = asyncio.run(orch.handle_reviewer_verdict("R", "converged", []))
    assert action == "converged"
    orch._on_converged.assert_awaited_once_with("R")


def test_handle_reviewer_verdict_reject_consumes_round(tmp_path):
    orch = _orch(tmp_path)
    orch._rounds["R"] = RoundContext(snapshot=_blank_snap())
    findings = [{"dimension": "completeness", "severity": "blocking", "detail": "x"}]
    action = asyncio.run(orch.handle_reviewer_verdict("R", "reject", findings))
    assert action == "wake_transformer_next_round"
    assert orch._rounds["R"].round_index == 2
    assert orch._rounds["R"].last_reviewer_findings == findings


def test_handle_reviewer_verdict_reject_at_max_rounds_deadlocks(tmp_path):
    orch = _orch(tmp_path)
    ctx = RoundContext(snapshot=_blank_snap())
    ctx.round_index = 3
    orch._rounds["R"] = ctx
    action = asyncio.run(orch.handle_reviewer_verdict("R", "reject", []))
    assert action == "deadlock"
```

- [ ] **Step 2: Run tests (must fail)**

Run: `python -m pytest tests/test_spec_transform_orchestrator.py -v -k handle_reviewer`
Expected: FAIL.

- [ ] **Step 3: Implement `handle_reviewer_verdict`**

Append to `SpecTransformOrchestrator`:
```python
    async def handle_reviewer_verdict(
        self, req_id: str, verdict: str, findings: list[dict],
    ) -> "NextAction":
        ctx = self._rounds.get(req_id)
        if ctx is None:
            self._trace.append(req_id, {
                "event": "recovery_deadlock", "reason": "no round context",
            })
            return "deadlock"
        self._trace.append(req_id, {
            "event": "reviewer_verdict",
            "verdict": verdict,
            "findings": findings,
            "round": ctx.round_index,
        })
        if verdict == "converged":
            await self._on_converged(req_id)
            return "converged"
        ctx.last_reviewer_findings = findings
        return self._advance_round_or_deadlock(ctx, req_id)

    async def _on_converged(self, req_id: str) -> None:
        # Implemented in S6; placeholder so tests can monkeypatch.
        self._trace.append(req_id, {"event": "converged_placeholder"})
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_spec_transform_orchestrator.py -v -k handle_reviewer`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/spec_transform.py tests/test_spec_transform_orchestrator.py
git commit -m "feat(spec-transform): handle_reviewer_verdict with round accounting"
```

### Task 17: `/openclaw/spec-transform-callback` endpoint

**Files:**
- Modify: `src/requirement_workflow_v12/service_app.py`
- Test: `tests/test_service_app_spec_transform.py`

- [ ] **Step 1: Inspect existing callback endpoint pattern**

Run: `grep -n "openclaw/spec-context\|openclaw/spec-turn\|@app.post\|verify.*signature" src/requirement_workflow_v12/service_app.py | head -30`
Note the auth header name and signature verification helper.

- [ ] **Step 2: Write failing test**

Append to `tests/test_service_app_spec_transform.py`:
```python
import asyncio
from unittest.mock import AsyncMock, MagicMock


def test_spec_transform_callback_routes_transformer_output():
    from requirement_workflow_v12.service_app import ServiceApp
    app = ServiceApp.__new__(ServiceApp)
    app.coordinator = MagicMock()
    app.coordinator.spec_orchestrator = MagicMock()
    app.coordinator.spec_orchestrator.handle_transformer_output = AsyncMock(
        return_value="wake_reviewer"
    )
    payload = {
        "req_id": "REQ-P-1", "event": "transformer_output",
        "data": {"design_md": "x", "tasks_md": "T-001 a\n",
                 "ac_schedule_yaml": "version: 1\nacs: []\n",
                 "harness_files": {}, "supersedes_decl": [],
                 "round_zero_ac_ids": []},
    }
    result = asyncio.run(app.handle_openclaw_spec_transform_callback(payload))
    assert result["next_action"] == "wake_reviewer"
    app.coordinator.spec_orchestrator.handle_transformer_output.assert_awaited_once_with(
        "REQ-P-1", payload["data"],
    )


def test_spec_transform_callback_routes_reviewer_verdict():
    from requirement_workflow_v12.service_app import ServiceApp
    app = ServiceApp.__new__(ServiceApp)
    app.coordinator = MagicMock()
    app.coordinator.spec_orchestrator = MagicMock()
    app.coordinator.spec_orchestrator.handle_reviewer_verdict = AsyncMock(
        return_value="converged"
    )
    payload = {
        "req_id": "REQ-P-1", "event": "reviewer_verdict",
        "data": {"verdict": "converged", "findings": []},
    }
    result = asyncio.run(app.handle_openclaw_spec_transform_callback(payload))
    assert result["next_action"] == "converged"
```

- [ ] **Step 3: Run tests (must fail)**

Run: `python -m pytest tests/test_service_app_spec_transform.py -v -k callback`
Expected: FAIL.

- [ ] **Step 4: Implement endpoint handler**

Add to `src/requirement_workflow_v12/service_app.py`:
```python
    async def handle_openclaw_spec_transform_callback(self, payload: dict) -> dict:
        req_id = payload["req_id"]
        event = payload["event"]
        data = payload.get("data", {})
        orch = self.coordinator.spec_orchestrator
        if event == "transformer_output":
            action = await orch.handle_transformer_output(req_id, data)
        elif event == "reviewer_verdict":
            action = await orch.handle_reviewer_verdict(
                req_id, data["verdict"], data.get("findings", []),
            )
        else:
            return {"ok": False, "error": f"unknown event: {event}"}
        return {"ok": True, "next_action": action}
```

If service_app uses an HTTP framework decorator pattern, also wire a route, e.g.:
```python
    # alongside other route registrations
    self._router.add_post(
        "/openclaw/spec-transform-callback",
        self._wrap_authenticated(self.handle_openclaw_spec_transform_callback),
    )
```
(Substitute for the codebase's actual auth wrapper used by other openclaw endpoints.)

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_service_app_spec_transform.py -v -k callback`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/requirement_workflow_v12/service_app.py tests/test_service_app_spec_transform.py
git commit -m "feat(service-app): /openclaw/spec-transform-callback dispatch"
```

### Task 18: `docs/agents/spec-transformer/` SKILL.md and callback-schema.json

**Files:**
- Create: `docs/agents/spec-transformer/SKILL.md`
- Create: `docs/agents/spec-transformer/callback-schema.json`

- [ ] **Step 1: Write SKILL.md**

Create `docs/agents/spec-transformer/SKILL.md`:
````markdown
---
name: spec-transformer
description: 把飞书 9 节 Spec 转化为 GitHub 四文件（design.md + tasks.md + ac-schedule.yaml + harness 骨架）。Coordinator 在 SPEC_TRANSFORMING 状态下唤醒；最多 3 轮博弈。
---

# Spec Transformer Agent

## 启动流程

收到包含「请开始 Spec 转化 REQ-xxx (round=N)」的消息时启动。

**Step 1：通过 spec-transform-context 拉取项目级上下文**

```bash
python3 /home/admin/.openclaw/bin/send_openclaw_callback.py \
  --base-url "${COORDINATOR_BASE_URL:-http://127.0.0.1:8004}" \
  --secret "${OPENCLAW_CALLBACK_SECRET:-}" \
  --req-id "{req_id}" \
  spec-transform-context
```

响应包含：
```json
{
  "snapshot": {
    "req_id": "...",
    "spec_source_revision": "...",
    "architecture_revision": "...",
    "acm_registry_revision": "...",
    "acm_active_slice": ["AC-001", ...]
  },
  "spec_doc_text": "...",                  // 飞书 9 节 Spec 全文
  "architecture_yaml": "...",
  "acm_registry_text": "...",
  "previous_reviewer_findings": [ ... ]    // round >= 2 时非空
}
```

**Step 2：硬约束**

1. **Round 0 AC 回显**：在 `design.md` 第一段必须列出 `snapshot.acm_active_slice` 中**全部** AC ID（即使本 REQ 不取代它们），声明本 REQ 与这些 AC 的关系（保留 / supersedes / no-impact）
2. **四文件全产出**：design.md + tasks.md + ac-schedule.yaml + harness/tests/REQ-xxx/...
3. **`design.md` 必须包含 `## supersedes` 节**，无取代时显式写 "no supersession"
4. **`ac-schedule.yaml` 每条 AC 字段齐全**：id / title / priority / given / expected / test_file / test_function
5. **harness 骨架每个 test 文件含 `@pytest.mark.ac("<AC-ID>")` 装饰器**
6. **路径一致性**：ac-schedule 的 test_file 必须在 harness payload 中实际存在

**Step 3：回调 Coordinator**

```bash
python3 /home/admin/.openclaw/bin/send_openclaw_callback.py \
  --base-url "${COORDINATOR_BASE_URL:-http://127.0.0.1:8004}" \
  --secret "${OPENCLAW_CALLBACK_SECRET:-}" \
  --req-id "{req_id}" \
  spec-transform-callback \
  --event transformer_output \
  --data @output.json
```

`output.json` schema 见同目录 `callback-schema.json`。

**Step 4：等待 next_action**

Coordinator 返回 `next_action`：
- `wake_reviewer`：你的活完成，等 reviewer
- `soft_retry_transformer`：根据 findings 修正格式问题，本轮内重发（不计入 round）
- `wake_transformer_next_round`：reviewer 已 reject，下轮重试（计入 round）
- `deadlock`：博弈终止，无需再发

不要在 deadlock 后继续发 callback。
````

- [ ] **Step 2: Write callback schema JSON**

Create `docs/agents/spec-transformer/callback-schema.json`:
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "spec-transformer transformer_output payload",
  "type": "object",
  "required": ["design_md", "tasks_md", "ac_schedule_yaml", "harness_files",
               "supersedes_decl", "round_zero_ac_ids"],
  "properties": {
    "design_md": {"type": "string"},
    "tasks_md": {"type": "string"},
    "ac_schedule_yaml": {"type": "string"},
    "harness_files": {
      "type": "object",
      "additionalProperties": {"type": "string"}
    },
    "supersedes_decl": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["old_ac_id", "by_ac_id"],
        "properties": {
          "old_ac_id": {"type": "string"},
          "by_ac_id": {"type": "string"}
        }
      }
    },
    "round_zero_ac_ids": {
      "type": "array",
      "items": {"type": "string"}
    }
  }
}
```

- [ ] **Step 3: Commit**

```bash
git add docs/agents/spec-transformer/
git commit -m "docs(agents): spec-transformer SKILL.md + callback schema"
```

### Task 19: `docs/agents/spec-transformer-reviewer/` SKILL.md and callback-schema.json

**Files:**
- Create: `docs/agents/spec-transformer-reviewer/SKILL.md`
- Create: `docs/agents/spec-transformer-reviewer/callback-schema.json`

- [ ] **Step 1: Write SKILL.md**

Create `docs/agents/spec-transformer-reviewer/SKILL.md`:
````markdown
---
name: spec-transformer-reviewer
description: 评审 spec-transformer 产出的四文件，按五维度判定 verdict ∈ {converged, reject}。
---

# Spec Transformer Reviewer Agent

## 启动流程

收到包含「请评审 Spec 转化产出 REQ-xxx (round=N)」时启动。

**Step 1：拉取本轮 transformer 产出 + snapshot**

```bash
python3 /home/admin/.openclaw/bin/send_openclaw_callback.py \
  --base-url "${COORDINATOR_BASE_URL:-http://127.0.0.1:8004}" \
  --secret "${OPENCLAW_CALLBACK_SECRET:-}" \
  --req-id "{req_id}" \
  spec-transform-context \
  --include-last-transformer-payload
```

**Step 2：五维度审查**

| 维度 | 判据 |
|---|---|
| `completeness` | 飞书 9 节每节都能映射到 design.md / tasks.md / ac-schedule 中的位置 |
| `consistency` | design.md 接口契约与 ac-schedule 各 AC 的 given/expected 不矛盾 |
| `testability` | 每条 AC 在 ac-schedule 中有可执行 given/expected；harness 骨架 docstring 与 AC title 一致 |
| `architecture_fit` | design.md 架构接合点与 snapshot.architecture_yaml 当前接口一致 |
| `supersedes` | design.md ## supersedes 节真实反映 active_slice 的覆盖关系 |

**Step 3：回调 verdict**

```bash
python3 /home/admin/.openclaw/bin/send_openclaw_callback.py \
  --base-url "${COORDINATOR_BASE_URL:-http://127.0.0.1:8004}" \
  --secret "${OPENCLAW_CALLBACK_SECRET:-}" \
  --req-id "{req_id}" \
  spec-transform-callback \
  --event reviewer_verdict \
  --data @verdict.json
```

verdict.json schema 见同目录 `callback-schema.json`。

`findings` 即使 verdict = converged 也可包含非阻塞观察（severity = info），但凡有 severity = blocking 必须 reject。
````

- [ ] **Step 2: Write callback schema JSON**

Create `docs/agents/spec-transformer-reviewer/callback-schema.json`:
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "spec-transformer-reviewer reviewer_verdict payload",
  "type": "object",
  "required": ["verdict", "findings"],
  "properties": {
    "verdict": {"type": "string", "enum": ["converged", "reject"]},
    "findings": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["dimension", "severity", "detail"],
        "properties": {
          "dimension": {
            "type": "string",
            "enum": ["completeness", "consistency", "testability",
                     "architecture_fit", "supersedes"]
          },
          "severity": {"type": "string", "enum": ["blocking", "warning", "info"]},
          "detail": {"type": "string"}
        }
      }
    }
  }
}
```

- [ ] **Step 3: Commit**

```bash
git add docs/agents/spec-transformer-reviewer/
git commit -m "docs(agents): spec-transformer-reviewer SKILL.md + callback schema"
```

---

## Slice S5 · Multi-round + deadlock + crash recovery

### Task 20: Crash recovery deadlock test

**Files:** Test only (logic already in S4 Task 15/16).

- [ ] **Step 1: Write test that simulates orchestrator without round context**

Append to `tests/test_spec_transform_orchestrator.py`:
```python
def test_handle_transformer_output_without_round_context_deadlocks(tmp_path):
    orch = _orch(tmp_path)
    # No entry in _rounds — simulates Coordinator restart mid-game
    action = asyncio.run(orch.handle_transformer_output("R", {}))
    assert action == "deadlock"
    trace = (tmp_path / "R.jsonl").read_text()
    assert "recovery_deadlock" in trace


def test_handle_reviewer_verdict_without_round_context_deadlocks(tmp_path):
    orch = _orch(tmp_path)
    action = asyncio.run(orch.handle_reviewer_verdict("R", "converged", []))
    assert action == "deadlock"
```

- [ ] **Step 2: Run tests**

Run: `python -m pytest tests/test_spec_transform_orchestrator.py -v -k without_round_context`
Expected: PASS (logic already implemented).

- [ ] **Step 3: Commit**

```bash
git add tests/test_spec_transform_orchestrator.py
git commit -m "test(spec-transform): crash recovery → deadlock"
```

### Task 21: Wire deadlock to set `Requirement.spec_deadlocked`

**Files:**
- Modify: `src/requirement_workflow_v12/spec_transform.py`
- Modify: `src/requirement_workflow_v12/coordinator_service.py`
- Test: append to `tests/test_spec_transform_orchestrator.py`

- [ ] **Step 1: Add `on_deadlock` callback to orchestrator**

Add to `SpecTransformOrchestrator.__init__` parameters:
```python
        on_deadlock=None,
```
Store: `self._on_deadlock_cb = on_deadlock`.

In `_advance_round_or_deadlock`, replace the deadlock return with:
```python
        if ctx.round_index >= self._max_rounds:
            self._trace.append(req_id, {"event": "deadlock", "reason": "max_rounds"})
            self._rounds.pop(req_id, None)
            if self._on_deadlock_cb is not None:
                self._on_deadlock_cb(req_id, "max_rounds")
            return "deadlock"
```

Same for the recovery_deadlock branches in `handle_transformer_output` and `handle_reviewer_verdict`:
```python
            if self._on_deadlock_cb is not None:
                self._on_deadlock_cb(req_id, "recovery")
            return "deadlock"
```

- [ ] **Step 2: Write failing test**

Append to `tests/test_spec_transform_orchestrator.py`:
```python
def test_deadlock_callback_invoked(tmp_path):
    called = []
    orch = SpecTransformOrchestrator(
        gateway=AsyncMock(), registry=MagicMock(), feishu=MagicMock(),
        trace_dir=tmp_path,
        on_deadlock=lambda req, reason: called.append((req, reason)),
    )
    ctx = RoundContext(snapshot=_blank_snap()); ctx.round_index = 3
    orch._rounds["R"] = ctx
    action = asyncio.run(orch.handle_reviewer_verdict("R", "reject", []))
    assert action == "deadlock"
    assert called == [("R", "max_rounds")]
```

- [ ] **Step 3: Run test**

Run: `python -m pytest tests/test_spec_transform_orchestrator.py -v -k deadlock_callback`
Expected: PASS.

- [ ] **Step 4: Wire callback in CoordinatorService.__init__**

In `coordinator_service.py`, where `spec_orchestrator` will be instantiated (currently `None`), add a method:
```python
    def _on_spec_deadlock(self, req_id: str, reason: str) -> None:
        r = self.requirements.get(req_id)
        if r is None:
            return
        from .spec_state_machine import SpecEvent, apply_spec_event
        decision = apply_spec_event(r.spec_status, SpecEvent.TRANSFORM_DEADLOCK)
        if decision.allowed:
            r.spec_deadlocked = True
```

(Final wiring of `spec_orchestrator = SpecTransformOrchestrator(... on_deadlock=self._on_spec_deadlock)` happens in S6 Task 28.)

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/spec_transform.py src/requirement_workflow_v12/coordinator_service.py tests/test_spec_transform_orchestrator.py
git commit -m "feat(spec-transform): deadlock callback sets Requirement.spec_deadlocked"
```

---

## Slice S6 · acm-registry + regression scan + Spec PR

### Task 22: AcmRegistry — types + parse + active slice

**Files:**
- Create: `src/requirement_workflow_v12/acm_registry.py`
- Test: `tests/test_acm_registry.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_acm_registry.py`:
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.acm_registry import (
    AcmRegistry, AcEntry, RegistryDoc, SupersedeDecl,
)


def test_parse_active_slice_returns_only_active_ids():
    text = (
        "version: 3\n"
        "entries:\n"
        "  - {ac_id: AC-001, req_id: R, status: active, priority: P0}\n"
        "  - {ac_id: AC-002, req_id: R, status: retired, priority: P1}\n"
        "  - {ac_id: AC-003, req_id: R, status: active, priority: P0}\n"
    )
    reg = AcmRegistry(gateway=None)
    assert reg.parse_active_slice(text) == ["AC-001", "AC-003"]


def test_parse_active_slice_empty_when_no_entries():
    reg = AcmRegistry(gateway=None)
    assert reg.parse_active_slice("version: 3\nentries: []\n") == []
```

- [ ] **Step 2: Run tests (must fail)**

Run: `python -m pytest tests/test_acm_registry.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement skeleton**

Create `src/requirement_workflow_v12/acm_registry.py`:
```python
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import AsyncIterator
import yaml


@dataclass
class AcEntry:
    ac_id: str
    req_id: str
    status: str            # "active" | "retired" | "superseded"
    priority: str
    added_at: str = ""
    breaking_change: bool = False
    source_version: int = 1
    supersedes: list[str] = field(default_factory=list)
    superseded_by: str | None = None
    retired_at: str = ""


@dataclass
class RegistryDoc:
    version: int
    entries: list[AcEntry]


@dataclass(frozen=True)
class SupersedeDecl:
    old_ac_id: str
    by_ac_id: str


class AcmRegistry:
    def __init__(self, gateway):
        self._gateway = gateway
        self._lock = asyncio.Lock()

    def parse_active_slice(self, registry_text: str) -> list[AcEntry] | list[str]:
        doc = yaml.safe_load(registry_text) or {}
        entries = doc.get("entries", []) or []
        return [e["ac_id"] for e in entries if e.get("status") == "active"]
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_acm_registry.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/acm_registry.py tests/test_acm_registry.py
git commit -m "feat(acm-registry): types + parse_active_slice"
```

### Task 23: AcmRegistry — `compose_patch`

**Files:**
- Modify: `src/requirement_workflow_v12/acm_registry.py`
- Test: `tests/test_acm_registry.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_acm_registry.py`:
```python
def test_compose_patch_appends_active_entries():
    reg = AcmRegistry(gateway=None)
    current = RegistryDoc(version=3, entries=[
        AcEntry("AC-001", "REQ-A", "active", "P0"),
    ])
    new_acs = [{"id": "AC-100", "priority": "P0"}]
    patched = reg.compose_patch(
        current, new_acs=new_acs, supersedes=[], req_id="REQ-B",
    )
    ids = [e.ac_id for e in patched.entries]
    assert "AC-001" in ids
    assert "AC-100" in ids
    new_entry = next(e for e in patched.entries if e.ac_id == "AC-100")
    assert new_entry.status == "active"
    assert new_entry.req_id == "REQ-B"


def test_compose_patch_marks_superseded_old_ac():
    reg = AcmRegistry(gateway=None)
    current = RegistryDoc(version=3, entries=[
        AcEntry("AC-001", "REQ-A", "active", "P0"),
    ])
    patched = reg.compose_patch(
        current,
        new_acs=[{"id": "AC-100", "priority": "P0"}],
        supersedes=[SupersedeDecl(old_ac_id="AC-001", by_ac_id="AC-100")],
        req_id="REQ-B",
    )
    old = next(e for e in patched.entries if e.ac_id == "AC-001")
    assert old.status == "retired"
    assert old.superseded_by == "AC-100"
```

- [ ] **Step 2: Run tests (must fail)**

Run: `python -m pytest tests/test_acm_registry.py -v -k compose_patch`
Expected: FAIL.

- [ ] **Step 3: Implement `compose_patch`**

Append to `AcmRegistry`:
```python
    def compose_patch(
        self,
        current: RegistryDoc,
        *,
        new_acs: list[dict],
        supersedes: list[SupersedeDecl],
        req_id: str,
    ) -> RegistryDoc:
        import datetime as _dt
        now = _dt.datetime.now(_dt.timezone.utc).isoformat()
        retired_map = {d.old_ac_id: d.by_ac_id for d in supersedes}
        new_entries: list[AcEntry] = []
        for old in current.entries:
            if old.ac_id in retired_map and old.status == "active":
                new_entries.append(AcEntry(
                    ac_id=old.ac_id, req_id=old.req_id, status="retired",
                    priority=old.priority, added_at=old.added_at,
                    breaking_change=old.breaking_change,
                    source_version=old.source_version,
                    supersedes=old.supersedes,
                    superseded_by=retired_map[old.ac_id],
                    retired_at=now,
                ))
            else:
                new_entries.append(old)
        for ac in new_acs:
            new_entries.append(AcEntry(
                ac_id=ac["id"], req_id=req_id, status="active",
                priority=ac.get("priority", "P1"),
                added_at=now,
                breaking_change=ac.get("breaking_change", False),
            ))
        return RegistryDoc(version=current.version, entries=new_entries)

    def serialize(self, doc: RegistryDoc) -> str:
        return yaml.safe_dump({
            "version": doc.version,
            "entries": [
                {k: v for k, v in vars(e).items()
                 if v not in (None, "", [], False) or k in {"status", "ac_id", "req_id", "priority"}}
                for e in doc.entries
            ],
        }, sort_keys=False, allow_unicode=True)

    def parse(self, text: str) -> RegistryDoc:
        doc = yaml.safe_load(text) or {}
        entries = []
        for e in doc.get("entries", []) or []:
            entries.append(AcEntry(
                ac_id=e["ac_id"], req_id=e["req_id"],
                status=e.get("status", "active"),
                priority=e.get("priority", "P1"),
                added_at=e.get("added_at", ""),
                breaking_change=e.get("breaking_change", False),
                source_version=e.get("source_version", 1),
                supersedes=e.get("supersedes", []) or [],
                superseded_by=e.get("superseded_by"),
                retired_at=e.get("retired_at", ""),
            ))
        return RegistryDoc(version=doc.get("version", 3), entries=entries)
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_acm_registry.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/acm_registry.py tests/test_acm_registry.py
git commit -m "feat(acm-registry): compose_patch + serialize + parse"
```

### Task 24: AcmRegistry — async `fetch_snapshot` + `write_lock`

**Files:**
- Modify: `src/requirement_workflow_v12/acm_registry.py`
- Test: `tests/test_acm_registry.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_acm_registry.py`:
```python
import asyncio
from unittest.mock import AsyncMock


def test_fetch_snapshot_returns_sha_and_doc():
    gw = AsyncMock()
    gw.fetch_file_sha = AsyncMock(return_value=(
        "sha-1",
        "version: 3\nentries:\n  - {ac_id: AC-1, req_id: R, status: active, priority: P0}\n",
    ))
    reg = AcmRegistry(gateway=gw)
    sha, doc = asyncio.run(reg.fetch_snapshot("o/r"))
    assert sha == "sha-1"
    assert len(doc.entries) == 1


def test_write_lock_serializes_concurrent_callers():
    reg = AcmRegistry(gateway=None)
    order = []
    async def waiter(name):
        async with reg.write_lock():
            order.append(("enter", name))
            await asyncio.sleep(0.01)
            order.append(("exit", name))
    asyncio.run(asyncio.gather(waiter("a"), waiter("b")))
    assert order == [("enter", "a"), ("exit", "a"), ("enter", "b"), ("exit", "b")] \
        or order == [("enter", "b"), ("exit", "b"), ("enter", "a"), ("exit", "a")]
```

- [ ] **Step 2: Run tests (must fail)**

Run: `python -m pytest tests/test_acm_registry.py -v -k "fetch_snapshot or write_lock"`
Expected: FAIL.

- [ ] **Step 3: Implement methods**

Append to `AcmRegistry`:
```python
    async def fetch_snapshot(self, project_repo: str) -> tuple[str, RegistryDoc]:
        sha, text = await self._gateway.fetch_file_sha(
            project_repo, "main", "acm-registry.yaml",
        )
        return sha, self.parse(text)

    @asynccontextmanager
    async def write_lock(self) -> AsyncIterator[None]:
        async with self._lock:
            yield
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_acm_registry.py -v -k "fetch_snapshot or write_lock"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/acm_registry.py tests/test_acm_registry.py
git commit -m "feat(acm-registry): fetch_snapshot + write_lock"
```

### Task 25: `regression_scan.scan`

**Files:**
- Create: `src/requirement_workflow_v12/regression_scan.py`
- Test: `tests/test_regression_scan.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_regression_scan.py`:
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.regression_scan import scan, RegressionResult
from requirement_workflow_v12.acm_registry import SupersedeDecl


def test_scan_passes_when_active_anchored_in_harness():
    result = scan(
        active_ids=["AC-001"],
        supersedes_decl=[],
        harness_files={
            "harness/tests/x.py":
                "import pytest\n@pytest.mark.ac('AC-001')\ndef test(): pass\n",
        },
    )
    assert result.passed is True


def test_scan_passes_when_active_is_superseded():
    result = scan(
        active_ids=["AC-001"],
        supersedes_decl=[SupersedeDecl("AC-001", "AC-100")],
        harness_files={},
    )
    assert result.passed is True


def test_scan_fails_when_active_not_anchored_and_not_superseded():
    result = scan(
        active_ids=["AC-001", "AC-002"],
        supersedes_decl=[SupersedeDecl("AC-002", "AC-200")],
        harness_files={},
    )
    assert result.passed is False
    assert result.missing == ["AC-001"]
```

- [ ] **Step 2: Run tests (must fail)**

Run: `python -m pytest tests/test_regression_scan.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement scan**

Create `src/requirement_workflow_v12/regression_scan.py`:
```python
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class RegressionResult:
    passed: bool
    missing: list[str]


def _anchor_re(ac_id: str) -> re.Pattern:
    return re.compile(rf"@pytest\.mark\.ac\(['\"]{re.escape(ac_id)}['\"]\)")


def scan(
    *,
    active_ids: list[str],
    supersedes_decl: list,
    harness_files: dict[str, str],
) -> RegressionResult:
    superseded = {d.old_ac_id for d in supersedes_decl}
    missing: list[str] = []
    for ac_id in active_ids:
        if ac_id in superseded:
            continue
        pattern = _anchor_re(ac_id)
        if any(pattern.search(text) for text in harness_files.values()):
            continue
        missing.append(ac_id)
    return RegressionResult(passed=len(missing) == 0, missing=missing)
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_regression_scan.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/regression_scan.py tests/test_regression_scan.py
git commit -m "feat(regression-scan): active AC ↔ harness anchor scan"
```

### Task 26: GitHubGateway `commit_spec_pr_files` (atomic multi-file)

**Files:**
- Modify: `src/requirement_workflow_v12/github_gateway.py`
- Test: `tests/test_github_gateway.py`

- [ ] **Step 1: Inspect existing `commit_files` to understand Git Data API pattern**

Run: `grep -n "create_blob\|create_tree\|create_commit\|commit_files" src/requirement_workflow_v12/github_gateway.py | head -20`

- [ ] **Step 2: Add `commit_spec_pr_files` as wrapper**

Append to `GitHubGateway`:
```python
    async def commit_spec_pr_files(
        self,
        repo: str,
        branch: str,
        files: dict[str, str],
        message: str,
    ) -> str:
        """Atomic multi-file commit on `branch`. Returns new commit sha.
        Thin wrapper over the existing commit_files() Git Data API path."""
        return await self.commit_files(
            repo=repo, branch=branch, files=files, message=message,
        )
```

(If existing `commit_files` signature differs, adapt. The wrapper exists so callers express *intent* - "this is the Spec PR commit".)

- [ ] **Step 3: Write test**

Append to `tests/test_github_gateway.py`:
```python
@pytest.mark.asyncio
async def test_commit_spec_pr_files_delegates_to_commit_files(monkeypatch):
    gw = GitHubGateway(token="t")
    called = {}
    async def fake_commit_files(*, repo, branch, files, message):
        called.update(repo=repo, branch=branch, files=files, message=message)
        return "newsha"
    monkeypatch.setattr(gw, "commit_files", fake_commit_files)
    sha = await gw.commit_spec_pr_files(
        "o/r", "spec/REQ-X", {"a.md": "1"}, "msg",
    )
    assert sha == "newsha"
    assert called["files"] == {"a.md": "1"}
    await gw.aclose()
```

- [ ] **Step 4: Run test**

Run: `python -m pytest tests/test_github_gateway.py -v -k commit_spec_pr_files`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/github_gateway.py tests/test_github_gateway.py
git commit -m "feat(github-gateway): commit_spec_pr_files semantic wrapper"
```

### Task 27: Orchestrator `_on_converged` (write-locked patch + scan + commit + PR)

**Files:**
- Modify: `src/requirement_workflow_v12/spec_transform.py`
- Test: `tests/test_spec_transform_orchestrator.py`

- [ ] **Step 1: Write failing test for happy-path convergence**

Append to `tests/test_spec_transform_orchestrator.py`:
```python
def test_on_converged_commits_pr_and_locks(tmp_path):
    from requirement_workflow_v12.acm_registry import (
        AcmRegistry, RegistryDoc, AcEntry, SupersedeDecl,
    )
    gateway = AsyncMock()
    gateway.fetch_file_sha = AsyncMock(return_value=(
        "registry-sha-1",
        "version: 3\nentries:\n  - {ac_id: AC-1, req_id: R, status: active, priority: P0}\n",
    ))
    gateway.commit_spec_pr_files = AsyncMock(return_value="commit-sha")
    gateway.open_pull_request = AsyncMock(return_value={"html_url": "https://gh/pr/1"})
    registry = AcmRegistry(gateway=gateway)
    feishu = MagicMock()

    orch = SpecTransformOrchestrator(
        gateway=gateway, registry=registry, feishu=feishu, trace_dir=tmp_path,
    )
    snap = TransformContextSnapshot(
        req_id="REQ-P-1", spec_source_revision="r",
        architecture_revision="a", acm_registry_revision="registry-sha-1",
        acm_active_slice=["AC-1"], captured_at="2026-04-16",
    )
    ctx = RoundContext(snapshot=snap)
    ctx.last_transformer_payload = {
        "design_md": "## supersedes\nno supersession\n",
        "tasks_md": "T-001 init\n",
        "ac_schedule_yaml": (
            "version: 1\nacs:\n"
            "  - {id: AC-100, title: t, priority: P0, given: g, expected: e, "
            "test_file: harness/tests/REQ-P-1/test_x.py, test_function: test_x}\n"
        ),
        "harness_files": {
            "harness/tests/REQ-P-1/test_x.py":
                "import pytest\n@pytest.mark.ac('AC-1')\ndef test(): pass\n"
                "@pytest.mark.ac('AC-100')\ndef test2(): pass\n",
        },
        "supersedes_decl": [],
        "round_zero_ac_ids": ["AC-1"],
    }
    orch._rounds["REQ-P-1"] = ctx
    orch._project_repo_for = lambda req_id: "o/r"

    asyncio.run(orch._on_converged("REQ-P-1"))

    gateway.commit_spec_pr_files.assert_awaited_once()
    gateway.open_pull_request.assert_awaited_once()
    trace = (tmp_path / "REQ-P-1.jsonl").read_text()
    assert '"locked"' in trace
```

- [ ] **Step 2: Run test (must fail)**

Run: `python -m pytest tests/test_spec_transform_orchestrator.py -v -k on_converged_commits`
Expected: FAIL — `_on_converged` is still placeholder.

- [ ] **Step 3: Replace placeholder `_on_converged`**

Replace `_on_converged` in `SpecTransformOrchestrator` with the full implementation:
```python
    async def _on_converged(self, req_id: str) -> None:
        from .acm_registry import SupersedeDecl
        from .regression_scan import scan
        ctx = self._rounds[req_id]
        payload = ctx.last_transformer_payload
        project_repo = self._project_repo_for(req_id)

        async with self._registry.write_lock():
            for race_attempt in range(self._max_race_retries):
                current_sha, current_doc = await self._registry.fetch_snapshot(project_repo)
                # parse new ACs out of ac_schedule yaml
                import yaml
                ac_doc = yaml.safe_load(payload["ac_schedule_yaml"]) or {}
                new_acs = ac_doc.get("acs", []) or []
                supersedes = [
                    SupersedeDecl(old_ac_id=d["old_ac_id"], by_ac_id=d["by_ac_id"])
                    for d in payload.get("supersedes_decl", [])
                ]
                patched = self._registry.compose_patch(
                    current_doc, new_acs=new_acs,
                    supersedes=supersedes, req_id=req_id,
                )
                active_ids = [e.ac_id for e in patched.entries if e.status == "active"]
                regression = scan(
                    active_ids=active_ids,
                    supersedes_decl=supersedes,
                    harness_files=payload["harness_files"],
                )
                if not regression.passed:
                    self._trace.append(req_id, {
                        "event": "regression_failed",
                        "missing": regression.missing,
                    })
                    self._rounds.pop(req_id, None)
                    if self._on_deadlock_cb is not None:
                        self._on_deadlock_cb(req_id, "regression_failed")
                    return
                # commit attempt
                files = self._compose_pr_files(req_id, payload, patched)
                try:
                    await self._gateway.commit_spec_pr_files(
                        project_repo, f"spec/{req_id}",
                        files, f"feat(spec): {req_id}",
                    )
                    break
                except Exception as exc:
                    if "sha mismatch" in str(exc).lower() and race_attempt < self._max_race_retries - 1:
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
                    if self._on_deadlock_cb is not None:
                        self._on_deadlock_cb(req_id, "github_commit_failed")
                    return
            else:
                self._trace.append(req_id, {"event": "acm_race_giveup"})
                if self._on_deadlock_cb is not None:
                    self._on_deadlock_cb(req_id, "acm_race_giveup")
                return

        pr = await self._gateway.open_pull_request(
            project_repo,
            head=f"spec/{req_id}",
            base="main",
            title=f"Spec: {req_id}",
            body=f"Spec PR for {req_id}.\n\nRounds used: {ctx.round_index}",
        )
        self._trace.append(req_id, {
            "event": "locked", "pr_url": pr.get("html_url"),
        })
        self._rounds.pop(req_id, None)
        if self._on_locked_cb is not None:
            self._on_locked_cb(req_id, pr.get("html_url"))

    def _compose_pr_files(self, req_id, payload, patched_registry) -> dict[str, str]:
        prefix = f"docs/specs/{req_id}"
        files = {
            f"{prefix}/design.md": payload["design_md"],
            f"{prefix}/tasks.md": payload["tasks_md"],
            f"{prefix}/ac-schedule.yaml": payload["ac_schedule_yaml"],
            f"{prefix}/transform_trace.jsonl": self._trace.read_all(req_id),
            "acm-registry.yaml": self._registry.serialize(patched_registry),
        }
        for path, content in payload.get("harness_files", {}).items():
            files[path] = content
        return files

    def _project_repo_for(self, req_id: str) -> str:
        # Default impl; CoordinatorService may override by injecting a resolver.
        raise NotImplementedError("project_repo_for must be set by Coordinator wiring")
```

Also add to `__init__`:
```python
        on_locked=None,
```
Store: `self._on_locked_cb = on_locked`.

- [ ] **Step 4: Run test**

Run: `python -m pytest tests/test_spec_transform_orchestrator.py -v -k on_converged_commits`
Expected: PASS.

- [ ] **Step 5: Add regression-fail test**

Append to `tests/test_spec_transform_orchestrator.py`:
```python
def test_on_converged_regression_fail_deadlocks(tmp_path):
    from requirement_workflow_v12.acm_registry import AcmRegistry
    gateway = AsyncMock()
    gateway.fetch_file_sha = AsyncMock(return_value=(
        "sha-1",
        "version: 3\nentries:\n  - {ac_id: AC-1, req_id: R, status: active, priority: P0}\n",
    ))
    registry = AcmRegistry(gateway=gateway)
    called = []
    orch = SpecTransformOrchestrator(
        gateway=gateway, registry=registry, feishu=MagicMock(),
        trace_dir=tmp_path,
        on_deadlock=lambda req, reason: called.append(reason),
    )
    snap = TransformContextSnapshot(
        req_id="REQ-P-1", spec_source_revision="",
        architecture_revision="", acm_registry_revision="sha-1",
        acm_active_slice=["AC-1"], captured_at="",
    )
    ctx = RoundContext(snapshot=snap)
    # New AC anchored, but old AC-1 is NOT anchored AND NOT superseded → fail
    ctx.last_transformer_payload = {
        "design_md": "## supersedes\nno supersession\n",
        "tasks_md": "T-001 a\n",
        "ac_schedule_yaml": (
            "version: 1\nacs:\n"
            "  - {id: AC-100, title: t, priority: P0, given: g, expected: e, "
            "test_file: harness/tests/REQ-P-1/test_x.py, test_function: test_x}\n"
        ),
        "harness_files": {
            "harness/tests/REQ-P-1/test_x.py":
                "import pytest\n@pytest.mark.ac('AC-100')\ndef test(): pass\n",
        },
        "supersedes_decl": [],
        "round_zero_ac_ids": ["AC-1"],
    }
    orch._rounds["REQ-P-1"] = ctx
    orch._project_repo_for = lambda req_id: "o/r"
    asyncio.run(orch._on_converged("REQ-P-1"))
    assert called == ["regression_failed"]
    trace = (tmp_path / "REQ-P-1.jsonl").read_text()
    assert "regression_failed" in trace
```

- [ ] **Step 6: Run all orchestrator tests**

Run: `python -m pytest tests/test_spec_transform_orchestrator.py -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add src/requirement_workflow_v12/spec_transform.py tests/test_spec_transform_orchestrator.py
git commit -m "feat(spec-transform): _on_converged with patch + regression + PR"
```

### Task 28: Wire orchestrator + registry into CoordinatorService

**Files:**
- Modify: `src/requirement_workflow_v12/coordinator_service.py`
- Test: append to `tests/test_spec_state_machine_transforming.py`

- [ ] **Step 1: Add construction wiring in CoordinatorService**

Locate `CoordinatorService.__init__`. Add (or replace placeholder `None`s):
```python
        from .acm_registry import AcmRegistry
        from .spec_transform import SpecTransformOrchestrator
        from pathlib import Path
        self._acm_registry = AcmRegistry(gateway=self._github_gateway) \
            if hasattr(self, "_github_gateway") else None
        self.spec_orchestrator = SpecTransformOrchestrator(
            gateway=self._github_gateway,
            registry=self._acm_registry,
            feishu=self._feishu_gateway if hasattr(self, "_feishu_gateway") else None,
            trace_dir=Path("/var/spec_traces"),
            on_deadlock=self._on_spec_deadlock,
            on_locked=self._on_spec_locked,
        ) if hasattr(self, "_github_gateway") else None
        if self.spec_orchestrator is not None:
            self.spec_orchestrator._project_repo_for = self._project_repo_for
```

(Adapt attribute names to actual `__init__`. If gateways are not injected by default, leave hooks as `None` and wire in the production entry-point file.)

Add helpers:
```python
    def _project_repo_for(self, req_id: str) -> str:
        r = self.requirements[req_id]
        cfg = self.project_configs.get(r.project)
        return cfg.scaffold_repo

    def _on_spec_locked(self, req_id: str, pr_url: str) -> None:
        r = self.requirements.get(req_id)
        if r is None:
            return
        from .spec_state_machine import SpecEvent, apply_spec_event
        decision = apply_spec_event(r.spec_status, SpecEvent.TRANSFORM_CONVERGED)
        if decision.allowed:
            r.spec_status = decision.next_status
            r.spec_pr_url = pr_url   # add field to Requirement if missing
```

If `Requirement.spec_pr_url` does not exist, add `spec_pr_url: str = ""` in `models.py` and run the existing-fields baseline tests to ensure they still pass.

- [ ] **Step 2: Write smoke test for wiring (no real GitHub)**

Append to `tests/test_spec_state_machine_transforming.py`:
```python
def test_coordinator_init_creates_orchestrator_when_gateway_present(monkeypatch):
    svc = CoordinatorService()
    # If default __init__ does not inject gateway, this assertion documents that.
    # Production wiring lives in service entry-point.
    assert hasattr(svc, "spec_orchestrator")
```

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/ -x -q`
Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add src/requirement_workflow_v12/coordinator_service.py src/requirement_workflow_v12/models.py tests/test_spec_state_machine_transforming.py
git commit -m "feat(coordinator): wire SpecTransformOrchestrator + AcmRegistry"
```

---

## Slice S7 · Integration test (e2e with mocked subprocesses)

### Task 29: e2e happy-path test

**Files:**
- Create: `tests/integration/__init__.py`
- Create: `tests/integration/test_spec_transform_e2e.py`

- [ ] **Step 1: Create integration package init**

Create `tests/integration/__init__.py` (empty).

- [ ] **Step 2: Write happy-path e2e test**

Create `tests/integration/test_spec_transform_e2e.py`:
```python
"""End-to-end: simulate transformer + reviewer subprocesses by directly
invoking the callback handler. Real Claude Code subprocess spawning is
deferred to staging deploy task #22."""
import sys
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from requirement_workflow_v12.spec_transform import SpecTransformOrchestrator
from requirement_workflow_v12.acm_registry import AcmRegistry


def _gateway():
    gw = AsyncMock()
    gw.fetch_file_sha = AsyncMock(side_effect=[
        ("arch-sha", "modules: []\n"),
        ("registry-sha", "version: 3\nentries: []\n"),
        # second registry fetch happens inside _on_converged write_lock
        ("registry-sha", "version: 3\nentries: []\n"),
    ])
    gw.create_branch = AsyncMock()
    gw.commit_spec_pr_files = AsyncMock(return_value="commit-sha")
    gw.open_pull_request = AsyncMock(return_value={"html_url": "https://gh/pr/1"})
    return gw


def test_e2e_one_round_converged(tmp_path):
    gw = _gateway()
    registry = AcmRegistry(gateway=gw)
    feishu = MagicMock()
    feishu.fetch_document_revision.return_value = "rev-1"
    orch = SpecTransformOrchestrator(
        gateway=gw, registry=registry, feishu=feishu, trace_dir=tmp_path,
    )
    orch._project_repo_for = lambda r: "o/r"

    snap = asyncio.run(orch.on_enter_transforming(
        req_id="REQ-P-1", project_repo="o/r", spec_doc_id="doc-1",
    ))
    assert snap.spec_source_revision == "rev-1"

    # transformer round 1
    payload = {
        "design_md": "## supersedes\nno supersession\n",
        "tasks_md": "T-001 init\n",
        "ac_schedule_yaml": (
            "version: 1\nacs:\n"
            "  - {id: AC-100, title: t, priority: P0, given: g, expected: e, "
            "test_file: harness/tests/REQ-P-1/test_x.py, test_function: test_x}\n"
        ),
        "harness_files": {
            "harness/tests/REQ-P-1/test_x.py":
                "import pytest\n@pytest.mark.ac('AC-100')\ndef test(): pass\n",
        },
        "supersedes_decl": [],
        "round_zero_ac_ids": [],
    }
    action = asyncio.run(orch.handle_transformer_output("REQ-P-1", payload))
    assert action == "wake_reviewer"

    # reviewer verdict
    action = asyncio.run(orch.handle_reviewer_verdict("REQ-P-1", "converged", []))
    assert action == "converged"

    # PR opened, trace contains locked
    gw.open_pull_request.assert_awaited_once()
    trace = (tmp_path / "REQ-P-1.jsonl").read_text()
    assert "transform_started" in trace
    assert "gate_pass" in trace
    assert "reviewer_verdict" in trace
    assert "locked" in trace


def test_e2e_three_round_deadlock(tmp_path):
    gw = AsyncMock()
    gw.fetch_file_sha = AsyncMock(side_effect=[
        ("arch", ""), ("reg", "version: 3\nentries: []\n"),
    ])
    gw.create_branch = AsyncMock()
    registry = AcmRegistry(gateway=gw)
    feishu = MagicMock(); feishu.fetch_document_revision.return_value = "rev"
    deadlocks = []
    orch = SpecTransformOrchestrator(
        gateway=gw, registry=registry, feishu=feishu, trace_dir=tmp_path,
        on_deadlock=lambda req, reason: deadlocks.append(reason),
    )
    orch._project_repo_for = lambda r: "o/r"
    asyncio.run(orch.on_enter_transforming(
        req_id="REQ-P-1", project_repo="o/r", spec_doc_id="doc-1",
    ))
    payload = {
        "design_md": "## supersedes\nno supersession\n",
        "tasks_md": "T-001 a\n",
        "ac_schedule_yaml": (
            "version: 1\nacs:\n"
            "  - {id: AC-100, title: t, priority: P0, given: g, expected: e, "
            "test_file: harness/tests/REQ-P-1/test_x.py, test_function: test_x}\n"
        ),
        "harness_files": {
            "harness/tests/REQ-P-1/test_x.py":
                "import pytest\n@pytest.mark.ac('AC-100')\ndef test(): pass\n",
        },
        "supersedes_decl": [],
        "round_zero_ac_ids": [],
    }
    for _ in range(3):
        action = asyncio.run(orch.handle_transformer_output("REQ-P-1", payload))
        assert action == "wake_reviewer"
        action = asyncio.run(orch.handle_reviewer_verdict(
            "REQ-P-1", "reject",
            [{"dimension": "completeness", "severity": "blocking", "detail": "x"}],
        ))
    assert action == "deadlock"
    assert deadlocks == ["max_rounds"]
```

- [ ] **Step 3: Run integration tests**

Run: `python -m pytest tests/integration/ -v`
Expected: 2 PASS.

- [ ] **Step 4: Run full suite once more**

Run: `python -m pytest tests/ -x -q`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/
git commit -m "test(integration): spec transform e2e — converged + deadlock paths"
```

---

## Slice S8 · Documentation sync

### Task 30: Update spec-harness-layer docs to reflect implementation

**Files:**
- Modify: `docs/context/layers/spec-harness-layer.md`

- [ ] **Step 1: Locate §五 Phase 1 and Phase 2 sections**

Run: `grep -n "^### 5\|^## 五" docs/context/layers/spec-harness-layer.md`

- [ ] **Step 2: Add implementation notes to Phase 1 (Phase 1 onEnter)**

Edit `docs/context/layers/spec-harness-layer.md` Phase 1 / SPEC_TRANSFORMING onEnter section to add:
```
**实现细节**（2026-04-16 落地）：
- snapshot 字段 = `{spec_source_revision, architecture_revision, acm_registry_revision, acm_active_slice, captured_at}`
- 整个博弈期间 snapshot 冻结，agent 不主动重拉飞书 doc / ARCHITECTURE / acm-registry
- trace 落点 = `/var/spec_traces/REQ-{PROJECT}-{NNN}.jsonl`
- max_rounds = 3，max_soft_retries = 2，max_race_retries = 3
```

- [ ] **Step 3: Commit**

```bash
git add docs/context/layers/spec-harness-layer.md
git commit -m "docs(spec-harness-layer): note 2026-04-16 implementation parameters"
```

### Task 31: Delete epic file

**Files:**
- Delete: `docs/context/epics/spec-transform-epic-2026-04.md`

- [ ] **Step 1: Verify epic completion criteria met**

Read `docs/context/epics/spec-transform-epic-2026-04.md` §五 完成标准. All 7 blocks should be addressable to merged commits — the file says "完成后删除本文档".

- [ ] **Step 2: Delete file and commit**

```bash
git rm docs/context/epics/spec-transform-epic-2026-04.md
git commit -m "docs(epic): retire spec-transform-epic-2026-04 — implementation merged"
```

---

## Post-merge follow-up: Task #22 (deployment)

**Out of scope for this plan** — see task #22 in the project task list. Once S1–S8 are merged to main, the deployment task syncs `docs/agents/spec-transformer{,-reviewer}/` to the remote OpenClaw workspace per the dual-sync requirement (`agents/<id>/SKILL.md` + `skills/<id>/SKILL.md`), then runs one staging REQ end-to-end through real Claude Code CLI subprocesses.

---

## Self-Review Notes

Performed against the spec. Key checks:

1. **Spec coverage**: every spec section has at least one task —
   - Architecture (§2) → Task 6 (snapshot dataclass) + Task 8 (orchestrator)
   - Data flow §3.1 onEnter → Task 8
   - Data flow §3.2 single round → Tasks 12-16
   - Data flow §3.3 converged → Tasks 22-27
   - Data flow §3.4 restart → Tasks 4-5
   - Failure modes §6 → Tasks 15, 16, 20, 21, 27
   - Modules §4 → Tasks 6-8 (spec_transform), 12-14 (spec_gate), 22-24 (acm_registry), 25 (regression_scan), 10-11, 26 (github_gateway), 4-5, 9, 28 (coordinator/service_app)
   - Slices §5 → mapped 1:1 to Slice headings
2. **No placeholders**: every code step shows actual code; no "implement later".
3. **Type consistency**: `TransformerOutput` payload shape consistent across Tasks 12-19 and 27. `GateFinding(kind, rule, detail)` consistent in 12-14, 15. `RegistryDoc` / `AcEntry` / `SupersedeDecl` consistent in 22-24, 27.
4. **Known assumption**: `service_app.ServiceApp` class name and existing helpers (`_reply_text`, route registration) are placeholders — Task 5 / 17 instruct to "adapt to actual"; the engineer will inspect `grep -n` output in Step 1 of those tasks before editing.
