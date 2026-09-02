#!/usr/bin/env python3
"""Validate the four independent Skills without third-party dependencies."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import urlsplit


SKILL_NAMES = (
    "nebula-image2-1k",
    "nebula-image2-4k",
    "nebula-nanobanana",
    "nebula-grok",
)
REQUIRED_FILES = (
    "SKILL.md",
    "agents/openai.yaml",
    "scripts/config.json",
    "scripts/generate_image.py",
)
PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class ValidationError(RuntimeError):
    """A concise validation failure."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate the nebula-image-skills packages.")
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Run local Mock requests through all three provider protocols",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable validation results",
    )
    return parser.parse_args()


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        raise ValidationError(f"Cannot read {path}") from error


def read_json(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(read_text(path))
    except json.JSONDecodeError as error:
        raise ValidationError(f"Invalid JSON: {path}: {error.msg}") from error
    if not isinstance(value, dict):
        raise ValidationError(f"JSON root must be an object: {path}")
    return value


def frontmatter(text: str, path: Path) -> Dict[str, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValidationError(f"Missing YAML frontmatter: {path}")
    try:
        end = lines.index("---", 1)
    except ValueError as error:
        raise ValidationError(f"Unclosed YAML frontmatter: {path}") from error
    values: Dict[str, str] = {}
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            raise ValidationError(f"Invalid frontmatter line in {path}: {line}")
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    for key in ("name", "description"):
        if not values.get(key):
            raise ValidationError(f"Frontmatter needs {key}: {path}")
    return values


def quoted_yaml_value(text: str, key: str, path: Path) -> str:
    match = re.search(rf"^\s+{re.escape(key)}:\s*(['\"])(.*?)\1\s*$", text, re.MULTILINE)
    if not match:
        raise ValidationError(f"Missing quoted {key} in {path}")
    return match.group(2)


def validate_openai_yaml(path: Path, skill_name: str) -> None:
    text = read_text(path)
    if "dependencies:" in text:
        raise ValidationError(f"Skill metadata must remain self-contained: {path}")
    display_name = quoted_yaml_value(text, "display_name", path)
    short_description = quoted_yaml_value(text, "short_description", path)
    default_prompt = quoted_yaml_value(text, "default_prompt", path)
    if not 25 <= len(short_description) <= 64:
        raise ValidationError(f"short_description must be 25-64 characters: {path}")
    if f"${skill_name}" not in default_prompt:
        raise ValidationError(f"default_prompt must invoke ${skill_name}: {path}")
    if not display_name:
        raise ValidationError(f"display_name cannot be empty: {path}")
    if "allow_implicit_invocation: true" not in text:
        raise ValidationError(f"Implicit invocation should remain enabled: {path}")


def validate_config(path: Path, skill_name: str) -> Dict[str, Any]:
    config = read_json(path)
    required = (
        "version",
        "name",
        "label",
        "group",
        "transport",
        "endpoint",
        "model",
        "max_references",
        "default_timeout_seconds",
    )
    missing = [key for key in required if key not in config]
    if missing:
        raise ValidationError(f"Missing config keys {missing}: {path}")
    if config["name"] != skill_name:
        raise ValidationError(f"Config name does not match directory: {path}")
    if not str(config["version"]).startswith("2."):
        raise ValidationError(f"Unexpected config version: {path}")
    endpoint = urlsplit(str(config["endpoint"]))
    if endpoint.scheme not in {"http", "https"} or not endpoint.hostname:
        raise ValidationError(f"Config endpoint must be HTTP(S): {path}")
    if int(config["max_references"]) < 1 or float(config["default_timeout_seconds"]) <= 0:
        raise ValidationError(f"Invalid limits in config: {path}")
    transport = config["transport"]
    if transport == "images":
        for section_name in ("generation", "editing"):
            section = config.get(section_name)
            if not isinstance(section, dict) or not section.get("default_size"):
                raise ValidationError(f"Missing image section {section_name}: {path}")
            if not section.get("qualities"):
                raise ValidationError(f"Missing quality choices in {section_name}: {path}")
        if int(config.get("max_images", 0)) < 1:
            raise ValidationError(f"Invalid max_images: {path}")
    elif transport == "gemini":
        models = config.get("models")
        mappings = config.get("model_resolutions")
        if not isinstance(models, list) or not models or not isinstance(mappings, dict):
            raise ValidationError(f"Gemini model registry is incomplete: {path}")
        if not config.get("resolutions") or not config.get("aspect_ratios"):
            raise ValidationError(f"Gemini resolution/ratio registry is incomplete: {path}")
        for model in models:
            if model not in mappings or not mappings[model]:
                raise ValidationError(f"Missing resolution mapping for {model}: {path}")
    elif transport != "chat":
        raise ValidationError(f"Unsupported transport {transport}: {path}")
    return config


def run_checked(command: Sequence[str], cwd: Path, env: Optional[Dict[str, str]] = None, timeout: float = 20) -> str:
    try:
        completed = subprocess.run(
            list(command),
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValidationError(f"Command failed to start or timed out: {' '.join(command)}") from error
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip().replace("\n", " ")
        raise ValidationError(f"Command failed ({completed.returncode}): {' '.join(command)}: {detail[:300]}")
    return completed.stdout


def validate_skill(root: Path, skill_name: str) -> Dict[str, Any]:
    skill_root = root / "skills" / skill_name
    for relative in REQUIRED_FILES:
        path = skill_root / Path(relative)
        if not path.is_file():
            raise ValidationError(f"Missing required file: {path}")
    skill_text = read_text(skill_root / "SKILL.md")
    metadata = frontmatter(skill_text, skill_root / "SKILL.md")
    if metadata["name"] != skill_name:
        raise ValidationError(f"Skill name does not match directory: {skill_root / 'SKILL.md'}")
    validate_openai_yaml(skill_root / "agents" / "openai.yaml", skill_name)
    config = validate_config(skill_root / "scripts" / "config.json", skill_name)
    script = skill_root / "scripts" / "generate_image.py"
    try:
        compile(read_text(script), str(script), "exec")
    except SyntaxError as error:
        raise ValidationError(f"Python syntax error in {script}: {error}") from error

    env = os.environ.copy()
    env.pop("APINEBULA_API_KEY", None)
    run_checked([sys.executable, str(script), "--help"], root, env=env)
    dry_run_output = run_checked(
        [sys.executable, str(script), "--prompt", "validation prompt", "--dry-run"],
        root,
        env=env,
    )
    try:
        dry_run = json.loads(dry_run_output)
    except json.JSONDecodeError as error:
        raise ValidationError(f"Dry-run did not return JSON: {script}") from error
    if dry_run.get("status") != "dry-run" or dry_run.get("skill") != skill_name:
        raise ValidationError(f"Unexpected dry-run result: {script}")
    return {
        "name": skill_name,
        "transport": config["transport"],
        "model": config["model"],
        "status": "passed",
    }


class SmokeHandler(BaseHTTPRequestHandler):
    """Return protocol-shaped image responses without contacting a provider."""

    server_version = "nebula-image-skills-smoke/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_POST(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        length = int(self.headers.get("content-length", "0"))
        body = self.rfile.read(length)
        received = getattr(self.server, "received", [])
        received.append((self.path, self.headers.get("authorization", ""), body))
        self.server.received = received
        if not self.headers.get("authorization", "").startswith("Bearer "):
            self.send_error(401)
            return
        encoded = base64.b64encode(PNG_BYTES).decode("ascii")
        if self.path.endswith("/v1/images/generations") or self.path.endswith("/v1/images/edits"):
            payload: Dict[str, Any] = {"id": "smoke-images", "data": [{"b64_json": encoded}]}
        elif ":generateContent" in self.path:
            payload = {
                "responseId": "smoke-gemini",
                "candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "image/png", "data": encoded}}]}}],
            }
        elif self.path.endswith("/v1/chat/completions"):
            payload = {
                "id": "smoke-chat",
                "choices": [{"message": {"content": f"data:image/png;base64,{encoded}"}}],
            }
        else:
            self.send_error(404)
            return
        response = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)


def run_smoke(root: Path) -> List[Dict[str, Any]]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), SmokeHandler)
    server.received = []
    import threading

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    results: List[Dict[str, Any]] = []
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        with tempfile.TemporaryDirectory(prefix="nebula-image-skills-smoke-") as temporary:
            output_root = Path(temporary)
            for skill_name in SKILL_NAMES:
                script = root / "skills" / skill_name / "scripts" / "generate_image.py"
                command = [
                    sys.executable,
                    str(script),
                    "--prompt",
                    "smoke test",
                    "--base-url",
                    base_url,
                    "--output",
                    str(output_root / f"{skill_name}.png"),
                ]
                if skill_name == "nebula-image2-1k" or skill_name == "nebula-image2-4k":
                    command += ["--quality", "low"]
                elif skill_name == "nebula-nanobanana":
                    command += ["--resolution", "1K", "--aspect-ratio", "1:1"]
                environment = os.environ.copy()
                environment["APINEBULA_API_KEY"] = "smoke-key"
                completed = subprocess.run(
                    command,
                    cwd=str(root),
                    env=environment,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
                if completed.returncode != 0:
                    detail = (completed.stderr or completed.stdout).strip().replace("\n", " ")
                    raise ValidationError(f"Smoke request failed for {skill_name}: {detail[:300]}")
                image_path = output_root / f"{skill_name}.png"
                metadata_path = output_root / f"{skill_name}.json"
                if not image_path.is_file() or not metadata_path.is_file():
                    raise ValidationError(f"Smoke output missing for {skill_name}")
                metadata_text = metadata_path.read_text(encoding="utf-8")
                if "smoke-key" in metadata_text:
                    raise ValidationError(f"Smoke metadata leaked the test key: {skill_name}")
                metadata = json.loads(metadata_text)
                artifact = metadata["apinebula_skill"]["artifacts"][0]
                if artifact["width"] != 1 or artifact["height"] != 1:
                    raise ValidationError(f"Smoke pixel inspection failed: {skill_name}")
                results.append({"name": skill_name, "status": "passed", "request": "completed"})

            reference = output_root / "reference.png"
            reference.write_bytes(PNG_BYTES)
            edit_script = root / "skills" / "nebula-image2-1k" / "scripts" / "generate_image.py"
            edit_output = output_root / "edit.png"
            environment = os.environ.copy()
            environment["APINEBULA_API_KEY"] = "smoke-key"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(edit_script),
                    "--prompt",
                    "smoke edit",
                    "--reference",
                    str(reference),
                    "--base-url",
                    base_url,
                    "--output",
                    str(edit_output),
                ],
                cwd=str(root),
                env=environment,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if completed.returncode != 0:
                detail = (completed.stderr or completed.stdout).strip().replace("\n", " ")
                raise ValidationError(f"Smoke edit failed: {detail[:300]}")
            if not edit_output.is_file():
                raise ValidationError("Smoke edit did not create an image")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    paths = [item[0] for item in getattr(server, "received", [])]
    required_paths = {
        "/v1/images/generations",
        "/v1/images/edits",
        "/v1/chat/completions",
    }
    if not required_paths.issubset(set(paths)) or not any(":generateContent" in path for path in paths):
        raise ValidationError(f"Smoke server did not receive every protocol: {paths}")
    return results


def main() -> int:
    args = parse_args()
    root = project_root()
    results: List[Dict[str, Any]] = []
    try:
        for skill_name in SKILL_NAMES:
            results.append(validate_skill(root, skill_name))
        if args.smoke:
            results.extend(run_smoke(root))
    except (OSError, ValidationError, ValueError, json.JSONDecodeError) as error:
        if args.json:
            print(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=False))
        else:
            print(f"Error: {error}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({"status": "passed", "results": results}, ensure_ascii=False, indent=2))
    else:
        for result in results:
            print(f"PASS {result['name']} {result.get('transport', result.get('request', ''))}".rstrip())
        print(f"VALIDATED {len(results)} checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
