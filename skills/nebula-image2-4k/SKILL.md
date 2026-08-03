---
name: nebula-image2-4k
description: Generate or edit fixed 3840x2160 images with APINebula's image2-4k group using gpt-image-2-4k. Use when the user asks for Image2 4K, 3840x2160, or high-resolution Image2 output.
---

# Nebula Image2 4K

Use the dedicated `image2_4k` preset. This group is separate from Image2 1K and always requests a fixed 3840x2160 canvas.

## Fixed routing

- Group: `image2-4k`
- Model: `gpt-image-2-4k`
- Transport: OpenAI-compatible Images API
- Default endpoint root: `https://img-api.apinebula.ai`

## Parameters

- Always use `size=3840x2160`.
- `quality` accepts `auto`, `low`, `medium`, or `high`.
- `n` accepts `1` through `10`; Web batch count is separate and is bounded by the runtime.
- Use `inputFidelity=high` only for edits.
- `responseFormat=url` or `b64_json` is valid for the Images transport.
- Do not pass Gemini-only `resolution` or `aspectRatio` controls.
- Use a timeout up to `1800000` ms for slow requests.
- Verify actual width, height, MIME type, and file size after download.

## Use the runtime

- Prefer MCP with `preset: "image2_4k"`, `size: "3840x2160"`, and `timeoutMs: 1800000`.
- For local edits, use `jiuge_canva_edit_image` with `imagePaths`.
- For public URL edits, use `jiuge_canva_edit_image_async` with `imageUrls`; the async suffix is retained for compatibility with the existing workflow.
- CLI generation example:

```text
jiuge-canva image generate --preset image2_4k --prompt "wide anime mountain valley" --size 3840x2160 --quality high --timeout-ms 1800000
```

## Standalone package

This Skill package is usable without installing `jiuge-canva` or any other
model Skill. It includes a Python 3.9+ standard-library runner and always
requests the fixed `3840x2160` canvas.

Set `APINEBULA_API_KEY` in the process environment, then run from any folder:

```powershell
$skill = Join-Path $env:USERPROFILE ".codex\skills\nebula-image2-4k"
python "$skill\scripts\generate_image.py" `
  --prompt "wide anime mountain valley, no text or watermark" `
  --quality high `
  --timeout 1800 `
  --output .\image2-4k.png
```

Request multiple outputs with `--n 1` through `--n 10`. For a local edit,
repeat `--reference` for each input image. The runner downloads results,
checks the returned file signature, and reports actual width, height, MIME
type, and byte size.

## Security and results

- Read the API key from the configured environment or Web connection settings. Never reveal or persist it.
- Report the preset, group, model, request id, remote URL, local path, and actual image inspection details.
