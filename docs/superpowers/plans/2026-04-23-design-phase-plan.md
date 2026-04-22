# Design Phase Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the Design phase end-to-end per `docs/superpowers/specs/2026-04-23-design-phase-design.md`: extend `DesignStatus` to a 3-state machine, add `design-brief-author` skill contract, handle zip bundle intake, archive handoff artifacts to `design/archive/`, and gate on a D-DESIGN-2 final-approval card before unlocking Plan precondition.

**Architecture:** Mirror the existing Plan layer's pattern (state-machine-in-pure-function + hooks + coordinator methods + HTTP endpoints + Feishu cards). Introduce three new modules (`design_context.py`, `design_intake.py`, `design_syncer.py`) analogous to `plan_context.py` / `feishu_to_github_syncer.py`. Every REQ produces one self-contained archive under `design/archive/REQ-XXX_<slug>/` containing `BRIEF.md`, `MANIFEST.md`, `bundle.zip`, and `extracted/`. No diff, no drift log, no anchor dedup (v1 simplifications per spec §1.2).

**Tech Stack:** Python 3.11, `pytest` + `unittest.mock.MagicMock`, existing `CoordinatorRuntimeApp` in `src/requirement_workflow_v12/service_app.py`, existing `FeishuGateway` / `GithubGateway`. State machines are pure functions — all I/O happens in hooks.

**Reference:** Design spec at `docs/superpowers/specs/2026-04-23-design-phase-design.md`. Bootstrap-layer dependencies listed in that spec's Appendix A are **out of scope** — handle gracefully when `ProjectConfig.claude_design_project_url` is empty (skill still gets context, just with `""` for that field).

---

## Pre-flight

Before starting:

- [ ] Run `python3 -m unittest discover -s tests -v 2>&1 | tail -5` — record green baseline (expect `OK` at tail).
- [ ] Read `docs/superpowers/specs/2026-04-23-design-phase-design.md` cover-to-cover.
- [ ] Read `src/requirement_workflow_v12/plan_state_machine.py` to understand existing `DesignStatus` + `DesignEvent` (we extend, not rewrite).
- [ ] Read `src/requirement_workflow_v12/coordinator_service.py:807-993` (the PLANNING layer methods are the pattern to mirror).
- [ ] Inspect the three real handoff zips at `/tmp/cd_v0/`, `/tmp/cd_v1/`, `/tmp/cd_v2/` (extracted previously during brainstorming). These are fixtures for Task 5 intake tests.

---

## File Structure

**New files** (create in this plan):
- `src/requirement_workflow_v12/design_context.py` — `DesignContextBuilder`, mirrors `plan_context.py`
- `src/requirement_workflow_v12/design_intake.py` — zip extraction + MANIFEST generation
- `src/requirement_workflow_v12/design_syncer.py` — GitHub atomic commit on READY
- `tests/test_design_state_machine.py`
- `tests/test_design_context.py`
- `tests/test_design_intake.py`
- `tests/test_design_syncer.py`
- `tests/test_coordinator_design.py`
- `tests/test_design_endpoint_service_app.py`
- `tests/test_design_phase_e2e.py`
- `tests/fixtures/design/` — copy of one real zip for deterministic intake tests

**Modified files:**
- `src/requirement_workflow_v12/plan_state_machine.py` — extend `DesignStatus` (add `SUBMIT_PENDING_REVIEW`), extend `DesignEvent` (add `DESIGN_FINAL_APPROVE`, `DESIGN_FINAL_REJECT`), update `_DESIGN_TRANSITIONS`
- `src/requirement_workflow_v12/models.py` — add 7 new fields to `Requirement`
- `src/requirement_workflow_v12/store.py` — serialize/deserialize the new fields
- `src/requirement_workflow_v12/coordinator_service.py` — add `design_start` / `design_submit` / `design_final_approve` / `design_final_reject` methods + hook wiring
- `src/requirement_workflow_v12/service_app.py` — 2 HTTP endpoints + 3 card handlers + design start card renderer + D-DESIGN-2 card renderer
- `src/requirement_workflow_v12/feishu_gateway.py` — add `create_design_document`, `download_card_attachment`
- `src/requirement_workflow_v12/plan_context.py` — inject `design_artifact` field
- `src/requirement_workflow_v12/spec_context.py` — inject `design_artifact` field

---

## Task 1: Extend DesignStatus + DesignEvent + Transitions

**Files:**
- Modify: `src/requirement_workflow_v12/plan_state_machine.py`
- Test: `tests/test_design_state_machine.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_design_state_machine.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.plan_state_machine import (
    DesignStatus, DesignEvent, apply_design_event,
)


def test_design_start_from_none_goes_drafting():
    d = apply_design_event(None, DesignEvent.DESIGN_START)
    assert d.allowed is True
    assert d.next_status is DesignStatus.DRAFTING


def test_design_submit_from_drafting_goes_submit_pending_review():
    d = apply_design_event(DesignStatus.DRAFTING, DesignEvent.DESIGN_SUBMIT)
    assert d.allowed is True
    assert d.next_status is DesignStatus.SUBMIT_PENDING_REVIEW


def test_design_final_approve_from_submit_pending_review_goes_ready():
    d = apply_design_event(
        DesignStatus.SUBMIT_PENDING_REVIEW, DesignEvent.DESIGN_FINAL_APPROVE,
    )
    assert d.allowed is True
    assert d.next_status is DesignStatus.READY


def test_design_final_reject_from_submit_pending_review_goes_drafting():
    d = apply_design_event(
        DesignStatus.SUBMIT_PENDING_REVIEW, DesignEvent.DESIGN_FINAL_REJECT,
    )
    assert d.allowed is True
    assert d.next_status is DesignStatus.DRAFTING


def test_design_submit_from_none_rejected():
    d = apply_design_event(None, DesignEvent.DESIGN_SUBMIT)
    assert d.allowed is False


def test_design_final_approve_from_drafting_rejected():
    d = apply_design_event(DesignStatus.DRAFTING, DesignEvent.DESIGN_FINAL_APPROVE)
    assert d.allowed is False


def test_design_restart_from_any_state_goes_none():
    for st in [DesignStatus.DRAFTING, DesignStatus.SUBMIT_PENDING_REVIEW, DesignStatus.READY]:
        d = apply_design_event(st, DesignEvent.DESIGN_RESTART)
        assert d.allowed is True
        assert d.next_status is None


def test_design_restart_from_none_rejected():
    d = apply_design_event(None, DesignEvent.DESIGN_RESTART)
    assert d.allowed is False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_design_state_machine.py -v
```
Expected: FAIL with `AttributeError: SUBMIT_PENDING_REVIEW` (existing `DesignStatus` only has `DRAFTING`/`READY`).

- [ ] **Step 3: Extend `plan_state_machine.py`**

In `src/requirement_workflow_v12/plan_state_machine.py`:

Replace the `DesignStatus` enum (lines 40-42) with:
```python
class DesignStatus(str, Enum):
    DRAFTING              = "DESIGN_DRAFTING"
    SUBMIT_PENDING_REVIEW = "DESIGN_SUBMIT_PENDING_REVIEW"
    READY                 = "DESIGN_READY"
```

Replace the `DesignEvent` enum (lines 45-48) with:
```python
class DesignEvent(str, Enum):
    DESIGN_START         = "design_start"
    DESIGN_SUBMIT        = "design_submit"
    DESIGN_FINAL_APPROVE = "design_final_approve"
    DESIGN_FINAL_REJECT  = "design_final_reject"
    DESIGN_RESTART       = "design_restart"
```

Replace `_DESIGN_TRANSITIONS` (lines 118-121) with:
```python
_DESIGN_TRANSITIONS: dict[tuple[Optional[DesignStatus], DesignEvent], DesignStatus] = {
    (None, DesignEvent.DESIGN_START): DesignStatus.DRAFTING,
    (DesignStatus.DRAFTING, DesignEvent.DESIGN_SUBMIT): DesignStatus.SUBMIT_PENDING_REVIEW,
    (DesignStatus.SUBMIT_PENDING_REVIEW, DesignEvent.DESIGN_FINAL_APPROVE): DesignStatus.READY,
    (DesignStatus.SUBMIT_PENDING_REVIEW, DesignEvent.DESIGN_FINAL_REJECT): DesignStatus.DRAFTING,
}
```

The existing `apply_design_event` function body (lines 124-153) already handles `DESIGN_RESTART` and dict lookup — no change needed.

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m pytest tests/test_design_state_machine.py -v
```
Expected: 8 tests PASS.

- [ ] **Step 5: Run the full suite to catch regressions**

```bash
python3 -m unittest discover -s tests -v 2>&1 | tail -5
```
Expected: `OK` at tail. (Existing `DesignStatus` string value changed? No — old DRAFTING value was `"DESIGN_DRAFTING"`, READY was `"DESIGN_READY"`; those are unchanged.)

- [ ] **Step 6: Commit**

```bash
git add src/requirement_workflow_v12/plan_state_machine.py tests/test_design_state_machine.py
git commit -m "feat(design-phase): extend DesignStatus to 3-state machine"
```

---

## Task 2: Extend Requirement Model with Design Fields

**Files:**
- Modify: `src/requirement_workflow_v12/models.py:142-143`
- Test: `tests/test_models_design_fields.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_models_design_fields.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.models import Requirement


def _make_req() -> Requirement:
    return Requirement(
        req_id="REQ-X-001", name="n", project="X", summary="s", creator="c",
    )


def test_design_doc_fields_default_empty():
    r = _make_req()
    assert r.design_doc_id == ""
    assert r.design_doc_url == ""


def test_design_archive_fields_default_empty():
    r = _make_req()
    assert r.design_archive_path == ""
    assert r.design_github_revision == ""


def test_design_precondition_met_defaults_false():
    r = _make_req()
    assert r.design_precondition_met is False


def test_pending_design_brief_defaults_none():
    r = _make_req()
    assert r.pending_design_brief is None


def test_pending_design_handoff_defaults_none():
    r = _make_req()
    assert r.pending_design_handoff is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_models_design_fields.py -v
```
Expected: FAIL with `AttributeError: 'Requirement' object has no attribute 'design_doc_id'`.

- [ ] **Step 3: Add fields to `models.py`**

In `src/requirement_workflow_v12/models.py`, after the existing `design_status` line (line 142), insert:

```python
    design_doc_id: str = ""
    design_doc_url: str = ""
    design_archive_path: str = ""
    design_github_revision: str = ""
    design_precondition_met: bool = False
    pending_design_brief: dict | None = None
    pending_design_handoff: dict | None = None
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m pytest tests/test_models_design_fields.py -v
```
Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/models.py tests/test_models_design_fields.py
git commit -m "feat(design-phase): add design fields to Requirement model"
```

---

## Task 3: Extend Store Serialization for Design Fields

**Files:**
- Modify: `src/requirement_workflow_v12/store.py`
- Test: `tests/test_store_design_fields_roundtrip.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_store_design_fields_roundtrip.py`:

