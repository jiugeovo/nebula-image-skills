---
name: nebula-canvas
description: Generate or edit images through APINebula with NebulaCanvas. Use for gpt-image-2, gpt-image-2-4k, Gemini Nano Banana image models, or grok-imagine-image through the matching non-Adobe model group, using NebulaCanvas MCP, CLI, REST, or Web workflows.
---

# NebulaCanvas

Use NebulaCanvas to generate or edit APINebula images. Route every request through the model's matching group and protocol.

## Configuration

```env
APINEBULA_API_KEY=your_api_key_here
APINEBULA_BASE_URL=https://img-api.apinebula.ai
NEBULA_CANVAS_IMAGE2_MODEL=gpt-image-2
NEBULA_CANVAS_IMAGE2_4K_MODEL=gpt-image-2-4k
NEBULA_CANVAS_NANOBANANA_MODEL=gemini-3.1-flash-image
NEBULA_CANVAS_GROK_MODEL=grok-imagine-image
NEBULA_CANVAS_OUTPUT_DIR=./outputs
NEBULA_CANVAS_TIMEOUT_MS=1800000
```

Never reveal or persist an API key. A model passed in the tool call overrides the environment default.

## Preset Routing

| Intent | Preset | Group | Default model | Protocol |
| --- | --- | --- | --- | --- |
| Image 2 1K generation or editing | `image2` | `gpt-image-2-1k` | `gpt-image-2` | Images API |
| Fixed 3840x2160 Image 2 generation or editing | `image2_4k` | `image2-4k` | `gpt-image-2-4k` | Images API |
| Gemini image generation or editing | `nanobanana` | `nanobanana` | `gemini-3.1-flash-image` | Gemini native |
| Grok image generation or editing | `grok` | `Grok` | `grok-imagine-image` | Chat Completions |

Use `gpt-image-2-1k` or the legacy alias `image-2-1k` only as aliases for the `image2` preset.

## MCP Tools

Prefer MCP when available:

- `nebula_canvas_generate_image`: requires `prompt` and either `preset` or `model`.
- `nebula_canvas_edit_image`: requires `prompt`, `imagePaths`, and either `preset` or `model`.
- `nebula_canvas_edit_image_async`: requires `prompt`, `imageUrls`, and either `preset` or `model`; despite its legacy name, it uses the selected documented synchronous protocol.
- `nebula_canvas_get_task`: legacy task lookup only.

Common optional fields are `n`, `size`, `resolution`, `aspectRatio`, `quality`, `responseFormat`, `inputFidelity`, `outputDir`, `timeoutMs`, and `noDownload`. Only pass fields supported by the selected preset.

## Parameter Rules

### `image2`

- Use model `gpt-image-2` and group `gpt-image-2-1k`.
- Use `1024x1024` for generation. Edits may also use the documented `1536x1024` landscape value.
- Use quality `auto`, `low`, `medium`, or `high`.
- Keep `n=1`; this group does not provide 2K or 4K output.
- Use `inputFidelity=high` only for edits.

### `image2_4k`

- Use model `gpt-image-2-4k` and group `image2-4k`.
- Always use `size=3840x2160`.
- `n` supports 1 through 10.
- Use a timeout up to `1800000` ms for slow requests.
- Use `inputFidelity=high` only for edits.

### `nanobanana`

- Use the `nanobanana` group and Gemini native protocol.
- Use `resolution=1K|2K|4K` and a documented `aspectRatio`.
- `gemini-2.5-flash-image` and its preview support only 1K.
- Gemini 3.1 Flash, its preview, and Gemini 3 Pro preview support 1K, 2K, and 4K.
- Do not pass `size`, `quality`, `responseFormat`, `inputFidelity`, or `n`.
- The provider returns inline Base64; NebulaCanvas saves it locally and strips it from metadata.

### `grok`

- Use model `grok-imagine-image` and group `Grok`.
- The current output is 1K.
- Put `16:9`, `9:16`, or `1:1` directly in the prompt.
- Do not pass `size`, `resolution`, `aspectRatio`, `quality`, `responseFormat`, `inputFidelity`, or `n`.
- Read the Markdown image URL returned in the assistant message.

## CLI Fallback

The CLI currently generates images:

```bash
node bin/nebula-canvas.js image generate --preset image2 --prompt "A clean product photograph, soft daylight, no text or watermark." --size 1024x1024 --quality high
```

Use Web, REST, or MCP for image editing.

## Result Handling

For user-facing results, report:

- selected preset, group, and model;
- request id when returned;
- remote image URL when returned;
- local image path;
- actual width, height, and MIME type from `inspections`.

Do not infer output resolution from request parameters. Do not expose API keys or full Base64 payloads.
