"""Unified dispatcher for project_context_change gate.

Each ``changes[].artifact`` routes to a dedicated executor. MVP
implements the ``architecture`` executor fully; ``environments`` and
``skill_md`` are logged stubs that preserve the original content.
"""
from __future__ import annotations

import logging

from .project_repo.architecture_apply import (
    ArchitectureApplyError,
    apply_architecture_changes,
)


_logger = logging.getLogger(__name__)


class ProjectContextApplyError(ValueError):
    """Raised when a change block is malformed or unroutable."""


def apply_project_context_change(
    *, original_files: dict[str, str], change: dict
) -> dict[str, str]:
    changes = change.get("changes") or []
    updated = dict(original_files)
    arch_changes = []
    for entry in changes:
        artifact = entry.get("artifact")
        if artifact == "architecture":
            arch_changes.append(entry)
        elif artifact == "environments":
            _logger.warning(
                "project_context_change: environments executor is a stub (MVP); ignoring change section_path=%s",
                entry.get("section_path"),
            )
        elif artifact == "skill_md":
            _logger.warning(
                "project_context_change: skill_md executor is a stub (MVP); ignoring change section_path=%s",
                entry.get("section_path"),
            )
        else:
            raise ProjectContextApplyError(f"unknown artifact: {artifact!r}")

    if arch_changes:
        arch_path = "ARCHITECTURE.md"
        arch_text = updated.get(arch_path, "")
        try:
            updated[arch_path] = apply_architecture_changes(arch_text, arch_changes)
        except ArchitectureApplyError as exc:
            raise ProjectContextApplyError(
                f"architecture apply failed: {exc}"
            ) from exc
    return updated
