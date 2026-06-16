# ai-workflow-cards

把文章、博客、GitHub 项目或产品页转成可发布的小红书图文组图的 Agent。

当前新增了小红书 Visual Agent MVP：支持输入内容 brief 或 URL，先抓取并结构化提炼文章，再由 Visual Agent 选择视觉策略，生成渲染 payload，调用运行时 skill 输出 PNG，并记录人工反馈。

## 本次更新概览

这一版重点把“能生成”推进到“可调试、可验证、接近 guizang 展示效果”：

- URL 输入链路：`main.py --url ...` 会先抓取网页内容，再提炼成结构化 brief。
- 文章提炼：新增 `agent/tools/extract.py` 和 `skills/xhs-card-skill/extract_article_brief.py`，优先走 DeepSeek 结构化提炼，失败时用规则 fallback。
- 渲染切换：`agent/tools/render.py` 改为适配 `skills/guizang-social-card-skill`，用 guizang seed template + Playwright 输出 PNG。
- 版式质量：Swiss 内容页不再是通用卡片列表，而是按 recipe 生成 `S06/S09/S10/S11/S12` 的 Pipeline、KPI Tower、H-Bar、Ledger、Matrix 结构。
- 质量校验：渲染后调用 `validate-social-deck.mjs`，并把校验结果写入 `render_result.json`。
- 测试覆盖：新增 URL fetch、文章结构化、guizang recipe DOM、`render-deck` 等测试。

## 更新时间线

- 2026-06-10：搭建 Visual Agent MVP 骨架，定义 `agent/`、`skills/`、`tests/`、`output/` 等目录和基础 CLI。
- 2026-06-12：补齐 `INTERFACE.md`、架构文档和 ADR，确定 `visual_blueprint.image_jobs` 是主接口，`slides` 保留为兼容字段。
- 2026-06-15：接入 `xhs-card-skill` 的 DeepSeek planner、Seedream/OpenAI-compatible provider、动态 image jobs 和旧 HTML fallback。
- 2026-06-16 上午：新增 URL 输入、网页抓取、浏览器 fallback、文章结构化 brief 提炼和 `render-deck` 端到端入口。
- 2026-06-16 中午：切换运行时渲染到 `guizang-social-card-skill`，用 guizang 模板生成 HTML deck 并截图为 PNG。
- 2026-06-16 下午：把 Swiss 渲染从“简单文字卡片”升级为 guizang recipe DOM，修复密度、溢出和数字噪声问题；Hermes 样例输出达到 validator `0 fails / 0 warns`。

协作开发请先读：

- [docs/architecture.md](docs/architecture.md)：当前架构、模块边界、数据契约和扩展点。
- [INTERFACE.md](INTERFACE.md)：Agent 层与渲染 Skill 层的接口契约。
- [docs/decisions/ADR-001-dynamic-visual-blueprint.md](docs/decisions/ADR-001-dynamic-visual-blueprint.md)：为什么采用动态视觉蓝图。

## MVP 链路

当前合作约定的核心链路是：

```text
URL / content brief -> VisualAgent -> fetch/extract -> render payload -> guizang-social-card-skill -> Playwright PNG -> validate -> 人工审核发布
```

MVP 不直接自动发布小红书。用户输入 URL 或内容 brief，Agent 负责编排抓取、提炼、策略选择和渲染调用；运行时 skill 负责具体排版、截图和质量检查；最后通过本地操作台辅助人工审核和反馈记录。

Visual Agent MVP 的策略链路是：

```text
URL / content brief -> 结构化 brief -> 视觉策略 -> render payload -> PNG assets -> 人工审核 -> 反馈记录
```

## 模块分工

项目分成三层：

- Web/API 层：本地操作台、HTTP API、人工反馈入口。
- Agent 层：策略选择、调用 skill、校验 schema、维持对外契约。
- Skill 层：小红书领域规则、DeepSeek planner、provider 适配和 PNG 生成。

初步任务分工：

- Agent 层 + 整合：T1 项目初始化、T3 Agent 主循环、T5 System Prompt + layouts、T7 CLI、T8 端到端测试、T9 一键准备发布、T10 文档。
- 渲染层：T2 skill 环境验证、T4 skill 包装器、T6 validate 工具封装、渲染单元测试。

接口契约以 [INTERFACE.md](INTERFACE.md) 为准；架构边界以 [docs/architecture.md](docs/architecture.md) 为准。

## 目录约定

