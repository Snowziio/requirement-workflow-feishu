from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
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
