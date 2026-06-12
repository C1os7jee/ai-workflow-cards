# Architecture: Xiaohongshu Visual Agent

## Status

Current architecture for collaborative development.

## Objective

This project converts a content brief into publishable Xiaohongshu image cards.
The architecture is intentionally split so creative strategy, skill
configuration, model providers, rendering, and the local UI can evolve
independently.

The current default production path is:

```text
content brief
  -> VisualAgent orchestration
  -> xhs-card-skill prepare step
  -> DeepSeek planner creates visual_blueprint.image_jobs
  -> xhs-card-skill render step
  -> image provider generates final PNG cards
  -> local web UI previews output and captures feedback
```

The default planner is DeepSeek. The default image provider is Volcengine
Seedream. OpenAI-compatible image generation remains available as an explicit
fallback provider.

## Design Principles

- High cohesion: each module owns one reason to change.
- Low coupling: modules exchange explicit JSON-like payloads, not shared runtime
  objects or hidden global state.
- Skill-first behavior: creative policy lives in `skills/xhs-card-skill/skill.json`
  wherever possible, so prompt, provider, card-count, copy, and strategy tuning
  do not require Python code changes.
- Provider adapters are replaceable: model-specific request fields are isolated
  in renderer helpers.
- Fail diagnosably: planner and provider failures should surface in payloads or
  raised errors rather than silently returning fake images.
- Backward compatibility: legacy `slides` remain in the render input as a
  fallback and as a bridge for older tests/tools, but `visual_blueprint` is the
  preferred contract.

## Runtime Boundaries

### Web/UI Layer

Files:

- `web/index.html`
- `web/app.js`
- `web/styles.css`
- `agent/web_app.py`

Responsibilities:

- Collect the content brief and selected image provider.
- Call `/api/plan` for a cheap planning preview.
- Call `/api/render-deck` for full DeepSeek planning plus image generation.
- Render plan, blueprint, payload JSON, generated assets, and feedback form.

Must not:

- Contain model-provider request fields.
- Hard-code visual strategy rules.
- Mutate generated assets outside the returned output paths.

### Agent Orchestration Layer

Files:

- `agent/agent.py`
- `agent/schemas.py`
- `agent/tools/render.py`
- `agent/tools/validate.py`
- `agent/tools/layouts.py`

Responsibilities:

- Choose a high-level visual strategy.
- Invoke the runtime skill preparer and renderer through stable subprocess
  boundaries.
- Convert skill payloads into validated dataclasses.
- Preserve a `render_input_snapshot` so planning and rendering use the same
  blueprint.
- Record human feedback.

Must not:

- Know DeepSeek, Seedream, or OpenAI request formats.
- Build provider-specific prompts directly.
- Render HTML/PNG itself.

### Runtime Skill Layer

Files:

- `skills/xhs-card-skill/skill.json`
- `skills/xhs-card-skill/prepare_payload.py`
- `skills/xhs-card-skill/render_deck.py`
- `skills/xhs-card-skill/template.html`

Responsibilities:

- Own domain-specific creative policy for Xiaohongshu card generation.
- Convert content brief and strategy into a render payload.
- Ask DeepSeek to create dynamic `visual_blueprint.image_jobs` when requested.
- Fall back to skill-driven image jobs when planner mode is not AI or the
  planner fails open.
- Render final card assets by calling the selected image provider.
- Keep legacy HTML screenshot rendering as a compatibility fallback.

Must not:

- Depend on the web UI.
- Depend on agent dataclasses.
- Hide provider failures by returning fake images.

### Provider Adapter Layer

Located inside `skills/xhs-card-skill/render_deck.py` for now.

Current adapters:

- `volcengine-seedream`
- `openai-compatible`

Responsibilities:

- Convert a generic image prompt into provider-specific request payloads.
- Read provider credentials from `.env`.
- Normalize provider responses into local PNG files.

