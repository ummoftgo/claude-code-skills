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
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REVIEW_SKILLS = ("code-quality-review", "web-security-review", "branch-merge-review")

QUALITY_REFERENCES = ("php-quality", "js-quality", "css-quality")

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
    ("js-quality", "ESLint 설치", r"npm install[^\n]*\beslint\b", r"npm install[^\n]*\beslint\b"),
    ("js-quality", "Biome 설치", r"npm install[^\n]*@biomejs/biome", r"npm install[^\n]*@biomejs/biome"),
    ("js-quality", "Biome 초기화", r"@biomejs/biome init", r"@biomejs/biome init"),
    ("js-quality", "Oxlint 설치", r"npm install[^\n]*\boxlint\b", r"npm install[^\n]*\boxlint\b"),
    ("js-quality", "svelte-check 설치", r"npm install[^\n]*svelte-check", r"npm install[^\n]*svelte-check"),
    ("js-quality", "knip 설치", r"npm install[^\n]*\bknip\b", r"npm install[^\n]*\bknip\b"),
    ("js-quality", "ESLint 보고서 출력", r"-o \S+\.json", r"-o \S+\.json"),
    ("js-quality", "ESLint 자동수정", r"eslint[^\n]*--fix", r"eslint[^\n]*--fix"),
    ("js-quality", "Biome 자동수정", r"biome[^\n]*--write", r"biome[^\n]*--write"),
    ("js-quality", "Oxlint 자동수정", r"oxlint[^\n]*--fix", r"oxlint[^\n]*--fix"),
    ("js-quality", "knip 자동수정", r"knip[^\n]*--fix", r"knip[^\n]*--fix"),
    ("css-quality", "Stylelint 설치", r"(?m)npm install[^\n]*\bstylelint$", r"(?m)npm install[^\n]*\bstylelint$"),
    ("css-quality", "Stylelint 표준 설정 설치", r"(?m)npm install[^\n]*stylelint-config-standard$", r"(?m)npm install[^\n]*stylelint-config-standard$"),
    ("css-quality", "Stylelint SCSS 설정 설치", r"npm install[^\n]*stylelint-config-standard-scss", r"npm install[^\n]*stylelint-config-standard-scss"),
    # 설정 생성은 지시가 산문, 내용은 코드 블록 — 앵커와 보존이 갈리는 유일한 항목.
    ("css-quality", "Stylelint 설정 생성", r"create a minimal one", r'"extends": \[[^\]]*stylelint-config-standard'),
    ("css-quality", "Stylelint 자동수정", r"stylelint[^\n]*--fix", r"stylelint[^\n]*--fix"),
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
    "**Read-only:** skip this command; record it as `skipped (not installed)`."
)

#: 마커를 명령과 연결하는 창. 절 단위 불리언이면 같은 절의 한 명령만 가드해도 나머지가 함께
#: 통과한다(PHP 설치 네 건이 같은 `## 1. CLI Tool Setup` 절에 있다).
GUARD_WINDOW_LINES = 10


def non_instructional_spans(text: str) -> list[tuple[int, int]]:
    """지시로 읽히지 않는 구간 — 펜스 코드 블록과 HTML 주석의 (시작, 끝) 오프셋.

    이 저장소는 HTML 주석을 비지시 텍스트로 취급한다(`tests/test_skill_contracts.py` 의
    `instructional_text()`). 코드 블록 안의 문장도 실행 예제이지 모델에 대한 지시가 아니다.
    """
    spans: list[tuple[int, int]] = []
    for match in re.finditer(
        r"^(```+|~~~+)[^\n]*\n.*?^\1", text, re.DOTALL | re.MULTILINE
    ):
        spans.append((match.start(), match.end()))
    for match in re.finditer(r"<!--.*?-->", text, re.DOTALL):
        spans.append((match.start(), match.end()))
    return spans


