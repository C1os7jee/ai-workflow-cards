# ai-workflow-cards

把文章、博客、GitHub 项目或产品页转成可发布的小红书图文组图的 Agent。

当前新增了小红书 Visual Agent MVP：根据内容 brief 判断视觉策略，调用 DeepSeek planner 生成动态 `visual_blueprint.image_jobs`，再由可配置生图 provider 逐张生成最终 PNG，并记录人工反馈。

协作开发请先读：

- [docs/architecture.md](docs/architecture.md)：当前架构、模块边界、数据契约和扩展点。
- [INTERFACE.md](INTERFACE.md)：Agent 层与渲染 Skill 层的接口契约。
- [docs/decisions/ADR-001-dynamic-visual-blueprint.md](docs/decisions/ADR-001-dynamic-visual-blueprint.md)：为什么采用动态视觉蓝图。

## MVP 链路

当前合作约定的核心链路是：

```text
content brief -> VisualAgent -> xhs-card-skill -> DeepSeek planner -> visual_blueprint.image_jobs -> image provider -> PNG -> 人工审核发布
```

MVP 不做自动采集，也不直接自动发布小红书。用户输入内容 brief，Agent 负责编排策略和 skill 调用；Skill 负责生成动态视觉蓝图并调用生图 provider；最后通过本地操作台辅助人工审核和反馈记录。

Visual Agent MVP 的策略链路是：

```text
content brief -> 视觉策略 -> visual_blueprint -> PNG assets -> 人工审核 -> 反馈记录
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
│       ├── fetch.py      # fetch_url
│       ├── layouts.py    # list_layouts，读取渲染 skill 版式表
│       ├── render.py     # render_xiaohongshu，调用 runtime skill
│       └── validate.py   # validate_output，调用渲染 skill 校验脚本
├── prompts/
│   └── system.md         # IP 定位 + 小红书文案风格
├── docs/
│   ├── architecture.md   # 当前架构说明和协作边界
│   ├── decisions/        # ADR 架构决策记录
│   ├── specs/            # MVP 规格和任务清单
│   └── memories/         # 视觉策略、实验记录、帖子表现记录
├── skills/               # 应用运行时 skill，当前为 xhs-card-skill
├── output/               # 生成的 PNG，已加入 .gitignore
├── tests/
├── INTERFACE.md          # 两人协作的接口契约
├── main.py               # CLI 入口
├── requirements.txt
└── README.md
```

注意：`skills/` 是应用运行时依赖的渲染 skill 目录；外层 `../.agents/skills/` 是给开发 Agent 使用的工作流 skills，不能混入应用发布产物。

## CLI 目标形态

```bash
python main.py --url "https://github.com/xxx/yyy"
python main.py --url "https://example.com/post" --style swiss --theme IKB
python main.py --url "https://example.com/post" --slides 6 --output ./output
```

当前可运行的 Visual Agent MVP 命令：

```bash
python main.py --mode web
python main.py --input "workflow 自动化内容" --mode visual-plan
python main.py --input "workflow 自动化内容" --mode render-input
python main.py --input "workflow 自动化内容" --mode record-feedback \
  --post-id "post-001" \
  --topic "workflow post" \
  --metrics-json '{"views": 1200, "likes": 38, "saves": 96}' \
  --human-notes "收藏率不错，但封面还不够抓人"
```

页面中的“生成 PNG”会调用本地运行时渲染 skill：

```text
skills/xhs-card-skill
```

该实现现在默认走动态视觉蓝图：`brief -> DeepSeek planner -> visual_blueprint.image_jobs -> 生图 provider 逐张生成最终 PNG`。生成图片默认使用 `Volcengine Seedream`，前端仍可手动切换到保留的 `OpenAI-compatible` 生图接口。旧的 `slides JSON -> HTML -> Chrome headless 截图 -> PNG` 路径仍作为兼容兜底保留。

协作边界：

- 调整创意策略、卡图数量、planner prompt：优先改 `skills/xhs-card-skill/skill.json`。
- 调整 DeepSeek 或 Seedream/OpenAI-compatible 请求字段：改 `skills/xhs-card-skill/prepare_payload.py` 或 `render_deck.py`，并补测试。
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

## 里程碑

- Phase 1：锁定 `INTERFACE.md`、`docs/architecture.md` 和 ADR，确保协作边界清楚。
- Phase 2：打通 `DeepSeek planner -> visual_blueprint.image_jobs -> Seedream/OpenAI-compatible provider -> PNG`。
- Phase 3：把创意质量调优收敛到 `skills/xhs-card-skill/skill.json`，尽量不改 Python 代码。
- Phase 4：完善反馈记录、失败诊断和真实选题回归测试。
