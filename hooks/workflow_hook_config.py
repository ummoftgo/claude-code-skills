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
# `hooks` 아래에서 인라인 훅으로 보지 않는 유일한 키(Codex 신뢰 상태 저장소).
CODEX_HOOK_STATE_KEY = "state"
# 인라인 훅이 선언되는 루트 키. 비교는 항상 정규화된 키 이름으로 하며, TOML 키는
# 대소문자를 구분하므로 `Hooks`는 다른 키다.
CODEX_HOOK_ROOT_KEY = "hooks"
# TOML 키 하나: bare key, basic string key(`"..."`), literal string key(`'...'`)는
# 모두 동등하다. https://toml.io/en/v1.0.0#keys
# 인용부호를 벗기고 basic string 의 `\uXXXX`/`\UXXXXXXXX`(및 `\\`, `\"`)를 디코딩하는
# 일은 _normalized_toml_key 가 맡는다. literal string 은 이스케이프를 해석하지 않는
# 다는 TOML 규칙 때문에 두 인용부호를 구분해서 처리한다.
CODEX_TOML_KEY = r"""[A-Za-z0-9_-]+|"(?:[^"\\]|\\.)*"|'[^']*'"""
# 루트 키도 quoted 로 쓸 수 있으므로(`"hooks".Event = ...`) 텍스트로 고정하지 않고
# 일반 키로 붙잡아 정규화한 뒤 `hooks` 와 비교한다.
# `[hooks]`, `[hooks.Event]`, `[[hooks.Event]]`, `[[hooks."Event"]]` 및 TOML이 허용하는
# 점 주변 공백(`[[ hooks . Event ]]`) 까지 받는다.
CODEX_HOOK_TABLE = re.compile(
    rf"^\s*\[\[?\s*({CODEX_TOML_KEY})\s*"
    rf"(?:\.\s*({CODEX_TOML_KEY})\s*)?(?:\.|\])"
)
# 점 표기 대입(`hooks.Event = <무엇이든>`, `hooks."Event" = ...`, `"hooks".Event = ...`)과
# 루트 인라인 테이블(`hooks = { ... }`)을 받는다. 점 표기는 array-of-tables와 같은 구조를
# 만들므로 값의 모양을 가리지 않는다. 반면 점 없는 단독 `hooks` 키는 `= {` 인 경우로
# 제한한다. `[features]` 섹션의 기능 플래그 `hooks = true`를 인라인 훅으로 오탐하지 않기
# 위한 보호막이다(`"hooks" = true` 도 같은 이유로 걸러진다).
# 두 갈래 모두 루트 테이블(어떤 `[table]` 헤더보다 앞) 에서만 유효하다. `[other]` 안의
# `hooks.SessionEnd = []` 는 `other.hooks.SessionEnd` 이지 루트 훅 선언이 아니다.
CODEX_HOOK_INLINE_TABLE = re.compile(
    rf"^({CODEX_TOML_KEY})\s*(?:\.\s*({CODEX_TOML_KEY})\s*[.=]|=\s*\{{)"
)
# basic string 안에서 디코딩하는 이스케이프. `\uXXXX`/`\UXXXXXXXX` 는 키 이름에 실제로
# 쓰일 수 있어 해석하고, `\\`/`\"` 는 그 해석이 어긋나지 않도록 함께 처리한다.
# 그 밖의 이스케이프(`\n`, `\t`, `\r`, `\f`, `\b`)는 알려진 한계로 남긴다: 제어문자
# 키까지 다루려면 줄 스캐너에 TOML 문자열 디코더를 통째로 넣어야 한다. 이 한계는 지금의
# 판정을 바꾸지 못한다 — 비교 대상 이름은 소문자 ASCII인 `hooks`/`state` 둘뿐이고, 그
# 문자를 만들어낼 수 있는 이스케이프는 `\u`/`\U` 뿐이기 때문이다.
CODEX_TOML_ESCAPE = re.compile(r"\\(u[0-9A-Fa-f]{4}|U[0-9A-Fa-f]{8}|.)", re.DOTALL)
# 줄 기반 경로가 아직 알아볼 수 있는 유일한 구조 오류(깨진 테이블 헤더)를 판별하는 기준.
CODEX_TOML_TABLE_HEADER = re.compile(
    rf"^\[\[?\s*(?:{CODEX_TOML_KEY})(?:\s*\.\s*(?:{CODEX_TOML_KEY}))*\s*\]\]?$"
)
CODEX_MULTILINE_DELIMITERS = ('"""', "'''")
# _multiline_closing 의 두 실패값. -1 은 "이 줄에서 아직 닫히지 않음"(다음 줄로 이어짐),
# -2 는 "TOML 문법상 존재할 수 없는 따옴표 연속"(=무효한 TOML)이다.
CODEX_MULTILINE_UNCLOSED = -1
CODEX_MULTILINE_INVALID_RUN = -2


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


