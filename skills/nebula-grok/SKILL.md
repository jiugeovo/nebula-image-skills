---
name: nebula-grok
description: Generate or edit images with APINebula's Grok Imagine group. Use for Grok Imagine or grok-imagine-image image requests.
---

# Nebula Grok Imagine

Use this Skill when the user explicitly asks for Grok Imagine or
`grok-imagine-image`. Keep the request on the configured Grok
chat-completions protocol.

## Contract

- Endpoint root: `https://img-api.apinebula.ai`.
- Model: `grok-imagine-image` in group `Grok`.
- The group currently returns 1K-class images. Put the desired composition
  ratio in the prompt, for example `16:9`, `9:16`, or `1:1`.
- Supplying one or more `--reference` values embeds the images for an edit.
- This Skill intentionally exposes no Image2 `--size` or `--quality`, Gemini
  `--resolution` or `--aspect-ratio`, or multi-output `--n` controls.
- Inspect the saved file and report its actual dimensions instead of inferring
  resolution from the prompt or response text.

## Invocation

The package is self-contained and requires only Python 3.9+ standard-library
modules. Read the key from the process environment and keep it out of prompts,
logs, source files, metadata, and commits.

```powershell
$skill = Join-Path $env:USERPROFILE ".codex\skills\nebula-grok"
$env:APINEBULA_API_KEY = "<your-api-key>"
python "$skill\scripts\generate_image.py" `
  --prompt "cinematic anime coast, wide 16:9 composition, no text or watermark" `
  --output .\grok-coast.png
```

For an edit, repeat `--reference` for each local image:

```powershell
python "$skill\scripts\generate_image.py" `
  --prompt "preserve the original illustration and replace only the foreground tomatoes with a cute flat manga-style beef dish" `
  --reference .\input.png `
  --output .\edited.png
```

Use `--prompt-file` for long prompts. `--base-url` and
`APINEBULA_BASE_URL` accept an HTTP(S) root; a trailing `/v1` is normalized.
Use `--dry-run` to validate the request without calling the provider.

## Result handling

The runner extracts image URLs or inline image data from the response,
downloads URL results, validates PNG/JPEG/WebP/GIF signatures and dimensions,
writes the image atomically, and creates a redacted JSON sidecar. Report the
Skill, group, model, request id when available, local path, MIME type, byte
count, SHA-256, and actual width and height.
