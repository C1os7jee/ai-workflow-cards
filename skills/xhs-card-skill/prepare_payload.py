"""Prepare render payloads from a content brief using skill configuration."""

from __future__ import annotations

import argparse
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


SKILL_ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = SKILL_ROOT / "skill.json"

_CLAUSE_SPLIT_RE = re.compile(r"[。！？!?；;\n]+")
_SOFT_SPLIT_RE = re.compile(r"[，,、：:]+")
_TOKEN_RE = re.compile(r"\d+(?:\.\d+)?(?:%|[A-Za-z]+)?|[A-Za-z][A-Za-z0-9.+_-]*|[\u4e00-\u9fff]{2,}")


@dataclass(frozen=True)
class PreparedPayload:
    render_input: Dict[str, Any]
    visual: str
    slides_plan: List[str]


def prepare_payload(
    content_goal: str,
    strategy: str,
    config_path: Path = DEFAULT_CONFIG_PATH,
    image_provider: str = "",
    planner_mode: str = "",
) -> PreparedPayload:
    config = load_skill_config(config_path)
    strategy_config = _strategy_config(config, strategy)
    selected_image_provider = _selected_image_provider(config, image_provider)
    copy_rules = config.get("copy_rules", {})
    source = _normalize_text(content_goal)
    keywords = _extract_keywords(source, copy_rules)
    clauses = _extract_clauses(source)

    title = _render_template(
        strategy_config.get("cover_title_template", "{lead}关键拆解"),
        _template_context(keywords, clauses),
        copy_rules,
        15,
    )
    hook = _render_template(
        strategy_config.get("cover_hook_template", "{number} 是关键变化"),
        _template_context(keywords, clauses),
        copy_rules,
        30,
    )
    slide_items = _build_slide_items(clauses, keywords, copy_rules)
    slides = [
        {
            "type": "cover",
            "title": title,
            "hook": hook,
        }
    ]
    slides.extend(_content_slide(item) for item in slide_items)
    slides.append(
        {
            "type": "cta",
            "text": _render_template(
                config.get("cta_template", "收藏这张 {lead} 卡"),
                _template_context(keywords, clauses),
                copy_rules,
                20,
            ),
        }
    )
    visual = _render_template(
        strategy_config.get("cover_visual_template", "{lead} / {secondary} 关系图"),
        _template_context(keywords, clauses),
        copy_rules,
        60,
    )
    visual_blueprint = _build_visual_blueprint(
        source=source,
        keywords=keywords,
        clauses=clauses,
        slides=slides,
        strategy=strategy,
        visual=visual,
        config=config,
        planner_mode=planner_mode,
    )
    render_input = {
        "style": strategy_config.get("style", "swiss"),
        "theme": strategy_config.get("theme", "IKB"),
        "layout_id": strategy_config.get("layout_id", "S12"),
        "visual_direction": visual,
        "visual_blueprint": visual_blueprint,
        "slides": slides,
    }
    if selected_image_provider:
        render_input["image_provider"] = selected_image_provider
    return PreparedPayload(
        render_input=render_input,
        visual=visual,
        slides_plan=slide_items,
    )


def load_skill_config(config_path: Path = DEFAULT_CONFIG_PATH) -> Dict[str, Any]:
    data = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("skill config must be a JSON object")
    return data


def load_env() -> Dict[str, str]:
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


def _strategy_config(config: Dict[str, Any], strategy: str) -> Dict[str, Any]:
    strategies = config.get("strategies", {})
    if not isinstance(strategies, dict):
        raise ValueError("skill config strategies must be an object")
    selected = strategies.get(strategy) or strategies.get("default")
    if not isinstance(selected, dict):
        raise ValueError("skill config missing strategy: %s" % strategy)
    return selected


def _selected_image_provider(config: Dict[str, Any], requested_provider: str) -> str:
    image_generation = config.get("image_generation", {})
    if not isinstance(image_generation, dict) or not image_generation.get("enabled"):
        return requested_provider.strip()
    providers = image_generation.get("providers", {})
    provider = requested_provider.strip()
    if provider:
        if isinstance(providers, dict) and providers and provider not in providers:
            raise ValueError("unknown image provider: %s" % provider)
        return provider
    default_provider = image_generation.get("default_provider") or image_generation.get("provider")
    return str(default_provider or "").strip()