```python
import sys
import json
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.models import Requirement
from requirement_workflow_v12.plan_state_machine import DesignStatus
from requirement_workflow_v12.store import RequirementStore


def test_design_fields_roundtrip(tmp_path: Path) -> None:
    store = RequirementStore(tmp_path / "state.json")
    r = Requirement(
        req_id="REQ-X-001", name="n", project="X", summary="s", creator="c",
        design_status=DesignStatus.SUBMIT_PENDING_REVIEW,
        design_doc_id="doc-id-1",
        design_doc_url="https://feishu/d/1",
        design_archive_path="design/archive/REQ-X-001_foo/",
        design_github_revision="abc1234",
        design_precondition_met=True,
        pending_design_brief={"brief_yaml_frontmatter": "a"},
        pending_design_handoff={"manifest_summary": "b"},
    )
    store.save({"REQ-X-001": r})

    store2 = RequirementStore(tmp_path / "state.json")
    loaded = store2.load()["REQ-X-001"]

    assert loaded.design_status is DesignStatus.SUBMIT_PENDING_REVIEW
    assert loaded.design_doc_id == "doc-id-1"
    assert loaded.design_doc_url == "https://feishu/d/1"
    assert loaded.design_archive_path == "design/archive/REQ-X-001_foo/"
    assert loaded.design_github_revision == "abc1234"
    assert loaded.design_precondition_met is True
    assert loaded.pending_design_brief == {"brief_yaml_frontmatter": "a"}
    assert loaded.pending_design_handoff == {"manifest_summary": "b"}


def test_missing_design_fields_load_as_defaults(tmp_path: Path) -> None:
    """Old snapshots lack new fields; loader must tolerate."""
    path = tmp_path / "state.json"
    path.write_text(json.dumps({
        "requirements": [{
            "req_id": "OLD-001", "name": "n", "project": "X",
            "summary": "s", "creator": "c",
            "status": "CREATED",
        }]
    }))
    loaded = RequirementStore(path).load()["OLD-001"]
    assert loaded.design_doc_id == ""
    assert loaded.design_precondition_met is False
    assert loaded.pending_design_brief is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_store_design_fields_roundtrip.py -v
```
Expected: FAIL — fields not serialized.

- [ ] **Step 3: Extend `store.py`**

Open `src/requirement_workflow_v12/store.py`. Find the `_requirement_to_dict` function (or equivalent — the dict-building logic for saving). Add the new fields to the serialized dict.

Find the load function (around line 104 where `raw_design_status` is read). After the existing `design_status` block, add:

```python
        design_doc_id = str(data.get("design_doc_id") or "")
        design_doc_url = str(data.get("design_doc_url") or "")
        design_archive_path = str(data.get("design_archive_path") or "")
        design_github_revision = str(data.get("design_github_revision") or "")
        design_precondition_met = bool(data.get("design_precondition_met", False))
        pending_design_brief = data.get("pending_design_brief")
        if pending_design_brief is not None and not isinstance(pending_design_brief, dict):
            pending_design_brief = None
        pending_design_handoff = data.get("pending_design_handoff")
        if pending_design_handoff is not None and not isinstance(pending_design_handoff, dict):
            pending_design_handoff = None
```

Then pass them to the `Requirement(...)` constructor call (find the existing `design_status=design_status,` line; add the new fields below it).

For the save side, find the function that writes `Requirement` to dict (grep for `"design_status":` as anchor). Add alongside:

```python
            "design_doc_id": r.design_doc_id,
            "design_doc_url": r.design_doc_url,
            "design_archive_path": r.design_archive_path,
            "design_github_revision": r.design_github_revision,
            "design_precondition_met": r.design_precondition_met,
            "pending_design_brief": r.pending_design_brief,
            "pending_design_handoff": r.pending_design_handoff,
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m pytest tests/test_store_design_fields_roundtrip.py -v
```
Expected: 2 tests PASS.

- [ ] **Step 5: Run the full suite**

```bash
python3 -m unittest discover -s tests -v 2>&1 | tail -5
```
Expected: `OK`.

- [ ] **Step 6: Commit**

```bash
git add src/requirement_workflow_v12/store.py tests/test_store_design_fields_roundtrip.py
git commit -m "feat(design-phase): serialize design fields in RequirementStore"
```

---

## Task 4: DesignContextBuilder — pull design-context payload

**Files:**
- Create: `src/requirement_workflow_v12/design_context.py`
- Test: `tests/test_design_context.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_design_context.py`:

```python
import sys
from pathlib import Path
from unittest.mock import MagicMock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.models import Requirement, WorkflowStatus
from requirement_workflow_v12.plan_state_machine import DesignStatus
from requirement_workflow_v12.design_context import (
    DesignContextBuilder, DesignContextGateError, DesignContextMisconfigured,
)


def _approved_req(**kw) -> Requirement:
    return Requirement(
        req_id="REQ-X-001", name="测试需求", project="X",
        summary="用户上传头像审核流程", creator="user1",
        status=WorkflowStatus.APPROVED,
        needs_ui=True,
        design_status=DesignStatus.DRAFTING,
        document_url="https://feishu/d/req001",
        design_doc_id="design-doc-001",
        design_doc_url="https://feishu/d/design001",
        **kw,
    )


def _service_with(requirement, project_config=None):
    svc = MagicMock()
    svc.requirements = {requirement.req_id: requirement}
    svc.project_configs = {requirement.project: project_config} if project_config else {}
    return svc


def _cfg(**kw):
    cfg = MagicMock()
    cfg.tech_stack = kw.get("tech_stack", {"frontend": "Vite+React"})
    cfg.category = kw.get("category", "enterprise-app")
    cfg.template_version = kw.get("template_version", "v1")
    cfg.claude_design_project_url = kw.get("claude_design_project_url", "")
    cfg.frontend_subpath = kw.get("frontend_subpath", "src/x_webapp")
    cfg.architecture_doc_url = kw.get("architecture_doc_url", "")
    cfg.github_repo_url = kw.get("github_repo_url", "")
    return cfg


def test_build_returns_full_context_for_drafting_req():
    req = _approved_req()
    svc = _service_with(req, _cfg(claude_design_project_url="https://claude.ai/design/p/xyz"))
    ctx = DesignContextBuilder(svc).build("REQ-X-001")
    assert ctx["req_id"] == "REQ-X-001"
    assert ctx["needs_ui"] is True
    assert ctx["claude_design_project_url"] == "https://claude.ai/design/p/xyz"
    assert ctx["frontend_subpath"] == "src/x_webapp"
    assert ctx["design_doc_id"] == "design-doc-001"
    assert ctx["design_doc_url"] == "https://feishu/d/design001"
    assert "current_pages" in ctx
    assert ctx["current_pages"] == []


def test_build_rejects_wrong_status():
    req = _approved_req(status=WorkflowStatus.CREATED)
    svc = _service_with(req, _cfg())
    import pytest
    with pytest.raises(DesignContextGateError):
        DesignContextBuilder(svc).build("REQ-X-001")


def test_build_rejects_needs_ui_false():
    req = _approved_req(needs_ui=False)
    svc = _service_with(req, _cfg())
    import pytest
    with pytest.raises(DesignContextGateError):
        DesignContextBuilder(svc).build("REQ-X-001")


def test_build_rejects_wrong_design_status():
    req = _approved_req(design_status=DesignStatus.READY)
    svc = _service_with(req, _cfg())
    import pytest
    with pytest.raises(DesignContextGateError):
        DesignContextBuilder(svc).build("REQ-X-001")


def test_build_raises_misconfigured_when_no_project_config():
    req = _approved_req()
    svc = _service_with(req, project_config=None)
    import pytest
    with pytest.raises(DesignContextMisconfigured):
        DesignContextBuilder(svc).build("REQ-X-001")


def test_build_empty_claude_design_url_still_succeeds():
    """Bootstrap may not have run; url may be empty. Context still emits, skill handles."""
    req = _approved_req()
    svc = _service_with(req, _cfg(claude_design_project_url=""))
    ctx = DesignContextBuilder(svc).build("REQ-X-001")
    assert ctx["claude_design_project_url"] == ""
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_design_context.py -v
```
Expected: FAIL with `ModuleNotFoundError: design_context`.

- [ ] **Step 3: Create `design_context.py`**

Create `src/requirement_workflow_v12/design_context.py`:

```python
"""DESIGN-layer context builder used by design-brief-author skill."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .models import WorkflowStatus
from .plan_state_machine import DesignStatus


DESIGN_CONTEXT_ALLOWED_STATUSES = {DesignStatus.DRAFTING}


class DesignContextGateError(Exception):
    def __init__(self, message: str, current_status: str) -> None:
        super().__init__(message)
        self.current_status = current_status


class DesignContextMisconfigured(Exception):
    """No ProjectConfig for this project."""


class DesignContextBuilder:
    def __init__(self, service) -> None:
        self._service = service

    def build(self, req_id: str) -> dict[str, Any]:
        r = self._service.requirements.get(req_id)
        if r is None:
            raise ValueError(f"未知需求：{req_id}")
        if r.status != WorkflowStatus.APPROVED or not r.needs_ui:
            raise DesignContextGateError(
                f"design-context 要求 APPROVED + needs_ui=true; "
                f"got status={r.status.value} needs_ui={r.needs_ui}",
                current_status=r.status.value,
            )
        if r.design_status not in DESIGN_CONTEXT_ALLOWED_STATUSES:
            label = r.design_status.value if r.design_status else "None"
            raise DesignContextGateError(
                f"design-context 要求 DesignStatus=DRAFTING; got {label}",
                current_status=r.status.value,
            )
        cfg = self._service.project_configs.get(r.project)
        if cfg is None:
            raise DesignContextMisconfigured(f"项目 {r.project} 未初始化")

        current_pages = self._load_pages_registry_slice(cfg)
        prior_archive = self._find_prior_archive(req_id, r.project)

        return {
            "req_id": r.req_id,
            "project": r.project,
            "requirement_document_url": r.document_url,
            "needs_ui": r.needs_ui,
            "claude_design_project_url": getattr(cfg, "claude_design_project_url", ""),
            "frontend_subpath": getattr(cfg, "frontend_subpath", ""),
            "frontend_tech_stack": dict(getattr(cfg, "tech_stack", {})),
            "category": cfg.category,
            "template_version": cfg.template_version,
            "architecture_doc_url": cfg.architecture_doc_url,
            "project_repo": cfg.github_repo_url,
            "design_doc_id": r.design_doc_id,
            "design_doc_url": r.design_doc_url,
            "current_pages": current_pages,
            "prior_handoff_archive_ref": prior_archive,
        }

    def _load_pages_registry_slice(self, cfg) -> list[dict]:
        """Read design/PAGES.yaml from the project repo (if accessible).

        In MVP we return [] when the file is unreachable (no project repo cloned
        locally for coordinator to read). Real integration hooks this to a
        project-repo gateway in a future task.
        """
        return []

    def _find_prior_archive(self, req_id: str, project: str) -> str:
        """Return path of the most recent predecessor REQ's design archive.

        v1: returns "" — the coordinator does not have filesystem access to the
        project repo to enumerate. The skill handles empty gracefully.
        """
        return ""
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m pytest tests/test_design_context.py -v
```
Expected: 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/design_context.py tests/test_design_context.py
git commit -m "feat(design-phase): add DesignContextBuilder for brief-author skill"
```

---

## Task 5: design_intake — zip extraction + MANIFEST generation

**Files:**
- Create: `src/requirement_workflow_v12/design_intake.py`
- Create: `tests/fixtures/design/handoff_v0.zip` — copy from `/Users/macbookpro/Downloads/投资经理助手-handoff.zip`
- Test: `tests/test_design_intake.py` (new)

- [ ] **Step 1: Copy real zip fixture**

```bash
mkdir -p tests/fixtures/design
cp "/Users/macbookpro/Downloads/投资经理助手-handoff.zip" tests/fixtures/design/handoff_sample.zip
ls -la tests/fixtures/design/handoff_sample.zip
```
Expected: ~107 KB.

- [ ] **Step 2: Write the failing test**

Create `tests/test_design_intake.py`:

```python
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.design_intake import (
    DesignIntake, IntakeResult, IntakeError,
)


