# ADR-001: Use Dynamic Visual Blueprints for Xiaohongshu Image Generation

## Status

Accepted

## Date

2026-06-12

## Context

The first working prototype used a fixed HTML card structure and inserted
model-generated images into that structure. That proved useful for validating
the local render loop, but it constrained the image model too much:

- The model could only create a cover asset, not decide the overall visual
  composition.
- The number of images was effectively predetermined by the HTML slide schema.
- Improving output quality required code edits and template tweaks rather than
  skill configuration.
- The architecture encouraged static cards instead of a real visual planning
  process.

The product goal is different: the AI planner should decide how many images are
needed, what each image should communicate, and how each generated card should
behave as a final publishable Xiaohongshu image.

## Decision

Use a dynamic visual blueprint as the primary render contract.

The default path is:

```text
content brief
  -> DeepSeek planner
  -> visual_blueprint.image_jobs
  -> selected image provider
  -> final PNG cards
```

`visual_blueprint.image_jobs` is the preferred contract between planning and
rendering. Each image job contains:

- `id`
- `role`
- `title`
- `message`
- `source_detail`
- `prompt`
- `output_name`

The runtime skill owns this contract and configuration. The Agent layer
orchestrates it, but does not know provider-specific request details.

The default planner is DeepSeek (`deepseek-v4-pro`). The default image provider
is Volcengine Seedream. The OpenAI-compatible image provider remains as an
explicit fallback/compatibility option.

Legacy `slides` are retained in the render input to preserve compatibility with
older validation, tests, and HTML screenshot fallback rendering.

## Alternatives Considered

### Fixed HTML Template Plus Generated Cover Image

Pros:

- Easy to reason about.
- Deterministic layout.
- Works without relying on image-model text rendering quality.

Cons:

- Prevents the planner from deciding card count and composition.
- Pushes creative decisions into Python and HTML rather than model planning.
- Produces static-looking outputs.

Rejected as the primary path. Kept only as a compatibility fallback.

### Fully Hard-Code Provider-Specific Pipelines

Pros:

- Fast to implement for one provider.
- Easy to optimize for a single API.

Cons:

- Couples product behavior to vendor-specific request fields.
- Makes future provider swaps expensive.
- Forces code changes for creative-policy changes.

Rejected. Provider adapters remain isolated behind `image_provider` dispatch.

### One Big Agent Function

Pros:

- Fewer files at first.
- Simple for a solo prototype.

Cons:

- Low cohesion and high coupling.
- Hard for collaborators to modify safely.
- Hard to test provider request details separately from creative planning.

Rejected. The project uses explicit layer boundaries and JSON payload contracts.

## Consequences

Positive:

- AI can dynamically choose card count and image roles.
- Prompt and provider behavior can be tuned from `skill.json`.
- Providers can be added without changing the web UI or Agent dataclasses.
- DeepSeek planner failures can fail open to deterministic skill rules.
- Tests can verify DeepSeek planning, Seedream request payloads, and direct image
  deck rendering independently.

Trade-offs:

- Direct image cards depend more heavily on the image model's ability to render
  Chinese text and composition.
- Planner output must be validated because it is external, untrusted data.
- Legacy `slides` and new `visual_blueprint` coexist for now, which adds some
  schema duplication.
- Full rendering can incur multiple image API calls per user action.

## Guardrails

- Keep `visual_blueprint.image_jobs` additive and backward compatible.
- Do not move provider request fields into `agent/` or `web/`.
- Do not silently fall back to fake images.
- Preserve `planner_error` when DeepSeek planning fails open.
- Keep `image_prompts.json` in each task output for debugging and review.
- Run `python3 -m unittest discover -s tests -v` before pushing.

