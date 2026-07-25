# 팀 AI 스킬·에이전트 모음

Claude Desktop Code와 Codex 앱/CLI에서 함께 사용하는 스킬, 에이전트, 워크플로우 훅 모음입니다. Windows 네이티브 설치와 WSL/Linux 설치를 분리하며, 설치 대상은 [`components.json`](./components.json) 한 곳에서 관리합니다.

## 설치 환경 선택

| 실행 환경 | 설치기 | 대상 |
|---|---|---|
| Windows 네이티브 PowerShell 5.1+ | `.\install.ps1` | Windows Claude Desktop Code, Windows Codex 앱/CLI |
| WSL 또는 Linux 셸 | `bash install.sh` | 해당 Linux 홈을 사용하는 Claude Code/Codex |

Windows 앱이 WSL 배포판을 작업 환경으로 사용한다면 Windows 설치기를 섞지 말고 배포판 안에서 `bash install.sh`를 실행하세요. 반대로 Windows 네이티브 앱·CLI에는 `.\install.ps1`을 사용합니다.

설치기는 저장소의 스킬·에이전트·훅만 관리합니다. Claude 플러그인, Node.js, PHP, Codex CLI, Context7, agent-browser 같은 외부 도구는 자동 설치하지 않고 감지 결과와 설치 명령만 보여 줍니다.

## 빠른 시작

