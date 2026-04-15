import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.project_config import ProjectConfig
from requirement_workflow_v12.store import JsonStateStore


def test_store_round_trips_project_config():
    cfg = ProjectConfig(
        category="public-web-site",
        template_version="public-web-site.v1",
        architecture_doc_id="doc_pw",
        architecture_doc_url="https://feishu.example/docx/doc_pw",
        tech_stack={"language": "python"},
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        store = JsonStateStore(f"{tmpdir}/state.json")
        store.save_snapshot({}, {}, {}, {"MyProj": cfg})
        _, _, _, loaded = store.load_snapshot()
        assert loaded["MyProj"].category == "public-web-site"
        assert loaded["MyProj"].architecture_doc_id == "doc_pw"
        assert loaded["MyProj"].tech_stack == {"language": "python"}


def test_store_ignores_legacy_project_config_fields():
    import json
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "state.json"
        path.write_text(json.dumps({
            "requirements": {},
            "active_req_by_user": {},
            "project_groups": {},
            "project_configs": {
                "LegacyProj": {
                    "category": "miniprogram",
                    "template_version": "miniprogram.v1",
                    "architecture_doc_id": "doc_l",
                    "architecture_doc_url": "https://feishu.example/docx/doc_l",
                    "github_repo_url": "https://github.com/org/legacy",
                    "onboarding_state": "COMPLETE",
                }
            },
        }, ensure_ascii=False))
        store = JsonStateStore(str(path))
        _, _, _, loaded = store.load_snapshot()
        assert loaded["LegacyProj"].category == "miniprogram"
