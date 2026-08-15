"""PHP 기준선 — 다언어 작업이 주 스택(PHP)의 실효 동작을 줄이지 못하게 고정한다.

두 종류가 섞여 있다.

* **GREEN** — 현재 동작을 고정하는 특성화 테스트. 작성 즉시 통과해야 한다. 실패하면
  다언어 작업이 무언가를 깨뜨렸거나, 현행 동작을 잘못 이해한 것이다.
* **RED** — 아직 없는 동작을 요구하는 인수 테스트. `@unittest.expectedFailure`로 표시하며
  지금은 실패가 정상이다. 해당 단계에서 동작이 들어오면 `unexpectedSuccess`가 되고,
  unittest는 그것을 실패로 집계하므로(`TestResult.wasSuccessful()`) 데코레이터를 떼지 않으면
  스위트가 붉어진다. 즉 게이트가 스스로 강제된다.

설계 규칙 세 가지.

1. **합친 문자열을 쓰지 않는다.** `read_skill()`은 SKILL.md와 참조를 합치므로 지시가 잘못된
   파일로 옮겨가도 통과한다(해당 헬퍼의 docstring이 스스로 경고한다). 여기서는 지시가 있어야
   할 위치를 직접 읽는다.
2. **단어가 아니라 동작을 고정한다.** "read-only라는 단어가 파일 어딘가에 있다"는 인수 조건이
   될 수 없다 — 한 줄 추가로 통과하면서 `wget` 설치와 `--fix`가 그대로 남는다. 쓰기를 유발하는
   **명령 각각**이 읽기 전용 가드를 동반하는지, 규칙 **각각**이 살아 있는지를 본다.
3. **RED의 전제조건은 별도 GREEN으로 고정한다.** `expectedFailure`는 모든 예외를 흡수하므로,
   RED가 읽는 파일이 사라져 `FileNotFoundError`가 나도 "예상 실패"로 집계된다.
   `PreconditionsForRedTests`가 그 전제를 따로 지킨다.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REVIEW_SKILLS = ("code-quality-review", "web-security-review", "branch-merge-review")

QUALITY_REFERENCES = (
    "php-quality",
    "js-toolchain",          # 3단계 분할: 도구 + 환경 중립 패턴 (명령의 단일 원천)
    "js-frontend-quality",   # 브라우저 표면
    "node-quality",          # 서버·CLI·데몬·라이브러리
    "python-quality",        # 6단계: Python
    "go-quality",            # 6단계: Go
    "rust-quality",          # 6단계: Rust
    "css-quality",
)

#: 쓰기 유발 능력마다 (참조, 이름, **앵커 패턴**, **보존 패턴**).
#:
#: 앵커와 보존을 나누는 이유: 계약 마커가 붙어야 할 자리와, 명령이 살아 있는지 확인할 자리가
#: 다를 수 있다. Stylelint 설정 생성은 지시가 산문이고 실제 내용은 코드 블록이다.
#: 능력마다 앵커가 **모호하지 않아야** 한다 — `phpcbf` 로만 찾으면 설치 파일명(`phpcbf.phar`)이
#: 먼저 잡혀, 설치만 가드하고 자동수정은 무조건 실행해도 통과한다.
WRITE_CAUSING = (
    # 설치 준비 — 디렉터리 생성과 실행 권한 부여도 쓰기다.
    ("php-quality", "설치 디렉터리 생성", r"mkdir -p ~/\.local/bin", r"mkdir -p ~/\.local/bin"),
    ("php-quality", "PHPStan 설치", r"wget[^\n]*phpstan", r"wget[^\n]*phpstan"),
    ("php-quality", "PHPStan 실행권한", r"(?m)chmod \+x ~/\.local/bin/phpstan$", r"(?m)chmod \+x ~/\.local/bin/phpstan$"),
    ("php-quality", "phpcs 설치", r"curl[^\n]*phpcs\.phar", r"curl[^\n]*phpcs\.phar"),
    ("php-quality", "phpcbf 설치", r"curl[^\n]*phpcbf\.phar", r"curl[^\n]*phpcbf\.phar"),
    ("php-quality", "phpcs/phpcbf 실행권한", r"chmod \+x[^\n]*phpcs[^\n]*phpcbf", r"chmod \+x[^\n]*phpcs[^\n]*phpcbf"),
    ("php-quality", "phpmd 설치", r"wget[^\n]*phpmd", r"wget[^\n]*phpmd"),
    ("php-quality", "phpmd 실행권한", r"chmod \+x ~/\.local/bin/phpmd", r"chmod \+x ~/\.local/bin/phpmd"),
    ("php-quality", "phpcpd 설치", r"wget[^\n]*phpcpd", r"wget[^\n]*phpcpd"),
    ("php-quality", "phpcpd 실행권한", r"chmod \+x ~/\.local/bin/phpcpd", r"chmod \+x ~/\.local/bin/phpcpd"),
    ("php-quality", "PHP 자동수정 실행", r"(?m)^phpcbf\s+--", r"(?m)^phpcbf\s+--"),
    ("js-toolchain", "ESLint 설치", r"npm install[^\n]*\beslint\b", r"npm install[^\n]*\beslint\b"),
    ("js-toolchain", "Biome 설치", r"npm install[^\n]*@biomejs/biome", r"npm install[^\n]*@biomejs/biome"),
    ("js-toolchain", "Biome 초기화", r"@biomejs/biome init", r"@biomejs/biome init"),
    ("js-toolchain", "Oxlint 설치", r"npm install[^\n]*\boxlint\b", r"npm install[^\n]*\boxlint\b"),
    ("js-toolchain", "svelte-check 설치", r"npm install[^\n]*svelte-check", r"npm install[^\n]*svelte-check"),
    ("js-toolchain", "knip 설치", r"npm install[^\n]*\bknip\b", r"npm install[^\n]*\bknip\b"),
    ("js-toolchain", "ESLint 보고서 출력", r"-o \S+\.json", r"-o \S+\.json"),
    ("js-toolchain", "ESLint 자동수정", r"eslint[^\n]*--fix", r"eslint[^\n]*--fix"),
    ("js-toolchain", "Biome 자동수정", r"biome[^\n]*--write", r"biome[^\n]*--write"),
    ("js-toolchain", "Oxlint 자동수정", r"oxlint[^\n]*--fix", r"oxlint[^\n]*--fix"),
    ("js-toolchain", "knip 자동수정", r"knip[^\n]*--fix", r"knip[^\n]*--fix"),
    ("css-quality", "Stylelint 설치", r"(?m)npm install[^\n]*\bstylelint$", r"(?m)npm install[^\n]*\bstylelint$"),
    ("css-quality", "Stylelint 표준 설정 설치", r"(?m)npm install[^\n]*stylelint-config-standard$", r"(?m)npm install[^\n]*stylelint-config-standard$"),
    ("css-quality", "Stylelint SCSS 설정 설치", r"npm install[^\n]*stylelint-config-standard-scss", r"npm install[^\n]*stylelint-config-standard-scss"),
    # 설정 생성은 지시가 산문, 내용은 코드 블록 — 앵커와 보존이 갈리는 유일한 항목.
    ("css-quality", "Stylelint 설정 생성", r"create a minimal one", r'"extends": \[[^\]]*stylelint-config-standard'),
    ("css-quality", "Stylelint 자동수정", r"stylelint[^\n]*--fix", r"stylelint[^\n]*--fix"),
    ("python-quality", "Python 도구 설치(uv)", r"uv tool install", r"uv tool install"),
    ("python-quality", "Python 도구 설치(pip)", r"pip install", r"pip install"),
    ("python-quality", "ruff 자동수정", r"ruff check --fix", r"ruff check --fix"),
    ("python-quality", "ruff 포매팅 적용", r"(?m)^ruff format \.$", r"(?m)^ruff format \.$"),
    ("go-quality", "staticcheck 설치", r"go install[^\n]*staticcheck", r"go install[^\n]*staticcheck"),
    ("go-quality", "golangci-lint 설치", r"go install[^\n]*golangci-lint", r"go install[^\n]*golangci-lint"),
    ("go-quality", "gofmt 자동수정", r"gofmt -w", r"gofmt -w"),
    ("rust-quality", "clippy/rustfmt 컴포넌트 설치", r"rustup component add", r"rustup component add"),
    ("rust-quality", "cargo-audit 설치", r"cargo install cargo-audit", r"cargo install cargo-audit"),
    ("rust-quality", "rustfmt 자동수정", r"(?m)^cargo fmt\s+#", r"(?m)^cargo fmt\s+#"),
    ("rust-quality", "clippy 자동수정", r"cargo clippy --fix", r"cargo clippy --fix"),
)

#: 절 이름 → 선언된 심각도. 개수가 아니라 **의미**를 고정한다. 같은 `MUST` 문법에 서로 다른
#: 심각도가 붙는다는 사실이 "규칙 위반 = 자동 High" 같은 문법 기반 승격을 금지하는 근거다.
PHP_SECURITY_SEVERITY = {
    "1. SQL Injection": "Critical",
    "2. XSS — Output Encoding": "High",
    "3. CSRF Protection": "High",
    "4. Session Security": "High",
    "5. File Upload Security": "Critical",
    "6. Authentication & Password Handling": "Critical",
    "7. Input Validation": "Medium–High",
    "8. Directory Traversal": "Critical",
    "9. Error & Exception Handling": "Medium",
}

#: `10. Miscellaneous`는 하위 항목이 각자 심각도를 갖는다. 이것들을 하나로 뭉뚱그리면
#: CORS 오설정(High)이 HTTP 헤더(Medium)에 묻힌다.
PHP_SECURITY_SUBCATEGORIES = (
    "### HTTP Security Headers (Medium)",
    "### CORS (High if misconfigured)",
    "### Sensitive Data Exposure (High)",
)


def read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def quality_reference(name: str) -> str:
    return read(f"skills/code-quality-review/references/{name}.md")


def between(text: str, start_marker: str, end_marker: str, *, label: str) -> str:
    """start_marker부터 end_marker 직전까지. 마커가 없으면 진단 메시지와 함께 실패한다."""
    start = text.find(start_marker)
    if start < 0:
        raise AssertionError(f"{label}: 시작 마커를 찾지 못했다 — {start_marker!r}")
    end = text.find(end_marker, start + len(start_marker))
    if end < 0:
        raise AssertionError(f"{label}: 종료 마커를 찾지 못했다 — {end_marker!r}")
    return text[start:end]


#: **1단계가 내야 할 표준 계약 문구.** 쓰기를 유발하는 명령마다 바로 앞에 이 줄을 둔다.
#:
#: 자연어 부정 판별을 정규식으로 확장하는 것은 끝나지 않는 군비경쟁이다 — `never skip` 을
#: 막으면 `do not ever skip`, 그다음 `생략하면 안 된다` 가 나온다. 반대로 자연스러운 규범형
#: (`MUST NOT install or run`)은 거부되어 올바른 구현이 GREEN이 되지 못한다.
#:
#: 그래서 판정을 **선언된 계약**으로 옮긴다. 마커는 사람이 읽는 가시 텍스트여야 한다 —
#: HTML 주석은 이 저장소가 비지시 텍스트로 취급하므로 모델이 읽지 않는다.
READ_ONLY_MARKER = (
    "**Read-only:** skip this command; record it as `skipped-read-only`."
)

#: 블록 단위 계약. 코드 블록 바로 앞 산문에 두면 그 블록의 **모든** 명령을 덮는다.
#: 명령마다 긴 문장을 반복하면 설치 블록이 읽히지 않으므로 두 형태를 함께 허용하되,
#: 문구가 "every command in this block" 이라고 **범위를 명시**하므로 부분 가드로 오인되지
#: 않는다. 명령 하나만 가드하려는 의도라면 명령 단위 형태를 써야 한다.
READ_ONLY_BLOCK_MARKER = (
    "**Read-only:** skip every command in this block; "
    "record them as `skipped-read-only`."
)

#: 마커를 명령과 연결하는 창. 절 단위 불리언이면 같은 절의 한 명령만 가드해도 나머지가 함께
#: 통과한다(PHP 설치 네 건이 같은 `## 1. CLI Tool Setup` 절에 있다).
GUARD_WINDOW_LINES = 10


def html_comment_spans(text: str) -> list[tuple[int, int]]:
    """HTML 주석 구간. 이 저장소는 이를 비지시 텍스트로 취급하므로 모델이 읽지 않는다."""
    return [(m.start(), m.end()) for m in re.finditer(r"<!--.*?-->", text, re.DOTALL)]


_FENCE_OPEN = re.compile(r"^( {0,3})(`{3,}|~{3,})([^\n]*)$")


def fenced_spans_with_language(text: str) -> list[tuple[int, int, str, bool]]:
    """펜스 구간과 언어. CommonMark 규칙을 따른다.

    정규식 한 방으로 처리하면 세 가지를 함께 틀린다 — 최대 3칸 들여쓰기를 놓치고, 여는
    펜스보다 **긴** 닫는 펜스를 인정하지 않으며, `bash title=demo` 같은 info string에서
    언어를 뽑지 못한다. 각각이 진짜 펜스를 놓쳐 벌거벗은 마커를 통과시키거나, 반대로
    유효한 마커를 거부한다.
    """
    spans: list[tuple[int, int, str, bool]] = []
    lines = text.splitlines(keepends=True)
    offsets, position = [], 0
    for line in lines:
        offsets.append(position)
        position += len(line)

    index = 0
    while index < len(lines):
        opening = _FENCE_OPEN.match(lines[index].rstrip("\n\r"))
        if not opening:
            index += 1
            continue
        indent, fence, info = opening.groups()
        # info string 의 첫 낱말이 언어다. 나머지는 속성이므로 무시한다.
        language = info.strip().split()[0].lower() if info.strip() else ""
        start = offsets[index]
        index += 1
        while index < len(lines):
            candidate = lines[index].rstrip("\n\r")
            closing = re.match(rf"^ {{0,3}}({re.escape(fence[0])}{{{len(fence)},}})[ \t]*$", candidate)
            if closing:
                spans.append((start, offsets[index] + len(lines[index]), language, True))
                index += 1
                break
            index += 1
        else:
            # 닫히지 않은 펜스는 문서 끝까지로 본다 — 그 안의 마커를 지시로 오인하지 않는다.
            # 종결 여부를 함께 돌려줘야 `code_blocks()` 가 마지막 줄을 닫는 펜스로 오인하지 않는다.
            spans.append((start, len(text), language, False))
    return spans


#: 펜스 언어별 주석 접두. **언어와 무관하게 둘 다 허용하면 안 된다** — Bash에서 `//` 는
#: 주석이 아니라 명령이고, 그 줄은 오류를 내고 다음 명령이 그대로 실행된다. 즉 무효한 마커가
#: 정상 가드로 통과한다. 모르는 언어는 펜스 밖 산문 마커만 인정한다.
_FENCE_COMMENT_PREFIX = {
    "bash": "#", "sh": "#", "shell": "#", "zsh": "#", "console": "#",
    "powershell": "#", "ps1": "#", "pwsh": "#", "yaml": "#", "yml": "#",
    "js": "//", "javascript": "//", "ts": "//", "typescript": "//",
    "jsx": "//", "tsx": "//", "php": "//", "scss": "//", "sass": "//",
}
#: 의도적으로 뺀 것 — `json` 은 문법에 주석이 없고, 순수 `css` 주석은 `/* … */` 뿐이다.
#: SCSS/Sass 는 `//` 단일 행 주석을 정식으로 지원하므로 포함한다(저장소 자신도 그렇게 쓴다).
#: `//` 를 허용하면 "예제를 깨뜨리지 않는 유효한 주석"이라는 계약을 스스로 어긴다.
#: 이런 펜스에는 인라인 마커를 두지 말고 펜스 **밖** 산문 마커를 쓴다.


def marker_lines(text: str) -> list[int]:
    """계약 문구가 **지시로 읽히는 자리에** 독립된 줄로 놓인 위치(문자 오프셋).

    허용하는 두 형태:

    * 펜스 **밖**의 산문 줄 — 줄 전체가 계약 문장과 일치.
    * 펜스 **안**의 주석 줄 — `#` 또는 `//` 뒤에 계약 문장. 코드 블록은 이 스킬들에서
      실행할 명령 그 자체이므로, 명령 바로 위 주석이 가장 국소적이고 자연스러운 자리다.

    거부하는 것:

    * 접두어만 일치 — `**Read-only:** skip nothing; always run it.` 같은 반대 문구가 통과한다.
    * 펜스 안의 **벌거벗은** 줄 — 예제를 깨뜨리면서 게이트만 통과한다.
    * HTML 주석 안 — 이 저장소가 비지시 텍스트로 취급한다.
    """
    languages = fenced_spans_with_language(text)
    fences = [(start, end) for start, end, _lang, _closed in languages]
    comments = html_comment_spans(text)
    offsets = []
    position = 0
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        inside_fence = any(start <= position < end for start, end in fences)
        inside_comment = any(start <= position < end for start, end in comments)
        if inside_comment:
            position += len(line)
            continue
        if inside_fence:
            language = next(
                (lang for start, end, lang, _closed in languages if start <= position < end),
                "",
            )
            prefix = _FENCE_COMMENT_PREFIX.get(language)
            if prefix is None:
                matched = False   # 모르는 언어 — 펜스 밖 산문 마커만 인정한다
            else:
                body = stripped[len(prefix):].strip() if stripped.startswith(prefix) else None
                matched = body is not None and " ".join(body.split()) == READ_ONLY_MARKER
        else:
            matched = " ".join(stripped.split()) == READ_ONLY_MARKER
        if matched:
            offsets.append(position)
        position += len(line)
    return offsets


def block_guarded_spans(text: str) -> list[tuple[int, int]]:
    """블록 단위 마커가 덮는 펜스 구간.

    마커와 펜스 사이에는 **공백만** 허용한다. 거리 제한이 아니라 인접성 규칙이다 —
    사이에 산문이 끼면 그 산문이 계약을 뒤집을 수 있고, 어느 블록을 가리키는지도 모호해진다.
    (`GUARD_WINDOW_LINES` 는 명령 단위 마커에만 적용된다.)
    """
    fences = [(start, end) for start, end, _lang, _closed in fenced_spans_with_language(text)]
    covered = []
    for offset in _standalone_marker_offsets(text, READ_ONLY_BLOCK_MARKER):
        following = next((span for span in fences if span[0] >= offset), None)
        if following is None:
            continue
        # 마커 줄 자체를 제외한 사이 텍스트에 **공백 외의 것이 있으면 연결하지 않는다.**
        # "10줄 이내 첫 펜스"만 보면 사이에 "run them anyway" 같은 산문이 끼어도 통과한다.
        marker_line_end = text.find("\n", offset)
        between_text = text[marker_line_end + 1 : following[0]] if marker_line_end >= 0 else ""
        if between_text.strip() == "":
            covered.append(following)
    return covered


def _standalone_marker_offsets(text: str, marker: str) -> list[int]:
    """펜스·HTML 주석 **밖**의 산문 줄에서 `marker` 와 완전히 일치하는 줄의 오프셋."""
    fences = [(start, end) for start, end, _lang, _closed in fenced_spans_with_language(text)]
    comments = html_comment_spans(text)
    offsets = []
    position = 0
    for line in text.splitlines(keepends=True):
        outside = not any(
            start <= position < end for start, end in fences + comments
        )
        if outside and " ".join(line.split()) == marker:
            offsets.append(position)
        position += len(line)
    return offsets


def unguarded_by_anchor(text: str, anchors: dict[str, str]) -> dict[str, list[int]]:
    """앵커별로, 계약 문구를 동반하지 않은 발생의 줄 번호.

    세 가지를 함께 지킨다.

    * **모든 발생을 검사한다.** 첫 발생만 보면 같은 명령을 뒤에 가드 없이 추가해도 통과한다.
    * **마커를 1:1로 소비한다.** 한 마커가 뒤따르는 여러 명령을 함께 덮으면 "PHPStan만 생략"
      가드 하나로 같은 절의 네 설치가 전부 통과한다.
    * **소비는 파일 전체에서 한 번**이다. 능력마다 따로 계산하면 같은 마커를 여러 능력이
      각각 가져가 1:1이 깨진다.

    문서 순서대로 처리하고, 각 발생은 아직 소비되지 않은 가장 가까운 선행 마커만 가져간다.
    """
    occurrences = []
    for name, pattern in anchors.items():
        found = list(re.finditer(pattern, text, re.MULTILINE))
        if not found:
            raise AssertionError(f"{name}: {pattern!r} 가 사라졌다")
        occurrences.extend((match.start(), name) for match in found)
    occurrences.sort()

    available = marker_lines(text)
    block_covered = block_guarded_spans(text)
    consumed: set[int] = set()
    unguarded: dict[str, list[int]] = {name: [] for name in anchors}
    for position, name in occurrences:
        # 블록 단위 마커는 그 블록의 모든 명령을 덮으므로 1:1 소비 대상이 아니다.
        if any(start <= position < end for start, end in block_covered):
            continue
        window_start = _line_offset(text, position, -GUARD_WINDOW_LINES)
        claimed = next(
            (
                offset
                for offset in reversed(available)
                if offset not in consumed and window_start <= offset <= position
            ),
            None,
        )
        if claimed is None:
            unguarded[name].append(text.count("\n", 0, position) + 1)
        else:
            consumed.add(claimed)
    return unguarded


def unguarded_occurrences(text: str, pattern: str) -> list[int]:
    """단일 앵커용 얇은 래퍼 — 자기 테스트에서 쓴다."""
    return unguarded_by_anchor(text, {"anchor": pattern})["anchor"]


def _line_offset(text: str, position: int, lines_back: int) -> int:
    """`position` 에서 `lines_back` 줄 위의 오프셋. 경계는 **포함**이다.

    한 번 더 거슬러 올라가는 이유: 일치 위치가 자기 줄 중간이라 첫 되감기는 그 줄의 시작까지만
    간다. `+ 1` 이 없으면 `GUARD_WINDOW_LINES = 10` 이 실제로는 9줄까지만 인정한다.
    """
    start = position
    for _ in range(-lines_back + 1):
        previous = text.rfind("\n", 0, start)
        if previous < 0:
            return 0
        start = previous
    return start


def statements(text: str) -> list[str]:
    """빈 줄로 나눈 단락을 공백 정규화해 반환한다.

    물리적 한 줄로 검사하면 두 가지가 함께 깨진다 — 줄바꿈된 문장을 놓치고, 서로 무관한
    인접 두 줄을 한 문장으로 오인한다.
    """
    return [
        " ".join(block.split())
        for block in re.split(r"\n\s*\n", text)
        if block.strip()
    ]


#: `is not prohibited` 처럼 **금지어 자체가 부정된** 형태. 금지로 인정하면 게이트가 뒤집힌다.
_NEGATED_PROHIBITION = re.compile(
    r"(?:not|never|no longer)\s+(?:\w+\s+){0,2}?"
    r"(?:prohibited|forbidden|blocked|prevented|불가|금지)"
    r"|금지(?:되지|하지)\s*않",
    re.IGNORECASE,
)


def prohibits(text: str, subject: str) -> bool:
    """`subject` 를 **금지**한다고 말하는가. 언급도, 이중 부정도 인정하지 않는다.

    한계(수용): 자유 문장 판정이라 표현 변형에 취약하다. 이 검사는 3단계 인수 조건이므로,
    1단계처럼 즉시 필요한 게이트에는 `READ_ONLY_MARKER` 같은 선언 계약을 쓴다.
    """
    negation = r"cannot|must not|may not|never|is not|불가|금지|안 된다|않는다"
    pattern = re.compile(
        rf"(?:{negation}).{{0,80}}?{re.escape(subject)}"
        rf"|{re.escape(subject)}.{{0,80}}?(?:{negation})",
        re.IGNORECASE,
    )
    for statement in statements(text):
        if _NEGATED_PROHIBITION.search(statement):
            return False
        if pattern.search(statement):
            return True
    return False


def code_blocks(text: str) -> str:
    """펜스 코드 블록의 **본문만** 이어붙인다. 산문과 실행 지시를 가르는 경계다.

    스캐너는 하나뿐이다 — 별도 정규식을 두면 한쪽이 놓치는 펜스를 다른 쪽이 잡아 두 검사의
    결과가 어긋난다.

    **닫히지 않은 펜스는 마지막 줄을 버리지 않는다.** `body[1:-1]` 을 무조건 쓰면 닫는 펜스가
    없는 블록의 마지막 명령이 검사에서 사라져, 맨 `npx` 같은 우회가 통과한다.
    """
    parts = []
    for start, end, _language, closed in fenced_spans_with_language(text):
        body = text[start:end].splitlines(keepends=True)
        parts.extend(body[1:-1] if closed else body[1:])
    return "".join(parts)


def invoked_as_command(text: str, tool: str) -> bool:
    """도구가 **실행**되는가. 줄 첫머리 산문(`phpstan should not be run.`)과 구분한다.

    `vendor/bin/` 경로, `php <tool>.phar`, `$PHP_CMD` 접두, `~~~` 펜스를 모두 인정한다.
    """
    prefix = r"(?:\$PHP_CMD\s+)?(?:\$\(command -v\s+)?(?:php\s+)?(?:[\w./~-]*/)?"
    pattern = re.compile(
        rf"^\s*{prefix}{re.escape(tool)}(?:\.phar)?"
        rf"(?:\)?\s+(?:-|\$|<|\w+/|\w+\.|analyse|analyze|check|text|\*))",
        re.MULTILINE,
    )
    return bool(pattern.search(code_blocks(text)))


def states_affirmatively(text: str, phrase_pattern: str) -> bool:
    """문구가 **긍정형으로** 선언되는가.

    부정어는 **같은 문장 안**에서만 부정으로 본다 — 앞("Never dispatch …")이든 뒤
    ("Dispatching … is prohibited.")든 상관없다. 단락 전체를 보면
    무관한 부정어("The roster is variable, **not** fixed at three.")가 옆 문장에 있다는
    이유로 올바른 선언을 거부한다 — 거짓 음성도 게이트를 망가뜨린다.
    """
    negative = re.compile(
        r"\bnever\b|\bnot\b|\bno\b|없이|말고|않는다|않는|금지|exclude|prohibit",
        re.IGNORECASE,
    )
    for statement in statements(text):
        for sentence in re.split(r"(?<=[.!?])\s+", statement):
            match = re.search(phrase_pattern, sentence, re.IGNORECASE)
            if not match:
                continue
            # 문장 전체를 본다 — 부정은 앞에도("Never dispatch …") 뒤에도
            # ("Dispatching … is prohibited.") 올 수 있다. 문장 단위로 쪼갠 뒤이므로
            # 옆 문장의 무관한 부정어가 섞이지 않는다.
            if negative.search(sentence):
                continue
            return True
    return False


def _compiles(pattern: str) -> bool:
    try:
        re.compile(pattern)
    except re.error:
        return False
    return True


def enclosing_section(text: str, needle: str, *, label: str, regex: bool = False) -> str:
    """needle을 포함하는 `## ` 절 전체.

    "파일 어딘가에 단어가 있다"가 아니라 "그 명령이 놓인 절이 조건을 갖췄다"를 보기 위한
    것이다. 파일 맨 위에 한 줄 추가하는 것으로는 통과할 수 없다.
    """
    if regex:
        match = re.search(needle, text)
        position = match.start() if match else -1
    else:
        position = text.find(needle)
    if position < 0:
        raise AssertionError(f"{label}: {needle!r} 가 사라졌다")
    heading = text.rfind("\n## ", 0, position)
    start = 0 if heading < 0 else heading + 1
    following = text.find("\n## ", position)
    end = len(text) if following < 0 else following
    return text[start:end]


class PhpScopeBaseline(unittest.TestCase):
    """1 · 3 — PHP 경로가 리뷰 범위에서 누락되지 않는다."""

    def test_php_files_are_backend_scope_without_a_manifest(self) -> None:
        """GREEN — `.php` 확장자만으로 Backend가 결정된다.

        레거시 PHP 프로젝트에는 composer.json이 없는 경우가 흔하다. 분류가 매니페스트에
        의존하게 되면 그런 저장소의 백엔드 리뷰어가 통째로 디스패치되지 않는다.
        """
        table = between(
            read("skills/branch-merge-review/SKILL.md"),
            "| Category | Extensions / Filenames |",
            "If no files match a category",
            label="파일 분류 표",
        )
        rows = {
            line.split("|")[1].strip(): line
            for line in table.splitlines()
            if line.startswith("|") and line.count("|") >= 3
        }
        php_backend = [
            line for label, line in rows.items()
            if "Backend" in label and "PHP" in label
        ]
        self.assertTrue(php_backend, f"PHP Backend 행이 없다: {sorted(rows)}")
        self.assertIn("`*.php`", php_backend[0])
        # Backend 판정이 매니페스트를 요구하게 되면 composer 없는 저장소가 빠진다.
        self.assertRegex(
            php_backend[0], r"extension alone|확장자",
            "PHP 분류가 확장자만으로 결정된다고 표에 남아 있어야 한다",
        )
        for label, line in rows.items():
            if "Backend" not in label and "Category" not in label:
                with self.subTest(row=label):
                    self.assertNotIn("`*.php`", line)

        detection = read("skills/code-quality-review/SKILL.md")
        self.assertIn("- PHP: `composer.json`, `*.php` files", detection)

    def test_the_security_scope_command_keeps_deletions(self) -> None:
        """GREEN(3a) — 설명 문구가 아니라 **실효 명령**을 고정한다.

        제거된 인증 가드·검증기 자체가 findings이므로 보안 범위는 삭제를 포함해야 한다.
        품질 범위(`CHANGED_QA`)만 `--diff-filter=d`로 삭제를 제외한다. 설명만 남기고
        명령에 필터가 들어가는 회귀를 잡기 위해 명령 블록을 직접 읽는다.
        """
        skill = read("skills/branch-merge-review/SKILL.md")
        security_block = between(
            skill, "CHANGED_SEC=$(", "sort -u)", label="CHANGED_SEC 명령"
        )
        self.assertIn('git diff --name-only "$MERGE_BASE" HEAD', security_block)
        self.assertNotIn("--diff-filter", security_block)

        quality_block = between(
            skill, "CHANGED_QA=$(", "sort -u)", label="CHANGED_QA 명령"
        )
        self.assertIn("--diff-filter=d", quality_block)

    def test_rename_away_from_php_uses_the_previous_path(self) -> None:
        """GREEN (3단계에서 전환됨) — rename의 이전 경로가 보안 범위에 합류한다.

        커밋 범위 수집은 rename에서 새 경로만 산출하므로, 별도 수집이 없으면 `.php`가 `.ts`로
        옮겨가며 사라진 인증 로직이 리뷰에 보이지 않는다. 그래서 이전 경로를 따로 모아
        `CHANGED_SEC`에 합류시킨다.

        산문 선언과 **실효 명령**을 함께 요구하고, `cut` 필드 번호까지 고정한다 — 올바른 구현을
        설명하는 문장만 추가하거나 새 경로를 수집하는 구현으로는 통과할 수 없다.
        """
        skill = read("skills/branch-merge-review/SKILL.md")
        # 산문 선언과 **실효 명령** 둘 다 요구한다. `_previous` 같은 변수명 존재 여부는
        # 대리 신호일 뿐이라, 올바른 구현이 다른 이름을 쓰면 거짓 실패한다.
        self.assertTrue(
            states_affirmatively(
                skill, r"previous path[^\n]*CHANGED_SEC|CHANGED_SEC[^\n]*previous"
            ),
            "이전 경로가 보안 범위에 합류한다고 긍정형으로 선언되지 않았다",
        )
        commands = code_blocks(skill)
        # `--name-status --diff-filter=R` 은 `R100\t이전\t새` 를 낸다. `cut -f2` 가 이전 경로,
        # `cut -f3` 은 **새 경로**다 — 후자를 수집하면 이미 있는 경로를 다시 넣을 뿐이라
        # 사라진 PHP 문맥은 여전히 안 보인다. 명령의 필드 선택까지 고정한다.
        posix = re.search(
            r"--name-status[^\n]*--diff-filter=R[^\n]*\|[^\n]*cut -f(\d)", commands
        )
        self.assertIsNotNone(posix, "rename 이전 경로를 수집하는 POSIX 명령이 없다")
        self.assertEqual(
            posix.group(1), "2",
            "cut 필드가 2가 아니면 새 경로를 수집하는 것이다 (이전 경로는 2번 필드)",
        )
        self.assertRegex(
            commands,
            r"CHANGED_SEC=[^\n]*RENAME|RENAME[^\n]*CHANGED_SEC",
            "수집한 이전 경로가 CHANGED_SEC 에 합류하지 않는다",
        )
        # Windows 네이티브 설치에서도 같은 합류가 있어야 한다.
        self.assertRegex(
            commands,
            # PowerShell 블록에는 백틱(`` `t ``)이 있으므로 백틱을 제외하면 매치되지 않는다.
            r"(?s)diff --name-status[^\n]*-M[\s\S]{0,600}?changedSec",
            "PowerShell 수집에 rename 이전 경로 합류가 없다",
        )


class PhpReviewerBaseline(unittest.TestCase):
    """2 · 4 · 10 — PHP 리뷰어가 밀려나거나, 지시를 잃거나, 실패를 숨기지 않는다."""

    PHP_SPECIFIC_CHECKS = (
        "N+1 query patterns",
        "Evaluation order",
        "Duplicated query logic",
        "phpstan.neon",
    )

    def test_php_specific_checks_stay_reachable(self) -> None:
        """GREEN — 페르소나를 매개변수화해도 이 점검 항목은 도달 가능해야 한다.

        정본 수렴 단계에서 지시가 프롬프트에서 `php-quality.md`로 옮겨갈 수 있다. 그래서
        두 허용 위치를 각각 읽고 **적어도 한 곳**에 있으면 통과시킨다. 합친 문자열을 쓰지
        않으면서도 정당한 이동에 거짓 실패하지 않기 위함이다.
        """
        allowed = {
            "reviewer-prompts.md": read(
                "skills/branch-merge-review/references/reviewer-prompts.md"
            ),
            "php-quality.md": quality_reference("php-quality"),
        }
        for check in self.PHP_SPECIFIC_CHECKS:
            with self.subTest(check=check):
                locations = [name for name, text in allowed.items() if check in text]
                self.assertTrue(
                    locations, f"{check!r} 가 허용된 두 위치 어디에도 없다"
                )

    def test_php_and_node_get_separate_quality_reviewers(self) -> None:
        """GREEN (3단계에서 전환됨) — Backend Quality 리뷰어가 하나뿐이라 한 언어가 다른 언어를 덮는다.

        고정 로스터에서는 백엔드 품질 슬롯이 하나뿐이라 특정 언어 참조를 직접 지정했다.
        `{language}` 치환만 하면 PHP+Node 저장소에서 한쪽 리뷰가 사라진다.

        산문이 아니라 **로스터 표의 구조**를 본다 — 백엔드 품질 슬롯 행이 특정 언어 참조를 고정하지
        않아야 하고, 감지된 백엔드 언어마다 리뷰어가 생성돼야 한다.
        """
        skill = read("skills/branch-merge-review/SKILL.md")
        self.assertNotIn("Dispatch 3 Reviewers in Parallel", skill)

        roster = between(
            skill,
            "| Agent | Skill invoked | Scope |",
            "- Every prompt embeds the Common Instructions",
            label="리뷰어 로스터",
        )
        backend_row = next(
            (line for line in roster.splitlines() if "Backend Quality" in line), ""
        )
        self.assertNotIn("php-quality.md", backend_row)
        self.assertTrue(
            states_affirmatively(
                skill, r"per (?:detected )?backend language|감지된 백엔드 언어마다"
            ),
            "언어별 디스패치가 긍정형으로 선언되지 않았다 — 부정 선언은 게이트가 아니다",
        )

    def test_incomplete_php_review_blocks_ready_to_merge(self) -> None:
        """GREEN (3단계에서 전환됨) — PHP 리뷰어가 실패해도 정상 승인이 나올 수 있다.

        현행 실패 처리는 부분 결과로 진행하고, 보고서 판정에는 언어별 검토 완료 게이트가
        없다. 리뷰어가 언어별로 늘어나면 조용한 누락 위험이 커진다.

        게이트는 **조건과 금지를 함께** 명시해야 한다. 한 단어가 우연히 같은 줄에 있는
        것으로는 통과할 수 없도록, 세 실패 모드를 각각 요구한다.
        """
        gate = between(
            read("skills/branch-merge-review/SKILL.md"),
            "**Failure handling**",
            "## Step 5",
            label="리뷰어 실패 처리",
        )
        self.assertTrue(
            prohibits(gate, "Ready to merge"),
            "실패 처리 절이 `Ready to merge` 를 금지하지 않는다 — 언급만으로는 게이트가 아니다",
        )
        for failure_mode in (
            r"did not complete|실패",
            r"not dispatched|미디스패치|디스패치되지",
            # 부재를 뜻하는 표현이면 형태는 자유다 — 한 가지 철자만 받으면 정상 문구를 거부한다.
            r"(?:without|not|missing|미)[^\n]{0,40}reference[^\n]{0,40}load"
            r"|reference[^\n]{0,40}(?:not|without|missing)[^\n]{0,20}load"
            r"|참조[^\n]{0,20}(?:미로드|로드되지)",
        ):
            with self.subTest(failure_mode=failure_mode):
                self.assertRegex(gate, failure_mode)


class PhpToolchainBaseline(unittest.TestCase):
    """5 · 6 — 도구 실행 지시가 정본 하나에 모이고, 읽기 전용을 위반하지 않는다."""

    #: 정본이 하나여야 하는 네 조각. 문자열 하나가 아니라 의미 단위로 본다.
    VERSION_RESOLUTION_PIECES = {
        "composer 부재 폴백": r'if \[ -f composer\.json \]|composer\.json.*not|fall back',
        "제약 버전 파싱": r'"php"\s*\\?s\*:|PHP_CONSTRAINT',
        "versioned CLI": r"php\{major\}\.\{minor\}|ALT_PHP|php8\.",
        "SRC_DIR PSR-4": r"SRC_DIR|psr-4",
    }

    def test_the_four_php_tool_roles_run(self) -> None:
        """GREEN — 정적 분석 / 스타일 / 복잡도 / 중복 네 역할이 **실행 절에** 살아 있다.

        이름이 목차나 산문에만 남고 실행 절에서 빠지는 회귀를 잡기 위해, 파일 전체가 아니라
        `## 2. Running the Tools` 절만 읽는다.
        """
        reference = quality_reference("php-quality")
        # 절 번호가 바뀌어도 따라가도록 제목을 정규식으로 찾는다. 합의 기준은 물리적 배치를
        # 불변 대상으로 삼지 않으므로, 고정할 것은 "실행 절이 있고 거기서 호출된다"까지다.
        heading = re.search(r"^## \d+\. Running the Tools\s*$", reference, re.MULTILINE)
        self.assertIsNotNone(heading, "php-quality 에 실행 절이 없다")
        following = re.search(
            r"^## ", reference[heading.end():], re.MULTILINE
        )
        run_section = reference[heading.end():][
            : following.start() if following else None
        ]
        reference_all = quality_reference("php-quality")
        for tool in ("phpstan", "phpcs", "phpmd", "phpcpd"):
            with self.subTest(tool=tool):
                # 실행 절에 명령이 있거나, 정본을 가리키고 그 정본에 명령이 있어야 한다.
                # 명령을 §2 안에 **강제**하면 정본 수렴 자체가 불가능해진다.
                here = invoked_as_command(run_section, tool)
                points_elsewhere = re.search(
                    rf"§0|Section 0|owns every {tool}", run_section, re.IGNORECASE
                ) and invoked_as_command(reference_all, tool)
                self.assertTrue(
                    here or points_elsewhere,
                    f"{tool} 이 실행되지도, 정본을 가리키지도 않는다",
                )

    def test_dispatch_prompts_do_not_restate_the_phpstan_config_rule(self) -> None:
        """GREEN (3단계에서 추가) — 정본을 만들고 프롬프트에 옛 지시를 남기면 권위가 갈린다.

        프롬프트가 `phpstan.neon` 하나만 확인하라고 하면, 정본이 세 이름을 처리해도 실제
        디스패치는 부분 검사로 돌아가 프로젝트 level 을 덮는다.
        """
        prompts = read("skills/branch-merge-review/references/reviewer-prompts.md")
        # 백틱 유무에 상관없이 잡는다 — 옛 문구가 평문으로 돌아와도 통과하면 안 된다.
        self.assertNotRegex(
            prompts,
            r"check\s+`?phpstan\.neon`?\s+first",
            "프롬프트가 단일 설정 이름 폴백을 다시 지시하고 있다",
        )
        # 정본 지시는 **그 항목 안**에 있어야 한다. 파일 어딘가에 파일명이 있는 것으로는
        # 그 항목이 정본을 가리킨다는 근거가 되지 않는다.
        # `{focus}` 표의 **PHP 행**을 고른다. "PHPStan 과 config 가 든 첫 임의 행"으로 고르면
        # 앞에 다른 행이 생겼을 때 회귀가 가려진다.
        # `{focus}` 표 구간으로 한정한다. 파일 전체에서 세면 역할 매핑 표의 PHP 행까지
        # 잡히고, `PHPStan` 을 조건에 넣어 좁히면 반대로 focus 행이 둘이어도 못 잡는다.
        focus_table = between(
            prompts,
            "`{focus}` per language",
            "When a language has no row here",
            label="focus 표",
        )
        php_rows = [
            line for line in focus_table.splitlines() if line.startswith("| PHP ")
        ]
        self.assertEqual(len(php_rows), 1, f"PHP focus 행이 정확히 하나여야 한다: {php_rows}")
        phpstan_line = php_rows[0]
        self.assertIn(
            "php-quality.md", phpstan_line,
            "PHPStan 항목이 정본을 가리키지 않는다",
        )

    def test_phpstan_config_discovery_covers_all_three_names(self) -> None:
        """GREEN (3단계에서 추가) — PHPStan 은 세 이름을 자동 탐지한다.

        두 개만 검사하면 `phpstan.dist.neon` 만 있는 프로젝트가 미설정으로 보이고,
        `--level=5` 폴백이 프로젝트가 정한 level 을 덮는다.
        """
        commands = code_blocks(quality_reference("php-quality"))
        for name in ("phpstan.neon", "phpstan.neon.dist", "phpstan.dist.neon"):
            with self.subTest(config=name):
                self.assertIn(name, commands)

    def test_phpstan_result_cache_is_gated_under_read_only(self) -> None:
        """GREEN (3단계에서 추가) — 캐시가 저장소 안에 떨어지는 **두** 경로를 모두 막는다.

        기본값(`sys_get_temp_dir()/phpstan`)은 저장소 밖이라 안전하다. 안으로 들어오는 길은
        둘이며, `tmpDir` 만 보면 나머지 하나로 그대로 새어 나간다.
        """
        reference = quality_reference("php-quality")
        for setting in ("tmpDir", "resultCachePath"):
            with self.subTest(setting=setting):
                self.assertIn(setting, reference)
        commands = code_blocks(reference)
        self.assertRegex(
            commands,
            r"tmpDir\|resultCachePath|\(tmpDir\|resultCachePath\)",
            "두 설정을 함께 읽는 명령이 없다",
        )
        # 우선순위대로 고른다 — `ls | head -1` 은 사전순이라 phpstan.dist.neon 을 먼저 잡는다.
        self.assertNotRegex(
            commands, r"ls\s+phpstan[^\n]*head -1",
            "사전순 선택은 PHPStan 의 실제 우선순위와 다르다",
        )
        order = re.search(
            r"for candidate in ([^\n;]+); do", commands
        )
        self.assertIsNotNone(order, "설정 후보를 우선순위대로 도는 루프가 없다")
        self.assertEqual(
            order.group(1).split(),
            ["phpstan.neon", "phpstan.neon.dist", "phpstan.dist.neon"],
            "PHPStan 의 설정 우선순위와 다르다",
        )
        # 게이트와 실행이 같은 변수를 써야 한다 — 갈리면 검사는 A 를, 실행은 B 를 본다.
        self.assertRegex(
            commands, r"--configuration=\"?\$PHPSTAN_CONFIG",
            "실행이 게이트가 검사한 설정을 그대로 쓰지 않는다",
        )
        self.assertRegex(
            commands, r"includes:",
            "부모 설정이 캐시 경로를 정할 수 있으므로 includes 를 따라야 한다",
        )
        self.assertRegex(
            reference, r"independently of `tmpDir`|독립",
            "resultCachePath 가 tmpDir 과 독립이라는 사실이 이 항목의 실질이다",
        )
        self.assertRegex(
            reference, r"[Uu]nknown is not safe|판정할 수 없|cannot be determined",
            "실효 설정을 못 읽는 경우를 안전으로 처리하면 게이트가 뚫린다",
        )
        self.assertRegex(reference, r"skipped-read-only")

    def test_normal_mode_still_installs_missing_tools(self) -> None:
        """GREEN — 읽기 전용 조건을 잘못 걸어 일반 모드까지 죽이면 리뷰가 빈 껍데기가 된다.

        일반 모드에서 도구가 없으면 설치한다는 지시가 살아 있어야 한다. 이것이 사라지면
        리뷰는 `skipped-not-installed` 만 잔뜩 내고 실제 검사를 하지 않는다.
        """
        skill = read("skills/code-quality-review/SKILL.md")
        step_two = between(
            skill, "## Step 2: Run CLI Tools", "## Step 3", label="Step 2"
        )
        # 일반 모드 설치 경로가 살아 있어야 한다.
        self.assertIn("install per the reference file instructions", step_two)
        # 그리고 읽기 전용에서만 보류돼야 한다 — 게이트 없이 설치하면 우선 규칙을 어긴다.
        self.assertRegex(step_two, r"read-only")
        self.assertIn("skipped-read-only", step_two)
        self.assertIn("skipped-not-installed", step_two)

    def test_npm_tools_are_never_invoked_with_a_bare_npx(self) -> None:
        """GREEN (1단계에서 추가) — 맨 `npx` 는 없는 패키지를 받아 설치한다.

        npm 문서상 비대화형·CI 환경에서는 `--yes` 가 가정되므로, 에이전트가 읽기 전용
        리뷰 중 `npx eslint` 를 실행하면 **조용히 설치된다.** `--no` 는 설치 대신 실패시킨다.
        `--no-install` 은 deprecated 별칭이라 계약의 철자를 하나로 고정하기 위해 거부한다.

        본문과 참조를 함께 검사한다 — 같은 명령이 양쪽에 있어 한쪽만 고치면 드리프트한다.
        검사 범위는 **실행 지시(코드 블록)** 다. 규칙을 설명하는 산문은 맨 `npx` 를 예시로
        들 수 있어야 한다.
        """
        sources = {
            "SKILL.md": read("skills/code-quality-review/SKILL.md"),
            **{f"{name}.md": quality_reference(name) for name in QUALITY_REFERENCES},
        }
        for name, text in sources.items():
            with self.subTest(source=name):
                bare = [
                    line.strip()
                    for line in code_blocks(text).splitlines()
                    # `--no-install` 은 deprecated 별칭이다. 계약은 `--no` 하나로 고정한다.
                    # `--` 없이 쓰면 npx 가 도구의 인자를 가로챈다 (아래 테스트 참조).
                    if re.search(r"\bnpx\s+(?!--no --\s)", line)
                ]
                self.assertEqual(
                    bare, [], f"{name}: `npx --no -- ` 또는 node_modules/.bin 을 써야 한다"
                )

    def test_the_bare_npx_check_rejects_deprecated_and_unclosed_forms(self) -> None:
        """실제 문서만 스캔하면 검사기 자체의 구멍이 드러나지 않는다."""
        def bare(text: str) -> list[str]:
            return [
                line.strip()
                for line in code_blocks(text).splitlines()
                if re.search(r"\bnpx\s+(?!--no --\s)", line)
            ]

        self.assertTrue(bare("```bash\nnpx --no-install eslint .\n```"),
                        "`--no-install` 은 deprecated 별칭이므로 거부해야 한다")
        self.assertTrue(bare("```bash\nnpx eslint ."),
                        "닫히지 않은 펜스의 명령도 검사 대상이다")
        self.assertTrue(bare("```bash\nnpx --no tsc --version\n```"),
                        "`--` 가 없으면 npx 가 도구의 인자를 가로챈다")
        self.assertFalse(bare("```bash\nnpx --no -- eslint .\n```"))

    def test_windows_gets_the_cmd_wrapper_form(self) -> None:
        """`node_modules/.bin/eslint` 은 Windows 에서 실행되지 않는다 — 확장자 없는 셸 스크립트다."""
        skill = " ".join(read("skills/code-quality-review/SKILL.md").split())
        self.assertRegex(
            skill, r"node_modules\\\.bin\\<tool>\.cmd",
            "Windows 용 `.cmd` 래퍼 형태가 없다",
        )

    def test_npx_without_a_separator_really_swallows_the_tool_arguments(self) -> None:
        """이 계약은 추측이 아니라 실측이다 — npm 11.16.0 에서 재현된다.

        `npx --no tsc --version` 은 TypeScript 가 없는 환경에서도 **npm 자신의 버전을 찍고
        0 으로 끝난다.** 리뷰어는 이걸 "타입 검사 통과"로 기록한다. `--` 를 넣으면 실패한다.
        """
        if shutil.which("npx") is None:
            self.skipTest("npx 없음")
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "package.json").write_text('{"name":"t","version":"1.0.0"}')
            env = {**os.environ, "CI": "1"}

            def run(argv: list[str]):
                return subprocess.run(
                    argv, cwd=tmp, env=env, capture_output=True, text=True, timeout=180
                )

            absent = "definitely-not-a-real-package-9d2f1a"
            guarded = run(["npx", "--no", "--", absent, "--version"])
            self.assertNotEqual(
                guarded.returncode, 0,
                "`npx --no -- <미설치>` 가 성공했다 — 설치 차단 계약이 깨졌다",
            )
            self.assertNotIn(
                absent, os.listdir(tmp),
                "읽기 전용 호출이 작업 디렉터리에 무언가를 남겼다",
            )
            self.assertEqual(
                sorted(os.listdir(tmp)), ["package.json"],
                "npx 호출이 node_modules 등 부산물을 남겼다",
            )

    def test_php_version_resolution_has_a_single_source(self) -> None:
        """GREEN (3단계에서 전환됨) — 버전 해석 네 조각이 본문과 참조에 흩어져 있다.

        `SRC_DIR` PSR-4 도출은 본문에만 있어 완전한 중복도 아니다. 권위 문구만 붙이면
        모델이 비권위 사본도 계속 읽으므로 충돌이 남는다.

        토큰 하나가 아니라 **네 조각 전부가 같은 한 파일에** 있는지를 본다.
        """
        # **실행 지시만 본다.** 정본을 가리키는 산문("… derivation lives in php-quality.md")은
        # 두 번째 사본이 아니라 단일 원천 설계 그 자체다. 산문까지 세면 올바른 구현이 막힌다.
        locations = {
            "SKILL.md": code_blocks(read("skills/code-quality-review/SKILL.md")),
            "php-quality.md": code_blocks(quality_reference("php-quality")),
        }
        owners = {}
        for piece, pattern in self.VERSION_RESOLUTION_PIECES.items():
            owners[piece] = {
                name
                for name, text in locations.items()
                if re.search(pattern, text, re.IGNORECASE)
            }
        distinct = {frozenset(found) for found in owners.values()}
        self.assertEqual(
            len(distinct), 1, f"조각마다 소유 파일이 다르다: {owners}"
        )
        self.assertEqual(
            len(next(iter(distinct))), 1, f"조각이 두 파일에 중복된다: {owners}"
        )

    def test_every_write_causing_instruction_carries_a_read_only_guard(self) -> None:
        """GREEN (1단계에서 전환됨) — 쓰기를 유발하는 **명령 각각**이 읽기 전용 가드를 동반해야 한다.

        Step 2의 게이트는 "도구 설치"만 가리므로 설정 생성·자동수정·보고서 출력은 걸리지
        않는다. 그래서 쓰기를 유발하는 능력마다 계약 문구를 요구한다(현재 38개 — `WRITE_CAUSING` 이 정본).

        **파일 상단에 문구 한 줄을 추가하는 것으로는 통과할 수 없다** — 각 명령이 자기
        계약 문구를 갖거나, 범위를 명시한 블록 문구가 그 블록을 덮어야 한다.
        """
        for reference_name in QUALITY_REFERENCES:
            anchors = {
                capability: anchor
                for name, capability, anchor, _preserved in WRITE_CAUSING
                if name == reference_name
            }
            # 파일 단위로 한 번에 계산해야 마커 1:1 소비가 능력 간에도 성립한다.
            unguarded = unguarded_by_anchor(quality_reference(reference_name), anchors)
            for capability, lines in unguarded.items():
                with self.subTest(reference=reference_name, capability=capability):
                    self.assertEqual(
                        lines,
                        [],
                        f"{reference_name} 의 {capability}: {READ_ONLY_MARKER!r} 계약"
                        f" 문구가 없는 발생 {len(lines)}건 (줄 {lines})",
                    )


class PhpStanReadOnlyGateTest(unittest.TestCase):
    """읽기 전용 캐시 게이트를 **실행해서** 검증한다.

    문자열 검사는 "설정 이름이 문서에 있다"까지만 말한다. 게이트가 실제로 실행을 막는지는
    돌려 봐야 안다 — 실제로 grep 결과를 출력만 하고 그대로 실행하는 구현이 문자열 검사를
    통과한 적이 있다.
    """

    ANALYSIS_MARKER = "RAN-ANALYSIS"

    def gate_script(self) -> str:
        """`php-quality.md` §0 의 bash 블록을 꺼내 분석 호출만 마커로 대체한다."""
        reference = quality_reference("php-quality")
        match = re.search(
            r"```bash\n(# One variable decides.*?)```", reference, re.DOTALL
        )
        self.assertIsNotNone(match, "§0 실행 블록을 찾지 못했다")
        block = match.group(1)
        # 줄 이음(`\` 개행)을 먼저 합친다. 첫 줄만 치환하면 `#` 가 그 줄의 `\` 까지 주석으로
        # 만들어, 이어지던 줄이 미아 명령으로 실행되고 스크립트가 127 로 죽는다.
        block = re.sub(r"\\\n\s+", " ", block)
        block = block.replace(
            "$PHP_CMD $(command -v phpstan) analyse", f"echo {self.ANALYSIS_MARKER} #"
        )
        block = re.sub(r"^(phpcs|phpmd|phpcpd) .*", "", block, flags=re.MULTILINE)
        return "PHP_CMD=php\nSRC_DIR=src\n" + block

    def run_gate(
        self,
        config: str | None,
        *,
        readable: bool = True,
        extra: dict[str, str] | None = None,
        unreadable: tuple[str, ...] = (),
        subdir: str = "",
        env: dict[str, str] | None = None,
    ) -> str:
        """게이트 블록을 실제로 실행한다. `extra` 로 include 대상 파일을 함께 놓는다."""
        with tempfile.TemporaryDirectory() as base:
            work = Path(base, subdir) if subdir else Path(base)
            work.mkdir(parents=True, exist_ok=True)
            work = str(work)
            (Path(work) / "gate.sh").write_text(self.gate_script(), encoding="utf-8")
            written = []
            if config is not None:
                target = Path(work) / "phpstan.neon"
                target.write_text(config, encoding="utf-8")
                written.append(target)
                if not readable:
                    os.chmod(target, 0o000)
            for name, body in (extra or {}).items():
                path = Path(work) / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(body, encoding="utf-8")
                written.append(path)
                if name in unreadable:
                    os.chmod(path, 0o000)
            result = subprocess.run(
                ["bash", "gate.sh"], cwd=work, capture_output=True, text=True,
                env={**os.environ, "READ_ONLY": "1", **(env or {})},
            )
            for path in written:
                os.chmod(path, 0o644)
            # 스크립트 자체가 죽으면 "실행되지 않았다"가 아니라 하네스 결함이다.
            self.assertEqual(
                result.returncode, 0,
                f"게이트 스크립트가 종료 코드 {result.returncode} 로 실패했다:\n{result.stderr}",
            )
            return result.stdout

    def assertRan(self, output: str, message: str) -> None:
        self.assertIn(self.ANALYSIS_MARKER, output, message)

    def assertSkipped(self, output: str, message: str) -> None:
        self.assertNotIn(self.ANALYSIS_MARKER, output, message)
        self.assertIn("skipped-read-only", output, message)

    def test_a_config_without_cache_settings_runs(self) -> None:
        """기본 캐시 위치는 저장소 밖이다 — 막으면 정상 프로젝트의 정적 분석이 죽는다."""
        self.assertRan(
            self.run_gate("parameters:\n\tlevel: 6\n"),
            "설정은 있으나 캐시를 옮기지 않는 프로젝트는 실행돼야 한다",
        )

    def test_no_config_at_all_runs(self) -> None:
        self.assertRan(self.run_gate(None), "설정이 없으면 기본값이므로 안전하다")

    def test_a_relative_tmpdir_blocks_the_run(self) -> None:
        """상대 경로는 설정 파일 디렉터리 기준으로 풀려 저장소 안에 떨어진다."""
        self.assertSkipped(
            self.run_gate("parameters:\n\ttmpDir: .phpstan-cache\n"),
            "상대 tmpDir 이 실행을 막지 못했다",
        )

    def test_a_result_cache_path_inside_the_repo_blocks_the_run(self) -> None:
        """`resultCachePath` 는 `tmpDir` 과 독립이다 — 한쪽만 보면 그대로 샌다."""
        self.assertSkipped(
            self.run_gate("parameters:\n\tresultCachePath: build/rc.php\n"),
            "resultCachePath 가 실행을 막지 못했다",
        )

    def test_a_grandparent_include_that_moves_the_cache_blocks_the_run(self) -> None:
        """한 단계만 따라가면 조부모 설정이 그대로 통과한다.

        `phpstan.neon` → `parent.neon` → `grand.neon` 에서 마지막이 `tmpDir` 을 저장소 안으로
        옮기면, 실제 PHPStan 은 그 값을 쓰고 캐시를 저장소에 남긴다.
        """
        self.assertSkipped(
            self.run_gate(
                "includes:\n\t- parent.neon\n",
                extra={
                    "parent.neon": "includes:\n\t- grand.neon\n",
                    "grand.neon": "parameters:\n\ttmpDir: .phpstan-cache\n",
                },
            ),
            "중첩 include 가 게이트를 우회했다",
        )

    def test_an_unreadable_include_blocks_the_run(self) -> None:
        """읽지 못한 include 를 조용히 버리면 판정 불가를 안전으로 처리하는 것이다."""
        self.assertSkipped(
            self.run_gate(
                "includes:\n\t- parent.neon\n",
                extra={"parent.neon": "parameters:\n\tlevel: 6\n"},
                unreadable=("parent.neon",),
            ),
            "읽을 수 없는 include 를 안전으로 처리했다",
        )

    def test_a_cache_path_at_the_repository_root_blocks_the_run(self) -> None:
        """`$PWD` 정확히 일치도 저장소 안이다 — `$PWD/*` 만 보면 루트 지정이 새어 나간다."""
        self.assertSkipped(
            self.run_gate("parameters:\n\ttmpDir: .\n"),
            "저장소 루트를 캐시 위치로 지정한 설정이 통과했다",
        )

    def test_a_self_including_config_terminates_and_is_judged(self) -> None:
        """경로 별칭(`./x` vs `x`)을 정규화하지 않으면 방문 검사를 우회해 무한 재귀한다."""
        self.assertSkipped(
            self.run_gate("includes:\n\t- ./phpstan.neon\nparameters:\n\ttmpDir: .cache\n"),
            "자기 include 순환에서 캐시 설정을 판정하지 못했다",
        )

    def test_a_path_containing_spaces_does_not_false_positive(self) -> None:
        """공백 구분 누적은 `C:\\Users\\First Last\\...` 같은 경로를 조각내 전부 unresolvable 로 만든다.

        fail-closed 라 저장소를 쓰지는 않지만, 안전한 프로젝트의 정적 분석이 통째로 사라진다.
        이 저장소는 Windows 네이티브 설치를 지원하므로 흔한 경로다.
        """
        self.assertRan(
            self.run_gate("parameters:\n\tlevel: 6\n", subdir="First Last/proj"),
            "공백이 든 경로에서 안전한 설정이 건너뛰어졌다",
        )
        self.assertSkipped(
            self.run_gate("parameters:\n\ttmpDir: .cache\n", subdir="First Last/proj"),
            "공백이 든 경로에서 위험한 설정이 통과했다",
        )

    def test_an_unreadable_config_blocks_the_run(self) -> None:
        """판정할 수 없으면 안전이 아니다 — 읽지 못한 설정이야말로 쓰기가 놀라움이 된다."""
        self.assertSkipped(
            self.run_gate("x\n", readable=False),
            "읽을 수 없는 설정을 안전으로 처리했다",
        )


class PhpStanInlineCacheGateTest(PhpStanReadOnlyGateTest):
    """캐시 게이트도 NEON inline 표기를 봐야 한다 — 읽기 전용 계약이 걸린 자리다.

    실행 게이트와 달리 이것은 **일상 경로**에서 돈다. 그래서 "설정이 있으면 무조건 skip"
    으로 갈 수 없고, inline 표기까지 값을 읽어 판정해야 한다.
    """

    SKIP_MARKER = "skipped-read-only"

    def test_inline_tmpdir_is_caught(self) -> None:
        """`parameters: {tmpDir: .cache}` 는 유효하고, 줄머리 grep 은 못 잡는다."""
        output = self.run_gate(
            "parameters: {level: 0, paths: [src], tmpDir: .cache}\n",
            extra={"src/A.php": "<?php class A {}"},
        )
        self.assertIn(self.SKIP_MARKER, output, "inline tmpDir 을 놓쳤다")
        self.assertNotIn(self.ANALYSIS_MARKER, output)

    def test_inline_result_cache_path_is_caught(self) -> None:
        output = self.run_gate(
            "parameters: {level: 0, paths: [src], resultCachePath: .rc/cache.php}\n",
            extra={"src/A.php": "<?php class A {}"},
        )
        self.assertIn(self.SKIP_MARKER, output)
        self.assertNotIn(self.ANALYSIS_MARKER, output)

    def test_a_cache_path_outside_the_repository_still_runs(self) -> None:
        """저장소 밖을 가리키면 안전하다 — 전부 막으면 일상 리뷰가 망가진다."""
        output = self.run_gate(
            "parameters: {level: 0, paths: [src], tmpDir: /tmp/phpstan-cache}\n",
            extra={"src/A.php": "<?php class A {}"},
        )
        self.assertIn(self.ANALYSIS_MARKER, output, "저장소 밖 캐시인데 막았다")
        self.assertNotIn(self.SKIP_MARKER, output)

    def test_an_escaped_config_cannot_be_judged_from_text(self) -> None:
        r"""`\uXXXX` 는 원문에 없는 값을 만든다 — 판정 불가는 안전이 아니다."""
        output = self.run_gate(
            '{"parameters":{"level":0,"paths":["src"],"tmpDir":"\\u002ecache"}}\n',
            extra={"src/A.php": "<?php class A {}"},
        )
        self.assertIn(self.SKIP_MARKER, output, "이스케이프된 설정을 안전으로 봤다")
        self.assertNotIn(self.ANALYSIS_MARKER, output)


class PhpStanTrustGateTest(PhpStanReadOnlyGateTest):
    """신뢰 경계 게이트도 **실행해서** 검증한다.

    문자열로는 "게이트가 문서에 있다"까지만 안다. 이 게이트는 두 번 순서가 틀렸었다 —
    체인 정의 앞에 놓여 빈 체인으로 통과했고, 고친다며 분석 뒤로 옮겨 이미 실행된 뒤에
    확인했다. 실행 테스트라야 그 둘을 다 잡는다.
    """

    SKIP_MARKER = "skipped-untrusted-execution"

    def test_a_trusted_branch_runs_the_analysis_unchanged(self) -> None:
        """PHP 무회귀의 핵심 — 평소 리뷰에서 이 게이트는 아무것도 바꾸지 않는다."""
        output = self.run_gate(
            "parameters:\n    level: 0\n    paths:\n        - src\n",
            extra={"src/A.php": "<?php class A {}"},
        )
        self.assertIn(self.ANALYSIS_MARKER, output, "신뢰 브랜치에서 분석이 실행되지 않았다")
        self.assertNotIn(self.SKIP_MARKER, output)

    def test_bootstrap_files_block_the_run_on_an_untrusted_diff(self) -> None:
        output = self.run_gate(
            "parameters:\n    level: 0\n    paths:\n        - src\n"
            "    bootstrapFiles:\n        - boot.php\n",
            extra={"src/A.php": "<?php class A {}", "boot.php": "<?php"},
            env={"UNTRUSTED_DIFF": "1"},
        )
        self.assertIn(self.SKIP_MARKER, output, "실행 위험이 있는데 분석이 막히지 않았다")
        self.assertNotIn(self.ANALYSIS_MARKER, output, "게이트가 판정 후에도 분석을 실행했다")

    def test_a_nested_include_is_caught_too(self) -> None:
        """루트 설정만 보면 통과한다 — 체인을 실제로 따라가는지 확인한다."""
        output = self.run_gate(
            "includes:\n    - inner.neon\nparameters:\n    level: 0\n    paths:\n        - src\n",
            extra={
                "src/A.php": "<?php class A {}",
                "inner.neon": "parameters:\n    rules:\n        - App\\MyRule\n",
            },
            env={"UNTRUSTED_DIFF": "1"},
        )
        self.assertIn(self.SKIP_MARKER, output, "include 안의 rules 를 놓쳤다")
        self.assertNotIn(self.ANALYSIS_MARKER, output)

    def test_a_php_include_is_caught(self) -> None:
        output = self.run_gate(
            "includes:\n    - dynamic.php\nparameters:\n    level: 0\n    paths:\n        - src\n",
            extra={"src/A.php": "<?php class A {}", "dynamic.php": "<?php return [];"},
            env={"UNTRUSTED_DIFF": "1"},
        )
        self.assertIn("executable-config", output, "`.php` include 를 실행 위험으로 보지 않았다")
        self.assertNotIn(self.ANALYSIS_MARKER, output)

    def test_a_legacy_autoload_parameter_is_caught(self) -> None:
        """구버전을 고정한 프로젝트에서는 옛 파라미터가 실제로 파일을 로드했다."""
        output = self.run_gate(
            "parameters:\n    level: 0\n    paths:\n        - src\n"
            "    autoload_files:\n        - side.php\n",
            extra={"src/A.php": "<?php class A {}", "side.php": "<?php"},
            env={"UNTRUSTED_DIFF": "1"},
        )
        self.assertIn("legacy-autoload", output)
        self.assertNotIn(self.ANALYSIS_MARKER, output)

    def test_inline_neon_notation_does_not_slip_past(self) -> None:
        """`includes: [danger.php]` 는 유효한 NEON 이고 실제로 실행된다 — 줄 기반 검사는 못 잡는다."""
        output = self.run_gate(
            "includes: [danger.php]\nparameters:\n    level: 0\n    paths:\n        - src\n",
            extra={"src/A.php": "<?php class A {}", "danger.php": "<?php return [];"},
            env={"UNTRUSTED_DIFF": "1"},
        )
        self.assertIn(self.SKIP_MARKER, output, "inline sequence 표기를 놓쳤다")
        self.assertNotIn(self.ANALYSIS_MARKER, output)

    def test_json_notation_does_not_slip_past(self) -> None:
        """NEON 은 JSON 상위집합이다 — 전체를 JSON 으로 쓴 설정도 유효하고 실행된다.

        `.php` 참조 검사만으로도 이 표본은 걸린다. 그래서 **어떤 검사가 잡았는지**까지
        고정한다 — 그러지 않으면 `bootstrapFiles` 검사를 줄머리 앵커로 되돌려도 통과한다.
        """
        output = self.run_gate(
            '{"parameters":{"level":0,"paths":["src"],"bootstrapFiles":["boot.php"]}}\n',
            extra={"src/A.php": "<?php class A {}", "boot.php": "<?php"},
            env={"UNTRUSTED_DIFF": "1"},
        )
        self.assertIn(self.SKIP_MARKER, output, "JSON 표기를 놓쳤다")
        self.assertNotIn(self.ANALYSIS_MARKER, output)
        self.assertIn(
            "config-loads-code", output,
            "`bootstrapFiles` 자체를 잡지 못하고 `.php` 참조로만 걸렸다",
        )

    def test_each_gate_check_stands_on_its_own(self) -> None:
        """검사들이 서로를 가리면 하나가 약해져도 드러나지 않는다.

        `.php` 확장자가 없는 이름으로 표본을 만들어, `bootstrapFiles` 검사 단독으로
        걸리는지 본다.
        """
        output = self.run_gate(
            "parameters: {level: 0, paths: [src], bootstrapFiles: [boot]}\n",
            extra={"src/A.php": "<?php class A {}", "boot": "<?php"},
            env={"UNTRUSTED_DIFF": "1"},
        )
        self.assertIn("config-loads-code", output, "`bootstrapFiles` 단독 검사가 동작하지 않는다")
        self.assertNotIn(self.ANALYSIS_MARKER, output)

    def test_inline_map_notation_does_not_slip_past(self) -> None:
        output = self.run_gate(
            "parameters: {level: 0, paths: [src], bootstrapFiles: [boot.php]}\n",
            extra={"src/A.php": "<?php class A {}", "boot.php": "<?php"},
            env={"UNTRUSTED_DIFF": "1"},
        )
        self.assertIn(self.SKIP_MARKER, output, "inline map 표기를 놓쳤다")
        self.assertNotIn(self.ANALYSIS_MARKER, output)

    def test_a_config_at_all_stops_an_untrusted_run(self) -> None:
        r"""텍스트 스캔으로는 fail-closed 를 만들 수 없다 — 설정이 있으면 멈춘다.

        inline `includes:` 대상은 체인이 수집하지 못하고, `\uXXXX` 이스케이프는 원문에
        없는 `.php` 를 복원한다. 무해한 설정도 많지만 그걸 증명하려면 진짜 NEON 파서로
        include 그래프 전체를 봐야 한다.
        """
        output = self.run_gate(
            "parameters:\n    level: 0\n    paths:\n        - src\n",
            extra={"src/A.php": "<?php class A {}"},
            env={"UNTRUSTED_DIFF": "1"},
        )
        self.assertIn(self.SKIP_MARKER, output, "설정이 있는데 분석이 실행됐다")
        self.assertIn("config-present", output, "차단 사유가 보고되지 않았다")
        self.assertNotIn(self.ANALYSIS_MARKER, output)

    def test_a_project_without_any_config_still_analyses(self) -> None:
        """전부 막으면 아무도 안 쓴다 — 설정이 없으면 실행 경로가 없으므로 분석한다."""
        output = self.run_gate(
            None,
            extra={"src/A.php": "<?php class A {}"},
            env={"UNTRUSTED_DIFF": "1"},
        )
        self.assertIn(self.ANALYSIS_MARKER, output, "설정이 없는데도 막았다")
        self.assertNotIn(self.SKIP_MARKER, output)

    def test_an_inline_include_target_cannot_slip_through(self) -> None:
        """`includes: [inner.neon]` 의 대상은 체인이 수집하지 못한다 — 코덱스가 든 반례다."""
        output = self.run_gate(
            "includes: [inner.neon]\n",
            extra={
                "src/A.php": "<?php class A {}",
                "inner.neon": "parameters: {level: 0, paths: [src], bootstrapFiles: [boot]}\n",
                "boot": "<?php",
            },
            env={"UNTRUSTED_DIFF": "1"},
        )
        self.assertIn(self.SKIP_MARKER, output, "inline include 체인이 통과했다")
        self.assertNotIn(self.ANALYSIS_MARKER, output)

    def test_a_unicode_escape_cannot_hide_a_php_reference(self) -> None:
        r"""`danger\u002ephp` 는 파서가 `danger.php` 로 복원한다 — 원문에는 `.php` 가 없다."""
        output = self.run_gate(
            '{"includes":["danger\\u002ephp"],"parameters":{"level":0,"paths":["src"]}}\n',
            extra={"src/A.php": "<?php class A {}", "danger.php": "<?php return [];"},
            env={"UNTRUSTED_DIFF": "1"},
        )
        self.assertIn(self.SKIP_MARKER, output, "이스케이프된 참조가 통과했다")
        self.assertNotIn(self.ANALYSIS_MARKER, output)


class PhpSecurityBaseline(unittest.TestCase):
    """7 · 8 — 보안 규칙의 실효 범위와 로딩 경로가 유지된다."""

    def php_security_reference(self) -> str:
        return read("skills/web-security-review/references/php-backend-security.md")

    def test_each_named_category_keeps_its_must_rules(self) -> None:
        """GREEN — 범주 제목만 남고 규칙 본문이 빠지는 손실을 잡는다.

        분할·이관 과정에서 제목은 옮기기 쉽고 본문은 빠뜨리기 쉽다. 각 절이 실제로
        `### MUST` 블록과 규칙 줄을 갖고 있는지 확인한다.
        """
        reference = self.php_security_reference()
        titles = list(PHP_SECURITY_SEVERITY)
        for index, title in enumerate(titles):
            following = titles[index + 1] if index + 1 < len(titles) else "10. Miscellaneous"
            with self.subTest(category=title):
                section = between(
                    reference, f"## {title}", f"## {following}", label=title
                )
                self.assertIn("### MUST", section)
                rules = [
                    line for line in section.splitlines()
                    if line.strip().startswith("- MUST")
                ]
                self.assertTrue(rules, f"{title} 에 MUST 규칙이 하나도 없다")

    def test_php_security_severity_semantics_are_pinned(self) -> None:
        """GREEN — 같은 `MUST` 문법에 서로 다른 심각도가 붙는다.

        개수가 아니라 **절별 매핑**을 고정한다. SQL 주입은 Critical, 입력 검증은
        Medium–High, 오류 처리는 Medium이다. 이것이 "규칙 위반 = 자동 High" 같은
        문법 기반 승격을 금지하는 근거이므로, 값이 평준화되면 그 근거가 사라진다.
        """
        reference = self.php_security_reference()
        titles = list(PHP_SECURITY_SEVERITY)
        for index, (title, severity) in enumerate(PHP_SECURITY_SEVERITY.items()):
            following = titles[index + 1] if index + 1 < len(titles) else "10. Miscellaneous"
            with self.subTest(category=title):
                section = between(
                    reference, f"## {title}", f"## {following}", label=title
                )
                declared = re.search(
                    r"\*\*Severity if violated\*\*: (.+)", section
                )
                self.assertIsNotNone(declared, f"{title} 에 심각도 선언이 없다")
                self.assertTrue(
                    declared.group(1).startswith(severity),
                    f"{title}: {severity!r} 를 기대했으나 {declared.group(1)!r}",
                )

        for subcategory in PHP_SECURITY_SUBCATEGORIES:
            with self.subTest(subcategory=subcategory):
                self.assertIn(subcategory, reference)

    def test_php_security_reference_is_loaded_from_both_review_paths(self) -> None:
        """GREEN — 파일을 안 바꿔도 로딩 경로가 끊기면 PHP 보안 검토가 사라진다.

        파일명이 파일 어딘가에 등장하는지가 아니라 **로드 지시 안에** 있는지를 본다.
        설명이나 비활성 템플릿에 이름만 남고 실제 선택에서 빠지는 회귀를 잡기 위함이다.
        """
        # 4단계에서 참조가 언어×표면 2차원으로 재구성됐다. 탐색 지점은 바뀌어도 요구는 같다 —
        # **PHP 변경이 이 참조를 로드하는가.** 참조 표와 선택 표 양쪽에 있어야 한다.
        skill = read("skills/web-security-review/SKILL.md")
        reference_table = between(
            skill, "| Axis | File | Covers |", "### Selecting references from the surface",
            label="참조 표",
        )
        self.assertIn("`references/php-backend-security.md`", reference_table)

        selection = between(
            skill, "| Change | Language axis | Surface axis |",
            "**`php-backend-security.md` already covers",
            label="참조 선택 표",
        )
        php_rows = [line for line in selection.splitlines() if line.startswith("| PHP ")]
        self.assertTrue(php_rows, "선택 표에 PHP 행이 없다")
        for row in php_rows:
            with self.subTest(row=row[:40]):
                self.assertIn("php-backend-security.md", row,
                              "PHP 변경이 언어 축 참조를 로드하지 않는다")
                # **부정 조건**: PHP 파일이 이미 HTTP 표면을 담고 있으므로 함께 로드하면
                # 같은 findings 를 두 번 낸다. 현재 동작만 확인하면 이 회귀를 놓친다.
                self.assertNotIn(
                    "http-server-security.md", row,
                    "PHP 행이 http-server 표면 참조를 함께 로드한다 — 이중 보고가 된다",
                )
        # PHP 파일이 HTTP 표면을 겸한다는 예외가 **글로도** 있어야 한다. 표만 맞고 규칙이
        # 없으면 다음 사람이 표를 늘릴 때 근거 없이 http-server 를 붙인다.
        self.assertRegex(
            " ".join(skill.split()),
            r"never pair (?:it|`php-backend-security\.md`) with[^.]{0,60}http-server-security",
            "PHP 를 http-server 표면과 함께 로드하지 말라는 규칙이 없다",
        )

        dispatched = between(
            read("skills/branch-merge-review/references/reviewer-prompts.md"),
            "**Skill to use**: Invoke `web-security-review`",
            "**Scope**",
            label="보안 리뷰어 로드 지시",
        )
        self.assertIn("references/php-backend-security.md", dispatched)


ALL_SURFACES = ("http-server-security.md", "browser-security.md", "native-security.md")


class SecurityReferenceSelectionTest(unittest.TestCase):
    """4단계 — 언어×표면 참조 선택이 실제로 지시대로인지 고정한다.

    이 표는 "어떤 파일을 읽는가"를 정하므로, 한 행이 틀리면 그 조합의 검토가 통째로 빠지거나
    같은 findings 를 두 번 낸다. 현재 동작만 확인하는 검사로는 둘 다 놓친다.
    """

    def skill(self) -> str:
        return read("skills/web-security-review/SKILL.md")

    def selection_rows(self) -> dict[str, str]:
        table = between(
            self.skill(),
            "| Change | Language axis | Surface axis |",
            "**`php-backend-security.md` already covers",
            label="참조 선택 표",
        )
        rows = {}
        for line in table.splitlines():
            if line.startswith("|") and line.count("|") >= 4 and "---" not in line:
                label = line.split("|")[1].strip()
                if label and label != "Change":
                    rows[label] = line
        return rows

    def test_every_node_row_loads_the_language_axis(self) -> None:
        """언어 축은 항상 로드된다 — 매니페스트·lockfile 의 공급망 findings 가 거기 있다."""
        for label, row in self.selection_rows().items():
            if not label.startswith("Node"):
                continue
            with self.subTest(row=label):
                self.assertIn(
                    "node-security.md", row,
                    f"{label} 행이 언어 축을 로드하지 않는다",
                )

    #: 행 이름이 아니라 **선택된 참조 집합**을 고정한다. 이름만 검사하면 SSR 행이 HTTP 표면을
    #: 빠뜨려도 통과한다 — 실제로 그 오류가 이 방식으로 숨어 있었다.
    ALL_SURFACES = ("http-server-security.md", "browser-security.md", "native-security.md")

    #: 행 이름이 아니라 **선택된 참조 집합 전체**를 고정한다. `assertIn` 만 쓰면 한 행이
    #: 표면을 전부 잃어도 통과한다 — 실제로 그 구멍으로 SSR 오류가 숨어 있었다.
    #: **행 레이블 전문**을 키로 쓴다. prefix 로 두면 새 행이 기존 등록에 흡수돼
    #: 검사 없이 통과한다 — `Node service + CLI` 가 `Node service + CLI + UI` 를 먹었다.
    REQUIRED_SELECTIONS = {
        "PHP server-rendered app": {"php-backend-security.md", "browser-security.md"},
        "PHP API, no HTML": {"php-backend-security.md"},
        "Node HTTP service": {"node-security.md", "http-server-security.md"},
        "Node CLI or daemon": {"node-security.md", "native-security.md"},
        "Node library with no surface evidence": {"node-security.md", *ALL_SURFACES},
        "Node service + CLI": {
            "node-security.md", "http-server-security.md", "native-security.md",
        },
        "Node static build (bundler, prerender)": {
            "node-security.md", "browser-security.md", "native-security.md",
        },
        "Node runtime SSR": {
            "node-security.md", "http-server-security.md", "browser-security.md",
        },
        "Node service that also serves a UI": {
            "node-security.md", "http-server-security.md", "browser-security.md",
        },
        "Node service + CLI + UI": {"node-security.md", *ALL_SURFACES},
        "Python HTTP service (Django, FastAPI, Flask)": {
            "python-security.md", "http-server-security.md",
        },
        "Python server-rendered app (templates)": {
            "python-security.md", "http-server-security.md", "browser-security.md",
        },
        "Python CLI, job, or daemon": {"python-security.md", "native-security.md"},
        "Python library with no surface evidence": {"python-security.md", *ALL_SURFACES},
        "Go HTTP service": {"go-security.md", "http-server-security.md"},
        "Go server-rendered app (html/template)": {
            "go-security.md", "http-server-security.md", "browser-security.md",
        },
        "Go CLI or daemon": {"go-security.md", "native-security.md"},
        "Go library with no surface evidence": {"go-security.md", *ALL_SURFACES},
        "Rust HTTP service": {"rust-security.md", "http-server-security.md"},
        "Rust CLI or daemon": {"rust-security.md", "native-security.md"},
        "Rust library with no surface evidence": {"rust-security.md", *ALL_SURFACES},
        "Browser assets only, no manifest change": {"browser-security.md"},
    }

    #: "all three" 같은 축약이 어떤 파일들을 뜻하는지. 표에서 축약이 사라지면 그냥 파일명이
    #: 읽히므로 이 매핑이 없어도 검사는 성립한다.
    SHORTHAND = {"all three": ALL_SURFACES}

    def referenced_files(self, row: str) -> set:
        found = {
            name for name in (
                "php-backend-security.md", "node-security.md", "python-security.md",
                "go-security.md", "rust-security.md", *ALL_SURFACES,
            ) if name in row
        }
        for phrase, expansion in self.SHORTHAND.items():
            if phrase in row:
                found.update(expansion)
        return found

    def test_no_selection_row_escapes_the_required_set(self) -> None:
        """등록된 행만 검사하면 새 언어를 추가할 때 그 행이 검사 없이 통과한다.

        실제로 Python 4행이 그렇게 빠져 있었다. 표에 행을 추가하면 여기에도 추가해야 한다.
        """
        self.assertEqual(
            set(self.selection_rows()), set(self.REQUIRED_SELECTIONS),
            "선택 표의 행 집합과 등록된 집합이 정확히 일치해야 한다 — "
            "행을 추가하면 REQUIRED_SELECTIONS 에도 추가해야 검사된다",
        )

    def test_each_row_selects_exactly_the_right_reference_set(self) -> None:
        rows = self.selection_rows()
        for label, required in self.REQUIRED_SELECTIONS.items():
            with self.subTest(row=label):
                self.assertIn(label, rows, f"행이 없다 / 있는 행: {list(rows)}")
                self.assertEqual(
                    self.referenced_files(rows[label]), required,
                    f"{label} 의 참조 집합이 기대와 다르다: {rows[label].strip()}",
                )

    def test_ambiguous_surface_dispatch_names_the_security_references(self) -> None:
        """표면 불명 시 품질 dispatch 만 정하고 보안 참조를 비워 두면 두 스킬이 모순된다."""
        section = between(
            read("skills/branch-merge-review/SKILL.md"),
            "When the surface is ambiguous",
            "If no files match a category",
            label="ambiguous dispatch",
        )
        for reference in (
            "http-server-security.md", "browser-security.md", "native-security.md",
        ):
            with self.subTest(reference=reference):
                self.assertIn(reference, section)

    def test_runtime_ssr_is_separated_from_a_static_build(self) -> None:
        """런타임 SSR 은 HTTP 서버다 — 정적 번들과 한 행으로 묶으면 인증·세션·CSRF 가 빠진다."""
        rows = self.selection_rows()
        ssr = [row for label, row in rows.items() if "SSR" in label]
        self.assertTrue(ssr, f"SSR 행이 없다: {list(rows)}")
        for row in ssr:
            with self.subTest(row=row[:40]):
                self.assertIn(
                    "http-server-security.md", row,
                    "런타임 SSR 행이 HTTP 표면 참조를 로드하지 않는다",
                )

    def test_the_only_row_without_a_language_axis_is_narrow(self) -> None:
        """언어 축이 없는 행은 하나뿐이어야 하고, 매니페스트가 diff 에 들어오면 사라져야 한다."""
        rows = self.selection_rows()
        without = [
            label for label, row in rows.items()
            if "security.md" not in row.split("|")[2]
        ]
        self.assertEqual(
            without, ["Browser assets only, no manifest change"],
            f"언어 축 없는 행이 예상과 다르다: {without}",
        )
        self.assertRegex(
            " ".join(self.skill().split()),
            r"the moment a `package\.json`, lockfile, or build script is in the diff",
            "매니페스트가 들어오면 언어 축이 돌아온다는 단서가 없다",
        )

    def test_no_reference_selection_says_both_files(self) -> None:
        """"both reference files" 는 2차원 이전의 표현이다 — 남으면 세 개짜리 조합이 둘로 준다."""
        for path in (
            "skills/web-security-review/SKILL.md",
            "skills/branch-merge-review/references/reviewer-prompts.md",
        ):
            with self.subTest(path=path):
                self.assertNotRegex(
                    read(path), r"both reference files|Load both reference",
                    "참조 선택이 두 파일로 고정된 표현이 남아 있다",
                )

    def test_a_library_without_surface_evidence_is_ambiguous(self) -> None:
        """소비자가 표면을 정하는데 소비자는 이 diff 에 없다 — 기본값을 주면 틀린다."""
        skill = " ".join(read("skills/branch-merge-review/SKILL.md").split())
        self.assertRegex(
            skill,
            r"library[^.]{0,80}no surface evidence|Do not default it to `native`",
            "표면 증거가 없는 라이브러리를 native 로 기본 분류하고 있다",
        )

    def test_php_can_carry_the_browser_surface(self) -> None:
        """서버 렌더링 PHP 는 브라우저 표면을 갖는다 — JS/TS 만 표면 판정이라고 쓰면 빠진다."""
        skill = " ".join(read("skills/branch-merge-review/SKILL.md").split())
        self.assertRegex(
            skill,
            r"Surfaces are still assigned to every language|PHP app that emits HTML",
            "PHP 의 브라우저 표면 판정 경로가 없다",
        )


class NodeSecuritySemanticsTest(unittest.TestCase):
    """4단계에서 고친 Node 보안 기술 주장을 고정한다.

    보안 참조의 틀린 설명은 품질 참조보다 위험하다 — 리뷰어가 안전한 코드를 취약하다고
    보고하거나, 더 나쁘게는 취약한 코드를 안전하다고 넘긴다.
    """

    def reference(self) -> str:
        return read("skills/web-security-review/references/node-security.md")

    def test_buffer_deprecation_rationale_is_type_confusion_not_uninitialised_memory(self) -> None:
        """`Buffer(size)` 는 Node 8부터 zero-fill 이다 — v24 실측으로도 전부 0이었다.

        미초기화 메모리를 반환하는 것은 `Buffer.allocUnsafe` 다. 근거를 틀리게 쓰면 리뷰어가
        존재하지 않는 정보 유출을 보고한다.
        """
        section = self.reference()
        self.assertRegex(section, r"zero-filled since Node 8|Node 8부터")
        self.assertIn("Buffer.allocUnsafe", section)
        self.assertNotRegex(
            section,
            r"`Buffer\(size\)`[^.]{0,60}allocates uninitialised memory",
            "틀린 근거가 되살아났다",
        )

    def test_batbadbut_states_the_patch_status_and_both_cves(self) -> None:
        """버전 범위 없이 CVE 를 쓰면 패치된 런타임에서도 findings 가 나간다."""
        section = self.reference()
        for token in ("CVE-2024-27980", "CVE-2024-36138"):
            with self.subTest(cve=token):
                self.assertIn(token, section)
        self.assertRegex(
            section, r"Both are patched|patched",
            "현재 런타임에서 패치됐다는 사실이 없으면 항상 findings 가 된다",
        )
        self.assertRegex(section, r"establish which runtime|runtime version")

    def test_argument_array_is_not_presented_as_sufficient(self) -> None:
        """배열은 셸 파싱만 막는다 — 대상 프로그램의 옵션 인젝션은 남는다."""
        section = self.reference()
        self.assertRegex(
            section, r"not the end of the check|does not stop the \*target program\*",
        )
        self.assertIn("'--'", section)

    def test_path_containment_requires_realpath(self) -> None:
        """`resolve` + `startsWith` 는 lexical 이라 symlink 탈출을 못 막는다."""
        section = self.reference()
        self.assertIn("realpath", section)
        self.assertRegex(section, r"lexical only|symlink or a Windows junction")
        # `path` 는 URL 디코딩하지 않으므로 `%2f` 예제는 순회를 만들지 않는다.
        self.assertRegex(section, r"does \*\*not\*\* URL-decode|not URL-decode")

    def test_path_containment_canonicalises_both_sides(self) -> None:
        """ROOT 가 symlink 면 한쪽만 realpath 한 비교는 정상 경로를 거부한다 (v24.18.0 재현)."""
        section = self.reference()
        good = between(section, "// GOOD — canonicalise", "```", label="path GOOD 패턴")
        self.assertIn("realpath(ROOT)", good.replace(" ", ""),
                      "ROOT 자체를 canonicalise 하지 않는다")
        self.assertNotRegex(
            good, r"startsWith\(ROOT \+ path\.sep\)",
            "raw ROOT 문자열과 비교하는 형태가 남아 있다",
        )

    def test_lifecycle_audit_separates_dependencies_from_this_repository(self) -> None:
        """설치된 의존성이 도는 훅과 이 저장소가 도는 훅은 범위도 담당자도 다르다."""
        section = self.reference()
        audit = between(section, "### Audit", "## 6.", label="공급망 audit")
        self.assertIn("node_modules/**/package.json", audit)
        self.assertIn("--glob '!node_modules'", audit)
        self.assertIn("prepublishOnly", audit)

    def test_batbadbut_gives_the_patch_boundary(self) -> None:
        """"패치됐다"만 쓰고 버전을 안 주면 판정할 수 없다 — 리뷰어가 매번 findings 를 낸다."""
        section = self.reference()
        for version in ("18.20.4", "20.15.1", "22.4.1"):
            with self.subTest(version=version):
                self.assertIn(version, section)

    def test_lifecycle_audit_covers_more_than_install_hooks(self) -> None:
        """`prepare`·`prepublish` 계열도 설치 중 실행된다 — install 3종만 보면 놓친다."""
        section = self.reference()
        for hook in ("prepare", "prepublish", "preprepare", "postprepare"):
            with self.subTest(hook=hook):
                self.assertIn(hook, section)

    def test_permission_flag_is_the_stable_one(self) -> None:
        """`--experimental-permission` 은 옛 이름이다 — 22.13/23.5 부터 `--permission`."""
        section = self.reference()
        self.assertRegex(section, r"`--permission`")
        self.assertRegex(section, r"22\.13|23\.5", "안정화 버전이 명시되지 않았다")

    def test_supply_chain_audit_does_not_conclude_from_omit_dev(self) -> None:
        """`--omit=dev` 는 우선순위용이다 — dev 의존성도 개발자 머신과 CI 에서 실행된다."""
        section = self.reference()
        self.assertRegex(section, r"prioritise, not to conclude|우선순위")
        # scoped·중첩 패키지를 놓치는 glob 이 되살아나면 안 된다.
        self.assertNotRegex(
            section, r"node_modules/\*/package\.json' \| head",
            "scoped·중첩 의존성을 놓치는 감사 명령이 되살아났다",
        )


class TypeScriptReadOnlyRuleTest(unittest.TestCase):
    """`tsc --noEmit` 의 3분기 규칙을 **실측**으로 고정한다.

    문서가 "읽기 전용에서 안전하다"고 말하는 형태가 실제로 파일을 쓰지 않는지, 그리고
    "안전한 형태가 없다"고 말하는 형태가 실제로 파일을 남기는지는 문자열 검사로는 알 수 없다.
    TypeScript 가 없는 환경에서는 skip 한다 — 저장소에 node_modules 를 두지 않기 위해서다.
    """

    BASE = '{"compilerOptions":{"target":"ES2022","strict":true%s},"include":["src"]}'

    @classmethod
    def setUpClass(cls) -> None:
        local = Path("node_modules/.bin/tsc")
        cls.tsc = [str(local.resolve())] if local.exists() else None
        if cls.tsc is None and shutil.which("tsc"):
            cls.tsc = [shutil.which("tsc")]
        if cls.tsc is None and shutil.which("npx"):
            probe = subprocess.run(
                ["npx", "--no", "--", "tsc", "--version"],
                capture_output=True, text=True, timeout=180,
            )
            if probe.returncode == 0 and "Version" in probe.stdout:
                cls.tsc = ["npx", "--no", "--", "tsc"]
        if cls.tsc is None:
            raise unittest.SkipTest("tsc 없음 — 설치 없이 검증할 수 없다")

    def run_check(self, options: str, extra_args: list[str]) -> tuple[int, list[str]]:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            (root / "src" / "a.ts").write_text("export const x: number = 1;\n")
            (root / "tsconfig.json").write_text(self.BASE % options)
            before = {p.name for p in root.iterdir()}
            done = subprocess.run(
                [*self.tsc, "--noEmit", *extra_args],
                cwd=tmp, capture_output=True, text=True, timeout=300,
            )
            written = sorted({p.name for p in root.iterdir()} - before)
            return done.returncode, written

    def test_plain_noemit_writes_nothing(self) -> None:
        rc, written = self.run_check("", [])
        self.assertEqual(rc, 0)
        self.assertEqual(written, [], "옵션 없는 --noEmit 이 파일을 남겼다")

    def test_incremental_noemit_still_writes_buildinfo(self) -> None:
        """이 쓰기가 사실이기 때문에 `--incremental false` 규칙이 존재한다."""
        _, written = self.run_check(',"incremental":true', [])
        self.assertTrue(
            any(name.endswith(".tsbuildinfo") for name in written),
            "incremental 프로젝트에서 --noEmit 이 아무것도 안 썼다 — 규칙의 전제가 무너진다",
        )

    def test_incremental_false_is_the_read_only_safe_form(self) -> None:
        rc, written = self.run_check(',"incremental":true', ["--incremental", "false"])
        self.assertEqual(rc, 0, "읽기 전용 안전 형태가 실행에 실패했다")
        self.assertEqual(written, [], "--incremental false 가 파일을 남겼다")

    def test_composite_has_no_safe_form(self) -> None:
        """composite 는 회피 시도가 더 나쁘다 — 실패하면서 파일을 남긴다. 그래서 skip 이다."""
        rc, written = self.run_check(',"composite":true', ["--incremental", "false"])
        self.assertNotEqual(rc, 0, "composite + --incremental false 가 성공했다")
        self.assertTrue(
            any(name.endswith(".tsbuildinfo") for name in written),
            "실패 실행이 파일을 남기지 않았다면 문서의 경고 근거가 달라진다",
        )

    def test_the_document_tells_the_same_three_way_rule(self) -> None:
        reference = read("skills/code-quality-review/references/js-toolchain.md")
        self.assertIn("--incremental false", reference)
        self.assertIn("TS6379", reference)
        composite = between(
            reference, "`composite: true` is the one case", "So the rule is three-way",
            label="composite rule",
        )
        self.assertIn("skipped-read-only", composite)


class NodeSurfacePilotTest(unittest.TestCase):
    """Node 파일럿 완료 기준 1 — 표본이 오분류되지도, 누락되지도 않는지.

    표의 증거 항목을 **실제로 읽어** 표본 매니페스트와 대조한다. 표본에 필요한 증거가 표에서
    사라지면 그 표본은 어느 표면에도 걸리지 않고, 리뷰는 조용히 그 파일을 건너뛴다.
    """

    #: (표본 이름, package.json, 형제 파일들, 기대 표면)
    WORKSPACES = (
        ("Vite + Svelte 앱", {"devDependencies": {"vite": "^5", "svelte": "^4"}},
         ["App.svelte"], {"browser"}),
        ("Express 서비스", {"dependencies": {"express": "^4"}}, ["server.js"], {"http-server"}),
        ("bin 을 가진 CLI", {"bin": {"tool": "./cli.js"}}, ["cli.js"], {"native"}),
        ("서비스 + CLI 겸용", {"dependencies": {"fastify": "^4"}, "bin": {"t": "./c.js"}},
         ["c.js"], {"http-server", "native"}),
        ("browser 필드만 있는 패키지", {"browser": "./dist/b.js"}, ["b.js"], {"browser"}),
        ("표면 증거 없는 라이브러리", {"main": "./index.js"}, ["index.js"], set()),
    )

    #: 표의 증거 문구 → 표본 매니페스트에서 그 증거를 읽어내는 방법.
    #: 문구가 표에서 빠지면 EVIDENCE 조회가 실패하고 그 줄이 RED 가 된다.
    EVIDENCE = {
        "browser": (
            ("Vite", lambda m, f: "vite" in _deps(m)),
            ("webpack", lambda m, f: "webpack" in _deps(m)),
            ("`*.svelte`", lambda m, f: any(n.endswith(".svelte") for n in f)),
            ("a `browser` field", lambda m, f: "browser" in m),
        ),
        "http-server": (
            ("Express", lambda m, f: "express" in _deps(m)),
            ("Fastify", lambda m, f: "fastify" in _deps(m)),
        ),
        "native": (
            ("a `bin` entry", lambda m, f: "bin" in m),
        ),
    }

    def surface_table(self) -> str:
        return between(
            read("skills/branch-merge-review/SKILL.md"),
            "### Deciding the JS/TS surface",
            "A workspace can carry more than one surface",
            label="surface evidence table",
        )

    def test_every_sample_workspace_lands_on_its_surface(self) -> None:
        table = self.surface_table()
        for name, manifest, siblings, expected in self.WORKSPACES:
            with self.subTest(workspace=name):
                found = set()
                for surface, rules in self.EVIDENCE.items():
                    for phrase, matches in rules:
                        self.assertIn(
                            phrase, table,
                            f"증거 문구가 표에서 사라졌다: {phrase!r} ({surface})",
                        )
                        if matches(manifest, siblings):
                            found.add(surface)
                self.assertEqual(
                    found, expected,
                    f"{name}: 표의 증거로 {sorted(found)} 가 나왔다 (기대 {sorted(expected)})",
                )

    def test_a_library_with_no_evidence_is_not_silently_dropped(self) -> None:
        """증거가 하나도 없는 표본이야말로 규칙이 필요한 곳이다 — 건너뛰기는 답이 아니다."""
        skill = read("skills/branch-merge-review/SKILL.md")
        rule = between(
            skill, "A library with no `bin` entry", "### Deciding the JS/TS surface",
            label="ambiguous rule",
        )
        self.assertIn("ambiguous", rule)
        self.assertRegex(rule, r"[Dd]o\s+not\s+default it to `native`")

    def test_a_manifest_outranks_the_directory_name(self) -> None:
        """`server/` 밑의 브라우저 번들을 경로만 보고 HTTP 로 넘기면 CSP·XSS 검토가 빠진다."""
        skill = " ".join(read("skills/branch-merge-review/SKILL.md").split())
        self.assertRegex(skill, r"supporting evidence only.{0,40}manifest outranks")

    def test_the_workspace_is_the_unit_not_the_repository(self) -> None:
        skill = " ".join(read("skills/branch-merge-review/SKILL.md").split())
        self.assertRegex(skill, r"per workspace, not per repository")
        self.assertIn("nearest enclosing `package.json`", skill)


def _deps(manifest: dict) -> set:
    return {
        *manifest.get("dependencies", {}),
        *manifest.get("devDependencies", {}),
        *manifest.get("peerDependencies", {}),
    }


class PythonReferenceSemanticsTest(unittest.TestCase):
    """Python 참조의 **실측된 사실**을 고정한다. 문자열이 아니라 동작을 근거로 쓴 것들이다."""

    def quality(self) -> str:
        return read("skills/code-quality-review/references/python-quality.md")

    def security(self) -> str:
        return read("skills/web-security-review/references/python-security.md")

    def test_ruff_and_mypy_are_invoked_without_writing_a_cache(self) -> None:
        """두 도구 모두 기본값으로 프로젝트 루트에 캐시 디렉터리를 만든다 — 리뷰가 약속한 적 없는 파일이다."""
        commands = code_blocks(self.quality())
        for line in commands.splitlines():
            stripped = line.strip()
            if stripped.startswith("ruff check") and "--fix" not in stripped:
                with self.subTest(command=stripped):
                    self.assertIn("--no-cache", stripped, "ruff 가 .ruff_cache 를 남긴다")
            if stripped.startswith("mypy "):
                with self.subTest(command=stripped):
                    self.assertIn("--cache-dir", stripped, "mypy 가 .mypy_cache 를 남긴다")

    def test_the_mypy_trap_is_stated_not_assumed(self) -> None:
        """`--no-incremental` 은 이름과 달리 캐시 디렉터리를 여전히 만든다 (mypy 2.3.1 실측).

        TypeScript 의 `--incremental false` 와 반대라서, 습관으로 옮겨 쓰면 조용히 깨진다.
        """
        quality = " ".join(self.quality().split())
        self.assertRegex(
            quality,
            r"--no-incremental does not do what its name suggests|"
            r"`--no-incremental` does not do what its name suggests",
        )
        self.assertIn("js-toolchain.md", quality, "TypeScript 규칙과의 차이를 짚지 않는다")

    def test_uv_tool_install_takes_one_package(self) -> None:
        """`uv tool install ruff mypy` 는 uv 0.9.17 에서 거부된다 — 그대로 쓰면 설치가 실패한다."""
        for line in code_blocks(self.quality()).splitlines():
            stripped = line.strip()
            if stripped.startswith("uv tool install"):
                with self.subTest(command=stripped):
                    self.assertEqual(
                        len(stripped.split()), 4,
                        "uv tool install 은 패키지 하나만 받는다",
                    )

    def test_declared_tool_roles_all_have_an_install_path(self) -> None:
        """역할로 선언해 놓고 설치 방법이 없으면 그 역할은 영원히 skipped 다."""
        install = between(
            self.quality(), "## 3. Availability and Authority", "## 4. Execution",
            label="설치 절",
        )
        for tool in ("ruff", "mypy", "vulture", "radon"):
            with self.subTest(tool=tool):
                self.assertIn(tool, install)

    def test_mypy_uses_the_null_device_not_a_temp_dir(self) -> None:
        """무쓰기가 가능하면 그 형태를 쓴다 — 상위 계약이 그렇게 정해져 있다."""
        commands = code_blocks(self.quality())
        self.assertIn("--cache-dir=/dev/null", commands)
        self.assertIn("--cache-dir=nul", commands, "Windows 형태가 없다")

    def test_the_exception_example_states_the_hierarchy_correctly(self) -> None:
        """`except Exception` 은 KeyboardInterrupt/SystemExit 을 잡지 않는다 — bare except 가 잡는다."""
        quality = " ".join(self.quality().split())
        self.assertRegex(
            quality,
            r"`except Exception` does NOT catch those two; the bare form does",
        )
        self.assertRegex(quality, r"default 'except:' must be last",
                         "세 블록을 나눈 이유(SyntaxError)가 없다")

    def test_vulture_confidence_floors_are_explained(self) -> None:
        """80 을 기본값처럼 쓰면 미사용 함수(60%)가 전부 사라진다 — vulture 2.16 실측."""
        quality = " ".join(self.quality().split())
        self.assertRegex(quality, r"unused function scores 60%")
        self.assertRegex(quality, r"unused import 90%|an unused import 90%")

    def test_requirements_audit_states_its_trust_boundary(self) -> None:
        """requirements 감사는 `pip install -r` 과 같은 신뢰 경계다 — 리뷰 대상이 악의적일 수 있다."""
        security = " ".join(self.security().split())
        self.assertRegex(security, r"same trust boundary as `pip install -r`")
        self.assertIn("--no-deps --disable-pip", security, "경계를 좁히는 형태가 없다")

    def test_literal_eval_is_not_called_safe_for_untrusted_input(self) -> None:
        """코드를 실행하지 않는 것과 신뢰하지 않는 입력에 안전한 것은 다르다 (CPython 문서)."""
        security = " ".join(self.security().split())
        self.assertRegex(security, r"not RCE.{0,40}not as .{0,20}harmless")
        self.assertRegex(security, r"C-stack exhaustion|memory or C-stack")

    def test_template_injection_is_rated_critical(self) -> None:
        """Python 실행에 도달한다고 서술하면서 High 로 두면 영향 기반 원칙과 어긋난다."""
        security = " ".join(self.security().split())
        self.assertRegex(security, r"\*\*Critical\*\* for template injection")
        self.assertIn("SandboxedEnvironment", security, "완화 수단을 구분하지 않는다")

    def test_zipfile_and_tarfile_are_not_described_as_the_same(self) -> None:
        """zipfile 은 멤버 이름을 정화하고 tarfile 은 하지 않는다 (3.12.3 실측)."""
        security = " ".join(self.security().split())
        self.assertRegex(security, r"zipfile\.extractall` sanitises member names")
        self.assertRegex(security, r"OutsideDestinationError")
        self.assertIn('hasattr(tarfile, "data_filter")', security,
                      "백포트 때문에 버전 비교는 부정확하다는 점이 없다")

    def test_pip_audit_dry_run_is_marked_as_not_an_audit(self) -> None:
        """`--dry-run` 은 감사 없이 `No known vulnerabilities found` 를 출력한다 — 통과로 읽힌다."""
        security = " ".join(self.security().split())
        self.assertRegex(security, r"--dry-run` does not audit|`--dry-run` does not audit")

    def test_os_path_join_absolute_trap_is_named(self) -> None:
        """`os.path.join(ROOT, "/etc/passwd")` 는 ROOT 를 버린다 — Python 고유의 경로 결함이다."""
        security = " ".join(self.security().split())
        self.assertRegex(security, r"returns `b` when `b` is absolute")
        self.assertIn("is_relative_to", security, "containment 검사 형태가 없다")

    def test_jinja_autoescape_default_is_stated(self) -> None:
        """Jinja2 `Environment()` 는 autoescape=False 로 시작한다 (3.1.2 실측)."""
        security = " ".join(self.security().split())
        self.assertIn("`Environment()` defaults to `autoescape=False`", security)
        self.assertIn("select_autoescape", security)

    def test_secrets_versus_random_is_stated_as_a_vulnerability(self) -> None:
        security = " ".join(self.security().split())
        self.assertIn("secrets.token_urlsafe", security)
        self.assertRegex(security, r"Mersenne Twister")

    def test_python_security_declares_the_two_axis_pairing(self) -> None:
        """언어축 파일은 표면축과 짝지어야 한다 — 혼자 로드되면 인증·세션 검토가 통째로 빠진다."""
        header = self.security()[:1200]
        self.assertIn("Language axis", header)
        for surface in ALL_SURFACES:
            with self.subTest(surface=surface):
                self.assertIn(surface, header)

    def test_python_quality_follows_the_target_section_contract(self) -> None:
        """새 참조는 목표 계약(§0–6)대로 쓰기로 했다 — 첫 사례가 어기면 계약이 무의미해진다."""
        quality = self.quality()
        for heading in (
            "## 0. Applicability and Scope",
            "## 1. Version Resolution",
            "## 2. Tool Roles",
            "## 3. Availability and Authority",
            "## 4. Execution",
            "## 5. Manual Patterns",
            "## 6. Severity Mapping",
        ):
            with self.subTest(section=heading):
                self.assertIn(heading, quality)


class GoReferenceSemanticsTest(unittest.TestCase):
    """Go 참조의 실측된 사실을 고정한다 (go1.22.2, staticcheck 2026.1, govulncheck)."""

    def quality(self) -> str:
        return read("skills/code-quality-review/references/go-quality.md")

    def security(self) -> str:
        return read("skills/web-security-review/references/go-security.md")

    def test_go_build_is_never_told_to_write_a_binary(self) -> None:
        """`go build ./...` 는 현재 디렉터리에 실행 파일을 남긴다 — 리뷰가 만들면 안 되는 파일이다."""
        for line in code_blocks(self.quality()).splitlines():
            stripped = line.strip()
            if stripped.startswith("go build"):
                with self.subTest(command=stripped):
                    self.assertIn("-o /dev/null", stripped, "빌드 산출물이 작업 트리에 남는다")

    def test_gofmt_exit_code_trap_is_stated(self) -> None:
        """`gofmt -l` 은 미포맷 파일이 있어도 0 으로 끝난다 — 종료 코드만 보면 항상 통과다."""
        quality = " ".join(self.quality().split())
        self.assertRegex(quality, r"gofmt -l` exits `0` whether or not")

    def test_go_vet_load_failure_is_not_reported_as_findings(self) -> None:
        """컴파일 실패도 findings 와 똑같이 1 이다 — 구분하지 않으면 검사가 안 돈 걸 모른다."""
        quality = " ".join(self.quality().split())
        self.assertRegex(quality, r"go vet` returns `1` for a compile failure")
        self.assertIn("execution-error", quality)

    def test_readonly_dependency_default_is_stated(self) -> None:
        """Go 1.16+ 는 `-mod=readonly` 가 기본이라 go.mod 를 고치지 않고 실패한다 — 실측."""
        quality = " ".join(self.quality().split())
        self.assertIn("-mod=readonly", quality)
        self.assertRegex(quality, r"go mod tidy|go get", "쓰기로 취급할 명령을 명시하지 않는다")

    def test_loop_variable_finding_is_version_gated(self) -> None:
        """1.22 에서 의미가 바뀌었다 — 버전을 안 보면 정상 코드에 High 를 낸다."""
        quality = " ".join(self.quality().split())
        self.assertRegex(quality, r"Go 1\.22 changed the semantics")
        severity = between(self.quality(), "## 6. Severity Mapping", "Severity follows impact",
                           label="심각도 표")
        self.assertRegex(severity, r"not a finding.{0,30}1\.22")

    def test_text_template_is_named_as_the_xss_sink(self) -> None:
        """`text/template` 는 이스케이프하지 않는다 — API 가 같아서 import 한 줄이 전부다 (실측)."""
        security = " ".join(self.security().split())
        self.assertIn("text/template", security)
        self.assertRegex(security, r"performs no contextual escaping|no contextual escaping")
        self.assertIn("html/template", security)

    def test_goinsecure_specificity_is_not_treated_as_safety(self) -> None:
        """구체적인 패턴도 평문 HTTP 를 허용한다 — 범위가 줄 뿐 안전해지지 않는다."""
        security = " ".join(self.security().split())
        self.assertRegex(
            security,
            r"specificity narrows the blast radius, it does not make it safe",
        )
        self.assertRegex(security, r"smaller finding, not a non-finding")

    def test_go_template_critical_requires_a_named_target(self) -> None:
        """Go 템플릿은 노출된 함수·메서드만 호출한다 — 입력이 템플릿이라고 RCE 가 아니다."""
        security = " ".join(self.security().split())
        self.assertRegex(
            security, r"call \*\*only\*\* what the data namespace and the `FuncMap` expose"
        )
        self.assertRegex(security, r"Critical needs a named target")
        self.assertRegex(security, r"If you cannot name one, the severity is High")
        # `call` 은 FuncMap 없이 함수값 필드·맵 항목을 호출한다 (go1.22.2 재현).
        self.assertRegex(security, r"builtin `call` invokes those")
        self.assertRegex(security, r"function value.{0,40}struct field or map entry")

    def test_supply_chain_env_vars_are_real_and_rated_by_meaning(self) -> None:
        """`GONOSUMCHECK` 는 Go 환경변수가 아니다 (go1.22.2 `go env` 로 확인) — 없는 것을 지적하게 된다.

        `GOPRIVATE`/`GONOSUMDB` 는 사설 모듈의 정상 설정이므로 자동 High 도 틀렸다.
        """
        security = " ".join(self.security().split())
        self.assertRegex(
            security, r"`GONOSUMCHECK` is \*\*not\*\* a Go environment variable",
        )
        self.assertRegex(security, r"GOSUMDB=off", "실제 전역 비활성화를 검사하지 않는다")
        self.assertRegex(
            security, r"normal way to exempt an \*?\*?internal\*?\*? module",
            "사설 모듈의 정상 설정과 구분하지 않는다",
        )
        for line in code_blocks(self.security()).splitlines():
            if "GOSUMDB" in line or "GOPRIVATE" in line:
                with self.subTest(pattern=line.strip()):
                    self.assertNotIn("GONOSUMCHECK", line, "존재하지 않는 변수를 검색한다")

    def test_go_supply_chain_states_what_the_ecosystem_removes(self) -> None:
        """다른 언어 참조를 그대로 옮기면 없는 위험(install hook)을 찾게 된다."""
        security = " ".join(self.security().split())
        self.assertRegex(security, r"no install-time hook")
        self.assertIn("go.sum", security)
        self.assertIn("govulncheck", security)

    def test_math_rand_is_judged_by_import_not_by_seeding(self) -> None:
        """Go 1.20 이후 시드가 필요 없어져 오용이 오히려 현대적으로 보인다."""
        security = " ".join(self.security().split())
        self.assertIn("crypto/rand", security)
        self.assertRegex(security, r"Judge by the import")

    def test_go_quality_follows_the_target_section_contract(self) -> None:
        quality = self.quality()
        for heading in (
            "## 0. Applicability and Scope", "## 1. Version Resolution", "## 2. Tool Roles",
            "## 3. Availability and Authority", "## 4. Execution", "## 5. Manual Patterns",
            "## 6. Severity Mapping",
        ):
            with self.subTest(section=heading):
                self.assertIn(heading, quality)

    def test_go_security_declares_the_two_axis_pairing(self) -> None:
        header = self.security()[:1000]
        self.assertIn("Language axis", header)
        for surface in ALL_SURFACES:
            with self.subTest(surface=surface):
                self.assertIn(surface, header)


class RustReferenceSemanticsTest(unittest.TestCase):
    """Rust 참조의 실측된 사실을 고정한다 (cargo 1.91.0 / rustc 1.91.0)."""

    def quality(self) -> str:
        return read("skills/code-quality-review/references/rust-quality.md")

    def security(self) -> str:
        return read("skills/web-security-review/references/rust-security.md")

    def test_cargo_commands_relocate_the_target_dir_and_lock_the_lockfile(self) -> None:
        """`cargo clippy` 는 Cargo.lock 과 target/ 을 크레이트 안에 만든다 — 둘 다 막아야 한다."""
        for line in code_blocks(self.quality()).splitlines():
            stripped = line.strip()
            if stripped.startswith("cargo clippy") or stripped.startswith("cargo check"):
                if "--fix" in stripped or "--version" in stripped:
                    continue
                with self.subTest(command=stripped):
                    self.assertIn("--locked", stripped, "Cargo.lock 이 새로 생긴다")
        quality = " ".join(self.quality().split())
        self.assertIn("CARGO_TARGET_DIR", quality, "target/ 을 크레이트 밖으로 보내지 않는다")

    def test_missing_lockfile_is_a_skip_not_a_workaround(self) -> None:
        """lock 이 없으면 --locked 는 101 로 실패한다. 그게 정답이지 우회할 상황이 아니다."""
        quality = " ".join(self.quality().split())
        self.assertRegex(quality, r"exit 101")
        self.assertRegex(quality, r"skipped-read-only")
        self.assertRegex(
            quality, r"--offline`?, which still writes the lockfile|do not substitute\s+`--offline`",
            "`--offline` 도 lock 을 쓴다는 사실이 없다",
        )

    def test_clippy_exit_code_trap_is_stated(self) -> None:
        """`cargo clippy` 는 warning 이 있어도 0 이다 — 종료 코드만 보면 항상 통과다."""
        quality = " ".join(self.quality().split())
        self.assertRegex(quality, r"exits `0` with warnings present")
        self.assertRegex(
            quality, r"-D warnings.{0,120}overrides the project",
            "-D warnings 가 프로젝트 정책을 덮는다는 경고가 없다",
        )

    def test_review_effort_is_pointed_away_from_what_the_compiler_owns(self) -> None:
        """안전한 Rust 에서 use-after-free 를 지적하면 보고서 신뢰도만 잃는다."""
        security = " ".join(self.security().split())
        self.assertRegex(security, r"compiler already rejects")
        for real in ("unsafe", "panic", "exhaustion", "dependencies"):
            with self.subTest(surface=real):
                self.assertIn(real, security)

    def test_overflow_behaviour_differs_by_profile(self) -> None:
        """debug 는 panic, release 는 wrap — 같은 코드가 프로파일에 따라 크래시와 오답이 된다 (실측)."""
        security = " ".join(self.security().split())
        self.assertRegex(security, r"debug build panics on overflow and a release build wraps")

    def test_pathbuf_push_absolute_trap_is_named(self) -> None:
        security = " ".join(self.security().split())
        self.assertRegex(security, r"`PathBuf::push` with an \*\*absolute\*\* path replaces")

    def test_debug_derive_leak_is_named(self) -> None:
        """`#[derive(Debug)]` 한 줄이 토큰을 로그로 내보낸다 — Rust 고유의 시크릿 누출 경로다."""
        security = " ".join(self.security().split())
        self.assertRegex(security, r"derive\(Debug\)")
        self.assertIn("tracing::debug!", security)

    def test_rust_quality_follows_the_target_section_contract(self) -> None:
        quality = self.quality()
        for heading in (
            "## 0. Applicability and Scope", "## 1. Version Resolution", "## 2. Tool Roles",
            "## 3. Availability and Authority", "## 4. Execution", "## 5. Manual Patterns",
            "## 6. Severity Mapping",
        ):
            with self.subTest(section=heading):
                self.assertIn(heading, quality)

    def test_thread_rng_is_not_flagged_as_weak(self) -> None:
        """`ThreadRng` 는 CSPRNG 다 (rand 0.8.7: `impl CryptoRng for ThreadRng`) — 지적하면 오탐이다."""
        security = " ".join(self.security().split())
        self.assertRegex(security, r"`thread_rng\(\)`\*?\*? all qualify|and \*\*`thread_rng\(\)`\*\* all qualify")
        self.assertRegex(security, r"impl CryptoRng for ThreadRng")
        grep_lines = [
            line for line in code_blocks(self.security()).splitlines()
            if "SmallRng" in line
        ]
        self.assertTrue(grep_lines, "약한 RNG grep 패턴이 없다")
        for line in grep_lines:
            with self.subTest(pattern=line.strip()):
                self.assertNotIn(
                    "thread_rng", line,
                    "thread_rng 를 grep 대상에 두면 모든 프로젝트에서 오탐이 난다",
                )

    def test_rust_security_declares_the_two_axis_pairing(self) -> None:
        header = self.security()[:1000]
        self.assertIn("Language axis", header)
        for surface in ALL_SURFACES:
            with self.subTest(surface=surface):
                self.assertIn(surface, header)


class SectionContractDepthTest(unittest.TestCase):
    """§0–6 계약이 **구조만** 요구하면 절이 비어도 통과한다. 내용 계약도 함께 고정한다."""

    NEW_REFERENCES = ("python-quality", "go-quality", "rust-quality")

    def test_version_resolution_collects_three_axes_not_one_answer(self) -> None:
        """floor·실행·테스트는 서로 다른 질문이다. 첫 답에서 멈추면 셋의 불일치를 못 본다."""
        for name in self.NEW_REFERENCES:
            section = between(
                quality_reference(name), "## 1. Version Resolution", "## 2. Tool Roles",
                label=f"{name} §1",
            )
            flat = " ".join(section.split())
            with self.subTest(reference=name):
                self.assertRegex(flat, r"Collect all", "첫 답에서 멈추는 방식이 남아 있다")
                for question in ("floor", "runs", "tested"):
                    self.assertIn(f"**{question}**", flat, f"{question} 축이 없다")

    def test_severity_distinguishes_an_application_from_a_published_library(self) -> None:
        """같은 결함도 소비자가 있으면 되돌릴 수 없다 — 영향 기반 심각도의 핵심 축이다."""
        for name in self.NEW_REFERENCES:
            section = " ".join(
                between(quality_reference(name), "## 6. Severity Mapping", "**Run states**",
                        label=f"{name} §6").split()
            )
            with self.subTest(reference=name):
                self.assertRegex(section, r"published library")
                self.assertRegex(section, r"Raise a severity one step")


class UntrustedExecutionContractTest(unittest.TestCase):
    """"워크스페이스에 안 쓴다"와 "신뢰하지 않는 코드를 실행하지 않는다"는 다른 보장이다.

    `cargo clippy` 는 `--locked` 와 `CARGO_TARGET_DIR` 를 다 줘도 `build.rs` 를 **실행한다**
    (cargo 1.91.0 에서 워크스페이스 밖 절대 경로에 쓰는 build.rs 로 재현). ESLint 도 flat
    config 를 모듈로 실행한다. 이 축을 문서가 말하지 않으면 리뷰어가 남의 코드를 돌린다.
    """

    def rule(self) -> str:
        # 인용 블록이므로 줄머리 `>` 를 걷어내야 문장이 이어진다.
        raw = between(
            read("skills/code-quality-review/SKILL.md"),
            "**Read-only mode (priority rule).**", "## Reference Files",
            label="읽기 전용 규칙",
        )
        return " ".join(re.sub(r"(?m)^\s*>\s?", "", raw).split())

    def test_the_execution_axis_is_stated_separately_from_the_write_axis(self) -> None:
        rule = self.rule()
        self.assertRegex(rule, r"does the tool \*?\*?execute\*?\*? the code under review")
        self.assertRegex(rule, r"different guarantees")

    #: 실행 조건이 **도구가 아니라 설정 형식**이라는 것이 이 표의 요지다. 조건을 빠뜨리면
    #: 리뷰어가 도구 이름만 보고 판단하게 된다 — 실제로 처음엔 mypy/Stylelint 를 안전으로
    #: 단정했다가 실측에서 뒤집혔다.
    EXECUTES = {
        "cargo clippy": "build.rs",
        "ESLint": "eslint.config.js",
        "Stylelint": ".stylelintrc.js",
        "mypy": "plugins",
        "PHPStan": "bootstrapFiles",
    }
    DOES_NOT_EXECUTE = ("ruff", "go vet", "tsc", "Biome")

    def test_each_executing_tool_states_the_condition_not_just_the_name(self) -> None:
        rule = self.rule()
        for tool, condition in self.EXECUTES.items():
            with self.subTest(tool=tool):
                self.assertIn(tool, rule, "실행하는 도구가 명시되지 않았다")
                self.assertIn(condition, rule, f"{tool} 의 실행 조건이 없다")

    def test_the_tools_that_do_not_execute_are_named_too(self) -> None:
        """실행하지 않는 도구까지 적어야 규칙이 과잉 적용되지 않는다."""
        rule = self.rule()
        for tool in self.DOES_NOT_EXECUTE:
            with self.subTest(tool=tool):
                self.assertIn(tool, rule)

    def test_the_rule_is_stated_as_a_criterion_not_a_tool_list(self) -> None:
        """도구 목록은 낡는다 — 판단 기준이 남아야 새 도구에도 적용된다."""
        rule = self.rule()
        self.assertRegex(rule, r"not the config's file format")
        for route in ("The config is a program", "The config names host code",
                      "manifest loads code behind the tool's back",
                      "Config chains hide all of the above"):
            with self.subTest(route=route):
                self.assertIn(route, rule, "실행 경로가 다 적히지 않았다")
        self.assertRegex(
            rule,
            r"names no host code and no\s+external executable",
            "안전한 경우가 '호스트 코드·외부 실행 파일 없음'으로 특정되지 않았다",
        )
        self.assertRegex(
            rule, r"have not resolved counts as unresolved, not as safe",
            "미해석을 안전으로 읽지 말라는 규칙이 없다",
        )

    def test_a_declarative_config_is_not_assumed_safe(self) -> None:
        """`.eslintrc.json`·`.stylelintrc.json` 도 모듈을 실행한다 (둘 다 재현)."""
        rule = self.rule()
        self.assertIn(".eslintrc.json", rule)
        self.assertIn(".stylelintrc.json", rule)
        self.assertRegex(rule, r"pure JSON")

    def test_the_repository_can_replace_the_tool_itself(self) -> None:
        """도구 설정보다 한 단계 위다 — `.cargo/config.toml` 과 `.npmrc` 는 도구를 바꾼다 (둘 다 재현)."""
        rule = self.rule()
        self.assertRegex(rule, r"replaces or wraps the tool itself")
        for knob in ("build.rustc-wrapper", ".npmrc", "node-options=--require"):
            with self.subTest(knob=knob):
                self.assertIn(knob, rule)
        self.assertRegex(
            rule, r"regardless of their own configs",
            "npm 주입이 도구별 설정과 무관하다는 점이 없다",
        )

    def test_the_criterion_is_whether_the_diff_controls_it(self) -> None:
        """메커니즘의 존재가 아니라 diff 가 제어하느냐가 기준이다 — Go 가 반례다."""
        rule = self.rule()
        self.assertRegex(rule, r"whether the diff\s+can control it")
        self.assertRegex(
            rule, r"never from a file in the repository",
            "Go 가 왜 안전한지(저장소가 GOFLAGS 를 못 준다)가 없다",
        )

    def test_naming_an_extension_is_not_sufficient_either(self) -> None:
        """Biome 의 GritQL 은 확장이지만 호스트 코드가 아니다 — 같이 묶으면 과잉 차단이다."""
        rule = self.rule()
        self.assertRegex(rule, r"not sufficient either")
        self.assertIn("GritQL", rule)
        self.assertRegex(
            rule, r"read the plugin, not as a reason to sandbox",
            "제한된 DSL 과 임의 코드 실행이 구분되지 않는다",
        )

    def test_isolation_covers_the_host_not_only_the_workspace(self) -> None:
        """재현한 build.rs 는 워크스페이스 밖 절대 경로에 썼다 — read-only mount 로는 안 막힌다."""
        rule = self.rule()
        self.assertRegex(rule, r"not\*?\*? enough on its own|is \*\*not\*\* enough")
        self.assertRegex(rule, r"absolute path outside the workspace")
        for knob in ("HOME", "CARGO_HOME", "npm_config_cache", "GOPATH"):
            with self.subTest(knob=knob):
                self.assertIn(knob, rule)

    def test_an_internal_branch_is_not_a_standing_exemption(self) -> None:
        """"우리 저장소"라고 새로 들어온 훅·플러그인까지 신뢰되는 것은 아니다."""
        self.assertRegex(
            self.rule(),
            r"newly introduced build hook, plugin, or dependency is code that was not there before",
        )

    def test_the_untrusted_case_has_a_named_run_state(self) -> None:
        rule = self.rule()
        self.assertIn("skipped-untrusted-execution", rule)
        self.assertIn(
            "skipped-untrusted-execution",
            read("skills/code-quality-review/SKILL.md"),
        )

    def test_the_rule_does_not_fire_on_an_ordinary_review(self) -> None:
        """자기 팀 브랜치 리뷰가 매번 이 경고를 달면 아무도 안 읽는다."""
        self.assertRegex(
            self.rule(), r"ordinary case and needs none of this",
        )

    def test_every_executing_tool_repeats_the_condition_in_its_reference(self) -> None:
        """SKILL.md 표만 있으면 명령을 읽는 사람이 조건을 못 본다."""
        places = {
            "rust-quality": ("build.rs",),
            # 선언형 설정도 코드를 부른다 — 두 경로를 다 적어야 한다.
            "js-toolchain": ("eslint.config.js", ".eslintrc.json", "plugins"),
            "css-quality": (".stylelintrc.js",),
            "python-quality": ("plugins",),
            "php-quality": ("bootstrapFiles", "autoload.files", "rules"),
        }
        for name, conditions in places.items():
            reference = " ".join(quality_reference(name).split())
            for condition in conditions:
                with self.subTest(reference=name, condition=condition):
                    self.assertIn(condition, reference, "실행 조건이 참조에 없다")
            with self.subTest(reference=name):
                self.assertRegex(
                    reference, r"untrusted[- ]diff|untrusted-execution|would not run",
                    "신뢰 경계 규칙으로 연결되지 않는다",
                )

    def test_the_phpstan_trust_gate_runs_before_the_analysis(self) -> None:
        """순서가 두 번 틀렸던 자리다. 체인 정의 → 게이트 → 분석, 셋 다 고정한다.

        처음에는 게이트가 `collect_config` 정의보다 **앞**에 있어 빈 체인으로 통과했고,
        고친다면서 분석 **뒤**로 옮겨 이미 실행된 뒤에 확인하게 만들었다.
        """
        reference = quality_reference("php-quality")
        definition = reference.index("collect_config() {")
        gate = reference.index("EXEC_RISK=\"\"")
        analysis = reference.index("$PHP_CMD $(command -v phpstan) analyse")
        self.assertLess(definition, gate, "게이트가 체인 정의보다 앞이다 — 빈 체인으로 통과한다")
        self.assertLess(gate, analysis, "게이트가 분석보다 뒤다 — 이미 실행된 뒤에 확인한다")
        # 게이트가 실행 분기와 **같은** if 체인이어야 판정이 실행을 막는다.
        branch = reference[gate:analysis]
        self.assertIn('if [ -n "$EXEC_RISK" ]', branch,
                      "게이트 결과가 실행 분기를 막지 않는다")
        self.assertIn("skipped-untrusted-execution", branch)

    def test_no_trust_gate_command_truncates_its_input(self) -> None:
        """잘린 목록은 짧은 목록으로 읽힌다 — 문제의 항목이 마지막이거나 6줄 뒤일 수 있다."""
        gate = between(
            quality_reference("php-quality"), 'EXEC_RISK=""',
            "# PHPStan — run under the correct PHP binary", label="신뢰 게이트",
        )
        for line in gate.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or not stripped:
                continue
            with self.subTest(command=stripped[:60]):
                self.assertNotRegex(stripped, r"\bhead\b", "목록을 잘라 읽는다")
                self.assertNotRegex(stripped, r"-A\d+", "고정 줄 수 창으로 자른다")

    def test_the_precheck_covers_dependency_extensions_and_versions(self) -> None:
        reference = " ".join(quality_reference("php-quality").split())
        self.assertIn("extension-installer", reference, "의존 패키지 확장 자동 활성화가 없다")
        self.assertIn("--autoload-file", reference, "실행 인자 경로가 없다")
        self.assertIn("0.12.26", reference, "전환 시점이 부정확하거나 없다")
        self.assertRegex(
            reference, r"not a rename",
            "`scanFiles` 가 옛 `autoload_files` 의 동의어가 아니라는 점이 없다",
        )
        # `autoload_files.php`(composer 산출물)가 같은 문자열을 포함하므로 그것만으로는
        # 구버전 파라미터 검사를 확인할 수 없다. 전용 마커를 요구한다.
        gate = between(
            quality_reference("php-quality"), 'EXEC_RISK=""',
            "# PHPStan — run under the correct PHP binary", label="신뢰 게이트",
        )
        self.assertIn("autoload_directories", gate, "구버전 파라미터를 검사하지 않는다")
        self.assertIn("legacy-autoload", gate, "구버전 발견을 별도로 표시하지 않는다")

    def test_stylelint_reference_matches_the_top_level_contract(self) -> None:
        """상위는 JSON 도 실행된다고 하는데 하위가 안전하다고 하면 하위가 이긴다 — 명령 옆이니까."""
        reference = " ".join(quality_reference("css-quality").split())
        self.assertRegex(reference, r"whatever the config is written in")
        for named in ("extends", "plugins", "customSyntax"):
            with self.subTest(names=named):
                self.assertIn(named, reference)
        self.assertNotRegex(
            reference, r"is data and is not",
            "JSON 설정을 안전으로 단정하는 표현이 남아 있다",
        )

    def test_phpstan_precheck_covers_the_whole_chain(self) -> None:
        """루트 설정 3개와 루트 composer.json 만 보면 세 경로를 놓친다 (전부 재현)."""
        reference = " ".join(quality_reference("php-quality").split())
        self.assertRegex(reference, r"not enough")
        self.assertIn("CONFIG_CHAIN", reference, "체인을 재사용하지 않는다")
        self.assertIn("autoload_files.php", reference, "의존 패키지 목록을 읽지 않는다")
        self.assertRegex(
            reference, r"executable-config:",
            "`.php` includes 항목을 찾지 않는다",
        )

    def test_phpstan_execution_paths_are_stated_precisely(self) -> None:
        """PHPStan 은 조건부다 — 넓게 쓰면 모든 PHP 리뷰에 경고가 붙고, 빼면 두 경로를 놓친다.

        실측(PHPStan 2.x / PHP 8.3): paths·scanFiles 는 실행하지 않고,
        bootstrapFiles 와 composer 의 autoload.files 는 실행한다. 후자는 phpstan.neon 에
        아무 선언이 없어도 실행되므로 설정만 봐서는 알 수 없다.
        """
        rule = self.rule()
        self.assertIn("PHPStan", rule)
        self.assertIn("bootstrapFiles", rule)
        self.assertIn("autoload.files", rule)
        self.assertRegex(
            rule, r"`scanFiles:` \| No|scanFiles.{0,20}No",
            "실행하지 않는 경로를 구분하지 않으면 모든 PHP 리뷰에 경고가 붙는다",
        )
        self.assertRegex(
            rule, r"most projects|does not execute anything",
            "일반적인 PHP 프로젝트는 안전하다는 사실이 없다",
        )

    def test_the_php_reference_repeats_it_where_the_command_is(self) -> None:
        """주 스택이다 — 명령 옆에 없으면 아무도 SKILL.md 로 돌아가지 않는다."""
        reference = " ".join(quality_reference("php-quality").split())
        self.assertIn("bootstrapFiles", reference)
        self.assertIn("autoload.files", reference)
        self.assertIn("skipped-untrusted-execution", reference)
        self.assertRegex(
            reference, r"For your own or your team's branch it is inert",
            "기존 PHP 리뷰가 그대로라는 점이 명시되지 않았다",
        )

    def test_the_rust_reference_names_the_cargo_config_route(self) -> None:
        """"이 크레이트엔 build.rs 가 없다"로는 안 끝난다 — `.cargo/config.toml` 이 rustc 를 바꾼다."""
        execution = " ".join(
            between(
                quality_reference("rust-quality"), "## 4. Execution", "## 5. Manual Patterns",
                label="rust §4",
            ).split()
        )
        self.assertIn(".cargo/config.toml", execution)
        # 올바른 문장이 있어도 모순되는 옛 문장이 남으면 지시가 갈린다.
        self.assertNotRegex(
            execution, r"alias on `clippy` or `check` replaces",
            "내장 `check` 도 대체된다는 모순 문장이 남아 있다",
        )
        for route in ("rustc-wrapper", "rustc-workspace-wrapper", "[alias]",
                      "credential-provider", "linker"):
            with self.subTest(route=route):
                self.assertIn(route, execution, f"{route} 경로가 없다")
        # alias 는 외부 서브커맨드만 가린다 — `check` 까지 위험하다고 쓰면 틀린 지시가 된다.
        self.assertRegex(
            execution, r"alias on `check`, `build`, or any other\s+built-in is ignored",
            "내장 명령은 alias 로 못 가린다는 사실이 없다",
        )
        self.assertRegex(
            execution, r"`\[target\.\*\] runner` is narrower",
            "runner 의 적용 범위(run/test/bench)가 과장돼 있다",
        )
        self.assertRegex(
            execution, r"extensionless `\.cargo/config`",
            "확장자 없는 config 도 읽힌다는 사실이 없다",
        )
        self.assertRegex(
            execution, r"alias shadows it|shadows an external subcommand",
            "alias 가 clippy 자체를 대체한다는 점이 없다",
        )
        self.assertRegex(
            execution, r"does not settle the question",
            "build.rs 부재가 결론이 아니라는 점이 없다",
        )

    def test_the_rust_reference_repeats_the_warning_where_the_command_is(self) -> None:
        """명령 옆에 없으면 읽는 사람이 SKILL.md 로 돌아가지 않는다."""
        execution = between(
            quality_reference("rust-quality"), "## 4. Execution", "## 5. Manual Patterns",
            label="rust §4",
        )
        flat = " ".join(execution.split())
        self.assertRegex(flat, r"compile \*\*and execute\*\* `build.rs`")
        self.assertIn("skipped-untrusted-execution", flat)


class SecurityAuditorScopeTest(unittest.TestCase):
    """PHP 전용 체크리스트를 가진 에이전트가 다른 언어에 적용되지 않도록 경계를 고정한다.

    체크리스트 자체는 손대지 않는다 — 주 스택이고 잘 돌고 있다. 막아야 하는 것은
    PHP 패턴을 Go·Python 에 대입하는 것뿐이다.
    """

    AGENT_FILES = (
        "agents/security-auditor/claude.md",
        "agents/security-auditor/codex.toml",
    )

    def test_the_agent_names_its_language_scope_and_the_way_out(self) -> None:
        for path in self.AGENT_FILES:
            text = " ".join(read(path).split())
            with self.subTest(agent=path):
                self.assertRegex(text, r"Language Scope")
                self.assertIn("web-security-review", text, "다른 언어를 넘길 곳이 없다")
                self.assertRegex(
                    text, r"non-match is not evidence of safety",
                    "패턴 불일치를 안전으로 읽지 말라는 경고가 없다",
                )

    def test_the_php_checklist_itself_is_untouched(self) -> None:
        """주 스택의 감사 내용은 이 작업의 대상이 아니다 — 경계만 추가한다."""
        for path in self.AGENT_FILES:
            text = read(path)
            with self.subTest(agent=path):
                self.assertIn("PHP", text)
                self.assertRegex(
                    text, r"(?i)sql injection|injection",
                    "PHP 체크리스트가 사라졌다",
                )

    def test_the_codex_variant_is_still_valid_toml(self) -> None:
        """설명을 넣다가 TOML 을 깨면 Codex 쪽 에이전트가 통째로 로드되지 않는다."""
        import tomllib

        data = tomllib.loads(read("agents/security-auditor/codex.toml"))
        self.assertEqual(data["name"], "security-auditor")
        self.assertIn("developer_instructions", data)
        self.assertIn("Language Scope", data["developer_instructions"])


class ReadOnlyBoundaryContractTest(unittest.TestCase):
    """읽기 전용 계약의 **경계**를 하나로 고정한다.

    "작업 트리 무변경"과 "파일시스템 전체 무쓰기"가 섞여 있으면 참조마다 다른 해석이 나온다.
    Rust 는 후자를 문자 그대로 지키면 린트를 아예 못 돌린다 — 계약이 어느 쪽인지 말해야 한다.
    """

    def rule(self) -> str:
        return " ".join(
            between(
                read("skills/code-quality-review/SKILL.md"),
                "**Read-only mode (priority rule).**", "## Reference Files",
                label="읽기 전용 규칙",
            ).split()
        )

    def test_the_boundary_is_the_workspace_not_the_filesystem(self) -> None:
        rule = self.rule()
        self.assertRegex(rule, r"Where the boundary is")
        self.assertIn("CARGO_TARGET_DIR", rule, "임시 디렉터리 허용 사례가 없다")

    def test_a_genuinely_write_free_form_is_preferred_when_one_exists(self) -> None:
        """더 강한 보장이 공짜로 있으면 그걸 쓴다 — mypy 는 /dev/null 로 아무 데도 안 쓴다."""
        rule = self.rule()
        self.assertRegex(rule, r"prefer it")
        self.assertIn("--cache-dir=/dev/null", rule)

    def test_the_exception_does_not_leak_into_code_modification(self) -> None:
        """임시 경로 허용이 자동수정 명령의 우회로가 되면 계약 전체가 무의미해진다."""
        self.assertRegex(
            self.rule(),
            r"Never redirect a write out of the workspace to make a \*?\*?code-modifying",
        )


class LanguageRegistrationConsistencyTest(unittest.TestCase):
    """언어 하나를 지원하려면 네 곳에 등록해야 한다. 한 곳을 빠뜨리는 것이 이 구조의 기본 실패다.

    빠뜨리면 조용히 실패한다 — 참조 파일은 있는데 리뷰어가 로드하지 않거나, 분류는 되는데
    프롬프트가 없어 해당 파일이 아무에게도 안 간다.
    """

    #: 언어 → (품질 참조, 보안 참조, 분류 표에 쓰이는 확장자)
    LANGUAGES = {
        "PHP": ("php-quality.md", "php-backend-security.md", "*.php"),
        "Python": ("python-quality.md", "python-security.md", "*.py"),
        "Go": ("go-quality.md", "go-security.md", "*.go"),
        "Rust": ("rust-quality.md", "rust-security.md", "*.rs"),
    }

    #: JS/TS 는 참조가 표면별로 갈려 위 표의 1:1 구조에 맞지 않는다. 그래서 빠져 있었고,
    #: 게이트에서 JS/TS 를 지워도 테스트가 통과했다. 게이트 검사에는 반드시 포함한다.
    GATE_LANGUAGES = (*LANGUAGES, "JS/TS")

    def test_every_language_has_both_reference_files_on_disk(self) -> None:
        for language, (quality, security, _) in self.LANGUAGES.items():
            with self.subTest(language=language):
                self.assertTrue(
                    Path("skills/code-quality-review/references", quality).is_file(),
                    f"{quality} 가 없다",
                )
                self.assertTrue(
                    Path("skills/web-security-review/references", security).is_file(),
                    f"{security} 가 없다",
                )

    def test_every_language_is_listed_in_the_quality_skill(self) -> None:
        skill = read("skills/code-quality-review/SKILL.md")
        for language, (quality, _, _) in self.LANGUAGES.items():
            with self.subTest(language=language):
                self.assertIn(f"references/{quality}", skill, "참조 목록에 없다 — 로드되지 않는다")

    def test_every_language_is_detected_in_step_1(self) -> None:
        """목록에 있어도 감지 절에 없으면 standalone 리뷰가 그 언어를 알아채지 못한다."""
        detection = between(
            read("skills/code-quality-review/SKILL.md"),
            "## Step 1: Detect Stack", "Infer project conventions", label="Step 1 감지",
        )
        for language, (quality, _, extension) in self.LANGUAGES.items():
            with self.subTest(language=language):
                self.assertIn(quality, detection, "감지 절이 이 참조를 가리키지 않는다")
                self.assertIn(extension.lstrip("*"), detection, "감지 신호(확장자)가 없다")

    def test_every_language_has_an_execution_section_in_step_2(self) -> None:
        """감지만 하고 실행 위임이 없으면 도구를 어떻게 부르는지 아무도 모른다."""
        execution = between(
            read("skills/code-quality-review/SKILL.md"),
            "## Step 2: Run CLI Tools", "## Step 3", label="Step 2 실행",
        )
        for language, (quality, _, _) in self.LANGUAGES.items():
            with self.subTest(language=language):
                self.assertIn(quality, execution, "실행 위임 절이 없다")

    def test_every_language_has_a_quality_reviewer_mapping(self) -> None:
        """`{language} → {reference} → {scope}` 매핑이 없으면 branch 리뷰가 리뷰어를 못 만든다."""
        mapping = between(
            read("skills/branch-merge-review/references/reviewer-prompts.md"),
            "| `{language}` | `{reference}` | `{scope}` |",
            "Add a row when a language gains a reference", label="품질 리뷰어 매핑",
        )
        for language, (quality, _, extension) in self.LANGUAGES.items():
            with self.subTest(language=language):
                self.assertIn(quality, mapping, "매핑 표에 참조가 없다")
                self.assertIn(f"`{extension}`", mapping, "매핑 표에 scope 가 없다")

    def test_the_completion_gate_lists_every_covered_language(self) -> None:
        """게이트가 지원 언어를 빠뜨리면 정상 리뷰가 Block 으로 떨어진다.

        "미지원으로 적지 않았다"만 검사하면 아예 언급이 없어도 통과한다 — 실제로 그 구멍이
        있었다. 지원 목록에 **있어야** 통과하도록 바꾼다.
        """
        gate = " ".join(
            between(
                read("skills/branch-merge-review/SKILL.md"),
                "**Completion gate", "## Step 4", label="완료 게이트",
            ).split()
        )
        covered = between(gate, "Languages covered today", "The gate still applies",
                          label="지원 언어 목록")
        for language in self.GATE_LANGUAGES:
            with self.subTest(language=language):
                self.assertIn(language, covered, "게이트의 지원 언어 목록에 없다")
                self.assertNotRegex(
                    gate,
                    rf"without a language-axis reference[^.]{{0,80}}{language}",
                    f"{language} 를 여전히 미지원으로 적고 있다",
                )

    def test_every_language_is_listed_in_the_security_skill(self) -> None:
        skill = read("skills/web-security-review/SKILL.md")
        for language, (_, security, _) in self.LANGUAGES.items():
            with self.subTest(language=language):
                self.assertIn(f"references/{security}", skill, "참조 표에 없다")
                self.assertIn(security, skill.split("| Change | Language axis")[1],
                              "선택 표에 그 언어의 행이 없다")

    def test_every_language_is_classified_by_the_branch_review(self) -> None:
        skill = read("skills/branch-merge-review/SKILL.md")
        for language, (_, _, extension) in self.LANGUAGES.items():
            with self.subTest(language=language):
                self.assertIn(f"`{extension}`", skill, "분류 표에 확장자가 없다")

    def test_every_language_has_a_reviewer_prompt_focus(self) -> None:
        """focus 행이 없으면 그 언어는 dispatch 되지 않고 unreviewed 로 보고된다."""
        prompts = read("skills/branch-merge-review/references/reviewer-prompts.md")
        focus_table = between(prompts, "| `{language}` | `{focus}` |",
                              "When a language has no row here", label="focus 표")
        for language in self.LANGUAGES:
            expected = "Node/TS" if language == "Node" else language
            with self.subTest(language=language):
                self.assertIn(f"| {expected} |", focus_table, "focus 행이 없다")

    def test_the_security_prompt_table_covers_every_language(self) -> None:
        prompts = read("skills/branch-merge-review/references/reviewer-prompts.md")
        load_table = between(prompts, "| Changed files | Load |",
                             "Browser assets only", label="보안 로드 표")
        for language, (_, security, _) in self.LANGUAGES.items():
            with self.subTest(language=language):
                self.assertIn(security, load_table, "보안 리뷰어가 이 언어를 로드하지 않는다")

    def test_the_unsupported_language_example_is_actually_unsupported(self) -> None:
        """지원 언어를 "참조가 없는 언어" 예시로 쓰면 문서가 자기 자신과 모순된다."""
        for path in (
            "skills/code-quality-review/SKILL.md",
            "skills/web-security-review/SKILL.md",
        ):
            text = " ".join(read(path).split())
            for language in self.LANGUAGES:
                with self.subTest(skill=path, language=language):
                    self.assertNotRegex(
                        text, rf"checklist applied to {language}\b",
                        f"{language} 는 이제 지원 언어다 — 미지원 예시로 쓸 수 없다",
                    )


class SecurityMetadataAndGuidanceTest(unittest.TestCase):
    """4단계에서 넓힌 라우팅 표면과 표면 참조의 지침 정확성을 고정한다."""

    def test_the_skill_description_reaches_node_and_native_requests(self) -> None:
        """본문이 Node CLI·데몬까지 다루는데 description 이 PHP 웹만 말하면 도달하지 않는다."""
        description = between(
            read("skills/web-security-review/SKILL.md"), "description:", "\n---",
            label="description",
        )
        for token in ("Node", "CLI"):
            with self.subTest(token=token):
                self.assertIn(token, description)
        self.assertRegex(
            description, r"unreviewed|another language",
            "미지원 언어를 미검토로 보고한다는 경계가 description 에 없다",
        )

    def test_the_security_prompt_loads_one_language_file_per_language(self) -> None:
        """PHP+Node 브랜치를 리뷰어 하나가 처리한다 — 단수로 쓰면 한 언어가 빠진다."""
        prompts = " ".join(
            read("skills/branch-merge-review/references/reviewer-prompts.md").split()
        )
        self.assertRegex(
            prompts, r"per changed language",
            "언어 축을 언어마다 로드한다는 지시가 없다",
        )

    def test_scrypt_guidance_pins_every_cost_parameter(self) -> None:
        """`N` 만 고정하면 같은 N 으로도 r 을 낮춰 메모리 비용을 반감할 수 있다."""
        reference = read("skills/web-security-review/references/http-server-security.md")
        for parameter in ("N=2^17", "r=8", "p=1"):
            with self.subTest(parameter=parameter):
                self.assertIn(parameter, reference)

    def test_wildcard_cors_is_not_described_as_a_data_leak(self) -> None:
        """credentials + `*` 는 Fetch 표준상 브라우저가 실패시킨다 — 반사 origin 과 다르다."""
        reference = read("skills/web-security-review/references/http-server-security.md")
        cors = " ".join(
            between(reference, "## 8. CORS", "## 9.", label="CORS 절").split()
        )
        self.assertIn("fetch.spec.whatwg.org", cors, "표준 근거가 없다")
        self.assertRegex(cors, r"\bfails\b", "브라우저가 요청을 실패시킨다는 사실이 없다")
        self.assertRegex(
            cors, r"wildcard.{0,300}?broken configuration rather than a data leak",
            "wildcard 를 여전히 데이터 유출로 설명한다",
        )
        self.assertRegex(
            cors, r"reflect.{0,300}?Critical",
            "진짜 노출인 반사 origin 이 wildcard 와 구분되지 않는다",
        )

    def test_csp_is_scoped_to_document_responses(self) -> None:
        """JSON 만 반환하는 API 에 CSP 누락을 매번 보고하면 이 절 전체가 무시된다."""
        reference = read("skills/web-security-review/references/http-server-security.md")
        headers = between(reference, "## 7. Security Headers", "## 8.", label="헤더 절")
        self.assertRegex(headers, r"HTML document responses")
        self.assertRegex(
            headers, r"API[^.]{0,120}nosniff|nosniff[^.]{0,120}API",
            "API 에서도 유효한 헤더가 무엇인지 말하지 않는다",
        )

    def test_password_hashing_guidance_does_not_call_bcrypt_memory_hard(self) -> None:
        """bcrypt 는 memory-hard 가 아니다 — 동급으로 쓰면 GPU 공격 내성을 잘못 가르친다."""
        reference = read("skills/web-security-review/references/http-server-security.md")
        self.assertRegex(reference, r"bcrypt is not memory-hard|bcrypt[^.]{0,40}not memory-hard")
        self.assertNotRegex(
            reference,
            r"memory-hard algorithm \(argon2id, scrypt, bcrypt\)",
            "bcrypt 를 memory-hard 목록에 넣은 표현이 되살아났다",
        )
        self.assertRegex(reference, r"argon2id", "권장 알고리즘이 없다")


class PhpCrossValidationBaseline(unittest.TestCase):
    """9 — 교차 검증이 PHP 패턴을 유지하고, 양 플랫폼에서 동등하다."""

    #: POSIX grep과 PowerShell 해시테이블 **양쪽**에 있어야 하는 위험 토큰.
    SHARED_RISK_TOKENS = (
        "session_start",
        "session_regenerate_id",
        "move_uploaded_file",
        "innerHTML",
        "localStorage",
    )

    def cross_validation_block(self) -> str:
        return between(
            read("skills/branch-merge-review/SKILL.md"),
            "**4b. Cross-validate Critical and High findings**",
            "**4c. Mark each Critical/High finding**",
            label="교차 검증 절",
        )

    def test_the_non_dismissal_rule_survives(self) -> None:
        """GREEN — 정규식 불일치가 곧 기각은 아니다.

        불일치를 기각으로 바꾸면 부재 기반 결함(누락된 CSRF 검사 등)이 조용히 사라진다.
        """
        marks = between(
            read("skills/branch-merge-review/SKILL.md"),
            "**4c. Mark each Critical/High finding**",
            "**4d.",
            label="판정 상태",
        )
        self.assertIn("Needs runtime/architectural verification", marks)
        self.assertIn("cannot confirm via static analysis alone", marks)

    def test_posix_and_powershell_cover_the_same_risks(self) -> None:
        """GREEN — 언어별 패턴 선택을 도입할 때 한쪽만 고치는 회귀를 잡는다.

        4b는 POSIX grep 블록과 PowerShell 폴백(`$patternFamilies`)을 모두 갖는다.
        POSIX 쪽만 갱신하고 해시테이블을 방치하면 Windows 네이티브 설치에서 교차 검증이
        조용히 뒤처진다. 두 블록을 나눠 **같은 위험 토큰을 각각** 갖는지 확인한다.
        """
        block = self.cross_validation_block()
        split = block.find("On native Windows")
        self.assertGreater(split, 0, "PowerShell 폴백 절이 사라졌다")
        posix, powershell = block[:split], block[split:]

        self.assertIn("$patternFamilies", powershell)
        self.assertIn("Select-String", powershell)
        for token in self.SHARED_RISK_TOKENS:
            with self.subTest(token=token):
                self.assertIn(token, posix, f"POSIX 블록에서 {token} 이 사라졌다")
                self.assertIn(token, powershell, f"PowerShell 블록에서 {token} 이 사라졌다")

    def test_posix_patterns_are_valid_shell(self) -> None:
        """PowerShell 쪽만 검사하고 POSIX 명령의 문법 게이트가 없었다.

        실제로 세 명령이 인용 오류로 실행조차 되지 않았다 — 큰따옴표 문자열 안에
        큰따옴표를 그대로 둔 형태다. 문서를 **원문 그대로** `bash -n` 에 넣는다:
        손으로 다시 타이핑하면 이스케이프가 조용히 고쳐져 결함이 사라진다.
        """
        if shutil.which("bash") is None:
            self.skipTest("bash 없음")
        block = self.cross_validation_block()
        posix = block.split("On native Windows", 1)[0]
        checked = 0
        for line in posix.splitlines():
            command = line.strip()
            if not command.startswith(("grep ", "rg ")) or "<implicated_files>" not in command:
                continue
            checked += 1
            probe = command.replace("<implicated_files>", "sample.txt")
            done = subprocess.run(
                ["bash", "-n", "-c", probe], capture_output=True, text=True, timeout=30
            )
            with self.subTest(command=command[:60]):
                self.assertEqual(
                    done.returncode, 0,
                    f"셸 문법 오류로 실행되지 않는다: {done.stderr.strip()[:120]}",
                )
        # 하한만 두면 추출이 절반으로 줄어도 통과한다. **보안 블록과 품질 블록 각각에서**
        # 언어별 커버리지를 본다 — 한쪽만 검사하면 다른 쪽이 통째로 사라져도 통과한다.
        security = between(posix, "**Security patterns**", "**Quality patterns**",
                           label="보안 패턴 블록")
        quality = posix.split("**Quality patterns**", 1)[1]
        for marker in ("*.php", "*.py", "*.go", "*.rs", "*.js"):
            with self.subTest(block="security", language=marker):
                self.assertIn(marker, security, f"{marker} 보안 패턴이 없다")
        for marker in ("*.php", "*.py", "*.go", "*.rs", "*.css"):
            with self.subTest(block="quality", language=marker):
                self.assertIn(marker, quality, f"{marker} 품질 패턴이 없다")
        self.assertGreaterEqual(checked, 30, f"추출된 명령이 {checked}개뿐이다")

    def test_powershell_patterns_actually_match(self) -> None:
        """GREEN — 토큰 존재가 아니라 **패턴을 실제로 실행**해 확인한다.

        해시테이블에 항상 실패하는 패턴(`(?!)` 등)을 넣어 무력화하는 회귀는 토큰 검사로는
        잡히지 않는다. 추출한 패턴을 컴파일해 표본 줄에 돌려 본다.
        """
        powershell = self.cross_validation_block().split("On native Windows", 1)[1]
        extracted = re.findall(
            r"^\s*(\w+)\s*=\s*@\((.*)\)\s*(?:#.*)?$", powershell, re.MULTILINE
        )
        self.assertTrue(extracted, "PowerShell 패턴 해시테이블을 추출하지 못했다")
        names = [name for name, _raw in extracted]
        # dict() 로 바로 받으면 중복 패밀리가 조용히 덮인다 — 그러면 하나가 사라져도 통과한다.
        self.assertEqual(
            len(names), len(set(names)), f"패밀리 이름이 중복된다: {names}"
        )
        families = dict(extracted)

        # **모든** 패밀리에 표본을 연결한다. 표본 없는 패밀리는 무력화돼도 드러나지 않는다.
        samples = {
            "SqlInjection": "$db->query(\'SELECT * FROM u WHERE id=\' . $_GET[\'id\']);",
            "Xss": "echo $_GET[\'name\'];",
            "Csrf": "$_POST['token']",
            "Session": "session_start();",
            "Upload": "move_uploaded_file($tmp, $dest);",
            "Secrets": "$password = 'hunter2';",
            "BrowserStorage": "localStorage.setItem('k', v)",
            "BackendQuality": "foreach ($rows as $row) { $db->query($sql); }",
            "FrontendQuality": "store.subscribe(fn)",
            "PythonSecurity": "cur.execute(f\"SELECT * FROM u WHERE id={uid}\")",
            "GoSecurity": 'exec.Command("sh", "-c", cmd)',
            "RustSecurity": "let v = map.get(&id).unwrap();",
            "PythonQuality": "except Exception:",
            "GoQuality": "f, _ := os.Open(path)",
            "RustQuality": "std::thread::sleep(d);",
        }
        self.assertEqual(
            set(samples), set(families),
            "패밀리와 표본이 1:1이어야 한다 — 표본 없는 패밀리는 무력화돼도 드러나지 않는다",
        )
        for family, sample in samples.items():
            with self.subTest(family=family):
                patterns = [
                    value.replace("''", "'")
                    for value in re.findall(r"'([^']*(?:''[^']*)*)'", families[family])
                ]
                self.assertTrue(patterns, f"{family} 에 패턴이 하나도 없다")
                broken = [pattern for pattern in patterns if not _compiles(pattern)]
                self.assertFalse(
                    broken, f"{family} 에 컴파일되지 않는 패턴이 있다: {broken}"
                )
                self.assertTrue(
                    any(re.search(pattern, sample, re.IGNORECASE) for pattern in patterns),
                    f"{family} 의 어떤 패턴도 표본 {sample!r} 을 잡지 못한다",
                )


class PhpInstallSupportBaseline(unittest.TestCase):
    """11 — 지원 셀이 조용히 꺼지지 않는다."""

    def test_review_skills_stay_installable_on_all_four_cells(self) -> None:
        """GREEN — 현행 설치 계약 테스트는 자료형만 검사한다.

        `assertTrue(all(isinstance(value, bool) ...))`는 `true`가 `false`로 바뀌어도
        통과하므로, 리뷰 스킬이 Windows나 Codex에서 빠져도 아무도 알아채지 못한다.
        여기서는 **값**을 고정한다.
        """
        catalog = json.loads(read("components.json"))
        by_name = {item["name"]: item for item in catalog["components"]}
        for name in REVIEW_SKILLS:
            with self.subTest(skill=name):
                support = by_name[name]["support"]
                for client in ("claude", "codex"):
                    for platform in ("posix", "windows"):
                        self.assertIs(
                            support[client][platform],
                            True,
                            f"{name} 가 {client}/{platform} 에서 빠졌다",
                        )


class PreconditionsForRedTests(unittest.TestCase):
    """RED 테스트의 전제조건 — `expectedFailure`가 흡수하지 못하는 자리에 둔다.

    `@unittest.expectedFailure`는 **모든 예외**를 예상 실패로 집계한다. RED가 읽는 파일이
    이동·삭제되어 `FileNotFoundError`가 나도, 마커가 사라져 탐색이 실패해도 스위트는 초록으로
    남고 게이트는 조용히 가짜가 된다. 그 전제를 여기서 GREEN으로 따로 지킨다.
    """

    def test_files_the_red_tests_read_exist(self) -> None:
        for relative_path in (
            "skills/branch-merge-review/SKILL.md",
            "skills/branch-merge-review/references/reviewer-prompts.md",
            "skills/code-quality-review/SKILL.md",
            *(f"skills/code-quality-review/references/{name}.md"
              for name in QUALITY_REFERENCES),
        ):
            with self.subTest(path=relative_path):
                self.assertTrue((ROOT / relative_path).is_file(), relative_path)

    #: (시작, 종료) — RED가 `between()`으로 탐색하는 구간. **순서까지** 지켜야 한다.
    #: 종료 마커가 시작보다 앞에 있으면 올바른 구현이 들어와도 영영 GREEN이 되지 않는다.
    NAVIGATION_RANGES = (
        ("| Agent | Skill invoked | Scope |", "- Every prompt embeds the Common Instructions"),
        ("**Failure handling**", "## Step 5"),
        ("| Category | Extensions / Filenames |", "If no files match a category"),
        ("CHANGED_SEC=$(", "sort -u)"),
        ("CHANGED_QA=$(", "sort -u)"),
    )

    def test_markers_the_red_tests_navigate_by_are_ordered(self) -> None:
        """마커 존재만으로는 부족하다 — 종료가 시작 뒤에 와야 구간이 성립한다."""
        skill = read("skills/branch-merge-review/SKILL.md")
        for start, end in self.NAVIGATION_RANGES:
            with self.subTest(start=start):
                start_at = skill.find(start)
                self.assertGreaterEqual(start_at, 0, f"시작 마커 소실: {start!r}")
                self.assertGreaterEqual(
                    skill.find(end, start_at + len(start)),
                    0,
                    f"종료 마커 {end!r} 가 시작 마커 뒤에 없다 — 구간이 성립하지 않는다",
                )

    def test_the_write_causing_instructions_are_still_present(self) -> None:
        """가드를 붙이는 대신 **명령을 지워서** RED를 통과시키는 우회를 막는다.

        1단계의 올바른 결과는 "명령이 읽기 전용에서 생략된다"이지 "명령이 사라진다"가
        아니다. 일반 모드에서는 설치도 자동수정도 계속 제공돼야 한다.
        """
        for reference_name, capability, _anchor, preserved in WRITE_CAUSING:
            with self.subTest(reference=reference_name, capability=capability):
                self.assertRegex(
                    code_blocks(quality_reference(reference_name)),
                    preserved,
                    f"{reference_name} 에서 {capability} 명령이 사라졌다 — 1단계의 올바른"
                    " 결과는 '읽기 전용에서 생략'이지 '명령 삭제'가 아니다."
                    " 산문에 이름만 남는 것은 명령이 아니다",
                )


class NodeReferenceSemanticsTest(unittest.TestCase):
    """3단계에서 고친 기술적 주장을 고정한다.

    이 파일들은 문법이 아니라 **런타임 의미**를 가르친다. 틀린 설명은 리뷰어가 잘못된 findings를
    내게 하고, 그 findings는 코드보다 오래 남는다. 각 항목은 검토에서 실제로 틀렸던 것이다.
    """

    def node_quality(self) -> str:
        return quality_reference("node-quality")

    def test_promise_all_is_not_described_as_leaving_rejections_unhandled(self) -> None:
        """`Promise.all` 은 모든 입력에 핸들러를 붙이므로 나중 거부도 handled 다.

        Node v24 실측에서 `unhandled=0`. "나중 거부가 unhandled 가 된다"고 쓰면 리뷰어가
        존재하지 않는 경고를 근거로 findings를 만든다. 실제 손실은 **호출자가 결과를 받지
        못한다**는 것이고, 경고가 없어서 조용하다는 점이 핵심이다.
        """
        section = between(
            self.node_quality(), "### `Promise.all`", "## 2. Error Propagation",
            label="Promise.all 절",
        )
        self.assertRegex(
            section,
            r"never receives their outcomes|호출자가[^\n]*받지 못",
            "손실을 '호출자가 결과를 받지 못함'으로 설명해야 한다",
        )
        self.assertRegex(
            section,
            r"not \*unhandled\*|unhandled 가 아니",
            "나중 거부가 unhandled 가 아니라는 사실이 빠지면 안 된다",
        )
        self.assertRegex(
            section,
            r"attaches a handler to every input|모든 입력에[^\n]*핸들러",
            "왜 unhandled 가 아닌지(모든 입력에 핸들러 부착)가 빠지면 근거 없는 주장이 된다",
        )
        self.assertRegex(
            section,
            r"loss is silent|no warning appears|조용",
            "경고가 없어 손실이 조용하다는 점이 이 항목의 실질이다",
        )
        self.assertNotRegex(
            section,
            r"becomes an unhandled rejection",
            "틀린 주장이 되살아났다",
        )

    def test_pipeline_caveat_names_the_settled_states(self) -> None:
        """`pipeline` 이 파괴하지 않는 것은 **이미 end/finish/close 를 낸** 스트림이다.

        "이미 오류난 스트림"으로 쓰면 오류 처리 의미를 반대로 가르친다.
        """
        section = between(
            self.node_quality(), "## 3. Streams & Backpressure", "## 4. Process Lifecycle",
            label="스트림 절",
        )
        self.assertRegex(section, r"`end`, `finish`, or `close`|end.*finish.*close")
        self.assertNotRegex(
            section, r"already\s+finished or errored", "틀린 주장이 되살아났다"
        )

    def test_type_checking_states_that_noemit_alone_is_not_read_only(self) -> None:
        """`tsc --noEmit` 도 `incremental`/`composite` 면 `.tsbuildinfo` 를 쓴다.

        1단계 읽기 전용 계약이 여기서 깨진다 — 검토가 약속한 무쓰기를 어기고 사용자 저장소에
        새 파일을 남긴다. tsconfig 를 먼저 읽으라는 지시와 composite 의 처리가 함께 있어야 한다.
        """
        toolchain = quality_reference("js-toolchain")
        section = between(
            toolchain, "### TypeScript", "### svelte-check", label="TypeScript 절"
        )
        self.assertIn(".tsbuildinfo", section)
        self.assertRegex(section, r"incremental")
        self.assertRegex(section, r"composite")
        self.assertRegex(
            section, r"skipped-read-only",
            "composite 프로젝트에서 무엇으로 기록할지가 없다",
        )
        self.assertNotRegex(
            section,
            r"`--noEmit` is what keeps this read-only safe",
            "틀린 전제가 되살아났다",
        )


class CheckerSelfTest(unittest.TestCase):
    """단언 자체를 검증한다 — 잘못된 구현이 **실제로** 통과하지 못하는지.

    기준선의 가치는 "현재 파일에서 통과한다"가 아니라 "틀린 구현을 거부한다"에 있다.
    실제 저장소 파일만 읽는 테스트는 그 거부력을 증명하지 못하므로, 여기서 합성한 나쁜
    입력을 체커에 먹여 본다. `tests/test_skill_contracts.py` 가 참조 파서를 같은 방식으로
    검증하는 관례를 따른다.
    """

    INSTALL = "```bash\nwget -q -O ~/.local/bin/phpstan phpstan.phar\n```"

    def test_a_command_without_the_marker_is_not_guarded(self) -> None:
        """1단계의 인수 조건이 여기에 걸려 있다."""
        for document in (
            self.INSTALL,
            # 산문으로 읽기 전용을 언급해도 계약 문구가 아니면 인정하지 않는다.
            f"This skill also supports read-only reviews.\n\n{self.INSTALL}",
            # 반대 지시는 물론이고, 자연어 부정 변형 일체를 판별하려 들지 않는다.
            f"In read-only mode, do not ever skip this.\n\n{self.INSTALL}",
            "생략하면 안 된다.\n\n" + self.INSTALL,
        ):
            with self.subTest(document=document.splitlines()[0]):
                self.assertTrue(
                    unguarded_occurrences(document, r"phpstan\.phar"),
                    "계약 문구 없이 가드로 인정되면 1단계 인수 조건이 가짜가 된다",
                )

    def test_the_contract_marker_is_a_guard(self) -> None:
        document = f"{READ_ONLY_MARKER}\n\n{self.INSTALL}"
        self.assertEqual(unguarded_occurrences(document, r"phpstan\.phar"), [])

    def test_a_marker_does_not_cover_a_distant_command(self) -> None:
        """능력별 연결 — 한 명령을 가드했다고 같은 절의 다른 명령까지 통과하면 안 된다.

        PHP 설치 네 건이 같은 `## 1. CLI Tool Setup` 절에 있으므로, 절 단위 불리언이면
        "PHPStan만 생략" 가드 하나로 네 항목이 모두 통과한다.
        """
        filler = "\n".join(f"# line {index}" for index in range(GUARD_WINDOW_LINES + 3))
        document = (
            f"{READ_ONLY_MARKER}\n"
            "```bash\nwget -O bin/phpstan phpstan.phar\n"
            f"{filler}\n"
            "curl -o bin/phpcs phpcs.phar\n```"
        )
        unguarded = unguarded_by_anchor(
            document, {"phpstan": r"phpstan\.phar", "phpcs": r"phpcs\.phar"}
        )
        self.assertEqual(unguarded["phpstan"], [])
        self.assertTrue(
            unguarded["phpcs"],
            "먼 곳의 마커가 다른 능력까지 덮으면 부분 구현이 통과한다",
        )

    def test_a_missing_command_is_reported_not_silently_passed(self) -> None:
        with self.assertRaises(AssertionError):
            unguarded_occurrences("nothing here", r"phpstan\.phar")

    def test_every_occurrence_needs_its_own_marker(self) -> None:
        """첫 발생만 검사하면 같은 명령을 뒤에 가드 없이 추가해도 통과한다."""
        document = (
            f"{READ_ONLY_MARKER}\n"
            "```bash\nwget -O bin/phpstan phpstan.phar\n"
            "wget -O bin/phpstan2 phpstan.phar\n```"
        )
        self.assertEqual(
            len(unguarded_occurrences(document, r"phpstan\.phar")),
            1,
            "두 번째 발생이 마커 없이 통과했다",
        )

    def test_one_marker_does_not_cover_consecutive_commands(self) -> None:
        """마커 하나 뒤에 여러 명령을 붙이는 우회 — 1:1 소비로 막는다."""
        document = (
            f"{READ_ONLY_MARKER}\n"
            "```bash\n"
            "wget -O bin/phpstan phpstan.phar\n"
            "wget -O bin/phpmd phpmd.phar\n"
            "```"
        )
        unguarded = unguarded_by_anchor(
            document, {"phpstan": r"phpstan\.phar", "phpmd": r"phpmd\.phar"}
        )
        self.assertEqual(unguarded["phpstan"], [])
        self.assertTrue(
            unguarded["phpmd"],
            "한 마커가 뒤따르는 두 명령을 함께 덮으면 부분 구현이 통과한다",
        )

    def test_a_partial_marker_is_not_the_contract(self) -> None:
        """접두어만 보면 `**Read-only:** skip nothing; always run it.` 이 가드로 통과한다."""
        for impostor in (
            "**Read-only:** skip nothing; always run it.",
            "**Read-only:** skip",
            "**Read-only:** skip this command.",
        ):
            with self.subTest(impostor=impostor):
                self.assertTrue(
                    unguarded_occurrences(f"{impostor}\n{self.INSTALL}", r"phpstan\.phar"),
                    "계약은 완전한 한 문장이어야 한다",
                )

    def test_the_guard_window_boundary_is_inclusive(self) -> None:
        """계획서의 "10줄 이내"와 구현이 어긋나지 않는지 고정한다."""
        filler = "\n".join(f"# line {index}" for index in range(GUARD_WINDOW_LINES - 1))
        inside = f"{READ_ONLY_MARKER}\n{filler}\nwget -O b phpstan.phar"
        self.assertEqual(unguarded_occurrences(inside, r"phpstan\.phar"), [])

        # 첫 불허 거리(11줄)를 고정한다 — 12줄만 보면 경계가 한 칸 밀려도 드러나지 않는다.
        farther = "\n".join(f"# line {index}" for index in range(GUARD_WINDOW_LINES))
        outside = f"{READ_ONLY_MARKER}\n{farther}\nwget -O b phpstan.phar"
        self.assertTrue(
            unguarded_occurrences(outside, r"phpstan\.phar"),
            "경계 바로 바깥(11줄)이 통과하면 창이 한 칸 밀린 것이다",
        )

    def test_a_marker_in_a_non_instructional_position_is_not_a_guard(self) -> None:
        """계약 문장을 그대로 써도 **읽히지 않는 자리**면 가드가 아니다.

        여러 명령 앞에 문구를 넣다 보면 코드 블록 안에 들어가기 쉽다. 그러면 실행 예제를
        깨뜨리면서 게이트만 통과한다. HTML 주석은 이 저장소가 비지시 텍스트로 취급한다.
        """
        for label, document in (
            (
                "펜스 안 벌거벗은 줄 (예제를 깨뜨린다)",
                f"```bash\n{READ_ONLY_MARKER}\nwget -O b phpstan.phar\n```",
            ),
            (
                "HTML 주석 안 (모델이 읽지 않는다)",
                f"<!--\n{READ_ONLY_MARKER}\n-->\n```bash\nwget -O b phpstan.phar\n```",
            ),
        ):
            with self.subTest(label=label):
                self.assertTrue(
                    unguarded_occurrences(document, r"phpstan\.phar"),
                    f"{label} 의 마커를 지시로 인정하면 안 된다",
                )

    def test_a_comment_marker_inside_a_block_is_a_guard(self) -> None:
        """코드 블록은 이 스킬들에서 실행할 명령 그 자체다.

        명령 바로 위 주석이 가장 국소적인 자리이고, 주석 형태라 예제도 깨지지 않는다.
        단 **접두는 그 언어의 주석 문법이어야** 한다.
        """
        for language, prefix in (("bash", "#"), ("js", "//"), ("php", "//")):
            with self.subTest(language=language):
                document = (
                    f"```{language}\n{prefix} {READ_ONLY_MARKER}\n"
                    "wget -O b phpstan.phar\n```"
                )
                self.assertEqual(unguarded_occurrences(document, r"phpstan\.phar"), [])

    def test_a_comment_prefix_from_another_language_is_not_a_guard(self) -> None:
        """Bash에서 `//` 는 주석이 아니라 명령이다 — 오류를 내고 다음 명령이 그대로 실행된다."""
        document = (
            f"```bash\n// {READ_ONLY_MARKER}\nwget -O b phpstan.phar\n```"
        )
        self.assertTrue(
            unguarded_occurrences(document, r"phpstan\.phar"),
            "무효한 주석 접두가 정상 가드로 통과하면 안 된다",
        )

    def test_languages_without_line_comments_admit_no_inline_marker(self) -> None:
        """JSON에는 주석이 없고 CSS 주석은 `/* … */` 다 — `//` 는 예제를 깨뜨린다."""
        for language in ("json", "css"):
            with self.subTest(language=language):
                document = (
                    f"```{language}\n// {READ_ONLY_MARKER}\n"
                    "wget -O b phpstan.phar\n```"
                )
                self.assertTrue(unguarded_occurrences(document, r"phpstan\.phar"))

    def test_scss_line_comments_are_a_valid_marker_form(self) -> None:
        """SCSS/Sass 는 `//` 단일 행 주석을 정식 지원한다 — 이 저장소도 그렇게 쓴다."""
        for language in ("scss", "sass"):
            with self.subTest(language=language):
                document = (
                    f"```{language}\n// {READ_ONLY_MARKER}\n"
                    "wget -O b phpstan.phar\n```"
                )
                self.assertEqual(unguarded_occurrences(document, r"phpstan\.phar"), [])

    def test_block_markers_use_the_same_fence_scanner(self) -> None:
        """블록 마커 경로가 다른 파서를 쓰면 표준 펜스에서 올바른 계약이 거부된다."""
        for label, fence_open, fence_close in (
            ("긴 닫는 펜스", "```bash", "````"),
            ("들여쓴 펜스", "  ```bash", "  ```"),
        ):
            with self.subTest(label=label):
                document = (
                    f"{READ_ONLY_BLOCK_MARKER}\n\n"
                    f"{fence_open}\nwget -O b phpstan.phar\n{fence_close}"
                )
                self.assertEqual(
                    unguarded_occurrences(document, r"phpstan\.phar"),
                    [],
                    "블록 마커 판정이 명령 단위와 같은 스캐너를 써야 한다",
                )

    def test_an_unclosed_fence_keeps_its_last_command(self) -> None:
        """닫는 펜스가 없으면 마지막 줄이 본문에서 사라져 맨 `npx` 검사가 뚫린다."""
        self.assertIn("npx eslint", code_blocks("```bash\nnpx eslint ."))

    def test_commonmark_fence_forms_are_recognised(self) -> None:
        """펜스를 놓치면 그 안의 벌거벗은 마커가 산문으로 취급돼 가드로 통과한다."""
        for label, document in (
            ("여는 펜스보다 긴 닫는 펜스",
             f"```bash\n{READ_ONLY_MARKER}\nwget -O b phpstan.phar\n````"),
            ("최대 3칸 들여쓰기",
             f"  ```bash\n  {READ_ONLY_MARKER}\n  wget -O b phpstan.phar\n  ```"),
        ):
            with self.subTest(label=label):
                self.assertTrue(unguarded_occurrences(document, r"phpstan\.phar"))

    def test_an_info_string_with_attributes_still_resolves_its_language(self) -> None:
        """`bash title=demo` 의 언어는 첫 낱말이다 — 못 뽑으면 유효한 마커를 거부한다."""
        document = (
            f"```bash title=demo\n# {READ_ONLY_MARKER}\n"
            "wget -O b phpstan.phar\n```"
        )
        self.assertEqual(unguarded_occurrences(document, r"phpstan\.phar"), [])

    def test_an_unlabelled_fence_admits_no_inline_marker(self) -> None:
        """언어를 모르면 어떤 접두가 주석인지 알 수 없다 — 펜스 밖 산문만 인정한다."""
        document = f"```\n# {READ_ONLY_MARKER}\nwget -O b phpstan.phar\n```"
        self.assertTrue(unguarded_occurrences(document, r"phpstan\.phar"))

    def test_a_backtick_inside_a_block_does_not_close_the_fence(self) -> None:
        """내용 속 백틱을 종결 펜스로 오인하면, 진짜 블록 안의 마커가 가드로 인정된다."""
        document = (
            "```bash\n"
            "echo \'inline ``` in content\'\n"
            f"{READ_ONLY_MARKER}\n"
            "wget -O b phpstan.phar\n"
            "```"
        )
        self.assertTrue(
            unguarded_occurrences(document, r"phpstan\.phar"),
            "펜스 안 마커가 인정되면 안 된다",
        )

    def test_a_block_marker_covers_every_command_in_that_block(self) -> None:
        """범위를 명시한 블록 마커는 그 블록 전체를 덮는다 — 부분 가드가 아니다."""
        document = (
            f"{READ_ONLY_BLOCK_MARKER}\n\n"
            "```bash\n"
            "wget -O b phpstan.phar\n"
            "wget -O b phpmd.phar\n"
            "```"
        )
        unguarded = unguarded_by_anchor(
            document, {"phpstan": r"phpstan\.phar", "phpmd": r"phpmd\.phar"}
        )
        self.assertEqual(unguarded["phpstan"], [])
        self.assertEqual(unguarded["phpmd"], [])

    def test_prose_between_a_block_marker_and_its_fence_breaks_the_link(self) -> None:
        """사이에 산문이 끼면 그 산문이 계약을 뒤집을 수 있다 — 공백만 허용한다."""
        document = (
            f"{READ_ONLY_BLOCK_MARKER}\n\n"
            "This paragraph says to run the commands anyway.\n\n"
            "```bash\nwget -O b phpstan.phar\n```"
        )
        self.assertTrue(unguarded_occurrences(document, r"phpstan\.phar"))

    def test_a_block_marker_does_not_cover_the_next_block(self) -> None:
        """바로 뒤 블록만 덮는다 — 사이에 다른 블록이 끼면 어느 쪽인지 알 수 없다."""
        document = (
            f"{READ_ONLY_BLOCK_MARKER}\n\n"
            "```bash\nwget -O b phpstan.phar\n```\n\n"
            "```bash\nwget -O b phpmd.phar\n```"
        )
        unguarded = unguarded_by_anchor(
            document, {"phpstan": r"phpstan\.phar", "phpmd": r"phpmd\.phar"}
        )
        self.assertEqual(unguarded["phpstan"], [])
        self.assertTrue(unguarded["phpmd"], "두 번째 블록까지 덮으면 안 된다")

    def test_a_command_scoped_marker_does_not_cover_a_block(self) -> None:
        """명령 단위 문구를 블록 앞에 두는 것으로 블록 전체를 덮을 수 없다."""
        document = (
            f"{READ_ONLY_MARKER}\n\n"
            "```bash\n"
            "wget -O b phpstan.phar\n"
            "wget -O b phpmd.phar\n"
            "```"
        )
        unguarded = unguarded_by_anchor(
            document, {"phpstan": r"phpstan\.phar", "phpmd": r"phpmd\.phar"}
        )
        self.assertEqual(len(unguarded["phpstan"]) + len(unguarded["phpmd"]), 1)

    def test_a_marker_inside_a_code_comment_is_not_an_instruction(self) -> None:
        document = (
            "```bash\n"
            f"# {READ_ONLY_MARKER} this\n"
            "wget -O bin/phpstan phpstan.phar\n```"
        )
        self.assertTrue(
            unguarded_occurrences(document, r"phpstan\.phar"),
            "코드 주석 속 마커를 지시로 인정하면 안 된다",
        )

    def test_naming_a_tool_is_not_invoking_it(self) -> None:
        for prose in ("Do not run phpstan on generated files.", "phpstan should not be run."):
            with self.subTest(prose=prose):
                self.assertFalse(invoked_as_command(f"```bash\n{prose}\n```", "phpstan"))

    def test_real_invocation_spellings_are_accepted(self) -> None:
        """정본 수렴 시 올바른 명령 표현을 제한하지 않아야 한다."""
        for spelling, fence in (
            ("phpcs --standard=PSR12 src/", "```"),
            ("$PHP_CMD $(command -v phpstan) analyse src", "```"),
            ("vendor/bin/phpstan analyse src", "```"),
            ("php phpstan.phar analyse src", "```"),
            ("phpcpd src/", "~~~"),
        ):
            tool = "phpcs" if spelling.startswith("phpcs") else (
                "phpcpd" if "phpcpd" in spelling else "phpstan"
            )
            with self.subTest(spelling=spelling):
                self.assertTrue(
                    invoked_as_command(f"{fence}bash\n{spelling}\n{fence}", tool),
                    spelling,
                )

    def test_mentioning_a_verdict_is_not_prohibiting_it(self) -> None:
        for allowance in (
            "If a reviewer is unavailable, proceed and you may still pick Ready to merge.",
            "Ready to merge is not prohibited.",
            "Ready to merge is not actually prohibited.",
        ):
            with self.subTest(allowance=allowance):
                self.assertFalse(prohibits(allowance, "Ready to merge"))

    def test_a_negated_verdict_is_prohibiting_it(self) -> None:
        for gate in (
            "When a required PHP reviewer did not complete, Ready to merge is not available.",
            "PHP 리뷰어가 실패하면 `Ready to merge` 판정은 불가하다.",
        ):
            with self.subTest(gate=gate):
                self.assertTrue(prohibits(gate, "Ready to merge"))

    def test_a_negated_declaration_is_not_affirmative(self) -> None:
        for negated in (
            "Never dispatch per detected backend language.",
            "Dispatching per detected backend language is prohibited.",
        ):
            with self.subTest(negated=negated):
                self.assertFalse(
                    states_affirmatively(negated, r"per detected backend language")
                )
        self.assertTrue(
            states_affirmatively(
                "Dispatch one quality reviewer per detected backend language.",
                r"per detected backend language",
            )
        )

    def test_between_reports_an_inverted_range(self) -> None:
        """종료 마커가 시작보다 앞이면 조용히 통과하지 않고 진단과 함께 실패해야 한다.

        실제로 이 결함이 한 번 들어왔다 — 로스터 표의 종료 마커가 표보다 앞에 있어,
        올바른 구현이 들어와도 영영 GREEN이 되지 않는 죽은 게이트였다.
        """
        with self.assertRaises(AssertionError) as caught:
            between("END\n...\nSTART\n...", "START", "END", label="역순 구간")
        self.assertIn("종료 마커", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
