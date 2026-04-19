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
