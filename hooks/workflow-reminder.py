#!/usr/bin/env python3
"""Inject non-blocking workflow reminders for Claude Code and Codex prompts."""

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

REVIEW_INTENT = re.compile(
    r"(?:설명|검토|리뷰|감사|분석|조사|점검|확인|검증|대조|반례|검색|찾아|요약|번역|상태)|"
    r"\b(?:explain|review|audit|analy[sz]e|inspect|investigate|verify|validate|"
    r"check|research|search|summari[sz]e|translate|status)\b",
    re.IGNORECASE,
)

EXPLICIT_MUTATION = re.compile(
    r"(?:구현|개발|추가|생성|구축|도입|수정)"
    r"(?:해|해줘|해주세요|하자|해라|하고|한\s*(?:뒤|다음)|해서)|"
    r"코드.{0,20}작성(?:해|해줘|해주세요|하자|해라)|"
    r"만들(?:어|어줘|어주세요|고)|고쳐(?:줘|주세요)?|"
    r"(?:^|[,.!?;:]\s*|\b(?:please|and|then|also|now)\s+|"
    r"\b(?:can|could|would|will)\s+you\s+|"
    r"\b(?:need|want)\s+(?:you\s+)?to\s+)"
    r"(?:implement|build|create|develop|add|scaffold|introduce|fix|change|update)\b",
    re.IGNORECASE,
)

NO_CHANGES = re.compile(
    r"읽기\s*전용|무수정|(?:수정|변경)\s*없이|"
    r"(?:파일|코드|내용|작업물)?\s*(?:을|를|은|는)?\s*"
    r"(?:수정|변경|편집)(?:은|는|을|를)?\s*(?:하지\s*말|하지\s*마|금지)|"
    r"(?:파일|코드)\s*(?:생성|작성|수정|변경)\s*금지|"
    r"건드리지\s*마|"
    r"\bread[- ]only\b|\bno\s+changes?\b|"
    r"\bwithout\s+(?:making\s+)?(?:any\s+)?changes?\b|"
    r"\bwithout\s+(?:changing|modifying|editing)\s+(?:any\s+)?(?:code|files?)\b|"
    r"\bdo\s+not\s+(?:modify|edit|change|write)\b|"
    r"\bdo\s+not\s+make\s+(?:any\s+)?changes?\b|"
    r"\bdon['’]t\s+(?:modify|edit|change|write)\b|"
    r"\bdon['’]t\s+make\s+(?:any\s+)?changes?\b|"
    r"\bno\s+(?:file|code)\s+(?:modifications?|edits?|writes?)\b",
    re.IGNORECASE,
)

EVIDENCE_REVIEW_INTENT = re.compile(
    r"(?:검토|리뷰|감사|분석|조사|점검|확인|검증|대조|반례)|"
    r"\b(?:review|audit|analy[sz]e|inspect|investigate|verify|validate|check)\b",
    re.IGNORECASE,
)

CHECKPOINT_OR_HANDOFF_ACTION = re.compile(
    r"(?:체크\s*포인트|인수\s*인계).{0,30}"
    r"(?:남기|만들|작성|생성|갱신|업데이트|준비|정리|저장)|"
    r"(?:체크\s*포인트|인수\s*인계)\s*(?:해\s*줘|해주세요|하자|해라)|"
    r"(?:남기|만들|작성|생성|갱신|업데이트|준비|정리|저장).{0,30}"
    r"(?:체크\s*포인트|인수\s*인계)|"
    r"\b(?:create|make|leave|write|update|prepare|record|save|finish)\b"
    r".{0,50}\b(?:checkpoint|hand[- ]?off|handover)\b|"
    r"\b(?:checkpoint|hand[- ]?off|handover)\b.{0,40}"
    r"\b(?:this|the|my|our)\s+(?:work|changes?|task|project)\b|"
    r"\bWIP\b.{0,20}\b(?:commit|checkpoint)\b|"
    r"(?:WIP|작업\s*중).{0,20}(?:커밋|체크\s*포인트)",
    re.IGNORECASE,
)

RESUME_INTENT = re.compile(
    r"(?:집|다른\s*곳|내일).{0,30}(?:이어|재개)|"
    r"(?:이어|재개).{0,30}(?:집|다른\s*곳|내일)|"
    r"재개\s*(?:지점|명령|방법|할\s*수)|"
    r"\b(?:resume|continue|pick\s+up)\b.{0,40}\b(?:this|the)\s+(?:work|task|project)\b|"
    r"\b(?:tomorrow|later|elsewhere|from\s+home)\b.{0,40}"
    r"\b(?:resume|continue|pick\s+up)\b",
    re.IGNORECASE,
)

