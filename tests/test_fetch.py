from __future__ import annotations

import unittest

from agent.tools import extract
from agent.tools import fetch


class _FakeResponse:
    def __init__(self, body: bytes, content_type: str) -> None:
        self._body = body
        self.headers = {"content-type": content_type}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, limit: int = -1) -> bytes:
        return self._body


class FetchTests(unittest.TestCase):
    def test_brief_from_url_collects_static_metadata(self):
        html_doc = b"""
        <html>
          <head>
            <title>Static Article</title>
            <meta name="description" content="Meta summary for planner">
          </head>
          <body>
            <script>ignored()</script>
            <main>
              <h1>Main Heading</h1>
              <h2>Supporting Heading</h2>
              <p>workflow automation compresses research into five minutes.</p>
            </main>
          </body>
        </html>
        """

        original_urlopen = fetch.urllib.request.urlopen
        fetch.urllib.request.urlopen = lambda request, timeout: _FakeResponse(
            html_doc,
            "text/html; charset=utf-8",
        )
        try:
            brief = fetch.brief_from_url("https://example.com/post")
        finally:
            fetch.urllib.request.urlopen = original_urlopen

        self.assertIn("Static Article", brief)
        self.assertIn("Meta summary for planner", brief)
        self.assertIn("Main Heading", brief)
        self.assertIn("Supporting Heading", brief)
        self.assertIn("workflow automation compresses research", brief)
        self.assertNotIn("ignored()", brief)

    def test_brief_from_url_uses_browser_fallback_for_js_shells(self):
        html_doc = b"""
        <html>
          <head>
            <title>Loading Shell</title>
          </head>
          <body>
            <div id="app">Loading...</div>
            <script src="app.js"></script>
          </body>
        </html>
        """

        original_urlopen = fetch.urllib.request.urlopen
        original_browser_snapshot = fetch._browser_snapshot_from_url
        fetch.urllib.request.urlopen = lambda request, timeout: _FakeResponse(
            html_doc,
            "text/html; charset=utf-8",
        )
        fetch._browser_snapshot_from_url = lambda url, max_chars=1800: {
            "title": "Rendered Title",
            "description": "Rendered summary",
            "headings": ["Rendered Heading"],
            "body": "Rendered body with hydrated content.",
        }
        try:
            brief = fetch.brief_from_url("https://example.com/app")
        finally:
            fetch.urllib.request.urlopen = original_urlopen
            fetch._browser_snapshot_from_url = original_browser_snapshot

        self.assertIn("Rendered Title", brief)
        self.assertIn("Rendered summary", brief)
        self.assertIn("Rendered Heading", brief)
        self.assertIn("hydrated content", brief)
        self.assertNotIn("Loading...", brief)

    def test_extract_article_brief_formats_model_structured_result(self):
        original = extract._call_ai_extractor
        extract._call_ai_extractor = lambda raw_brief: {
            "source_url": "https://example.com/post",
            "title": "Hermes Agent 上线 Profile Builder",
            "topic": "Hermes Agent Profile Builder",
            "core_hook": "5 步配置 AI 智能体",
            "summary": "把命令行配置整合成网页端向导。",
            "key_points": [
                "网页端一站式创建角色",
                "支持模型、技能、MCP",
                "按需加载 SKILL.md",
            ],
            "entities": ["Hermes Agent", "Profile Builder", "MCP"],
            "numbers": ["5 步"],
            "audience_angle": "AI 工具玩家",
        }
        try:
            brief = extract.extract_article_brief("来源 URL：https://example.com/post")
        finally:
            extract._call_ai_extractor = original

        self.assertIn("主题：Hermes Agent Profile Builder", brief)
        self.assertIn("核心钩子：5 步配置 AI 智能体", brief)
        self.assertIn("关键点：网页端一站式创建角色", brief)


if __name__ == "__main__":
    unittest.main()
