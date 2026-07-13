"""多源内容提取。所有方法返回 ExtractResult,永远成功返回。"""
import html
import json
import re
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

from schemas import ExtractedContent, ExtractResult


MIN_EXTRACTED_CHARS = 80
MAX_EXTRACTED_CHARS = 12000
MAX_URL_BYTES = 3_000_000
BLOCK_TAGS = {"article", "main", "section", "div", "p", "li", "h1", "h2", "h3", "br"}
SKIP_TAGS = {"script", "style", "noscript", "svg", "canvas", "form", "iframe"}
BOILERPLATE_TAGS = {"nav", "footer", "header", "aside"}
CONTENT_HINT_RE = re.compile(
    r"(article|body|content|entry|main|post|story|text|news|detail|正文|新闻)",
    re.I,
)
NOISE_HINT_RE = re.compile(
    r"(comment|related|recommend|sidebar|footer|header|nav|menu|share|login|subscribe|"
    r"advert|ad-|cookie|breadcrumb|toolbar)",
    re.I,
)
LOADING_TOKENS = {
    "loading",
    "please wait",
    "enable javascript",
    "javascript",
    "app is loading",
}
URL_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


class _ArticleHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.meta_title = ""
        self.description = ""
        self.meta_author = ""
        self.meta_publish_date = ""
        self.headings: list[str] = []
        self.json_ld_parts: list[str] = []
        self.body_parts: list[str] = []
        self.candidate_parts: dict[str, list[str]] = {}
        self.candidate_boosts: dict[str, int] = {}
        self._tag_stack: list[dict] = []
        self._skip_depth = 0
        self._json_ld_depth = 0
        self._in_title = False
        self._in_heading = False
        self._candidate_counter = 0
        self.selected_source = "body"

    def handle_starttag(self, tag: str, attrs):
        tag = tag.lower()
        attrs_map = {str(key).lower(): str(value or "") for key, value in attrs if key}
        if tag == "meta":
            self._capture_meta(attrs_map)

        is_json_ld = tag == "script" and "ld+json" in attrs_map.get("type", "").lower()
        if is_json_ld:
            self._json_ld_depth += 1
        elif tag in SKIP_TAGS:
            self._skip_depth += 1

        if tag == "title":
            self._in_title = True
        if tag in {"h1", "h2", "h3"}:
            self._in_heading = True

        candidates: list[str] = []
        if not self._is_noise_element(tag, attrs_map):
            boost = self._content_boost(tag, attrs_map)
            if boost:
                candidate_id = f"{tag}:{self._candidate_counter}"
                self._candidate_counter += 1
                self.candidate_parts[candidate_id] = []
                self.candidate_boosts[candidate_id] = boost
                candidates.append(candidate_id)

        self._tag_stack.append(
            {
                "tag": tag,
                "attrs": attrs_map,
                "noise": self._is_noise_element(tag, attrs_map),
                "candidates": candidates,
            }
        )
        if tag in BLOCK_TAGS:
            self._append_separator()

    def handle_endtag(self, tag: str):
        tag = tag.lower()
        if tag in BLOCK_TAGS:
            self._append_separator()
        if tag == "script" and self._json_ld_depth:
            self._json_ld_depth -= 1
        elif tag in SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        if tag == "title":
            self._in_title = False
        if tag in {"h1", "h2", "h3"}:
            self._in_heading = False
        if self._tag_stack:
            self._tag_stack.pop()

    def handle_data(self, data: str):
        text = data.strip()
        if not text:
            return
        if self._json_ld_depth:
            self.json_ld_parts.append(data)
            return
        if self._in_title:
            self.title_parts.append(text)
            return
        if self._skip_depth:
            return
        if self._is_navigation_context():
            return
        clean = _clean_text(text)
        if not clean:
            return
        if self._in_heading:
            self.headings.append(clean)
        self.body_parts.append(clean)
        for candidate_id in self._active_candidates():
            self.candidate_parts[candidate_id].append(clean)

    def _append_separator(self):
        self.body_parts.append("\n")
        for candidate_id in self._active_candidates():
            self.candidate_parts[candidate_id].append("\n")

    def _is_navigation_context(self) -> bool:
        return any(item["noise"] for item in self._tag_stack)

    def _active_candidates(self) -> list[str]:
        ids: list[str] = []
        for item in self._tag_stack:
            ids.extend(item["candidates"])
        return ids

    def _capture_meta(self, attrs_map: dict[str, str]):
        key = (attrs_map.get("name") or attrs_map.get("property") or "").lower()
        content = _clean_text(attrs_map.get("content", ""))
        if not key or not content:
            return
        if key in {"og:title", "twitter:title"} and not self.meta_title:
            self.meta_title = content
        elif key in {"description", "og:description", "twitter:description"} and not self.description:
            self.description = content
        elif key in {"author", "article:author", "twitter:creator"} and not self.meta_author:
            self.meta_author = content
        elif key in {
            "article:published_time",
            "publishdate",
            "pubdate",
            "date",
            "datepublished",
            "dc.date",
            "dc.date.issued",
        } and not self.meta_publish_date:
            self.meta_publish_date = content

    def _is_noise_element(self, tag: str, attrs_map: dict[str, str]) -> bool:
        if tag in BOILERPLATE_TAGS:
            return True
        hints = " ".join([attrs_map.get("id", ""), attrs_map.get("class", ""), attrs_map.get("role", "")])
        return bool(NOISE_HINT_RE.search(hints))

    def _content_boost(self, tag: str, attrs_map: dict[str, str]) -> int:
        if tag == "article":
            return 700
        if tag == "main":
            return 500
        hints = " ".join([attrs_map.get("id", ""), attrs_map.get("class", ""), attrs_map.get("role", "")])
        if CONTENT_HINT_RE.search(hints):
            return 300
        return 0

    @property
    def title(self) -> str | None:
        json_ld = self._json_ld_metadata()
        title = (
            self.meta_title
            or _clean_text(" ".join(self.title_parts))
            or json_ld.get("title", "")
            or (self.headings[0] if self.headings else "")
        )
        return title or None

    @property
    def author(self) -> str | None:
        author = self.meta_author or self._json_ld_metadata().get("author", "")
        return author or None

    @property
    def publish_date(self) -> str | None:
        publish_date = self.meta_publish_date or self._json_ld_metadata().get("publish_date", "")
        return publish_date or None

    @property
    def body(self) -> str:
        body, source = self.select_body()
        self.selected_source = source
        return body

    def select_body(self) -> tuple[str, str]:
        candidates: list[tuple[int, str, str]] = []
        json_ld_body = self._json_ld_metadata().get("article_body", "")
        if json_ld_body:
            candidates.append((_score_article_text(json_ld_body, 900), "json_ld", json_ld_body))

        for candidate_id, parts in self.candidate_parts.items():
            text = _clean_text("\n".join(parts))
            if text:
                boost = self.candidate_boosts.get(candidate_id, 0)
                candidates.append((_score_article_text(text, boost), "content_block", text))

        full_body = _clean_text("\n".join(self.body_parts))
        if full_body:
            candidates.append((_score_article_text(full_body, 0), "body", full_body))

        if not candidates:
            return "", "empty"
        _, source, text = max(candidates, key=lambda item: item[0])
        return text, source

    def _json_ld_metadata(self) -> dict[str, str]:
        metadata: dict[str, str] = {}
        for raw in self.json_ld_parts:
            for item in _iter_json_objects(raw):
                if not isinstance(item, dict):
                    continue
                article_body = _clean_text(str(item.get("articleBody") or item.get("text") or ""))
                if article_body and not metadata.get("article_body"):
                    metadata["article_body"] = article_body
                headline = _clean_text(str(item.get("headline") or item.get("name") or ""))
                if headline and not metadata.get("title"):
                    metadata["title"] = headline
                publish_date = _clean_text(str(item.get("datePublished") or item.get("dateCreated") or ""))
                if publish_date and not metadata.get("publish_date"):
                    metadata["publish_date"] = publish_date
                author = _json_ld_author(item.get("author"))
                if author and not metadata.get("author"):
                    metadata["author"] = author
        return metadata


