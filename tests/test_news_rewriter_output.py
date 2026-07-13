from __future__ import annotations

import sys
import unittest
from pathlib import Path


NEWS_REWRITER_DIR = Path(__file__).resolve().parents[1] / "news_rewriter"
if str(NEWS_REWRITER_DIR) not in sys.path:
    sys.path.insert(0, str(NEWS_REWRITER_DIR))

from schemas import FactAnchors, Recommendation, RewriteDraft, RewriteResult, SelfCheck


class NewsRewriterOutputTests(unittest.TestCase):
    def test_post_package_contains_only_downstream_fields(self):
        result = RewriteResult(
            run_id="run_test_001",
            source={
                "type": "url",
                "origin": "https://example.com/news",
                "original_title": "示例资讯",
                "extract_method": "html_parse",
            },
            fact_anchors=FactAnchors(
                numbers=["2026年7月19日", "50%"],
                features=["免费使用期限延长", "每周50%配额可用"],
                raw_text_summary="某产品延长免费使用期限",
            ),
            recommendation=Recommendation(
                worth_writing=True,
                angle="利用免费期测试性价比",
                risk_level="high",
            ),
            draft=RewriteDraft(
                title_candidates=["我用免费期省了50%成本"],
                opening_candidates=["免费期延长了。"],
                body="改写后的正文",
                ending_options={"提问型": "你会怎么选？"},
                fabricated_segments=["[似真例子,待核对]: 示例[/似真例子]"],
            ),
            self_check=SelfCheck(
                fact_ok=True,
                warnings=["发稿前替换似真例子"],
            ),
        )

        package = result.to_post_package()

        self.assertEqual(
            set(package),
            {"run_id", "source", "post_draft", "review", "fact_guardrails"},
        )
        self.assertEqual(package["source"]["url"], "https://example.com/news")
        self.assertEqual(package["post_draft"]["body"], "改写后的正文")
        self.assertEqual(package["review"]["risk_level"], "high")
        self.assertEqual(
            package["review"]["fabricated_segments"],
            ["[似真例子,待核对]: 示例[/似真例子]"],
        )
        self.assertEqual(
            package["fact_guardrails"]["must_not_change"],
            ["免费使用期限延长", "每周50%配额可用"],
        )
        self.assertNotIn("fact_anchors", package)
        self.assertNotIn("recommendation", package)
        self.assertNotIn("traces", package)

    def test_post_package_uses_null_url_for_non_url_sources(self):
        result = RewriteResult(
            run_id="run_test_002",
            source={"type": "text", "origin": "用户输入", "original_title": None},
            fact_anchors=FactAnchors(),
            recommendation=Recommendation(
                worth_writing=False,
                angle="信息不足",
                risk_level="medium",
            ),
            draft=RewriteDraft(),
            self_check=SelfCheck(),
        )

        self.assertIsNone(result.to_post_package()["source"]["url"])


if __name__ == "__main__":
    unittest.main()
