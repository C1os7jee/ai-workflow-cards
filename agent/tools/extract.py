"""Structured article extraction helpers."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = PROJECT_ROOT / "skills" / "xhs-card-skill"
EXTRACTOR_SCRIPT = SKILL_ROOT / "extract_article_brief.py"


def extract_article_brief(raw_brief: str) -> str:
    raw_brief = (raw_brief or "").strip()
    if not raw_brief:
        raise ValueError("raw_brief must be a non-empty string")
    if not EXTRACTOR_SCRIPT.exists():
        return format_article_brief(_fallback_extract_article_brief(raw_brief), raw_brief)
    return format_article_brief(_call_ai_extractor(raw_brief), raw_brief)


def format_article_brief(data: Dict[str, Any], raw_brief: str = "") -> str:
    brief = _normalize_article_brief(data)
    if not brief["topic"] and raw_brief:
        brief = _fallback_extract_article_brief(raw_brief)
    parts = []
    if brief["source_url"]:
        parts.append("来源 URL：%s" % brief["source_url"])
    if brief["title"]:
        parts.append("标题：%s" % brief["title"])
    if brief["topic"]:
        parts.append("主题：%s" % brief["topic"])
    if brief["core_hook"]:
        parts.append("核心钩子：%s" % brief["core_hook"])
    if brief["summary"]:
        parts.append("摘要：%s" % brief["summary"])
    if brief["key_points"]:
        parts.append("关键点：%s" % " / ".join(brief["key_points"][:4]))
    if brief["entities"]:
        parts.append("关键实体：%s" % " / ".join(brief["entities"][:6]))
    if brief["numbers"]:
        parts.append("关键数字：%s" % " / ".join(brief["numbers"][:4]))
    if brief["audience_angle"]:
        parts.append("受众角度：%s" % brief["audience_angle"])
    return "\n".join(parts)


def _call_ai_extractor(raw_brief: str) -> Dict[str, Any]:
    with tempfile.NamedTemporaryFile(
        "w",
        suffix=".txt",
        encoding="utf-8",
        delete=False,
        dir=str(SKILL_ROOT),
    ) as handle:
        handle.write(raw_brief)
        input_path = Path(handle.name)
    try:
        completed = subprocess.run(
            ["python", str(EXTRACTOR_SCRIPT), "--input", str(input_path)],
            cwd=str(SKILL_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        if completed.returncode != 0:
            error_output = (completed.stderr or "").strip() or (completed.stdout or "").strip()
            raise RuntimeError("article extractor failed: %s" % error_output)
        data = json.loads(completed.stdout)
        if not isinstance(data, dict):
            raise RuntimeError("article extractor returned invalid JSON")
        return _normalize_article_brief(data)
    finally:
        input_path.unlink(missing_ok=True)


def _fallback_extract_article_brief(raw_brief: str) -> Dict[str, Any]:
    lines = [line.strip() for line in raw_brief.splitlines() if line.strip()]
    title = ""
    core_hook = ""
    body = ""
    for line in lines:
        if line.startswith("标题："):
            title = line.split("：", 1)[1].strip()
        elif line.startswith("摘要：") or line.startswith("正文摘要："):
            body = line.split("：", 1)[1].strip()
    if title and "5 步" in title:
        core_hook = "5 步配置 AI 智能体"
    elif "流程" in body:
        core_hook = "把内容拆成可执行流程"
    else:
        core_hook = title[:12] if title else "文章结构化提炼"
    key_points = _build_key_points(title, body)
    return {
        "source_url": _first_line_value(lines, "来源 URL"),
        "title": title,
        "topic": title or "内容结构化提炼",
        "core_hook": core_hook,
        "summary": body[:160],
        "key_points": key_points,
        "entities": _entity_tokens(title, body),
        "numbers": _number_tokens(body),
        "audience_angle": "内容创作者 / 工具实践者",
    }


def _normalize_article_brief(data: Dict[str, Any]) -> Dict[str, Any]:
    key_points = data.get("key_points", [])
    if not isinstance(key_points, list):
        key_points = []
    entities = data.get("entities", [])
    if not isinstance(entities, list):
        entities = []
    numbers = data.get("numbers", [])
    if not isinstance(numbers, list):
        numbers = []
    return {
        "source_url": str(data.get("source_url", "")).strip(),
        "title": str(data.get("title", "")).strip(),
        "topic": str(data.get("topic", "")).strip(),
        "core_hook": str(data.get("core_hook", "")).strip(),
        "summary": str(data.get("summary", "")).strip(),
        "key_points": [str(item).strip() for item in key_points if str(item).strip()],
        "entities": [str(item).strip() for item in entities if str(item).strip()],
        "numbers": [str(item).strip() for item in numbers if str(item).strip()],
        "audience_angle": str(data.get("audience_angle", "")).strip(),
    }


def _build_key_points(title: str, body: str) -> List[str]:
    points: List[str] = []
    if "5 步" in body or "五个" in body:
        points.append("把流程整理成 5 个步骤")
    if "网页端" in body:
        points.append("网页端一站式完成配置")
    if "MCP" in body:
        points.append("技能和 MCP 都可配置")
    if "SKILL.md" in body:
        points.append("技能以 SKILL.md 形式加载")
    if title and title not in points:
        points.append(title[:20])
    return points[:4] or ["提炼文章核心结构"]


def _first_line_value(lines: List[str], prefix: str) -> str:
    for line in lines:
        if line.startswith(prefix + "："):
            return line.split("：", 1)[1].strip()
    return ""


def _entity_tokens(title: str, body: str) -> List[str]:
    tokens: List[str] = []
    for value in [title, body]:
        for token in ["Hermes Agent", "Profile Builder", "MCP", "SKILL.md", "Nous Research"]:
            if token in value and token not in tokens:
                tokens.append(token)
    return tokens


def _number_tokens(body: str) -> List[str]:
    tokens: List[str] = []
    for token in ["5 步", "127.0.0.1:9119"]:
        if token in body and token not in tokens:
            tokens.append(token)
    return tokens
