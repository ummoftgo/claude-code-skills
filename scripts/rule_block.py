#!/usr/bin/env python3
"""Install/remove an owned Codex rule block without rewriting surrounding bytes."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import sys
import tempfile

import manifest


def write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as file:
            file.write(content)
        if path.exists():
            os.chmod(temporary, path.stat().st_mode)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def update(args: argparse.Namespace) -> None:
    target = args.target
    if target.is_symlink() or (target.exists() and not target.is_file()):
        print(f"[WARN] rule 대상을 보존합니다 (일반 파일 아님): {target}")
        return
    original = target.read_bytes() if target.exists() else b""
    data = manifest._load(args.manifest)
    entry = next((item for item in data["entries"] if item["target"] == str(target)), None)
    start = f"<!-- claude-code-skills:{args.name} -->".encode()
    end = f"<!-- /claude-code-skills:{args.name} -->".encode()
    block = re.search(rb"(?m)^" + re.escape(start) + rb"\r?\n(?P<content>[\s\S]*?)^"
                      + re.escape(end) + rb"(?:\r?\n|$)", original)
    has_markers = start in original or end in original
    if has_markers or entry is not None:
        if (block is None or original.count(start) != 1 or original.count(end) != 1
                or entry is None or entry.get("kind") != "rule"
                or hashlib.sha256(block["content"]).hexdigest() != entry.get("hash")):
            print(f"[WARN] 수정되었거나 소유권을 확인할 수 없는 rule 블록을 보존합니다: {target}")
            return
    elif args.action == "remove":
        return

    separator = entry.get("blockSeparator", "").encode("ascii") if entry else b""
    if args.action == "remove":
        left = block.start()
        if separator and original[:left].endswith(separator):
            left -= len(separator)
        updated = original[:left] + original[block.end():]
    else:
        content = args.source.read_bytes()
        if not content.endswith(b"\n"):
            content += b"\n"
        if block:
            updated = original[:block.start("content")] + content + original[block.end("content"):]
        else:
            newline = b"\r\n" if b"\r\n" in original else b"\n"
            if original and not original.endswith((b"\n\n", b"\n\r\n")):
                separator = newline if original.endswith(b"\n") else newline * 2
            updated = original + separator + start + b"\n" + content + end + b"\n"
        new_entry = {
            "platform": "posix", "scope": "global", "client": "codex", "kind": "rule",
            "component": args.name, "target": str(target), "method": "merge",
            "source": str(args.source), "hash": hashlib.sha256(content).hexdigest(),
            "installedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "blockSeparator": separator.decode("ascii"),
        }

    existed = target.exists()
    manifest_before = args.manifest.read_bytes() if args.manifest.exists() else None
    try:
        write_bytes(target, updated)
        if args.action == "remove":
            manifest.prune(args.manifest, str(target))
        else:
            data["entries"] = [item for item in data["entries"] if item["target"] != str(target)]
            data["entries"].append(new_entry)
            manifest._write(args.manifest, data)
    except OSError:
        if existed:
            write_bytes(target, original)
        else:
            target.unlink(missing_ok=True)
        if manifest_before is not None:
            write_bytes(args.manifest, manifest_before)
        else:
            args.manifest.unlink(missing_ok=True)
        raise
    print(f"[OK] rule {args.action}: {target}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("install", "remove"))
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--source", type=Path)
    args = parser.parse_args()
    if args.action == "install" and args.source is None:
        parser.error("install requires --source")
    try:
        update(args)
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
