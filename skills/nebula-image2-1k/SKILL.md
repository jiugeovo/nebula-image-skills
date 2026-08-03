---
name: nebula-image2-1k
description: Generate or edit images with APINebula's gpt-image-2-1k group using gpt-image-2. Use when the user mentions Image2, gpt-image-2, image-2-1k, 1K Image2, or asks for Image2 quality and size controls.
---

# Nebula Image2 1K

Use the dedicated `image2` preset. Do not substitute another model group when a request is explicitly for Image2 1K.

## Fixed routing

- Group: `gpt-image-2-1k`
- Model: `gpt-image-2`
- Transport: OpenAI-compatible Images API
- Default endpoint root: `https://img-api.apinebula.ai`

## Parameters

- Generation uses `size=1024x1024`; local or URL edits may also use the documented `1536x1024` landscape size.
- `quality` accepts `auto`, `low`, `medium`, or `high`.
- Keep `n=1`; this group does not provide 2K or 4K output.
- Use `inputFidelity=high` only for edits.
- `responseFormat=url` or `b64_json` is valid for the Images transport.
- Do not pass Gemini-only `resolution` or `aspectRatio` controls.
- Do not infer final pixels from the request; report the saved-file inspection.

## Use the runtime

- Prefer MCP with `preset: "image2"` and `prompt`.
- For local edits, use `jiuge_canva_edit_image` with `imagePaths`.
- For public URL edits, use `jiuge_canva_edit_image_async` with `imageUrls`; the async suffix is retained for compatibility with the existing workflow.
- CLI generation example:

```text
jiuge-canva image generate --preset image2 --prompt "clean anime landscape" --size 1024x1024 --quality high
```

## Standalone package

This Skill package is usable without installing `jiuge-canva` or any other
model Skill. It includes a Python 3.9+ standard-library runner for direct
APINebula requests.

Set `APINEBULA_API_KEY` in the process environment, then run from any folder:

```powershell
$skill = Join-Path $env:USERPROFILE ".codex\skills\nebula-image2-1k"
python "$skill\scripts\generate_image.py" `
  --prompt "clean anime landscape, no text or watermark" `
  --quality high `
  --output .\image2-1k.png
```

For a local edit, repeat `--reference` for each input image:

```powershell
python "$skill\scripts\generate_image.py" `
  --prompt "keep the subject and replace the background with a pink sunset" `
  --reference .\input.png `
  --output .\edited.png
```

The standalone runner accepts `APINEBULA_BASE_URL` or `--base-url` as a root
URL without `/v1`, downloads returned images, and reports actual dimensions.

## Security and results

- Read the API key from the configured environment or Web connection settings. Never reveal or persist it.
- Report the preset, group, model, request id, remote URL, local path, and actual width, height, and MIME type when returned.
