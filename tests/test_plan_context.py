import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest
from unittest.mock import MagicMock

from requirement_workflow_v12.coordinator_service import CoordinatorService
from requirement_workflow_v12.models import Requirement, WorkflowStatus
from requirement_workflow_v12.plan_context import (
    PlanContextBuilder, PlanContextGateError,
)
from requirement_workflow_v12.plan_state_machine import PlanStatus
from requirement_workflow_v12.project_config import ProjectConfig


def _req(svc, req_id="REQ-P-1"):
    r = Requirement(
        req_id=req_id, name="n", project="P", summary="s", creator="c",
    )
    r.status = WorkflowStatus.APPROVED
    svc.requirements[req_id] = r
    svc.project_configs["P"] = ProjectConfig(
        category="web", template_version="v1",
        architecture_doc_id="doc-a", architecture_doc_url="https://x",
        tech_stack={"backend": "python"}, github_repo_url="owner/repo",
    )
    return r


def test_plan_context_returns_expected_fields_when_plan_none():
    svc = CoordinatorService()
    r = _req(svc)
    builder = PlanContextBuilder(service=svc)

    ctx = builder.build(r.req_id)

    assert ctx["req_id"] == "REQ-P-1"
    assert ctx["project"] == "P"
    assert ctx["needs_ui"] is False
    assert ctx["tech_stack"] == {"backend": "python"}
    assert ctx["project_repo"] == "owner/repo"
    assert ctx["architecture_doc_url"] == "https://x"


def test_plan_context_rejected_when_not_approved():
    svc = CoordinatorService()
    r = _req(svc)
    r.status = WorkflowStatus.DRAFTING
    builder = PlanContextBuilder(service=svc)
    with pytest.raises(PlanContextGateError):
        builder.build(r.req_id)


def test_plan_context_rejected_when_already_ready():
    svc = CoordinatorService()
    r = _req(svc)
    r.plan_status = PlanStatus.READY
    builder = PlanContextBuilder(service=svc)
    with pytest.raises(PlanContextGateError):
        builder.build(r.req_id)


def test_plan_context_allowed_when_drafting():
    svc = CoordinatorService()
    r = _req(svc)
    r.plan_status = PlanStatus.DRAFTING
    builder = PlanContextBuilder(service=svc)
    ctx = builder.build(r.req_id)
    assert ctx["req_id"] == "REQ-P-1"


def test_plan_context_allowed_when_needs_ui_true_and_no_design():
    """MVP (2026-04-21): plan_start no longer couples to needs_ui/design_status;
    plan_context must stay consistent with that — it should NOT gate on design."""
    svc = CoordinatorService()
    r = _req(svc)
    r.needs_ui = True
    # design_status stays None
    builder = PlanContextBuilder(service=svc)
    ctx = builder.build(r.req_id)
    assert ctx["req_id"] == "REQ-P-1"
    assert ctx["needs_ui"] is True


def test_plan_context_exposes_feishu_plan_doc_fields():
    """Time-phased SOT (2026-04-21): plan-author MUST see the Feishu plan docx
    URL/id so it can read/write the construction-phase SOT. Without these
    fields the agent falls back to 'where is my plan doc?' confusion."""
    svc = CoordinatorService()
    r = _req(svc)
    r.plan_status = PlanStatus.DRAFTING
    r.plan_doc_id = "docx-plan-abc"
    r.plan_doc_url = "https://my.feishu.cn/docx/docx-plan-abc"
    builder = PlanContextBuilder(service=svc)

    ctx = builder.build(r.req_id)

    assert ctx["plan_doc_id"] == "docx-plan-abc"
    assert ctx["plan_doc_url"] == "https://my.feishu.cn/docx/docx-plan-abc"


def test_plan_context_plan_doc_fields_default_empty_string():
    """Backward-compatible default: for REQs whose plan docx was never
    created (legacy or misconfigured folder_token), plan-author receives
    empty strings rather than missing keys, so jq/JSON access stays safe."""
    svc = CoordinatorService()
    r = _req(svc)
    # plan_doc_id / plan_doc_url never set
    builder = PlanContextBuilder(service=svc)

    ctx = builder.build(r.req_id)

    assert ctx["plan_doc_id"] == ""
    assert ctx["plan_doc_url"] == ""


