from __future__ import annotations

import unittest
import urllib.request
import sys
from pathlib import Path

NEWS_REWRITER_DIR = Path(__file__).resolve().parents[1] / "news_rewriter"
if str(NEWS_REWRITER_DIR) not in sys.path:
    sys.path.insert(0, str(NEWS_REWRITER_DIR))

from extractor import Extractor


class FakeResponse:
    def __init__(self, body: str, content_type: str = "text/html; charset=utf-8"):
        self._body = body.encode("utf-8")
        self.headers = {"Content-Type": content_type}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, size: int = -1):
        if size is None or size < 0:
            return self._body
        return self._body[:size]


class NewsRewriterExtractorTests(unittest.TestCase):
    def test_url_extractor_retries_numeric_cookie_challenge(self):
        challenge = """
        <script>
        function a(a) {
          function n() { var t = ""; t=a[_x](t,40); return t; }
          var e={WTKkN:10,bOYDu:20,wyeCN:30};
        }
        document.cookie="__tst_status="+a(0)+"#;";
        document.cookie="EO_Bot_Ssid="+a(1)+";";
        </script>
        """
        article = """
        <html>
          <head><title>通过验证后的资讯</title></head>
          <body>
            <article>
              <p>这是通过 Cookie 验证后返回的完整资讯正文，包含产品发布信息、关键数字和使用限制。</p>
              <p>正文长度需要足够长，确保提取器能够把它识别为有效文章，而不是验证页或加载提示。</p>
            </article>
          </body>
        </html>
        """
        responses = iter([FakeResponse(challenge), FakeResponse(article)])
        requests = []

        def fake_urlopen(request, timeout=20):
            requests.append(request)
            return next(responses)

        original_urlopen = urllib.request.urlopen
        urllib.request.urlopen = fake_urlopen
        try:
            result = Extractor().extract("https://example.com/protected", "url")
        finally:
            urllib.request.urlopen = original_urlopen

        self.assertTrue(result.success)
        self.assertTrue(result.fallback_used)
        self.assertEqual(len(requests), 2)
        self.assertEqual(
            requests[1].get_header("Cookie"),
            "__tst_status=60#; EO_Bot_Ssid=40",
        )
        self.assertIn("Cookie 验证", " ".join(result.content.warnings))
        self.assertIn("完整资讯正文", result.content.body)

    def test_url_extractor_collects_title_and_article_text(self):
        html = """
        <html>
          <head><title>Notion 发布 AI Meetings</title></head>
          <body>
            <nav>首页 登录 下载</nav>
            <article>
              <h1>Notion 发布 AI Meetings</h1>
              <p>Notion 今日发布 AI Meetings 功能，支持自动录制会议、生成纪要和待办事项。</p>
              <p>官方称中英文识别准确率达 95%，平均可将整理纪要的时间从 30 分钟缩短到 2 分钟。</p>
              <p>目前支持 Zoom、Google Meet、Microsoft Teams，但暂不支持本地录音文件上传。</p>
            </article>
            <script>window.noise = true</script>
          </body>
        </html>
        """

        original_urlopen = urllib.request.urlopen
        urllib.request.urlopen = lambda request, timeout=20: FakeResponse(html)
        try:
            result = Extractor().extract("https://example.com/news", "url")
        finally:
            urllib.request.urlopen = original_urlopen

        self.assertTrue(result.success)
        self.assertEqual(result.content.title, "Notion 发布 AI Meetings")
        self.assertIn("识别准确率达 95%", result.content.body)
        self.assertNotIn("window.noise", result.content.body)
        self.assertNotIn("首页 登录 下载", result.content.body)

    def test_url_extractor_rejects_short_pages(self):
        original_urlopen = urllib.request.urlopen
        urllib.request.urlopen = lambda request, timeout=20: FakeResponse("<title>短页</title><p>太短</p>")
        try:
            result = Extractor().extract("https://example.com/short", "url")
        finally:
            urllib.request.urlopen = original_urlopen

        self.assertFalse(result.success)
        self.assertIn("URL正文提取过短", result.error)

    def test_url_extractor_prefers_json_ld_article_body(self):
        html = """
        <html>
          <head>
            <script type="application/ld+json">
            {
              "@type": "NewsArticle",
              "headline": "DeepSeek 发布新模型",
              "datePublished": "2026-07-13T10:00:00+08:00",
              "author": {"name": "AI News"},
              "articleBody": "DeepSeek 发布新模型，重点优化长文本推理和工具调用。官方称在复杂任务上响应更稳定，并提供 OpenAI-compatible 接口，方便开发者迁移已有应用。"
            }
            </script>
          </head>
          <body>
            <main>页面加载了很多按钮、广告和推荐卡片，但不是完整正文。</main>
          </body>
        </html>
        """

        original_urlopen = urllib.request.urlopen
        urllib.request.urlopen = lambda request, timeout=20: FakeResponse(html)
        try:
            result = Extractor().extract("https://example.com/jsonld", "url")
        finally:
            urllib.request.urlopen = original_urlopen

        self.assertTrue(result.success)
        self.assertEqual(result.content.title, "DeepSeek 发布新模型")
        self.assertEqual(result.content.author, "AI News")
        self.assertEqual(result.content.publish_date, "2026-07-13T10:00:00+08:00")
        self.assertIn("长文本推理和工具调用", result.content.body)
        self.assertIn("JSON-LD", " ".join(result.content.warnings))

    def test_url_extractor_keeps_meta_fields_and_ignores_related_blocks(self):
        html = """
        <html>
          <head>
            <title>网页标题</title>
            <meta property="og:title" content="OpenAI 推出新功能">
            <meta name="author" content="Tech Writer">
            <meta property="article:published_time" content="2026-07-13">
          </head>
          <body>
            <div class="related">推荐阅读 推荐阅读 推荐阅读 推荐阅读 推荐阅读 推荐阅读 推荐阅读</div>
            <div class="article-content">
              <h1>OpenAI 推出新功能</h1>
              <p>OpenAI 推出新的工作流功能，支持把输入、工具调用和输出校验串成一个自动化流程。</p>
              <p>这项能力适合内容团队和产品团队使用，能减少人工复制粘贴，并保留每一步的执行记录。</p>
              <p>官方强调开发者仍需要检查结果，尤其是外部资料、数字和用户可见文案。</p>
            </div>
          </body>
        </html>
        """

        original_urlopen = urllib.request.urlopen
        urllib.request.urlopen = lambda request, timeout=20: FakeResponse(html)
        try:
            result = Extractor().extract("https://example.com/meta", "url")
        finally:
            urllib.request.urlopen = original_urlopen

        self.assertTrue(result.success)
        self.assertEqual(result.content.title, "OpenAI 推出新功能")
        self.assertEqual(result.content.author, "Tech Writer")
        self.assertEqual(result.content.publish_date, "2026-07-13")
        self.assertIn("自动化流程", result.content.body)
        self.assertNotIn("推荐阅读 推荐阅读", result.content.body)

    def test_url_extractor_accepts_plain_text_response(self):
        text = (
            "这是一条纯文本资讯。产品发布了新的自动化能力，支持把网页正文提取、事实锚定、"
            "风格化改写和自检串成一个流程。官方称适合内容团队处理高频资讯。"
            "测试阶段会保留来源、标题、正文和警告信息，方便人工复核。"
        )

        original_urlopen = urllib.request.urlopen
        urllib.request.urlopen = lambda request, timeout=20: FakeResponse(
            text,
            content_type="text/plain; charset=utf-8",
        )
        try:
            result = Extractor().extract("https://example.com/plain.txt", "url")
        finally:
            urllib.request.urlopen = original_urlopen

        self.assertTrue(result.success)
        self.assertEqual(result.content.extract_method, "text_url")
        self.assertIn("纯文本资讯", result.content.body)
        self.assertIn("非HTML", " ".join(result.content.warnings))


if __name__ == "__main__":
    unittest.main()
