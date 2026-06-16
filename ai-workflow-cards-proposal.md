# ai-workflow-cards 项目方案

> OPC 创业者 IP × AI 内容自动化 · Codex Agent 执行版

---

## 一、项目目标

在 Codex 会话中输入一个 URL，由 Codex Agent 读取内容、生成符合 IP 风格的小红书图文方案，再调用本地渲染工具输出 PNG，人工审核后发布。

**核心价值：把"看到一个好内容 → 发一条小红书"从 2 小时压缩到 1 分钟。**

**MVP 范围：**
- URL 输入 → Codex 读取/提炼 → slides JSON → PNG 输出 → 一键准备发布
- 不做自动采集，手动输入 URL
- 不做小红书全自动发布（官方 API 不开放），人工点发布
- 不做完全无头自动化服务，MVP 阶段 Codex 就是内容生产的 Agent 操作台

---

## 二、技术方案

### 整体链路

```
用户在 Codex 会话里输入 URL
    ↓
Codex Agent 读取页面内容（通过内置联网/浏览能力）
    ↓
Codex 理解内容类型（GitHub项目 / AI工具页 / 技术文章）
    ↓
Codex 按 IP System Prompt 提炼文案，决定内容角度 / 版式 / 主题色
    ↓
输出 slides JSON（标题 / 要点 / 版式 / 主题色）
    ↓
本地 Python 校验 slides JSON
    ↓
guizang-social-card-skill 接收 JSON → 渲染 HTML → 截图 PNG
    ↓
validate-social-deck.mjs 校验排版质量
    ↓（不合格则由 Codex 根据 issues 修改文案重渲，最多 2 次）
输出 PNG 组图 + 文案 + 标签
    ↓
一键准备：打开 output 文件夹，复制文案和标签，打开小红书创作页
    ↓
人工拖入图片，审核，点发布
```

### 技术选型

| 组件 | 选型 | 理由 |
|------|------|------|
| Agent 操作台 | Codex Agent | 直接在开发会话中读取 URL、生成方案、调用本地代码，适合一人开发和快速迭代 |
| 内容读取 | Codex 内置联网/浏览能力 | 不单独维护抓取器，MVP 阶段由 Codex 读取网页/GitHub/文章并提炼 |
| 图文渲染 | guizang-social-card-skill | 28种版式、10套主题、质量校验脚本，排版层无需自研 |
| 本地编排 | Python CLI | 固定执行 schema 校验、渲染、validate、发布准备，方便调试和测试 |
| 渲染运行时 | Node.js + Playwright | 跑 skill 渲染和截图 |
| 工作流策略 | 固定流水线 + 局部 Agent 决策 | 流程可调试，Codex 只决定角度、版式、文案修复 |

### 为什么用固定流水线 + Codex Agent

完整流程必须固定，否则调试会变难：

```
read_url → generate_slides_json → schema_validate → render → validate → repair_or_finish
```

Codex 可以决定内容角度、版式、主题色和文案修复，但不自由改变主流程。代码负责确定性执行；Codex 负责需要判断力的部分。

---

## 三、项目结构

```
ai-workflow-cards/
├── agent/
│   ├── workflow.py       # 固定流水线：校验 → 渲染 → validate → repair 协调
│   ├── schemas.py        # slides JSON schema（Pydantic 定义）
│   └── tools/
│       ├── layouts.py    # list_layouts：读 skill 版式列表
│       ├── render.py     # render_xiaohongshu：调 skill 出图
│       └── validate.py   # validate_output：封装质量校验脚本
├── prompts/
│   └── system.md         # IP定位 + 文案风格 System Prompt（已定稿）
├── skills/               # git submodule: guizang-social-card-skill
├── output/               # 生成 PNG 存放目录（.gitignore）
├── tests/
│   ├── test_workflow.py
│   ├── test_render.py
│   └── fixtures/
│       └── minimal_slides.json
├── main.py               # CLI 入口
├── INTERFACE.md          # 接口契约文档
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

---

## 四、各模块职责

### `main.py` · CLI 入口

接收参数，读取 Codex 生成的 slides JSON 或交互式传入的 JSON 文件，调本地 workflow 执行，打印每步耗时，输出 PNG 路径。

```bash
python main.py --input tests/fixtures/minimal_slides.json
python main.py --input output/draft/slides.json --output output/run_001
```

### `agent/workflow.py` · 固定流水线

负责确定性执行本地步骤，不让 Agent 自由改流程。

```text
schema_validate
  → render_xiaohongshu
  → validate_output
  → passed ? finish : return issues for Codex repair
