# `/rewrite` 输出 JSON 字段说明

`POST /rewrite` 返回供后续小红书帖子生成使用的精简数据包。接口以已经改写好的内容为主，事实抽取、选题判断和执行 traces 等完整内部数据仍保存在本地运行记录中。

## 完整示例

```json
{
  "run_id": "run_20260713_161545_575308",
  "source": {
    "url": "https://example.com/news",
    "title": "资讯原标题"
  },
  "post_draft": {
    "title_candidates": [
      "标题候选 1",
      "标题候选 2"
    ],
    "opening_candidates": [
      "开头候选 1",
      "开头候选 2"
    ],
    "body": "已经完成风格化改写的正文",
    "ending_options": {
      "资料型": "资料型结尾",
      "提问型": "提问型结尾"
    }
  },
  "review": {
    "risk_level": "high",
    "fact_ok": true,
    "warnings": [
      "有 1 段[似真例子],发稿前必须用你的真实经历替换"
    ],
    "fabricated_segments": [
      "[似真例子,待核对]: 示例内容[/似真例子]"
    ]
  },
  "fact_guardrails": {
    "summary": "原资讯的核心事实摘要",
    "numbers": [
      "2026年7月19日",
      "50%"
    ],
    "must_not_change": [
      "免费使用期限延长至2026年7月19日",
      "每周用量上限的50%可用于该模型"
    ]
  }
}
```

## 字段说明

| 字段 | 类型 | 是否必有 | 说明 |
| --- | --- | --- | --- |
| `run_id` | `string` | 是 | 本次改写任务的唯一编号，用于查找本地完整运行记录和提交发布反馈。 |
| `source` | `object` | 是 | 输入来源的最小必要信息。 |
| `source.url` | `string \| null` | 是 | 原资讯 URL。输入不是 URL 时为 `null`。 |
| `source.title` | `string \| null` | 是 | 提取到的原资讯标题；无法提取或输入是纯文本时可能为 `null`。 |
| `post_draft` | `object` | 是 | 后续帖子生成应主要消费的改写结果。 |
| `post_draft.title_candidates` | `string[]` | 是 | 可供选择的标题候选。生成失败时为空数组。 |
| `post_draft.opening_candidates` | `string[]` | 是 | 可供选择的开头候选。生成失败时为空数组。 |
| `post_draft.body` | `string` | 是 | 已完成风格化重写的正文，是下游最主要的输入。改写失败时会包含失败提示或为空字符串。 |
| `post_draft.ending_options` | `object<string, string>` | 是 | 不同结尾类型及对应文案，例如 `资料型`、`追更型`、`提问型`、`悬念型`。键由模型生成，不保证固定。 |
| `review` | `object` | 是 | 发布前审核信息，不属于帖子正文。 |
| `review.risk_level` | `low \| medium \| high` | 是 | 内容风险级别。`high` 表示应优先人工核对来源、产品名、日期和结论。 |
| `review.fact_ok` | `boolean` | 是 | 当前自检是否未发现事实缺失问题。`true` 只表示通过程序现有检查，不等于外部事实已经得到权威验证。 |
| `review.warnings` | `string[]` | 是 | 撞稿、禁用表达、似真例子或提取失败等发布前提醒。 |
| `review.fabricated_segments` | `string[]` | 是 | 模型明确标记为“似真例子、待核对”的正文片段。发布前必须删除，或替换成真实经历。 |
| `fact_guardrails` | `object` | 是 | 给后续帖子模型使用的事实边界，不属于最终帖子正文。 |
| `fact_guardrails.summary` | `string` | 是 | 原资讯的一句话核心事实摘要。事实锚定失败时可能是失败提示。 |
| `fact_guardrails.numbers` | `string[]` | 是 | 日期、金额、比例、数量等原文数字。后续生成不得擅自修改。 |
| `fact_guardrails.must_not_change` | `string[]` | 是 | 从事实锚点 `features` 映射出的关键事实陈述。后续可以调整表达方式，但不能改变事实含义。 |

## 下游使用约定

后续小红书帖子生成默认使用 `post_draft`。`review` 用于决定是否需要人工介入，`fact_guardrails` 用于约束二次润色不要改动关键事实。

建议在进入发帖或制图流程前满足以下条件：

1. `post_draft.body` 非空，且不包含 `[改写失败]`。
2. `review.fact_ok` 为 `true`。
3. `review.fabricated_segments` 为空；不为空时先替换或删除对应片段。
4. `review.risk_level` 为 `high` 时，人工复核 `fact_guardrails` 和原始来源。

## 本地完整记录

精简响应不会删除内部数据。每次运行的完整结果仍写入：

```text
news_rewriter_state/runs/{run_id}.json
```

完整记录包含 `fact_anchors`、`recommendation`、`draft`、`self_check` 和 `traces`，用于排查和回溯，不建议直接传给后续帖子生成接口。
