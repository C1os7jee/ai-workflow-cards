# INTERFACE.md

本文件是 Agent 层与渲染层的接口契约。双方并行开发时，以这里的 schema、字段含义和兼容性规则为准。

## 总体约定

- Agent 层负责策略选择、调用 skill、维护对外 API 和人工反馈。
- Skill 层负责从内容 brief 生成 `visual_blueprint.image_jobs`，并调用生图 provider 生成 PNG。
- 当前主路径是 `direct-image-deck`：DeepSeek planner 动态决定图片数量和图片角色，Volcengine Seedream 默认负责生成最终 PNG。
- `slides` 仍保留为兼容字段，用于旧 HTML 渲染、旧测试和可读摘要；新功能优先使用 `visual_blueprint`。
- `png_paths` 顺序必须与 `visual_blueprint.image_jobs` 顺序一致；旧 HTML fallback 下才与 `slides` 顺序一致。

## render_xiaohongshu 输入

Agent/Skill 生成完方案后，按下面格式传给渲染工具：

```json
{
  "style": "swiss",
  "theme": "IKB",
  "layout_id": "S09",
  "image_provider": "volcengine-seedream",
  "visual_direction": "MiniMax / MoSA 关系图",
  "visual_blueprint": {
    "mode": "direct-image-deck",
    "planner": "ai",
    "target_cards": 3,
    "visual_direction": "MiniMax / MoSA 关系图",
    "image_jobs": [
      {
        "id": "card_01",
        "role": "cover",
        "title": "MiniMax 提出 MoSA",
        "message": "长上下文注意力计算减少 28.4 倍",
        "source_detail": "H800 上 prefill 加速 14.2 倍",
        "prompt": "Create one finished Xiaohongshu vertical 3:4 card image...",
        "output_name": "card_01.png"
      }
    ]
  },
  "slides": [
    {
      "type": "cover",
      "title": "不超过15字",
      "hook": "不超过30字"
    },
    {
      "type": "content",
      "heading": "不超过12字",
      "points": ["不超过20字", "不超过20字"]
    },
    {
      "type": "cta",
      "text": "不超过20字"
    }
  ]
}
```

字段说明：

- `style`：视觉风格。当前约定支持 `swiss` 和 `editorial`。
- `theme`：主题色方案，例如 `IKB`、`lemon`、`forest` 等。完整列表由 `list_layouts` 或渲染 skill 提供。
- `layout_id`：版式 ID，例如 `S09`、`M05`。Agent 在规划阶段通过 `list_layouts` 查询后选择。
- `image_provider`：可选生图服务商 ID，例如 `openai-compatible` 或 `volcengine-seedream`。为空时由渲染 skill 的 `image_generation.default_provider` 决定。
- `visual_direction`：给 planner 和 image prompt 使用的方向性摘要。
- `visual_blueprint`：当前主契约，描述本次要生成几张最终卡图、每张图的角色和 prompt。
- `slides`：兼容字段，至少包含 `cover` 和 `cta`，中间为 1 张或多张 `content`。

`visual_blueprint` 字段说明：

- `mode`：当前主模式为 `direct-image-deck`。旧 HTML fallback 可不提供该字段。
- `planner`：`ai` 表示 DeepSeek planner 产出；`skill` 表示 skill 规则产出。
- `planner_error`：可选。DeepSeek planner fail-open 时保留错误摘要。
- `target_cards`：本次计划生成的卡图数量。
- `image_jobs`：按顺序排列的最终卡图生成任务。

`image_jobs` 字段说明：

| field | 含义 | 约束 |
| --- | --- | --- |
| `id` | 稳定任务 ID | 建议 `card_01` 形式 |
| `role` | 卡图角色 | 如 `cover`、`mechanism`、`evidence`、`takeaway` |
| `title` | 卡图主标题 | 必填，允许由生图模型排版 |
| `message` | 卡图核心信息 | 必填 |
| `source_detail` | 支撑细节 | 供 prompt grounding 使用 |
| `prompt` | 传给生图 provider 的最终 prompt | 必填 |
| `output_name` | 输出文件名 | 必须是 `.png` |

slide 类型约束：

| type | 必填字段 | 硬约束 |
| --- | --- | --- |
| `cover` | `title`, `hook` | `title` 不超过 15 字；`hook` 不超过 30 字 |
| `content` | `heading`, `points` | `heading` 不超过 12 字；`points` 为 2-3 条，每条不超过 20 字 |
| `cta` | `text` | `text` 不超过 20 字 |

## render_xiaohongshu 输出

渲染工具完成后返回：

```json
{
  "success": true,
  "png_paths": [
    "output/task_xxx/card_01.png",
    "output/task_xxx/card_02.png"
  ],
  "task_dir": "output/task_xxx",
  "generated_assets": {
    "deck_images": [
      "output/task_xxx/card_01.png",
      "output/task_xxx/card_02.png"
    ],
    "image_prompts": "output/task_xxx/image_prompts.json",
    "image_provider": "volcengine-seedream"
  }
}
```

字段说明：

- `success`：渲染过程是否成功。
- `png_paths`：生成的 PNG 路径列表，主路径下顺序与 `visual_blueprint.image_jobs` 一一对应。
- `task_dir`：本次任务输出目录，包含 `render_input.json`、`render_result.json`、`image_prompts.json` 和 PNG。
- `generated_assets`：生成资产明细。`image_prompts` 用于调试 DeepSeek planner 和生图 prompt。

旧 HTML fallback 仍可能返回：

```json
{
  "success": true,
  "png_paths": [
    "output/task_xxx/slide_01.png"
  ],
  "task_dir": "output/task_xxx"
}
```

失败时仍应返回可诊断信息。后续实现可扩展 `error` 字段，但不得改变上述字段含义。

## validate_output 输出

渲染后调用质量检查脚本，返回：

```json
{
  "passed": true,
  "issues": []
}
```

字段说明：

- `passed`：`true` 表示图文质量可以进入人工审核；`false` 表示需要修正文案或重渲。
- `issues`：具体问题列表，例如 `text overflow on slide 2`、`font too small on slide 3`。

## 重试约定

- `validate_output.passed == false` 时，Agent 可根据 `issues` 缩短文案或调整 slide 内容后重渲。
- 自动重渲最多 2 次。
- 仍失败时保留 `task_dir`、原始 render input、最新 issues，交给人工判断。

## 兼容性规则

- 新增字段必须向后兼容，消费者不能依赖未声明字段。
- `visual_blueprint.image_jobs` 是主契约；不要把 provider 请求字段泄漏到 Agent/UI 层。
- `slides` 兼容字段暂不删除；删除前必须写新的 ADR 并迁移测试。
- 修改 `style`、`theme`、`layout_id` 可选值前，先更新本文件。
- 修改字数限制、slide 类型或返回字段前，双方先确认。
- 修改 provider 协议、planner 协议或 `image_jobs` 字段前，先更新 [docs/architecture.md](docs/architecture.md) 和 ADR。