def test_plan_context_includes_design_artifact():
    """Plan context must include design_artifact slice for plan-author consumption."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

    from unittest.mock import MagicMock
    from requirement_workflow_v12.models import Requirement, WorkflowStatus
    from requirement_workflow_v12.plan_state_machine import DesignStatus
    from requirement_workflow_v12.plan_context import PlanContextBuilder

    r = Requirement(
        req_id="REQ-X-001", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
        design_status=DesignStatus.READY,
        design_archive_path="design/archive/REQ-X-001_foo/",
    )
    svc = MagicMock()
    svc.requirements = {r.req_id: r}
    cfg = MagicMock()
    cfg.tech_stack = {}; cfg.category = "enterprise-app"
    cfg.template_version = "v1"
    cfg.architecture_doc_url = ""; cfg.github_repo_url = ""
    svc.project_configs = {r.project: cfg}

    ctx = PlanContextBuilder(svc).build("REQ-X-001")
    assert "design_artifact" in ctx
    assert ctx["design_artifact"]["archive_path"] == "design/archive/REQ-X-001_foo/"
    assert ctx["design_artifact"]["needs_ui"] is True
    assert ctx["design_artifact"]["design_status"] == "DESIGN_READY"


def test_plan_context_design_artifact_when_needs_ui_false():
    """Non-UI REQ still gets a design_artifact slice, but with empty/None fields."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

    from unittest.mock import MagicMock
    from requirement_workflow_v12.models import Requirement, WorkflowStatus
    from requirement_workflow_v12.plan_context import PlanContextBuilder

    r = Requirement(
        req_id="REQ-X-002", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=False,
    )
    svc = MagicMock()
    svc.requirements = {r.req_id: r}
    cfg = MagicMock()
    cfg.tech_stack = {}; cfg.category = "enterprise-app"
    cfg.template_version = "v1"
    cfg.architecture_doc_url = ""; cfg.github_repo_url = ""
    svc.project_configs = {r.project: cfg}

    ctx = PlanContextBuilder(svc).build("REQ-X-002")
    assert ctx["design_artifact"]["needs_ui"] is False
    assert ctx["design_artifact"]["archive_path"] == ""
    assert ctx["design_artifact"]["design_status"] is None


# ── §6.2.8 Design → Plan alignment contract: enriched design_artifact ──


def _full_design_ready_req(project="P", req_id="REQ-D-001"):
    """Build a Requirement in APPROVED + DesignStatus.READY with all design fields populated."""
    from requirement_workflow_v12.plan_state_machine import DesignStatus
    r = Requirement(
        req_id=req_id, name="n", project=project, summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
        design_status=DesignStatus.READY,
        design_doc_id="docx-brief-xyz",
        design_doc_url="https://my.feishu.cn/docx/docx-brief-xyz",
        design_archive_path=f"design/archive/{req_id}_foo/",
        design_github_revision="8f0e2bad1234567890abcdef",
        design_precondition_met=True,
        design_pages=[{"display_name": "DashboardPage", "action": "new"}],
    )
    return r


def test_design_artifact_exposes_github_revision_for_pinned_reads():
    """plan-author needs github_revision to fetch archive files at a stable
    commit SHA — without it, it would be reading moving main HEAD."""
    svc = CoordinatorService()
    r = _full_design_ready_req(project="P")
    svc.requirements[r.req_id] = r
    svc.project_configs["P"] = ProjectConfig(
        category="web", template_version="v1",
        architecture_doc_id="a", architecture_doc_url="https://x",
        github_repo_url="owner/repo",
    )

    ctx = PlanContextBuilder(service=svc).build(r.req_id)
    assert ctx["design_artifact"]["github_revision"] == "8f0e2bad1234567890abcdef"


def test_design_artifact_exposes_feishu_brief_url_for_human_review():
    """Feishu Brief doc URL lets plan-author point the user back to the
    source visual context (and lets the agent use feishu_fetch_doc on it)."""
    svc = CoordinatorService()
    r = _full_design_ready_req(project="P")
    svc.requirements[r.req_id] = r
    svc.project_configs["P"] = ProjectConfig(
        category="web", template_version="v1",
        architecture_doc_id="a", architecture_doc_url="https://x",
        github_repo_url="owner/repo",
    )

    ctx = PlanContextBuilder(service=svc).build(r.req_id)
    assert ctx["design_artifact"]["feishu_brief_url"] == "https://my.feishu.cn/docx/docx-brief-xyz"


