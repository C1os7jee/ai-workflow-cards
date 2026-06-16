"""Render helpers backed by guizang-social-card-skill.

The Agent layer keeps the project contract stable. This module adapts
VisualAgent output into a small guizang HTML deck, then renders each `.poster`
node to PNG with Playwright.
"""

from __future__ import annotations

import html
import json
import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from agent.schemas import RenderInput, RenderSlide, VisualPlan
from agent.tools.layouts import get_strategy_preset


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = PROJECT_ROOT / "skills" / "guizang-social-card-skill"
SWISS_TEMPLATE = SKILL_ROOT / "assets" / "template-swiss-card.html"
EDITORIAL_TEMPLATE = SKILL_ROOT / "assets" / "template-editorial-card.html"
VALIDATOR = SKILL_ROOT / "validate-social-deck.mjs"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "output"


SWISS_ACCENTS = {
    "ikb": "ikb",
    "IKB": "ikb",
    "lemon": "lemon-yellow",
    "lemon-yellow": "lemon-yellow",
    "lemon-green": "lemon-green",
    "forest": "lemon-green",
    "safety-orange": "safety-orange",
    "orange": "safety-orange",
}

EDITORIAL_THEMES = {
    "ink-classic": "ink-classic",
    "IKB": "indigo-porcelain",
    "indigo": "indigo-porcelain",
    "indigo-porcelain": "indigo-porcelain",
    "forest": "forest-ink",
    "forest-ink": "forest-ink",
    "kraft": "kraft-paper",
    "kraft-paper": "kraft-paper",
    "dune": "dune",
    "midnight": "midnight-ink",
    "midnight-ink": "midnight-ink",
    "lemon": "ink-classic",
}


def prepare_render_plan(
    content_goal: str,
    strategy: str,
    image_provider: str = "",
    planner_mode: str = "",
) -> Dict[str, Any]:
    """Build the render payload expected by the rest of the Agent layer."""
    preset = get_strategy_preset(strategy)
    clauses = _extract_clauses(content_goal)
    keywords = _extract_keywords(content_goal)
    slides = _build_slides(content_goal, preset, clauses, keywords)
    visual_blueprint = _build_visual_blueprint(slides, preset, content_goal)
    render_input = {
        "style": preset.style,
        "theme": preset.theme,
        "layout_id": preset.layout_id,
        "visual_direction": _fill_template(preset.cover_visual, keywords, clauses),
        "image_provider": image_provider,
        "visual_blueprint": visual_blueprint,
        "slides": slides,
    }
    return {
        "render_input": render_input,
        "visual": render_input["visual_direction"],
        "slides_plan": _slides_plan(slides),
        "planner_mode": planner_mode or "guizang-template",
    }


def build_render_input(plan: VisualPlan) -> RenderInput:
    prepared = prepare_render_plan(
        content_goal=plan.content_goal,
        strategy=plan.recommended_strategy,
        image_provider=plan.image_provider,
    )
    return build_render_input_from_payload(prepared["render_input"])


def build_render_input_from_payload(payload: Dict[str, Any]) -> RenderInput:
    slides = [_slide_from_dict(slide) for slide in payload["slides"]]
    return RenderInput(
        style=str(payload["style"]),
        theme=str(payload["theme"]),
        layout_id=str(payload["layout_id"]),
        slides=slides,
        visual_direction=str(payload.get("visual_direction", "")),
        image_provider=str(payload.get("image_provider", "")),
        visual_blueprint=payload.get("visual_blueprint", {})
        if isinstance(payload.get("visual_blueprint", {}), dict)
        else {},
    ).validate()


def _slide_from_dict(slide: Dict[str, Any]) -> RenderSlide:
    slide_type = str(slide.get("type", ""))
    if slide_type == "cover":
        return RenderSlide(
            type="cover",
            title=str(slide.get("title", "")),
            hook=str(slide.get("hook", "")),
        )
    if slide_type == "content":
        points = slide.get("points", [])
        if not isinstance(points, list):
            points = []
        return RenderSlide(
            type="content",
            heading=str(slide.get("heading", "")),
            points=[str(point) for point in points],
        )
    return RenderSlide(type="cta", text=str(slide.get("text", "")))


def render_input_to_dict(render_input: RenderInput) -> Dict[str, object]:
    return render_input.to_dict()


