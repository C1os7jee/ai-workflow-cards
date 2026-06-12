from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent.agent import VisualAgent
from agent.schemas import FeedbackRecord, SchemaValidationError, VisualPlan
from agent.tools.validate import append_feedback_record, read_feedback_records


class VisualAgentTests(unittest.TestCase):
    def setUp(self):
        self.agent = VisualAgent()

    def test_workflow_content_prefers_flow_strategy(self):
        plan = self.agent.generate_plan("workflow 自动化内容")
        self.assertEqual(plan.recommended_strategy, "流程拆解型")
        self.assertIn("workflow", plan.content_goal)
        self.assertTrue(plan.human_checkpoints)

    def test_tool_content_prefers_tool_strategy(self):
        plan = self.agent.generate_plan("工具实操 demo")
        self.assertEqual(plan.recommended_strategy, "工具实操型")
        self.assertEqual(len(plan.alternatives), 2)

    def test_render_payload_matches_interface_shape(self):
        plan = self.agent.generate_plan("workflow 自动化内容")
        payload = self.agent.to_render_payload(plan)
        self.assertEqual(payload["style"], "swiss")
        self.assertEqual(payload["theme"], "IKB")
        self.assertEqual(payload["layout_id"], "S09")
        self.assertEqual(payload["slides"][0]["type"], "cover")
        self.assertEqual(payload["slides"][-1]["type"], "cta")

    def test_feedback_records_are_appended(self):
        plan = self.agent.generate_plan("workflow 自动化内容")
        with tempfile.TemporaryDirectory() as tmpdir:
            feedback_path = Path(tmpdir) / "records.jsonl"
            self.agent.record_feedback(
                feedback_path=feedback_path,
                post_id="post-001",
                topic="workflow post",
                plan=plan,
                metrics={"views": 123, "likes": 10},
                human_notes="good structure",
            )
            records = list(read_feedback_records(feedback_path))
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].post_id, "post-001")
            self.assertEqual(records[0].visual_strategy, "流程拆解型")

    def test_visual_plan_validation_rejects_empty_reason(self):
        plan = VisualPlan(
            content_goal="workflow",
            recommended_strategy="流程拆解型",
            alternatives=[],
            reason="",
            cover_direction=None,
            slides_plan=["a"],
            risk="risk",
            human_checkpoints=["x"],
        )
        with self.assertRaises(SchemaValidationError):
            plan.validate()

    def test_plan_uses_brief_content_instead_of_static_preset(self):
        mosa_plan = self.agent.generate_plan(
            "MiniMax 提出块稀疏注意力 MoSA，Main Branch 只对选中块执行精确块稀疏注意力，长上下文计算减少 28.4 倍。"
        )
        workflow_plan = self.agent.generate_plan(
            "workflow 自动化内容：把文章提炼、排版和校验串成小红书组图流水线。"
        )

        self.assertNotEqual(
            mosa_plan.cover_direction.title,
            workflow_plan.cover_direction.title,
        )
        self.assertTrue(
            any("MoSA" in item or "Main Branch" in item for item in mosa_plan.slides_plan)
        )


if __name__ == "__main__":
    unittest.main()
