#!/usr/bin/env python3
"""Read and atomically update claude-code-skills manifest v2."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


VERSION = 2


def _empty() -> dict[str, Any]:
    return {"version": VERSION, "entries": []}


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _empty()
    with path.open(encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict) or data.get("version") != VERSION:
        raise ValueError(f"unsupported manifest: {path}")
    entries = data.get("entries")
    if not isinstance(entries, list):
        raise ValueError(f"manifest entries must be an array: {path}")
    return data


def _write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as file:
            json.dump(data, file, indent=2, ensure_ascii=False)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, path)
    finally:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass


def _legacy_type(value: str) -> tuple[str, str]:
    if "-" not in value:
        return "unknown", value
    client, kind = value.split("-", 1)
    if kind not in {"skill", "agent", "hook"}:
        kind = "unknown"
    return client, kind


def _legacy_component(kind: str, target: str) -> str:
    name = Path(target).name
    if kind == "agent":
        return Path(name).stem
    if kind == "hook":
        return "workflow-reminder"
    return name


def import_v1(manifest: Path, legacy: Path, scope: str) -> int:
    data = _load(manifest)
    if not legacy.exists():
        return 0
    existing = {entry.get("target") for entry in data["entries"]}
    for raw_line in legacy.read_text(encoding="utf-8").splitlines():
        if not raw_line or raw_line.startswith("#"):
            continue
        fields = raw_line.split("\t")
        if len(fields) < 6:
            continue
        legacy_type, target, method, source, digest, timestamp = fields[:6]
        if target in existing:
            continue
        client, kind = _legacy_type(legacy_type)
        data["entries"].append(
            {
                "platform": "posix",
                "scope": scope,
                "client": client,
                "kind": kind,
                "component": _legacy_component(kind, target),
                "target": target,
                "method": method,
                "source": source,
                "hash": digest,
                "installedAt": timestamp,
                "importedFrom": "v1",
            }
        )
        existing.add(target)
    if data["entries"]:
        _write(manifest, data)
    return 0


def _scalar(value: str | None) -> Any:
    if value is None:
        return None
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in {"null", "none", "-"}:
        return None
    return value


def record(args: argparse.Namespace) -> int:
    data = _load(args.manifest)
    entry: dict[str, Any] = {
        "platform": args.platform,
        "scope": args.scope,
        "client": args.client,
        "kind": args.kind,
        "component": args.component,
        "target": args.target,
        "method": args.method,
        "source": args.source,
        "hash": args.hash,
        "installedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    if args.config_key or args.config_before is not None or args.config_after is not None:
        entry["configuration"] = {
            "key": args.config_key,
            "before": _scalar(args.config_before),
            "after": _scalar(args.config_after),
        }
    data["entries"] = [item for item in data["entries"] if item.get("target") != args.target]
    data["entries"].append(entry)
    _write(args.manifest, data)
    return 0


def lookup(manifest: Path, target: str) -> int:
    entry = next((item for item in _load(manifest)["entries"] if item.get("target") == target), None)
    if entry is None:
        return 1
    print(json.dumps(entry, ensure_ascii=False))
    return 0


def prune(manifest: Path, target: str) -> int:
    data = _load(manifest)
    data["entries"] = [item for item in data["entries"] if item.get("target") != target]
    if data["entries"]:
        _write(manifest, data)
    else:
        try:
            manifest.unlink()
        except FileNotFoundError:
            pass
        try:
            manifest.parent.rmdir()
        except OSError:
            pass
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="action", required=True)

    record_parser = subparsers.add_parser("record")
    record_parser.add_argument("--manifest", type=Path, required=True)
    for option in ("platform", "scope", "client", "kind", "component", "target", "method", "source", "hash"):
        record_parser.add_argument(f"--{option.replace('_', '-')}", required=True)
    record_parser.add_argument("--config-key")
    record_parser.add_argument("--config-before")
    record_parser.add_argument("--config-after")

    lookup_parser = subparsers.add_parser("lookup")
    lookup_parser.add_argument("--manifest", type=Path, required=True)
    lookup_parser.add_argument("--target", required=True)

    prune_parser = subparsers.add_parser("prune")
    prune_parser.add_argument("--manifest", type=Path, required=True)
    prune_parser.add_argument("--target", required=True)

    import_parser = subparsers.add_parser("import-v1")
    import_parser.add_argument("--manifest", type=Path, required=True)
    import_parser.add_argument("--legacy", type=Path, required=True)
    import_parser.add_argument("--scope", choices=("global", "project"), required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.action == "record":
            return record(args)
        if args.action == "lookup":
            return lookup(args.manifest, args.target)
        if args.action == "prune":
            return prune(args.manifest, args.target)
        return import_v1(args.manifest, args.legacy, args.scope)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(error, file=os.sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