### Windows 네이티브

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install.ps1
```

대화형으로 다음을 선택합니다.

- Claude Desktop Code, Codex 또는 둘 다
- 전역 또는 프로젝트 범위
- 스킬 복사 또는 심볼릭 링크
- 전역 범위의 워크플로우 훅

스킬 기본값은 복사입니다. 심볼릭 링크는 저장소와 대상이 모두 Windows 로컬 경로일 때만 선택할 수 있으며, 권한 문제로 링크 생성이 실패하면 복사로 안전하게 전환합니다. 에이전트와 훅은 항상 복사합니다.

제거:

```powershell
.\uninstall.ps1
```

### WSL/Linux

```bash
bash install.sh
```

제거:

```bash
bash uninstall.sh
```

## 설치 경로

| 범위 | Claude | Codex |
|---|---|---|
| Windows/POSIX 전역 스킬 | `~/.claude/skills/` | `~/.agents/skills/` |
| 전역 에이전트 | `~/.claude/agents/*.md` | `~/.codex/agents/*.toml` |
| 전역 훅 파일 | `~/.claude/hooks/` | `~/.codex/hooks/` |
| 전역 훅 설정 | `~/.claude/settings.json` | `~/.codex/hooks.json` |
| 프로젝트 스킬 | `<project>/.claude/skills/` | `<project>/.agents/skills/` |
| 프로젝트 에이전트 | `<project>/.claude/agents/*.md` | `<project>/.codex/agents/*.toml` |

Windows 프로젝트 범위는 스킬과 에이전트만 설치합니다. Windows 훅은 전역 범위에서만 설치합니다.

기존 Codex 스킬 경로 `~/.codex/skills/local/`은 설치기가 안전하게 이전합니다. 저장소 링크 대상 또는 매니페스트 해시로 소유가 확인되고 새 `.agents/skills/` 대상에 충돌이 없을 때만 복사 후 이전 항목을 제거합니다. 수정됨·미확인·충돌 항목은 그대로 보존합니다.

## 제공 컴포넌트

### 스킬

| 스킬 | Claude | Codex | 역할 |
|---|:---:|:---:|---|
| `use-context7` | ✓ | ✓ | 외부 라이브러리 코드 전 최신 문서 조회 |
| `plan-and-build` | ✓ | ✓ | 기능 사양·계획·TDD·병렬화 판단 |
| `evidence-first-review` | ✓ | ✓ | 컨텍스트와 현재 코드·원본 데이터에 근거한 읽기 전용 검토 |
| `safe-checkpoint` | ✓ | ✓ | 요청 범위와 쓰기 권한을 확인하는 커밋·인수인계 체크포인트 |
| `systematic-debugging` | ✓ | ✓ | 재현과 증거 기반 디버깅 |
| `web-security-review` | ✓ | ✓ | PHP/프론트엔드 보안 검토 |
| `web-parallel-dispatch` | ✓ | ✓ | 승인 기반 병렬 구현 분할 |
| `code-quality-review` | ✓ | ✓ | 코드 품질·성능 검토 |
| `branch-merge-review` | ✓ | ✓ | 머지 전 다중 리뷰 |
| `web-browser-preview` | ✓ | ✓ | Windows/WSL Chrome CDP 미리보기 |
| `report-output` | ✓ | ✓ | 리포트 출력 시 md/HTML 포맷 선택과 자체 완결형 HTML 리포트 생성 |
| `codex-delegate` | ✓ | — | Claude에서 Codex로 위임 |

### 트리거 예시

| 요청 예시 | 스킬 |
|---|---|
| “새 인증 기능을 구현해줘” | `plan-and-build` |
| “컨텍스트 문서부터 읽고 수정 없이 이전 지적을 재검토해줘” | `evidence-first-review` |
| “해당 변경만 커밋하고 내일 재개할 인수인계를 남겨줘” | `safe-checkpoint` |
| “원인이 불명확한 오류를 분석하고 고쳐줘” | `systematic-debugging` |
| “머지 전에 브랜치 리뷰해줘” | `branch-merge-review` |
| “분석 결과를 리포트로 출력해줘” | `report-output` |

### 리뷰 스킬 라우팅

리뷰 스킬은 네 개입니다. 자연어 트리거는 본질적으로 겹칩니다 — "이 PR을 보안 리뷰해줘"는 범위와 주제에, "이 PR의 지난 지적만 재검토해줘"는 범위와 작업 모드에 동시에 걸립니다. 그래서 이 표는 "겹치지 않는다"를 주장하지 않고, **겹침을 결정론적으로 해소하는 우선순위 규칙**입니다. 축의 순서는 다음으로 고정합니다.

**① 작업 모드 → ② 범위 → ③ 주제.** 앞 단계에서 결론이 나면 뒤 단계는 보지 않습니다.

#### 1단계 — 작업 모드 (범위·주제보다 우선)

| 작업 모드 | 요청 예시 | 스킬 |
|---|---|---|
| 재검토 (`recheck`) — 이전 지적·이전 리포트를 다시 확인 | “이 PR의 지난 리뷰 지적만 재검토해줘” | `evidence-first-review` |
| 최종 승인 (`final-approval`) — must-fix 조건 재검증과 승인 판정 | “이 PR의 이전 지적을 재검토하고 최종 승인해줘” | `evidence-first-review` |
| 증거 우선 검증 — 특정 주장 대조, 원본 JSON/CSV/DB·비Git 디렉터리 점검 | “컨텍스트 문서의 주장을 원본 데이터로 검증해줘” | `evidence-first-review` |
| 최초 검토 (`initial`) — 새 문제를 찾는 첫 리뷰 | “브랜치 리뷰해줘” | 2단계로 |

**범위가 PR·브랜치여도 작업 모드가 이깁니다.** `evidence-first-review`만 이전 지적을 1:1 원장으로 추적해 `resolved`·`partially resolved`·`unresolved`·`regressed`로 분류하고, must-fix 조건을 재검증해 `approved`·`conditionally approved`·`hold`를 판정합니다. `branch-merge-review`에는 이 모드가 없습니다 — 3인 병렬 리뷰어로 **신규 발견**을 하는 스킬입니다. 재검토·승인 요청을 범위만 보고 `branch-merge-review`로 보내면 사용자가 요청한 산출물(지적별 상태 분류, 승인 판정)이 나오지 않습니다.

#### 2단계 — 최초 검토일 때의 범위 (주제보다 우선)

| 요청 범위 | 3단계(주제) 적용 | 스킬 |
|---|---|---|
| PR·브랜치·머지 diff 전체 (커밋된 변경) | 보지 않음 — 품질·보안·혼합 무엇이든 동일 | `branch-merge-review` |
| 미커밋 작업 전체 (staged·unstaged·untracked) | 경로 목록을 먼저 확정한 뒤 주제로 결정 | 아래 “미커밋 변경 전체” 참고 |
| 브랜치 diff보다 좁음 (단일 파일, 특정 기능, 특정 엔드포인트) | 보안이 주제 | `web-security-review` |
| 브랜치 diff보다 좁음 | 품질·리팩터링·성능이 주제 | `code-quality-review` |
| 불분명 | 대상이 불분명한 일반 “리뷰해줘” | 현재 대상 문맥으로 판단하고, 모호하면 사용자에게 묻습니다 |

**범위가 주제보다 우선합니다.** "이 PR을 보안 리뷰해줘"처럼 보안이 명시돼도 범위가 브랜치·PR 전체이면 `branch-merge-review`를 사용합니다. `branch-merge-review`가 내부에서 `web-security-review`를 보안 리뷰어로 디스패치하므로 보안 검토가 빠지지 않습니다. `web-security-review`와 `code-quality-review`를 직접 호출하는 것은 범위가 브랜치 diff보다 좁을 때입니다. 두 스킬의 description도 브랜치·PR 전체 검토는 `branch-merge-review`로 넘기도록 명시하고 있습니다.

#### 미커밋 변경 전체 — 자동 수집하는 리뷰 스킬이 없습니다

"지금 작업 중인 변경 전체를 검토해줘"는 흔한 요청이지만, **staged·unstaged·untracked 집합을 스스로 수집하는 리뷰 스킬은 없습니다.** 각 스킬의 실제 수집 방식은 다음과 같습니다.

| 스킬 | 실제 수집 범위 | 미커밋 변경 |
|---|---|---|
| `branch-merge-review` | `git log <base>..HEAD --no-merges --name-only`로 이 브랜치가 건드린 파일을 모으고, 각 경로를 `git diff <merge-base> HEAD`로 다시 걸러 품질 범위(`--diff-filter=d` — 삭제만 제외)와 보안 범위(필터 없음 — 전체)로 나눔 (main을 중간에 머지해도 범위가 새지 않도록 일부러 일괄 `git diff <merge-base> HEAD`를 쓰지 않습니다) | **불가** — `HEAD`까지만 비교하므로 미커밋 변경이 보이지 않고, 커밋이 없으면 “Nothing to review”로 종료 |
| `code-quality-review` | Git을 쓰지 않고 **현재 작업 트리 파일 내용**을 CLI 도구·패턴으로 검사 | 파일 경로를 받으면 검토 가능 (변경 집합을 스스로 열거하지는 않음) |
| `web-security-review` | Git을 쓰지 않고 지정된 파일·기능의 **현재 내용**을 점검 (“Identify scope: 불분명하면 질문”) | 파일 경로를 받으면 검토 가능 (변경 집합을 스스로 열거하지는 않음) |
| `evidence-first-review` | 현재 파일·설정을 1순위 증거로 사용하고 diff는 범위에 포함될 때만 사용, 비Git 디렉터리도 직접 점검 | 특정 주장 검증·재검토 모드에서 현재 파일 기준으로 가능 |

따라서 절차는 **경로 열거 → 주제로 라우팅**입니다.

1. **경로를 NUL 구분으로 수집하고 세 갈래로 나눕니다.** 아래 한 블록이 staged·unstaged·untracked를 **개별 파일 단위로** 모두 모으면서, 내용으로 검토할 경로(`CONTENT`), diff로 검토할 삭제 경로(`DELETED`), 그리고 **안전하게 검토할 수 없어 중단해야 하는 경로**(`BLOCKED`)를 분리합니다.

   ```bash
   CONTENT=()   # 현재 파일 내용으로 검토 — code-quality-review / web-security-review
   DELETED=()   # 현재 내용이 없음 — diff로 검토 (아래 3번)
   BLOCKED=()   # index와 worktree가 갈린 혼합 상태 / 미해결 충돌 — 검토 중단

   while IFS= read -r -d '' entry; do
     status=${entry:0:2}
     path=${entry:3}
     # 이름변경·복사 항목은 "XY 새경로\0이전경로\0" 두 레코드다 — 이전 경로 레코드를 소비한다.
     # 상태는 정확히 두 칸(X=index, Y=worktree)이므로 *R*|*C*로 두 칸을 모두 검사한다.
     case "$status" in
       *R*|*C*) IFS= read -r -d '' _previous || _previous="" ;;
     esac
     # allowlist — "두 칸 중 정확히 한 칸만 채워진" 상태만 통과시킨다. 나머지는 전부 BLOCKED.
     case "$status" in
       '??')              CONTENT+=("$path") ;;   # untracked
       *U*)               BLOCKED+=("$status $path") ;;   # 미해결 충돌
       'D '|' D')         DELETED+=("$path") ;;   # 순수 삭제 — diff 검토
       ' '[!\ ]|[!\ ]' ') CONTENT+=("$path") ;;   # 한 칸만 채워짐 → 현재 파일이 곧 커밋될 내용
       *)                 BLOCKED+=("$status $path") ;;   # 두 칸 모두 채워짐 (MM/AM/RM/MT/AD/RD/MD…)
     esac
   done < <(git status --porcelain=v1 -z --untracked-files=all)

   if [ ${#BLOCKED[@]} -gt 0 ]; then
     printf '검토를 진행할 수 없습니다 — index와 worktree가 갈렸거나 미해결인 경로 %d건:\n' "${#BLOCKED[@]}"
     printf '  %s\n' "${BLOCKED[@]}"
     echo '`git add <경로>`로 두 칸을 합치거나(worktree 내용을 채택합니다), 커밋·stash·충돌 해소 후 다시 요청해 주세요.'
     exit 1
   fi
   ```

   목록을 사용자와 확정한 뒤 2·3번으로 넘깁니다. 다음 네 가지를 지키세요.
   - `--untracked-files=all`을 생략하지 마세요. 기본값은 새로 만든 디렉터리를 `dir/` 한 줄로 접어 그 안의 파일을 열거하지 않으므로, 검토 대상 파일이 조용히 빠집니다. 접히는지 여부는 상위 디렉터리에 추적 중인 파일이 있는지에 따라 달라져서 눈으로는 누락을 알아채기 어렵습니다.
   - **`| cut -c4-`로 상태 코드만 잘라내는 방식은 쓰지 마세요.** 개행 구분 출력에서 이름변경 항목은 `R  "old name.md" -> "new name.md"` **한 줄**이라 잘라내도 `"old name.md" -> "new name.md"`가 통째로 남고, 공백·비ASCII 경로는 Git이 큰따옴표로 감싸 이스케이프하므로 `"\355\225\234\352\270\200 \355\214\214\354\235\274.md"` 같은 문자열이 그대로 남습니다. 그 목록을 리뷰어에게 넘기면 **존재하지 않는 경로를 검토하게 됩니다.** `-z`는 레코드를 NUL로 구분하고 **경로를 인용·이스케이프하지 않으므로** 두 문제가 함께 사라집니다. 대신 이름변경·복사 항목이 두 개의 NUL 필드를 쓰므로 위 루프처럼 이전 경로 레코드를 반드시 소비해야 합니다.

     이때 **상태의 두 칸을 모두 보세요.** 상태는 `XY` 두 칸이고 X는 index, Y는 worktree입니다. worktree 쪽 이름변경은 **첫 칸이 공백인 ` R`** 로 나옵니다 — 재현은 **파일시스템 `mv` 후 새 경로에 `git add -N`** 입니다(실측 원시 레코드: `[ R 한글 새 이름.md]` + `[한글 이름.md]`). `git mv` 후 `git add -N`은 ` R`이 아니라 **`R `(staged rename)** 을 만듭니다 — `git mv`가 이미 index를 갱신했으므로 뒤따르는 `git add -N`은 아무 일도 하지 않습니다(실측: 두 명령 순서 모두 `[R  한글 새 이름.md]` + `[한글 이름.md]`). `R*|C*`처럼 첫 칸만 보는 패턴은 이 항목을 놓쳐 이전 경로 레코드를 소비하지 않고, 그 레코드가 **다음 항목의 경로로 읽혀** `${entry:3}`가 앞 3글자를 잘라낸 `이름.md` 같은 **존재하지 않는 경로**가 목록에 들어갑니다. 상태가 정확히 2문자이므로 `*R*|*C*`로 검사하면 두 칸이 함께 커버됩니다.
   - `-z` 출력을 `read`로 읽을 때는 `while IFS= read -r -d ''`가 필수입니다. 줄 단위 `read`나 `for` 단어 분할은 NUL 구분을 해석하지 못해 전체가 한 덩어리로 들어옵니다.
   - **통과 조건은 "두 칸 중 정확히 한 칸만 채워졌는가" 하나입니다 — 조합을 열거하지 마세요.** 두 칸(X=index, Y=worktree)은 **서로 다른 내용을 가질 수 있고**, 이 스킬은 리뷰어에게 **현재 파일 경로**만 넘기므로 "현재 내용" 하나로 무엇이 커밋될지 말할 수 있을 때만 검토가 성립합니다.

     | 채워진 칸 | 예 | index와 worktree 관계 | 판정 |
     |---|---|---|---|
     | X만 (Y=공백) | `M `·`A `·`R `·`T `·`D ` | worktree = index (변경은 index에만) | **통과** — 현재 파일이 곧 커밋될 내용 |
     | Y만 (X=공백) | ` M`·` A`·` R`·` T`·` D` | index = HEAD (변경은 worktree에만) | **통과** — 현재 파일이 곧 커밋될 내용 |
     | 두 칸 모두 | `MM`·`AM`·`RM`·`MT`·`AD`·`RD`·`MD` | **서로 다를 수 있음** | **중단** — 현재 내용만 봐선 커밋될 내용을 알 수 없음 |
     | `??` | untracked | — | **통과** |

     두 칸이 모두 채워진 상태를 통과시키면 **`git commit`이 기록할 내용을 통째로 놓칩니다.** 실측 근거:

     | 상태 | 만드는 방법 | `git diff HEAD -- <경로>` (현재 내용) | `git diff --cached HEAD -- <경로>` (커밋될 내용) |
     |---|---|---|---|
     | `MM` | 위험한 수정을 staged 후 worktree를 HEAD 내용으로 되돌림 | **빈 결과** — 검토할 것이 하나도 없음 | 제거된 `htmlspecialchars()`가 그대로 보임 |
     | `AM` | 위험한 새 파일 staged 후 worktree를 무해한 내용으로 덮음 | 무해한 쪽만 보임 | index의 위험한 추가가 보임 |
     | `AD` | 새 파일 `git add` 후 worktree에서 삭제 | **빈 결과** | 파일 추가 (내용은 index에만) |
     | `RD` | `git mv` 후 새 경로 삭제 | 새 경로는 빈 결과 (삭제로 나오는 건 **이전 경로**) | 이름변경 |
     | `MD` | 수정 staged 후 삭제 | 순수 삭제만 표시 | 가려진 staged 수정 내용 |
     | `?U?`·`AA`·`DD` | 미해결 머지 충돌 | 경우마다 다름 | 검토할 "현재 내용"이 애초에 하나로 정해지지 않습니다 |

     `MM`·`AM`이 핵심입니다 — 둘 다 흔하고, 둘 다 **현재 파일만 검토하면 위험한 쪽을 못 봅니다.** 실측에서 `MM`의 `git diff HEAD`는 완전히 빈 결과였고 위험한 변경은 `git diff --cached HEAD`에만 있었습니다.

     셸에서는 조합을 열거하는 대신 **부정 문자 클래스로 "한 칸만 채워짐"을 그대로 표현**합니다 — `' '[!\ ]`(X만 공백)와 `[!\ ]' '`(Y만 공백). `[!\ ]`는 "공백이 아닌 아무 문자"이므로 `M`·`A`·`R`·`C`·`T`·`D`는 물론 앞으로 Git이 새 상태 문자를 추가해도 자동으로 커버됩니다. 열거식(`[ MARCT][ MTRC]`)은 두 칸이 모두 채워진 조합(`MM`·`AM`·`RM`·`MT`…)까지 함께 통과시켜 정확히 위 결함을 냅니다. 미해결 충돌 쌍(`DD`·`AU`·`UD`·`UA`·`DU`·`AA`·`UU`)은 전부 두 칸이 채워져 있어 이 규칙만으로도 중단되지만, 의도를 문서화하려고 `*U*`를 앞에 따로 둡니다.

     **중단이 맞고, index와 worktree를 각각 검토하는 방식은 이 스킬에 맞지 않습니다.** 이 스킬이 디스패치하는 `code-quality-review`·`web-security-review`는 **디스크의 현재 파일을 경로로 받아** 검사합니다. index 쪽 내용은 디스크에 파일로 존재하지 않으므로 `git show :<경로>`로 임시 파일에 꺼내 넘겨야 하고, 그러면 리뷰어의 findings가 **저장소에 없는 임시 경로와 줄 번호**를 가리켜 보고서를 쓸 수 없게 됩니다. 게이트를 통과한 상태에서는 "현재 파일 = 커밋될 내용"이라는 단일 전제가 성립하는데, 양쪽 검토를 도입하면 그 전제가 깨지고 사용자는 두 보고서 중 어느 쪽이 커밋될 코드인지 알 수 없습니다. 대신 중단 메시지에 **해소 명령을 같이 적어** 실용성을 확보하세요 — 실측에서 `git add -A` 한 번으로 `MM`·`AM`·`RM`·`MT`·`AD`·`RD`·`MD` 전부가 한 칸만 채워진 상태로 접혔습니다(`AM`→`A `, `MT`→`T `, `RM`→`R `, `MD`·`RD`→`D `). 단 `git add`는 **worktree 쪽을 채택**하므로 index에만 있던 내용은 버려집니다 — `MM`처럼 worktree를 HEAD로 되돌린 경우 staged 변경이 사라지고 레코드 자체가 없어집니다. index 쪽을 살리려면 커밋하거나 `git stash`로 정리해야 합니다. 이 선택은 사용자만 할 수 있으므로 게이트가 대신 판단하지 않습니다.

   갈래를 명령으로 직접 나누는 방법도 **위 allowlist 게이트를 통과한 상태에서는** 같은 집합을 줍니다. 이름변경은 `--name-only`가 새 경로만 출력하므로 두 필드 처리가 필요 없습니다.

   ```bash
   git diff --name-only -z --diff-filter=d HEAD   # 추적 중인 변경에서 삭제만 제외 (소문자 d = 제외)
   git ls-files -z --others --exclude-standard     # untracked — 디렉터리로 접지 않고 파일을 나열
   git diff --name-only -z --diff-filter=D HEAD    # 삭제 — 3번의 diff 검토 대상 (대문자 D = 포함)
   ```

   **`--diff-filter=ACMR`를 쓰지 마세요 — `T`(type change)를 누락합니다.** 이 목록은 위 status 루프가 allowlist로 `CONTENT`에 보내는 집합과 **같아야 합니다.** 그런데 `ACMR`는 일반 파일을 심볼릭 링크로 바꾸는 등의 형식 변경을 빠뜨립니다 — 실측에서 `git status`는 ` T`/`T `를 냈지만 `--diff-filter=ACMR`는 그 경로를 **한 건도 출력하지 않았습니다.** 보안 관련 설정 파일이 심볼릭 링크로 바뀌어도 조용히 검토에서 빠집니다. 소문자 `d`는 Git 문서상 "해당 상태를 제외"를 뜻하므로 `--diff-filter=d`는 **삭제만 제외**라는 규칙을 그대로 옮기고 `T`를 자동으로 포함합니다. 열거식을 고집한다면 최소한 `ACMRT`여야 합니다. 두 방식이 정말 같은 집합인지는 각각 `sort -z`로 정렬해 비교하면 확인할 수 있습니다.

   같은 이유로 `branch-merge-review`의 커밋 기반 Step 1도 품질 범위에 `--diff-filter=d`, 보안 범위에는 **필터 없이** 전체를 씁니다 — 실측에서 일반 파일을 심볼릭 링크로 바꿔 커밋했을 때 `ACMR`는 품질 범위에서, `ACMRD`는 보안 범위에서 그 경로를 누락했습니다.

   단, **머지 충돌이 미해결인 상태에서는 두 방식이 어긋나고 어느 쪽도 쓸 수 없습니다.** modify/delete 충돌을 실제로 만들어 측정한 원시 결과는 다음과 같습니다 — status는 `AA both.txt`, `DU f1.txt`, `UD f2.txt`를 냈고, `--diff-filter=d HEAD`는 `both.txt`·`f1.txt`를, `--diff-filter=D HEAD`는 **빈 결과**를 냈습니다. 즉 `DU`는 `d` 갈래에 **들어가고** `UD`만 두 갈래 어디에도 들어가지 않습니다(`AA`도 `d` 갈래에 들어갑니다). 그리고 이때 status 루프도 대안이 아닙니다 — 미해결 경로에는 검토할 내용이 하나로 정해지지 않으므로, 위 allowlist 게이트가 `?U?`·`AA`·`DD`를 전부 `BLOCKED`로 보내 **중단합니다.** 충돌을 해소한 뒤 다시 수집하세요.

   `git diff --name-only HEAD` 단독은 untracked 파일을 한 건도 출력하지 않으므로 대안이 아닙니다. 반드시 `git ls-files --others --exclude-standard`와 **둘 다** 실행해 합치세요.

   Windows PowerShell에는 `read -d ''`가 없으므로, 위 세 명령을 쓰고 NUL 구분 출력을 직접 쪼갭니다. `-z` 출력에는 개행이 없어 PowerShell이 통짜 문자열로 받으므로 `-join ''` 후 `[char]0`으로 분리합니다.

   ```powershell
   # Windows PowerShell 5.1은 네이티브 출력을 콘솔 코드페이지로 디코드하므로 UTF-8을 먼저 지정합니다
   [Console]::OutputEncoding = [Text.Encoding]::UTF8
   function Get-NulPaths { param($Output) ($Output -join '') -split [char]0 | Where-Object { $_ } }

   # 게이트 먼저 — Bash와 같은 규칙("한 칸만 채워짐"). 통과하지 못하는 상태가 있으면 중단합니다.
   $records = @(Get-NulPaths (git status --porcelain=v1 -z --untracked-files=all))
   $blocked = @(); $i = 0
   while ($i -lt $records.Count) {
     $status = $records[$i].Substring(0, 2)
     $path = $records[$i].Substring(3)
     $i++
     if ($status -match '[RC]') { $i++ }        # 이전 경로 레코드 소비
     if ($status -eq '??') { continue }
     if ($status -match 'U') { $blocked += "$status $path"; continue }   # 미해결 충돌
     if ($status -eq 'D ' -or $status -eq ' D') { continue }
     # '^( [^ ]|[^ ] )$' = 두 칸 중 정확히 한 칸만 채워짐 (Bash의 ' '[!\ ]|[!\ ]' '와 같은 규칙)
     if ($status -notmatch '^( [^ ]|[^ ] )$') { $blocked += "$status $path" }
   }
   if ($blocked.Count -gt 0) {
     Write-Host "검토를 진행할 수 없습니다 — index와 worktree가 갈렸거나 미해결인 경로 $($blocked.Count)건:"
     $blocked | ForEach-Object { Write-Host "  $_" }
     throw '`git add <경로>`로 두 칸을 합치거나(worktree 내용을 채택합니다), 커밋·stash·충돌 해소 후 다시 요청해 주세요.'
   }

   $content = @(Get-NulPaths (git diff --name-only -z --diff-filter=d HEAD)) +
              @(Get-NulPaths (git ls-files -z --others --exclude-standard))
   $deleted = @(Get-NulPaths (git diff --name-only -z --diff-filter=D HEAD))
   foreach ($p in $deleted) { git diff HEAD -- $p }
   ```

2. `CONTENT` 목록을 주제에 맞는 스킬에 넘깁니다 — 보안이면 `web-security-review`, 품질·성능이면 `code-quality-review`.
3. **`DELETED` 목록을 건너뛰지 마세요. 파일 내용이 아니라 diff로 검토합니다.** 삭제는 "무엇이 사라졌는지"가 핵심이라 검토에서 가장 위험한 변경 중 하나입니다. 삭제된 인증 로직·검증 함수·CSRF 체크·입력 정제기가 조용히 빠지지 않도록, 각 경로의 삭제 내용을 읽고 그 자체를 findings 대상으로 삼습니다.

   ```bash
   for p in "${DELETED[@]}"; do
     git diff HEAD -- "$p"   # staged·unstaged 삭제 모두 "deleted file mode"와 제거된 본문을 보여 줍니다
   done
   ```

   판정 기준은 `branch-merge-review`가 커밋된 삭제를 다루는 방식(보안 리뷰어에게 `--diff-filter` 없이 삭제를 포함한 전체 경로를 넘김)과 같습니다 — 제거된 CSRF 체크·인증 가드·입력 정제기·CSP 헤더는 그 자체가 findings입니다. 대체 구현이 함께 추가됐는지 `CONTENT` 쪽에서 확인하고, 없으면 심각도를 낮추지 마세요.
4. `branch-merge-review`로 보내지 않습니다. 이 스킬은 커밋 기반이라 변경을 빠뜨리거나 “검토할 커밋 없음”으로 끝납니다.
5. Codex 위임이 허용된 상황이라면 `codex-delegate`의 `codex exec review --uncommitted`가 staged·unstaged·untracked를 한 번에 수집하는 유일한 경로입니다. 이는 Codex 네이티브 리뷰어의 기능이며, 저장소의 리뷰 스킬이 대신 제공하는 능력이 아닙니다.

#### 여러 표면이 동시에 매칭될 때 — 우선순위로 하나가 남습니다

| 요청 | 동시에 걸리는 표면 | ①작업 모드 | ②범위 | ③주제 | 결론 |
|---|---|---|---|---|---|
| “이 PR을 보안 리뷰해줘” | `branch-merge-review`, `web-security-review`, `security-auditor` | 최초 검토 → 다음 단계 | PR 전체 → 결정 | 보지 않음 | `branch-merge-review` (내부에서 `web-security-review` 디스패치) |
| “이 PR의 지난 지적만 재검토해줘” | `branch-merge-review`, `evidence-first-review` | 재검토 → 결정 | 보지 않음 | 보지 않음 | `evidence-first-review` |
| “이 PR의 이전 보안 지적을 재검토하고 최종 승인해줘” | `branch-merge-review`, `evidence-first-review`, `web-security-review`, `security-auditor` | 재검토 + 최종 승인 → 결정 | 보지 않음 | 보지 않음 | `evidence-first-review` (`recheck` 후 `final-approval`) |

`branch-merge-review`와 `evidence-first-review`의 description은 이 경계를 서로 반대 방향에서 명시합니다. `evidence-first-review`는 "범위가 PR·브랜치여도 재검토·승인이면 이 스킬"을, `branch-merge-review`는 "재검토·승인·증거 검증 요청은 이 스킬이 아니라 `evidence-first-review`"를 선언하므로 두 description이 상호 배타적입니다.

#### 에이전트와 리뷰 스킬은 다른 층입니다

`agents/security-auditor`는 스킬이 아니라 **서브에이전트**이며 description상 보안 검토 작업에서 자동 활성화됩니다. 그래서 보안 요청에서는 리뷰 스킬과 동시에 매칭될 수 있지만, 층이 다르므로 경쟁이 아닙니다 — **어느 스킬을 실행할지는 위 우선순위가 결정하고, 그 스킬이 정의한 절차 안에서 보안 점검을 수행하는 실행 단위로 이 에이전트를 씁니다** (예: `branch-merge-review`가 보안 리뷰어를 띄우는 자리). 이 에이전트는 발견과 개선 가이드만 산출하고 코드를 수정하지 않으므로, 어느 경로로 쓰여도 읽기 전용 제약을 깨지 않습니다.

#### 읽기 전용 제약은 네 번째 축이 아닙니다

**읽기 전용·무수정 제약은 위 세 축 어느 것도 바꾸지 않습니다.** 선택된 스킬의 실행 방식만 바꿉니다. "수정하지 말고 브랜치 리뷰해줘"는 최초 검토 + PR 범위이므로 `branch-merge-review`를 읽기 전용으로 실행합니다. 반대로 "수정하지 말고 이전 지적을 재검토해줘"는 재검토 모드이므로 범위와 무관하게 `evidence-first-review`입니다. 워크플로우 리마인더 훅은 명시적인 읽기 전용·무수정 표현에만 반응하며, 주입되는 안내문도 "작업 모드 먼저, 그다음 범위" 순서를 그대로 알려 주므로 이 표와 같은 결론에 도달합니다. 무수정 제약 표현이 없는 재검토·승인 요청("이 PR의 이전 지적을 재검토하고 최종 승인해줘")에는 훅이 침묵하며, 이때 라우팅은 각 스킬 description의 자동 매칭에 맡깁니다.

### 리뷰 결과 출력

리뷰 스킬은 **결과를 대화에 인라인으로 출력하는 것이 기본**입니다. "리포트로 만들어줘", "보고서로 출력해줘"처럼 파일 저장을 명시적으로 요청했을 때만 파일로 남깁니다. 단순 검토 요청이 작업 트리를 바꾸고 커밋 후보를 늘리지 않도록 하기 위해서입니다.

파일 저장이 필요하면 리뷰 스킬은 slug와 권장 형식만 넘기고 `report-output`에 위임합니다. `.tasks/reports/` 경로 결정, 이름 충돌 회피, 원자적 게시는 `report-output` 한 곳이 책임집니다.

### 에이전트

- `php-backend-developer`
- `frontend-developer`
- `security-auditor`

각 에이전트는 Claude용 `.md`와 Codex용 `.toml`을 제공합니다.

## 훅과 재시작

개발 워크플로우 리마인더 훅은 요청에 따라 다음 안내를 실행 순서대로 결합하며, 오류가 나도 프롬프트를 차단하지 않습니다.

- 큰 구현 요청: `plan-and-build`
- 명시적인 읽기 전용·무수정 검토: "작업 모드 먼저, 그다음 범위" 라우팅 안내 (이전 지적 재검토·최종 승인 판정·원본 데이터·비Git 점검이면 범위가 PR·브랜치여도 `evidence-first-review`, 최초 검토이면서 범위가 PR·브랜치·머지 diff이면 `branch-merge-review`를 읽기 전용으로)
- 선택적 커밋·체크포인트·인수인계·재개: `safe-checkpoint`

명시적인 무수정 제약이 있으면 구현 관련 단어가 포함되어도 `plan-and-build`를 억제합니다. 평범한 코드·보안·브랜치 리뷰, 체크포인트에 관한 설명 요청, 단순한 퇴근 인사에는 동작하지 않습니다. 훅은 안내만 제공하며 명령, 파일 변경, staging, commit, push를 실행하지 않습니다.

**훅이 위 세 개만 리마인드하는 원칙**: 훅은 권한·작업 상태·구조적 의사결정 경계를 놓쳤을 때 영향이 큰 워크플로우만 리마인드합니다. 디버깅처럼 "수행 방법론"에 해당하는 스킬은 훅이 아니라 스킬 description 기반 자동 선택에 맡깁니다. 예를 들어 `systematic-debugging`은 훅에 넣지 않습니다 — "고쳐줘" 같은 표현이 대부분의 버그 요청과 구별되지 않아 거짓 양성이 급증하기 때문입니다. 새 워크플로우를 훅에 추가하려면 유용한 것만으로는 부족하고 이 기준을 통과해야 합니다.

- Claude: Windows에서는 `powershell.exe`와 `args`를 사용하는 exec 훅으로 등록합니다. 처음으로 `skills` 또는 `agents` 디렉터리를 만든 경우에만 Claude Desktop을 한 번 재시작하라는 안내가 표시됩니다.
- Codex: `command`와 `commandWindows`를 함께 등록합니다. 새 Codex 세션을 시작하고 `/hooks`에서 경로와 내용을 검토한 뒤 신뢰를 승인해야 합니다.
- 기존 JSON/TOML과 외부 훅은 보존합니다. 설정 병합이 실패하면 새 훅 파일과 설정 변경을 함께 원복합니다.
- Windows 설치기가 Codex 훅 기능을 `false`에서 `true`로 바꾼 경우에만 이전 상태를 기록하며, 제거 시 값이 여전히 설치 후 상태일 때만 복원합니다. POSIX 설치기는 `config.toml`을 자동 변경하지 않고 수동 활성화를 안내합니다.

## 소유권과 안전 제거

설치 기록은 범위 루트의 `.claude-code-skills/manifest.json` v2에 저장됩니다. 플랫폼, 범위, 클라이언트, 컴포넌트, 대상, 설치 방식, 해시, 설정 변경 전후 상태를 기록합니다. 이전 `manifest.tsv` v1도 POSIX 기록으로 읽습니다.

제거기는 매니페스트와 현재 해시 또는 저장소 링크 대상을 함께 확인합니다. 외부 동명 파일, 사용자가 수정한 복사본, 매니페스트 유실 항목, 확인할 수 없는 링크는 삭제하지 않습니다.

자세한 설치·검증 절차는 [INSTALL.md](./INSTALL.md)를 참고하세요.

관련 공식 문서: [Codex skills](https://learn.chatgpt.com/docs/build-skills), [Codex hooks](https://learn.chatgpt.com/docs/hooks), [Codex Windows](https://developers.openai.com/codex/app/windows), [Claude hooks](https://code.claude.com/docs/en/hooks), [Claude Desktop](https://code.claude.com/docs/en/desktop), [Chrome remote debugging](https://developer.chrome.com/blog/remote-debugging-port).
