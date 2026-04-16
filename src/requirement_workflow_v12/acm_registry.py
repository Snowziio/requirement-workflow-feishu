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
    def __init__(self, gateway):
        self._gateway = gateway
        self._lock = threading.Lock()

    def parse_active_slice(self, registry_text: str) -> list[str]:
        doc = yaml.safe_load(registry_text) or {}
        entries = doc.get("entries", []) or []
        return [e["ac_id"] for e in entries if e.get("status") == "active"]
