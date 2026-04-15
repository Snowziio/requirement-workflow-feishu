import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.store import JsonStateStore


def test_save_snapshot_does_not_persist_project_configs():
    """ProjectConfig lives in Bitable, not state.json — save_snapshot must not write it."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "state.json"
        store = JsonStateStore(str(path))
        store.save_snapshot({}, {"user": "req_1"}, {"MyProj": "chat_1"})
        payload = json.loads(path.read_text())
        assert "project_configs" not in payload
        assert payload["active_req_by_user"] == {"user": "req_1"}
        assert payload["project_groups"] == {"MyProj": "chat_1"}


def test_load_snapshot_ignores_legacy_project_configs():
    """Pre-migration state.json may still carry project_configs — load must skip it."""
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
                }
            },
        }, ensure_ascii=False))
        store = JsonStateStore(str(path))
        _, _, _, project_configs = store.load_snapshot()
        assert project_configs == {}
