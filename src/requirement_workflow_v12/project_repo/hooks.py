"""State-transition hook registry.

``on_enter(status, fn)`` fires after a state machine lands the new
status; ``on_exit(status, fn)`` fires before it. Callbacks take a single
``Requirement`` argument.

Contract: a hook raising propagates — remaining hooks for that transition
do NOT run (fail-fast). Before re-raising, the exception is logged with
structured fields so operators can trace which hook blew up and why.
"""
from __future__ import annotations

import logging
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

    def _fire(
        self,
        transition: str,
        fns,
        status: "SpecStatus",
        req: "Requirement",
    ) -> None:
        for fn in fns:
            try:
                fn(req)
            except Exception as exc:
                _logger.exception(
                    "hook_exception event=hook_exception transition=%s "
                    "status=%s req_id=%s hook_name=%s exception=%s",
                    transition,
                    status.name if hasattr(status, "name") else status,
                    req.req_id,
                    getattr(fn, "__qualname__", repr(fn)),
                    f"{type(exc).__name__}: {exc}",
                )
                raise
