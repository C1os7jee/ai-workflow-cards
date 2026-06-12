"""Render input helpers.

The MVP keeps rendering as a separate concern: this module only converts the
Visual Agent output into the existing `INTERFACE.md` input shape.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict

from agent.schemas import RenderInput, RenderSlide, VisualPlan
from agent.tools.layouts import get_strategy_preset


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = PROJECT_ROOT / "skills" / "xhs-card-skill"
SKILL_PREPARER = SKILL_ROOT / "prepare_payload.py"
SKILL_RENDERER = PROJECT_ROOT / "skills" / "xhs-card-skill" / "render_deck.py"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "output"


def prepare_render_plan(
    content_goal: str,
    strategy: str,
    image_provider: str = "",
    planner_mode: str = "",
) -> Dict[str, Any]:
    if not SKILL_PREPARER.exists():
        raise FileNotFoundError("missing xhs card skill preparer: %s" % SKILL_PREPARER)
    payload = {
        "content_goal": content_goal,
        "strategy": strategy,
        "image_provider": image_provider,
        "planner_mode": planner_mode,
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False) as handle:
        json.dump(payload, handle, ensure_ascii=False)
        input_path = Path(handle.name)
    try:
        completed = subprocess.run(
            [
                "python3",
                str(SKILL_PREPARER),
                "--input",
                str(input_path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "xhs card skill prepare failed: %s"
                % (completed.stderr.strip() or completed.stdout.strip())
            )
        data = json.loads(completed.stdout)
    finally:
        input_path.unlink(missing_ok=True)
    if not isinstance(data, dict) or "render_input" not in data:
        raise RuntimeError("xhs card skill prepare returned invalid payload")
    return data


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
        visual_blueprint=payload.get("visual_blueprint", {}) if isinstance(payload.get("visual_blueprint", {}), dict) else {},
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


def render_xiaohongshu(render_input: RenderInput, output_root: Path = DEFAULT_OUTPUT_ROOT) -> Dict[str, object]:
    payload = render_input.to_dict()
    if not SKILL_RENDERER.exists():
        raise FileNotFoundError("missing xhs card renderer: %s" % SKILL_RENDERER)
    output_root.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False) as handle:
        json.dump(payload, handle, ensure_ascii=False)
        input_path = Path(handle.name)
    try:
        command = [
            "python3",
            str(SKILL_RENDERER),
            "--input",
            str(input_path),
            "--output",
            str(output_root),
        ]
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "xhs card renderer failed: %s" % (completed.stderr.strip() or completed.stdout.strip())
            )
        return json.loads(completed.stdout)
    finally:
        input_path.unlink(missing_ok=True)