def _iter_json_objects(raw: str):
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return
    stack = [data]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            yield item
            graph = item.get("@graph")
            if isinstance(graph, list):
                stack.extend(graph)
        elif isinstance(item, list):
            stack.extend(item)


def _json_ld_author(value) -> str:
    if isinstance(value, str):
        return _clean_text(value)
    if isinstance(value, dict):
        return _clean_text(str(value.get("name") or value.get("@id") or ""))
    if isinstance(value, list):
        names = [_json_ld_author(item) for item in value]
        return " / ".join(name for name in names if name)
    return ""


def _score_article_text(text: str, boost: int) -> int:
    clean = _clean_text(text)
    if not clean:
        return -10_000
    paragraph_count = max(1, len([p for p in clean.splitlines() if len(p.strip()) >= 20]))
    punctuation_count = len(re.findall(r"[。！？.!?]", clean))
    score = min(len(clean), MAX_EXTRACTED_CHARS) + paragraph_count * 60 + punctuation_count * 15 + boost
    lower = clean.lower()
    if any(token in lower for token in LOADING_TOKENS) and len(clean) < 500:
        score -= 800
    return score


def _clean_text(text: str) -> str:
    text = html.unescape(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _decode_html(raw: bytes, content_type: str = "") -> str:
    match = re.search(r"charset=([\w.-]+)", content_type, flags=re.I)
    encodings = [match.group(1)] if match else []
    head = raw[:4096].decode("ascii", errors="ignore")
    meta_match = re.search(r"<meta[^>]+charset=[\"']?([\w.-]+)", head, flags=re.I)
    if meta_match:
        encodings.append(meta_match.group(1))
    encodings.extend(["utf-8", "gb18030"])
    for encoding in encodings:
        try:
            return raw.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("utf-8", errors="replace")


def _extract_cookie_challenge(html_text: str) -> str | None:
    """解析已知的数字型 Cookie 验证页，不执行页面 JavaScript。"""
    if "__tst_status" not in html_text or "EO_Bot_Ssid" not in html_text:
        return None

    values: list[int] = []
    for name in ("WTKkN", "bOYDu", "wyeCN"):
        match = re.search(rf"\b{name}:(\d+)\b", html_text)
        if not match:
            return None
        values.append(int(match.group(1)))

    ssid_match = re.search(
        r"t=a\[[^\]]+\]\(t,(\d+)\)",
        html_text,
    )
    if not ssid_match:
        return None

    return (
        f"__tst_status={sum(values)}#; "
        f"EO_Bot_Ssid={ssid_match.group(1)}"
    )


def _fetch_url(url: str, extra_headers: dict[str, str] | None = None) -> tuple[bytes, str]:
    headers = dict(URL_HEADERS)
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read(MAX_URL_BYTES), resp.headers.get("Content-Type", "")


class Extractor:
    def extract(self, source: str, source_type: str = "auto") -> ExtractResult:
        try:
            if source_type == "auto":
                source_type = self._detect_type(source)

            if source_type == "url":
                return self._from_url(source)
            elif source_type == "pdf":
                return self._from_pdf(source)
            elif source_type == "image":
                return self._from_image(source)
            elif source_type == "doc":
                return self._from_doc(source)
            elif source_type == "text":
                return self._from_text(source)
            else:
                return ExtractResult(
                    success=False,
                    error=f"Unsupported source type: {source_type}",
                )
        except Exception as e:
            return ExtractResult(
                success=False,
                error=f"{type(e).__name__}: {e}",
            )

    def _detect_type(self, source: str) -> str:
        if source.startswith(("http://", "https://")):
            return "url"
        p = Path(source)
        if not p.exists():
            return "text"
        ext = p.suffix.lower()
        if ext == ".pdf":
            return "pdf"
        elif ext in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
            return "image"
        elif ext in {".docx", ".doc", ".md", ".txt"}:
            return "doc"
        return "text"

    # ---- 各类型实现 ----

    def _from_url(self, url: str) -> ExtractResult:
        raw, content_type = _fetch_url(url)
        decoded = _decode_html(raw, content_type)
        warnings: list[str] = []
        fallback_used = False

        challenge_cookie = _extract_cookie_challenge(decoded)
        if challenge_cookie:
            raw, content_type = _fetch_url(
                url,
                extra_headers={
                    "Cookie": challenge_cookie,
                    "Referer": url,
                },
            )
            decoded = _decode_html(raw, content_type)
            warnings.append("URL通过 JavaScript Cookie 验证后重试")
            fallback_used = True

        if "html" not in content_type.lower() and "<html" not in decoded[:1000].lower():
            body = _clean_text(decoded)
            if len(body) < MIN_EXTRACTED_CHARS:
                return ExtractResult(
                    success=False,
                    error=f"URL正文提取过短({len(body)}字),可能不是可读文本页面",
                    fallback_used=fallback_used,
                )
            return ExtractResult(
                success=True,
                content=ExtractedContent(
                    source_type="url",
                    origin=url,
                    title=None,
                    body=body[:MAX_EXTRACTED_CHARS].rstrip(),
                    extract_method="text_url",
                    warnings=warnings + ["URL返回非HTML内容,按纯文本处理"],
                ),
                fallback_used=fallback_used,
            )

        parser = _ArticleHTMLParser()
        parser.feed(decoded)
        parser.close()
        body = parser.body
        if len(body) < MIN_EXTRACTED_CHARS:
            return ExtractResult(
                success=False,
                error=f"URL正文提取过短({len(body)}字),可能是JS渲染页面或反爬限制",
                fallback_used=fallback_used,
            )
        if parser.selected_source == "json_ld":
            warnings.append("URL正文来自 JSON-LD articleBody")
        elif parser.selected_source == "content_block":
            warnings.append("URL正文使用页面正文候选区块")
        if len(body) > MAX_EXTRACTED_CHARS:
            body = body[:MAX_EXTRACTED_CHARS].rstrip()
            warnings.append(f"URL正文已截断到 {MAX_EXTRACTED_CHARS} 字")

        return ExtractResult(
            success=True,
            content=ExtractedContent(
                source_type="url",
                origin=url,
                title=parser.title,
                publish_date=parser.publish_date,
                author=parser.author,
                body=body,
                extract_method="html_parse",
                warnings=warnings,
            ),
            fallback_used=fallback_used,
        )

    def _from_pdf(self, path: str) -> ExtractResult:
        # 实际部署示例(伪代码):
        # import pdfplumber
        # with pdfplumber.open(path) as pdf:
        #     text = "\n".join(p.extract_text() or "" for p in pdf.pages)
        # if len(text.strip()) < 50:
        #     # 降级到 OCR
        #     text = self._ocr_pdf(path)
        #     return ExtractResult(success=True, fallback_used=True, content=...)
        return ExtractResult(
            success=True,
            content=ExtractedContent(
                source_type="pdf",
                origin=path,
                title=Path(path).stem,
                body="[TODO: 实现PDF提取]",
                extract_method="pdf_text",
            ),
        )

    def _from_image(self, path: str) -> ExtractResult:
        return ExtractResult(
            success=True,
            content=ExtractedContent(
                source_type="image",
                origin=path,
                title=None,
                body="[TODO: 实现图片OCR/VLM]",
                extract_method="vlm",
            ),
        )

    def _from_doc(self, path: str) -> ExtractResult:
        ext = Path(path).suffix.lower()
        if ext in {".md", ".txt"}:
            body = Path(path).read_text(encoding="utf-8")
        elif ext == ".docx":
            body = "[TODO: 实现DOCX提取]"
        else:
            body = "[TODO: 其他文档]"
        return ExtractResult(
            success=True,
            content=ExtractedContent(
                source_type="doc",
                origin=path,
                title=Path(path).stem,
                body=body,
                extract_method="plain",
            ),
        )

    def _from_text(self, text: str) -> ExtractResult:
        return ExtractResult(
            success=True,
            content=ExtractedContent(
                source_type="text",
                origin="(inline)",
                title=None,
                body=text,
                extract_method="plain",
            ),
        )
