from __future__ import annotations

from .models import DISCUSSION_FIELDS, Requirement, RequirementDocument


class RequirementDocumentCompiler:
    """Maintain a stable section-based requirement document."""

    ORDERED_SECTIONS = [
        "需求概览",
        *DISCUSSION_FIELDS,
        "多轮讨论纪要",
        "AI Review结论",
        "人工Review结论",
    ]

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
        self.refresh_derived_sections(requirement, document)
        return document

    def refresh_derived_sections(self, requirement: Requirement, document: RequirementDocument | None = None) -> RequirementDocument:
        document = document or requirement.document or self.create_document(requirement)
        document.rewrite_section("需求概览", requirement.summary.strip() or "待补充")
        document.rewrite_section("多轮讨论纪要", self._discussion_history_summary(requirement))
        document.rewrite_section("AI Review结论", self._review_history_summary(requirement))
        document.rewrite_section("人工Review结论", self._human_review_summary(requirement))
        return document

    def render_markdown(self, document: RequirementDocument) -> str:
        blocks = [f"# {document.title}"]
        for section in self.ORDERED_SECTIONS:
            blocks.append(f"## {section}")
            blocks.append(document.sections.get(section, "待补充"))
        return "\n\n".join(blocks).strip() + "\n"

    def _discussion_history_summary(self, requirement: Requirement) -> str:
        if not requirement.discussion_history:
            return "待补充"
        lines = []
        for turn in requirement.discussion_history:
            normalized_fields = "；".join(
                f"{field}：{content}" for field, content in turn.normalized_updates.items() if content.strip()
            ) or "无结构化更新"
            lines.append(
                f"第{turn.round_number}轮｜聚焦：{turn.focused_field}｜用户输入：{turn.user_input.strip() or '待补充'}"
            )
            lines.append(f"归一化结果：{normalized_fields}")
            lines.append(f"AI结论：{turn.review_summary or '待补充'}")
            if turn.next_question:
                lines.append(f"下一问：{turn.next_question}")
        return "\n".join(lines)

    def _review_history_summary(self, requirement: Requirement) -> str:
        if not requirement.review_history:
            return "待补充"
        lines = []
        for index, review in enumerate(requirement.review_history, start=1):
            readiness = "可进入人工确认" if review.ready_for_human_confirmation else "需继续打磨"
            line = f"第{index}次AI Review｜{readiness}｜结论：{review.summary}"
            if review.weak_fields:
                line += f"｜弱项字段：{', '.join(review.weak_fields)}"
            if review.conflicts:
                line += f"｜冲突：{'; '.join(review.conflicts)}"
            if review.non_testable_acceptance_criteria:
                line += f"｜不可测验收：{'; '.join(review.non_testable_acceptance_criteria)}"
            if review.next_focus:
                line += f"｜下一焦点：{review.next_focus}"
            lines.append(line)
        return "\n".join(lines)

    def _human_review_summary(self, requirement: Requirement) -> str:
        if not requirement.human_review_history:
            return "待补充"
        lines = []
        for index, review in enumerate(requirement.human_review_history, start=1):
            outcome = "通过" if review.approved else "退回修改"
            lines.append(f"第{index}次人工Review｜{outcome}｜结论：{review.summary}")
        return "\n".join(lines)
