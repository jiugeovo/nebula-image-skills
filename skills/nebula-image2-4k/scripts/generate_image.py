#!/usr/bin/env python3
"""Standalone APINebula runner used by each independent image Skill."""

from __future__ import annotations

import argparse
import base64
import binascii
import datetime as datetime_module
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
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit, urlunsplit
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "https://img-api.apinebula.ai"
MAX_INPUT_BYTES = 32 * 1024 * 1024
MAX_OUTPUT_BYTES = 128 * 1024 * 1024
MAX_RESPONSE_BYTES = 256 * 1024 * 1024
USER_AGENT = "apinebula-image-skill/2.1"
IMAGE_DATA_URI = re.compile(r"^data:(image/[^;,]+);base64,(.+)$", re.IGNORECASE | re.DOTALL)
SIZE_PATTERN = re.compile(r"^(\d+)x(\d+)$", re.IGNORECASE)


class SkillError(RuntimeError):
    """A user-facing error that does not expose credentials."""


def main() -> int:
    config = load_config()
    parser = build_parser(config)
    args = parser.parse_args()
    api_key = os.environ.get("APINEBULA_API_KEY", "").strip()
    try:
        prompt = read_prompt(args)
        references = [load_reference(value, index) for index, value in enumerate(args.reference, 1)]
        settings = resolve_settings(config, args, len(references))
        if args.dry_run:
            print(json.dumps(dry_run_summary(settings, prompt), ensure_ascii=False, indent=2))
            return 0
        if not api_key:
            raise SkillError("APINEBULA_API_KEY is not configured.")
        response = call_provider(config, settings, prompt, references, api_key)
        result = save_result(config, settings, prompt, response, args, api_key)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except KeyboardInterrupt:
        print("Cancelled.", file=sys.stderr)
        return 130
    except SkillError as error:
        print(f"Error: {sanitize_message(str(error), api_key if 'api_key' in locals() else '')}", file=sys.stderr)
        return 1
    except Exception as error:  # Keep unexpected failures concise and credential-free.
        print(f"Error: {sanitize_message(str(error), api_key if 'api_key' in locals() else '')}", file=sys.stderr)
        return 1


def load_config() -> Dict[str, Any]:
    config_path = Path(__file__).resolve().with_name("config.json")
    try:
        value = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SkillError(f"Cannot read Skill config: {config_path}") from error
    if not isinstance(value, dict):
        raise SkillError("Skill config must be a JSON object.")
    return value


def build_parser(config: Dict[str, Any]) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=f"Standalone {config['label']} runner")
    parser.add_argument("--version", action="version", version=str(config.get("version", "2.0")))
    prompts = parser.add_mutually_exclusive_group(required=True)
    prompts.add_argument("--prompt", help="Image prompt")
    prompts.add_argument("--prompt-file", help="UTF-8 text file containing the image prompt")
    parser.add_argument(
        "--reference",
        action="append",
        default=[],
        metavar="PATH_OR_URL",
        help="Local image path or public HTTP(S) image URL; repeat for edits",
    )
    parser.add_argument("--output", help="Output image path")
    parser.add_argument("--output-dir", help="Directory used when --output is omitted")
    parser.add_argument("--base-url", help="APINebula root URL; /v1 is removed if supplied")
    parser.add_argument("--timeout", type=float, help="Request timeout in seconds")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate inputs and print the request summary without calling APINebula",
    )

    transport = config["transport"]
    if transport == "images":
        parser.add_argument("--size", metavar="WIDTHxHEIGHT", help="Output size")
        parser.add_argument(
            "--quality",
            choices=config["generation"].get("qualities", ["auto", "low", "medium", "high"]),
            help="Image quality",
        )
        parser.add_argument("--n", type=int, help="Number of outputs")
    elif transport == "gemini":
        parser.add_argument("--model", choices=config["models"], help="Gemini image model")
        resolutions = config.get("resolutions") or sorted(
            {resolution for values in config.get("model_resolutions", {}).values() for resolution in values}
        )
        parser.add_argument("--resolution", choices=resolutions, help="Image resolution")
        parser.add_argument("--aspect-ratio", dest="aspect_ratio", choices=config["aspect_ratios"], help="Image aspect ratio")
    elif transport != "chat":
        parser.error(f"Unsupported Skill transport: {transport}")
    return parser


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