def marker_lines(text: str) -> list[int]:
    """계약 문구가 **지시로 읽히는 자리에** 독립된 줄로 놓인 위치(문자 오프셋).

    세 가지를 함께 요구한다.

    * 줄 전체가 계약 문장과 **완전히 일치**해야 한다. 접두어만 보면
      `**Read-only:** skip nothing; always run it.` 같은 반대 문구가 통과한다.
    * 코드 펜스 안이면 안 된다 — 실행 예제를 깨뜨리면서 게이트만 통과시키는 자리다.
    * HTML 주석 안이면 안 된다 — 이 저장소가 비지시 텍스트로 취급하므로 모델이 읽지 않는다.
    """
    spans = non_instructional_spans(text)
    offsets = []
    position = 0
    for line in text.splitlines(keepends=True):
        if " ".join(line.split()) == READ_ONLY_MARKER and not any(
            start <= position < end for start, end in spans
        ):
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
    consumed: set[int] = set()
    unguarded: dict[str, list[int]] = {name: [] for name in anchors}
    for position, name in occurrences:
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
    """펜스 코드 블록만 이어붙인다. 산문과 실행 지시를 가르는 경계다."""
    return "\n".join(
        block
        for _fence, block in re.findall(
            r"^(```+|~~~+)[^\n]*\n(.*?)^\1", text, re.DOTALL | re.MULTILINE
        )
    )


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

    한계(수용): 부정어를 같은 단락 전체에서 찾으므로, 무관한 부정어가 있는 단락은 보수적으로
    거부한다. 거짓 음성은 RED가 늦게 열릴 뿐이지만 거짓 양성은 게이트를 뚫는다.
    """
    negative = re.compile(
        r"never|not |없이|말고|않는다|않는|금지|제외|exclude|prohibit", re.IGNORECASE
    )
    for statement in statements(text):
        if not re.search(phrase_pattern, statement, re.IGNORECASE):
            continue
        if negative.search(statement):
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
        backend = rows.get("**Backend**", "")
        self.assertIn("`*.php`", backend)
        # Backend 판정이 매니페스트를 요구하게 되면 composer 없는 저장소가 빠진다.
        frontend = rows.get("**Frontend**", "")
        self.assertNotIn("`*.php`", frontend)

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

    @unittest.expectedFailure
    def test_rename_away_from_php_uses_the_previous_path(self) -> None:
        """RED → 3단계 — rename의 이전 경로가 **읽히기만 하고 쓰이지 않는다**.

        현행 수집기는 이전 경로 레코드를 `_previous`로 소비한 뒤 버리고, 커밋 범위 수집은
        새 경로만 산출한다. `.php`가 `.ts`로 옮겨가며 인증 로직이 사라져도 이전 경로의
        PHP 보안 문맥이 리뷰에 들어오지 않는다.

        문장이 아니라 **변수가 실제로 사용되는지**를 본다 — 올바른 구현을 설명하는 산문만
        추가해서는 통과할 수 없다.
        """
        skill = read("skills/branch-merge-review/SKILL.md")
        # 이전 경로를 버리는 현행 표기(`_previous`)가 사라지고, 실제로 범위에 합류해야 한다.
        self.assertNotIn("_previous", skill)
        self.assertTrue(
            states_affirmatively(
                skill, r"CHANGED_SEC[^\n]*previous|previous path[^\n]*CHANGED_SEC"
            ),
            "이전 경로가 보안 범위에 합류한다고 긍정형으로 선언되지 않았다",
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

    @unittest.expectedFailure
    def test_php_and_node_get_separate_quality_reviewers(self) -> None:
        """RED → 3단계 — Backend Quality 리뷰어가 하나뿐이라 한 언어가 다른 언어를 덮는다.

        현행은 정확히 3인 고정 로스터이고 Agent A 행이 `php-quality.md`를 직접 지정한다.
        `{language}` 치환만 하면 PHP+Node 저장소에서 한쪽 리뷰가 사라진다.

        산문이 아니라 **로스터 표의 구조**를 본다 — Agent A 행이 특정 언어 참조를 고정하지
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

    @unittest.expectedFailure
    def test_incomplete_php_review_blocks_ready_to_merge(self) -> None:
        """RED → 3단계 — PHP 리뷰어가 실패해도 정상 승인이 나올 수 있다.

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
            r"reference[^\n]*not loaded|참조[^\n]*로드",
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
        for tool in ("phpstan", "phpcs", "phpmd", "phpcpd"):
            with self.subTest(tool=tool):
                self.assertTrue(
                    invoked_as_command(run_section, tool),
                    f"{tool} 이 실행 절에서 명령으로 호출되지 않는다",
                )

    def test_normal_mode_still_installs_missing_tools(self) -> None:
        """GREEN — 읽기 전용 조건을 잘못 걸어 일반 모드까지 죽이면 리뷰가 빈 껍데기가 된다.

        일반 모드에서 도구가 없으면 설치한다는 지시가 살아 있어야 한다. 이것이 사라지면
        리뷰는 `skipped (not installed)`만 잔뜩 내고 실제 검사를 하지 않는다.
        """
        skill = read("skills/code-quality-review/SKILL.md")
        self.assertIn("if not, install per the reference file instructions", skill)
        self.assertIn("unless read-only mode applies", skill)
        self.assertIn("skipped (not installed)", skill)

    @unittest.expectedFailure
    def test_php_version_resolution_has_a_single_source(self) -> None:
        """RED → 3단계 — 버전 해석 네 조각이 본문과 참조에 흩어져 있다.

        `SRC_DIR` PSR-4 도출은 본문에만 있어 완전한 중복도 아니다. 권위 문구만 붙이면
        모델이 비권위 사본도 계속 읽으므로 충돌이 남는다.

        토큰 하나가 아니라 **네 조각 전부가 같은 한 파일에** 있는지를 본다.
        """
        locations = {
            "SKILL.md": read("skills/code-quality-review/SKILL.md"),
            "php-quality.md": quality_reference("php-quality"),
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

    @unittest.expectedFailure
    def test_every_write_causing_instruction_carries_a_read_only_guard(self) -> None:
        """RED → 1단계 — 쓰기를 유발하는 **명령 각각**이 읽기 전용 가드를 동반해야 한다.

        본문(`SKILL.md`)은 읽기 전용에서 설치·수정·모든 파일 쓰기를 금지하는 우선 규칙을
        선언하지만, 본문이 "먼저 읽으라"고 지시하는 참조에는 조건 없는 쓰기 명령이 있다.
        Step 2의 게이트는 "도구 설치"만 가리므로 설정 생성·자동수정·보고서 출력은 걸리지 않는다.

        **파일 상단에 "read-only" 한 줄을 추가하는 것으로는 통과할 수 없다** — 각 명령이
        놓인 절이 가드를 갖췄는지 확인한다. 1단계의 실효 완료 조건이므로 여기가 느슨하면
        불완전한 구현이 GREEN으로 전환된다.
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
        standalone = between(
            read("skills/web-security-review/SKILL.md"),
            "Load these before proceeding:",
            "## Operating Modes",
            label="web-security-review 로드 지시",
        )
        self.assertIn("`references/php-backend-security.md`", standalone)

        dispatched = between(
            read("skills/branch-merge-review/references/reviewer-prompts.md"),
            "**Skill to use**: Invoke `web-security-review`",
            "**Scope**",
            label="보안 리뷰어 로드 지시",
        )
        self.assertIn("references/php-backend-security.md", dispatched)


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

        27개 명령 앞에 문구를 넣다 보면 코드 블록 안에 들어가기 쉽다. 그러면 실행 예제를
        깨뜨리면서 게이트만 통과한다. HTML 주석은 이 저장소가 비지시 텍스트로 취급한다.
        """
        for label, document in (
            (
                "코드 펜스 안",
                f"```bash\n{READ_ONLY_MARKER}\nwget -O b phpstan.phar\n```",
            ),
            (
                "HTML 주석 안",
                f"<!--\n{READ_ONLY_MARKER}\n-->\n```bash\nwget -O b phpstan.phar\n```",
            ),
        ):
            with self.subTest(label=label):
                self.assertTrue(
                    unguarded_occurrences(document, r"phpstan\.phar"),
                    f"{label} 의 마커를 지시로 인정하면 안 된다",
                )

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
