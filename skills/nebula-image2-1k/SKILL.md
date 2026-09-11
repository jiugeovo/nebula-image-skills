---
name: nebula-image2-1k
description: Generate or edit images through APINebula's Image2 1K group. Use for Image2 1K concept art, illustrations, composition variants, and reference-image edits, with an optional model override.
---

# Nebula Image2 1K

Use this Skill when the user explicitly asks for Image2 1K or the
`gpt-image-2-1k` group. Keep the request on this group; do not silently move
it to Gemini or Image2 4K.

## Contract

- Endpoint root: `https://img-api.apinebula.ai`.
- Default model: `gpt-image-2.5` in group `gpt-image-2-1k`.
- Override the model per request with `--model` or the
  `APINEBULA_IMAGE2_1K_MODEL` environment variable. Precedence is `--model`,
  then the environment variable, then `model` in `scripts/config.json`.
  Empty or whitespace-only values are skipped. Pass a user-specified model
  through `--model`; otherwise let the runner resolve the environment/default.
  Other model names must support the Images API and this Skill's parameters.
  Selecting a model does not change the API key's group permissions.
- Generation defaults to one `1024x1024` image.
- Supplying one or more `--reference` values switches to the edit endpoint.
  Edits default to `1024x1024` and accept the configured documented sizes plus
  custom sizes from 256 to 2048 pixels per side, up to 4 megapixels.
- `quality` accepts `auto`, `low`, `medium`, or `high`. Prefer `high` when
  preserving a reference image is important.
- The runner sends `input_fidelity=high` for edits and always inspects the
  downloaded file. Treat actual saved dimensions as authoritative.

## Invocation

The package is self-contained and requires only Python 3.9+ standard-library
modules. Read the key from the process environment and never place a real key
in a prompt, source file, metadata file, or commit.

```powershell
$skill = Join-Path $env:USERPROFILE ".codex\skills\nebula-image2-1k"
$env:APINEBULA_API_KEY = "<your-api-key>"
python "$skill\scripts\generate_image.py" `
  --prompt "a clean anime landscape after rain, no text or watermark" `
  --quality high `
  --output .\image2-1k.png
```

To use another model accepted by the same group:

```powershell
python "$skill\scripts\generate_image.py" `
  --model "your-model-name" `
  --prompt "a clean anime landscape after rain, no text or watermark" `
  --output .\image2-1k-custom-model.png
```

For an edit, repeat `--reference` for each local image:

```powershell
python "$skill\scripts\generate_image.py" `
  --prompt "replace only the foreground tomatoes with manga-style stir-fried beef; preserve the rest" `
  --reference .\input.jpg `
  --size 1536x1024 `
  --quality high `
  --output .\edited.png
```

Use `--prompt-file` for long prompts. `--base-url` and
`APINEBULA_BASE_URL` accept an HTTP(S) root; a trailing `/v1` is normalized.
Use `--dry-run` to validate parameters and see the resolved endpoint without
making an API request.

## Result handling

The runner downloads URL results, validates PNG/JPEG/WebP/GIF signatures and
dimensions, writes the image atomically, and creates a redacted JSON sidecar.
Report the Skill, group, model, request id when available, local path, MIME
type, byte count, SHA-256, and actual width and height. Do not infer final
pixels from the requested `--size` or response metadata.