FIXTURE_ZIP = Path(__file__).parent / "fixtures" / "design" / "handoff_sample.zip"


def test_intake_extracts_zip_to_archive_dir(tmp_path: Path) -> None:
    archive_root = tmp_path / "design" / "archive"
    archive_root.mkdir(parents=True)
    result = DesignIntake().intake(
        zip_path=FIXTURE_ZIP,
        req_id="REQ-TEST-001",
        slug="report-editor",
        archive_root=archive_root,
    )
    assert isinstance(result, IntakeResult)
    assert result.archive_dir.name == "REQ-TEST-001_report-editor"
    # extracted tree must have at least untitled/README.md
    assert (result.archive_dir / "extracted" / "untitled" / "README.md").exists()
    # original zip preserved
    assert (result.archive_dir / "bundle.zip").exists()


def test_intake_generates_manifest(tmp_path: Path) -> None:
    archive_root = tmp_path / "design" / "archive"
    archive_root.mkdir(parents=True)
    result = DesignIntake().intake(
        zip_path=FIXTURE_ZIP,
        req_id="REQ-TEST-001",
        slug="report-editor",
        archive_root=archive_root,
    )
    manifest = (result.archive_dir / "MANIFEST.md").read_text(encoding="utf-8")
    assert "REQ-TEST-001" in manifest
    assert "export_type:" in manifest
    # bundle has the v2 anchor folder
    assert "design_handoff_" in manifest


def test_intake_detects_chinese_filenames(tmp_path: Path) -> None:
    """zip contains Chinese CN file/dir names; intake must preserve them via
    cp437→utf-8 repair."""
    archive_root = tmp_path / "design" / "archive"
    archive_root.mkdir(parents=True)
    result = DesignIntake().intake(
        zip_path=FIXTURE_ZIP,
        req_id="REQ-TEST-001",
        slug="x",
        archive_root=archive_root,
    )
    # Walk extracted tree; any filename with Chinese chars must be readable
    extracted_files = list((result.archive_dir / "extracted").rglob("*"))
    chinese = [f for f in extracted_files if any("一" <= c <= "鿿" for c in f.name)]
    assert len(chinese) > 0, "Expected some Chinese-named files in the sample zip"


def test_intake_raises_on_corrupt_zip(tmp_path: Path) -> None:
    bad_zip = tmp_path / "bad.zip"
    bad_zip.write_bytes(b"not a zip")
    archive_root = tmp_path / "design" / "archive"
    archive_root.mkdir(parents=True)
    import pytest
    with pytest.raises(IntakeError):
        DesignIntake().intake(
            zip_path=bad_zip, req_id="REQ-TEST-001", slug="x",
            archive_root=archive_root,
        )
```

- [ ] **Step 3: Run test to verify it fails**

```bash
python3 -m pytest tests/test_design_intake.py -v
```
Expected: FAIL with `ModuleNotFoundError: design_intake`.

- [ ] **Step 4: Create `design_intake.py`**

Create `src/requirement_workflow_v12/design_intake.py`:

```python
"""Design handoff bundle intake: unzip, normalize filenames, generate MANIFEST."""
from __future__ import annotations

import hashlib
import shutil
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


class IntakeError(Exception):
    """Raised when a handoff zip cannot be processed."""


@dataclass
class IntakeResult:
    archive_dir: Path
    export_type: str              # "pure_export" | "anchor_bump"
    anchors_in_bundle: list[dict] # [{folder_name, tree_sha256}]
    pages_hint: list[str]         # display_name candidates from src/*.jsx
    inner_readme_excerpt: str


class DesignIntake:
    """Stateless handler: accepts a zip + meta, writes archive dir + MANIFEST."""

    def intake(
        self, *, zip_path: Path, req_id: str, slug: str, archive_root: Path,
        known_anchor_hashes: set[str] | None = None,
    ) -> IntakeResult:
        archive_dir = archive_root / f"{req_id}_{slug}"
        archive_dir.mkdir(parents=True, exist_ok=False)

        try:
            shutil.copy2(zip_path, archive_dir / "bundle.zip")
            extracted = archive_dir / "extracted"
            extracted.mkdir()
            self._extract_with_cn_repair(zip_path, extracted)
        except Exception as exc:
            shutil.rmtree(archive_dir, ignore_errors=True)
            raise IntakeError(f"intake failed for {req_id}: {exc}") from exc

        anchors = self._enumerate_anchors(extracted)
        known = known_anchor_hashes or set()
        new_anchors = [a for a in anchors if a["tree_sha256"] not in known]
        export_type = "anchor_bump" if new_anchors else "pure_export"

        pages_hint = self._extract_page_hints(extracted)
        inner_readme_excerpt = self._extract_inner_readme(extracted, limit=500)

        manifest = self._render_manifest(
            req_id=req_id, export_type=export_type,
            anchors=anchors, pages_hint=pages_hint,
            inner_readme_excerpt=inner_readme_excerpt,
        )
        (archive_dir / "MANIFEST.md").write_text(manifest, encoding="utf-8")

        return IntakeResult(
            archive_dir=archive_dir, export_type=export_type,
            anchors_in_bundle=anchors, pages_hint=pages_hint,
            inner_readme_excerpt=inner_readme_excerpt,
        )

    def _extract_with_cn_repair(self, zip_path: Path, dest: Path) -> None:
        with zipfile.ZipFile(zip_path) as zf:
            for info in zf.infolist():
                try:
                    info.filename = info.filename.encode("cp437").decode("utf-8")
                except (UnicodeEncodeError, UnicodeDecodeError):
                    pass  # already UTF-8 or plain ASCII
                zf.extract(info, dest)

    def _enumerate_anchors(self, extracted: Path) -> list[dict]:
        anchors = []
        for candidate in extracted.rglob("design_handoff_*"):
            if not candidate.is_dir():
                continue
            tree_hash = self._hash_tree(candidate)
            anchors.append({
                "folder_name": candidate.name,
                "tree_sha256": tree_hash,
            })
        return anchors

    def _hash_tree(self, root: Path) -> str:
        h = hashlib.sha256()
        for f in sorted(p for p in root.rglob("*") if p.is_file()):
            h.update(str(f.relative_to(root)).encode("utf-8"))
            h.update(b"\0")
            h.update(f.read_bytes())
        return h.hexdigest()

    def _extract_page_hints(self, extracted: Path) -> list[str]:
        """Heuristic: bare project/src/*.jsx filenames (capitalized) are page candidates."""
        hints: list[str] = []
        for proj in extracted.rglob("project"):
            if not proj.is_dir():
                continue
            src = proj / "src"
            if src.is_dir():
                for jsx in sorted(src.glob("*.jsx")):
                    name = jsx.stem
                    if name[:1].isupper() and name not in ("App", "Shell"):
                        hints.append(name)
                break
        return hints

    def _extract_inner_readme(self, extracted: Path, *, limit: int) -> str:
        for readme in extracted.rglob("design_handoff_*/README.md"):
            text = readme.read_text(encoding="utf-8", errors="replace")
            return text[:limit]
        return ""

    def _render_manifest(
        self, *, req_id: str, export_type: str, anchors: list[dict],
        pages_hint: list[str], inner_readme_excerpt: str,
    ) -> str:
        lines = ["---"]
        lines.append(f"req_id: {req_id}")
        lines.append(f"archived_at: \"{datetime.now(timezone.utc).isoformat()}\"")
        lines.append("archived_by: coordinator-service")
        lines.append(f"export_type: {export_type}")
        lines.append("anchors_in_bundle:")
        for a in anchors:
            lines.append(f"  - folder_name: {a['folder_name']}")
            lines.append(f"    tree_sha256: {a['tree_sha256']}")
        lines.append("pages_hint:")
        for p in pages_hint:
            lines.append(f"  - {p}")
        lines.append("bundle_inner_readme_excerpt: |")
        for line in inner_readme_excerpt.splitlines():
            lines.append(f"  {line}")
        lines.append("---")
        lines.append("")
        lines.append(f"# {req_id} Design Handoff Summary")
        lines.append("")
        lines.append("## Pages Hint (from bundle src/*.jsx)")
        for p in pages_hint:
            lines.append(f"- {p}")
        lines.append("")
        lines.append("## Reviewer Notes (D-DESIGN-2 终审人填写)")
        lines.append("_待填_")
        lines.append("")
        return "\n".join(lines)
```

- [ ] **Step 5: Run test to verify it passes**

```bash
python3 -m pytest tests/test_design_intake.py -v
```
Expected: 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/requirement_workflow_v12/design_intake.py tests/test_design_intake.py tests/fixtures/design/handoff_sample.zip
git commit -m "feat(design-phase): add DesignIntake for bundle extraction + MANIFEST"
```

---

## Task 6: design_syncer — GitHub atomic commit on READY

**Files:**
- Create: `src/requirement_workflow_v12/design_syncer.py`
- Test: `tests/test_design_syncer.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_design_syncer.py`:

