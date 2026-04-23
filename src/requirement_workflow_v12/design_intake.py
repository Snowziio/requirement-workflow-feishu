"""Design handoff bundle intake: unzip, normalize filenames, generate MANIFEST."""
from __future__ import annotations

import hashlib
import shutil
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


class IntakeError(Exception):
    """Raised when a handoff zip cannot be processed."""


@dataclass
class IntakeResult:
    archive_dir: Path
    export_type: str              # "pure_export" | "anchor_bump"
    anchors_in_bundle: list[dict] # [{folder_name, tree_sha256}]
    pages_hint: list[str]         # display_name candidates from src/*.jsx
    inner_readme_excerpt: str


class DesignIntake:
    """Stateless handler: accepts a zip + meta, writes archive dir + MANIFEST."""

    def intake(
        self, *, zip_path: Path, req_id: str, slug: str, archive_root: Path,
        known_anchor_hashes: set | None = None,
    ) -> IntakeResult:
        archive_dir = archive_root / f"{req_id}_{slug}"
        archive_dir.mkdir(parents=True, exist_ok=False)

        try:
            shutil.copy2(zip_path, archive_dir / "bundle.zip")
            extracted = archive_dir / "extracted"
            extracted.mkdir()
            self._extract_with_cn_repair(zip_path, extracted)
        except Exception as exc:
            shutil.rmtree(archive_dir, ignore_errors=True)
            raise IntakeError(f"intake failed for {req_id}: {exc}") from exc

        anchors = self._enumerate_anchors(extracted)
        known = known_anchor_hashes or set()
        new_anchors = [a for a in anchors if a["tree_sha256"] not in known]
        export_type = "anchor_bump" if new_anchors else "pure_export"

        pages_hint = self._extract_page_hints(extracted)
        inner_readme_excerpt = self._extract_inner_readme(extracted, limit=500)

        manifest = self._render_manifest(
            req_id=req_id, export_type=export_type,
            anchors=anchors, pages_hint=pages_hint,
            inner_readme_excerpt=inner_readme_excerpt,
        )
        (archive_dir / "MANIFEST.md").write_text(manifest, encoding="utf-8")

        return IntakeResult(
            archive_dir=archive_dir, export_type=export_type,
            anchors_in_bundle=anchors, pages_hint=pages_hint,
            inner_readme_excerpt=inner_readme_excerpt,
        )

    def _extract_with_cn_repair(self, zip_path: Path, dest: Path) -> None:
        with zipfile.ZipFile(zip_path) as zf:
            for info in zf.infolist():
                try:
                    info.filename = info.filename.encode("cp437").decode("utf-8")
                except (UnicodeEncodeError, UnicodeDecodeError):
                    pass  # already UTF-8 or plain ASCII
                zf.extract(info, dest)

    def _enumerate_anchors(self, extracted: Path) -> list[dict]:
        anchors = []
        for candidate in extracted.rglob("design_handoff_*"):
            if not candidate.is_dir():
                continue
            tree_hash = self._hash_tree(candidate)
            anchors.append({
                "folder_name": candidate.name,
                "tree_sha256": tree_hash,
            })
        return anchors

    def _hash_tree(self, root: Path) -> str:
        h = hashlib.sha256()
        for f in sorted(p for p in root.rglob("*") if p.is_file()):
            h.update(str(f.relative_to(root)).encode("utf-8"))
            h.update(b"\0")
            h.update(f.read_bytes())
        return h.hexdigest()

    def _extract_page_hints(self, extracted: Path) -> list[str]:
        """Heuristic: bare project/src/*.jsx filenames (capitalized) are page candidates.
        Skips common shared files (App, Shell, primitives, data) that aren't pages.
        """
        hints: list[str] = []
        skip = {"App", "Shell", "primitives", "data"}
        for proj in extracted.rglob("project"):
            if not proj.is_dir():
                continue
            src = proj / "src"
            if src.is_dir():
                for jsx in sorted(src.glob("*.jsx")):
                    name = jsx.stem
                    if name[:1].isupper() and name not in skip:
                        hints.append(name)
                break
        return hints

    def _extract_inner_readme(self, extracted: Path, *, limit: int) -> str:
        for readme in extracted.rglob("design_handoff_*/README.md"):
            text = readme.read_text(encoding="utf-8", errors="replace")
            return text[:limit]
        return ""

    def _render_manifest(
        self, *, req_id: str, export_type: str, anchors: list[dict],
        pages_hint: list[str], inner_readme_excerpt: str,
    ) -> str:
        lines = ["---"]
        lines.append(f"req_id: {req_id}")
        lines.append(f"archived_at: \"{datetime.now(timezone.utc).isoformat()}\"")
        lines.append("archived_by: coordinator-service")
        lines.append(f"export_type: {export_type}")
        lines.append("anchors_in_bundle:")
        for a in anchors:
            lines.append(f"  - folder_name: {a['folder_name']}")
            lines.append(f"    tree_sha256: {a['tree_sha256']}")
        lines.append("pages_hint:")
        for p in pages_hint:
            lines.append(f"  - {p}")
        lines.append("bundle_inner_readme_excerpt: |")
        for line in inner_readme_excerpt.splitlines():
            lines.append(f"  {line}")
        lines.append("---")
        lines.append("")
        lines.append(f"# {req_id} Design Handoff Summary")
        lines.append("")
        lines.append("## Pages Hint (from bundle src/*.jsx)")
        for p in pages_hint:
            lines.append(f"- {p}")
        lines.append("")
        lines.append("## Reviewer Notes (D-DESIGN-2 终审人填写)")
        lines.append("_待填_")
        lines.append("")
        return "\n".join(lines)
