from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ProjectConfig:
    category: str
    template_version: str
    architecture_doc_id: str
    architecture_doc_url: str
    tech_stack: dict[str, str] = field(default_factory=dict)
    design_system_doc_id: str | None = None
    github_repo_url: str = ""
    github_owner_username: str = ""
    bitable_record_id: str = ""
    bootstrap_status: str = "UNBOOTSTRAPPED"
    bootstrap_log: list[dict] = field(default_factory=list)
    bootstrap_completed_at: str | None = None
    project_status: str = "UNBOOTSTRAPPED"
    feishu_chat_id: str = ""
    architecture_github_path: str = "docs/ARCHITECTURE.md"
    architecture_github_revision: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "ProjectConfig":
        return cls(
            category=data["category"],
            template_version=data["template_version"],
            architecture_doc_id=data["architecture_doc_id"],
            architecture_doc_url=data["architecture_doc_url"],
            tech_stack=data.get("tech_stack", {}),
            design_system_doc_id=data.get("design_system_doc_id"),
            github_repo_url=data.get("github_repo_url", ""),
            github_owner_username=data.get("github_owner_username", ""),
            bitable_record_id=data.get("bitable_record_id", ""),
            bootstrap_status=data.get("bootstrap_status", "UNBOOTSTRAPPED"),
            bootstrap_log=data.get("bootstrap_log", []),
            bootstrap_completed_at=data.get("bootstrap_completed_at"),
            project_status=data.get("project_status", "UNBOOTSTRAPPED"),
            feishu_chat_id=data.get("feishu_chat_id", ""),
            architecture_github_path=data.get("architecture_github_path", "docs/ARCHITECTURE.md"),
            architecture_github_revision=data.get("architecture_github_revision", ""),
        )
