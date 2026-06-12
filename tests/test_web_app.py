from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.web_app import build_visual_response, record_feedback, render_deck_response
from agent.tools.validate import read_feedback_records


class WebAppTests(unittest.TestCase):
    def test_build_visual_response_includes_plan_and_render_input(self):
        response = build_visual_response("workflow 自动化内容")
        self.assertEqual(response["visual_plan"]["recommended_strategy"], "流程拆解型")
        self.assertEqual(response["render_input"]["style"], "swiss")
        self.assertEqual(response["render_input"]["slides"][0]["type"], "cover")

    def test_record_feedback_writes_jsonl(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            feedback_path = Path(tmpdir) / "feedback.jsonl"
            response = record_feedback(
                {
                    "content_goal": "workflow 自动化内容",
                    "post_id": "post-002",
                    "topic": "workflow post",
                    "metrics": {"views": 100},
                    "human_notes": "封面还可以更直给",
                },
                feedback_path=feedback_path,
            )
            self.assertTrue(response["success"])
            records = list(read_feedback_records(feedback_path))
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].post_id, "post-002")

    def test_render_deck_response_symbol_exists(self):
        self.assertTrue(callable(render_deck_response))


if __name__ == "__main__":
    unittest.main()