```python
import sys
from pathlib import Path
from unittest.mock import MagicMock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.design_syncer import (
    DesignSyncer, DesignSyncResult, DesignSyncError,
)


def _mk_archive_dir(tmp: Path, req_id: str, slug: str) -> Path:
    d = tmp / "design" / "archive" / f"{req_id}_{slug}"
    d.mkdir(parents=True)
    (d / "MANIFEST.md").write_text("# mf\n", encoding="utf-8")
    (d / "BRIEF.md").write_text("# bf\n", encoding="utf-8")
    (d / "bundle.zip").write_bytes(b"zipbytes")
    ex = d / "extracted"
    ex.mkdir()
    (ex / "README.md").write_text("readme\n", encoding="utf-8")
    return d


def test_sync_commits_archive_and_updates_registry(tmp_path: Path) -> None:
    archive = _mk_archive_dir(tmp_path, "REQ-X-001", "foo")
    registry = tmp_path / "design" / "PAGES.yaml"
    registry.write_text("schema_version: '1.0'\npages: []\n", encoding="utf-8")
    index = tmp_path / "design" / "INDEX.md"
    index.write_text("# Design Handoff Index\n", encoding="utf-8")

    gateway = MagicMock()
    gateway.project_repo_commit.return_value = "commit-sha-abc"

    result = DesignSyncer(gateway).sync(
        project_repo="org/repo",
        req_id="REQ-X-001",
        slug="foo",
        archive_dir=archive,
        pages_registry_path=registry,
        index_path=index,
        pages_touched=[
            {"display_name": "Dashboard", "action": "modify"},
            {"display_name": "ProfileUpload", "action": "new"},
        ],
    )
    assert isinstance(result, DesignSyncResult)
    assert result.commit_sha == "commit-sha-abc"
    gateway.project_repo_commit.assert_called_once()
    _, kwargs = gateway.project_repo_commit.call_args
    files = kwargs["files"]
    assert any("design/archive/REQ-X-001_foo/MANIFEST.md" in f for f in files)
    assert "design/PAGES.yaml" in files
    assert "design/INDEX.md" in files


def test_sync_updates_registry_new_page_entry(tmp_path: Path) -> None:
    archive = _mk_archive_dir(tmp_path, "REQ-X-002", "bar")
    registry = tmp_path / "design" / "PAGES.yaml"
    registry.write_text("schema_version: '1.0'\npages: []\n", encoding="utf-8")
    index = tmp_path / "design" / "INDEX.md"
    index.write_text("# Design Handoff Index\n", encoding="utf-8")

    gateway = MagicMock()
    gateway.project_repo_commit.return_value = "c"

    DesignSyncer(gateway).sync(
        project_repo="org/repo", req_id="REQ-X-002", slug="bar",
        archive_dir=archive, pages_registry_path=registry, index_path=index,
        pages_touched=[{"display_name": "Upload", "action": "new"}],
    )
    new_reg = registry.read_text(encoding="utf-8")
    assert "Upload" in new_reg
    assert "REQ-X-002" in new_reg


def test_sync_updates_index_prepends_entry(tmp_path: Path) -> None:
    archive = _mk_archive_dir(tmp_path, "REQ-X-003", "baz")
    registry = tmp_path / "design" / "PAGES.yaml"
    registry.write_text("schema_version: '1.0'\npages: []\n", encoding="utf-8")
    index = tmp_path / "design" / "INDEX.md"
    index.write_text("# Design Handoff Index\n\n## 2026-04-20 prior\n", encoding="utf-8")

    gateway = MagicMock()
    gateway.project_repo_commit.return_value = "c"

    DesignSyncer(gateway).sync(
        project_repo="org/repo", req_id="REQ-X-003", slug="baz",
        archive_dir=archive, pages_registry_path=registry, index_path=index,
        pages_touched=[{"display_name": "X", "action": "new"}],
    )
    new_idx = index.read_text(encoding="utf-8")
    assert new_idx.index("REQ-X-003") < new_idx.index("2026-04-20 prior")


def test_sync_raises_when_gateway_fails(tmp_path: Path) -> None:
    archive = _mk_archive_dir(tmp_path, "REQ-X-004", "qux")
    registry = tmp_path / "design" / "PAGES.yaml"
    registry.write_text("schema_version: '1.0'\npages: []\n", encoding="utf-8")
    index = tmp_path / "design" / "INDEX.md"
    index.write_text("# Design Handoff Index\n", encoding="utf-8")

    gateway = MagicMock()
    gateway.project_repo_commit.side_effect = RuntimeError("gh 500")

    import pytest
    with pytest.raises(DesignSyncError):
        DesignSyncer(gateway).sync(
            project_repo="org/repo", req_id="REQ-X-004", slug="qux",
            archive_dir=archive, pages_registry_path=registry, index_path=index,
            pages_touched=[],
        )
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_design_syncer.py -v
```
Expected: FAIL with `ModuleNotFoundError: design_syncer`.

- [ ] **Step 3: Create `design_syncer.py`**

Create `src/requirement_workflow_v12/design_syncer.py`:

```python
"""Design READY → GitHub single-commit syncer.

Atomic operation on `onEnter(DesignStatus.READY)`:
  - commit the REQ's archive dir (recursive)
  - update design/PAGES.yaml with pages_touched
  - update design/INDEX.md (prepend entry)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore


class DesignSyncError(Exception):
    pass


@dataclass
class DesignSyncResult:
    commit_sha: str


class DesignSyncer:
    def __init__(self, project_repo_gateway) -> None:
        self._gw = project_repo_gateway

    def sync(
        self, *,
        project_repo: str,
        req_id: str,
        slug: str,
        archive_dir: Path,
        pages_registry_path: Path,
        index_path: Path,
        pages_touched: list[dict],
    ) -> DesignSyncResult:
        self._update_pages_registry(pages_registry_path, req_id, pages_touched)
        self._update_index(index_path, req_id, slug, pages_touched)

        files = self._collect_files(
            archive_dir=archive_dir,
            registry_path=pages_registry_path,
            index_path=index_path,
        )

        try:
            sha = self._gw.project_repo_commit(
                project_repo=project_repo,
                message=f"design: lock handoff for {req_id}",
                files=files,
            )
        except Exception as exc:
            raise DesignSyncError(f"github commit failed: {exc}") from exc

        return DesignSyncResult(commit_sha=sha)

    def _update_pages_registry(
        self, registry_path: Path, req_id: str, pages_touched: list[dict],
    ) -> None:
        if yaml is None:
            raise DesignSyncError("PyYAML not installed; required for PAGES.yaml update")
        doc = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
        pages = doc.setdefault("pages", [])
        archive_ref = f"design/archive/{req_id}_{self._slug_from_archive(registry_path, req_id)}"

        index_by_name = {p["display_name"]: p for p in pages if "display_name" in p}
        for touch in pages_touched:
            name = touch["display_name"]
            action = touch.get("action", "new")
            if name in index_by_name:
                entry = index_by_name[name]
                entry["last_modified_by_req"] = req_id
                entry["latest_archive_ref"] = archive_ref
            else:
                pages.append({
                    "display_name": name,
                    "created_by_req": req_id,
                    "last_modified_by_req": req_id,
                    "latest_archive_ref": archive_ref,
                    "target_component": "",
                    "target_route": "",
                    "bundle_src_hint": f"src/{name}.jsx",
                })
        registry_path.write_text(
            yaml.safe_dump(doc, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

    def _slug_from_archive(self, registry_path: Path, req_id: str) -> str:
        """Scan design/archive/ for REQ-X_<slug>/ dir; return <slug>.

        Called after the archive dir already exists on disk.
        """
        design_root = registry_path.parent
        archive_root = design_root / "archive"
        for child in archive_root.iterdir():
            if child.is_dir() and child.name.startswith(f"{req_id}_"):
                return child.name[len(req_id) + 1:]
        raise DesignSyncError(f"cannot locate archive dir for {req_id}")

    def _update_index(
        self, index_path: Path, req_id: str, slug: str, pages_touched: list[dict],
    ) -> None:
        existing = index_path.read_text(encoding="utf-8")
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        pages_str = ", ".join(
            f"{p['display_name']} ({p.get('action', 'new')})"
            for p in pages_touched
        ) or "(no pages declared)"
        entry = (
            f"\n## {date} | {req_id} | {slug}\n"
            f"- Archive: [design/archive/{req_id}_{slug}/](./archive/{req_id}_{slug}/)\n"
            f"- Pages touched: {pages_str}\n"
        )
        header_end = existing.find("\n", existing.find("# Design Handoff Index"))
        if header_end == -1:
            new = existing.rstrip() + entry
        else:
            new = existing[: header_end + 1] + entry + existing[header_end + 1 :]
        index_path.write_text(new, encoding="utf-8")

    def _collect_files(
        self, *, archive_dir: Path, registry_path: Path, index_path: Path,
    ) -> dict[str, bytes]:
        """Return {relative_repo_path: content_bytes} for the commit."""
        design_root = registry_path.parent
        repo_root = design_root.parent  # design/ is at repo_root/design
        files: dict[str, bytes] = {}
        for f in archive_dir.rglob("*"):
            if f.is_file():
                rel = f.relative_to(repo_root).as_posix()
                files[rel] = f.read_bytes()
        files[registry_path.relative_to(repo_root).as_posix()] = registry_path.read_bytes()
        files[index_path.relative_to(repo_root).as_posix()] = index_path.read_bytes()
        return files
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m pytest tests/test_design_syncer.py -v
```
Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/design_syncer.py tests/test_design_syncer.py
git commit -m "feat(design-phase): add DesignSyncer for READY→GitHub atomic commit"
```

---

## Task 7: FeishuGateway — create_design_document

**Files:**
- Modify: `src/requirement_workflow_v12/feishu_gateway.py`
- Test: `tests/test_feishu_design_document.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_feishu_design_document.py`:

```python
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.models import Requirement
from requirement_workflow_v12.feishu_gateway import FeishuGateway


def _req() -> Requirement:
    return Requirement(
        req_id="REQ-X-007", name="头像审核", project="X",
        summary="上传头像走审核流程", creator="u",
    )


def test_create_design_document_returns_doc_id_and_url():
    gw = FeishuGateway.__new__(FeishuGateway)  # bypass __init__
    with patch.object(gw, "_create_docx", return_value=("doc-x7", "https://feishu/d/x7")) as mk:
        got = gw.create_design_document(_req())
        assert got.document_id == "doc-x7"
        assert got.document_url == "https://feishu/d/x7"
        args, kwargs = mk.call_args
        assert "REQ-X-007" in args[0]
        assert "设计" in args[0] or "Design" in args[0]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_feishu_design_document.py -v
```
Expected: FAIL — `AttributeError: create_design_document`.

- [ ] **Step 3: Extend `feishu_gateway.py`**

In `feishu_gateway.py`, find `create_plan_document`. Add immediately below it (parallel implementation):

```python
    def create_design_document(self, requirement: "Requirement"):
        from .feishu_gateway import CreatedDocument   # re-import to avoid cycles
        title = f"{requirement.req_id} · {requirement.name} · 设计 Brief"
        doc_id, doc_url = self._create_docx(title)
        return CreatedDocument(document_id=doc_id, document_url=doc_url)
```

If `CreatedDocument` dataclass doesn't exist in the module yet, add near top:

```python
from dataclasses import dataclass

@dataclass
class CreatedDocument:
    document_id: str
    document_url: str
```

(Check existing `create_plan_document` in the same file — if it already uses a shape, match it exactly. Do not introduce a parallel type.)

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m pytest tests/test_feishu_design_document.py -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/feishu_gateway.py tests/test_feishu_design_document.py
git commit -m "feat(design-phase): add FeishuGateway.create_design_document"
```

---

## Task 8: FeishuGateway — download_card_attachment

**Files:**
- Modify: `src/requirement_workflow_v12/feishu_gateway.py`
- Test: `tests/test_feishu_download_attachment.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_feishu_download_attachment.py`:

```python
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.feishu_gateway import FeishuGateway


def test_download_card_attachment_writes_to_path(tmp_path: Path):
    gw = FeishuGateway.__new__(FeishuGateway)
    dest = tmp_path / "handoff.zip"

    def fake_http_get_bytes(url, headers):
        return b"FAKE_ZIP_BYTES"

    with patch.object(gw, "_http_get_bytes", side_effect=fake_http_get_bytes):
        got = gw.download_card_attachment(
            file_key="file-key-abc",
            file_token="token-xyz",
            dest_path=dest,
        )
        assert got == dest
        assert dest.read_bytes() == b"FAKE_ZIP_BYTES"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_feishu_download_attachment.py -v
```
Expected: FAIL — no method.

- [ ] **Step 3: Extend `feishu_gateway.py`**

Append to `FeishuGateway`:

