from __future__ import annotations

from .models import DISCUSSION_FIELDS, Requirement, RequirementDocument


class RequirementDocumentCompiler:
    """Maintain a stable section-based requirement document."""

    ORDERED_SECTIONS = ["需求概览", *DISCUSSION_FIELDS]

    def create_document(self, requirement: Requirement) -> RequirementDocument:
        sections = {section: "待补充" for section in self.ORDERED_SECTIONS}
        sections["需求概览"] = requirement.summary.strip() or "待补充"
        return RequirementDocument(title=f"{requirement.req_id} {requirement.name}", sections=sections)

    def rewrite_sections(self, requirement: Requirement, updates: dict[str, str]) -> RequirementDocument:
        document = requirement.document or self.create_document(requirement)
        for section, content in updates.items():
            if section not in self.ORDERED_SECTIONS:
                continue
            normalized = content.strip() or "待补充"
            if document.sections.get(section) == normalized:
                continue
            document.rewrite_section(section, normalized)
        return document

    def render_markdown(self, document: RequirementDocument) -> str:
        blocks = [f"# {document.title}"]
        for section in self.ORDERED_SECTIONS:
            blocks.append(f"## {section}")
            blocks.append(document.sections.get(section, "待补充"))
        return "\n\n".join(blocks).strip() + "\n"