def _multiline_closing(text: str, delimiter: str, start: int) -> int:
    """Index where the closing `delimiter` of a multi-line string body begins.

    TOML lets one or two quotes sit immediately inside the closing delimiter, so
    a run of adjacent quotes has to be consumed whole before deciding where the
    string ends - only its *last* three are the delimiter. The v1.0.0 grammar
    spells this out as `ml-basic-body = *mlb-content *( mlb-quotes 1*mlb-content )
    [ mlb-quotes ]` with `mlb-quotes = 1*2quotation-mark` (and the identical
    `ml-literal-body` / `mll-quotes = 1*2apostrophe`), which the prose states as
    "You can write a quotation mark, or two adjacent quotation marks, anywhere
    inside a multi-line basic string. They can also be written just inside the
    delimiters" with the example
    `str7 = \"\"\"\"This,\" she said, \"is just a pointless statement.\"\"\"\"`
    (https://toml.io/en/v1.0.0#string). So `\"\"\"a\"\"\"\"` is the string `a\"`
    and `\"\"\"a\"\"\"\"\"` is `a\"\"`; taking the *first* three quotes of the run
    as the delimiter instead would hide the rest of the line inside the string.

    Six or more adjacent quotes cannot appear in a multi-line string body at all:
    the body alternates content with `1*2` quotes, and no content character is
    itself an unescaped quote (`mlb-unescaped`/`mll-char` exclude it), so the
    longest legal run is two content quotes plus the delimiter. That case returns
    CODEX_MULTILINE_INVALID_RUN rather than a position - it is provably invalid
    TOML, which tomllib rejects too, so the fallback reports it instead of
    guessing where such a string would have ended.

    Only a multi-line basic string interprets `\\` escapes - a literal string has
    none - which is why `\"\"\"a\\\"\"\"` is unterminated while `'''a\\'''` is not.
    """
    quote = delimiter[0]
    interprets_escapes = delimiter == '"""'
    position = start
    while position < len(text):
        if interprets_escapes and text[position] == "\\":
            position += 2
            continue
        if text[position] != quote:
            position += 1
            continue
        run_start = position
        while position < len(text) and text[position] == quote:
            position += 1
        run_length = position - run_start
        if run_length > 5:
            return CODEX_MULTILINE_INVALID_RUN
        if run_length >= 3:
            return run_start + run_length - 3
    return -1


def _toml_code_lines_with_state(content: str) -> tuple[list[str], str | None, bool]:
    """Strip comments and multi-line string bodies so hook shapes inside them are ignored.

    The second element is the multi-line delimiter that was still open at end of
    input (None when every one was closed) and the third says an impossible run of
    adjacent quotes was seen; both are structure errors a line scanner can
    recognise on its own. Scanning stops at an impossible run, so the returned
    lines are truncated in that case - the caller must raise rather than read them.
    """
    open_delimiter: str | None = None
    code_lines: list[str] = []
    for raw_line in content.splitlines():
        kept: list[str] = []
        position = 0

        if open_delimiter is not None:
            closing = _multiline_closing(raw_line, open_delimiter, 0)
            if closing == CODEX_MULTILINE_INVALID_RUN:
                return code_lines, None, True
            if closing < 0:
                code_lines.append("")
                continue
            position = closing + 3
            open_delimiter = None

        in_single_quote = False
        in_double_quote = False
        escaped = False
        while position < len(raw_line):
            character = raw_line[position]

            if in_double_quote:
                kept.append(character)
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == '"':
                    in_double_quote = False
                position += 1
                continue
            if in_single_quote:
                kept.append(character)
                if character == "'":
                    in_single_quote = False
                position += 1
                continue

            candidate = raw_line[position : position + 3]
            if candidate in CODEX_MULTILINE_DELIMITERS:
                closing = _multiline_closing(raw_line, candidate, position + 3)
                if closing == CODEX_MULTILINE_INVALID_RUN:
                    return code_lines, None, True
                if closing < 0:
                    open_delimiter = candidate
                    break
                position = closing + 3
                continue
            if character == "#":
                break
            if character == '"':
                in_double_quote = True
            elif character == "'":
                in_single_quote = True
            kept.append(character)
            position += 1
        code_lines.append("".join(kept))
    return code_lines, open_delimiter, False