def render_xiaohongshu(
    render_input: RenderInput,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> Dict[str, object]:
    """Render a Xiaohongshu deck through guizang-social-card-skill templates."""
    payload = render_input.to_dict()
    _assert_guizang_skill_ready()
    task_dir = _new_task_dir(output_root)
    task_dir.mkdir(parents=True, exist_ok=False)
    (task_dir / "render_input.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    index_path = task_dir / "index.html"
    index_path.write_text(_build_deck_html(render_input), encoding="utf-8")
    result = _render_with_playwright(index_path, task_dir)
    png_paths = result["png_paths"]
    render_result = {
        "success": True,
        "png_paths": png_paths,
        "task_dir": str(task_dir),
        "html_path": str(index_path),
        "skill": "guizang-social-card-skill",
        "generated_assets": {
            "deck_images": png_paths,
            "html": str(index_path),
        },
    }
    validator_result = _run_validator(task_dir)
    if validator_result:
        render_result["validation"] = validator_result
    (task_dir / "render_result.json").write_text(
        json.dumps(render_result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return render_result


def _assert_guizang_skill_ready() -> None:
    if not SKILL_ROOT.exists():
        raise FileNotFoundError("missing guizang social card skill: %s" % SKILL_ROOT)
    if not SWISS_TEMPLATE.exists() or not EDITORIAL_TEMPLATE.exists():
        raise FileNotFoundError("missing guizang seed templates under %s" % SKILL_ROOT)


def _build_deck_html(render_input: RenderInput) -> str:
    style = render_input.style.strip().lower()
    if style == "editorial":
        template_path = EDITORIAL_TEMPLATE
        attr_name = "data-theme"
        attr_value = EDITORIAL_THEMES.get(render_input.theme, "ink-classic")
        posters = _build_editorial_posters(render_input)
    else:
        template_path = SWISS_TEMPLATE
        attr_name = "data-accent"
        attr_value = SWISS_ACCENTS.get(render_input.theme, "ikb")
        posters = _build_swiss_posters(render_input)
    template = template_path.read_text(encoding="utf-8")
    template = re.sub(r'<html lang="zh-CN" [^>]*>', f'<html lang="zh-CN" {attr_name}="{attr_value}">', template, count=1)
    return _replace_placeholder_block(template, "\n".join(posters))


def _replace_placeholder_block(template: str, posters_html: str) -> str:
    marker = "    <!-- POSTERS_HERE -->"
    marker_index = template.find(marker)
    if marker_index < 0:
        raise RuntimeError("guizang template is missing POSTERS_HERE marker")
    start = marker_index
    placeholder_start = template.find("    <!-- ============================================================", marker_index)
    if placeholder_start < 0:
        placeholder_start = marker_index + len(marker)
    end = template.find("  </main>", placeholder_start)
    if end < 0:
        raise RuntimeError("guizang template is missing closing main")
    return template[:start] + "    <!-- POSTERS_HERE -->\n" + posters_html + "\n\n" + template[end:]


def _build_swiss_posters(render_input: RenderInput) -> List[str]:
    posters = []
    content_index = 0
    for index, slide in enumerate(render_input.slides, start=1):
        poster_id = "xhs-%02d" % index
        if slide.type == "cover":
            posters.append(_swiss_cover(poster_id, slide, render_input, index))
        elif slide.type == "content":
            content_index += 1
            posters.append(
                _swiss_content(poster_id, slide, render_input, index, content_index)
            )
        else:
            posters.append(_swiss_cta(poster_id, slide, render_input, index))
    return posters


def _build_editorial_posters(render_input: RenderInput) -> List[str]:
    posters = []
    for index, slide in enumerate(render_input.slides, start=1):
        poster_id = "xhs-%02d" % index
        if slide.type == "cover":
            posters.append(_editorial_cover(poster_id, slide, render_input, index))
        elif slide.type == "content":
            posters.append(_editorial_content(poster_id, slide, render_input, index))
        else:
            posters.append(_editorial_cta(poster_id, slide, render_input, index))
    return posters


def _swiss_cover(poster_id: str, slide: RenderSlide, render_input: RenderInput, index: int) -> str:
    hook = slide.hook or render_input.visual_direction or "一组可复用的内容工作流卡片"
    signal_points = _ensure_point_count([hook], render_input, 4)
    metric = _primary_metric(_deck_text(render_input)) or "%02d" % len(render_input.slides)
    return f"""    <section class="poster xhs" id="{poster_id}">
      <div class="dot-mat"></div>
      <div class="content stack gap-8">
        <div class="chrome-min">
          <span>{_esc(render_input.layout_id)} · Guizang</span>
          <span>{_esc(_deck_date())}</span>
        </div>
        <div class="grid-12">
          <div class="span-8 stack gap-5">
            <p class="t-cat">Cover · S01</p>
            <h1 class="h-statement">{_break_title(slide.title or "")}</h1>
          </div>
          <div class="span-4 stack gap-5">
            <div class="card-fill stack gap-4">
              <p class="t-meta">Signal 01</p>
              <p class="lead">{_esc(signal_points[0])}</p>
            </div>
            <div class="card-outlined stack gap-4">
              <p class="t-meta">Signal 02</p>
              <p class="lead">{_esc(signal_points[1])}</p>
            </div>
          </div>
        </div>
        <div class="grid-12">
          <div class="span-6 card-ink stack gap-4">
            <p class="t-meta">Core Message</p>
            <p class="h-md">{_esc(signal_points[2])}</p>
          </div>
          <div class="span-6 card-fill stack gap-4">
            <p class="t-meta">Visual Direction</p>
            <p class="lead">{_esc(render_input.visual_direction or signal_points[3])}</p>
          </div>
        </div>
        <div class="hero-stat-bottom">
          <div>
            <p class="t-cat">Deck · Ready</p>
            <p class="lead">从 brief 到 PNG，保留结构、证据和人工审核入口。</p>
          </div>
          <p class="num-mega">{_esc(metric)}</p>
        </div>
      </div>
    </section>"""


def _swiss_content(
    poster_id: str,
    slide: RenderSlide,
    render_input: RenderInput,
    index: int,
    content_index: int,
) -> str:
    recipe = _select_swiss_recipe(render_input, slide, content_index)
    if recipe == "S06":
        return _swiss_pipeline(poster_id, slide, render_input, index)
    if recipe == "S09":
        return _swiss_kpi_tower(poster_id, slide, render_input, index)
    if recipe == "S10":
        return _swiss_h_bar(poster_id, slide, render_input, index)
    if recipe == "S11":
        return _swiss_stacked_ledger(poster_id, slide, render_input, index)
    if recipe == "S12":
        return _swiss_matrix(poster_id, slide, render_input, index)
    return _swiss_file_card(poster_id, slide, render_input, index)


def _swiss_pipeline(poster_id: str, slide: RenderSlide, render_input: RenderInput, index: int) -> str:
    steps = _ensure_point_count(slide.points, render_input, 3)
    step_html = []
    for step_index, step in enumerate(steps[:3], start=1):
        step_html.append(
            f"""          <div class="card-fill stack gap-5">
            <p class="num-xl">{step_index:02d}</p>
            <p class="t-meta">{_esc(_pipeline_label(step, step_index))}</p>
            <p class="lead">{_esc(_shorten(step, 22))}</p>
          </div>"""
        )
    return f"""    <section class="poster xhs" id="{poster_id}">
      <div class="cross-mat"></div>
      <div class="content" style="display:grid; grid-template-rows:auto auto 1fr auto; row-gap:32px">
        <div class="chrome-min">
          <span>S06 · Pipeline</span>
          <span>Card {index:02d}</span>
        </div>
        <div class="stack gap-4">
          <p class="t-cat">Workflow · Architecture</p>
          <h2 class="h-xl">{_break_title(slide.heading or "流程拆解")}</h2>
        </div>
        <div class="grid-3" style="height:100%">
{chr(10).join(step_html)}
        </div>
        <div class="hero-stat-bottom">
          <div>
            <p class="t-cat">Output · PNG</p>
            <p class="lead">{_esc(render_input.visual_direction or "流程被拆成可审核的连续节点。")}</p>
          </div>
          <p class="num-mega">{len(steps[:3])}</p>
        </div>
      </div>
    </section>"""


def _swiss_kpi_tower(poster_id: str, slide: RenderSlide, render_input: RenderInput, index: int) -> str:
    items = _kpi_items(render_input, slide)
    cols = []
    for item_index, item in enumerate(items, start=1):
        muted = " muted" if item_index == len(items) else ""
        cols.append(
            f"""          <div class="tower-col{muted}">
            <p class="num">{_esc(item["num"])}</p>
            <p class="lbl">{_esc(item["label"])}</p>
            <div class="bar-tower" style="--h:{item["height"]}px"></div>
          </div>"""
        )
    return f"""    <section class="poster xhs" id="{poster_id}">
      <div class="dot-mat"></div>
      <div class="content" style="display:grid; grid-template-rows:auto auto auto 1fr; row-gap:32px">
        <div class="chrome-min">
          <span>S09 · KPI Tower</span>
          <span>Card {index:02d}</span>
        </div>
        <p class="t-cat">Data · Signals</p>
        <h2 class="h-xl">{_break_title(slide.heading or "关键数字")}</h2>
        <div class="kpi-tower-row" style="height:100%">
{chr(10).join(cols)}
        </div>
      </div>
    </section>"""


def _swiss_h_bar(poster_id: str, slide: RenderSlide, render_input: RenderInput, index: int) -> str:
    rows = _ensure_point_count(slide.points, render_input, 6)
    metrics = _metric_tokens(_deck_text(render_input))
    widths = [94, 82, 70, 58, 46, 34]
    row_html = []
    for row_index, row in enumerate(rows[:6], start=1):
        value = metrics[row_index - 1] if row_index <= len(metrics) else "%02d" % row_index
        row_html.append(
            f"""          <div class="bar-row">
            <div class="row-lbl">{_esc(_shorten(row, 16))}</div>
            <div class="row-track"><div class="row-fill" style="--w:{widths[row_index - 1]}%"></div></div>
            <div class="row-val">{_esc(value)}</div>
          </div>"""
        )
    return f"""    <section class="poster xhs" id="{poster_id}">
      <div class="ring-mat"></div>
      <div class="content" style="display:grid; grid-template-rows:auto auto auto 1fr; row-gap:32px">
        <div class="chrome-min">
          <span>S10 · H-Bar</span>
          <span>Card {index:02d}</span>
        </div>
        <p class="t-cat">Ranking · Comparison</p>
        <h2 class="h-xl">{_break_title(slide.heading or "优先级排序")}</h2>
        <div class="h-bar-chart" style="align-self:center">
{chr(10).join(row_html)}
        </div>
      </div>
    </section>"""


def _swiss_stacked_ledger(poster_id: str, slide: RenderSlide, render_input: RenderInput, index: int) -> str:
    rows = _ensure_point_count(slide.points, render_input, 4)
    metrics = _metric_tokens(_deck_text(render_input))
    icons = ["square-stack", "bolt", "network", "book-open"]
    row_html = []
    for row_index, row in enumerate(rows[:4], start=1):
        number = metrics[row_index - 1] if row_index <= len(metrics) else "%02d" % row_index
        row_html.append(
            f"""          <div class="ledger-row">
            <p class="ledger-num">{_esc(_shorten(number, 8))}</p>
            <div class="ledger-lbl">{_esc(_shorten(row, 16))}
              <span class="sub">{_esc(_supporting_line(render_input, row_index))}</span>
            </div>
            <i class="ledger-icn" data-lucide="{icons[row_index - 1]}"></i>
          </div>"""
        )
    return f"""    <section class="poster xhs" id="{poster_id}">
      <div class="cross-mat"></div>
      <div class="content" style="display:grid; grid-template-rows:auto auto auto 1fr; row-gap:32px">
        <div class="chrome-min">
          <span>S11 · Ledger</span>
          <span>Card {index:02d}</span>
        </div>
        <p class="t-cat">Inventory · Evidence</p>
        <h2 class="h-xl">{_break_title(slide.heading or "能力清单")}</h2>
        <div class="stacked-ledger" style="align-self:center">
{chr(10).join(row_html)}
        </div>
      </div>
    </section>"""


def _swiss_matrix(poster_id: str, slide: RenderSlide, render_input: RenderInput, index: int) -> str:
    cells = _ensure_point_count(slide.points, render_input, 6)
    cell_html = []
    for cell_index, cell in enumerate(cells[:6], start=1):
        accent = " is-accent" if cell_index == 3 else ""
        cell_html.append(
            f"""          <div class="matrix-cell{accent}">
            <p class="cell-nb">{cell_index:02d}</p>
            <p class="cell-title">{_esc(_shorten(cell, 14))}</p>
          </div>"""
        )
    return f"""    <section class="poster xhs" id="{poster_id}">
      <div class="dot-mat"></div>
      <div class="content" style="display:grid; grid-template-rows:auto auto auto 1fr auto; row-gap:32px">
        <div class="chrome-min">
          <span>S12 · Matrix</span>
          <span>Card {index:02d}</span>
        </div>
        <p class="t-cat">Capabilities · Matrix</p>
        <h2 class="h-xl">{_break_title(slide.heading or "能力矩阵")}</h2>
        <div class="matrix-fill" style="height:100%; grid-auto-rows:1fr">
{chr(10).join(cell_html)}
        </div>
        <div class="hero-stat-bottom">
          <div>
            <p class="t-cat">In total · 累计</p>
            <p class="lead">{_esc(render_input.visual_direction or "把关键信息压缩成可复用卡片结构。")}</p>
          </div>
          <p class="num-mega">{len(cells[:6])}</p>
        </div>
      </div>
    </section>"""


def _swiss_file_card(poster_id: str, slide: RenderSlide, render_input: RenderInput, index: int) -> str:
    points = _ensure_point_count(slide.points, render_input, 4)
    rows = []
    for item_index, point in enumerate(points[:4], start=1):
        rows.append(
            f"""              <div class="row gap-6" style="align-items:flex-start">
                <p class="t-meta">0{item_index}</p>
                <p class="lead">{_esc(point)}</p>
              </div>"""
        )
    return f"""    <section class="poster xhs" id="{poster_id}">
      <div class="ring-mat"></div>
      <div class="content" style="display:grid; grid-template-rows:auto 1fr auto; row-gap:32px">
        <div class="chrome-min">
          <span>S03 · File Card</span>
          <span>Card {index:02d}</span>
        </div>
        <div class="grid-12">
          <div class="span-7 card-ink stack gap-5">
            <p class="t-meta">Source of truth</p>
            <h2 class="h-xl">{_break_title(slide.heading or "核心拆解")}</h2>
          </div>
          <div class="span-5 card-fill stack gap-5">
{chr(10).join(rows)}
          </div>
        </div>
        <div class="hero-stat-bottom">
          <div>
            <p class="t-cat">Trace · 保留依据</p>
            <p class="lead">{_esc(render_input.visual_direction or "结构、文案和输出路径都可回看。")}</p>
          </div>
          <p class="num-mega">{len(points[:4])}</p>
        </div>
      </div>
    </section>"""


def _swiss_cta(poster_id: str, slide: RenderSlide, render_input: RenderInput, index: int) -> str:
    rows = _ensure_point_count([slide.text or "", "人工审核发布"], render_input, 4)
    row_html = []
    for row_index, row in enumerate(rows[:4], start=1):
        row_html.append(
            f"""          <div class="ledger-row">
            <p class="ledger-num">{row_index:02d}</p>
            <div class="ledger-lbl">{_esc(_shorten(row, 16))}
              <span class="sub">{_esc(_supporting_line(render_input, row_index))}</span>
            </div>
            <i class="ledger-icn" data-lucide="check-square"></i>
          </div>"""
        )
    return f"""    <section class="poster xhs" id="{poster_id}">
      <div class="cross-mat"></div>
      <div class="content" style="display:grid; grid-template-rows:auto auto auto 1fr auto; row-gap:32px">
        <div class="chrome-min">
          <span>Review · Publish</span>
          <span>Card {index:02d}</span>
        </div>
        <p class="t-cat">下一步 · Action</p>
        <h2 class="h-xl">{_break_title(slide.text or "")}</h2>
        <div class="stacked-ledger" style="align-self:center">
{chr(10).join(row_html)}
        </div>
        <div class="hero-stat-bottom">
          <div>
            <p class="t-cat">Manual check · 人工审核</p>
            <p class="lead">{_esc(render_input.visual_direction or "先审稿，再发布，把好内容变成稳定流程。")}</p>
          </div>
          <p class="num-mega">PNG</p>
        </div>
      </div>
    </section>"""


def _select_swiss_recipe(render_input: RenderInput, slide: RenderSlide, content_index: int) -> str:
    layout_id = render_input.layout_id.strip().upper()
    sequences = {
        "S06": ["S06", "S12", "S11", "S10"],
        "S09": ["S09", "S06", "S12", "S11"],
        "S10": ["S10", "S11", "S12"],
        "S11": ["S11", "S10", "S12"],
        "S12": ["S12", "S11", "S10"],
        "S03": ["S03", "S12", "S11"],
    }
    if layout_id in sequences:
        sequence = sequences[layout_id]
        return sequence[(content_index - 1) % len(sequence)]
    text = _deck_text(render_input, slide)
    if _has_metric(text):
        return "S09"
    if _looks_workflow_text(text):
        return "S06"
    return "S12"


def _deck_strategy(render_input: RenderInput) -> str:
    blueprint = render_input.visual_blueprint
    if isinstance(blueprint, dict):
        return str(blueprint.get("strategy", ""))
    return ""


def _deck_text(render_input: RenderInput, slide: RenderSlide | None = None) -> str:
    parts = [render_input.visual_direction, _deck_strategy(render_input)]
    for item in render_input.slides:
        parts.extend(
            [
                item.title or "",
                item.hook or "",
                item.heading or "",
                " ".join(item.points or []),
                item.text or "",
            ]
        )
    blueprint = render_input.visual_blueprint
    if isinstance(blueprint, dict):
        for job in blueprint.get("image_jobs", []):
            if isinstance(job, dict):
                parts.extend(
                    [
                        str(job.get("role", "")),
                        str(job.get("title", "")),
                        str(job.get("message", "")),
                        str(job.get("source_detail", "")),
                    ]
                )
    if slide is not None:
        parts.extend([slide.heading or "", " ".join(slide.points or [])])
    return _content_text_for_keywords(" ".join(part for part in parts if part))


def _deck_keywords(render_input: RenderInput) -> List[str]:
    return _extract_keywords(_deck_text(render_input))


def _has_metric(text: str) -> bool:
    return bool(_primary_metric(text))


def _looks_workflow_text(text: str) -> bool:
    return any(token in text for token in ["流程", "步骤", "节点", "workflow", "Pipeline", "URL", "Agent"])


def _all_content_points(render_input: RenderInput) -> List[str]:
    points: List[str] = []
    for slide in render_input.slides:
        if slide.heading:
            points.append(slide.heading)
        points.extend(slide.points or [])
        if slide.hook:
            points.append(slide.hook)
        if slide.text:
            points.append(slide.text)
    return points


def _ensure_point_count(points: List[str], render_input: RenderInput, count: int) -> List[str]:
    candidates = []
    candidates.extend(points)
    candidates.extend(_all_content_points(render_input))
    candidates.extend(_deck_keywords(render_input))
    candidates.extend(
        [
            render_input.visual_direction,
            _deck_strategy(render_input),
            "保留证据链",
            "生成 PNG",
            "人工审核发布",
            "复用这套结构",
        ]
    )
    result = []
    for item in candidates:
        clean = _shorten(str(item), 24)
        if clean and clean not in result:
            result.append(clean)
        if len(result) >= count:
            return result
    while len(result) < count:
        result.append("结构化输出")
    return result


def _metric_tokens(text: str) -> List[str]:
    matches = re.findall(
        r"\d+(?:\.\d+)?\s*(?:倍|%|分钟|小时|步|张|个|项|页|年|月|日|周|M|K|B)?",
        text,
    )
    tokens = []
    for match in matches:
        clean = re.sub(r"\s+", "", match)
        if clean and clean not in tokens:
            tokens.append(clean)
        if len(tokens) >= 6:
            break
    return tokens


def _kpi_items(render_input: RenderInput, slide: RenderSlide) -> List[Dict[str, Any]]:
    metrics = _metric_tokens(_deck_text(render_input, slide))
    points = _ensure_point_count([slide.heading or ""] + slide.points, render_input, 4)
    fallback_metrics = [
        "%d页" % len(render_input.slides),
        "%d项" % len(_all_content_points(render_input)),
        "1链",
        _deck_date(),
    ]
    heights = [320, 260, 200, 140]
    items = []
    for index in range(4):
        number = metrics[index] if index < len(metrics) else fallback_metrics[index]
        items.append(
            {
                "num": _shorten(number, 8),
                "label": _shorten(_strip_metric(points[index]), 18),
                "height": heights[index],
            }
        )
    return items


def _strip_metric(value: str) -> str:
    stripped = re.sub(
        r"\d+(?:\.\d+)?\s*(?:倍|%|分钟|小时|步|张|个|项|页|年|月|日|周|M|K|B)?",
        "",
        value,
    ).strip(" ：:，,/-")
    return stripped or value


def _pipeline_label(value: str, index: int) -> str:
    clean = re.split(r"[：:，,、/\\-]+", value, maxsplit=1)[0].strip()
    return _shorten(clean or "Step %02d" % index, 12)


def _supporting_line(render_input: RenderInput, index: int) -> str:
    candidates = _all_content_points(render_input) + [render_input.visual_direction]
    if not candidates:
        return "保留上下文，方便人工审核。"
    return _shorten(candidates[(index - 1) % len(candidates)], 28)


def _editorial_cover(poster_id: str, slide: RenderSlide, render_input: RenderInput, index: int) -> str:
    return f"""    <section class="poster xhs" id="{poster_id}">
      <canvas class="mag-bg" data-bg="ink-flow"></canvas>
      <div class="grain"></div>
      <div class="content stack gap-4">
        <div class="issue-row">
          <span>Vol. {index:02d}</span><span class="dot"></span><span>{_esc(_deck_date())}</span>
        </div>
        <div class="stack gap-2">
          <p class="kicker">封面 · Cover</p>
          <h1 class="h-display">{_break_title(slide.title or "")}</h1>
          <p class="h-sub">{_esc(slide.hook or render_input.visual_direction)}</p>
        </div>
        <p class="lead">{_esc(render_input.visual_direction or "一组关于 AI 工作流的视觉记录。")}</p>
      </div>
      <div class="issue-strip">
        <span>Issue · AI Workflow</span>
        <span>—</span>
        <span>Guizang Social Card</span>
      </div>
    </section>"""


def _editorial_content(poster_id: str, slide: RenderSlide, render_input: RenderInput, index: int) -> str:
    rows = []
    for item_index, point in enumerate(slide.points[:3], start=1):
        rows.append(
            f"""          <div class="ledger-row">
            <span>0{item_index}</span>
            <strong>{_esc(point)}</strong>
          </div>"""
        )
    return f"""    <section class="poster xhs" id="{poster_id}">
      <canvas class="mag-bg" data-bg="ink-flow"></canvas>
      <div class="grain"></div>
      <div class="content stack gap-5">
        <div class="issue-row">
          <span>Note {index:02d}</span><span class="dot"></span><span>Workflow</span>
        </div>
        <p class="kicker">拆解 · Notes</p>
        <h2 class="h-display">{_break_title(slide.heading or "")}</h2>
        <div class="ledger">
{chr(10).join(rows)}
        </div>
        <p class="lead">{_esc(render_input.visual_direction or "每一页只讲一个关键变化。")}</p>
      </div>
      <div class="issue-strip">
        <span>{_esc(render_input.layout_id)}</span>
        <span>—</span>
        <span>AI Workflow Cards</span>
      </div>
    </section>"""


def _editorial_cta(poster_id: str, slide: RenderSlide, render_input: RenderInput, index: int) -> str:
    return f"""    <section class="poster xhs" id="{poster_id}">
      <canvas class="mag-bg" data-bg="ink-flow"></canvas>
      <div class="grain"></div>
      <div class="content stack gap-5">
        <div class="issue-row">
          <span>End</span><span class="dot"></span><span>Review</span>
        </div>
        <p class="kicker">下一步 · Action</p>
        <h2 class="h-display">{_break_title(slide.text or "")}</h2>
        <p class="lead">{_esc(render_input.visual_direction or "先审核，再发布。把好内容变成稳定流程。")}</p>
      </div>
      <div class="issue-strip">
        <span>Manual Review</span>
        <span>—</span>
        <span>Publish</span>
      </div>
    </section>"""


def _render_with_playwright(index_path: Path, task_dir: Path) -> Dict[str, List[str]]:
    script = _playwright_script()
    with tempfile.NamedTemporaryFile(
        "w",
        suffix=".mjs",
        encoding="utf-8",
        delete=False,
        dir=str(SKILL_ROOT),
    ) as handle:
        handle.write(script)
        script_path = Path(handle.name)
    try:
        completed = subprocess.run(
            [
                "node",
                str(script_path),
                str(index_path),
                str(task_dir),
            ],
            cwd=str(SKILL_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if completed.returncode != 0:
            error_output = (completed.stderr or "").strip() or (completed.stdout or "").strip()
            raise RuntimeError(
                "guizang Playwright render failed: %s"
                % error_output
            )
        data = json.loads(completed.stdout)
        return {"png_paths": [str(Path(path)) for path in data.get("png_paths", [])]}
    finally:
        script_path.unlink(missing_ok=True)


def _playwright_script() -> str:
    return r"""
import { chromium } from 'playwright';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const indexPath = process.argv[2];
const taskDir = process.argv[3];
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1200, height: 1600 }, deviceScaleFactor: 1 });
await page.goto(pathToFileURL(indexPath).href, { waitUntil: 'networkidle' });
await page.evaluate(async () => {
  if (document.fonts && document.fonts.ready) {
    await document.fonts.ready;
  }
});
await page.waitForTimeout(700);
const posters = await page.$$('.poster.xhs, .poster.square, .poster.wide');
const pngPaths = [];
for (let index = 0; index < posters.length; index += 1) {
  const id = await posters[index].evaluate((node, idx) => node.id || `poster-${idx + 1}`, index);
  const outputPath = path.join(taskDir, `${id}.png`);
  await posters[index].screenshot({ path: outputPath });
  pngPaths.push(outputPath);
}
await browser.close();
console.log(JSON.stringify({ png_paths: pngPaths }));
"""


def _run_validator(task_dir: Path) -> Dict[str, Any]:
    if not VALIDATOR.exists():
        return {}
    completed = subprocess.run(
        ["node", str(VALIDATOR), str(task_dir)],
        cwd=str(SKILL_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return {
        "passed": completed.returncode == 0,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def _new_task_dir(output_root: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = output_root / ("xhs-guizang-" + stamp)
    if not base.exists():
        return base
    suffix = 2
    while True:
        candidate = output_root / ("xhs-guizang-%s-%02d" % (stamp, suffix))
        if not candidate.exists():
            return candidate
        suffix += 1


def _build_slides(content_goal: str, preset: Any, clauses: List[str], keywords: List[str]) -> List[Dict[str, Any]]:
    structured = _parse_structured_brief(content_goal)
    if structured:
        return _build_slides_from_structured_brief(structured, preset)

    title = _shorten(_fill_template(preset.cover_title, keywords, clauses), 15)
    hook = _shorten(_fill_template(preset.cover_hook, keywords, clauses), 30)
    if _looks_static_preset(title, content_goal):
        title = _shorten(_headline_from_source(content_goal, keywords), 15)
    slides = [{"type": "cover", "title": title, "hook": hook}]
    headings = ["关键变化", "怎么做到", "值得保存"]
    for index, clause in enumerate(clauses[:2], start=0):
        points = _points_for_clause(clause, clauses, keywords)
        slides.append(
            {
                "type": "content",
                "heading": _shorten(headings[index], 12),
                "points": [_shorten(point, 20) for point in points[:3]],
            }
        )
    if len(slides) == 1:
        slides.append(
            {
                "type": "content",
                "heading": "核心拆解",
                "points": [_shorten(item, 20) for item in preset.content_plan[:3]],
            }
        )
    slides.append({"type": "cta", "text": _shorten("保存这套流程", 20)})
    return slides


def _build_slides_from_structured_brief(structured: Dict[str, Any], preset: Any) -> List[Dict[str, Any]]:
    topic = str(structured.get("主题") or structured.get("标题") or "").strip()
    core_hook = str(structured.get("核心钩子") or "").strip()
    entities = structured.get("关键实体", [])
    key_points = structured.get("关键点", [])
    title_source = _structured_title_source(topic, entities)
    title = _shorten(title_source or _without_template_suffix(preset.cover_title), 15)
    hook = _shorten(core_hook or _without_template_suffix(preset.cover_hook), 30)
    slides = [{"type": "cover", "title": title, "hook": hook}]
    headings = ["关键变化", "怎么做到", "值得保存"]
    for index, point in enumerate(key_points[:3], start=0):
        points = _points_for_structured_key_point(point, entities)
        slides.append(
            {
                "type": "content",
                "heading": _shorten(headings[index], 12),
                "points": [_shorten(item, 20) for item in points[:3]],
            }
        )
    if len(slides) == 1:
        slides.append(
            {
                "type": "content",
                "heading": "核心拆解",
                "points": [_shorten(item, 20) for item in key_points[:3] or [core_hook, topic]],
            }
        )
    slides.append({"type": "cta", "text": _shorten("保存这张卡", 20)})
    return slides


def _build_visual_blueprint(slides: List[Dict[str, Any]], preset: Any, source: str) -> Dict[str, Any]:
    jobs = []
    for index, slide in enumerate(slides, start=1):
        if slide["type"] == "cover":
            title = slide["title"]
            message = slide["hook"]
            role = "cover"
        elif slide["type"] == "content":
            title = slide["heading"]
            message = " / ".join(slide["points"])
            role = "takeaway"
        else:
            title = slide["text"]
            message = "人工审核后发布"
            role = "cta"
        jobs.append(
            {
                "id": "card_%02d" % index,
                "role": role,
                "title": title,
                "message": message,
                "source_detail": _shorten(source, 60),
                "prompt": "",
                "output_name": "xhs-%02d.png" % index,
            }
        )
    return {
        "mode": "guizang-html-deck",
        "planner": "guizang-template",
        "strategy": preset.strategy,
        "target_cards": len(jobs),
        "visual_direction": preset.cover_visual,
        "image_jobs": jobs,
    }


def _slides_plan(slides: List[Dict[str, Any]]) -> List[str]:
    plan = []
    for slide in slides:
        if slide["type"] == "cover":
            plan.append("%s / %s" % (slide["title"], slide["hook"]))
        elif slide["type"] == "content":
            plan.append("%s：%s" % (slide["heading"], " / ".join(slide["points"])))
        else:
            plan.append(slide["text"])
    return plan


def _extract_clauses(text: str) -> List[str]:
    text = _content_text_for_keywords(text)
    parts = [part.strip() for part in re.split(r"[。！？!?；;\n]+", text) if part.strip()]
    return parts or [text.strip()]


def _extract_keywords(text: str) -> List[str]:
    text = _content_text_for_keywords(text)
    latin = re.findall(r"[A-Za-z][A-Za-z0-9._-]{1,}", text)
    numbers = re.findall(r"\d+(?:\.\d+)?\s*(?:倍|分钟|小时|%|张|个)?", text)
    chinese_chunks = re.findall(r"[\u4e00-\u9fff]{2,8}", text)
    keywords = []
    for item in latin + numbers + chinese_chunks:
        clean = item.strip()
        if clean and clean not in keywords:
            keywords.append(clean)
    return keywords[:8]


def _parse_structured_brief(text: str) -> Dict[str, Any]:
    fields: Dict[str, Any] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if "：" not in line:
            continue
        key, value = line.split("：", 1)
        key = key.strip()
        value = value.strip()
        if key in {"关键点", "关键实体", "关键数字"}:
            fields[key] = [item.strip() for item in value.split(" / ") if item.strip()]
        elif key in {"主题", "核心钩子", "标题", "摘要", "受众角度"}:
            fields[key] = value
    if fields.get("核心钩子") or fields.get("关键点"):
        return fields
    return {}


def _structured_title_source(topic: str, entities: List[str]) -> str:
    if entities:
        lead = str(entities[0]).strip()
        if lead:
            return lead
    if "，" in topic:
        return topic.split("，", 1)[0].strip()
    return topic


def _points_for_structured_key_point(point: str, entities: List[str]) -> List[str]:
    point = _strip_leading_label(point)
    support = next((entity for entity in entities if entity and entity in point), "")
    points = [point]
    if support and support != point:
        points.append("关联 %s" % support)
    elif entities:
        points.append("关联 %s" % entities[0])
    else:
        points.append("保留原文证据")
    return points


def _strip_leading_label(value: str) -> str:
    value = value.strip()
    if "：" in value and len(value.split("：", 1)[0]) <= 8:
        return value.split("：", 1)[1].strip()
    return value


def _without_template_suffix(template: str) -> str:
    return re.sub(r"\{[^}]+\}", "", template).strip() or "内容卡片"


def _content_text_for_keywords(text: str) -> str:
    lines = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("来源 URL"):
            continue
        lines.append(line)
    text = "\n".join(lines)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?\b", " ", text)
    return text


def _fill_template(template: str, keywords: List[str], clauses: List[str]) -> str:
    lead = keywords[0] if keywords else "内容"
    number = next((item for item in keywords if re.search(r"\d", item)), "1次")
    secondary = keywords[1] if len(keywords) > 1 else lead
    return (
        template.replace("{lead}", lead)
        .replace("{number}", number)
        .replace("{secondary}", secondary)
        .replace("{source}", clauses[0] if clauses else lead)
    )


def _headline_from_source(content_goal: str, keywords: List[str]) -> str:
    metric = _primary_metric(content_goal)
    if keywords:
        if metric:
            return "%s %s" % (keywords[0], metric)
        return "%s 关键拆解" % keywords[0]
    return content_goal


def _points_for_clause(clause: str, clauses: List[str], keywords: List[str]) -> List[str]:
    candidates = []
    metric = _primary_metric("。".join(clauses))
    if metric:
        candidates.append("%s 是关键变化" % metric)
    candidates.extend(keywords)
    candidates.append(clause)
    candidates.extend(item for item in clauses if item != clause)
    points = []
    for item in candidates:
        clean = _shorten(item, 20)
        if clean and clean not in points:
            points.append(clean)
        if len(points) >= 3:
            break
    while len(points) < 2:
        points.append("保留证据再发布")
    return points


def _primary_metric(text: str) -> str:
    patterns = [
        r"\d+(?:\.\d+)?\s*倍",
        r"\d+(?:\.\d+)?\s*%",
        r"\d+(?:\.\d+)?\s*分钟",
        r"\d+(?:\.\d+)?\s*小时",
        r"\d+(?:\.\d+)?",
    ]
    for pattern in patterns:
        matches = re.findall(pattern, text)
        decimal = next((match for match in matches if "." in match), "")
        if decimal:
            return re.sub(r"\s+", "", decimal)
        if matches:
            return re.sub(r"\s+", "", matches[0])
    return ""


def _looks_static_preset(title: str, source: str) -> bool:
    if any(token in source for token in ["MoSA", "MiniMax", "H800"]):
        return title in {"我把内容做成系统了", "8分钟生成组图", "结果比解释更有用"}
    return False


def _shorten(value: str, limit: int) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) <= limit:
        return value
    return value[:limit]


def _break_title(value: str) -> str:
    escaped = _esc(value)
    if len(value) <= 7:
        return escaped
    midpoint = max(4, min(len(value) - 3, len(value) // 2))
    return _esc(value[:midpoint]) + "<br>" + _esc(value[midpoint:])


def _esc(value: str) -> str:
    return html.escape(str(value), quote=True)


def _deck_date() -> str:
    return datetime.now().strftime("%Y.%m")


def _card_class(index: int) -> str:
    if index == 1:
        return "card-ink"
    if index == 2:
        return "card-fill"
    return "card-outlined"
