#!/usr/bin/env python3
"""Query the cross-platform component catalog for shell installers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("catalog", type=Path)
    parser.add_argument("--kind", choices=("skill", "agent", "hook"), required=True)
    parser.add_argument("--client", choices=("claude", "codex"), required=True)
    parser.add_argument("--platform", choices=("posix", "windows"), required=True)
    parser.add_argument("--field", choices=("name", "source"), default="name")
    parser.add_argument("--name", help="limit the query to one component")
    args = parser.parse_args()

    with args.catalog.open(encoding="utf-8") as file:
        data = json.load(file)
    if data.get("version") != 1 or not isinstance(data.get("components"), list):
        raise ValueError(f"unsupported component catalog: {args.catalog}")
    for component in data["components"]:
        if component.get("kind") != args.kind:
            continue
        if args.name is not None and component.get("name") != args.name:
            continue
        if component.get("support", {}).get(args.client, {}).get(args.platform) is True:
            if args.field == "name":
                print(component["name"])
            else:
                source = component.get("source")
                if isinstance(source, str):
                    print(source)
                elif component["kind"] == "agent":
                    print(source[args.client])
                else:
                    print(source[args.platform])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
