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
    bitable_record_id: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "ProjectConfig":
        return cls(
            category=data["category"],
            template_version=data["template_version"],
            architecture_doc_id=data["architecture_doc_id"],
            architecture_doc_url=data["architecture_doc_url"],
            tech_stack=data.get("tech_stack", {}),
            design_system_doc_id=data.get("design_system_doc_id"),
            bitable_record_id=data.get("bitable_record_id", ""),
        )
