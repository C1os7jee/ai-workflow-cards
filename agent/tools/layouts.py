"""Static visual strategy presets for the MVP.

The current implementation uses a small, explicit mapping so the first version
can run without a layout service. Later this can be replaced by a live
`list_layouts` integration without changing the calling contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class StrategyPreset:
    strategy: str
    style: str
    theme: str
    layout_id: str
    cover_title: str
    cover_hook: str
    cover_visual: str
    content_plan: List[str]
    risk: str


STRATEGY_PRESETS: Dict[str, StrategyPreset] = {
    "流程拆解型": StrategyPreset(
        strategy="流程拆解型",
        style="swiss",
        theme="IKB",
        layout_id="S09",
        cover_title="8分钟生成组图",
        cover_hook="我的小红书内容开始自动化了",
        cover_visual="中心流程图 + 关键节点高亮",
        content_plan=[
            "痛点：写一篇配一套图太慢",
            "流程：URL -> 提炼 -> 卡片 -> 校验",
            "结果：人只负责审核和发布",
        ],
        risk="如果流程图太复杂，封面点击率会下降",
    ),
    "前后对比型": StrategyPreset(
        strategy="前后对比型",
        style="editorial",
        theme="lemon",
        layout_id="M05",
        cover_title="3小时压缩到5分钟",
        cover_hook="我把重复内容整理成了可复用流程",
        cover_visual="左右对比 + 数字变化",
        content_plan=[
            "Before：每次都从零开始",
            "After：内容和图片一起流水线化",
            "结果：更快，也更统一",
        ],
        risk="如果对比不够具体，读者会觉得只是包装",
    ),
    "工具实操型": StrategyPreset(
        strategy="工具实操型",
        style="swiss",
        theme="forest",
        layout_id="S03",
        cover_title="这套工具真能省时",
        cover_hook="给内容生产加一个可执行的动作链",
        cover_visual="截图拼贴 + 操作步骤",
        content_plan=[
            "工具：输入内容或 URL",
            "步骤：提炼、排版、校验、发布",
            "收益：人工只做最后确认",
        ],
        risk="如果步骤太多，会显得复杂且不友好",
    ),
    "结果证明型": StrategyPreset(
        strategy="结果证明型",
        style="editorial",
        theme="IKB",
        layout_id="M03",
        cover_title="结果比解释更有用",
        cover_hook="先给你看产出，再说怎么做的",
        cover_visual="成果截图 + 数据强调",
        content_plan=[
            "结果：最终图能直接发布",
            "证据：过程、截图、校验都保留",
            "复盘：哪些地方还要改",
        ],
        risk="如果没有真实结果支撑，会变成空展示",
    ),
    "系统感封面型": StrategyPreset(
        strategy="系统感封面型",
        style="swiss",
        theme="IKB",
        layout_id="S12",
        cover_title="我把内容做成系统了",
        cover_hook="不是单篇产出，而是持续进化的结构",
        cover_visual="模块关系图 + 层级结构",
        content_plan=[
            "层级：账号定位、视觉策略、反馈",
            "机制：主 Agent 决策，Visual Agent 执行",
            "目标：越用越懂这个账号",
        ],
        risk="如果抽象度过高，会牺牲点击和理解成本",
    ),
}


def list_supported_strategies() -> List[str]:
    return list(STRATEGY_PRESETS.keys())


def get_strategy_preset(strategy: str) -> StrategyPreset:
    if strategy not in STRATEGY_PRESETS:
        raise KeyError("unknown strategy: %s" % strategy)
    return STRATEGY_PRESETS[strategy]
