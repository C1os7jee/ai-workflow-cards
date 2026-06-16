"""URL fetching helpers for turning a URL into a content brief."""

from __future__ import annotations

import html
import json
import re
import subprocess
import tempfile
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, List


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BROWSER_SKILL_ROOT = PROJECT_ROOT / "skills" / "guizang-social-card-skill"
URL_RE = re.compile(r"^https?://", re.IGNORECASE)


class _ReadableTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title_parts: List[str] = []
        self.description = ""
        self.headings: List[str] = []
        self.text_parts: List[str] = []
        self._in_title = False
        self._in_heading = False
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag == "title":
            self._in_title = True
        elif tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
        elif tag in {"h1", "h2", "h3"}:
            self._in_heading = True
        elif tag == "meta":
            self._capture_meta(attrs)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
        elif tag in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1
        elif tag in {"h1", "h2", "h3"}:
            self._in_heading = False

    def handle_data(self, data: str) -> None:
        text = _clean_text(data)
        if not text:
            return
        if self._in_title:
            self.title_parts.append(text)
            return
        if self._skip_depth:
            return
        if self._in_heading:
            self.headings.append(text)
            self.text_parts.append(text)
            return
        self.text_parts.append(text)

    def _capture_meta(self, attrs) -> None:
        attrs_map = {str(key).lower(): str(value) for key, value in attrs if key}
        if self.description:
            return
        name = (attrs_map.get("name") or attrs_map.get("property") or "").lower()
        content = _clean_text(attrs_map.get("content", ""))
        if not content:
            return
        if name in {"description", "og:description", "twitter:description"}:
            self.description = content


def is_url(value: str) -> bool:
    return bool(URL_RE.match((value or "").strip()))


def brief_from_url(url: str, max_chars: int = 1800) -> str:
    """Fetch a URL and return a compact brief for the VisualAgent."""
    url = url.strip()
    if not is_url(url):
        raise ValueError("url must start with http:// or https://")
    static_snapshot = _snapshot_from_url(url, max_chars=max_chars)
    browser_snapshot = {}
    if _should_try_browser_fallback(static_snapshot):
        try:
            browser_snapshot = _browser_snapshot_from_url(url, max_chars=max_chars)
        except Exception:
            browser_snapshot = {}
    snapshot = _merge_snapshots(static_snapshot, browser_snapshot)
    return _format_brief(url, snapshot, max_chars=max_chars)


def _snapshot_from_url(url: str, max_chars: int = 1800) -> Dict[str, object]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "ai-workflow-cards/0.1 (+https://localhost)",
            "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read(2_000_000)
        content_type = response.headers.get("content-type", "")
    charset = _charset_from_content_type(content_type) or "utf-8"
    text = raw.decode(charset, errors="replace")
    if "html" in content_type.lower() or "<html" in text[:1000].lower():
        return _extract_html_snapshot(text, max_chars=max_chars)
    body = _clean_text(html.unescape(text))
    if len(body) > max_chars:
        body = body[:max_chars].rstrip() + "..."
    return {
        "title": "",
        "description": "",
        "headings": [],
        "body": body,
    }


def _extract_html_snapshot(text: str, max_chars: int = 1800) -> Dict[str, object]:
    parser = _ReadableTextParser()
    parser.feed(text)
    title = _clean_text(" ".join(parser.title_parts))
    description = _clean_text(parser.description)
    headings = _unique_text(parser.headings)
    body = _clean_text(html.unescape(" ".join(parser.text_parts)))
    if len(body) > max_chars:
        body = body[:max_chars].rstrip() + "..."
    return {
        "title": title,
        "description": description,
        "headings": headings,
        "body": body,
    }


def _should_try_browser_fallback(snapshot: Dict[str, object]) -> bool:
    title = str(snapshot.get("title", ""))
    description = str(snapshot.get("description", ""))
    body = str(snapshot.get("body", ""))
    headings = snapshot.get("headings", [])
    heading_count = len(headings) if isinstance(headings, list) else 0
    haystack = " ".join([title, description, body]).lower()
    if not body and not heading_count:
        return True
    if any(token in haystack for token in _LOADING_TOKENS):
        return True
    if heading_count and len(body) < 120 and not description:
        return True
    return False


