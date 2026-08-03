---
name: jiuge-canva
description: Route generic APINebula image generation and editing requests through jiuge-canva when the user does not specify a model or model group. Use the dedicated nebula-image2-1k, nebula-image2-4k, nebula-nanobanana, or nebula-grok skill when the user names a specific model, provider, or group.
---

# jiuge-canva Router

Use this skill as the default entry point for an image request without an explicit model choice. Keep model-specific protocol and parameter rules in the dedicated skill for that group.

## Route the request

- Route `image2`, `gpt-image-2`, `gpt-image-2-1k`, or an unspecified ordinary image request to `image2` and the `nebula-image2-1k` skill.
- Route `image2_4k`, `gpt-image-2-4k`, `4K`, or `3840x2160` requests to `image2_4k` and the `nebula-image2-4k` skill.
- Route `Nano Banana`, `Gemini image`, `gemini-*image*`, or Gemini resolution/aspect-ratio requests to `nanobanana` and the `nebula-nanobanana` skill.
- Route `Grok`, `Grok Imagine`, or `grok-imagine-image` requests to `grok` and the `nebula-grok` skill.
- If the user names a model or group, follow that dedicated skill directly instead of applying generic defaults.
- The legacy Adobe group is unavailable in jiuge-canva.

## Execute through jiuge-canva

- Prefer `jiuge_canva_generate_image`, `jiuge_canva_edit_image`, or `jiuge_canva_edit_image_async` through the shared MCP server when available.
- Otherwise use the CLI for generation or the local Web workbench for editing.
- Always pass the selected `preset` explicitly so the shared runtime validates the correct group.
- Do not invent parameters from another group. If the request becomes model-specific, hand off to the matching dedicated skill.
- Keep API keys out of prompts, output metadata, manifests, logs, and responses.

## Report the result

- Report the selected preset, APINebula group, model, request id when available, remote URL when available, local output path, and actual dimensions from `inspections`.
- Do not infer final image dimensions from the requested size or resolution.
