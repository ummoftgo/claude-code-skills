#!/usr/bin/env python3
"""Inject a planning reminder for Claude Code and Codex implementation prompts."""

from __future__ import annotations

import json
import re
import sys


ACTION = re.compile(
    r"구현|개발|만들|작성|추가|생성|구축|도입|"
    r"\b(?:implement|build|create|develop|add|scaffold|introduce|set\s*up)\b|"
    r"\bwrite\b.{0,30}\bcode\b",
    re.IGNORECASE | re.DOTALL,
)

SUBSTANTIAL = re.compile(
    r"새(?:로운)?\s*.{0,30}(?:프로젝트|기능|서비스|앱|애플리케이션|api|페이지|컴포넌트|모듈)|"
    r"(?:프로젝트|서비스|앱|애플리케이션).{0,20}(?:새로|처음부터).{0,20}(?:구현|개발|만들|작성|생성|구축)|"
    r"(?:프로젝트|기능|서비스|api|페이지|컴포넌트|모듈).{0,30}(?:구현|개발|만들|추가|생성|구축)|"
    r"(?:TDD|테스트\s*우선).{0,30}프로젝트.{0,50}(?:기능|코드).{0,30}(?:구현|개발|작성|추가|생성)|"
    r"(?:여러|다수|복수|동시에|병렬|나눠서|각각|독립적인?).{0,50}(?:구현|개발|작성|작업|기능|페이지|컴포넌트)|"
    r"\bnew\s+(?:project|feature|service|app|application|api|page|component|module)\b|"
    r"\b(?:from\s+scratch|multiple|in\s+parallel)\b|"
    r"\b(?:implement|build|create|add)\b.{0,40}\b(?:feature|auth|authentication|api|page|component|module|service|project)\b|"
    r"(?:backend|back-end).{0,50}(?:frontend|front-end)|(?:frontend|front-end).{0,50}(?:backend|back-end)",
    re.IGNORECASE | re.DOTALL,
)

SMALL_EDIT = re.compile(
    r"(?:작은|간단한?|사소한?|한\s*줄|한\s*글자|오타|문구만|색상만)|"
    r"\b(?:tiny|small|trivial|one[- ]line|typo|copy[- ]only)\b",
    re.IGNORECASE,
)

READ_ONLY = re.compile(
    r"(?:설명|검토|리뷰|분석|조사|검색|찾아|요약|번역|상태)|"
    r"\b(?:explain|review|audit|analy[sz]e|inspect|research|search|summari[sz]e|translate|status)\b",
    re.IGNORECASE,
)

EXPLICIT_MUTATION = re.compile(
    r"(?:구현|개발|추가|생성|구축|도입|수정)(?:해|해줘|해주세요|하자|해라)|"
    r"코드.{0,20}작성(?:해|해줘|해주세요|하자|해라)|"
    r"만들(?:어|어줘|어주세요)|고쳐(?:줘|주세요)?|"
    r"(?:^|[,.!?;:]\s*|\b(?:please|and|then|also|now)\s+|"
    r"\b(?:can|could|would|will)\s+you\s+|"
    r"\b(?:need|want)\s+(?:you\s+)?to\s+)"
    r"(?:implement|build|create|develop|add|scaffold|introduce|fix|change|update)\b",
    re.IGNORECASE,
)

REMINDER = (
    "This appears to be substantial implementation work. Invoke the plan-and-build "
    "skill before editing implementation code. Inspect the repository first, write one "
    "lightweight specification and plan, get design approval when architecture or contracts "
    "materially change, decide whether TDD applies, and split only truly independent work "
    "with stable contracts. Get explicit user approval before dispatching parallel workers. "
    "If inspection proves the change is small and localized, exit the workflow and proceed "
    "directly."
)


def should_remind(prompt: str) -> bool:
    text = " ".join(prompt.split())
    if not text or not ACTION.search(text):
        return False

    substantial = bool(SUBSTANTIAL.search(text))
    if SMALL_EDIT.search(text) and not substantial:
        return False
    if READ_ONLY.search(text) and not EXPLICIT_MUTATION.search(text):
        return False

    return substantial or len(text) >= 180


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            return 0
        prompt = payload.get("user_prompt")
        if prompt is None:
            prompt = payload.get("prompt", "")
        if not isinstance(prompt, str) or not should_remind(prompt):
            return 0

        output = {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": REMINDER,
            }
        }
        json.dump(output, sys.stdout, ensure_ascii=False)
        sys.stdout.write("\n")
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        # A reminder hook must never prevent the user's prompt from being processed.
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
