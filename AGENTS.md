# AGENTS.md

本文件是 `ai-workflow-cards` 项目的开发协作入口，供 Codex、Claude Code、Cursor、Copilot 等 coding agent 在修改本仓库时读取。

## 项目定位

- 本项目目标是构建一个把内容 brief 转成可发布小红书图文组图的 Visual Agent。
- 当前合作约定的 MVP 主链路是：`content brief -> VisualAgent -> xhs-card-skill -> DeepSeek planner -> visual_blueprint.image_jobs -> image provider -> PNG -> 人工审核发布`。
- 当前默认 planner 是 DeepSeek；默认生图 provider 是 Volcengine Seedream；OpenAI-compatible 生图接口作为显式 fallback 保留。
- 协作中的硬接口是 [INTERFACE.md](INTERFACE.md)。实现 `agent/tools/render.py`、`agent/tools/validate.py`、`agent/tools/layouts.py` 或 Agent 输出 schema 前必须先读它。
- 架构边界以 [docs/architecture.md](docs/architecture.md) 为准；关键决策见 [docs/decisions/ADR-001-dynamic-visual-blueprint.md](docs/decisions/ADR-001-dynamic-visual-blueprint.md)。
- 小红书无官方发布 API，MVP 做“一键准备”：生成 PNG、整理文案和标签、打开创作页面，由人工审核发布。

## 开发用 Skills

本工作区安装了开发用 agent skills，不属于应用运行时代码：

- `../.agents/skills/ai-project-governance`
- `../.agents/skills/agent-skills`

工作时按任务意图读取相应 `SKILL.md`：

- 新功能或大改动：`agent-skills/skills/spec-driven-development/SKILL.md`，再读 `planning-and-task-breakdown`、`incremental-implementation`。
- 设计模块接口、数据结构或工具边界：`agent-skills/skills/api-and-interface-design/SKILL.md`。
- 实现业务逻辑或修复行为：`agent-skills/skills/test-driven-development/SKILL.md`。
- UI、卡片视觉、渲染输出或前端体验：`agent-skills/skills/frontend-ui-engineering/SKILL.md`。
- 浏览器渲染验证：`agent-skills/skills/browser-testing-with-devtools/SKILL.md`。
- 代码审查：`agent-skills/skills/code-review-and-quality/SKILL.md`。
- 版本管理和提交拆分：`agent-skills/skills/git-workflow-and-versioning/SKILL.md`。

这些 skills 用于指导开发流程，不应被复制进应用包、运行时依赖或发布产物。

不要混淆两类 `skills`：

- `../.agents/skills/`：开发用 agent workflow skills，只给开发者和 coding agent 读取。
- `skills/`：应用运行时 skill 目录，当前包含 `xhs-card-skill`，由 `render_xiaohongshu` 和 `prepare_render_plan` 调用。

## 修改边界

- 不要把外层 `skills/`、`.agents/`、本地个人配置或临时文件作为应用功能的一部分引入。
- 未经明确要求，不新增生产依赖；确需新增时，说明用途、替代方案和验证方式。
- 不写入真实 API key、cookie、token、账号资料或其他敏感信息。
- 不覆盖用户未提交的改动；修改前先查看 `git status --short`。
- 对文生图相关实现，优先保持接口可替换：planner、图片模型、提示词模板、渲染器和存储位置不要硬编码成单一供应商或单一路径。
- 不要把 DeepSeek、Seedream、OpenAI-compatible 的请求字段写进 `agent/` 或 `web/`；provider 细节属于 runtime skill。
- 不擅自修改 `INTERFACE.md` 中的硬约束；确需变更时，先说明对 Web/API 层、Agent 层和 Skill 层的影响。
- `xhs-card-skill` 若引入外部运行时依赖，应锁定版本或 commit hash，不自动漂移。

## 推荐项目结构

在实现时优先沿用现有骨架：

