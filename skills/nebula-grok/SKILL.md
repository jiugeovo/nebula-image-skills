---
name: nebula-grok
description: Generate or edit images with APINebula's Grok Imagine group using grok-imagine-image. Use when the user mentions Grok, Grok Imagine, or grok-imagine-image and wants image generation or image editing.
---

# Nebula Grok Imagine

Use the dedicated `grok` preset and Chat Completions protocol. Do not pass Image2 or Gemini output controls to this group.

## Fixed routing

- Group: `Grok`
- Model: `grok-imagine-image`
- Transport: OpenAI-compatible Chat Completions
- Default endpoint root: `https://img-api.apinebula.ai`

## Parameters

- The current group returns 1K images.
- Put `16:9`, `9:16`, or `1:1` directly in the prompt when a ratio matters.
- Do not pass `size`, `resolution`, `aspectRatio`, `quality`, `responseFormat`, `inputFidelity`, or `n`.
- Read the Markdown image URL in the assistant response; the shared runtime extracts it and can download the image locally.
- Report actual dimensions from the saved-file inspection.

## Use the runtime

- Prefer MCP with `preset: "grok"` and a prompt containing the requested ratio.
- For local edits, use `jiuge_canva_edit_image` with `imagePaths`.
- For public URL edits, use `jiuge_canva_edit_image_async` with `imageUrls`; the async suffix is retained for compatibility with the existing workflow.
- CLI generation example:

```text
jiuge-canva image generate --preset grok --prompt "cinematic anime coast, wide 16:9, no text or watermark"
```

## Standalone package

This Skill package is usable without installing `jiuge-canva` or any other
model Skill. It includes a Python 3.9+ standard-library runner for direct
Grok Imagine requests.

Set `APINEBULA_API_KEY` in the process environment, then run from any folder:

```powershell
$skill = Join-Path $env:USERPROFILE ".codex\skills\nebula-grok"
python "$skill\scripts\generate_image.py" `
  --prompt "cinematic anime coast, wide 16:9, no text or watermark" `
  --output .\grok-coast.png
```

Put `16:9`, `9:16`, or `1:1` directly in the prompt. The standalone runner
does not accept Image2 or Gemini output controls, downloads the returned
Markdown image URL, and verifies the actual image dimensions.

## Security and results

- Read the API key from the configured environment or Web connection settings. Never reveal or persist it.
- Report the preset, group, model, request id, remote URL, local path, and actual image inspection details.