def resolve_settings(config: Dict[str, Any], args: argparse.Namespace, reference_count: int) -> Dict[str, Any]:
    if reference_count > int(config.get("max_references", 8)):
        raise SkillError(f"At most {config.get('max_references', 8)} reference images are supported.")
    timeout = args.timeout if args.timeout is not None else float(config["default_timeout_seconds"])
    if timeout <= 0:
        raise SkillError("--timeout must be positive.")

    settings: Dict[str, Any] = {
        "transport": config["transport"],
        "skill": config["name"],
        "group": config["group"],
        "model": config["model"],
        "edit": reference_count > 0,
        "reference_count": reference_count,
        "timeout": timeout,
        "base_url": normalize_base_url(
            args.base_url or os.environ.get("APINEBULA_BASE_URL", config.get("endpoint", DEFAULT_BASE_URL))
        ),
    }

    if config["transport"] == "images":
        section = config["editing"] if reference_count else config["generation"]
        size = normalize_size(args.size or section["default_size"])
        if size not in section.get("sizes", []) and not is_custom_size_allowed(section, size):
            allowed = ", ".join(section.get("sizes", []))
            raise SkillError(f"size={size} is not supported here; use {allowed}.")
        quality = args.quality or section.get("default_quality", config["generation"].get("default_quality", "medium"))
        qualities = set(section.get("qualities", config["generation"].get("qualities", [])))
        if quality not in qualities:
            raise SkillError(f"quality={quality} is not supported by this Skill.")
        count = args.n if args.n is not None else 1
        max_images = int(config["max_images"])
        if count < 1 or count > max_images:
            raise SkillError(f"--n must be between 1 and {max_images} for this Skill.")
        settings.update({"size": size, "quality": quality, "count": count})
        return settings

    if config["transport"] == "gemini":
        model = args.model or os.environ.get(config.get("model_env", ""), config["model"])
        if model not in config["models"]:
            raise SkillError(f"Model {model} is not supported by this Skill.")
        resolution = args.resolution or config["default_resolution"]
        supported_resolutions = config.get("model_resolutions", {}).get(model, ["1K"])
        if resolution not in supported_resolutions:
            raise SkillError(f"{model} supports only {', '.join(supported_resolutions)}.")
        aspect_ratio = args.aspect_ratio or config["default_aspect_ratio"]
        if aspect_ratio not in config["aspect_ratios"]:
            raise SkillError(f"aspect ratio {aspect_ratio} is not supported by this Skill.")
        settings.update({"model": model, "resolution": resolution, "aspect_ratio": aspect_ratio, "count": 1})
        return settings

    if config["transport"] == "chat":
        settings["count"] = 1
        return settings

    raise SkillError(f"Unsupported Skill transport: {config['transport']}")


def dry_run_summary(settings: Dict[str, Any], prompt: str) -> Dict[str, Any]:
    """Expose validated intent without echoing the full prompt or credentials."""
    summary: Dict[str, Any] = {
        "status": "dry-run",
        "skill": settings["skill"],
        "group": settings["group"],
        "model": settings["model"],
        "transport": settings["transport"],
        "endpoint": endpoint_for(settings),
        "mode": "edit" if settings["edit"] else "generate",
        "reference_count": settings["reference_count"],
        "prompt_characters": len(prompt),
    }
    for key in ("size", "quality", "resolution", "aspect_ratio", "count", "timeout"):
        if key in settings:
            summary[key] = settings[key]
    return summary


def endpoint_for(settings: Dict[str, Any]) -> str:
    if settings["transport"] == "images":
        suffix = "/v1/images/edits" if settings["edit"] else "/v1/images/generations"
    elif settings["transport"] == "gemini":
        suffix = f"/v1beta/models/{quote(settings['model'], safe='.-_~')}:generateContent"
    else:
        suffix = "/v1/chat/completions"
    return f"{settings['base_url']}{suffix}"