def _toml_code_lines(content: str) -> list[str]:
    return _toml_code_lines_with_state(content)[0]


def _decoded_toml_escapes(text: str) -> str:
    """Decode the basic-string escapes a TOML key can realistically carry.

    Only `\\uXXXX` / `\\UXXXXXXXX` (plus `\\\\` and `\\"`, so that a literal
    backslash is never mistaken for the start of one) are decoded; see
    CODEX_TOML_ESCAPE for the escapes deliberately left alone.
    """

    def replace(match: re.Match[str]) -> str:
        token = match.group(1)
        marker = token[0]
        # A one-character token is the catch-all branch: `\uZZZZ` and `\u007`
        # are not escapes TOML accepts, so `u` arrives here without its digits.
        if len(token) > 1 and marker in "uU":
            code_point = int(token[1:], 16)
            if code_point > 0x10FFFF or 0xD800 <= code_point <= 0xDFFF:
                # Not a Unicode scalar value: invalid TOML, so leave it as
                # written rather than inventing a key the parser would reject.
                return match.group(0)
            return chr(code_point)
        if marker in '\\"':
            return marker
        return match.group(0)

    return CODEX_TOML_ESCAPE.sub(replace, text)


def _normalized_toml_key(raw_key: str | None) -> str | None:
    """Turn a captured TOML key into the key name TOML itself would produce.

    `hooks."state"`, `hooks.'state'` and `hooks."\\u0073tate"` all name
    `hooks.state`, while `hooks.'\\u0073tate'` does not: a literal string never
    interprets escapes (https://toml.io/en/v1.0.0#keys).
    """
    if raw_key is None:
        return None
    if len(raw_key) >= 2 and raw_key[0] == raw_key[-1]:
        if raw_key[0] == '"':
            return _decoded_toml_escapes(raw_key[1:-1])
        if raw_key[0] == "'":
            return raw_key[1:-1]
    return raw_key


def _toml_bracket_delta(code_line: str) -> int:
    """Net `[`/`{` nesting a comment-free line opens, ignoring single-line strings."""
    delta = 0
    in_single_quote = False
    in_double_quote = False
    escaped = False
    for character in code_line:
        if in_double_quote:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_double_quote = False
            continue
        if in_single_quote:
            if character == "'":
                in_single_quote = False
            continue
        if character == '"':
            in_double_quote = True
        elif character == "'":
            in_single_quote = True
        elif character in "[{":
            delta += 1
        elif character in "]}":
            delta -= 1
    return delta


def _fallback_toml_structure_error(
    code_lines: list[str],
    open_delimiter: str | None,
    invalid_quote_run: bool,
) -> str | None:
    """Report the TOML structure errors a line scanner can still recognise.

    This is not TOML validation and the two paths do not share an error
    contract. The structural (tomllib) path parses the file, so every invalid
    config becomes a ConfigError that install.sh turns into exit code 2. The
    fallback parses nothing: it only reports damage a scanner can prove without
    reading values - an unterminated multi-line string, an impossible run of
    adjacent quotes, a line that starts a table header but is not one, and
    brackets that never close. Everything else invalid (a bad literal like
    `hooks.X = tru`, duplicate keys, `x = 01`) is indistinguishable from valid
    input here, so the fallback answers a bool where the structural path errors:
    the same file exits 2 on 3.11+ and 0 or 1 on 3.10. Full parity is not
    reachable without a TOML parser for 3.10, so the gap is pinned case by case
    as `invalidToml.missedByLineBased` in
    tests/fixtures/codex_inline_hooks.json rather than claimed closed.
    """
    if invalid_quote_run:
        # Six or more adjacent quotes cannot occur inside a multi-line string
        # body (see _multiline_closing), so this is provably not valid TOML.
        return "impossible run of adjacent quotes in a multi-line string"
    if open_delimiter is not None:
        return f"unterminated multi-line string ({open_delimiter})"

    depth = 0
    for code_line in code_lines:
        line = code_line.strip()
        # Only a line at nesting depth 0 can be a table header; inside an
        # unclosed array a `[...]` line is an element, not a header.
        if depth == 0 and line.startswith("[") and not CODEX_TOML_TABLE_HEADER.match(line):
            return f"malformed table header: {line}"
        depth = max(0, depth + _toml_bracket_delta(code_line))
    if depth > 0:
        return "unterminated array or inline table"
    return None