LEAVING_WORK_INTENT = re.compile(
    r"퇴근\s*(?:전|하기\s*전).{0,30}(?:마무리|정리|체크\s*포인트|인수\s*인계|커밋|푸시)|"
    r"(?:마무리|정리|체크\s*포인트|인수\s*인계).{0,30}퇴근",
    re.IGNORECASE,
)

SELECTIVE_GIT_INTENT = re.compile(
    r"(?:이|해당|이번|현재|관련|요청한|지정한|선택한).{0,50}"
    r"(?:변경(?:사항)?|파일|내용).{0,12}만.{0,30}(?:커밋|푸시)|"
    r"(?:^|\s)\S+\s*만\s*(?:커밋|푸시)|"
    r"(?:커밋|푸시).{0,30}(?:해당|이번|현재|관련|요청한|지정한|선택한).{0,30}"
    r"(?:변경(?:사항)?|파일|내용).{0,12}만|"
    r"\b(?:commit|push)\s+(?:only\s+)?"
    r"(?:these|those|the|specified|selected|current)\s+(?:changes?|files?)"
    r"(?:\s+only)?\b|"
    r"\b(?:commit|push)\s+only\s+[\w./-]+|"
    r"\b(?:commit|push)\s+[\w./-]+\s+only\b|"
    r"\bonly\s+(?:commit|push)\b.{0,40}\b(?:changes?|files?)\b|"
    r"\b(?:commit|push)\b.{0,30}\b(?:only|specified|selected)\b.{0,30}"
    r"\b(?:changes?|files?)\b",
    re.IGNORECASE,
)

PLAN_REMINDER = (
    "This appears to be substantial implementation work. Invoke the plan-and-build "
    "skill before editing implementation code. Inspect the repository first, write one "
    "lightweight specification and plan, get design approval when architecture or contracts "
    "materially change, decide whether TDD applies, and split only truly independent work "
    "with stable contracts. Get explicit user approval before dispatching parallel workers. "
    "If inspection proves the change is small and localized, exit the workflow and proceed "
    "directly."
)

EVIDENCE_REVIEW_REMINDER = (
    "This request explicitly requires a non-mutating review. Invoke the "
    "evidence-first-review skill before reviewing. Lock the user-supplied context and scope "
    "first, then independently verify claims against current files, relevant diffs, raw data, "
    "and runtime evidence. Respect the read-only boundary: do not modify or create files, "
    "install tools, create checkouts or worktrees, stage changes, or save a report. Return "
    "the evidence-backed result in the user's language as a message only."
)

SAFE_CHECKPOINT_REMINDER = (
    "This request appears to need a scoped checkpoint or resumable handoff. Invoke the "
    "safe-checkpoint skill before any Git or handoff write. Inspect branch, upstream, status, "
    "diffs, runtime manifests, and existing handoff sources; separate intended changes from "
    "unrelated dirty work and generated files. Require matching authorization for handoff "
    "writes, staging and commit, remote push, and failed WIP commits. After any authorized "
    "push, re-read HEAD, upstream synchronization, and remaining dirty state."
)


def normalize(prompt: str) -> str:
    return " ".join(prompt.split())


def should_plan_and_build(text: str) -> bool:
    if not text or NO_CHANGES.search(text) or not ACTION.search(text):
        return False

    substantial = bool(SUBSTANTIAL.search(text))
    if SMALL_EDIT.search(text) and not substantial:
        return False
    if REVIEW_INTENT.search(text) and not EXPLICIT_MUTATION.search(text):
        return False

    return substantial or len(text) >= 180


def should_evidence_first_review(text: str) -> bool:
    return bool(
        text
        and NO_CHANGES.search(text)
        and EVIDENCE_REVIEW_INTENT.search(text)
    )


def should_safe_checkpoint(text: str) -> bool:
    return bool(
        text
        and (
            CHECKPOINT_OR_HANDOFF_ACTION.search(text)
            or RESUME_INTENT.search(text)
            or LEAVING_WORK_INTENT.search(text)
            or SELECTIVE_GIT_INTENT.search(text)
        )
    )


def reminders_for(prompt: str) -> list[str]:
    text = normalize(prompt)
    reminders: list[str] = []
    if should_plan_and_build(text):
        reminders.append(PLAN_REMINDER)
    if should_evidence_first_review(text):
        reminders.append(EVIDENCE_REVIEW_REMINDER)
    if should_safe_checkpoint(text):
        reminders.append(SAFE_CHECKPOINT_REMINDER)
    return reminders


def should_remind(prompt: str) -> bool:
    """Return whether any managed workflow should be mentioned."""

    return bool(reminders_for(prompt))


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            return 0
        prompt = payload.get("user_prompt")
        if prompt is None:
            prompt = payload.get("prompt", "")
        if not isinstance(prompt, str):
            return 0

        reminders = reminders_for(prompt)
        if not reminders:
            return 0

        output = {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": "\n\n".join(reminders),
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