Provider adapters should stay small and stateless. If a third provider becomes
non-trivial, extract provider modules under `skills/xhs-card-skill/providers/`
without changing the public render input contract.

## Data Contracts

### Plan Request

`POST /api/plan`

```json
{
  "content_goal": "MiniMax MoSA ...",
  "image_provider": "volcengine-seedream",
  "planner_mode": "skill"
}
```

`planner_mode` is optional:

- `skill`: deterministic skill-driven blueprint, useful for cheap preview.
- `ai`: use DeepSeek planner; falls back according to skill config.

### Render Request

`POST /api/render-deck`

```json
{
  "content_goal": "MiniMax MoSA ...",
  "image_provider": "volcengine-seedream",
  "planner_mode": "ai"
}
```

The web UI defaults full rendering to `planner_mode: "ai"`.

### Render Input

The render input is the contract between Agent and Skill:

```json
{
  "style": "swiss",
  "theme": "IKB",
  "layout_id": "S12",
  "image_provider": "volcengine-seedream",
  "visual_direction": "MiniMax / MoSA 关系图",
  "visual_blueprint": {
    "mode": "direct-image-deck",
    "planner": "ai",
    "target_cards": 3,
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
  "slides": []
}
```

`visual_blueprint` is the preferred contract. `slides` remain for compatibility
with legacy render paths, validation, and old tests.

### Render Output

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

## Configuration

Environment variables:

```text
DEEPSEEK_API_KEY=...
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_TEXT_MODEL=deepseek-v4-pro

ARK_API_KEY=...
ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
ARK_IMAGE_MODEL=doubao-seedream-5-0-260128

OPENAI_API_KEY=...
OPENAI_BASE_URL=https://api.openai.com
OPENAI_IMAGE_MODEL=gpt-image-1
```

Skill configuration:

- `deck_generation.mode`: currently `direct-image-deck`.
- `deck_generation.min_cards` / `max_cards`: controls planner output bounds.
- `deck_generation.prompt_template`: converts image jobs to provider prompts.
- `deck_generation.planner.*`: DeepSeek planner settings.
- `image_generation.default_provider`: default image provider.
- `image_generation.providers.*`: provider adapter settings.
- `strategies.*`: copy and visual strategy templates.
- `copy_rules.*`: deterministic fallback extraction rules.

## Collaboration Rules

- Treat `INTERFACE.md` and this document as API contracts.
- Add fields rather than changing existing field types.
- Keep provider-specific request details out of `agent/` and `web/`.
- Keep UI-specific behavior out of `skills/xhs-card-skill/`.
- Update `skill.json` before changing Python when the desired change is a
  creative-policy or prompt-tuning change.
- Add or update tests for any contract change.
- Do not commit `.env` or generated `output/` assets.

## Extension Points

Add a new image provider:

1. Add provider config under `image_generation.providers`.
2. Add a provider dispatch branch in `_call_image_provider`.
3. Add request-building tests for provider-specific fields.
4. Keep render input unchanged.

Tune card quality:

1. Edit `deck_generation.prompt_template`.
2. Adjust `min_cards` / `max_cards`.
3. Update strategy templates or copy rules.
4. Compare generated `image_prompts.json` and PNG outputs.

Replace planner:

1. Update `deck_generation.planner.*`.
2. Keep output shape as `visual_blueprint.image_jobs`.
3. Add a test proving request URL, auth, model, and JSON response parsing.

Move provider adapters to modules:

1. Create `skills/xhs-card-skill/providers/`.
2. Move request builders without changing `render_deck.render_deck`.
3. Keep existing tests green before adding new providers.

## Review Checklist

- Does the change preserve module ownership?
- Does the change keep provider details outside the Agent/UI layers?
- Does the change remain configurable through `skill.json` where appropriate?
- Are external API responses validated before use?
- Are errors visible in `planner_error`, `generated_assets`, or raised
  exceptions?
- Do `python3 -m unittest discover -s tests -v` tests pass?