def _merge_snapshots(static_snapshot: Dict[str, object], browser_snapshot: Dict[str, object]) -> Dict[str, object]:
    if not browser_snapshot:
        return static_snapshot
    merged = dict(static_snapshot)
    for key in ("title", "description", "body"):
        browser_value = _clean_text(str(browser_snapshot.get(key, "")))
        if browser_value:
            merged[key] = browser_value
    browser_headings = browser_snapshot.get("headings", [])
    if isinstance(browser_headings, list) and browser_headings:
        merged["headings"] = _unique_text([str(item) for item in browser_headings])
    return merged


def _format_brief(url: str, snapshot: Dict[str, object], max_chars: int = 1800) -> str:
    parts = [f"来源 URL：{url}"]
    title = _clean_text(str(snapshot.get("title", "")))
    description = _clean_text(str(snapshot.get("description", "")))
    headings = snapshot.get("headings", [])
    body = _clean_text(str(snapshot.get("body", "")))

    if title:
        parts.append(f"标题：{title}")
    if description and description != title:
        parts.append(f"摘要：{description}")
    if isinstance(headings, list) and headings:
        heading_text = " / ".join(_unique_text([str(item) for item in headings])[:3])
        if heading_text:
            parts.append(f"页面标题：{heading_text}")
    if body:
        parts.append(f"正文摘要：{body[:max_chars]}")
    return "\n".join(parts)


def _browser_snapshot_from_url(url: str, max_chars: int = 1800) -> Dict[str, object]:
    if not BROWSER_SKILL_ROOT.exists():
        raise FileNotFoundError("missing browser skill root: %s" % BROWSER_SKILL_ROOT)
    script = _browser_snapshot_script()
    with tempfile.NamedTemporaryFile(
        "w",
        suffix=".mjs",
        encoding="utf-8",
        delete=False,
        dir=str(BROWSER_SKILL_ROOT),
    ) as handle:
        handle.write(script)
        script_path = Path(handle.name)
    try:
        completed = subprocess.run(
            ["node", str(script_path), url, str(max_chars)],
            cwd=str(BROWSER_SKILL_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=40,
        )
        if completed.returncode != 0:
            error_output = (completed.stderr or "").strip() or (completed.stdout or "").strip()
            raise RuntimeError("browser snapshot failed: %s" % error_output)
        raw = completed.stdout.strip() or "{}"
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise RuntimeError("browser snapshot returned invalid JSON")
        return {
            "title": _clean_text(str(data.get("title", ""))),
            "description": _clean_text(str(data.get("description", ""))),
            "headings": _unique_text([str(item) for item in data.get("headings", [])])
            if isinstance(data.get("headings", []), list)
            else [],
            "body": _truncate_text(_clean_text(str(data.get("body", ""))), max_chars),
        }
    finally:
        script_path.unlink(missing_ok=True)


def _browser_snapshot_script() -> str:
    return r"""
import { chromium } from 'playwright';

const targetUrl = process.argv[2];
const maxChars = Number(process.argv[3] || '1800');

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 2200 }, deviceScaleFactor: 1 });
await page.goto(targetUrl, { waitUntil: 'domcontentloaded', timeout: 20000 });
await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {});
await page.waitForTimeout(500);
const data = await page.evaluate((limit) => {
  const clean = (value) => (value || '').replace(/\s+/g, ' ').trim();
  const unique = (items) => [...new Set(items.map(clean).filter(Boolean))];
  const title = clean(document.title || '');
  const descriptionNode = document.querySelector('meta[name="description"], meta[property="og:description"], meta[name="twitter:description"]');
  const description = clean(descriptionNode ? descriptionNode.content : '');
  const headings = unique(Array.from(document.querySelectorAll('h1, h2, h3')).map((node) => node.innerText));
  const body = clean((document.body && document.body.innerText) || '');
  return {
    title,
    description,
    headings,
    body: body.slice(0, limit),
  };
}, maxChars);
await browser.close();
console.log(JSON.stringify(data));
"""


def _charset_from_content_type(content_type: str) -> str:
    match = re.search(r"charset=([^;\s]+)", content_type or "", re.IGNORECASE)
    return match.group(1).strip("\"'") if match else ""


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _truncate_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + "..."


def _unique_text(values: List[str]) -> List[str]:
    items: List[str] = []
    for value in values:
        clean = _clean_text(value)
        if clean and clean not in items:
            items.append(clean)
    return items


_LOADING_TOKENS = {
    "loading",
    "loading...",
    "please wait",
    "loading shell",
    "javascript",
    "enable javascript",
    "app is loading",
}
