---
name: nebula-image2-4k
description: Generate or edit fixed 3840x2160 images with APINebula's image2-4k group. Use for Image2 4K requests.
---

# Nebula Image2 4K

Use this Skill when the user asks for Image2 4K or the `image2-4k` group.
Keep the request on the fixed 4K workflow and do not downgrade it to another
model group.

## Contract

- Endpoint root: `https://img-api.apinebula.ai`.
- Model: `gpt-image-2-4k` in group `image2-4k`.
- Every generation and edit requests `3840x2160` (`16:9`). The runner rejects
  other sizes for this Skill.
- `quality` accepts `auto`, `low`, `medium`, or `high`; `high` is the default.
- `--n` accepts 1 through 10. Supplying `--reference` values selects editing;
  edits send `input_fidelity=high`.
- Large requests can take up to 30 minutes. Use a suitable `--timeout`.
- Inspect the saved file and report its real pixels; request metadata is not
  proof of the returned dimensions.

## Invocation

The package is self-contained and requires only Python 3.9+ standard-library
modules. Read the key from the process environment and keep it out of prompts,
logs, source files, metadata, and commits.

```powershell
$skill = Join-Path $env:USERPROFILE ".codex\skills\nebula-image2-4k"
$env:APINEBULA_API_KEY = "<your-api-key>"
python "$skill\scripts\generate_image.py" `
  --prompt "wide anime mountain valley at sunrise, cinematic 16:9 composition, no text or watermark" `
  --quality high `
  --timeout 1800 `
  --output .\image2-4k.png
```

For multiple outputs use `--n 1` through `--n 10`. For an edit, repeat
`--reference` for each local image:

```powershell
python "$skill\scripts\generate_image.py" `
  --prompt "preserve the line art and characters; replace only the foreground dish with a manga-style dish" `
  --reference .\input.png `
  --quality high `
  --timeout 1800 `
  --output .\edited.png
```

Use `--prompt-file` for long prompts. `--base-url` and
`APINEBULA_BASE_URL` accept an HTTP(S) root; a trailing `/v1` is normalized.
Use `--dry-run` to validate a large request without sending it.

## Result handling

The runner downloads each returned URL, validates the image signature and
dimensions, writes files atomically, and creates a redacted JSON sidecar.
Report the Skill, group, model, request id when available, every local path,
MIME type, byte count, SHA-256, and actual width and height.
