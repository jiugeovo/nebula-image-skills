---
name: nebula-nanobanana
description: Generate or edit images through APINebula's Gemini-native Nano Banana group. Use for Nano Banana, Gemini image, resolution, or aspect-ratio requests.
---

# Nebula Nano Banana

Use this Skill when the user asks for Nano Banana or a Gemini image model.
Use the Gemini `generateContent` protocol defined by the runner; do not
translate the request to an Images API or chat-completions request.

## Contract

- Endpoint root: `https://img-api.apinebula.ai`.
- Default model: `gemini-3.1-flash-image` in group `nanobanana`.
- Supported models, model-specific resolutions, and aspect ratios are the
  source of truth in `scripts/config.json`.
- Use `--resolution 1K`, `2K`, or `4K` only when the selected model supports
  it. The 2.5 Flash image models are restricted to `1K`.
- Use `--aspect-ratio` for the configured ratios, including `1:1`, `2:3`,
  `3:2`, `9:16`, `16:9`, and `21:9`.
- Supplying one or more `--reference` values embeds the images in the Gemini
  request and selects editing.
- Do not pass Image2-only `--size`, `--quality`, or `--n` options.

## Invocation

The package is self-contained and requires only Python 3.9+ standard-library
modules. Read the key from the process environment and never put a real key
in a prompt, source file, metadata file, or commit. Select another configured
model with `--model` or `APINEBULA_NANOBANANA_MODEL`.

```powershell
$skill = Join-Path $env:USERPROFILE ".codex\skills\nebula-nanobanana"
$env:APINEBULA_API_KEY = "<your-api-key>"
python "$skill\scripts\generate_image.py" `
  --prompt "an anime spring landscape above a sea of clouds, no text or watermark" `
  --resolution 2K `
  --aspect-ratio 16:9 `
  --output .\anime-landscape.png
```

For an edit, repeat `--reference` for each local image:

```powershell
python "$skill\scripts\generate_image.py" `
  --prompt "keep the original illustration and replace only the red food with flat manga-style stir-fried beef" `
  --reference .\input.jpg `
  --resolution 1K `
  --aspect-ratio 1:1 `
  --output .\edited.png
```

Use `--prompt-file` for long prompts. `--base-url` and
`APINEBULA_BASE_URL` accept an HTTP(S) root; a trailing `/v1` is normalized.
Use `--dry-run` to validate the model, resolution, and ratio without making an
API request.

## Result handling

The runner extracts inline image data, validates the saved file's signature
and real dimensions, writes it atomically, and creates a redacted JSON
sidecar. Report the Skill, group, model, request id when available, local path,
MIME type, byte count, SHA-256, and actual width and height. Treat requested
resolution and ratio as intent, not proof of the final pixels.
