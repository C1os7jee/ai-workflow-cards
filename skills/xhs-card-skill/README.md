# xhs-card-skill

This runtime skill owns Xiaohongshu card copy preparation and PNG rendering.
The Agent layer should pass a content brief and strategy into the skill; it
should not hard-code card copy rules.

## Files

- `skill.json`: configurable copy, strategy, theme, layout, and CTA rules.
- `prepare_payload.py`: turns a content brief into render payload JSON using
  `skill.json`.
- `render_deck.py`: optionally calls a configured image API provider, then
  renders payload JSON into PNG files.
- `template.html`: card HTML/CSS screenshot template.

## Stable Tuning Points

Tune generation quality by editing `skill.json`:

- `copy_rules.stopwords`: words ignored during keyword extraction.
- `copy_rules.section_headings`: headings for content slides.
- `cta_template`: final slide copy.
- `strategies.*.cover_title_template`: cover title pattern.
- `strategies.*.cover_hook_template`: cover hook pattern.
- `strategies.*.cover_visual_template`: visual direction text.
- `strategies.*.style`, `theme`, `layout_id`: renderer appearance.
- `deck_generation.planner.*`: DeepSeek planner settings for deciding dynamic
  image jobs before rendering.
- `image_generation.default_provider`: image provider used when no request override is
  supplied.
- `image_generation.providers.*`: real image model provider credentials, model,
  size, output format, and prompt template.

Template variables:

- `{lead}`: primary keyword.
- `{secondary}`: secondary keyword.
- `{third}`: third keyword.
- `{number}`: prioritized numeric signal.
- `{first_clause}`: first extracted source clause.

## CLI

Prepare a render payload:

```bash
python3 skills/xhs-card-skill/prepare_payload.py \
  --input /path/to/brief.json
```

Input shape:

```json
{
  "content_goal": "MiniMax MoSA 让注意力计算减少 28.4 倍。",
  "strategy": "系统感封面型",
  "image_provider": "volcengine-seedream"
}
```

Render PNG:

```bash
python3 skills/xhs-card-skill/render_deck.py \
  --input /path/to/render_input.json \
  --output output
```

## Real Image Generation

When `deck_generation.planner.enabled: true`, clicking the full generation path
can ask DeepSeek to decide the final `visual_blueprint.image_jobs` first:

```text
{DEEPSEEK_BASE_URL}/chat/completions
```

using `DEEPSEEK_API_KEY` from `.env`. The default base URL is
`https://api.deepseek.com`, and the default planner model is `deepseek-v4-pro`.

When `skill.json` has `image_generation.enabled: true`, rendering calls the
provider selected by `render_input.image_provider`, falling back to
`image_generation.default_provider`.

OpenAI-compatible providers call:

```text
{OPENAI_BASE_URL}/v1/images/generations
```

using `OPENAI_API_KEY` from `.env`.

Volcengine Seedream providers call:

```text
{ARK_BASE_URL}/images/generations
```

using `ARK_API_KEY` from `.env`. The default base URL is
`https://ark.cn-beijing.volces.com/api/v3`, and the default model is
`doubao-seedream-5-0-260128`.

The generated image is saved as `generated_cover.png` inside the task directory
and injected into the cover card before screenshots are captured.

Required `.env` values:

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

If your gateway blocks server-side requests, rendering fails instead of falling
back to a fake local image. This is intentional so API-backed generation is
observable and debuggable.
