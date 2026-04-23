"""PLANNING-layer context builder used by plan-author agents.

The ``design_artifact`` slice implements the Coordinator side of the
Design → Plan alignment contract (methodology v3.0 §6.2.8). It gives
plan-author enough pointers to actually read the design output before
identifying decisions, avoiding two failure modes:

- decision duplication: plan-author proposes layout/color/interaction items
  the designer already decided in Claude Design
- decision omission: plan-author doesn't know the UI was designed, so
  plan-level UI-adjacent decisions (data source, routing, framework,
  token translation) never surface

Archive file contents are inlined into the response rather than referenced
by URL because plan-author runs in the OpenClaw gateway sandbox without
GitHub credentials — project repos are typically private and unreachable.
Coordinator has local disk access to the archive (mounted persistent volume)
plus its own GitHub token, so serving the bytes through plan-context is the
cheapest handoff.
"""
from __future__ import annotations

from pathlib import Path

from .models import WorkflowStatus
from .plan_state_machine import PlanStatus


PLAN_CONTEXT_ALLOWED_STATUSES = {None, PlanStatus.DRAFTING}

# Safety caps for design archive inlining. Individual files that exceed
# MAX_INLINE_FILE_BYTES are skipped; once we cross MAX_INLINE_TOTAL_BYTES
# we stop collecting. These limits are generous for Claude Design exports
# (typical full bundle < 100KB) but prevent pathological payloads.
MAX_INLINE_FILE_BYTES = 100 * 1024
MAX_INLINE_TOTAL_BYTES = 400 * 1024


class PlanContextGateError(Exception):
    def __init__(self, message: str, current_status: str) -> None:
        super().__init__(message)
        self.current_status = current_status


class PlanContextMisconfigured(Exception):
    """No ProjectConfig for this project."""


class PlanContextBuilder:
    def __init__(
        self,
        service,
        *,
        feishu_base_url: str = "https://my.feishu.cn",
        archive_root: Path | str | None = None,
    ) -> None:
        self._service = service
        self._feishu_base_url = feishu_base_url.rstrip("/")
        # Directory on coordinator's local disk where design archives live.
        # e.g. /app/design/archive on staging. Falls back to the relative
        # default so test harnesses don't need to set it.
        self._archive_root = (
            Path(archive_root) if archive_root else Path("design/archive")
        )

    def build(self, req_id: str) -> dict:
        r = self._service.requirements.get(req_id)
        if r is None:
            raise ValueError(f"未知需求：{req_id}")
        if (
            r.status != WorkflowStatus.APPROVED
            or r.plan_status not in PLAN_CONTEXT_ALLOWED_STATUSES
        ):
            plan_label = r.plan_status.value if r.plan_status else "None"
            raise PlanContextGateError(
                f"当前状态 status={r.status.value} plan_status={plan_label} "
                "不允许获取 plan-context",
                current_status=r.status.value,
            )
        cfg = self._service.project_configs.get(r.project)
        if cfg is None:
            raise PlanContextMisconfigured(f"项目 {r.project} 未初始化")

        return {
            "req_id": r.req_id,
            "project": r.project,
            "requirement_document_url": r.document_url,
            "needs_ui": r.needs_ui,
            "tech_stack": dict(cfg.tech_stack),
            "category": cfg.category,
            "template_version": cfg.template_version,
            "architecture_doc_url": cfg.architecture_doc_url,
            "project_repo": cfg.github_repo_url,
            "plan_doc_id": r.plan_doc_id,
            "plan_doc_url": r.plan_doc_url,
            "plan_outline": list(r.plan_outline),
            "plan_decisions_wip": list(r.plan_decisions_wip),
            "plan_phase": r.plan_phase.value if r.plan_phase else None,
            "design_artifact": self._design_artifact_slice(r, cfg),
        }

    def _design_artifact_slice(self, r, cfg) -> dict:
        """Build the design_artifact slice per §6.2.8.

        For needs_ui=true + DesignStatus=READY requirements, plan-author uses
        these pointers to (a) read the archive at the pinned commit SHA via
        GitHub, (b) consult the Feishu Brief + DS doc for visual context, and
        (c) enumerate which pages this REQ touched — so it can skip
        design-decided items and surface design-open boundary decisions.
        """
        ds_doc_id = getattr(cfg, "design_system_doc_id", None)
        design_system_doc_url = (
            f"{self._feishu_base_url}/docx/{ds_doc_id}"
            if ds_doc_id else ""
        )
        return {
            "archive_path": getattr(r, "design_archive_path", "") or "",
            "needs_ui": getattr(r, "needs_ui", False),
            "design_status": r.design_status.value if getattr(r, "design_status", None) else None,
            "github_revision": getattr(r, "design_github_revision", "") or "",
            "feishu_brief_url": getattr(r, "design_doc_url", "") or "",
            "design_system_doc_url": design_system_doc_url,
            "pages": list(getattr(r, "design_pages", []) or []),
            "inline_files": self._read_archive_inline_files(r),
        }

    def _read_archive_inline_files(self, r) -> list[dict]:
        """Read text files from the REQ's on-disk archive for inlining.

        Returns ``[{"path": rel_path, "content": text}, ...]`` where rel_path
        is relative to the archive dir (e.g. "MANIFEST.md" or
        "extracted/vc-assistant-test/project/src/DashboardPage.jsx").

        Skips: binary files (including bundle.zip), individual files over
        MAX_INLINE_FILE_BYTES, and stops when cumulative payload reaches
        MAX_INLINE_TOTAL_BYTES. Order is lexicographic so output is stable
        across calls.
        """
        arch_rel = getattr(r, "design_archive_path", "") or ""
        if not arch_rel:
            return []
        arch_dir_name = Path(arch_rel.rstrip("/")).name
        archive_dir = self._archive_root / arch_dir_name
        if not archive_dir.is_dir():
            return []
        files: list[dict] = []
        total = 0
        for f in sorted(archive_dir.rglob("*")):
            if not f.is_file():
                continue
            if f.name == "bundle.zip":
                continue
            try:
                size = f.stat().st_size
            except OSError:
                continue
            if size > MAX_INLINE_FILE_BYTES:
                continue
            try:
                text = f.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            entry_bytes = len(text.encode("utf-8"))
            if total + entry_bytes > MAX_INLINE_TOTAL_BYTES:
                break
            files.append({
                "path": f.relative_to(archive_dir).as_posix(),
                "content": text,
            })
            total += entry_bytes
        return files