def _build_visual_blueprint(
    source: str,
    keywords: List[str],
    clauses: List[str],
    slides: List[Dict[str, Any]],
    strategy: str,
    visual: str,
    config: Dict[str, Any],
    planner_mode: str = "",
) -> Dict[str, Any]:
    deck_config = config.get("deck_generation", {})
    if not isinstance(deck_config, dict):
        deck_config = {}
    mode = str(deck_config.get("mode", "direct-image-deck"))
    min_cards = max(1, int(deck_config.get("min_cards", 2)))
    max_cards = max(min_cards, int(deck_config.get("max_cards", 4)))
    target_cards = min(max_cards, max(min_cards, _suggest_card_count(clauses, keywords)))
    context = _template_context(keywords, clauses)
    jobs = []
    source_details = _source_details(clauses, source, target_cards)
    roles = _deck_roles(target_cards)
    prompt_template = str(deck_config.get("prompt_template", "{title}. {message}. {visual_direction}"))
    ai_blueprint = _try_ai_visual_blueprint(
        source=source,
        strategy=strategy,
        visual=visual,
        deck_config=deck_config,
        prompt_template=prompt_template,
        min_cards=min_cards,
        max_cards=max_cards,
        planner_mode=planner_mode,
    )
    planner_error = ""
    if ai_blueprint and ai_blueprint.get("image_jobs"):
        return ai_blueprint
    if ai_blueprint:
        planner_error = str(ai_blueprint.get("planner_error", ""))
    for index in range(target_cards):
        title, message = _card_copy_for(index, slides, source_details[index], context)
        prompt_context = {
            "role": roles[index],
            "title": title,
            "message": message,
            "source_detail": source_details[index],
            "visual_direction": visual,
            "strategy": strategy,
            "lead": context["lead"],
            "secondary": context["secondary"],
            "number": context["number"],
        }
        jobs.append(
            {
                "id": "card_%02d" % (index + 1),
                "role": roles[index],
                "title": title,
                "message": message,
                "source_detail": source_details[index],
                "prompt": _format_template(prompt_template, prompt_context),
                "output_name": "card_%02d.png" % (index + 1),
            }
        )
    blueprint = {
        "mode": mode,
        "planner": "skill",
        "strategy": strategy,
        "target_cards": target_cards,
        "visual_direction": visual,
        "image_jobs": jobs,
    }
    if planner_error:
        blueprint["planner_error"] = planner_error
    return blueprint


def _try_ai_visual_blueprint(
    source: str,
    strategy: str,
    visual: str,
    deck_config: Dict[str, Any],
    prompt_template: str,
    min_cards: int,
    max_cards: int,
    planner_mode: str,
) -> Optional[Dict[str, Any]]:
    planner_config = deck_config.get("planner", {})
    if not isinstance(planner_config, dict) or not planner_config.get("enabled", True):
        return None
    selected_mode = (planner_mode or str(planner_config.get("default_mode", "skill"))).strip().lower()
    if selected_mode not in {"ai", "llm", "model"}:
        return None
    try:
        jobs = _call_ai_planner(
            source=source,
            strategy=strategy,
            visual=visual,
            planner_config=planner_config,
            prompt_template=prompt_template,
            min_cards=min_cards,
            max_cards=max_cards,
        )
    except Exception as exc:
        if not planner_config.get("fail_open", True):
            raise
        return {
            "planner": "skill",
            "planner_error": str(exc),
            "image_jobs": [],
        }
    return {
        "mode": str(deck_config.get("mode", "direct-image-deck")),
        "planner": "ai",
        "strategy": strategy,
        "target_cards": len(jobs),
        "visual_direction": visual,
        "image_jobs": jobs,
    }