def test_design_artifact_exposes_design_system_doc_url_from_project_config():
    """DS doc URL is per-project; Coordinator renders it from ProjectConfig's
    design_system_doc_id + the configured feishu_base_url."""
    svc = CoordinatorService()
    r = _full_design_ready_req(project="P")
    svc.requirements[r.req_id] = r
    svc.project_configs["P"] = ProjectConfig(
        category="web", template_version="v1",
        architecture_doc_id="a", architecture_doc_url="https://x",
        github_repo_url="owner/repo",
        design_system_doc_id="docx-ds-abc",
    )

    ctx = PlanContextBuilder(
        service=svc, feishu_base_url="https://staging.feishu.cn",
    ).build(r.req_id)
    assert ctx["design_artifact"]["design_system_doc_url"] == "https://staging.feishu.cn/docx/docx-ds-abc"


def test_design_artifact_design_system_url_empty_when_ds_not_configured():
    """Project without a DS (e.g. non-UI project or first-UI REQ before DS
    creation) gets empty string, not 'null' or missing key."""
    svc = CoordinatorService()
    r = _full_design_ready_req(project="P")
    svc.requirements[r.req_id] = r
    svc.project_configs["P"] = ProjectConfig(
        category="web", template_version="v1",
        architecture_doc_id="a", architecture_doc_url="https://x",
        github_repo_url="owner/repo",
        # design_system_doc_id deliberately None
    )

    ctx = PlanContextBuilder(service=svc).build(r.req_id)
    assert ctx["design_artifact"]["design_system_doc_url"] == ""


def test_design_artifact_exposes_pages_list():
    """Pages touched by this REQ are surfaced so plan-author can target
    them directly instead of guessing from archive tree."""
    svc = CoordinatorService()
    r = _full_design_ready_req(project="P")
    svc.requirements[r.req_id] = r
    svc.project_configs["P"] = ProjectConfig(
        category="web", template_version="v1",
        architecture_doc_id="a", architecture_doc_url="https://x",
        github_repo_url="owner/repo",
    )

    ctx = PlanContextBuilder(service=svc).build(r.req_id)
    pages = ctx["design_artifact"]["pages"]
    assert len(pages) == 1
    assert pages[0]["display_name"] == "DashboardPage"


def test_design_artifact_all_six_fields_present_for_alignment_contract():
    """§6.2.8 contract: design_artifact must expose at least six fields so
    plan-author can act on the handoff. Regression guard against future
    field removal."""
    svc = CoordinatorService()
    r = _full_design_ready_req(project="P")
    svc.requirements[r.req_id] = r
    svc.project_configs["P"] = ProjectConfig(
        category="web", template_version="v1",
        architecture_doc_id="a", architecture_doc_url="https://x",
        github_repo_url="owner/repo",
        design_system_doc_id="ds-id",
    )

    art = PlanContextBuilder(service=svc).build(r.req_id)["design_artifact"]
    required_keys = {
        "archive_path", "needs_ui", "design_status",
        "github_revision", "feishu_brief_url",
        "design_system_doc_url", "pages",
    }
    missing = required_keys - set(art.keys())
    assert not missing, f"design_artifact missing keys: {missing}"


def test_design_final_approve_persists_pages_into_design_pages_field():
    """§6.2.8 implementation: design_final_approve moves pages_touched out of
    the ephemeral pending_design_handoff (cleared on approve) into the
    persistent design_pages field, so plan-author reads them post-approval.
    """
    from requirement_workflow_v12.plan_state_machine import DesignStatus
    svc = CoordinatorService()
    r = Requirement(
        req_id="REQ-D-777", name="n", project="P", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
        design_status=DesignStatus.SUBMIT_PENDING_REVIEW,
        design_doc_url="u", design_doc_id="d",
        design_archive_path="design/archive/REQ-D-777_foo/",
        pending_design_handoff={
            "archive_path": "design/archive/REQ-D-777_foo/",
            "pages_touched": [
                {"display_name": "Dashboard", "action": "new"},
                {"display_name": "Profile", "action": "new"},
            ],
        },
    )
    svc.requirements[r.req_id] = r
    svc.project_configs["P"] = ProjectConfig(
        category="web", template_version="v1",
        architecture_doc_id="a", architecture_doc_url="u",
        claude_design_project_url="https://claude.ai/design/p/x",
    )

    svc.design_final_approve(r.req_id, approved_by="u1")

    refreshed = svc.get_requirement(r.req_id)
    assert refreshed.design_status == DesignStatus.READY
    # pending cleared
    assert refreshed.pending_design_handoff is None
    # pages preserved
    assert len(refreshed.design_pages) == 2
    names = [p["display_name"] for p in refreshed.design_pages]
    assert "Dashboard" in names and "Profile" in names


