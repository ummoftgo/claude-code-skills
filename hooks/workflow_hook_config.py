#!/usr/bin/env python3
"""Safely manage the workflow reminder entry in Claude Code or Codex JSON."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 fallback
    tomllib = None  # type: ignore[assignment]


EVENT = "UserPromptSubmit"
CODEX_HOOK_EVENTS = {
    "SessionStart",
    "SubagentStart",
    "PreToolUse",
    "PermissionRequest",
    "PostToolUse",
    "PostToolUseFailure",
    "Notification",
    "SubagentStop",
    "Stop",
    "UserPromptSubmit",
    "PreCompact",
    "PostCompact",
}
CODEX_HOOK_TABLE = re.compile(
    r"^\s*\[\[?\s*hooks(?:\.([A-Za-z][A-Za-z0-9]*))?(?:\.|\s*\])"
)


class ConfigError(ValueError):
    """Raised when an existing hook configuration cannot be safely updated."""


class OutsideRootError(ConfigError):
    """Raised when a settings path resolves outside the authorized root."""


def managed_command(hook_path: Path) -> str:
    return f"python3 {shlex.quote(str(hook_path))}"


def _resolved_path(
    path: Path,
    *,
    allowed_root: Path | None = None,
    allow_outside_root: bool = False,
    label: str = "path",
) -> Path:
    try:
        resolved_path = path.resolve(strict=path.is_symlink())
    except (OSError, RuntimeError) as error:
        raise ConfigError(
            f"{label} symlink does not resolve safely: {path}: {error}"
        ) from error

    if allowed_root is None or allow_outside_root:
        return resolved_path

    try:
        resolved_root = allowed_root.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise ConfigError(
            f"allowed root does not resolve safely: {allowed_root}: {error}"
        ) from error

    if resolved_path != resolved_root and resolved_root not in resolved_path.parents:
        raise OutsideRootError(
            f"{label} target is outside the allowed install root: "
            f"{path} -> {resolved_path} (allowed root: {resolved_root})"
        )
    return resolved_path


def _resolved_settings_path(
    settings_path: Path,
    *,
    allowed_root: Path | None = None,
    allow_outside_root: bool = False,
) -> Path:
    return _resolved_path(
        settings_path,
        allowed_root=allowed_root,
        allow_outside_root=allow_outside_root,
        label="settings",
    )


def validate_scope(
    path: Path,
    *,
    allowed_root: Path | None = None,
    allow_outside_root: bool = False,
) -> None:
    _resolved_path(
        path,
        allowed_root=allowed_root,
        allow_outside_root=allow_outside_root,
    )


def _load_resolved(settings_path: Path, read_path: Path) -> dict[str, Any]:
    if not read_path.exists():
        return {}

    try:
        with read_path.open(encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        raise ConfigError(f"cannot read valid JSON from {settings_path}: {error}") from error

    if not isinstance(data, dict):
        raise ConfigError(f"top-level JSON value must be an object: {settings_path}")
    return data


def _entries(data: dict[str, Any], *, create: bool) -> tuple[dict[str, Any] | None, list[Any]]:
    hooks = data.get("hooks")
    if hooks is None:
        if not create:
            return None, []
        hooks = {}
        data["hooks"] = hooks
    if not isinstance(hooks, dict):
        raise ConfigError("the hooks value must be an object")

    entries = hooks.get(EVENT)
    if entries is None:
        if not create:
            return hooks, []
        entries = []
        hooks[EVENT] = entries
    if not isinstance(entries, list):
        raise ConfigError(f"hooks.{EVENT} must be an array")
    return hooks, entries


def _is_managed_hook(hook: Any, command: str) -> bool:
    return isinstance(hook, dict) and hook.get("command") == command


def _without_managed(entries: list[Any], command: str) -> tuple[list[Any], bool]:
    cleaned: list[Any] = []
    changed = False
    for entry in entries:
        nested = entry.get("hooks") if isinstance(entry, dict) else None
        if not isinstance(nested, list):
            cleaned.append(entry)
            continue

        kept = [hook for hook in nested if not _is_managed_hook(hook, command)]
        removed_managed = len(kept) != len(nested)
        if removed_managed:
            changed = True
        if not removed_managed:
            cleaned.append(entry)
        elif kept:
            updated = dict(entry)
            updated["hooks"] = kept
            cleaned.append(updated)
    return cleaned, changed


def _atomic_write_text_resolved(
    display_path: Path,
    write_path: Path,
    content: str,
) -> None:
    write_path.parent.mkdir(parents=True, exist_ok=True)
    mode = 0o600
    if write_path.exists():
        try:
            mode = stat.S_IMODE(write_path.stat().st_mode)
        except OSError as error:
            raise ConfigError(f"cannot inspect {display_path}: {error}") from error

    descriptor = -1
    temporary_path: Path | None = None
    try:
        descriptor, raw_path = tempfile.mkstemp(
            prefix=f".{write_path.name}.",
            dir=write_path.parent,
        )
        temporary_path = Path(raw_path)
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            descriptor = -1
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, write_path)
        temporary_path = None
    except OSError as error:
        raise ConfigError(f"cannot atomically update {display_path}: {error}") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass


def _atomic_write_resolved(
    settings_path: Path,
    write_path: Path,
    data: dict[str, Any],
) -> None:
    content = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    _atomic_write_text_resolved(settings_path, write_path, content)


def validate_config(
    settings_path: Path,
    *,
    allowed_root: Path | None = None,
    allow_outside_root: bool = False,
) -> None:
    resolved_path = _resolved_settings_path(
        settings_path,
        allowed_root=allowed_root,
        allow_outside_root=allow_outside_root,
    )
    data = _load_resolved(settings_path, resolved_path)
    _entries(data, create=False)


def has_inline_hooks(config_path: Path) -> bool:
    if not config_path.exists():
        return False
    try:
        with config_path.open(encoding="utf-8") as file:
            for line in file:
                match = CODEX_HOOK_TABLE.match(line)
                if match and (
                    match.group(1) is None or match.group(1) in CODEX_HOOK_EVENTS
                ):
                    return True
    except OSError as error:
        raise ConfigError(f"cannot inspect {config_path}: {error}") from error
    return False


def _fallback_hook_feature_setting(config_path: Path) -> tuple[bool | None, str | None]:
    current_section = ""
    assignments: dict[str, bool] = {}
    section = re.compile(r"^\[\s*([^]]+)\s*\]$")
    assignment = re.compile(
        r"^(?:(features)\.)?(hooks|codex_hooks)\s*=\s*(true|false)\s*$",
        re.IGNORECASE,
    )
    try:
        with config_path.open(encoding="utf-8") as file:
            for raw_line in file:
                line = raw_line.split("#", 1)[0].strip()
                if not line:
                    continue
                table = section.match(line)
                if table:
                    current_section = table.group(1).strip()
                    continue
                value = assignment.match(line)
                if not value:
                    continue
                dotted_section = value.group(1)
                key = value.group(2).lower()
                enabled = value.group(3).lower() == "true"
                if current_section == "features" and dotted_section is None:
                    assignments[key] = enabled
                elif current_section == "" and dotted_section == "features":
                    assignments[key] = enabled
    except OSError as error:
        raise ConfigError(f"cannot inspect {config_path}: {error}") from error
    if "hooks" in assignments:
        return assignments["hooks"], "[features] hooks"
    if "codex_hooks" in assignments:
        return assignments["codex_hooks"], "[features] codex_hooks"
    return None, None


def _fallback_disabled_hook_reason(config_path: Path) -> str | None:
    enabled, setting = _fallback_hook_feature_setting(config_path)
    if enabled is False:
        return f"{setting} = false"
    return None


def _hook_feature_setting(config_path: Path) -> tuple[bool | None, str | None]:
    if not config_path.exists():
        return None, None
    if tomllib is None:
        return _fallback_hook_feature_setting(config_path)
    try:
        with config_path.open("rb") as file:
            data = tomllib.load(file)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ConfigError(f"cannot read valid TOML from {config_path}: {error}") from error

    features = data.get("features")
    if not isinstance(features, dict):
        return None, None
    if "hooks" in features and isinstance(features["hooks"], bool):
        return features["hooks"], "[features] hooks"
    if isinstance(features.get("codex_hooks"), bool):
        return features["codex_hooks"], "[features] codex_hooks"
    return None, None


def disabled_hook_reason(
    config_path: Path,
    *,
    base_config_path: Path | None = None,
) -> str | None:
    enabled, setting = _hook_feature_setting(config_path)
    inherited = False
    if enabled is None and base_config_path is not None:
        enabled, setting = _hook_feature_setting(base_config_path)
        inherited = enabled is not None

    if enabled is False:
        suffix = " (inherited from user config)" if inherited else ""
        return f"{setting} = false{suffix}"
    return None


def _enabled_hooks_toml(content: str, config_path: Path) -> str:
    if tomllib is not None:
        try:
            parsed = tomllib.loads(content) if content else {}
        except tomllib.TOMLDecodeError as error:
            raise ConfigError(f"cannot read valid TOML from {config_path}: {error}") from error
    else:
        parsed = {}

    lines = content.splitlines(keepends=True)
    section = ""
    features_header: int | None = None
    canonical: list[tuple[int, re.Match[str], bool]] = []
    deprecated: list[tuple[int, re.Match[str], bool]] = []
    table = re.compile(r"^\s*\[\s*([^]]+)\s*\]\s*(?:#.*)?(?:\r?\n)?$")
    assignment = re.compile(
        r"^(\s*)(?:(features)\.)?(hooks|codex_hooks)(\s*=\s*)"
        r"(true|false)(\s*(?:#.*)?)(\r?\n)?$",
        re.IGNORECASE,
    )

    for index, line in enumerate(lines):
        header = table.match(line)
        if header:
            section = header.group(1).strip()
            if section == "features":
                features_header = index
            continue
        match = assignment.match(line)
        if not match:
            continue
        dotted = match.group(2) is not None
        if not ((section == "features" and not dotted) or (section == "" and dotted)):
            continue
        item = (index, match, section == "")
        if match.group(3).lower() == "hooks":
            canonical.append(item)
        else:
            deprecated.append(item)

    selected = canonical[0] if canonical else (deprecated[0] if deprecated else None)
    if selected is not None:
        index, match, dotted = selected
        if match.group(5).lower() == "true" and canonical:
            return content
        key = "features.hooks" if dotted else "hooks"
        newline = match.group(7) or ""
        lines[index] = (
            f"{match.group(1)}{key}{match.group(4)}true{match.group(6)}{newline}"
        )
        updated = "".join(lines)
    elif features_header is not None:
        newline = "\r\n" if "\r\n" in content else "\n"
        if not lines[features_header].endswith(("\n", "\r")):
            lines[features_header] += newline
        lines.insert(features_header + 1, f"hooks = true{newline}")
        updated = "".join(lines)
    else:
        if isinstance(parsed.get("features"), dict):
            raise ConfigError(
                f"cannot safely add hooks to inline features table: {config_path}"
            )
        newline = "\r\n" if "\r\n" in content else "\n"
        separator = "" if not content or content.endswith(("\n", "\r")) else newline
        updated = f"{content}{separator}[features]{newline}hooks = true{newline}"

    if tomllib is not None:
        try:
            tomllib.loads(updated)
        except tomllib.TOMLDecodeError as error:
            raise ConfigError(
                f"refusing to write invalid TOML to {config_path}: {error}"
            ) from error
    return updated


def enable_hooks(
    config_path: Path,
    *,
    allowed_root: Path | None = None,
    allow_outside_root: bool = False,
) -> None:
    if tomllib is None:
        raise ConfigError(
            "Python 3.11 or newer is required to safely update Codex config.toml"
        )
    resolved_path = _resolved_path(
        config_path,
        allowed_root=allowed_root,
        allow_outside_root=allow_outside_root,
        label="config",
    )
    try:
        content = (
            resolved_path.read_text(encoding="utf-8") if resolved_path.exists() else ""
        )
    except OSError as error:
        raise ConfigError(f"cannot inspect {config_path}: {error}") from error

    updated = _enabled_hooks_toml(content, config_path)
    if updated != content:
        _atomic_write_text_resolved(config_path, resolved_path, updated)


def has_disabled_hooks(config_path: Path) -> bool:
    return disabled_hook_reason(config_path) is not None


def is_configured(
    settings_path: Path,
    hook_path: Path,
    *,
    allowed_root: Path | None = None,
    allow_outside_root: bool = False,
) -> bool:
    resolved_path = _resolved_settings_path(
        settings_path,
        allowed_root=allowed_root,
        allow_outside_root=allow_outside_root,
    )
    data = _load_resolved(settings_path, resolved_path)
    _, entries = _entries(data, create=False)
    command = managed_command(hook_path)
    return any(
        _is_managed_hook(hook, command)
        for entry in entries
        for hook in (
            entry.get("hooks", [])
            if isinstance(entry, dict) and isinstance(entry.get("hooks"), list)
            else []
        )
    )


def install_hook(
    settings_path: Path,
    hook_path: Path,
    *,
    allowed_root: Path | None = None,
    allow_outside_root: bool = False,
) -> None:
    resolved_path = _resolved_settings_path(
        settings_path,
        allowed_root=allowed_root,
        allow_outside_root=allow_outside_root,
    )
    data = _load_resolved(settings_path, resolved_path)
    hooks, entries = _entries(data, create=True)
    assert hooks is not None

    command = managed_command(hook_path)
    cleaned, _ = _without_managed(entries, command)
    new_entry: dict[str, Any] = {
        "hooks": [
            {
                "type": "command",
                "command": command,
                "timeout": 5,
            }
        ]
    }
    cleaned.append(new_entry)
    hooks[EVENT] = cleaned
    _atomic_write_resolved(settings_path, resolved_path, data)


def remove_hook(
    settings_path: Path,
    hook_path: Path,
    *,
    allowed_root: Path | None = None,
    allow_outside_root: bool = False,
) -> bool:
    if not settings_path.exists() and not settings_path.is_symlink():
        return False

    resolved_path = _resolved_settings_path(
        settings_path,
        allowed_root=allowed_root,
        allow_outside_root=allow_outside_root,
    )
    data = _load_resolved(settings_path, resolved_path)
    hooks, entries = _entries(data, create=False)
    if hooks is None:
        return False

    cleaned, changed = _without_managed(entries, managed_command(hook_path))
    if not changed:
        return False

    if cleaned:
        hooks[EVENT] = cleaned
    else:
        hooks.pop(EVENT, None)
    if not hooks:
        data.pop("hooks", None)
    _atomic_write_resolved(settings_path, resolved_path, data)
    return True


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action",
        choices=(
            "validate",
            "scope-status",
            "inline-status",
            "disabled-status",
            "enable-hooks",
            "status",
            "install",
            "remove",
        ),
    )
    parser.add_argument("settings", type=Path)
    parser.add_argument("hook_path", type=Path, nargs="?")
    parser.add_argument("--allowed-root", type=Path)
    parser.add_argument("--allow-outside-root", action="store_true")
    parser.add_argument("--base-config", type=Path)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        if args.action == "validate":
            validate_config(
                args.settings,
                allowed_root=args.allowed_root,
                allow_outside_root=args.allow_outside_root,
            )
            return 0
        if args.action == "scope-status":
            validate_scope(
                args.settings,
                allowed_root=args.allowed_root,
                allow_outside_root=args.allow_outside_root,
            )
            return 0
        if args.action == "inline-status":
            return 0 if has_inline_hooks(args.settings) else 1
        if args.action == "disabled-status":
            reason = disabled_hook_reason(
                args.settings,
                base_config_path=args.base_config,
            )
            if reason is None:
                return 1
            print(reason)
            return 0
        if args.action == "enable-hooks":
            enable_hooks(
                args.settings,
                allowed_root=args.allowed_root,
                allow_outside_root=args.allow_outside_root,
            )
            return 0
        if args.hook_path is None:
            raise ConfigError(f"{args.action} requires hook_path")
        if args.action == "status":
            return 0 if is_configured(
                args.settings,
                args.hook_path,
                allowed_root=args.allowed_root,
                allow_outside_root=args.allow_outside_root,
            ) else 1
        if args.action == "install":
            install_hook(
                args.settings,
                args.hook_path,
                allowed_root=args.allowed_root,
                allow_outside_root=args.allow_outside_root,
            )
            return 0
        remove_hook(
            args.settings,
            args.hook_path,
            allowed_root=args.allowed_root,
            allow_outside_root=args.allow_outside_root,
        )
        return 0
    except OutsideRootError as error:
        print(error, file=sys.stderr)
        return 3
    except ConfigError as error:
        print(error, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