```python
    def download_card_attachment(
        self, *, file_key: str, file_token: str, dest_path: "Path",
    ) -> "Path":
        """Download a card-uploaded file to dest_path.

        Feishu API: POST /open-apis/im/v1/files/{file_key}?file_token=... returning bytes.
        """
        from pathlib import Path as _P
        url = f"{self.base_url}/open-apis/im/v1/files/{file_key}?file_token={file_token}"
        headers = {"Authorization": f"Bearer {self._tenant_access_token()}"}
        data = self._http_get_bytes(url, headers)
        dest = _P(dest_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return dest

    def _http_get_bytes(self, url: str, headers: dict) -> bytes:
        """Override-able thin wrapper around requests.get for testability."""
        import requests
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.content
```

(If the gateway class already has a `_tenant_access_token()` accessor / `base_url` attribute, the code compiles; otherwise wire through the existing auth helper — grep for how `create_plan_document` reaches tokens.)

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m pytest tests/test_feishu_download_attachment.py -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/feishu_gateway.py tests/test_feishu_download_attachment.py
git commit -m "feat(design-phase): add FeishuGateway.download_card_attachment"
```

---

## Task 9: CoordinatorService — design_start

**Files:**
- Modify: `src/requirement_workflow_v12/coordinator_service.py` (add method after `design_restart`)
- Test: `tests/test_coordinator_design.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_coordinator_design.py` (only the first case for now):

```python
import sys
from pathlib import Path
from unittest.mock import MagicMock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.models import Requirement, WorkflowStatus
from requirement_workflow_v12.plan_state_machine import DesignStatus
from requirement_workflow_v12.coordinator_service import CoordinatorService


def _make_svc() -> CoordinatorService:
    svc = CoordinatorService.__new__(CoordinatorService)
    svc.requirements = {}
    svc._hooks = MagicMock()
    return svc


def test_design_start_requires_approved_and_needs_ui():
    svc = _make_svc()
    r = Requirement(
        req_id="REQ-X-001", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
    )
    svc.requirements[r.req_id] = r
    result = svc.design_start(
        r.req_id,
        design_doc_id="d-1",
        design_doc_url="https://feishu/d/1",
    )
    assert result.design_status is DesignStatus.DRAFTING
    assert result.design_doc_id == "d-1"
    assert result.design_doc_url == "https://feishu/d/1"
    svc._hooks.fire_enter.assert_called_once()


def test_design_start_rejects_not_approved():
    svc = _make_svc()
    r = Requirement(
        req_id="REQ-X-002", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.CREATED, needs_ui=True,
    )
    svc.requirements[r.req_id] = r
    import pytest
    with pytest.raises(ValueError, match="APPROVED"):
        svc.design_start(r.req_id, design_doc_id="d", design_doc_url="u")


def test_design_start_rejects_needs_ui_false():
    svc = _make_svc()
    r = Requirement(
        req_id="REQ-X-003", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=False,
    )
    svc.requirements[r.req_id] = r
    import pytest
    with pytest.raises(ValueError, match="needs_ui"):
        svc.design_start(r.req_id, design_doc_id="d", design_doc_url="u")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_coordinator_design.py -v
```
Expected: FAIL — `AttributeError: design_start`.

- [ ] **Step 3: Add `design_start` to coordinator_service.py**

Find `design_restart` (line ~984) in `coordinator_service.py`. **After** that method, add:

```python
    # ── DESIGN layer ────────────────────────────────────────────────────

    def design_start(
        self,
        req_id: str,
        *,
        design_doc_id: str = "",
        design_doc_url: str = "",
    ) -> "Requirement":
        from .plan_state_machine import DesignEvent, apply_design_event
        r = self.requirements[req_id]
        if r.status != WorkflowStatus.APPROVED:
            raise ValueError(
                f"design_start requires workflow_status=APPROVED, got {r.status.value}"
            )
        if not r.needs_ui:
            raise ValueError("design_start requires needs_ui=True")
        decision = apply_design_event(r.design_status, DesignEvent.DESIGN_START)
        if not decision.allowed:
            raise ValueError(decision.message)

        prev = r.design_status
        self._hooks.fire_exit(prev, r)
        r.design_status = decision.next_status
        r.design_doc_id = design_doc_id
        r.design_doc_url = design_doc_url
        self._hooks.fire_enter(r.design_status, r)
        return r
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m pytest tests/test_coordinator_design.py -v
```
Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/coordinator_service.py tests/test_coordinator_design.py
git commit -m "feat(design-phase): add CoordinatorService.design_start"
```

---

## Task 10: CoordinatorService — design_submit

**Files:**
- Modify: `src/requirement_workflow_v12/coordinator_service.py`
- Test: `tests/test_coordinator_design.py` (append)

- [ ] **Step 1: Append failing test**

Add to `tests/test_coordinator_design.py`:

```python
def test_design_submit_requires_drafting():
    svc = _make_svc()
    r = Requirement(
        req_id="REQ-X-010", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
        design_status=None,
    )
    svc.requirements[r.req_id] = r
    import pytest
    with pytest.raises(ValueError):
        svc.design_submit(r.req_id, archive_path="design/archive/REQ-X-010_x/",
                          pages_touched=[])


def test_design_submit_transitions_to_submit_pending_review():
    svc = _make_svc()
    r = Requirement(
        req_id="REQ-X-011", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
        design_status=DesignStatus.DRAFTING,
    )
    svc.requirements[r.req_id] = r
    out = svc.design_submit(
        r.req_id,
        archive_path="design/archive/REQ-X-011_foo/",
        pages_touched=[{"display_name": "Upload", "action": "new"}],
    )
    assert out.design_status is DesignStatus.SUBMIT_PENDING_REVIEW
    assert out.pending_design_handoff is not None
    assert out.pending_design_handoff["archive_path"] == "design/archive/REQ-X-011_foo/"
    assert out.pending_design_handoff["pages_touched"] == [
        {"display_name": "Upload", "action": "new"}
    ]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_coordinator_design.py -v
```
Expected: FAIL on new cases.

- [ ] **Step 3: Add `design_submit`**

After `design_start`, add:

```python
    def design_submit(
        self,
        req_id: str,
        *,
        archive_path: str,
        pages_touched: list[dict],
    ) -> "Requirement":
        from .plan_state_machine import DesignEvent, apply_design_event
        r = self.requirements[req_id]
        decision = apply_design_event(r.design_status, DesignEvent.DESIGN_SUBMIT)
        if not decision.allowed:
            raise ValueError(decision.message)

        r.pending_design_handoff = {
            "archive_path": archive_path,
            "pages_touched": list(pages_touched),
            "submitted_at": datetime.now(timezone.utc).isoformat(),
        }

        prev = r.design_status
        self._hooks.fire_exit(prev, r)
        r.design_status = decision.next_status
        self._hooks.fire_enter(r.design_status, r)
        return r
```

(If `datetime` / `timezone` are not imported at the top of `coordinator_service.py`, add `from datetime import datetime, timezone`.)

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m pytest tests/test_coordinator_design.py -v
```
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/coordinator_service.py tests/test_coordinator_design.py
git commit -m "feat(design-phase): add CoordinatorService.design_submit"
```

---

## Task 11: CoordinatorService — design_final_approve + design_final_reject

**Files:**
- Modify: `src/requirement_workflow_v12/coordinator_service.py`
- Test: `tests/test_coordinator_design.py` (append)

- [ ] **Step 1: Append failing tests**

```python
def test_design_final_approve_transitions_to_ready_and_unlocks_plan():
    svc = _make_svc()
    r = Requirement(
        req_id="REQ-X-020", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
        design_status=DesignStatus.SUBMIT_PENDING_REVIEW,
        pending_design_handoff={
            "archive_path": "design/archive/REQ-X-020_x/",
            "pages_touched": [],
            "submitted_at": "2026-04-23T00:00:00+00:00",
        },
    )
    svc.requirements[r.req_id] = r
    out = svc.design_final_approve(r.req_id, approved_by="tech-lead-1")
    assert out.design_status is DesignStatus.READY
    assert out.design_precondition_met is True
    assert out.pending_design_handoff is None     # cleared after approval
    assert out.design_archive_path == "design/archive/REQ-X-020_x/"


def test_design_final_reject_returns_to_drafting():
    svc = _make_svc()
    r = Requirement(
        req_id="REQ-X-021", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
        design_status=DesignStatus.SUBMIT_PENDING_REVIEW,
        pending_design_handoff={
            "archive_path": "design/archive/REQ-X-021_x/",
            "pages_touched": [],
            "submitted_at": "2026-04-23T00:00:00+00:00",
        },
    )
    svc.requirements[r.req_id] = r
    out = svc.design_final_reject(r.req_id, reason="配色偏差")
    assert out.design_status is DesignStatus.DRAFTING
    assert out.design_precondition_met is False
    # handoff kept for reference; reason recorded
    assert out.pending_design_handoff is not None
    assert out.pending_design_handoff["reject_reason"] == "配色偏差"
```

- [ ] **Step 2: Run test**

Expected: FAIL.

- [ ] **Step 3: Add the two methods**

After `design_submit`, add:

```python
    def design_final_approve(
        self, req_id: str, *, approved_by: str = "",
    ) -> "Requirement":
        from .plan_state_machine import DesignEvent, apply_design_event
        r = self.requirements[req_id]
        decision = apply_design_event(r.design_status, DesignEvent.DESIGN_FINAL_APPROVE)
        if not decision.allowed:
            raise ValueError(decision.message)

        handoff = r.pending_design_handoff or {}
        r.design_archive_path = handoff.get("archive_path", "")

        prev = r.design_status
        self._hooks.fire_exit(prev, r)
        r.design_status = decision.next_status
        r.design_precondition_met = True
        r.pending_design_handoff = None    # cleared; now archived
        self._hooks.fire_enter(r.design_status, r)
        LOGGER.info(
            "design_final_approve req_id=%s approved_by=%s archive=%s",
            req_id, approved_by, r.design_archive_path,
        )
        return r

    def design_final_reject(
        self, req_id: str, *, reason: str = "",
    ) -> "Requirement":
        from .plan_state_machine import DesignEvent, apply_design_event
        r = self.requirements[req_id]
        decision = apply_design_event(r.design_status, DesignEvent.DESIGN_FINAL_REJECT)
        if not decision.allowed:
            raise ValueError(decision.message)

        handoff = r.pending_design_handoff or {}
        handoff["reject_reason"] = reason
        r.pending_design_handoff = handoff

        prev = r.design_status
        self._hooks.fire_exit(prev, r)
        r.design_status = decision.next_status
        r.design_precondition_met = False
        self._hooks.fire_enter(r.design_status, r)
        LOGGER.info("design_final_reject req_id=%s reason=%s", req_id, reason)
        return r
```

- [ ] **Step 4: Run test**

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/coordinator_service.py tests/test_coordinator_design.py
git commit -m "feat(design-phase): add design_final_approve and design_final_reject"
```

---

## Task 12: Wire design_start into approve_requirement

**Files:**
- Modify: `src/requirement_workflow_v12/service_app.py` (the service layer that calls `approve_requirement`)
- Test: `tests/test_design_auto_start_on_approve.py` (new)

**Context**: The design spec §4.2 says `DESIGN_START` fires automatically on `approve_requirement` when `needs_ui=true`. The wiring lives in `service_app.py` (where cards / flow decisions happen), not in the pure `CoordinatorService`. Look at `service_app.py:872` — existing `approve_requirement` post-hook already creates the design system doc for first `needs_ui=true` REQ; we add the `design_start` dispatch alongside.

- [ ] **Step 1: Write the failing test**

Create `tests/test_design_auto_start_on_approve.py`:

```python
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.models import Requirement, WorkflowStatus
from requirement_workflow_v12.plan_state_machine import DesignStatus