def test_design_restart_clears_design_pages():
    """Cascading reset semantics: /design restart must wipe design_pages
    along with other design fields, so the next handoff starts clean."""
    from requirement_workflow_v12.plan_state_machine import DesignStatus
    svc = CoordinatorService()
    r = Requirement(
        req_id="REQ-D-888", name="n", project="P", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
        design_status=DesignStatus.READY,
        design_pages=[{"display_name": "Old", "action": "new"}],
    )
    svc.requirements[r.req_id] = r

    svc.design_restart(r.req_id)

    refreshed = svc.get_requirement(r.req_id)
    assert refreshed.design_pages == []


# ── §6.2.8 inline_files: coordinator-side fileserver for design archive ──


def _make_archive(archive_root, req_id, slug, files_dict):
    """Create a fake archive dir at {archive_root}/{req_id}_{slug}/ with files_dict."""
    d = archive_root / f"{req_id}_{slug}"
    d.mkdir(parents=True)
    for rel_path, content in files_dict.items():
        f = d / rel_path
        f.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            f.write_bytes(content)
        else:
            f.write_text(content, encoding="utf-8")
    return d


def test_design_artifact_inline_files_reads_archive_contents(tmp_path):
    """Plan-author runs without GitHub creds and can't clone private repos;
    plan-context must inline the archive files so plan-author sees them."""
    from requirement_workflow_v12.plan_state_machine import DesignStatus
    svc = CoordinatorService()
    r = Requirement(
        req_id="REQ-Z-001", name="n", project="P", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
        design_status=DesignStatus.READY,
        design_archive_path="design/archive/REQ-Z-001_foo/",
    )
    svc.requirements[r.req_id] = r
    svc.project_configs["P"] = ProjectConfig(
        category="web", template_version="v1",
        architecture_doc_id="a", architecture_doc_url="u",
        github_repo_url="owner/repo",
    )

    _make_archive(tmp_path, "REQ-Z-001", "foo", {
        "MANIFEST.md": "# MANIFEST\npages_hint: [DashboardPage]\n",
        "extracted/project/src/DashboardPage.jsx": "export function Dashboard() { return <div/>; }",
        "extracted/project/styles/tokens.css": "--color-primary: #f00;\n",
    })

    ctx = PlanContextBuilder(
        service=svc, archive_root=tmp_path,
    ).build(r.req_id)

    inline = ctx["design_artifact"]["inline_files"]
    paths = sorted(f["path"] for f in inline)
    assert paths == [
        "MANIFEST.md",
        "extracted/project/src/DashboardPage.jsx",
        "extracted/project/styles/tokens.css",
    ]
    contents = {f["path"]: f["content"] for f in inline}
    assert "pages_hint" in contents["MANIFEST.md"]
    assert "Dashboard" in contents["extracted/project/src/DashboardPage.jsx"]
    assert "--color-primary" in contents["extracted/project/styles/tokens.css"]


def test_design_artifact_inline_files_skips_bundle_zip(tmp_path):
    """bundle.zip is binary and opaque; no value to plan-author. Must skip."""
    from requirement_workflow_v12.plan_state_machine import DesignStatus
    svc = CoordinatorService()
    r = Requirement(
        req_id="REQ-Z-002", name="n", project="P", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
        design_status=DesignStatus.READY,
        design_archive_path="design/archive/REQ-Z-002_foo/",
    )
    svc.requirements[r.req_id] = r
    svc.project_configs["P"] = ProjectConfig(
        category="web", template_version="v1",
        architecture_doc_id="a", architecture_doc_url="u",
    )
    _make_archive(tmp_path, "REQ-Z-002", "foo", {
        "MANIFEST.md": "# m",
        "bundle.zip": b"\x00\x01\x02\x03PK\x03\x04",  # fake zip bytes
    })

    ctx = PlanContextBuilder(service=svc, archive_root=tmp_path).build(r.req_id)
    paths = [f["path"] for f in ctx["design_artifact"]["inline_files"]]
    assert "bundle.zip" not in paths
    assert "MANIFEST.md" in paths


