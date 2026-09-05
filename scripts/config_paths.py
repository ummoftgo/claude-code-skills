"""Reject unsupported global config roots before managed files can change."""

import argparse
import os
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", choices=("global", "project"), required=True)
    parser.add_argument("--clients", nargs="+", choices=("claude", "codex"), required=True)
    args = parser.parse_args()
    if args.scope == "project":
        return 0

    variables = {"claude": ("CLAUDE_CONFIG_DIR", ".claude"), "codex": ("CODEX_HOME", ".codex")}
    for client in args.clients:
        variable, directory = variables[client]
        configured = os.environ.get(variable)
        default = os.path.join(os.environ["HOME"], directory)
        if configured and os.path.realpath(configured) != os.path.realpath(default):
            print(
                f"Unsupported global configuration: {variable} differs from {default}. "
                "No managed files were changed. Use project scope or manage components "
                "in the custom configuration directory manually.",
                file=sys.stderr,
            )
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
