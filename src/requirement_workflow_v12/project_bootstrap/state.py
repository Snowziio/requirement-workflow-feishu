"""Bootstrap log helpers: append entries + read last-completed step."""
from __future__ import annotations

from datetime import datetime, timezone

from .types import BootstrapStep


def append_log_entry(
    log: list[dict],
    *,
    step: BootstrapStep,
    status: str,
    error_msg: str | None = None,
) -> list[dict]:
    """Return a new log list with an entry appended. Does not mutate input."""
    entry = {
        "step": int(step),
        "step_name": step.name,
        "ts": datetime.now(timezone.utc).isoformat(),
        "status": status,
    }
    if error_msg is not None:
        entry["error_msg"] = error_msg
    return list(log) + [entry]


def last_completed_step(log: list[dict]) -> int:
    """Return the largest step number with status=='ok'; 0 if none."""
    completed = [e["step"] for e in log if e.get("status") == "ok"]
    return max(completed) if completed else 0