def test_approve_triggers_design_start_when_needs_ui(tmp_path: Path):
    # Minimal smoke test: instantiate app with mocks, call approve path, assert design_start called
    from requirement_workflow_v12.service_app import CoordinatorRuntimeApp
    app = MagicMock(spec=CoordinatorRuntimeApp)
    app.service = MagicMock()
    app.service.requirements = {}
    app.gateway = MagicMock()
    created_doc = MagicMock(document_id="d-1", document_url="https://feishu/d/1")
    app.gateway.create_design_document.return_value = created_doc

    r = Requirement(
        req_id="REQ-X-001", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
    )
    app.service.requirements[r.req_id] = r

    from requirement_workflow_v12.service_app import dispatch_design_start_if_needed
    dispatch_design_start_if_needed(app, r)

    app.gateway.create_design_document.assert_called_once_with(r)
    app.service.design_start.assert_called_once_with(
        r.req_id, design_doc_id="d-1", design_doc_url="https://feishu/d/1",
    )


def test_approve_skips_design_start_when_needs_ui_false():
    from requirement_workflow_v12.service_app import (
        CoordinatorRuntimeApp, dispatch_design_start_if_needed,
    )
    app = MagicMock(spec=CoordinatorRuntimeApp)
    app.gateway = MagicMock()
    r = Requirement(
        req_id="REQ-X-002", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=False,
    )
    dispatch_design_start_if_needed(app, r)
    app.gateway.create_design_document.assert_not_called()
```

- [ ] **Step 2: Run test**

Expected: FAIL — `dispatch_design_start_if_needed` not defined.

- [ ] **Step 3: Add dispatch helper to `service_app.py`**

Near the top-level functions section of `service_app.py` (outside the class, mirror where `_normalize_form_value` etc live), add:

```python
def dispatch_design_start_if_needed(app: "CoordinatorRuntimeApp", requirement) -> None:
    """Called from approve_requirement post-hook. Creates Feishu design docx and
    calls service.design_start. No-op when needs_ui=False."""
    if not requirement.needs_ui:
        return
    try:
        created = app.gateway.create_design_document(requirement)
    except Exception as exc:
        LOGGER.warning(
            "create_design_document failed req_id=%s: %s", requirement.req_id, exc,
        )
        return
    try:
        app.service.design_start(
            requirement.req_id,
            design_doc_id=created.document_id,
            design_doc_url=created.document_url,
        )
    except Exception as exc:
        LOGGER.warning(
            "design_start failed req_id=%s: %s", requirement.req_id, exc,
        )
```

Then wire it into the existing `approve_requirement` post-hook in `service_app.py` around line 871-882 (where `create_design_system_document` is called). Add, **inside the existing `if approved and requirement.status == WorkflowStatus.APPROVED and requirement.needs_ui:` block**, after the design-system-doc creation:

```python
            dispatch_design_start_if_needed(self, requirement)
```

- [ ] **Step 4: Run test**

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/service_app.py tests/test_design_auto_start_on_approve.py
git commit -m "feat(design-phase): auto-dispatch design_start on approve_requirement"
```

---

## Task 13: HTTP endpoint — GET /queries/openclaw/design-context/<req>

**Files:**
- Modify: `src/requirement_workflow_v12/service_app.py` (add handler + route dispatch)
- Test: `tests/test_design_endpoint_service_app.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_design_endpoint_service_app.py`:

```python
import sys
from pathlib import Path
from unittest.mock import MagicMock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.service_app import CoordinatorRuntimeApp
from requirement_workflow_v12.models import Requirement, WorkflowStatus
from requirement_workflow_v12.plan_state_machine import DesignStatus


def _app_with_req(req: Requirement, cfg=None) -> CoordinatorRuntimeApp:
    app = CoordinatorRuntimeApp.__new__(CoordinatorRuntimeApp)
    app.service = MagicMock()
    app.service.requirements = {req.req_id: req}
    app.service.project_configs = {req.project: cfg} if cfg else {}
    app.gateway = MagicMock()
    # Inject DesignContextBuilder
    from requirement_workflow_v12.design_context import DesignContextBuilder
    app._design_context_builder = DesignContextBuilder(app.service)
    return app


def _cfg():
    cfg = MagicMock()
    cfg.tech_stack = {"frontend": "Vite+React"}
    cfg.category = "enterprise-app"
    cfg.template_version = "v1"
    cfg.claude_design_project_url = "https://claude.ai/design/p/xyz"
    cfg.frontend_subpath = "src/x_webapp"
    cfg.architecture_doc_url = ""
    cfg.github_repo_url = ""
    return cfg


def test_design_context_endpoint_returns_200_with_payload():
    r = Requirement(
        req_id="REQ-X-001", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
        design_status=DesignStatus.DRAFTING,
        design_doc_id="d-1", design_doc_url="https://feishu/d/1",
    )
    app = _app_with_req(r, _cfg())
    status, body = app.handle_openclaw_design_context_query("REQ-X-001")
    assert status == 200
    assert body["req_id"] == "REQ-X-001"
    assert body["claude_design_project_url"] == "https://claude.ai/design/p/xyz"


def test_design_context_endpoint_returns_404_for_unknown_req():
    app = _app_with_req(Requirement(
        req_id="REQ-X-999", name="n", project="X", summary="s", creator="c",
    ), _cfg())
    status, body = app.handle_openclaw_design_context_query("REQ-NOT-EXIST")
    assert status == 404


def test_design_context_endpoint_returns_409_on_gate_failure():
    r = Requirement(
        req_id="REQ-X-002", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.CREATED,
    )
    app = _app_with_req(r, _cfg())
    status, body = app.handle_openclaw_design_context_query("REQ-X-002")
    assert status == 409
```

- [ ] **Step 2: Run test**