```

### `agent/schemas.py` · 接口契约

用 Pydantic 定义 slides JSON schema，所有字段加字数约束。这是 Agent 输出和渲染器输入之间的唯一连接点。

### `agent/tools/layouts.py` · 版式列表

读 `skills/references/layout-recipes.md`，解析返回 28 种版式骨架列表，每条包含 `id / name / best_for`。静态数据，可缓存。

### `agent/tools/render.py` · 渲染核心（最难）

接收 slides JSON，读 skill HTML 模板，把数据注入模板占位符，用 `subprocess` 调 `node render.mjs` 出图，返回 `{success, png_paths, task_dir}`。

写之前必须先读透这两个文件：
- `skills/assets/template-swiss-card.html`
- `skills/references/layout-recipes.md`

### `agent/tools/validate.py` · 质量校验

封装 skill 自带的 `validate-social-deck.mjs`，用 subprocess 调用，解析返回 `{passed, issues}`。validate 失败时 Agent 读 issues 修改 slides 内容重渲，最多重试 2 次。

### `prompts/system.md` · System Prompt（已定稿）

```
## 账号定位
垂类：AI 效率工具与内容自动化
方向：展示一个人用 AI 重构工作方式的真实过程，不做技术科普

## 人设
程序员出身的 OPC 创业者。
一个人用 AI 工具链跑内容、运营和产品。
核心标签：别人有工具，我有系统。

## 受众
25-38 岁职场人、程序员、产品经理、自由职业者。
痛点：重复劳动多，想用 AI 但不知从哪下手。
特征：需要看到真实结果才会行动，不吃焦虑营销。

## 内容原则
1. 利他优先——每条内容的标准是「读者看完能直接用」
2. 真实呈现——有截图/录屏佐证，说踩坑不只说成功
3. 简洁直接——标题一眼知道内容是什么、能获得什么
4. 具体可信——带数字（8分钟/3小时压缩到5分钟）

## 文案风格
语气：和朋友发微信，说的是干货。
不是在"教"，是在"分享我发现了什么"。
第一人称叙事，读者跟着我经历这件事。

## 标题
公式：「我 + 动作 + 结果」，结尾带反差或悬念。
必须有具体数字。

## 开头
第一句制造画面、结果或反差。
不能以"今天分享"/"本期内容"开头。

## 正文
短句，一个意思一行。
每3-4行留呼吸点：小结论或反问。

## 结尾
不写"希望对你有帮助"。
资料型/追更型/提问型/悬念型四选一，必须带互动引导。

## 禁止词
颠覆认知、绝绝子、深度好文、贩卖焦虑等过度营销词汇。
```

---

## 五、接口契约

### render_xiaohongshu 输入

```json
{
  "source_url":   "https://example.com/article",
  "source_title": "原始内容标题",
  "style":        "swiss | editorial",
  "theme":        "IKB | lemon | forest | ...",
  "deck_layout":  "S09 | M05 | ...",
  "slide_count":  5,
  "post_caption": "小红书正文文案，≤500字",
  "hashtags":     ["#AI工具", "#工作流", "#效率"],
  "slides": [
    {
      "id": "slide_01",
      "type": "cover",
      "layout_id": "S09",
      "title": "≤15字",
      "hook": "≤30字",
      "visual_hint": "首屏视觉提示，可选"
    },
    {
      "id": "slide_02",
      "type": "content",
      "layout_id": "S09",
      "heading": "≤12字",
      "points": ["≤20字", "≤20字", "≤20字"]
    },
    {
      "id": "slide_05",
      "type": "cta",
      "layout_id": "S09",
      "text": "≤20字"
    }
  ]
}
```

说明：
- `deck_layout` 是整组图的默认版式。
- `slides[].layout_id` 是单页实际版式；未填写时继承 `deck_layout`。
- `post_caption` 和 `hashtags` 用于一键准备发布，不参与图片渲染。

### render_xiaohongshu 输出

```json
{
  "success":   true,
  "png_paths": ["output/task_xxx/slide_01.png", "..."],
  "task_dir":  "output/task_xxx",
  "slides_json": "output/task_xxx/slides.json"
}
```

### validate_output 输出

```json
{
  "passed": true,
  "issues": []
}
```

> **字数是硬性限制，不是建议值。** skill 模板固定尺寸，超出会排版溢出导致 validate fail。
>
> 字数校验不能只用 Python `len()`。中文、英文、数字和符号的视觉宽度不同，schema 里要实现 `display_width` 校验：中文按 1 计，英文/数字按 0.5-0.6 计，超出直接失败。

---

## 六、Agent 生命周期

```
感知  → Codex 读取 URL 页面，识别内容类型（工具页/GitHub/文章）
规划  → Codex 查看版式列表，决定角度/slide数/风格/主题
执行  → 本地 workflow 校验 JSON，并调用 render_xiaohongshu 生成 PNG
反思  → validate_output 检查质量
         ↳ 失败：读 issues，修改 slides，重渲（最多2次）
         ↳ 通过：返回 png_paths + 文案摘要
