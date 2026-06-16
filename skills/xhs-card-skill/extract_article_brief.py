"""Extract a structured article brief for the Visual Agent."""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List


SKILL_ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = SKILL_ROOT / "skill.json"


def extract_article_brief(raw_brief: str, config_path: Path = DEFAULT_CONFIG_PATH) -> Dict[str, Any]:
    config = _load_skill_config(config_path)
    extractor_config = config.get("brief_extraction", {})
    if not isinstance(extractor_config, dict):
        extractor_config = {}
    if extractor_config.get("enabled", True):
        try:
            return _normalize_article_brief(_call_ai_extractor(raw_brief, extractor_config))
        except Exception as exc:
            if not extractor_config.get("fail_open", True):
                raise
            fallback = _fallback_extract_article_brief(raw_brief)
            fallback["extractor_error"] = str(exc)
            return fallback
    return _fallback_extract_article_brief(raw_brief)


def _call_ai_extractor(raw_brief: str, extractor_config: Dict[str, Any]) -> Dict[str, Any]:
    env = _load_env()
    api_key_env = str(extractor_config.get("api_key_env", "DEEPSEEK_API_KEY"))
    api_key = env.get(api_key_env, "")
    if not api_key:
        raise RuntimeError("%s is required for article brief extraction" % api_key_env)
    base_url = env.get(
        str(extractor_config.get("base_url_env", "DEEPSEEK_BASE_URL")),
        str(extractor_config.get("default_base_url", "https://api.deepseek.com")),
    ).rstrip("/")
    model = env.get(str(extractor_config.get("model_env", "DEEPSEEK_TEXT_MODEL")), "") or str(
        extractor_config.get("default_model", "deepseek-v4-pro")
    )
    system_prompt = (
        "You extract structured briefs for a Xiaohongshu visual planning agent. "
        "Return strict JSON only. Do not return markdown. The response must be a JSON object."
    )
    user_prompt = (
        "Extract the article below into JSON fields: source_url, title, topic, core_hook, summary, "
        "key_points, entities, numbers, audience_angle. key_points must be 3-5 concise Chinese points. "
        "core_hook should be publishable as a Xiaohongshu hook and must preserve the main topic.\n\n"
        "Article brief:\n%s" % raw_brief
    )
    request_payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": float(extractor_config.get("temperature", 0.2)),
        "response_format": {"type": "json_object"},
    }
    request = urllib.request.Request(
        base_url + str(extractor_config.get("endpoint", "/chat/completions")),
        data=json.dumps(request_payload).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError("article brief extractor failed: HTTP %s %s" % (exc.code, body[:300]))
    content = _chat_completion_text(data)
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise RuntimeError("article brief extractor returned invalid JSON")
    return parsed


def _fallback_extract_article_brief(raw_brief: str) -> Dict[str, Any]:
    lines = [line.strip() for line in raw_brief.splitlines() if line.strip()]
    title = _line_value(lines, "标题")
    source_url = _line_value(lines, "来源 URL")
    body = _line_value(lines, "正文摘要") or _line_value(lines, "摘要")
    key_points = _key_points_from_text(body)
    entities = _entity_tokens(title + " " + body)
    numbers = _number_tokens(title + " " + body)
    core_hook = _core_hook(title, body, numbers)
    return _normalize_article_brief(
        {
            "source_url": source_url,
            "title": title,
            "topic": title.replace("_腾讯新闻", "") or _first_meaningful_phrase(body),
            "core_hook": core_hook,
            "summary": body[:180],
            "key_points": key_points,
            "entities": entities,
            "numbers": numbers,
            "audience_angle": "AI 工具玩家 / 内容创作者",
        }
    )


def _normalize_article_brief(data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "source_url": str(data.get("source_url", "")).strip(),
        "title": str(data.get("title", "")).strip(),
        "topic": str(data.get("topic", "")).strip(),
        "core_hook": str(data.get("core_hook", "")).strip(),
        "summary": str(data.get("summary", "")).strip(),
        "key_points": _string_list(data.get("key_points", []), 5),
        "entities": _string_list(data.get("entities", []), 8),
        "numbers": _string_list(data.get("numbers", []), 6),
        "audience_angle": str(data.get("audience_angle", "")).strip(),
    }


def _chat_completion_text(data: Dict[str, Any]) -> str:
    choices = data.get("choices", [])
    if not choices:
        raise RuntimeError("chat completion response missing choices")
    message = choices[0].get("message", {})
    content = message.get("content", "")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("chat completion response missing content")
    return content.strip()


def _load_skill_config(config_path: Path) -> Dict[str, Any]:
    data = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("skill config must be a JSON object")
    return data


def _load_env() -> Dict[str, str]:
    env_path = SKILL_ROOT.parents[1] / ".env"
    values: Dict[str, str] = {}
    if not env_path.exists():
        return values
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _line_value(lines: List[str], label: str) -> str:
    prefix = label + "："
    for line in lines:
        if line.startswith(prefix):
            return line.split("：", 1)[1].strip()
    return ""


def _key_points_from_text(body: str) -> List[str]:
    points: List[str] = []
    if "网页端" in body or "网页" in body:
        points.append("网页端一站式创建智能体角色")
    if "五个" in body or "5 步" in body or "五步" in body:
        points.append("配置流程被压缩成 5 个步骤")
    if "MCP" in body:
        points.append("模型、技能和 MCP 统一配置")
    if "SKILL.md" in body:
        points.append("技能以 SKILL.md 形式按需加载")
    if "Profile Builder" in body:
        points.append("Profile Builder 接管分散配置")
    return points[:4] or [_first_meaningful_phrase(body)]


def _entity_tokens(text: str) -> List[str]:
    entities: List[str] = []
    for token in ["Hermes Agent", "Profile Builder", "Nous Research", "MCP", "Skills Hub", "SKILL.md"]:
        if token in text and token not in entities:
            entities.append(token)
    return entities


def _number_tokens(text: str) -> List[str]:
    numbers = re.findall(r"\d+(?:\.\d+)?(?:\.\d+)*(?::\d+)?\s*(?:步|个|日|月|年|分钟|小时)?", text)
    return _unique([number.strip() for number in numbers if number.strip()])[:6]


def _core_hook(title: str, body: str, numbers: List[str]) -> str:
    if "Profile Builder" in title or "Profile Builder" in body:
        if any("5" in number for number in numbers) or "五" in body:
            return "5 步配置 AI 智能体"
        return "网页端配置 AI 智能体"
    return title[:18] if title else _first_meaningful_phrase(body)[:18]


def _first_meaningful_phrase(text: str) -> str:
    for part in re.split(r"[。！？!?；;\n]+", text):
        part = part.strip()
        if len(part) >= 6:
            return part[:40]
    return text[:40] or "文章核心信息"


def _string_list(value: Any, limit: int) -> List[str]:
    if not isinstance(value, list):
        return []
    return _unique([str(item).strip() for item in value if str(item).strip()])[:limit]


def _unique(values: List[str]) -> List[str]:
    result: List[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="raw brief text path")
    args = parser.parse_args()
    raw_brief = Path(args.input).read_text(encoding="utf-8")
    print(json.dumps(extract_article_brief(raw_brief), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
