---
name: nebula-nanobanana
description: Generate or edit images through APINebula's Nano Banana Gemini-native group. Use when the user mentions Nano Banana, Gemini image models, Gemini 3 Pro image preview, Gemini 3.1 Flash image, or 1K/2K/4K Gemini resolution and aspect ratio controls.
---

# Nebula Nano Banana

Use the dedicated `nanobanana` preset and Gemini-native `generateContent` protocol. Do not send this request through the Images API or Chat Completions transport.

## Fixed routing

- Group: `nanobanana`
- Default model: `gemini-3.1-flash-image`
- Supported model families include Gemini 3.1 Flash image, its preview, Gemini 3 Pro image preview, and Gemini 2.5 Flash image.
- Default endpoint root: `https://img-api.apinebula.ai`

## Parameters

- Use `resolution=1K|2K|4K` and a documented `aspectRatio` such as `1:1`, `16:9`, or `9:16`.
- Gemini 3.1 Flash image, its preview, and Gemini 3 Pro image preview support 1K, 2K, and 4K.
- Gemini 2.5 Flash image and its preview support only 1K.
- Do not pass `size`, `quality`, `responseFormat`, `inputFidelity`, or `n`.
- The provider returns inline Base64 image data; the shared runtime saves it locally and removes the payload from metadata.
- Verify actual dimensions from the saved file rather than assuming the requested resolution.

## Use the runtime

- Prefer MCP with `preset: "nanobanana"`, `resolution`, and `aspectRatio`.
- For local edits, use `jiuge_canva_edit_image` with `imagePaths`.
- For public URL edits, use `jiuge_canva_edit_image_async` with `imageUrls`; the async suffix is retained for compatibility with the existing workflow.
- CLI generation example:

```text
jiuge-canva image generate --preset nanobanana --prompt "anime spring landscape" --resolution 2K --aspect-ratio 16:9
```

## Standalone package

This Skill package is usable without installing `jiuge-canva` or any other
model Skill. It includes a Python 3.9+ standard-library runner for the
Gemini-native APINebula endpoint.

Set `APINEBULA_API_KEY` in the process environment, then run from any folder:

```powershell
$skill = Join-Path $env:USERPROFILE ".codex\skills\nebula-nanobanana"
python "$skill\scripts\generate_image.py" `
  --prompt "anime spring landscape, no text or watermark" `
  --resolution 2K `
  --aspect-ratio 16:9 `
  --output .\nanime-landscape.png
```

Use `--model` for a supported Gemini image model. Gemini 2.5 Flash image
models accept only `1K`; Gemini 3.1 Flash image and Gemini 3 Pro image
preview accept `1K`, `2K`, and `4K`. Repeat `--reference` for local edits.

## Security and results

- Read the API key from the configured environment or Web connection settings. Never reveal or persist it.
- Report the preset, group, model, request id, local path, and actual image inspection details. Do not expose inline Base64.
