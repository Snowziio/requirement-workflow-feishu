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


import datetime as _dt


class SpecTransformOrchestrator:
    """Coordinator-side game runner. Holds in-memory RoundContext per req_id.
    Crash recovery is `/spec restart`; trace is audit-only."""

    def __init__(
        self,
        *,
        gateway,
        registry,
        feishu,
        trace_dir: Path,
        max_rounds: int = 3,
        max_soft_retries: int = 2,
        max_race_retries: int = 3,
    ):
        self._gateway = gateway
        self._registry = registry
        self._feishu = feishu
        self._trace = TraceWriter(trace_dir)
        self._max_rounds = max_rounds
        self._max_soft_retries = max_soft_retries
        self._max_race_retries = max_race_retries
        self._rounds: dict[str, RoundContext] = {}

    async def on_enter_transforming(
        self,
        *,
        req_id: str,
        project_repo: str,
        spec_doc_id: str,
    ) -> TransformContextSnapshot:
        spec_rev = self._feishu.fetch_document_revision(spec_doc_id)
        arch_sha, _ = await self._gateway.fetch_file_sha(
            project_repo, "main", "ARCHITECTURE.yaml",
        )
        registry_sha, registry_text = await self._gateway.fetch_file_sha(
            project_repo, "main", "acm-registry.yaml",
        )
        active = self._registry.parse_active_slice(registry_text)
        snap = TransformContextSnapshot(
            req_id=req_id,
            spec_source_revision=spec_rev,
            architecture_revision=arch_sha,
            acm_registry_revision=registry_sha,
            acm_active_slice=active,
            captured_at=_dt.datetime.now(_dt.timezone.utc).isoformat(),
        )
        self._trace.reset(req_id)
        self._trace.append(req_id, {
            "event": "transform_started",
            "snapshot": {
                "spec_source_revision": snap.spec_source_revision,
                "architecture_revision": snap.architecture_revision,
                "acm_registry_revision": snap.acm_registry_revision,
                "acm_active_slice": snap.acm_active_slice,
            },
        })
        await self._gateway.create_branch(
            project_repo, f"spec/{req_id}", base="main",
        )
        self._rounds[req_id] = RoundContext(snapshot=snap)
        return snap
