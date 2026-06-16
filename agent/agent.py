"""Main orchestration for the Visual Agent MVP."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from agent.schemas import FeedbackRecord, VisualPlan, VisualCoverDirection
from agent.tools import extract
from agent.tools import fetch
from agent.tools.layouts import get_strategy_preset, list_supported_strategies
from agent.tools.render import (
    build_render_input,
    build_render_input_from_payload,
    prepare_render_plan,
    render_input_to_dict,
    render_xiaohongshu,
)
from agent.tools.validate import append_feedback_record, validate_visual_plan


class VisualAgent:
    def generate_plan(
        self,
        content_goal: str,
        image_provider: str = "",
        planner_mode: str = "",
    ) -> VisualPlan:
        if fetch.is_url(content_goal):
            content_goal = extract.extract_article_brief(fetch.brief_from_url(content_goal))
        strategy = self._choose_strategy(content_goal)
        preset = get_strategy_preset(strategy)
        prepared = prepare_render_plan(
            content_goal=content_goal,
            strategy=strategy,
            image_provider=image_provider,
            planner_mode=planner_mode,
        )
        render_input = prepared["render_input"]
        plan = VisualPlan(
            content_goal=content_goal,
            recommended_strategy=preset.strategy,
            alternatives=self._alternatives(strategy),
            reason=self._reason(strategy),
            image_provider=str(render_input.get("image_provider", image_provider)),
            cover_direction=VisualCoverDirection(
                title=str(render_input["slides"][0]["title"]),
                hook=str(render_input["slides"][0]["hook"]),
                visual=str(prepared["visual"]),
            ),
            slides_plan=list(prepared["slides_plan"]),
            render_input_snapshot=render_input,
            risk=preset.risk,
            human_checkpoints=[
                "标题是否够具体",
                "截图或流程是否可信",
                "是否符合账号口吻",
            ],
        )
        return validate_visual_plan(plan)

    def to_render_input(self, plan: VisualPlan):
        if plan.render_input_snapshot:
            return build_render_input_from_payload(plan.render_input_snapshot)
        return build_render_input(plan)

    def to_render_payload(self, plan: VisualPlan) -> Dict[str, object]:
        return render_input_to_dict(self.to_render_input(plan))

    def generate_deck(self, plan: VisualPlan) -> Dict[str, object]:
        return render_xiaohongshu(self.to_render_input(plan))

    def record_feedback(
        self,
        feedback_path: Path,
        post_id: str,
        topic: str,
        plan: VisualPlan,
        metrics: Dict[str, object],
        human_notes: str,
    ) -> None:
        record = FeedbackRecord(
            post_id=post_id,
            topic=topic,
            visual_strategy=plan.recommended_strategy,
            cover_type=plan.cover_direction.title if plan.cover_direction else "",
            metrics=metrics,
            human_notes=human_notes,
        )
        append_feedback_record(feedback_path, record)

    def _choose_strategy(self, content_goal: str) -> str:
        text = content_goal.lower()
        if any(word in text for word in ["workflow", "流程", "自动化", "链路", "系统"]):
            return "流程拆解型"
        if any(word in text for word in ["before", "after", "前后", "对比", "压缩"]):
            return "前后对比型"
        if any(word in text for word in ["工具", "实操", "插件", "脚本", "demo"]):
            return "工具实操型"
        if any(word in text for word in ["结果", "证明", "数据", "产出"]):
            return "结果证明型"
        return "系统感封面型"

    def _alternatives(self, strategy: str):
        strategies = [item for item in list_supported_strategies() if item != strategy]
        return strategies[:2]

    def _reason(self, strategy: str) -> str:
        reasons = {
            "流程拆解型": "workflow 内容需要先让读者看懂系统结构",
            "前后对比型": "读者更容易理解时间和成本变化",
            "工具实操型": "实操类内容需要把步骤和动作直接露出来",
            "结果证明型": "内容已经有结果，应该优先展示证据",
            "系统感封面型": "当前信息更适合先建立账号系统感",
        }
        return reasons[strategy]
