#!/usr/bin/env python3
"""Build independently installable ZIP archives for the four Skills."""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
import zipfile
from pathlib import Path, PurePosixPath
from typing import Iterable, List, Optional, Tuple


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
EXCLUDED_PARTS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".tmp", ".log"}


class PackageError(RuntimeError):
    """A packaging error that can be shown without a traceback."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Package the independent jiuge-canva Skills.")
    parser.add_argument(
        "--output",
        help="Output directory for archives (default: <project>/dist/skills)",
    )
    return parser.parse_args()


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def resolve_output(root: Path, value: Optional[str]) -> Path:
    if not value:
        return root / "dist" / "skills"
    path = Path(value).expanduser()
    return path if path.is_absolute() else Path.cwd() / path


def iter_files(skill_root: Path) -> Iterable[Tuple[Path, str]]:
    for path in sorted(skill_root.rglob("*")):
        relative = path.relative_to(skill_root)
        if path.is_symlink():
            raise PackageError(f"Symlinks are not allowed in a Skill: {path}")
        if not path.is_file():
            continue
        if any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        if path.suffix.lower() in EXCLUDED_SUFFIXES or path.name.startswith(".env"):
            continue
        yield path, relative.as_posix()


def validate_source(skill_root: Path) -> List[Tuple[Path, str]]:
    if not skill_root.is_dir():
        raise PackageError(f"Missing Skill directory: {skill_root}")
    for relative in REQUIRED_FILES:
        path = skill_root / Path(relative)
        if not path.is_file():
            raise PackageError(f"Missing required Skill file: {path}")
    files = list(iter_files(skill_root))
    if not files:
        raise PackageError(f"Skill has no packageable files: {skill_root}")
    return files


def archive_path(output_root: Path, skill_name: str) -> Path:
    return output_root / f"{skill_name}.zip"


def write_archive(output_root: Path, skill_name: str, files: List[Tuple[Path, str]]) -> Path:
    destination = archive_path(output_root, skill_name)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    try:
        with zipfile.ZipFile(
            temporary,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
        ) as archive:
            for path, relative in files:
                member = f"{skill_name}/{relative}"
                info = zipfile.ZipInfo(member)
                info.date_time = (2020, 1, 1, 0, 0, 0)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                info.create_system = 3
                archive.writestr(info, path.read_bytes())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def validate_archive(path: Path, skill_name: str) -> None:
    prefix = f"{skill_name}/"
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if not names:
            raise PackageError(f"Archive is empty: {path}")
        for name in names:
            parts = PurePosixPath(name).parts
            if name.startswith("/") or ".." in parts:
                raise PackageError(f"Unsafe archive member: {name}")
            if not name.startswith(prefix):
                raise PackageError(f"Archive member is outside its Skill root: {name}")
        for required in REQUIRED_FILES:
            if f"{prefix}{required}" not in names:
                raise PackageError(f"Archive is missing {required}: {path}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_checksums(output_root: Path, archives: List[Path]) -> Path:
    path = output_root / "SHA256SUMS.txt"
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    content = "".join(f"{sha256(archive)}  {archive.name}\n" for archive in archives)
    try:
        with temporary.open("w", encoding="ascii", newline="") as stream:
            stream.write(content)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def main() -> int:
    args = parse_args()
    root = project_root()
    output_root = resolve_output(root, args.output)
    try:
        output_root.mkdir(parents=True, exist_ok=True)
        archives: List[Path] = []
        for skill_name in SKILL_NAMES:
            source = root / "skills" / skill_name
            files = validate_source(source)
            archive = write_archive(output_root, skill_name, files)
            validate_archive(archive, skill_name)
            archives.append(archive)
            print(f"PACKED {skill_name} {archive.stat().st_size} bytes SHA256 {sha256(archive)}")
        checksums = write_checksums(output_root, archives)
        print(f"WROTE {checksums}")
        return 0
    except (OSError, zipfile.BadZipFile, PackageError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