```

边界原则：
- Codex 可以决定内容角度、版式、主题色和文案修复。
- Codex 不改变主流程；主流程固定为 `schema_validate → render → validate → repair_or_finish`。
- 每次修复必须只改 slides JSON，不直接改 skill 模板，避免把内容问题和渲染问题混在一起。

---

## 七、内容质量三道关卡

| 关卡 | 机制 | 作用 |
|------|------|------|
| 第一道 | System Prompt | 人设/语气/禁忌词约束，Codex 每次生成文案都在这个框架内 |
| 第二道 | Pydantic schema 字数校验 | 超出字数无法通过校验，从源头防止排版溢出 |
| 第三道 | validate 自动检查 | 检查溢出/字号/密度，失败则 Codex 修改文案重渲 |

---

## 八、开发计划

| Day | 任务 | 目标 |
|-----|------|------|
| 1 | 接口契约 + skill 环境验证 | `INTERFACE.md` 定稿，手动跑 `render.mjs` 出图 |
| 2 | `render.py` 最小包装器 | 用 `tests/fixtures/minimal_slides.json` 通过 Python subprocess 出 PNG |
| 3 | `workflow.py` 串联 | schema 校验 → render → validate 全链路跑通 |
| 4 | 端到端联调 | URL → PNG 全链路跑通 |
| 5 | 5个真实 URL 测试 + 一键准备工具 + 文档 | 测试通过，可用 |

**Day 1 必须做的事：**
1. 写完 `INTERFACE.md`，锁定 slides JSON、render 输出、validate 输出。
2. 把 skill clone 下来，pin 住 commit hash。
3. `npm install`，手动跑一次 `node render.mjs`，确认 Playwright/Chromium 环境正常能出 PNG。
4. 新建 `tests/fixtures/minimal_slides.json`，作为后续所有渲染测试的基准输入。

**最难的部分是 `render.py`。** skill 的模板不是简单的 `{{title}}` 占位符，是有结构的 HTML，需要先读懂 `layout-recipes.md` 和模板文件的 class 结构，再写注入逻辑。

`render.py` 分三层实现：
1. hardcode JSON 手动喂给 skill，确认模板能出图。
2. Python subprocess 调 `node render.mjs`，接收 `minimal_slides.json` 出图。
3. 接 Codex 生成的真实 slides JSON，失败时输出可读错误。

---

## 九、关键风险

| 风险 | 应对 |
|------|------|
| render.py 模板注入失败 | Day 1 先跑通 skill 环境；hardcode 数据测通后再接真实 JSON；pin 住 skill 的 git commit hash |
| Codex 输出不符合 schema | Pydantic 强校验，失败让 Codex 修复 JSON，最多 2 次 |
| 小红书无官方发布 API | MVP 做「一键准备」工具，不做全自动发布 |
| 图片复制/自动上传不稳定 | 打开 output 文件夹 + 复制文案标签 + 打开创作页，图片由人工拖入 |
| validate 一直 fail | 缩短文案字数是唯一出路，在 System Prompt 和 schema 里加更严格的字数/视觉宽度限制 |
| GitHub/skill 下载失败 | 支持 zip 下载、手动 vendor、镜像源三种 fallback；不要让安装卡住开发 |
| Node/Playwright/Chromium 环境不一致 | 增加 render smoke test，`minimal_slides.json` 必须能稳定出一组 PNG |
| URL 内容过长 | Codex 读取后先做摘要，只把与小红书选题相关的内容写入 slides JSON |
| 来源改写风险 | 保留 `source_url` 和 `source_title`，发布文案里可按需写来源或灵感出处 |

---

## 十、与 IP 运营的关系

这个项目本身就是最好的内容素材。每次用这套系统生成一条内容，「生成过程」本身就是一条工作流暴露类内容。

| 项目产出 | 对应 IP 内容类型 |
|----------|-----------------|
| 系统搭建过程 | 工作流暴露（周一） |
| 工具选型对比 | 工具测评（周四） |
| 踩坑与调试记录 | 踩坑实录（周五） |
| 每周生产数据 | 进度日记（周六） |
| 工作流费用清单 | 工具栈公开（周日） |

工具在跑，内容在产，IP 在增长——三件事同时发生。

---

*v1.0 · 2026.06*
