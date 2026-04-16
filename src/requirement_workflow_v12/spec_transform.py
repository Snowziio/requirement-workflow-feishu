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
        on_deadlock=None,
    ):
        self._gateway = gateway
        self._registry = registry
        self._feishu = feishu
        self._trace = TraceWriter(trace_dir)
        self._max_rounds = max_rounds
        self._max_soft_retries = max_soft_retries
        self._max_race_retries = max_race_retries
        self._on_deadlock_cb = on_deadlock
        self._rounds: dict[str, RoundContext] = {}

    def on_enter_transforming(
        self,
        *,
        req_id: str,
        project_repo: str,
        spec_doc_id: str,
    ) -> TransformContextSnapshot:
        spec_rev = self._feishu.fetch_document_revision(spec_doc_id)
        arch_sha, _ = self._gateway.fetch_file_sha(
            project_repo, "main", "ARCHITECTURE.yaml",
        )
        registry_sha, registry_text = self._gateway.fetch_file_sha(
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
        self._gateway.create_branch(
            project_repo, f"spec/{req_id}", base="main",
        )
        self._rounds[req_id] = RoundContext(snapshot=snap)
        return snap

    def handle_transformer_output(
        self, req_id: str, payload: dict,
    ) -> "NextAction":
        from .spec_gate import run_gate
        ctx = self._rounds.get(req_id)
        if ctx is None:
            self._trace.append(req_id, {
                "event": "recovery_deadlock",
                "reason": "no in-memory round context (likely after restart)",
            })
            if self._on_deadlock_cb is not None:
                self._on_deadlock_cb(req_id, "recovery")
            return "deadlock"
        ctx.last_transformer_payload = payload
        result = run_gate(payload, ctx.snapshot)
        if result.passed:
            self._trace.append(req_id, {
                "event": "gate_pass", "round": ctx.round_index,
            })
            return "wake_reviewer"
        if result.has_format_failure and not result.has_semantic_failure:
            if ctx.soft_retry_count < self._max_soft_retries:
                ctx.soft_retry_count += 1
                self._trace.append(req_id, {
                    "event": "soft_retry",
                    "round": ctx.round_index,
                    "retry": ctx.soft_retry_count,
                    "findings": [vars(f) for f in result.findings],
                })
                return "soft_retry_transformer"
            self._trace.append(req_id, {
                "event": "round_used",
                "reason": "format_max",
                "round": ctx.round_index,
            })
        else:
            self._trace.append(req_id, {
                "event": "round_used",
                "reason": "semantic",
                "round": ctx.round_index,
                "findings": [vars(f) for f in result.findings],
            })
        return self._advance_round_or_deadlock(ctx, req_id)

    def _advance_round_or_deadlock(self, ctx: "RoundContext", req_id: str) -> "NextAction":
        if ctx.round_index >= self._max_rounds:
            self._trace.append(req_id, {
                "event": "deadlock", "reason": "max_rounds",
            })
            self._rounds.pop(req_id, None)
            if self._on_deadlock_cb is not None:
                self._on_deadlock_cb(req_id, "max_rounds")
            return "deadlock"
        ctx.round_index += 1
        ctx.soft_retry_count = 0
        return "wake_transformer_next_round"

    def handle_reviewer_verdict(
        self, req_id: str, verdict: str, findings: list[dict],
    ) -> "NextAction":
        ctx = self._rounds.get(req_id)
        if ctx is None:
            self._trace.append(req_id, {
                "event": "recovery_deadlock", "reason": "no round context",
            })
            if self._on_deadlock_cb is not None:
                self._on_deadlock_cb(req_id, "recovery")
            return "deadlock"
        self._trace.append(req_id, {
            "event": "reviewer_verdict",
            "verdict": verdict,
            "findings": findings,
            "round": ctx.round_index,
        })
        if verdict == "converged":
            self._on_converged(req_id)
            return "converged"
        ctx.last_reviewer_findings = findings
        return self._advance_round_or_deadlock(ctx, req_id)

    def _on_converged(self, req_id: str) -> None:
        # Full converged path implemented in S6 (Task 27); placeholder so tests can monkeypatch.
        self._trace.append(req_id, {"event": "converged_placeholder"})
