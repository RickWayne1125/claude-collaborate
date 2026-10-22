#!/usr/bin/env python3
"""Build an offline, reproducible ZIP from an explicit source allowlist."""

from __future__ import annotations

import argparse
import io
import os
from pathlib import Path, PurePosixPath
import stat
import sys
import tempfile
from typing import Union
import zipfile


class ReleaseError(ValueError):
    """The manifest or filesystem is unsuitable for a source release."""


BLOCKED_PARTS = {
    ".git", ".claude", ".codex", ".agents", ".aws", ".ssh", ".config",
    ".cache", "__pycache__", "node_modules", ".venv", "venv", "dist", "build",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".ds_store",
}
BLOCKED_SUFFIXES = {".pyc", ".pyo", ".jsonl", ".log", ".swp", ".swo"}
WINDOWS_RESERVED = {"con", "prn", "aux", "nul"} | {
    prefix + str(number) for prefix in ("com", "lpt") for number in range(1, 10)
}
FIXED_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


def is_link_or_reparse(details: os.stat_result) -> bool:
    """Python 3.9 does not classify every Windows junction as a symlink."""
    return stat.S_ISLNK(details.st_mode) or bool(
        getattr(details, "st_file_attributes", 0) & REPARSE_POINT
    )


def validate_name(value: str) -> str:
    """Accept a portable, relative POSIX file path without hidden traversal."""
    if not value or "\\" in value or ":" in value:
        raise ReleaseError("Manifest paths must be relative POSIX paths: %r" % value)
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ReleaseError("Control characters are not allowed in manifest paths")
    parts = value.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ReleaseError("Empty, absolute, and traversal paths are forbidden: %r" % value)
    for part in parts:
        folded = part.casefold()
        if part.endswith((".", " ")) or folded.split(".")[0] in WINDOWS_RESERVED:
            raise ReleaseError("Nonportable manifest path: %r" % value)
        if folded in BLOCKED_PARTS or folded == ".env" or folded.startswith(".env."):
            raise ReleaseError("Local configuration or cache path is forbidden: %r" % value)
    if PurePosixPath(value).suffix.casefold() in BLOCKED_SUFFIXES:
        raise ReleaseError("Cache or session/log file is forbidden: %r" % value)
    return value


def read_source(root: Path, name: str) -> bytes:
    """Read only regular files, rejecting links at every manifest path component."""
    validate_name(name)
    path = root
    parts = name.split("/")
    try:
        for index, part in enumerate(parts):
            path = path / part
            details = path.lstat()
            if is_link_or_reparse(details):
                raise ReleaseError("Symlinks and Windows reparse points are forbidden in release inputs: %s" % name)
            if index < len(parts) - 1 and not stat.S_ISDIR(details.st_mode):
                raise ReleaseError("Manifest parent is not a directory: %s" % name)
        if not stat.S_ISREG(details.st_mode):
            raise ReleaseError("Manifest entry is not a regular file: %s" % name)
        descriptor = os.open(str(path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened.st_mode) or (
                opened.st_dev, opened.st_ino
            ) != (details.st_dev, details.st_ino):
                raise ReleaseError("Release input changed while opening: %s" % name)
            return stream.read()
    except OSError as error:
        raise ReleaseError("Cannot read release input %s: %s" % (name, error.strerror)) from error


def read_manifest(root: Path, manifest: str) -> list[str]:
    try:
        text = read_source(root, manifest).decode("utf-8")
    except UnicodeDecodeError as error:
        raise ReleaseError("The release manifest must use UTF-8") from error
    names = []
    seen = set()
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line != line.strip():
            raise ReleaseError("Whitespace around manifest entry on line %d" % line_number)
        name = validate_name(line)
        if name.casefold() in seen:
            raise ReleaseError("Duplicate or case-colliding manifest entry: %s" % name)
        seen.add(name.casefold())
        names.append(name)
    if not names:
        raise ReleaseError("The release manifest contains no source files")
    return sorted(names)


def build_release(
    root: Union[str, Path], output: Union[str, Path], manifest: str = "release-files.txt"
) -> list[str]:
    """Validate all sources before replacing output; never discover files recursively."""
    root = Path(root).expanduser().absolute()
    try:
        root_details = root.lstat()
    except OSError as error:
        raise ReleaseError("Cannot inspect source root: %s" % error.strerror) from error
    if is_link_or_reparse(root_details) or not stat.S_ISDIR(root_details.st_mode):
        raise ReleaseError("Source root must be a real directory, not a symlink or Windows reparse point")
    names = read_manifest(root, manifest)
    output = Path(output).expanduser().absolute()
    # The output is user-selected, but must not overwrite an input or follow a link.
    for path in (output, *output.parents):
        try:
            details = path.lstat()
        except FileNotFoundError:
            continue
        if is_link_or_reparse(details):
            raise ReleaseError("Symlinks and Windows reparse points are forbidden in the output path")
    inputs = [root / name for name in names] + [root / manifest]
    if any(output.resolve() == path.resolve() for path in inputs):
        raise ReleaseError("Output must not overwrite a release input")

    buffer = io.BytesIO()
    # ZIP_STORED avoids zlib-version variation between supported Python/OS versions.
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for name in names:
            content = read_source(root, name)
            info = zipfile.ZipInfo(name, FIXED_TIMESTAMP)
            info.create_system = 3
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, content)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix=".release-", dir=str(output.parent), delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(buffer.getvalue())
        os.replace(str(temporary), str(output))
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return names


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1],
                        help="Source checkout (defaults to this script's repository)")
    parser.add_argument("--manifest", default="release-files.txt",
                        help="Relative allowlist path within the source checkout")
    parser.add_argument("--output", type=Path,
                        help="Local ZIP destination (default: <root>/dist/claude-collaborate-source.zip)")
    args = parser.parse_args(argv)
    output = args.output or args.root / "dist" / "claude-collaborate-source.zip"
    try:
        names = build_release(args.root, output, args.manifest)
    except (ReleaseError, OSError) as error:
        print("Release build failed: %s" % error, file=sys.stderr)
        return 1
    print("Built %s (%d explicitly listed source files)" % (output, len(names)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