def _fallback_has_inline_hooks(config_path: Path) -> bool:
    try:
        content = config_path.read_text(encoding="utf-8")
    except OSError as error:
        raise ConfigError(f"cannot inspect {config_path}: {error}") from error

    code_lines, open_delimiter, invalid_quote_run = _toml_code_lines_with_state(content)
    # Check for recognisable damage before answering. This is not the structural
    # path's "reject every invalid config" contract (see
    # _fallback_toml_structure_error), only the part of it a scanner can prove:
    # a broken config must never be reported as "no inline hooks" just because a
    # hook shaped line happened to appear before the damage.
    structure_error = _fallback_toml_structure_error(
        code_lines, open_delimiter, invalid_quote_run
    )
    if structure_error is not None:
        raise ConfigError(f"cannot read valid TOML from {config_path}: {structure_error}")

    # A dotted key only reaches the root `hooks` table while no `[table]` header
    # has been seen yet: inside `[other]`, `hooks.SessionEnd = []` declares
    # `other.hooks.SessionEnd`. Table headers themselves are absolute, so only
    # the assignment branch needs the context. `[hooks]`/`[hooks.Event]` already
    # answer true on the header line, and inside `[hooks.state]` a dotted key
    # lands under the exempt trust store, so root-only is the whole rule.
    at_root_table = True
    depth = 0
    for code_line in code_lines:
        line = code_line.strip()
        # The depth test gates every branch, not just the header one: only a line
        # at nesting depth 0 can declare anything. Inside an unclosed array a
        # `[...]` line is an element, so `values = [\n  ["hooks"]\n]` must not be
        # read as a `[hooks]` table header (the same rule
        # _fallback_toml_structure_error applies, and applying the table regex
        # before this test over-detected exactly that shape).
        if line and depth == 0:
            match = CODEX_HOOK_TABLE.match(line)
            if (
                match
                and _normalized_toml_key(match.group(1)) == CODEX_HOOK_ROOT_KEY
                and _normalized_toml_key(match.group(2)) != CODEX_HOOK_STATE_KEY
            ):
                return True
            if CODEX_TOML_TABLE_HEADER.match(line):
                at_root_table = False
            elif at_root_table:
                match = CODEX_HOOK_INLINE_TABLE.match(line)
                if (
                    match
                    and _normalized_toml_key(match.group(1)) == CODEX_HOOK_ROOT_KEY
                    and _normalized_toml_key(match.group(2)) != CODEX_HOOK_STATE_KEY
                ):
                    return True
        depth = max(0, depth + _toml_bracket_delta(code_line))
    return False


def has_inline_hooks(config_path: Path) -> bool:
    """True when config.toml declares anything under `hooks` other than `hooks.state`."""
    if not config_path.exists():
        return False
    if tomllib is None:
        return _fallback_has_inline_hooks(config_path)

    try:
        with config_path.open("rb") as file:
            data = tomllib.load(file)
    except OSError as error:
        raise ConfigError(f"cannot inspect {config_path}: {error}") from error
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"cannot read valid TOML from {config_path}: {error}") from error

    hooks = data.get(CODEX_HOOK_ROOT_KEY)
    if hooks is None:
        return False
    if not isinstance(hooks, dict):
        return True
    return any(key != CODEX_HOOK_STATE_KEY for key in hooks)


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
