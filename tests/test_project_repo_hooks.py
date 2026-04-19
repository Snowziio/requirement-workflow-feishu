"""Unit tests for the StateTransitionHooks registry.

Covers registration order, enter/exit separation, no-op on unregistered
statuses, and fail-fast observability contract for hook exceptions.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

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


# ── Task 4.2: exception observability contract ──────────────────────────

import logging


def test_hook_exception_is_logged_with_required_fields(caplog):
    hooks = StateTransitionHooks()

    def boom(_req):
        raise ProjectRepoError("disk full", recoverable=False)

    hooks.on_enter(SpecStatus.TRANSFORMING, boom)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(ProjectRepoError) as exc_info:
            hooks.fire_enter(SpecStatus.TRANSFORMING, _req("REQ-X-9"))

    assert "disk full" in str(exc_info.value)

    text = caplog.text
    assert "hook_exception" in text
    assert "transition=enter" in text
    assert "TRANSFORMING" in text
    assert "REQ-X-9" in text
    assert "boom" in text
    assert "ProjectRepoError" in text
    assert "disk full" in text


def test_hook_exception_is_fail_fast():
    hooks = StateTransitionHooks()
    calls: list[str] = []

    def first(_r):
        raise ProjectRepoError("halt")

    def second(_r):
        calls.append("should-not-run")

    hooks.on_enter(SpecStatus.TRANSFORMING, first)
    hooks.on_enter(SpecStatus.TRANSFORMING, second)

    with pytest.raises(ProjectRepoError):
        hooks.fire_enter(SpecStatus.TRANSFORMING, _req())

    assert calls == []


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


def test_hook_exception_propagates_for_plan_status():
    hooks = StateTransitionHooks()

    def boom(_r):
        raise ProjectRepoError("bad")

    hooks.on_enter(PlanStatus.READY, boom)

    with pytest.raises(ProjectRepoError):
        hooks.fire_enter(PlanStatus.READY, _req("REQ-Q-1"))
