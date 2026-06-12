# Spec: 小红书 Visual Agent MVP

> Status: historical MVP spec. 当前协作与实现以
> [../architecture.md](../architecture.md)、[../../INTERFACE.md](../../INTERFACE.md)
> 和 [../decisions/ADR-001-dynamic-visual-blueprint.md](../decisions/ADR-001-dynamic-visual-blueprint.md)
> 为准。本文件保留早期目标、边界和测试思路，不能覆盖当前
> `visual_blueprint.image_jobs` 主契约。

## Objective

为 `ai-workflow-cards` 增加一个面向小红书的视觉策略子系统：给定内容 brief，AI 先判断应该用什么视觉表达，再生成可渲染的小红书组图方案，人只在关键节点审核、选择和微调。

成功标准：

- 能把一篇内容或选题转成结构化视觉方案。
- 能通过 runtime skill 输出 PNG。当前主路径是动态
  `visual_blueprint.image_jobs`，旧 HTML/slides 渲染仅作为兼容 fallback。
- 能记录人工选择、修改理由和发布表现。
- 能把反馈沉淀回账号记忆文件，支持后续迭代。

## Tech Stack

- Python 3.9+
- 当前仓库现有的 Python 运行时
- 标准库 `unittest` 用于测试
- 标准库 `dataclasses` 用于结构化数据模型
- 现有 `ai-workflow-cards` 卡片渲染链路

## Commands

开发与验证阶段先约定以下命令：

```bash
python main.py --help
python main.py --input "..." --mode visual-plan
python main.py --input "..." --mode render-input
python main.py --input "..." --mode record-feedback --post-id "post-001" --topic "..." --human-notes "..." --metrics-json '{"views": 1200}'
python3 -m unittest discover -s tests -v
```

说明：

- `main.py` 是当前 CLI 入口。
- `--mode visual-plan` 用于生成视觉策略和组图草案。
- `--mode render-input` 用于输出符合 `INTERFACE.md` 的渲染输入。
- `--mode record-feedback` 用于追加人工反馈记录。
- 如果后续补充 lint 或 pytest，再在此处追加完整命令。

## Project Structure

建议在 `ai-workflow-cards/` 内补充以下结构：

```text
ai-workflow-cards/
├── agent/
│   ├── agent.py              # 主编排逻辑
│   ├── schemas.py            # content brief / visual plan / feedback schema
│   └── tools/
│       ├── fetch.py          # 输入内容读取
│       ├── layouts.py        # 版式和策略映射
│       ├── render.py         # PNG 渲染包装
│       └── validate.py       # 输出校验
├── docs/
│   ├── specs/
│   │   └── xhs-visual-agent-mvp.md
│   ├── ideas/
│   │   └── xhs-visual-agent.md
│   └── memories/
│       ├── 账号定位.md
│       ├── 视觉策略.md
│       ├── 视觉实验记录.md
│       └── 帖子表现记录.jsonl
├── prompts/
│   └── system.md
├── tests/
└── main.py
```

## Code Style

以“结构化输出优先、显式字段优先、最少隐式行为”为原则。

示例：

```python
from dataclasses import dataclass, field


@dataclass
class VisualPlan:
    content_goal: str
    recommended_strategy: str
    alternatives: list[str] = field(default_factory=list)
    reason: str


def choose_strategy(content_goal: str) -> VisualPlan:
    if "workflow" in content_goal.lower():
        return VisualPlan(
            content_goal=content_goal,
            recommended_strategy="流程拆解型",
            alternatives=["工具实操型", "系统感封面型"],
            reason="workflow 内容需要先让读者看懂系统结构",
        )
    raise ValueError("unsupported content goal")
```

约定：

- 输出结构必须可序列化。
- 每个字段都要能被后续 Agent 理解和复用。
- 规则判断优先显式映射，不靠隐藏 prompt 魔法。

## Testing Strategy

测试分三层：

- 单元测试：策略选择、schema 校验、反馈记录写入。
- 集成测试：`content brief -> visual plan -> render input` 的转换。
- 端到端测试：给定一个固定输入，验证能输出 PNG 路径和记录文件。

建议优先覆盖：

- 视觉策略映射是否稳定。
- 输出字段是否满足接口约束。
- 反馈记录不会污染旧数据。
- 渲染失败时是否保留可诊断信息。

## Boundaries

- Always: 先写 spec 再实现；所有结构化输出都要有 schema；每次人工修改都要可记录；保持与 `INTERFACE.md` 兼容。
- Ask first: 新增第三方依赖；修改 `INTERFACE.md`；改变渲染输出字段；接入自动发布或外部平台数据源。
- Never: 把账号敏感信息写入仓库；让 Visual Agent 修改账号定位本身；跳过人工兜底；把单篇表现当作长期规则直接写死。

## Success Criteria

- 可以从一个内容 brief 生成视觉策略建议。
- 可以把视觉策略映射为当前 `visual_blueprint.image_jobs` 渲染输入。
- 可以输出可追踪的反馈记录。
- 可以保留“人工为什么改”的信息。
- 可以用测试验证核心 schema 和转换逻辑。

## Open Questions

- 第一版 CLI 的输入形式是文本、URL 还是 JSON brief 优先？
- 视觉策略是否需要独立成枚举，还是先用字符串 + 约定列表？
- 记忆文件放在 `docs/memories/` 还是项目根目录更合适？
- 是否要先做“单方案 + 人工重试”，还是“一次生成 2-3 套候选方案”？
- 发布表现字段的最小集合是什么？
