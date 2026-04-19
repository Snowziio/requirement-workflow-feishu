from __future__ import annotations

import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator

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
    def __init__(self) -> None:
        self._lock = threading.Lock()

    def parse_active_slice(self, registry_text: str) -> list[str]:
        doc = yaml.safe_load(registry_text) or {}
        entries = doc.get("entries", []) or []
        return [e["ac_id"] for e in entries if e.get("status") == "active"]

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

    @contextmanager
    def write_lock(self) -> Iterator[None]:
        with self._lock:
            yield
