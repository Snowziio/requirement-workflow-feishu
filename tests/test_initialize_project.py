import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from requirement_workflow_v12.coordinator_service import CoordinatorService
from requirement_workflow_v12.project_config import ProjectConfig


def test_initialize_project_registers_config():
    svc = CoordinatorService()
    cfg = svc.initialize_project(
        project="MyProj",
        category="saas-ai-automation",
        template_version="saas-ai-automation.v1",
        architecture_doc_id="doc_xyz",
        architecture_doc_url="https://feishu.example/docx/doc_xyz",
        tech_stack={"backend": "FastAPI"},
    )
    assert isinstance(cfg, ProjectConfig)
    assert svc.project_configs["MyProj"] is cfg
    assert cfg.category == "saas-ai-automation"
    assert cfg.tech_stack == {"backend": "FastAPI"}


def test_initialize_project_rejects_duplicate():
    svc = CoordinatorService()
    svc.initialize_project(
        project="MyProj",
        category="miniprogram",
        template_version="miniprogram.v1",
        architecture_doc_id="doc_a",
        architecture_doc_url="https://feishu.example/docx/doc_a",
        tech_stack={},
    )
    with pytest.raises(ValueError, match="already initialized"):
        svc.initialize_project(
            project="MyProj",
            category="miniprogram",
            template_version="miniprogram.v1",
            architecture_doc_id="doc_b",
            architecture_doc_url="https://feishu.example/docx/doc_b",
            tech_stack={},
        )