def normalize_size(value: str) -> str:
    match = SIZE_PATTERN.fullmatch(value.strip())
    if not match:
        raise SkillError("--size must use WIDTHxHEIGHT, for example 1024x1024.")
    return f"{int(match.group(1))}x{int(match.group(2))}"


def is_custom_size_allowed(section: Dict[str, Any], size: str) -> bool:
    if not section.get("allow_custom_size"):
        return False
    match = SIZE_PATTERN.fullmatch(size)
    if not match:
        return False
    width, height = int(match.group(1)), int(match.group(2))
    minimum = int(section.get("min_dimension", 1))
    maximum = int(section.get("max_dimension", 100000))
    max_pixels = int(section.get("max_pixels", maximum * maximum))
    return minimum <= width <= maximum and minimum <= height <= maximum and width * height <= max_pixels


def call_provider(
    config: Dict[str, Any], settings: Dict[str, Any], prompt: str, references: List[Dict[str, Any]], api_key: str
) -> Dict[str, Any]:
    base_url = settings["base_url"]
    if settings["transport"] == "images":
        if references:
            fields: Dict[str, str] = {
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
        payload: Dict[str, Any] = {
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
        parts: List[Dict[str, Any]] = [{"text": prompt}]
        for reference in references:
            parts.append(
                {
                    "inlineData": {
                        "mimeType": reference["mime_type"],
                        "data": base64.b64encode(reference["buffer"]).decode("ascii"),
                    }
                }
            )
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
        model_path = quote(settings["model"], safe=".-_~")
        return post_json(f"{base_url}/v1beta/models/{model_path}:generateContent", payload, api_key, settings["timeout"])

    content: Any = prompt
    if references:
        content = [{"type": "text", "text": prompt}]
        for reference in references:
            encoded = base64.b64encode(reference["buffer"]).decode("ascii")
            content.append({"type": "image_url", "image_url": {"url": f"data:{reference['mime_type']};base64,{encoded}"}})
    payload = {
        "model": settings["model"],
        "messages": [{"role": "user", "content": content}],
        "stream": False,
    }
    return post_json(f"{base_url}/v1/chat/completions", payload, api_key, settings["timeout"])


def post_json(url: str, payload: Dict[str, Any], api_key: str, timeout: float) -> Dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    request = Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    return read_json_response(request, timeout)


def post_multipart(
    url: str, fields: Dict[str, str], references: List[Dict[str, Any]], api_key: str, timeout: float
) -> Dict[str, Any]:
    boundary = f"----APINebulaSkill{uuid.uuid4().hex}"
    chunks: List[bytes] = []
    for name, value in fields.items():
        chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode("utf-8"))
    for index, reference in enumerate(references, 1):
        filename = safe_filename(reference.get("filename", ""), index, reference["mime_type"])
        chunks.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{filename}"\r\n'
            f'Content-Type: {reference["mime_type"]}\r\n\r\n'.encode("utf-8")
        )
        chunks.extend([reference["buffer"], b"\r\n"])
    chunks.append(f"--{boundary}--\r\n".encode("ascii"))
    body = b"".join(chunks)
    request = Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    return read_json_response(request, timeout)


def read_json_response(request: Request, timeout: float) -> Dict[str, Any]:
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = read_limited(response, MAX_RESPONSE_BYTES)
            header_request_id = response.headers.get("x-request-id") or response.headers.get("request-id")
    except HTTPError as error:
        detail = error.read(MAX_RESPONSE_BYTES).decode("utf-8", "replace")
        message = extract_error_message(detail)
        request_id = extract_request_id(detail)
        suffix = f" (request id: {request_id})" if request_id else ""
        raise SkillError(f"APINebula HTTP {error.code}: {message}{suffix}") from error
    except (URLError, TimeoutError, OSError) as error:
        raise SkillError(f"APINebula request failed: {error}") from error
    try:
        value = json.loads(raw.decode("utf-8")) if raw else {}
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SkillError("APINebula returned a non-JSON response.") from error
    if not isinstance(value, dict):
        raise SkillError("APINebula returned an unexpected JSON shape.")
    if header_request_id and not request_id_from(value):
        value["_skill_request_id"] = header_request_id
    return value


