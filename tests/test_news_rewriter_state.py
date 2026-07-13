from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


NEWS_REWRITER_DIR = Path(__file__).resolve().parents[1] / "news_rewriter"
if str(NEWS_REWRITER_DIR) not in sys.path:
    sys.path.insert(0, str(NEWS_REWRITER_DIR))

from schemas import FactAnchors, Recommendation, RewriteDraft, RewriteResult, SelfCheck
from state import AgentState


class NewsRewriterFileStateTests(unittest.TestCase):
    def test_record_run_writes_json_file_and_index(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = AgentState(state_dir=tmpdir)
            result = RewriteResult(
                run_id="run_test_001",
                source={"type": "text", "origin": "(inline)"},
                fact_anchors=FactAnchors(raw_text_summary="Notion 发布 AI 会议功能"),
                recommendation=Recommendation(
                    worth_writing=True,
                    angle="会议纪要自动化",
                    risk_level="low",
                ),
                draft=RewriteDraft(body="draft"),
                self_check=SelfCheck(),
                created_at="2026-07-13T16:20:00",
            )

            state.record_run(result)

            run_path = Path(tmpdir) / "runs" / "run_test_001.json"
            index_path = Path(tmpdir) / "runs.jsonl"
            self.assertTrue(run_path.exists())
            self.assertTrue(index_path.exists())
            self.assertEqual(json.loads(run_path.read_text(encoding="utf-8"))["run_id"], "run_test_001")
            self.assertEqual(state.stats()["total_runs"], 1)
            self.assertEqual(state.find_similar("Notion 发布 AI 会议功能")[0]["run_id"], "run_test_001")

    def test_published_records_are_jsonl(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = AgentState(state_dir=tmpdir)
            state.save_published(
                run_id="run_test_001",
                final_title="我用 AI 省了 30 分钟",
                final_body="final body",
                rating="good",
            )

            self.assertEqual(state.stats()["published"], 1)
            examples = state.get_good_examples()
            self.assertEqual(examples[0]["final_title"], "我用 AI 省了 30 分钟")


if __name__ == "__main__":
    unittest.main()
