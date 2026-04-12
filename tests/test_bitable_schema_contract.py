from __future__ import annotations

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.bitable_schema import (
    build_coordinator_record_fields,
    coordinator_managed_field_names,
    reader_visible_field_specs,
)
from requirement_workflow_v12.models import Requirement, WorkflowStatus


class BitableSchemaContractTest(unittest.TestCase):
    def test_coordinator_record_fields_match_schema_contract(self) -> None:
        requirement = Requirement(
            req_id="REQ-HARNESS-001",
            name="schema contract test",
            project="HARNESS",
            summary="验证 Coordinator 写入字段集合和 schema 一致。",
            creator="tester",
            status=WorkflowStatus.DISCUSSING,
        )
        fields = build_coordinator_record_fields(requirement)
        self.assertEqual(tuple(fields.keys()), coordinator_managed_field_names())

    def test_author_and_reviewer_read_contracts_are_in_sync(self) -> None:
        author_fields = {spec.name for spec in reader_visible_field_specs("author")}
        reviewer_fields = {spec.name for spec in reader_visible_field_specs("reviewer")}
        self.assertEqual(author_fields, reviewer_fields)
        self.assertIn("需求文档链接", author_fields)
        self.assertIn("状态", author_fields)
        self.assertIn("当前阶段", author_fields)


if __name__ == "__main__":
    unittest.main()