```text
ai-workflow-cards/
├── agent/
│   ├── agent.py          # Visual Agent 编排逻辑
│   ├── schemas.py        # visual plan / blueprint / feedback schema
│   └── tools/
│       ├── extract.py    # raw article brief -> structured brief
│       ├── fetch.py      # URL 抓取、清洗和浏览器 fallback
│       ├── layouts.py    # list_layouts，读取渲染 skill 版式表
│       ├── render.py     # render_xiaohongshu，适配 guizang runtime skill
│       └── validate.py   # validate_output，调用渲染 skill 校验脚本
├── prompts/
│   └── system.md         # IP 定位 + 小红书文案风格
├── docs/
│   ├── architecture.md   # 当前架构说明和协作边界
│   ├── decisions/        # ADR 架构决策记录
│   ├── specs/            # MVP 规格和任务清单
│   └── memories/         # 视觉策略、实验记录、帖子表现记录
├── skills/               # 应用运行时 skill：xhs-card-skill + guizang-social-card-skill
├── output/               # 生成的 PNG，已加入 .gitignore
├── tests/
├── INTERFACE.md          # 两人协作的接口契约
├── main.py               # CLI 入口
├── requirements.txt
└── README.md
```

注意：`skills/` 是应用运行时依赖目录；外层 `../.agents/skills/` 是给开发 Agent 使用的工作流 skills，不能混入应用发布产物。

当前运行时分工：

- `skills/xhs-card-skill`：保留 DeepSeek brief 提炼、planner/provider 配置和直接生图能力。
- `skills/guizang-social-card-skill`：当前 HTML recipe 渲染主路径，负责 guizang seed template、Playwright 截图和 `validate-social-deck.mjs` 质量检查。

首次拉取或切换分支后，如果 `skills/guizang-social-card-skill` 为空，先初始化 submodule：

```bash
git submodule update --init --recursive
```

## CLI 目标形态

```bash
python main.py --url "https://github.com/xxx/yyy"
python main.py --url "https://example.com/post" --style swiss --theme IKB
python main.py --url "https://example.com/post" --slides 6 --output ./output
```

当前可运行的 Visual Agent MVP 命令：

```bash
python main.py --mode web
python main.py --url "https://example.com/post" --mode visual-plan
python main.py --url "https://example.com/post" --mode render-input
python main.py --url "https://example.com/post" --mode render-deck
python main.py --input "workflow 自动化内容" --mode visual-plan
python main.py --input "workflow 自动化内容" --mode render-input
python main.py --input "workflow 自动化内容" --mode render-deck
python main.py --input "workflow 自动化内容" --mode record-feedback \
  --post-id "post-001" \
  --topic "workflow post" \
  --metrics-json '{"views": 1200, "likes": 38, "saves": 96}' \
  --human-notes "收藏率不错，但封面还不够抓人"
```

页面中的“生成 PNG”会调用本地运行时渲染 skill。当前主渲染路径是：

```text
skills/guizang-social-card-skill
```

该实现会把 Agent 输出的 `RenderInput/slides` 转成 guizang 的 HTML deck，按 Swiss / Editorial template 生成 `.poster`，再用 Playwright 截图为 PNG，并执行 `validate-social-deck.mjs`。旧的 `xhs-card-skill` direct-image-deck 能力仍作为 planner/provider 和兼容测试基础保留。

协作边界：

- 调整文章提炼、planner prompt、provider 配置：优先改 `skills/xhs-card-skill/skill.json`。
- 调整 guizang HTML 版式映射、recipe DOM 或截图/校验流程：改 `agent/tools/render.py` 和 `skills/guizang-social-card-skill`，并补测试。
- 调整 DeepSeek 或 Seedream/OpenAI-compatible 请求字段：改 `skills/xhs-card-skill/prepare_payload.py`、`extract_article_brief.py` 或 `render_deck.py`，并补测试。
- 调整页面交互和预览：改 `web/` 和 `agent/web_app.py`，不要写 provider 请求逻辑。
- 调整公共字段：先更新 [INTERFACE.md](INTERFACE.md) 和 [docs/architecture.md](docs/architecture.md)。

真实生图需要在 `.env` 中配置对应服务商密钥：

```text
OPENAI_API_KEY=...
OPENAI_BASE_URL=https://api.openai.com
OPENAI_IMAGE_MODEL=gpt-image-1

DEEPSEEK_API_KEY=...
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_TEXT_MODEL=deepseek-v4-pro

ARK_API_KEY=...
ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
ARK_IMAGE_MODEL=doubao-seedream-5-0-260128
```

本地可视化操作台默认运行在：

```text
http://127.0.0.1:8765
```

运行测试：

```bash
python3 -m unittest discover -s tests -v
```

最近一次完整验证：

```text
python -m unittest discover -s tests -v  # 28 tests OK
output/xhs-guizang-20260616-144359       # 5 cards, validator 0 fails / 0 warns
```

## 里程碑

- Phase 1：锁定 `INTERFACE.md`、`docs/architecture.md` 和 ADR，确保协作边界清楚。
- Phase 2：打通 `DeepSeek planner -> visual_blueprint.image_jobs -> Seedream/OpenAI-compatible provider -> PNG`。
- Phase 3：把创意质量调优收敛到 `skills/xhs-card-skill/skill.json`，尽量不改 Python 代码。
- Phase 4：完善反馈记录、失败诊断和真实选题回归测试。
