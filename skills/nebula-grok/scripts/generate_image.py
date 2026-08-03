#!/usr/bin/env python3
"""Standalone APINebula image skill runner.

This file is copied into each model-group Skill package and reads the local
config.json beside it. It uses only the Python standard library.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import datetime as dt
import hashlib
import ipaddress
import json
import os
import re
import socket
import struct
import sys
import uuid
from pathlib import Path
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


MAX_INPUT_BYTES = 32 * 1024 * 1024
MAX_OUTPUT_BYTES = 128 * 1024 * 1024
DEFAULT_BASE_URL = "https://img-api.apinebula.ai"
QUALITY_OPTIONS = {"auto", "low", "medium", "high"}
RESOLUTION_OPTIONS = {"1K", "2K", "4K"}


def main() -> int:
    config = load_config()
    args = parse_args(config)
    try:
        prompt = read_prompt(args)
        api_key = os.environ.get("APINEBULA_API_KEY", "").strip()
        if not api_key:
            raise SkillError("APINEBULA_API_KEY is not configured.")

        settings = resolve_settings(config, args)
        references = [load_reference(value, index) for index, value in enumerate(args.reference or [], 1)]
        response = call_provider(config, settings, prompt, references, api_key)
        result = save_result(config, settings, prompt, response, args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except KeyboardInterrupt:
        print("Cancelled.", file=sys.stderr)
        return 130
    except SkillError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    except Exception as error:  # Keep unexpected failures concise and key-free.
        print(f"Error: {error}", file=sys.stderr)
        return 1


class SkillError(RuntimeError):
    """A user-facing, sanitized Skill error."""


def load_config() -> dict:
    config_path = Path(__file__).resolve().with_name("config.json")
    try:
        return json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SkillError(f"Cannot read Skill config: {config_path}") from error


def parse_args(config: dict) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=f"Standalone {config['label']} APINebula runner")
    parser.add_argument("--prompt", help="Image prompt")
    parser.add_argument("--prompt-file", help="UTF-8 file containing the prompt")
    parser.add_argument("--reference", action="append", default=[], help="Local image path or public image URL; repeatable")
    parser.add_argument("--output", help="Output image path; numbered when multiple images are returned")
    parser.add_argument("--output-dir", help="Output directory when --output is omitted")
    parser.add_argument("--base-url", help="APINebula root URL; defaults to APINEBULA_BASE_URL")
    parser.add_argument("--timeout", type=float, help="Request timeout in seconds")
    parser.add_argument("--n", type=int, help="Number of images for Image2 groups")
    parser.add_argument("--size", help="Image2 size, for example 1024x1024")
    parser.add_argument("--quality", choices=sorted(QUALITY_OPTIONS), help="Image2 quality")
    parser.add_argument("--model", help="Gemini model override within the Nano Banana group")
    parser.add_argument("--resolution", choices=sorted(RESOLUTION_OPTIONS), help="Gemini output resolution")
    parser.add_argument("--aspect-ratio", dest="aspect_ratio", help="Gemini aspect ratio, for example 16:9")
    args = parser.parse_args()
    if bool(args.prompt) == bool(args.prompt_file):
        parser.error("provide exactly one of --prompt or --prompt-file")
    return args


def read_prompt(args: argparse.Namespace) -> str:
    if args.prompt_file:
        try:
            prompt = Path(args.prompt_file).expanduser().read_text(encoding="utf-8")
        except OSError as error:
            raise SkillError(f"Cannot read prompt file: {args.prompt_file}") from error
    else:
        prompt = args.prompt or ""
    prompt = prompt.strip()
    if not prompt:
        raise SkillError("Prompt must not be empty.")
    return prompt


def resolve_settings(config: dict, args: argparse.Namespace) -> dict:
    transport = config["transport"]
    is_edit = bool(args.reference)
    settings = {
        "transport": transport,
        "preset": config["preset"],
        "group": config["group"],
        "model": config["model"],
        "is_edit": is_edit,
        "timeout": args.timeout if args.timeout is not None else config["default_timeout_seconds"],
        "base_url": normalize_base_url(args.base_url or os.environ.get("APINEBULA_BASE_URL", DEFAULT_BASE_URL)),
    }
    if settings["timeout"] <= 0:
        raise SkillError("--timeout must be positive.")

    if transport == "images":
        reject_args(args, ("resolution", "aspect_ratio", "model"), "Image2")
        sizes = config["edit_sizes"] if is_edit else config["generate_sizes"]
        size = args.size or config["default_size"]
        if size not in sizes:
            allowed = ", ".join(sizes)
            raise SkillError(f"size={size} is not supported here; use {allowed}.")
        quality = args.quality or config["default_quality"]
        if quality not in QUALITY_OPTIONS:
            raise SkillError(f"quality={quality} is not supported.")
        count = args.n if args.n is not None else 1
        if count < 1 or count > config["max_images"]:
            raise SkillError(f"--n must be between 1 and {config['max_images']} for this Skill.")
        settings.update({"size": size, "quality": quality, "count": count})
        return settings

    if transport == "gemini":
        reject_args(args, ("size", "quality", "n"), "Nano Banana")
        model = args.model or os.environ.get("NEBULA_NANOBANANA_MODEL", config["model"])
        if model not in config["models"]:
            raise SkillError(f"Model {model} is not supported by the Nano Banana group.")
        resolution = args.resolution or config["default_resolution"]
        supported_resolutions = config["model_resolutions"].get(model, ["1K"])
        if resolution not in supported_resolutions:
            raise SkillError(f"{model} supports only {', '.join(supported_resolutions)}.")
        aspect_ratio = args.aspect_ratio or config["default_aspect_ratio"]
        if aspect_ratio not in config["aspect_ratios"]:
            raise SkillError(f"aspect ratio {aspect_ratio} is not supported by this Skill.")
        settings.update({"model": model, "resolution": resolution, "aspect_ratio": aspect_ratio, "count": 1})
        return settings

    if transport == "chat":
        reject_args(args, ("size", "quality", "n", "resolution", "aspect_ratio", "model"), "Grok")
        settings["count"] = 1
        return settings

    raise SkillError(f"Unsupported Skill transport: {transport}")


def reject_args(args: argparse.Namespace, names: tuple[str, ...], label: str) -> None:
    for name in names:
        value = getattr(args, name)
        if value is not None:
            cli_name = name.replace("_", "-")
            raise SkillError(f"--{cli_name} is not supported by {label}.")


def call_provider(config: dict, settings: dict, prompt: str, references: list[dict], api_key: str) -> dict:
    base_url = settings["base_url"]
    if settings["transport"] == "images":
        if references:
            fields = {
                "model": settings["model"],
                "prompt": prompt,
                "size": settings["size"],
                "quality": settings["quality"],
                "response_format": "url",
                "input_fidelity": "high",
            }
            if settings["count"] > 1:
                fields["n"] = str(settings["count"])
            return post_multipart(f"{base_url}/v1/images/edits", fields, references, api_key, settings["timeout"])
        payload = {
            "model": settings["model"],
            "prompt": prompt,
            "size": settings["size"],
            "quality": settings["quality"],
            "response_format": "url",
        }
        if settings["count"] > 1:
            payload["n"] = settings["count"]
        return post_json(f"{base_url}/v1/images/generations", payload, api_key, settings["timeout"])

    if settings["transport"] == "gemini":
        parts = [{"text": prompt}]
        for reference in references:
            parts.append({"inlineData": {"mimeType": reference["mime_type"], "data": base64.b64encode(reference["buffer"]).decode("ascii")}})
        payload = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {
                "responseModalities": ["IMAGE"],
                "imageConfig": {
                    "imageSize": settings["resolution"],
                    "aspectRatio": settings["aspect_ratio"],
                },
            },
        }
        path = f"{base_url}/v1beta/models/{quote_path(settings['model'])}:generateContent"
        return post_json(path, payload, api_key, settings["timeout"])

    content: object = prompt
    if references:
        content = [{"type": "text", "text": prompt}]
        for reference in references:
            data_url = f"data:{reference['mime_type']};base64,{base64.b64encode(reference['buffer']).decode('ascii')}"
            content.append({"type": "image_url", "image_url": {"url": data_url}})
    payload = {
        "model": settings["model"],
        "messages": [{"role": "user", "content": content}],
        "stream": False,
    }
    return post_json(f"{base_url}/v1/chat/completions", payload, api_key, settings["timeout"])


def post_json(url: str, payload: dict, api_key: str, timeout: float) -> dict:
    body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    request = Request(url, data=body, method="POST", headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json",
        "User-Agent": "jiuge-canva-skill/1.0",
    })
    return read_json_request(request, timeout)


def post_multipart(url: str, fields: dict, references: list[dict], api_key: str, timeout: float) -> dict:
    boundary = f"----JiugeCanva{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode("utf-8"))
    for index, reference in enumerate(references, 1):
        filename = reference.get("filename") or f"reference-{index}{extension_for_mime(reference['mime_type'])}"
        chunks.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{filename}\"\r\n"
            f"Content-Type: {reference['mime_type']}\r\n\r\n".encode("utf-8")
        )
        chunks.append(reference["buffer"])
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode("ascii"))
    body = b"".join(chunks)
    request = Request(url, data=body, method="POST", headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Content-Length": str(len(body)),
        "Accept": "application/json",
        "User-Agent": "jiuge-canva-skill/1.0",
    })
    return read_json_request(request, timeout)


def read_json_request(request: Request, timeout: float) -> dict:
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except HTTPError as error:
        detail = error.read(4096).decode("utf-8", "replace")
        raise SkillError(f"APINebula HTTP {error.code}: {extract_error_message(detail)}") from error
    except (URLError, TimeoutError, OSError) as error:
        raise SkillError(f"APINebula request failed: {error}") from error
    try:
        value = json.loads(raw.decode("utf-8")) if raw else {}
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SkillError("APINebula returned a non-JSON response.") from error
    if not isinstance(value, dict):
        raise SkillError("APINebula returned an unexpected JSON shape.")
    return value


def load_reference(value: str, index: int) -> dict:
    if value.lower().startswith(("http://", "https://")):
        validate_reference_url(value)
        buffer = fetch_bytes(value, MAX_INPUT_BYTES)
        filename = Path(urlparse(value).path).name or f"reference-{index}.png"
    else:
        path = Path(value).expanduser()
        try:
            buffer = path.read_bytes()
        except OSError as error:
            raise SkillError(f"Cannot read reference image: {value}") from error
        filename = path.name
    if len(buffer) > MAX_INPUT_BYTES:
        raise SkillError("Reference image exceeds the 32 MB limit.")
    inspection = inspect_image(buffer)
    return {"buffer": buffer, "filename": filename, **inspection}


def validate_reference_url(value: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password or not parsed.hostname:
        raise SkillError("Reference URL must be a public HTTP or HTTPS URL.")
    hostname = parsed.hostname
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(hostname, None)}
    except socket.gaierror as error:
        raise SkillError("Reference URL hostname could not be resolved.") from error
    if not addresses or any(is_private_address(address) for address in addresses):
        raise SkillError("Reference URL must resolve to a public address.")


def is_private_address(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return True
    return (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def fetch_bytes(url: str, max_bytes: int) -> bytes:
    request = Request(url, headers={"Accept": "image/*", "User-Agent": "jiuge-canva-skill/1.0"})
    try:
        with urlopen(request, timeout=120) as response:
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise SkillError(f"Image download exceeds the {max_bytes // 1024 // 1024} MB limit.")
                chunks.append(chunk)
            return b"".join(chunks)
    except HTTPError as error:
        raise SkillError(f"Image download failed: HTTP {error.code}.") from error
    except (URLError, TimeoutError, OSError) as error:
        raise SkillError(f"Image download failed: {error}") from error


def save_result(config: dict, settings: dict, prompt: str, response: dict, args: argparse.Namespace) -> dict:
    images = extract_images(response)
    if not images:
        finish = response.get("candidates", [{}])[0].get("finishReason") if response.get("candidates") else None
        suffix = f" Finish reason: {finish}." if finish else ""
        raise SkillError(f"APINebula returned no usable image.{suffix}")

    base_output = resolve_output_base(args, config)
    artifacts: list[dict] = []
    for index, image in enumerate(images):
        buffer = image["buffer"] if image["kind"] == "inline" else fetch_bytes(image["url"], MAX_OUTPUT_BYTES)
        if len(buffer) > MAX_OUTPUT_BYTES:
            raise SkillError("Downloaded image exceeds the 128 MB limit.")
        inspection = inspect_image(buffer)
        output_path = numbered_output_path(base_output, index, len(images), inspection["extension"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(buffer)
        artifacts.append({
            "path": str(output_path.resolve()),
            "source": image.get("url", "inline"),
            "mime_type": inspection["mime_type"],
            "width": inspection["width"],
            "height": inspection["height"],
            "bytes": len(buffer),
        })

    metadata_path = base_output.with_suffix(".json")
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata = redact_base64(response)
    artifact_metadata = {
        "skill": config["name"],
        "preset": settings["preset"],
        "group": settings["group"],
        "model": settings["model"],
        "requested": request_summary(settings, prompt),
        "artifacts": artifacts,
    }
    metadata["jiuge_canva"] = artifact_metadata
    metadata["nebula_canvas"] = artifact_metadata
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return {
        "status": "completed",
        "skill": config["name"],
        "preset": settings["preset"],
        "group": settings["group"],
        "model": settings["model"],
        "request_id": response.get("id") or response.get("responseId"),
        "metadata_path": str(metadata_path.resolve()),
        "artifacts": artifacts,
    }


def request_summary(settings: dict, prompt: str) -> dict:
    value = {"prompt": prompt, "edit": settings["is_edit"], "count": settings["count"]}
    for key in ("size", "quality", "resolution", "aspect_ratio"):
        if key in settings:
            value[key] = settings[key]
    return value


def extract_images(response: dict) -> list[dict]:
    images: list[dict] = []

    def add_inline(value: object, mime_type: object = "image/png") -> None:
        if not isinstance(value, str) or not value:
            return
        try:
            buffer = base64.b64decode(value, validate=True)
        except (ValueError, binascii.Error):
            return
        if buffer:
            images.append({"kind": "inline", "buffer": buffer, "mime_type": str(mime_type or "image/png")})

    def add_url(value: object) -> None:
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            images.append({"kind": "url", "url": value.rstrip(".,\"'")})

    for item in response.get("data", []) if isinstance(response.get("data"), list) else []:
        if isinstance(item, dict):
            add_inline(item.get("b64_json"), item.get("mime_type", "image/png"))
            add_url(item.get("url") or item.get("download_url") or item.get("image_url"))
    for candidate in response.get("candidates", []) if isinstance(response.get("candidates"), list) else []:
        for part in candidate.get("content", {}).get("parts", []) if isinstance(candidate, dict) else []:
            if not isinstance(part, dict):
                continue
            inline = part.get("inlineData") or part.get("inline_data")
            if isinstance(inline, dict):
                add_inline(inline.get("data"), inline.get("mimeType") or inline.get("mime_type"))
    for choice in response.get("choices", []) if isinstance(response.get("choices"), list) else []:
        content = choice.get("message", {}).get("content") if isinstance(choice, dict) else None
        if isinstance(content, str):
            for match in re.findall(r"!\[[^\]]*\]\((https?://[^)\s]+)\)", content):
                add_url(match)
            for match in re.findall(r"https?://[^\s)]+", content):
                add_url(match)

    unique: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for image in images:
        digest = hashlib.sha256(image.get("buffer", b"")).hexdigest() if image["kind"] == "inline" else image.get("url")
        key = (image["kind"], image.get("url") or digest)
        if key not in seen:
            seen.add(key)
            unique.append(image)
    inline = [item for item in unique if item["kind"] == "inline"]
    return inline or [item for item in unique if item["kind"] == "url"]


def redact_base64(value: object, key: str = "") -> object:
    if isinstance(value, dict):
        return {name: redact_base64(item, name) for name, item in value.items()}
    if isinstance(value, list):
        return [redact_base64(item, key) for item in value]
    if key.lower() in {"b64_json", "data"} and isinstance(value, str) and len(value) > 128:
        return "[omitted]"
    return value


def resolve_output_base(args: argparse.Namespace, config: dict) -> Path:
    if args.output:
        path = Path(args.output).expanduser()
        return path if path.is_absolute() else Path.cwd() / path
    directory = Path(
        args.output_dir
        or os.environ.get("APINEBULA_OUTPUT_DIR")
        or os.environ.get("JIUGE_CANVA_OUTPUT_DIR")
        or os.environ.get("NEBULA_CANVAS_OUTPUT_DIR")
        or "./outputs"
    ).expanduser()
    if not directory.is_absolute():
        directory = Path.cwd() / directory
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return directory / f"{timestamp}-{config['preset']}"


def numbered_output_path(base: Path, index: int, total: int, extension: str) -> Path:
    if total == 1:
        return base.with_suffix(extension)
    stem = base.stem + f"-{index + 1:02d}"
    return base.with_name(stem + extension)


def normalize_base_url(value: str) -> str:
    base = value.strip().rstrip("/")
    if not base.startswith(("http://", "https://")):
        raise SkillError("APINEBULA_BASE_URL must be an HTTP or HTTPS root URL.")
    return base


def quote_path(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._~-]", lambda match: f"%{ord(match.group(0)):02X}", value)


def extract_error_message(raw: str) -> str:
    try:
        value = json.loads(raw)
        if isinstance(value, dict):
            error = value.get("error")
            if isinstance(error, dict) and error.get("message"):
                return str(error["message"])[:500]
            if value.get("message"):
                return str(value["message"])[:500]
    except json.JSONDecodeError:
        pass
    return raw[:500].replace("\n", " ") or "request failed"


def inspect_image(buffer: bytes) -> dict:
    if buffer.startswith(b"\x89PNG\r\n\x1a\n") and len(buffer) >= 24:
        width, height = struct.unpack(">II", buffer[16:24])
        return image_info("image/png", ".png", width, height)
    if buffer.startswith(b"\xff\xd8\xff"):
        width, height = jpeg_dimensions(buffer)
        return image_info("image/jpeg", ".jpg", width, height)
    if buffer[:6] in {b"GIF87a", b"GIF89a"} and len(buffer) >= 10:
        width, height = struct.unpack("<HH", buffer[6:10])
        return image_info("image/gif", ".gif", width, height)
    if buffer[:4] == b"RIFF" and buffer[8:12] == b"WEBP":
        width, height = webp_dimensions(buffer)
        return image_info("image/webp", ".webp", width, height)
    raise SkillError("Returned file is not a supported PNG, JPEG, WebP, or GIF image.")


def image_info(mime_type: str, extension: str, width: Optional[int], height: Optional[int]) -> dict:
    return {"mime_type": mime_type, "extension": extension, "width": width, "height": height}


def jpeg_dimensions(buffer: bytes) -> tuple[int, int]:
    position = 2
    while position + 9 < len(buffer):
        if buffer[position] != 0xFF:
            position += 1
            continue
        marker = buffer[position + 1]
        position += 2
        if marker in {0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
            continue
        if position + 2 > len(buffer):
            break
        length = struct.unpack(">H", buffer[position:position + 2])[0]
        if length < 2 or position + length > len(buffer):
            break
        if marker in set(range(0xC0, 0xC4)) | set(range(0xC5, 0xC8)) | set(range(0xC9, 0xCC)) | set(range(0xCD, 0xD0)):
            height, width = struct.unpack(">HH", buffer[position + 3:position + 7])
            return width, height
        position += length
    raise SkillError("Returned JPEG has no readable dimensions.")


def webp_dimensions(buffer: bytes) -> tuple[int, int]:
    chunk = buffer[12:16]
    if chunk == b"VP8X" and len(buffer) >= 30:
        width = 1 + int.from_bytes(buffer[24:27], "little")
        height = 1 + int.from_bytes(buffer[27:30], "little")
        return width, height
    if chunk == b"VP8L" and len(buffer) >= 25:
        bits = int.from_bytes(buffer[21:25], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    if chunk == b"VP8 " and len(buffer) >= 30:
        marker = b"\x9d\x01\x2a"
        position = buffer.find(marker, 20)
        if position >= 0 and position + 7 <= len(buffer):
            width, height = struct.unpack("<HH", buffer[position + 3:position + 7])
            return width & 0x3FFF, height & 0x3FFF
    raise SkillError("Returned WebP has no readable dimensions.")


def extension_for_mime(mime_type: str) -> str:
    return {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif", "image/webp": ".webp"}.get(mime_type, ".png")


if __name__ == "__main__":
    raise SystemExit(main())
