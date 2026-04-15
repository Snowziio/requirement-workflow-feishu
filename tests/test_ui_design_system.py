from requirement_workflow_v12.coordinator_service import CoordinatorService
from requirement_workflow_v12.project_config import ProjectConfig


def _make_service(project: str = "PROJ") -> CoordinatorService:
    svc = CoordinatorService()
    svc.project_configs[project] = ProjectConfig(
        category="saas-ai-automation",
        template_version="saas-ai-automation.v1",
        architecture_doc_id="doc_t",
        architecture_doc_url="https://feishu.example/docx/doc_t",
        tech_stack={},
    )
    return svc


def test_should_create_design_system_when_no_doc():
    svc = _make_service()
    assert svc.should_create_design_system("PROJ") is True


def test_should_not_create_when_doc_already_exists():
    svc = _make_service()
    svc.project_configs["PROJ"].design_system_doc_id = "doc_abc"
    assert svc.should_create_design_system("PROJ") is False


def test_should_not_create_when_no_project_config():
    svc = CoordinatorService()
    assert svc.should_create_design_system("UNKNOWN") is False


def test_set_design_system_doc_stores_id():
    svc = _make_service()
    svc.set_design_system_doc("PROJ", "doc_xyz")
    assert svc.project_configs["PROJ"].design_system_doc_id == "doc_xyz"


def test_set_design_system_doc_noop_for_unknown_project():
    svc = CoordinatorService()
    svc.set_design_system_doc("UNKNOWN", "doc_xyz")  # must not raise
