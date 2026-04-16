from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


def _compute_trace_digest(text: str) -> str:
    """Short audit digest for the per-REQ jsonl trace (sha256 prefix)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


NextAction = Literal[
    "soft_retry_transformer",
    "wake_reviewer",
    "wake_transformer_next_round",
    "wake_transformer_regression_retry",
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
    regression_retry_count: int = 0
    last_transformer_payload: dict | None = None
    last_reviewer_findings: list[dict] = field(default_factory=list)
    last_regression_missing: list[str] = field(default_factory=list)


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

    def has_trace(self, req_id: str) -> bool:
        return self._path(req_id).exists()

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
        max_regression_retries: int = 1,
        on_deadlock=None,
        on_locked=None,
    ):
        self._gateway = gateway
        self._registry = registry
        self._feishu = feishu
        self._trace = TraceWriter(trace_dir)
        self._max_rounds = max_rounds
        self._max_soft_retries = max_soft_retries
        self._max_race_retries = max_race_retries
        self._max_regression_retries = max_regression_retries
        self._on_deadlock_cb = on_deadlock
        self._on_locked_cb = on_locked
        self._rounds: dict[str, RoundContext] = {}

    def archive_trace(
        self, req_id: str, *, suffix: str = "restart",
    ) -> Path | None:
        """Archive the per-REQ trace.jsonl under ``trace_dir/archive/``.

        Returns the archived path, or ``None`` if no trace existed.
        Also drops any in-memory ``RoundContext`` for ``req_id`` so a
        subsequent ``on_enter_transforming`` starts cleanly.
        """
        self._rounds.pop(req_id, None)
        if not self._trace.has_trace(req_id):
            return None
        return self._trace.archive(req_id, suffix=suffix)

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
        owner, repo_name = project_repo.split("/", 1)
        self._gateway.create_branch(
            owner=owner,
            repo=repo_name,
            branch=f"spec/{req_id}",
            from_branch="main",
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
            outcome = self._on_converged(req_id)
            if outcome == "regression_retry":
                return "wake_transformer_regression_retry"
            if outcome == "deadlock":
                return "deadlock"
            return "converged"
        ctx.last_reviewer_findings = findings
        return self._advance_round_or_deadlock(ctx, req_id)

    def _on_converged(self, req_id: str) -> str:
        """Drive ACM patch + regression scan + commit + PR. Returns one of:

        - ``"locked"`` — Spec PR opened, ctx popped, on_locked fired.
        - ``"regression_retry"`` — regression scan missed AC anchors but
          ``regression_retry_count < max_regression_retries``; ctx kept,
          ``last_regression_missing`` populated for caller to feed back to
          the transformer (round保持).
        - ``"deadlock"`` — terminal failure (regression exhausted, github
          commit error, or ACM race giveup); ctx popped, on_deadlock fired.
        """
        from .acm_registry import SupersedeDecl
        from .regression_scan import scan
        import yaml
        ctx = self._rounds[req_id]
        payload = ctx.last_transformer_payload
        project_repo = self._project_repo_for(req_id)

        with self._registry.write_lock():
            committed = False
            for race_attempt in range(self._max_race_retries):
                current_sha, current_doc = self._registry.fetch_snapshot(project_repo)
                ac_doc = yaml.safe_load(payload["ac_schedule_yaml"]) or {}
                new_acs = ac_doc.get("acs", []) or []
                supersedes = [
                    SupersedeDecl(old_ac_id=d["old_ac_id"], by_ac_id=d["by_ac_id"])
                    for d in payload.get("supersedes_decl", [])
                ]
                patched = self._registry.compose_patch(
                    current_doc, new_acs=new_acs,
                    supersedes=supersedes, req_id=req_id,
                )
                active_ids = [e.ac_id for e in patched.entries if e.status == "active"]
                regression = scan(
                    active_ids=active_ids,
                    supersedes_decl=supersedes,
                    harness_files=payload["harness_files"],
                )
                if not regression.passed:
                    if ctx.regression_retry_count < self._max_regression_retries:
                        ctx.regression_retry_count += 1
                        ctx.last_regression_missing = list(regression.missing)
                        self._trace.append(req_id, {
                            "event": "regression_retry",
                            "attempt": ctx.regression_retry_count,
                            "missing": regression.missing,
                        })
                        return "regression_retry"
                    self._trace.append(req_id, {
                        "event": "regression_failed",
                        "reason": "max_regression_retries",
                        "missing": regression.missing,
                    })
                    self._rounds.pop(req_id, None)
                    if self._on_deadlock_cb is not None:
                        self._on_deadlock_cb(req_id, "regression_failed")
                    return "deadlock"

                files = self._compose_pr_files(req_id, payload, patched)
                try:
                    self._gateway.commit_spec_pr_files(
                        project_repo, f"spec/{req_id}",
                        files, f"feat(spec): {req_id}",
                    )
                    committed = True
                    break
                except Exception as exc:
                    if "mismatch" in str(exc).lower() and race_attempt < self._max_race_retries - 1:
                        ctx.race_retry_count += 1
                        self._trace.append(req_id, {
                            "event": "acm_race_retry",
                            "attempt": race_attempt + 1,
                        })
                        continue
                    self._trace.append(req_id, {
                        "event": "github_commit_failed",
                        "error": str(exc),
                    })
                    self._rounds.pop(req_id, None)
                    if self._on_deadlock_cb is not None:
                        self._on_deadlock_cb(req_id, "github_commit_failed")
                    return "deadlock"

            if not committed:
                self._trace.append(req_id, {"event": "acm_race_giveup"})
                self._rounds.pop(req_id, None)
                if self._on_deadlock_cb is not None:
                    self._on_deadlock_cb(req_id, "acm_race_giveup")
                return "deadlock"

        owner, repo_name = project_repo.split("/", 1)
        trace_digest = _compute_trace_digest(self._trace.read_all(req_id))
        source_revision = ctx.snapshot.spec_source_revision
        pr_body = (
            f"Spec PR for {req_id}.\n\n"
            f"spec_source_revision={source_revision} | "
            f"transform_round={ctx.round_index} | "
            f"transform_trace_digest={trace_digest}"
        )
        pr = self._gateway.open_pull_request(
            owner=owner, repo=repo_name,
            head_branch=f"spec/{req_id}", base_branch="main",
            title=f"Spec: {req_id}",
            body=pr_body,
        )
        self._trace.append(req_id, {
            "event": "locked", "pr_url": pr.get("html_url"),
        })
        self._rounds.pop(req_id, None)
        if self._on_locked_cb is not None:
            self._on_locked_cb(
                req_id, pr.get("html_url"),
                source_revision=source_revision,
                trace_digest=trace_digest,
                transform_round=ctx.round_index,
            )
        return "locked"

    def _compose_pr_files(self, req_id, payload, patched_registry) -> dict[str, str]:
        prefix = f"docs/specs/{req_id}"
        files = {
            f"{prefix}/design.md": payload["design_md"],
            f"{prefix}/tasks.md": payload["tasks_md"],
            f"{prefix}/ac-schedule.yaml": payload["ac_schedule_yaml"],
            f"{prefix}/transform_trace.jsonl": self._trace.read_all(req_id),
            "acm-registry.yaml": self._registry.serialize(patched_registry),
        }
        for path, content in payload.get("harness_files", {}).items():
            files[path] = content
        return files

    def _project_repo_for(self, req_id: str) -> str:
        # Default impl; CoordinatorService wiring (Task 28) injects a real resolver.
        raise NotImplementedError("project_repo_for must be set by Coordinator wiring")