def test_design_artifact_inline_files_skips_binary_files(tmp_path):
    """logo.svg, .png, any file that doesn't decode as UTF-8 should be skipped."""
    from requirement_workflow_v12.plan_state_machine import DesignStatus
    svc = CoordinatorService()
    r = Requirement(
        req_id="REQ-Z-003", name="n", project="P", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
        design_status=DesignStatus.READY,
        design_archive_path="design/archive/REQ-Z-003_foo/",
    )
    svc.requirements[r.req_id] = r
    svc.project_configs["P"] = ProjectConfig(
        category="web", template_version="v1",
        architecture_doc_id="a", architecture_doc_url="u",
    )
    _make_archive(tmp_path, "REQ-Z-003", "foo", {
        "MANIFEST.md": "text",
        "extracted/logo.png": b"\x89PNG\r\n\x1a\n" + b"\xff" * 100,
    })

    ctx = PlanContextBuilder(service=svc, archive_root=tmp_path).build(r.req_id)
    paths = [f["path"] for f in ctx["design_artifact"]["inline_files"]]
    assert "extracted/logo.png" not in paths
    assert "MANIFEST.md" in paths


def test_design_artifact_inline_files_skips_files_over_size_cap(tmp_path):
    """Individual files exceeding MAX_INLINE_FILE_BYTES (100KB) are skipped."""
    from requirement_workflow_v12.plan_state_machine import DesignStatus
    from requirement_workflow_v12.plan_context import MAX_INLINE_FILE_BYTES
    svc = CoordinatorService()
    r = Requirement(
        req_id="REQ-Z-004", name="n", project="P", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
        design_status=DesignStatus.READY,
        design_archive_path="design/archive/REQ-Z-004_foo/",
    )
    svc.requirements[r.req_id] = r
    svc.project_configs["P"] = ProjectConfig(
        category="web", template_version="v1",
        architecture_doc_id="a", architecture_doc_url="u",
    )
    huge = "x" * (MAX_INLINE_FILE_BYTES + 100)
    _make_archive(tmp_path, "REQ-Z-004", "foo", {
        "MANIFEST.md": "small",
        "extracted/huge.jsx": huge,
    })

    ctx = PlanContextBuilder(service=svc, archive_root=tmp_path).build(r.req_id)
    paths = [f["path"] for f in ctx["design_artifact"]["inline_files"]]
    assert "extracted/huge.jsx" not in paths
    assert "MANIFEST.md" in paths


def test_design_artifact_inline_files_empty_when_archive_missing_on_disk(tmp_path):
    """Fresh coordinator container (pre-first-intake) or REQ without design:
    no archive dir on disk → empty list, not error."""
    svc = CoordinatorService()
    r = Requirement(
        req_id="REQ-Z-005", name="n", project="P", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=False,
    )
    svc.requirements[r.req_id] = r
    svc.project_configs["P"] = ProjectConfig(
        category="web", template_version="v1",
        architecture_doc_id="a", architecture_doc_url="u",
    )

    ctx = PlanContextBuilder(service=svc, archive_root=tmp_path).build(r.req_id)
    assert ctx["design_artifact"]["inline_files"] == []


def test_design_artifact_inline_files_ordering_is_stable(tmp_path):
    """Same archive → same file order across calls (sorted lexicographically)."""
    from requirement_workflow_v12.plan_state_machine import DesignStatus
    svc = CoordinatorService()
    r = Requirement(
        req_id="REQ-Z-006", name="n", project="P", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
        design_status=DesignStatus.READY,
        design_archive_path="design/archive/REQ-Z-006_foo/",
    )
    svc.requirements[r.req_id] = r
    svc.project_configs["P"] = ProjectConfig(
        category="web", template_version="v1",
        architecture_doc_id="a", architecture_doc_url="u",
    )
    _make_archive(tmp_path, "REQ-Z-006", "foo", {
        "z.md": "z", "a.md": "a", "m.md": "m",
    })

    builder = PlanContextBuilder(service=svc, archive_root=tmp_path)
    call1 = [f["path"] for f in builder.build(r.req_id)["design_artifact"]["inline_files"]]
    call2 = [f["path"] for f in builder.build(r.req_id)["design_artifact"]["inline_files"]]
    assert call1 == call2
    assert call1 == ["a.md", "m.md", "z.md"]