def read_limited(response: Any, max_bytes: int) -> bytes:
    content_length = response.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > max_bytes:
                raise SkillError(f"Response exceeds the {max_bytes // 1024 // 1024} MB limit.")
        except ValueError:
            pass
    chunks: List[bytes] = []
    total = 0
    while True:
        chunk = response.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise SkillError(f"Response exceeds the {max_bytes // 1024 // 1024} MB limit.")
        chunks.append(chunk)
    return b"".join(chunks)


def load_reference(value: str, index: int) -> Dict[str, Any]:
    if value.lower().startswith(("http://", "https://")):
        validate_public_url(value)
        buffer = fetch_bytes(value, MAX_INPUT_BYTES, validate_final_url=True)
        filename = Path(urlsplit(value).path).name or f"reference-{index}.png"
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


def validate_public_url(value: str) -> None:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password or not parsed.hostname:
        raise SkillError("Image URL must be a public HTTP or HTTPS URL.")
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(parsed.hostname, parsed.port or None)}
    except (socket.gaierror, OSError) as error:
        raise SkillError("Image URL hostname could not be resolved.") from error
    if not addresses or any(is_private_address(address) for address in addresses):
        raise SkillError("Image URL must resolve to a public address.")


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


def fetch_bytes(url: str, max_bytes: int, validate_final_url: bool = False) -> bytes:
    request = Request(url, headers={"Accept": "image/*,application/octet-stream", "User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=180) as response:
            if validate_final_url:
                validate_public_url(response.geturl())
            return read_limited(response, max_bytes)
    except HTTPError as error:
        raise SkillError(f"Image download failed: HTTP {error.code}.") from error
    except (URLError, TimeoutError, OSError) as error:
        raise SkillError(f"Image download failed: {error}") from error


def save_result(
    config: Dict[str, Any],
    settings: Dict[str, Any],
    prompt: str,
    response: Dict[str, Any],
    args: argparse.Namespace,
    api_key: str,
) -> Dict[str, Any]:
    images = extract_images(response)
    if not images:
        finish = None
        candidates = response.get("candidates")
        if isinstance(candidates, list) and candidates and isinstance(candidates[0], dict):
            finish = candidates[0].get("finishReason") or candidates[0].get("finish_reason")
        suffix = f" Finish reason: {finish}." if finish else ""
        raise SkillError(f"APINebula returned no usable image.{suffix}")

    base_output = resolve_output_base(args, config)
    artifacts: List[Dict[str, Any]] = []
    failures: List[str] = []
    for index, image in enumerate(images):
        try:
            buffer = (
                image["buffer"]
                if image["kind"] == "inline"
                else fetch_bytes(image["url"], MAX_OUTPUT_BYTES, True)
            )
            inspection = inspect_image(buffer)
        except SkillError as error:
            failures.append(str(error))
            continue
        output_path = numbered_output_path(base_output, index, len(images), inspection["extension"])
        atomic_write_bytes(output_path, buffer)
        artifacts.append(
            {
                "path": str(output_path.resolve()),
                "source": image.get("url", "inline"),
                "mime_type": inspection["mime_type"],
                "width": inspection["width"],
                "height": inspection["height"],
                "bytes": len(buffer),
                "sha256": hashlib.sha256(buffer).hexdigest(),
            }
        )
    if not artifacts:
        detail = f" {failures[0]}" if failures else ""
        raise SkillError(f"No returned image could be downloaded and inspected.{detail}")

    metadata_path = base_output.with_suffix(".json")
    metadata = redact_response(response, api_key=api_key)
    metadata["apinebula_skill"] = {
        "name": config["name"],
        "group": settings["group"],
        "model": settings["model"],
        "requested": request_summary(settings, sanitize_message(prompt, api_key)),
        "artifacts": artifacts,
    }
    if failures:
        metadata["apinebula_skill"]["download_failures"] = failures
    atomic_write_text(metadata_path, json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
    return {
        "status": "completed",
        "skill": config["name"],
        "group": settings["group"],
        "model": settings["model"],
        "request_id": request_id_from(response),
        "metadata_path": str(metadata_path.resolve()),
        "artifacts": artifacts,
        **({"download_failures": failures} if failures else {}),
    }


def request_summary(settings: Dict[str, Any], prompt: str) -> Dict[str, Any]:
    value: Dict[str, Any] = {
        "prompt": prompt,
        "edit": settings["edit"],
        "reference_count": settings["reference_count"],
        "count": settings["count"],
    }
    for key in ("size", "quality", "resolution", "aspect_ratio"):
        if key in settings:
            value[key] = settings[key]
    return value


def extract_images(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    images: List[Dict[str, Any]] = []

    def add_inline(value: Any, mime_type: Any = "image/png") -> None:
        if not isinstance(value, str) or not value:
            return
        encoded = re.sub(r"\s+", "", value)
        try:
            buffer = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            return
        if buffer and len(buffer) <= MAX_OUTPUT_BYTES:
            images.append({"kind": "inline", "buffer": buffer, "mime_type": str(mime_type or "image/png")})

    def add_url(value: Any) -> None:
        if not isinstance(value, str):
            return
        value = value.strip().rstrip(".,\"'")
        data_match = IMAGE_DATA_URI.match(value)
        if data_match:
            add_inline(data_match.group(2), data_match.group(1))
        elif value.startswith(("http://", "https://")):
            images.append({"kind": "url", "url": value})

    def walk(value: Any, key: str = "") -> None:
        if isinstance(value, dict):
            for name, item in value.items():
                lower = name.lower()
                if lower in {"b64_json", "base64", "base64_data"}:
                    add_inline(item, value.get("mime_type") or value.get("mimeType") or "image/png")
                elif lower in {"url", "download_url", "image_url", "uri", "file_uri"}:
                    if isinstance(item, dict):
                        walk(item, name)
                    else:
                        add_url(item)
                elif lower in {"inline_data", "inlinedata"} and isinstance(item, dict):
                    add_inline(item.get("data"), item.get("mimeType") or item.get("mime_type") or "image/png")
                else:
                    walk(item, name)
        elif isinstance(value, list):
            for item in value:
                walk(item, key)
        elif isinstance(value, str) and key in {"content", "text", "message"}:
            for match in re.findall(r"!\[[^\]]*\]\((https?://[^)\s]+)", value):
                add_url(match)
            for match in re.findall(r"https?://[^\s)]+", value):
                add_url(match)
            for match in re.findall(r"data:image/[^\s)]+", value, re.IGNORECASE):
                add_url(match)

    walk(response)
    unique: List[Dict[str, Any]] = []
    seen: set = set()
    for image in images:
        if image["kind"] == "inline":
            identity = ("inline", hashlib.sha256(image["buffer"]).hexdigest())
        else:
            identity = ("url", image["url"])
        if identity not in seen:
            seen.add(identity)
            unique.append(image)
    inline = [image for image in unique if image["kind"] == "inline"]
    return unique


def resolve_output_base(args: argparse.Namespace, config: Dict[str, Any]) -> Path:
    if args.output:
        path = Path(args.output).expanduser()
        return path if path.is_absolute() else Path.cwd() / path
    directory = Path(args.output_dir or os.environ.get("APINEBULA_OUTPUT_DIR", "./outputs")).expanduser()
    if not directory.is_absolute():
        directory = Path.cwd() / directory
    timestamp = datetime_module.datetime.now(datetime_module.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return directory / f"{timestamp}-{config['name']}"


def numbered_output_path(base: Path, index: int, total: int, extension: str) -> Path:
    if total == 1:
        return base.with_suffix(extension)
    return base.with_name(f"{base.stem}-{index + 1:02d}{extension}")


def atomic_write_bytes(path: Path, contents: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_bytes(contents)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_write_text(path: Path, contents: str) -> None:
    atomic_write_bytes(path, contents.encode("utf-8"))


def normalize_base_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password or not parsed.hostname:
        raise SkillError("APINEBULA_BASE_URL must be an HTTP or HTTPS root URL.")
    if parsed.query or parsed.fragment:
        raise SkillError("APINEBULA_BASE_URL must not contain a query or fragment.")
    path = parsed.path.rstrip("/")
    if path.lower().endswith("/v1"):
        path = path[:-3].rstrip("/")
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", "")).rstrip("/")


def request_id_from(value: Any) -> Optional[str]:
    if not isinstance(value, dict):
        return None
    for key in ("id", "request_id", "requestId", "responseId", "task_id", "taskId", "_skill_request_id"):
        candidate = value.get(key)
        if isinstance(candidate, (str, int)) and str(candidate):
            return str(candidate)
    return None


def extract_request_id(raw: str) -> Optional[str]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        value = None
    if isinstance(value, dict):
        direct = request_id_from(value)
        if direct:
            return direct
        error = value.get("error")
        if isinstance(error, dict):
            return request_id_from(error)
    match = re.search(r"request\s*id\s*[:=]\s*([A-Za-z0-9_-]+)", raw, re.IGNORECASE)
    return match.group(1) if match else None


def extract_error_message(raw: str) -> str:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        value = None
    if isinstance(value, dict):
        error = value.get("error")
        if isinstance(error, dict):
            for key in ("message", "detail", "code"):
                if error.get(key):
                    return sanitize_message(str(error[key]))[:500]
        for key in ("message", "detail"):
            if value.get(key):
                return sanitize_message(str(value[key]))[:500]
    return sanitize_message(raw[:500].replace("\n", " ")) or "request failed"


def redact_response(value: Any, key: str = "", api_key: str = "") -> Any:
    if isinstance(value, dict):
        return {
            name: redact_response(item, name, api_key)
            for name, item in value.items()
            if name != "_skill_request_id"
        }
    if isinstance(value, list):
        return [redact_response(item, key, api_key) for item in value]
    if isinstance(value, str):
        if key.lower() in {"b64_json", "base64", "base64_data", "data"} and len(value) > 128:
            return "[omitted]"
        return sanitize_message(value, api_key)
    return value


def sanitize_message(value: str, api_key: str = "") -> str:
    result = value
    if api_key:
        result = result.replace(api_key, "[redacted]")
    result = re.sub(r"Bearer\s+[A-Za-z0-9._~-]+", "Bearer [redacted]", result, flags=re.IGNORECASE)
    result = re.sub(r"\bsk-[A-Za-z0-9]{20,}\b", "[redacted-key]", result)
    return result


def safe_filename(value: str, index: int, mime_type: str) -> str:
    name = Path(value).name
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name).strip("._")
    if not name:
        name = f"reference-{index}{extension_for_mime(mime_type)}"
    return name[:120]


def inspect_image(buffer: bytes) -> Dict[str, Any]:
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


def image_info(mime_type: str, extension: str, width: int, height: int) -> Dict[str, Any]:
    if width <= 0 or height <= 0:
        raise SkillError("Returned image has invalid dimensions.")
    return {"mime_type": mime_type, "extension": extension, "width": width, "height": height}


def jpeg_dimensions(buffer: bytes) -> Tuple[int, int]:
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
        length = struct.unpack(">H", buffer[position : position + 2])[0]
        if length < 2 or position + length > len(buffer):
            break
        if marker in set(range(0xC0, 0xC4)) | set(range(0xC5, 0xC8)) | set(range(0xC9, 0xCC)) | set(range(0xCD, 0xD0)):
            height, width = struct.unpack(">HH", buffer[position + 3 : position + 7])
            return width, height
        position += length
    raise SkillError("Returned JPEG has no readable dimensions.")


def webp_dimensions(buffer: bytes) -> Tuple[int, int]:
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
            width, height = struct.unpack("<HH", buffer[position + 3 : position + 7])
            return width & 0x3FFF, height & 0x3FFF
    raise SkillError("Returned WebP has no readable dimensions.")


def extension_for_mime(mime_type: str) -> str:
    return {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif", "image/webp": ".webp"}.get(mime_type, ".png")


if __name__ == "__main__":
    raise SystemExit(main())
