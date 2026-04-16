"""Regression scan: every active AC must either be anchored in a harness
test (``@pytest.mark.ac('AC-xxx')``) or declared as superseded by a newer
AC. Pure function — no I/O, no state. Callers pass in already-loaded
registry slice and harness file contents.
"""
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