- `agent/schemas.py`：请求、文章摘要、小红书帖子、图片提示词、渲染结果等结构化 schema。
- `agent/agent.py`：Agent 编排流程。
- `agent/tools/fetch.py`：文章 / blog 抓取与清洗。
- `agent/tools/layouts.py`：小红书卡片版式、尺寸、主题、排版规则。
- `agent/tools/render.py`：通过 runtime skill 调用 planner、图片生成和导出。
- `agent/tools/validate.py`：输入输出校验、图片尺寸 / 格式 / 质量检查。
- `prompts/system.md`：Agent 总体行为和内容风格约束。
- `skills/`：应用运行时渲染 skill，当前为 `xhs-card-skill`。
- `output/`：生成的 PNG 存放目录，应保持 gitignore。
- `INTERFACE.md`：Agent 层和渲染层的接口契约。
- `tests/`：与实现同步的最小验证测试。

如实际设计不同，先更新 README 或相关设计说明，再实现代码。

## 文生图实现原则

- 把“策略编排”和“领域出图能力”分层：Agent 编排，`xhs-card-skill` 负责 `visual_blueprint.image_jobs` 和 PNG。
- 当前主契约是 `visual_blueprint.image_jobs`，不是固定 HTML slides。`slides` 仍保留为兼容字段，不要作为新功能的主扩展点。
- Agent/Skill 生成的 `style`、`theme`、`layout_id`、`image_provider`、`visual_blueprint`、`slides` 必须符合 [INTERFACE.md](INTERFACE.md)。
- 字数限制主要约束 legacy `slides` fallback；`image_jobs` 允许交给生图模型排版，但必须保留清晰 `title`、`message`、`source_detail` 和 `prompt`。
- Agent 在规划阶段通过 `list_layouts` 读取可用版式和主题，不要凭空编造 `layout_id`。
- 渲染结果必须保留 `png_paths` 和 `task_dir`，方便 validate 和一键准备发布工具复用。
- 每次 direct image deck 渲染必须保留 `image_prompts.json`，方便评估 planner 和 prompt 质量。
- `validate_output` 失败时，Agent 最多自动缩短文案并重渲 2 次；仍失败则保留问题列表给人工处理。

## 开发节奏

- Phase 1：锁定 `INTERFACE.md`、`docs/architecture.md` 和 ADR，避免多人开发时出现两套契约。
- Phase 2：分别验证 DeepSeek planner、Seedream/OpenAI-compatible provider 和 direct image deck 输出。
- Phase 3：把出图质量问题优先收敛到 `skills/xhs-card-skill/skill.json`、planner prompt 和 provider prompt。
- Phase 4：用真实选题回归测试，并补充反馈记录、失败诊断和人工审核流程。

关键并行点：接口锁定后，Web/API、Agent 编排、runtime skill/provider adapter 可并行推进；公共字段变化必须先更新契约文档。

## 验证要求

优先验证：

- `python3 -m unittest discover -s tests -v`
- 与图片渲染相关的单元测试，例如 schema 校验、字数硬约束、layout 选择、导出文件存在性。
- DeepSeek planner 请求测试：验证 base URL、Bearer auth、model 和 JSON response_format。
- Seedream/OpenAI-compatible provider 请求测试：验证 provider-specific 字段没有串用。
- `render_xiaohongshu` mock 测试：验证 direct image deck 不生成 HTML shell，直接返回 card PNG。
- `validate_output` 失败重试测试：最多重渲 2 次，失败后返回 issues。
- 若引入浏览器或前端渲染，使用浏览器截图检查桌面和移动端输出是否非空、无遮挡、文字不溢出。

如果命令不存在或无法运行，最终回复必须说明原因、已做的替代检查和剩余风险。

## 完成定义

完成一次开发任务前，至少确认：

- 变更范围与用户要求一致。
- 相关代码、测试和文档已同步。
- 已运行可用的最小验证命令，或明确说明无法运行的原因。
- 文生图输出路径、失败处理、重试策略和提示词可追溯性没有被忽略。
- 没有把开发用 skills、临时下载目录或个人配置混入应用代码。