Expected: FAIL (method doesn't exist).

- [ ] **Step 3: Add handler and route dispatch**

In `service_app.py`:

1. In `__init__` of `CoordinatorRuntimeApp`, alongside `self._plan_context_builder = PlanContextBuilder(...)`, add:
   ```python
   from .design_context import DesignContextBuilder
   self._design_context_builder = DesignContextBuilder(self.service)
   ```

2. Add the handler method (mirror `handle_openclaw_plan_context_query`):
   ```python
   def handle_openclaw_design_context_query(
       self, req_id: str,
   ) -> tuple[int, dict]:
       from .design_context import (
           DesignContextGateError, DesignContextMisconfigured,
       )
       r = self.service.requirements.get(req_id)
       if r is None:
           return 404, {"error": "not_found", "req_id": req_id}
       try:
           ctx = self._design_context_builder.build(req_id)
           return 200, ctx
       except DesignContextGateError as exc:
           return 409, {"error": "gate_failed", "message": str(exc)}
       except DesignContextMisconfigured as exc:
           return 409, {"error": "misconfigured", "message": str(exc)}
       except Exception as exc:  # pragma: no cover
           LOGGER.exception("design-context failed req_id=%s", req_id)
           return 500, {"error": "design_context_failed", "message": str(exc)}
   ```

3. Route dispatch: find the router block that matches `/queries/openclaw/plan-context/` (around line 262). Below the plan-context branches, add:
   ```python
   elif self.path.startswith("/queries/openclaw/design-context/"):
       req_id = self.path[len("/queries/openclaw/design-context/"):]
       status, payload = app.handle_openclaw_design_context_query(req_id)
       # (reuse the JSON response writer used by plan-context)
   ```
   (Match the exact response-writing pattern already used by plan-context in lines ~287-292.)

- [ ] **Step 4: Run test**

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/service_app.py tests/test_design_endpoint_service_app.py
git commit -m "feat(design-phase): add GET /queries/openclaw/design-context/<req> endpoint"
```

---

## Task 14: HTTP endpoint — POST /openclaw/design-callback

**Files:**
- Modify: `src/requirement_workflow_v12/service_app.py`
- Test: `tests/test_design_endpoint_service_app.py` (append)

- [ ] **Step 1: Append failing tests**

```python
def test_design_callback_design_brief_submit_caches_on_requirement():
    r = Requirement(
        req_id="REQ-X-030", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
        design_status=DesignStatus.DRAFTING,
    )
    app = _app_with_req(r, _cfg())

    body = {
        "req_id": "REQ-X-030",
        "event": "design_brief_submit",
        "payload": {
            "brief_yaml_frontmatter": "schema_version: '1.0'\nreq_id: REQ-X-030\n",
            "brief_markdown_body": "# Brief\n...",
        },
    }
    status, resp = app.handle_openclaw_design_callback(body)
    assert status == 200
    assert r.pending_design_brief is not None
    assert r.pending_design_brief["brief_yaml_frontmatter"].startswith("schema_version")


def test_design_callback_unknown_event_returns_400():
    r = Requirement(
        req_id="REQ-X-031", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
        design_status=DesignStatus.DRAFTING,
    )
    app = _app_with_req(r, _cfg())
    status, resp = app.handle_openclaw_design_callback({
        "req_id": "REQ-X-031", "event": "unknown_foo", "payload": {},
    })
    assert status == 400
```

- [ ] **Step 2: Run test — expect FAIL**

- [ ] **Step 3: Add handler**

Mirror `handle_openclaw_plan_callback` in `service_app.py:1220-1276`. Add method:

```python
    def handle_openclaw_design_callback(
        self, body: dict,
    ) -> tuple[int, dict]:
        req_id = body.get("req_id", "")
        event = body.get("event", "")
        payload = body.get("payload") or {}

        r = self.service.requirements.get(req_id)
        if r is None:
            return 404, {"error": "not_found", "req_id": req_id}

        try:
            if event == "design_brief_submit":
                if r.design_status != DesignStatus.DRAFTING:
                    return 409, {
                        "error": "invalid_state",
                        "message": f"design_brief_submit requires design_status=DRAFTING, got {r.design_status.value if r.design_status else 'None'}",
                    }
                r.pending_design_brief = {
                    "brief_yaml_frontmatter": payload.get("brief_yaml_frontmatter", ""),
                    "brief_markdown_body": payload.get("brief_markdown_body", ""),
                    "submitted_at": utc_now().isoformat(),
                }
                self._save_state()
                # Optional: mirror Brief into Feishu design docx
                if r.design_doc_id and payload.get("brief_markdown_body"):
                    try:
                        self.gateway.write_document_text(
                            r.design_doc_id, payload.get("brief_markdown_body", ""),
                        )
                    except Exception as exc:
                        LOGGER.warning(
                            "mirror design brief to feishu failed req=%s: %s",
                            req_id, exc,
                        )
                # Push "设计启动卡" to project group / DM
                try:
                    self._dispatch_transition_notifications(
                        r, trigger="design_brief_ready",
                    )
                except Exception:
                    LOGGER.exception("design brief card dispatch failed req=%s", req_id)
                return 200, {"req_id": req_id, "design_status": r.design_status.value}
            return 400, {"error": "unknown_event", "event": event}
        except Exception as exc:  # pragma: no cover
            LOGGER.exception("design-callback failed req_id=%s event=%s", req_id, event)
            return 500, {"error": "design_callback_failed", "message": str(exc)}
```

Add route dispatch alongside the plan-callback route (around line 294):

```python
elif self.path == "/openclaw/design-callback":
    body_json = json.loads(raw_body.decode("utf-8") or "{}")
    status, payload = app.handle_openclaw_design_callback(body_json)
    # (write response using existing pattern)
```

(**Note**: v1 does not enforce OpenClaw HMAC auth on this endpoint to keep parity with `plan-callback` which is unauthenticated per current code. Add auth only if existing plan-callback gets it.)

- [ ] **Step 4: Run test — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/service_app.py tests/test_design_endpoint_service_app.py
git commit -m "feat(design-phase): add POST /openclaw/design-callback endpoint"
```

---

## Task 15: Card handler — /cards/design-upload-bundle (full intake)

**Files:**
- Modify: `src/requirement_workflow_v12/service_app.py` (card action dispatcher)
- Test: `tests/test_design_endpoint_service_app.py` (append)

- [ ] **Step 1: Append failing test**

```python
def test_design_upload_bundle_action_intakes_and_submits(tmp_path: Path, monkeypatch):
    r = Requirement(
        req_id="REQ-X-040", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
        design_status=DesignStatus.DRAFTING,
    )
    app = _app_with_req(r, _cfg())
    app.archive_root = tmp_path / "design" / "archive"
    app.archive_root.mkdir(parents=True)

    # Stage a "downloaded" zip by copying the fixture
    fixture = Path(__file__).parent / "fixtures" / "design" / "handoff_sample.zip"
    app.gateway.download_card_attachment = MagicMock(
        side_effect=lambda *, file_key, file_token, dest_path: (
            dest_path.write_bytes(fixture.read_bytes()) or dest_path
        ),
    )
    app.service.design_submit = MagicMock(return_value=r)

    value = {
        "req_id": "REQ-X-040",
        "file_key": "fk-1", "file_token": "ft-1",
    }
    operator = {"operator_id": {"user_id": "u1"}}
    status, resp = app._handle_design_upload_bundle_action(value, operator)
    assert status == 200
    app.gateway.download_card_attachment.assert_called_once()
    app.service.design_submit.assert_called_once()
    kwargs = app.service.design_submit.call_args.kwargs
    assert kwargs["archive_path"].startswith("design/archive/REQ-X-040_")
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Add handler**

Add `_handle_design_upload_bundle_action` near the other card handlers (search `send_plan_author_start` in `service_app.py:1576` for context; add in the same dispatch block):

```python
    def _handle_design_upload_bundle_action(
        self, value: dict, operator: dict,
    ) -> tuple[int, dict]:
        req_id = value.get("req_id", "")
        file_key = value.get("file_key", "")
        file_token = value.get("file_token", "")
        if not (req_id and file_key and file_token):
            return 200, {"toast": {"type": "error", "content": "缺少上传参数。"}}

        r = self.service.requirements.get(req_id)
        if r is None:
            return 200, {"toast": {"type": "error", "content": f"未知需求：{req_id}。"}}
        if r.design_status != DesignStatus.DRAFTING:
            return 200, {"toast": {
                "type": "error",
                "content": f"当前设计状态不允许上传：{r.design_status.value if r.design_status else 'None'}",
            }}

        import tempfile
        from .design_intake import DesignIntake, IntakeError
        tmp_dir = Path(tempfile.mkdtemp(prefix="design-handoff-"))
        zip_tmp = tmp_dir / f"{req_id}.zip"
        try:
            self.gateway.download_card_attachment(
                file_key=file_key, file_token=file_token, dest_path=zip_tmp,
            )
        except Exception as exc:
            LOGGER.warning("download_card_attachment failed req=%s: %s", req_id, exc)
            return 200, {"toast": {"type": "error", "content": "下载附件失败。"}}

        slug = self._build_design_slug(r)
        try:
            result = DesignIntake().intake(
                zip_path=zip_tmp,
                req_id=req_id,
                slug=slug,
                archive_root=self.archive_root,
            )
        except IntakeError as exc:
            LOGGER.warning("design intake failed req=%s: %s", req_id, exc)
            return 200, {"toast": {"type": "error", "content": f"解析 handoff 失败：{exc}"}}

        pages_touched = [{"display_name": p, "action": "new"} for p in result.pages_hint]

        try:
            self.service.design_submit(
                req_id,
                archive_path=f"design/archive/{result.archive_dir.name}/",
                pages_touched=pages_touched,
            )
        except Exception as exc:
            LOGGER.exception("design_submit failed req=%s: %s", req_id, exc)
            return 200, {"toast": {"type": "error", "content": f"状态机提交失败：{exc}"}}

        self._save_state()
        try:
            self._dispatch_transition_notifications(r, trigger="design_submit_pending_review")
        except Exception:
            LOGGER.exception("design submit card dispatch failed req=%s", req_id)

        return 200, {"toast": {"type": "success", "content": "Handoff 已接收，等待终审。"}}

    def _build_design_slug(self, requirement) -> str:
        """REQ-X-040 + 'n' (truncated) → 'n' or fallback 'handoff'."""
        import re
        name = requirement.name or "handoff"
        slug = re.sub(r"[^a-zA-Z0-9\-]+", "-", name).strip("-").lower()[:30]
        return slug or "handoff"
```

In the existing `_handle_card_action_payload` dispatcher, add routing for `action_name == "design_upload_bundle"`:

```python
        if action_name == "design_upload_bundle":
            return self._handle_design_upload_bundle_action(value, operator)
```

In `__init__` of `CoordinatorRuntimeApp`, add `self.archive_root` default:

```python
self.archive_root = Path(os.environ.get("DESIGN_ARCHIVE_ROOT", "design/archive"))
self.archive_root.mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/service_app.py tests/test_design_endpoint_service_app.py
git commit -m "feat(design-phase): add /cards/design-upload-bundle card action"
```

---

## Task 16: Card handlers — design_final_approve / design_final_reject

**Files:**
- Modify: `src/requirement_workflow_v12/service_app.py`
- Test: `tests/test_design_endpoint_service_app.py` (append)

- [ ] **Step 1: Append failing tests**

```python
def test_design_final_approve_action_promotes_req_to_ready():
    r = Requirement(
        req_id="REQ-X-050", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
        design_status=DesignStatus.SUBMIT_PENDING_REVIEW,
        pending_design_handoff={
            "archive_path": "design/archive/REQ-X-050_x/",
            "pages_touched": [],
            "submitted_at": "2026-04-23T00:00:00+00:00",
        },
    )
    app = _app_with_req(r, _cfg())
    # Stub design_final_approve to mutate the in-memory r
    def fake_approve(req_id, *, approved_by=""):
        r.design_status = DesignStatus.READY
        r.design_precondition_met = True
        return r
    app.service.design_final_approve = MagicMock(side_effect=fake_approve)

    status, resp = app._handle_card_action_payload({
        "action": {"value": {"action": "design_final_approve", "req_id": "REQ-X-050"}},
        "operator": {"operator_id": {"user_id": "u-tech-lead"}},
    })
    app.service.design_final_approve.assert_called_once()


def test_design_final_reject_action_returns_to_drafting():
    r = Requirement(
        req_id="REQ-X-051", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
        design_status=DesignStatus.SUBMIT_PENDING_REVIEW,
    )
    app = _app_with_req(r, _cfg())
    app.service.design_final_reject = MagicMock(return_value=r)

    status, resp = app._handle_card_action_payload({
        "action": {"value": {
            "action": "design_final_reject", "req_id": "REQ-X-051",
            "reason": "配色不对",
        }},
        "operator": {"operator_id": {"user_id": "u"}},
    })
    app.service.design_final_reject.assert_called_once_with(
        "REQ-X-051", reason="配色不对",
    )
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Add handlers + dispatcher branches**

In `_handle_card_action_payload`, add:

```python
        if action_name == "design_final_approve":
            req_id = value.get("req_id", "")
            if not req_id:
                return 200, {"toast": {"type": "error", "content": "缺少需求ID。"}}
            user_id = operator.get("operator_id", {}).get("user_id", "")
            try:
                self.service.design_final_approve(req_id, approved_by=user_id)
            except ValueError as exc:
                return 200, {"toast": {"type": "error", "content": str(exc)}}
            self._save_state()
            try:
                r = self.service.requirements.get(req_id)
                if r is not None:
                    self._dispatch_transition_notifications(r, trigger="design_ready")
            except Exception:
                LOGGER.exception("design ready card dispatch failed req=%s", req_id)
            return 200, {"toast": {"type": "success", "content": "设计通过，Plan 阶段已解锁。"}}

        if action_name == "design_final_reject":
            req_id = value.get("req_id", "")
            reason = value.get("reason", "")
            if not req_id:
                return 200, {"toast": {"type": "error", "content": "缺少需求ID。"}}
            try:
                self.service.design_final_reject(req_id, reason=reason)
            except ValueError as exc:
                return 200, {"toast": {"type": "error", "content": str(exc)}}
            self._save_state()
            return 200, {"toast": {"type": "success", "content": "已打回设计。"}}
```

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/service_app.py tests/test_design_endpoint_service_app.py
git commit -m "feat(design-phase): add design_final_approve/reject card actions"
```

---

## Task 17: Plan-context & spec-context inject design_artifact

**Files:**
- Modify: `src/requirement_workflow_v12/plan_context.py`
- Modify: `src/requirement_workflow_v12/spec_context.py`
- Test: `tests/test_plan_context.py` (extend) + `tests/test_spec_context.py` (extend or create)

- [ ] **Step 1: Append failing test to `tests/test_plan_context.py`**

```python
def test_plan_context_includes_design_artifact_when_ready():
    from requirement_workflow_v12.models import Requirement, WorkflowStatus
    from requirement_workflow_v12.plan_state_machine import DesignStatus
    from requirement_workflow_v12.plan_context import PlanContextBuilder

    r = Requirement(
        req_id="REQ-X-001", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
        design_status=DesignStatus.READY,
        design_archive_path="design/archive/REQ-X-001_foo/",
    )
    svc = MagicMock()
    svc.requirements = {r.req_id: r}
    cfg = MagicMock()
    cfg.tech_stack = {}; cfg.category = "enterprise-app"; cfg.template_version = "v1"
    cfg.architecture_doc_url = ""; cfg.github_repo_url = ""
    svc.project_configs = {r.project: cfg}

    ctx = PlanContextBuilder(svc).build("REQ-X-001")
    assert ctx["design_artifact"]["archive_path"] == "design/archive/REQ-X-001_foo/"
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Extend `plan_context.py`**

In `PlanContextBuilder.build`, append to the returned dict:

```python
            "design_artifact": self._design_artifact_slice(r),
```

Add method:

```python
    def _design_artifact_slice(self, r) -> dict:
        return {
            "archive_path": r.design_archive_path,
            "needs_ui": r.needs_ui,
            "design_status": r.design_status.value if r.design_status else None,
        }
```

- [ ] **Step 4: Mirror in `spec_context.py`** — add the same field to its returned context dict (match the existing spec-context schema; look at `spec_context.py` to find the shape).

- [ ] **Step 5: Run — expect PASS**

- [ ] **Step 6: Commit**

```bash
git add src/requirement_workflow_v12/plan_context.py src/requirement_workflow_v12/spec_context.py tests/test_plan_context.py
git commit -m "feat(design-phase): inject design_artifact into plan/spec context"
```

---

## Task 18: Hook wiring — configure_design_hooks + READY sync

**Files:**
- Modify: `src/requirement_workflow_v12/service_app.py` (hook configuration in bootstrap)
- Test: `tests/test_design_ready_hook.py` (new)

- [ ] **Step 1: Write the failing test**

```python
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.models import Requirement, WorkflowStatus
from requirement_workflow_v12.plan_state_machine import DesignStatus


def test_on_enter_ready_invokes_syncer(tmp_path):
    from requirement_workflow_v12.service_app import (
        configure_design_hooks, CoordinatorRuntimeApp,
    )
    app = MagicMock(spec=CoordinatorRuntimeApp)
    app.service = MagicMock()
    app._design_syncer = MagicMock()
    app._design_syncer.sync.return_value = MagicMock(commit_sha="c1")
    app.project_repo_for_project = MagicMock(return_value="org/repo")
    app.project_repo_root = tmp_path
    (tmp_path / "design").mkdir()
    (tmp_path / "design" / "PAGES.yaml").write_text("schema_version: '1.0'\npages: []\n")
    (tmp_path / "design" / "INDEX.md").write_text("# Design Handoff Index\n")
    (tmp_path / "design" / "archive" / "REQ-X-001_x").mkdir(parents=True)
    (tmp_path / "design" / "archive" / "REQ-X-001_x" / "MANIFEST.md").write_text("m")

    r = Requirement(
        req_id="REQ-X-001", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
        design_status=DesignStatus.READY,
        design_archive_path="design/archive/REQ-X-001_x/",
        pending_design_handoff={"archive_path": "design/archive/REQ-X-001_x/",
                                "pages_touched": [], "submitted_at": "t"},
    )
    hooks = MagicMock()
    configure_design_hooks(hooks, app)

    # Invoke the registered on_enter(READY) callback
    calls = [c for c in hooks.on_enter.call_args_list
             if c.args[0] is DesignStatus.READY]
    assert calls, "on_enter(READY) should be registered"
    callback = calls[0].args[1]
    callback(r)

    app._design_syncer.sync.assert_called_once()
```

- [ ] **Step 2: Run — expect FAIL** (no `configure_design_hooks`).

- [ ] **Step 3: Add `configure_design_hooks` + `_design_syncer` instantiation**

In `service_app.py`, add top-level function:

```python
def configure_design_hooks(hooks, app: "CoordinatorRuntimeApp") -> None:
    """Register design-layer state hooks on a StateTransitionHooks registry."""
    from .plan_state_machine import DesignStatus

    def _on_enter_drafting(r):
        # coordinator-side: Start card is pushed by dispatch_design_start_if_needed;
        # this hook is intentionally a no-op to keep the state machine decoupled.
        pass

    def _on_enter_submit_pending_review(r):
        try:
            app._dispatch_transition_notifications(r, trigger="design_submit_pending_review")
        except Exception:
            LOGGER.exception("design SUBMIT_PENDING_REVIEW card dispatch failed req=%s", r.req_id)

    def _on_enter_ready(r):
        handoff = r.pending_design_handoff or {}
        project_repo = app.project_repo_for_project(r.project)
        archive_dir = Path(app.project_repo_root) / r.design_archive_path.rstrip("/")
        registry = Path(app.project_repo_root) / "design" / "PAGES.yaml"
        index = Path(app.project_repo_root) / "design" / "INDEX.md"
        try:
            result = app._design_syncer.sync(
                project_repo=project_repo,
                req_id=r.req_id,
                slug=archive_dir.name.split("_", 1)[1] if "_" in archive_dir.name else "x",
                archive_dir=archive_dir,
                pages_registry_path=registry,
                index_path=index,
                pages_touched=handoff.get("pages_touched", []),
            )
            r.design_github_revision = result.commit_sha
        except Exception:
            LOGGER.exception("design READY sync failed req=%s", r.req_id)
            raise

    hooks.on_enter(DesignStatus.DRAFTING,              _on_enter_drafting)
    hooks.on_enter(DesignStatus.SUBMIT_PENDING_REVIEW, _on_enter_submit_pending_review)
    hooks.on_enter(DesignStatus.READY,                 _on_enter_ready)
```

In `CoordinatorRuntimeApp.__init__`, instantiate syncer and wire hooks:

```python
from .design_syncer import DesignSyncer
self._design_syncer = DesignSyncer(self._project_repo_gateway)
# ... existing hook registration ...
configure_design_hooks(self.service._hooks, self)
```

Ensure `project_repo_for_project(project)` and `project_repo_root` exist on `CoordinatorRuntimeApp`. If not, search for existing equivalents (grep `project_repo` in service_app.py) and reuse; otherwise add a thin helper reading from ProjectConfig.

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add src/requirement_workflow_v12/service_app.py tests/test_design_ready_hook.py
git commit -m "feat(design-phase): wire on_enter(READY) to DesignSyncer"
```

---

## Task 19: End-to-end happy path integration test

**Files:**
- Test: `tests/test_design_phase_e2e.py` (new)

- [ ] **Step 1: Write E2E test**

```python
import sys
from pathlib import Path
from unittest.mock import MagicMock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.models import Requirement, WorkflowStatus
from requirement_workflow_v12.plan_state_machine import DesignStatus


FIXTURE_ZIP = Path(__file__).parent / "fixtures" / "design" / "handoff_sample.zip"


def test_happy_path_draft_to_ready(tmp_path: Path) -> None:
    """Covers: APPROVED + needs_ui → DRAFT → zip upload → SUBMIT_PENDING →
    final approve → READY → design_precondition_met=True."""
    from requirement_workflow_v12.coordinator_service import CoordinatorService
    from requirement_workflow_v12.state_machine import StateTransitionHooks

    # Build a minimal CoordinatorService (no real gateways)
    hooks = StateTransitionHooks()
    svc = CoordinatorService.__new__(CoordinatorService)
    svc.requirements = {}
    svc.project_configs = {}
    svc._hooks = hooks

    r = Requirement(
        req_id="REQ-E2E-001", name="测试", project="P", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
    )
    svc.requirements[r.req_id] = r

    # Step 1: design_start
    svc.design_start(r.req_id, design_doc_id="d", design_doc_url="u")
    assert r.design_status is DesignStatus.DRAFTING

    # Step 2: intake a real bundle via DesignIntake
    from requirement_workflow_v12.design_intake import DesignIntake
    archive_root = tmp_path / "design" / "archive"
    archive_root.mkdir(parents=True)
    res = DesignIntake().intake(
        zip_path=FIXTURE_ZIP, req_id=r.req_id, slug="x", archive_root=archive_root,
    )
    assert (res.archive_dir / "MANIFEST.md").exists()

    # Step 3: design_submit
    svc.design_submit(
        r.req_id,
        archive_path=f"design/archive/{res.archive_dir.name}/",
        pages_touched=[{"display_name": p, "action": "new"} for p in res.pages_hint],
    )
    assert r.design_status is DesignStatus.SUBMIT_PENDING_REVIEW

    # Step 4: final approve
    svc.design_final_approve(r.req_id, approved_by="lead")
    assert r.design_status is DesignStatus.READY
    assert r.design_precondition_met is True
    assert r.design_archive_path.startswith("design/archive/REQ-E2E-001_")
```

- [ ] **Step 2: Run — expect PASS (all prior tasks must have shipped)**

```bash
python3 -m pytest tests/test_design_phase_e2e.py -v
```

- [ ] **Step 3: Run full suite**

```bash
python3 -m unittest discover -s tests -v 2>&1 | tail -15
```
Expected: `OK` at tail.

- [ ] **Step 4: Commit**

```bash
git add tests/test_design_phase_e2e.py
git commit -m "test(design-phase): add end-to-end happy-path integration test"
```

---

## Task 20: Update README with design phase note

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add to README "当前已实现" section**

Find the bullet list in `README.md` after "当前已实现". Add:

```markdown
- design 阶段三态状态机：DRAFTING → SUBMIT_PENDING_REVIEW → READY（当 needs_ui=true）
- OpenClaw skill `design-brief-author` 单轮上下文端点：`GET /queries/openclaw/design-context/<req>`
- Handoff bundle 上传入口：飞书卡片 `design_upload_bundle` action
- Design 阶段产物归档：`design/archive/REQ-*_<slug>/` 含 bundle.zip + extracted + MANIFEST.md + BRIEF.md
- Plan 层 precondition 解除：`design_precondition_met=True` 且 `PlanStatus == null/DRAFTING` 时允许进入 PLAN_DRAFTING
```

Add to "仍待补齐":

```markdown
- design-author / design-brief-author OpenClaw skill 真实落地（SKILL.md + 联调）
- Bootstrap 层对 design 目录样板文件的 populate（见 `docs/superpowers/specs/2026-04-23-design-phase-design.md` 附录 A）
- Claude Design → GitHub 仓库绑定子步骤
- 目标仓库前端脚手架（Vite + React + TS + Tailwind + shadcn/ui）
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs(readme): note design-phase implementation status"
```

---

## Self-Review

After Task 20 ships, run this checklist:

1. **Spec coverage**:
   - [ ] §2 state machine → Task 1 ✓
   - [ ] §4.1 Step 0 Bootstrap → Appendix only (out of scope, noted) ✓
   - [ ] §4.2 Step 1 DESIGN_START + skill dispatch → Tasks 9, 12 ✓
   - [ ] §4.3 Step 2 Claude Design work → no code (pure human step) ✓
   - [ ] §4.4 Step 3 intake → Tasks 5, 15 ✓
   - [ ] §4.5 Step 4 final approval → Tasks 11, 16, 18 ✓
   - [ ] §4.6 Step 5 downstream consumption → Task 17 ✓
   - [ ] §5.1 BRIEF.md schema → Task 14 (handling/caching); full schema lives in skill repo
   - [ ] §5.2 PAGES.yaml → Task 6 ✓
   - [ ] §5.3 MANIFEST.md → Task 5 ✓
   - [ ] §5.4 INDEX.md → Task 6 ✓
   - [ ] §5.5 intake implementation notes → Task 5 ✓
   - [ ] §6 directory structure → Tasks 5, 6 (create those dirs) ✓
   - [ ] §7 endpoints/events/cards → Tasks 13-16, 18 ✓
   - [ ] §8 skill contract → Task 14 (callback handler; SKILL.md out of scope) ✓
   - [ ] §9 tech stack → documented in spec, no code change ✓
   - [ ] §10 Requirement model fields → Tasks 2, 3 ✓
   - [ ] §11 failure matrix → covered by per-Task error paths ✓

2. **Placeholder scan**: searched for "TODO", "TBD", "implement later", "similar to Task N" in this plan; none found (the `待填` in Task 5 MANIFEST template is sample content the reviewer fills in, not a plan placeholder).

3. **Type consistency**: `DesignStatus.SUBMIT_PENDING_REVIEW` used in Tasks 1, 10, 11, 16; `DesignEvent.DESIGN_FINAL_APPROVE` in Tasks 1, 11, 16 — consistent. `Requirement.pending_design_handoff` / `pending_design_brief` naming consistent throughout Tasks 2, 3, 10, 11, 14, 18.

Self-review PASS.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-23-design-phase-plan.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per Task, review between tasks, fast iteration with guardrails. Best for the 20-task scope here.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batched with checkpoints.

**Which approach?**