def _call_ai_planner(
    source: str,
    strategy: str,
    visual: str,
    planner_config: Dict[str, Any],
    prompt_template: str,
    min_cards: int,
    max_cards: int,
) -> List[Dict[str, str]]:
    env = load_env()
    api_key_env = str(planner_config.get("api_key_env", "DEEPSEEK_API_KEY"))
    api_key = env.get(api_key_env, "")
    if not api_key:
        raise RuntimeError("%s is required for DeepSeek visual planning" % api_key_env)
    base_url = env.get(
        str(planner_config.get("base_url_env", "DEEPSEEK_BASE_URL")),
        str(planner_config.get("default_base_url", "https://api.deepseek.com")),
    ).rstrip("/")
    model = env.get(str(planner_config.get("model_env", "DEEPSEEK_TEXT_MODEL")), "") or str(
        planner_config.get("default_model", "deepseek-v4-pro")
    )
    system_prompt = (
        "You are the visual director for a Xiaohongshu image-generation agent. "
        "Decide how many final publishable card images are needed and what each image should contain. "
        "Return strict JSON only. Do not return markdown. The response must be a JSON object."
    )
    user_prompt = (
        "Content brief:\n%s\n\nRecommended strategy: %s\nVisual direction seed: %s\n\n"
        "Choose %s-%s cards. Each card must be a final generated image, not an HTML layout. "
        "Return a JSON object with key image_jobs. Each item needs id, role, title, message, source_detail, visual_direction. "
        "Roles should be specific, such as cover, mechanism, evidence, comparison, takeaway."
        % (source, strategy, visual, min_cards, max_cards)
    )
    request_payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": float(planner_config.get("temperature", 0.35)),
        "response_format": {"type": "json_object"},
    }
    url = base_url + str(planner_config.get("endpoint", "/chat/completions"))
    request = urllib.request.Request(
        url,
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
        raise RuntimeError("DeepSeek visual planner failed: HTTP %s %s" % (exc.code, body[:300]))
    except urllib.error.URLError as exc:
        raise RuntimeError("DeepSeek visual planner failed: %s" % exc)
    content = _chat_completion_text(data)
    parsed = json.loads(content)
    jobs = parsed.get("image_jobs", [])
    if not isinstance(jobs, list):
        raise RuntimeError("AI visual planner response missing image_jobs")
    normalized_jobs = []
    for index, job in enumerate(jobs[:max_cards], start=1):
        if not isinstance(job, dict):
            continue
        title = str(job.get("title", "")).strip()
        message = str(job.get("message", "")).strip()
        source_detail = str(job.get("source_detail", "")).strip()
        role = str(job.get("role", "card")).strip()
        if not title or not message:
            continue
        prompt_context = {
            "role": role,
            "title": title,
            "message": message,
            "source_detail": source_detail or source,
            "visual_direction": str(job.get("visual_direction", visual)).strip() or visual,
            "strategy": strategy,
            "lead": title,
            "secondary": message,
            "number": "",
        }
        normalized_jobs.append(
            {
                "id": str(job.get("id", "card_%02d" % index)),
                "role": role,
                "title": title,
                "message": message,
                "source_detail": source_detail or source,
                "prompt": _format_template(prompt_template, prompt_context),
                "output_name": "card_%02d.png" % index,
            }
        )
    if len(normalized_jobs) < min_cards:
        raise RuntimeError("AI visual planner returned too few usable image jobs")
    return normalized_jobs


def _chat_completion_text(data: Dict[str, Any]) -> str:
    choices = data.get("choices", [])
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("AI visual planner response missing choices")
    first = choices[0]
    if not isinstance(first, dict):
        raise RuntimeError("AI visual planner choice is invalid")
    message = first.get("message", {})
    if not isinstance(message, dict):
        raise RuntimeError("AI visual planner message is invalid")
    content = message.get("content", "")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("AI visual planner returned empty content")
    return content


def _suggest_card_count(clauses: List[str], keywords: List[str]) -> int:
    if len(clauses) >= 5 or len(keywords) >= 8:
        return 4
    if len(clauses) >= 3 or len(keywords) >= 5:
        return 3
    return 2


def _source_details(clauses: List[str], source: str, count: int) -> List[str]:
    details = [clause for clause in clauses if clause]
    if not details:
        details = [source or "把内容做成一组可发布小红书视觉卡"]
    while len(details) < count:
        details.append(details[-1])
    return details[:count]


def _deck_roles(count: int) -> List[str]:
    if count <= 2:
        return ["cover", "takeaway"]
    if count == 3:
        return ["cover", "mechanism", "takeaway"]
    return ["cover", "mechanism", "evidence", "takeaway"]


def _card_copy_for(
    index: int,
    slides: List[Dict[str, Any]],
    source_detail: str,
    context: Dict[str, str],
) -> tuple[str, str]:
    if index == 0 and slides:
        cover = slides[0]
        return str(cover.get("title", context["lead"])), str(cover.get("hook", context["first_clause"]))
    content_slides = [slide for slide in slides if slide.get("type") == "content"]
    content_index = index - 1
    if 0 <= content_index < len(content_slides):
        slide = content_slides[content_index]
        points = slide.get("points", [])
        if not isinstance(points, list):
            points = []
        return str(slide.get("heading", context["lead"])), " / ".join(str(point) for point in points if point)
    return context["lead"], source_detail


def _format_template(template: str, context: Dict[str, str]) -> str:
    rendered = str(template)
    for key, value in context.items():
        rendered = rendered.replace("{%s}" % key, str(value))
    return rendered


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def _extract_keywords(text: str, copy_rules: Dict[str, Any]) -> List[str]:
    seen = set()
    named_keywords = []
    numeric_keywords = []
    low_value = set(copy_rules.get("stopwords", []))
    for match in _TOKEN_RE.finditer(text):
        token = match.group(0).strip()
        if not token or token in seen or token in low_value:
            continue
        seen.add(token)
        if re.search(r"\d", token):
            numeric_keywords.append(token)
        else:
            named_keywords.append(token)
    keyword_limit = int(copy_rules.get("keyword_limit", 13))
    name_limit = int(copy_rules.get("named_keyword_limit", 7))
    numeric_limit = int(copy_rules.get("numeric_keyword_limit", 6))
    return (named_keywords[:name_limit] + numeric_keywords[:numeric_limit])[:keyword_limit]


def _extract_clauses(text: str) -> List[str]:
    clauses = []
    for part in _CLAUSE_SPLIT_RE.split(text):
        part = part.strip(" -")
        if not part:
            continue
        if len(part) <= 26:
            clauses.append(part)
            continue
        clauses.extend(item.strip(" -") for item in _SOFT_SPLIT_RE.split(part) if item.strip(" -"))
    return clauses[:8]


def _template_context(keywords: List[str], clauses: List[str]) -> Dict[str, str]:
    return {
        "lead": keywords[0] if keywords else (clauses[0] if clauses else "内容"),
        "secondary": keywords[1] if len(keywords) > 1 else "核心信息",
        "third": keywords[2] if len(keywords) > 2 else "关键点",
        "number": _best_numeric_keyword(keywords, clauses) or "重点",
        "first_clause": clauses[0] if clauses else "把重点做成可发布组图",
    }


def _render_template(
    template: str,
    context: Dict[str, str],
    copy_rules: Dict[str, Any],
    limit: int,
) -> str:
    rendered = template
    for key, value in context.items():
        rendered = rendered.replace("{%s}" % key, value)
    return _limit_text(rendered, limit, bool(copy_rules.get("avoid_broken_latin_tokens", True)))


def _build_slide_items(
    clauses: List[str],
    keywords: List[str],
    copy_rules: Dict[str, Any],
) -> List[str]:
    items = []
    for index, clause in enumerate(clauses[:3]):
        heading = _heading_for(index, clause, keywords, copy_rules)
        point_a = _compact_clause(clause, keywords, 20, copy_rules)
        point_b = _supporting_point(index, keywords, clause, copy_rules)
        items.append("%s：%s｜%s" % (heading, point_a, point_b))
    while len(items) < 3:
        index = len(items)
        keyword = keywords[index] if index < len(keywords) else "核心信息"
        items.append(
            "%s：%s｜%s"
            % (
                _heading_for(index, keyword, keywords, copy_rules),
                _compact_clause(keyword, keywords, 20, copy_rules),
                _supporting_point(index, keywords, keyword, copy_rules),
            )
        )
    return items[:3]


def _content_slide(item: str) -> Dict[str, Any]:
    if "｜" in item:
        lead, support = item.split("｜", 1)
    else:
        lead, support = item, "继续看下一步"
    if "：" in lead:
        heading, first_point = lead.split("：", 1)
    else:
        heading, first_point = lead[:12], lead[:20]
    return {
        "type": "content",
        "heading": heading[:12],
        "points": [first_point[:20], support[:20]],
    }


def _heading_for(
    index: int,
    clause: str,
    keywords: List[str],
    copy_rules: Dict[str, Any],
) -> str:
    if index == 0 and keywords:
        return _limit_text(keywords[0], 12, bool(copy_rules.get("avoid_broken_latin_tokens", True)))
    names = copy_rules.get("section_headings", ["机制", "证据", "价值"])
    if index < len(names):
        return str(names[index])[:12]
    return clause[:12]


def _supporting_point(
    index: int,
    keywords: List[str],
    clause: str,
    copy_rules: Dict[str, Any],
) -> str:
    if index == 0 and len(keywords) > 1:
        return _limit_text("关联 %s" % keywords[1], 20, bool(copy_rules.get("avoid_broken_latin_tokens", True)))
    if index == 1:
        numeric = _best_numeric_keyword(keywords, [clause])
        if numeric:
            return _limit_text("关键数字 %s" % numeric, 20, True)
    if index == 2 and len(keywords) > 2:
        return _limit_text("落点 %s" % keywords[2], 20, bool(copy_rules.get("avoid_broken_latin_tokens", True)))
    return _limit_text(clause, 20, bool(copy_rules.get("avoid_broken_latin_tokens", True)))


def _compact_clause(
    clause: str,
    keywords: List[str],
    limit: int,
    copy_rules: Dict[str, Any],
) -> str:
    present_keywords = [word for word in keywords if word in clause]
    latin_or_number = [word for word in present_keywords if _has_latin_or_digit(word)]
    if len(latin_or_number) >= 2:
        return _limit_text(" ".join(latin_or_number[:3]), limit, True)
    if latin_or_number and "提出" in clause:
        return _limit_text("%s 提出 %s" % (latin_or_number[0], _next_keyword(latin_or_number[0], keywords)), limit, True)
    if latin_or_number and ("减少" in clause or "加速" in clause):
        action = "计算减少" if "减少" in clause else "端到端加速"
        return _limit_text("%s %s" % (latin_or_number[-1], action), limit, True)
    return _limit_text(clause, limit, bool(copy_rules.get("avoid_broken_latin_tokens", True)))


def _next_keyword(current: str, keywords: List[str]) -> str:
    try:
        index = keywords.index(current)
    except ValueError:
        return "关键机制"
    for keyword in keywords[index + 1 :]:
        if _has_latin_or_digit(keyword):
            return keyword
    return "关键机制"


def _has_latin_or_digit(text: str) -> bool:
    return bool(re.search(r"[A-Za-z0-9]", text))


def _best_numeric_keyword(keywords: List[str], clauses: List[str]) -> str:
    numbers = [word for word in keywords if re.search(r"\d", word)]
    if not numbers:
        return ""
    for clause in clauses:
        if any(word in clause for word in ["减少", "降低", "节省"]):
            clause_numbers = [number for number in numbers if number in clause]
            decimal = next((number for number in clause_numbers if "." in number), "")
            if decimal:
                return decimal
            if clause_numbers:
                return clause_numbers[-1]
    decimal = next((number for number in numbers if "." in number), "")
    if decimal:
        return decimal
    return numbers[0]


def _limit_text(text: str, limit: int, avoid_broken_latin_tokens: bool) -> str:
    cleaned = _normalize_text(text)
    if len(cleaned) <= limit:
        return cleaned
    trimmed = cleaned[:limit].rstrip()
    if avoid_broken_latin_tokens and re.search(r"[A-Za-z0-9.]$", trimmed):
        token_match = re.search(r"[A-Za-z0-9.]+$", trimmed)
        if token_match and token_match.start() > 0:
            trimmed = trimmed[: token_match.start()].rstrip()
    return trimmed or cleaned[:limit]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="brief payload JSON path")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="skill config path")
    args = parser.parse_args()

    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    result = prepare_payload(
        content_goal=str(payload.get("content_goal", "")),
        strategy=str(payload.get("strategy", "default")),
        config_path=Path(args.config),
        image_provider=str(payload.get("image_provider", "")),
        planner_mode=str(payload.get("planner_mode", "")),
    )
    print(
        json.dumps(
            {
                "render_input": result.render_input,
                "visual": result.visual,
                "slides_plan": result.slides_plan,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
