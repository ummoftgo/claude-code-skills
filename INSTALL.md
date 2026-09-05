# 설치 및 검증 가이드

## 1. Windows 네이티브와 WSL 중 선택

먼저 실제 Claude/Codex 프로세스가 파일을 읽는 환경을 기준으로 설치기를 고릅니다.

- Windows Claude Desktop Code 또는 Windows Codex 앱/CLI: Windows PowerShell에서 `.\install.ps1`
- WSL 배포판 안의 Claude/Codex: WSL 셸에서 `bash install.sh`
- 네이티브 Linux: `bash install.sh`

Windows 설치기는 WSL 경로를 대상으로 하지 않습니다. WSL 모드를 쓰는 앱에는 배포판 내부 설치기를 별도로 실행하세요.

설치 대상은 [`components.json`](./components.json)이 단일 기준입니다. POSIX와 Windows 설치기·제거기는 이 카탈로그에서 각 클라이언트와 플랫폼이 지원하는 컴포넌트를 읽습니다.

### 사용자 지정 설정 디렉터리

전역 설치·제거는 기본 설정 경로(`~/.claude`, `~/.codex`)를 관리합니다. 선택한 클라이언트의 `CLAUDE_CONFIG_DIR` 또는 `CODEX_HOME`이 기본 경로와 다르면, 파일·설정·매니페스트 변경 전에 오류로 중단합니다. 잘못된 기본 디렉터리에 설치하거나 그 안의 기존 구성을 제거하지 않기 위한 검사입니다. 빈 변수와 명시적으로 지정한 기본 경로는 허용합니다.

사용자 지정 설정 디렉터리에서는 프로젝트 범위 설치·제거를 선택하거나 해당 디렉터리의 컴포넌트를 직접 관리하세요. 환경변수 값을 바꾸거나 사용자 지정 디렉터리를 자동 이전하지 않습니다. Windows에서는 선택한 클라이언트만 검사하며, POSIX 설치·제거는 기본적으로 양쪽 클라이언트를 대상으로 합니다. 프로젝트 범위에서는 이 전역 경로 검사를 적용하지 않습니다.

### 공용 스킬과 트리거

| 스킬 | Claude | Codex | 대표 요청 |
|---|:---:|:---:|---|
| `use-context7` | ✓ | ✓ | “Svelte 5 컴포넌트 만들어줘” |
| `plan-and-build` | ✓ | ✓ | “새 인증 기능을 구현해줘” |
| `evidence-first-review` | ✓ | ✓ | “컨텍스트 문서부터 읽고 이전 지적을 재검토해줘” |
| `safe-checkpoint` | ✓ | ✓ | “해당 변경만 커밋하고 내일 재개할 인수인계를 남겨줘” |
| `systematic-debugging` | ✓ | ✓ | “원인이 불명확한 오류를 분석하고 고쳐줘” |
| `web-security-review` | ✓ | ✓ | “보안 검토해줘” |
| `web-parallel-dispatch` | ✓ | ✓ | “API 계약대로 백엔드와 프론트엔드를 병렬 구현해줘” |
| `code-quality-review` | ✓ | ✓ | “코드 품질 검토해줘” |
| `branch-merge-review` | ✓ | ✓ | “머지 전에 브랜치 리뷰해줘” |
| `web-browser-preview` | ✓ | ✓ | “브라우저에서 확인해줘” |
| `codex-delegate` | ✓ | — | “Codex에게 검토를 위임해줘” |

리뷰 스킬의 자연어 트리거는 서로 겹칩니다. 겹침 자체를 없애려 하지 않고 **① 작업 모드 → ② 범위 → ③ 주제** 순서로 해소합니다. 앞 단계에서 결론이 나면 뒤 단계는 보지 않습니다.

1. **작업 모드** — 이전 지적 재검토(`recheck`), 최종 승인 판정(`final-approval`), 원본 데이터·비Git 디렉터리 검증이면 → `evidence-first-review`. **범위가 PR·브랜치여도 마찬가지입니다.** 지적별 상태 분류(`resolved`·`partially resolved`·`unresolved`·`regressed`)와 승인 판정(`approved`·`conditionally approved`·`hold`)은 이 스킬에만 있고, `branch-merge-review`는 신규 발견용이라 요청한 산출물이 나오지 않습니다. 두 스킬의 description이 이 경계를 서로 반대 방향에서 명시하므로 상호 배타적입니다.
2. **범위** — 최초 검토(`initial`)이면 범위가 결정합니다. 범위가 PR·브랜치·머지 diff(커밋된 변경)이면 보안이 함께 명시돼도 `branch-merge-review`를 실행하며, 이 스킬이 `web-security-review`와 `code-quality-review`를 리뷰어로 디스패치합니다.
3. **주제** — 범위가 브랜치 diff보다 좁을 때만 주제로 갈립니다. 보안이면 `web-security-review`, 품질·성능이면 `code-quality-review`.
4. **미커밋 작업 전체**(staged·unstaged·untracked)를 스스로 수집하는 리뷰 스킬은 없습니다. `branch-merge-review`는 `git log <base>..HEAD`와 `HEAD` 비교로만 수집하므로 미커밋 변경을 놓칩니다. `git status --porcelain=v1 -z --untracked-files=all`로 경로를 확정한 뒤, 현재 파일 내용을 검사하는 `code-quality-review`·`web-security-review`에 그 목록을 넘기세요. 네 가지를 지켜야 목록이 정확합니다.
   - `--untracked-files=all`은 생략하지 마세요 — 기본값은 새로 만든 디렉터리를 `dir/` 한 줄로 접어 그 안의 파일을 열거하지 않습니다.
   - `-z`(NUL 구분)를 쓰고 `| cut -c4-`로 상태 코드를 잘라내지 마세요. 개행 구분 출력은 이름변경을 `R  "old" -> "new"` 한 줄로 쓰고 공백·비ASCII 경로를 큰따옴표로 감싸 이스케이프하므로, 잘라낸 문자열은 존재하지 않는 경로가 됩니다. `-z`는 경로를 인용하지 않으며, 이름변경·복사 항목만 `XY 새경로\0이전경로\0` 두 필드를 쓰므로 읽을 때 이전 경로 레코드를 소비합니다(`while IFS= read -r -d ''`). 이때 **상태 두 칸(X=index, Y=worktree)을 모두 검사**해야 합니다 — `case "$status" in *R*|*C*)`. worktree 쪽 이름변경은 첫 칸이 공백인 ` R`이라 `R*|C*`처럼 첫 칸만 보면 이전 경로 레코드를 소비하지 못하고, 그 레코드가 다음 항목의 경로로 읽혀 존재하지 않는 경로가 목록에 섞입니다.
   - **통과 조건은 "두 칸 중 정확히 한 칸만 채워졌는가" 하나입니다 — 조합을 열거하지 마세요.** X만 채워졌으면(`M `·`A `·`R `·`T `·`D `) worktree가 index와 같고, Y만 채워졌으면(` M`·` A`·` R`·` T`·` D`) index가 HEAD와 같으므로, 어느 쪽이든 **현재 파일이 곧 커밋될 내용**입니다. `??`(untracked)도 통과하고 `D `·` D`는 순수 삭제라 diff로 검토합니다. **두 칸이 모두 채워졌으면 중단**하세요 — index와 worktree가 서로 다른 내용일 수 있어 현재 파일만으로는 무엇이 커밋될지 알 수 없습니다. 셸에서는 열거 대신 부정 문자 클래스로 그대로 표현합니다: `' '[!\ ]|[!\ ]' '`. 미해결 충돌 쌍(`DD`·`AU`·`UD`·`UA`·`DU`·`AA`·`UU`)은 전부 두 칸이 채워져 이 규칙만으로 중단되지만, 의도를 드러내려고 `*U*`를 앞에 따로 둡니다.

     실측 근거 — 두 칸이 모두 채워진 상태를 통과시키면 `git commit`이 기록할 내용을 놓칩니다. `MM`(위험한 수정 staged 후 worktree를 HEAD로 되돌림)은 `git diff HEAD`가 **완전히 빈 결과**이고 제거된 sanitizer는 `git diff --cached HEAD`에만 있었습니다. `AM`은 `git diff HEAD`가 무해한 worktree 쪽만 보여 주고 위험한 추가는 index에만 있었습니다. `AD`는 HEAD diff가 빈 결과인데 커밋하면 파일이 추가되고, `RD`의 HEAD diff는 **이전 경로**를 삭제로 내놓아 새 경로 diff가 비며, `MD`는 순수 삭제만 보여 staged 수정을 가립니다. 열거식 `[ MARCT][ MTRC]`는 `MM`·`AM`·`RM`·`MT`를 함께 통과시켜 바로 이 누락을 냈습니다.

     중단 메시지에는 해소 명령을 함께 적으세요 — 실측에서 `git add -A` 한 번으로 위 상태 전부가 한 칸만 채워진 상태로 접혔습니다. 단 `git add`는 worktree 쪽을 채택하므로 index에만 있던 내용은 버려집니다(`MM`은 레코드 자체가 사라집니다). index 쪽을 살리려면 커밋하거나 `git stash`를 써야 하고, 그 선택은 사용자만 할 수 있습니다.
   - 상태가 `D `·` D`인 경로는 현재 내용이 없으므로 내용 기반 리뷰어에 넘기지 말고 **`git diff HEAD -- <path>`로 삭제된 내용을 읽어 검토**하세요. 제거된 인증 가드·검증 함수·CSRF 체크는 그 자체가 findings입니다 — 조용히 건너뛰면 안 됩니다.

   갈래를 명령으로 직접 나눠도 됩니다(단 **위 allowlist 게이트를 통과한 뒤에**): `git diff --name-only -z --diff-filter=d HEAD`(내용 검토 대상, 이름변경은 새 경로만) + `git ls-files -z --others --exclude-standard`(untracked) + `git diff --name-only -z --diff-filter=D HEAD`(삭제, diff 검토 대상). 소문자 `d`는 "삭제만 제외"라는 뜻으로, allowlist를 통과한 상태에서는 위 status 루프와 같은 집합을 냅니다 — **`ACMR`를 쓰면 `T`(type change, 예: 일반 파일 → 심볼릭 링크)가 빠져** 형식이 바뀐 설정 파일이 조용히 검토에서 누락됩니다. 열거식을 쓰려면 최소한 `ACMRT`여야 합니다. 미해결 충돌에서는 두 방식이 어긋납니다 — 실측에서 `DU`는 `--diff-filter=d` 갈래에 들어가고 `UD`만 두 갈래 어디에도 들어가지 않으며(`AA`도 `d` 갈래), status 루프도 대안이 아니므로 게이트가 중단시킵니다. `git diff --name-only HEAD` 단독은 untracked 파일을 출력하지 않으므로 대안이 아닙니다.
5. 읽기 전용·무수정 제약은 위 세 축 어느 것도 바꾸지 않고 실행 방식만 바꿉니다. "수정하지 말고 브랜치 리뷰해줘"는 여전히 `branch-merge-review`를 읽기 전용으로 실행합니다.

`agents/security-auditor`는 스킬이 아닌 서브에이전트 층입니다. 보안 요청에서 리뷰 스킬과 동시에 매칭될 수 있지만, 어느 스킬을 실행할지는 위 우선순위가 정하고 에이전트는 그 절차 안에서 보안 점검을 수행하는 실행 단위로 쓰입니다.

자세한 라우팅 기준과 다중 매칭 예시는 [README.md](./README.md)의 "리뷰 스킬 라우팅"을 참고하세요.

## 2. Windows 네이티브 설치

PowerShell 5.1 이상에서 저장소 루트로 이동합니다.

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install.ps1
```

설치기는 무인 플래그를 받지 않습니다. 다음 항목을 순서대로 선택합니다.

1. Claude Desktop Code, Codex 또는 둘 다
2. 전역 또는 프로젝트 범위
3. 스킬 복사 또는 심볼릭 링크
4. 전역 범위일 때 클라이언트별 워크플로우 훅

복사가 기본값입니다. 링크는 저장소와 대상이 모두 로컬 Windows 경로일 때만 제시되며, Developer Mode/권한 부족 등으로 생성이 실패하면 복사로 전환합니다. 에이전트와 훅은 링크하지 않습니다.

### Windows 경로

| 항목 | Claude | Codex |
|---|---|---|
| 전역 스킬 | `%USERPROFILE%\.claude\skills` | `%USERPROFILE%\.agents\skills` |
| 전역 에이전트 | `%USERPROFILE%\.claude\agents` | `%USERPROFILE%\.codex\agents` |
| 전역 훅 | `%USERPROFILE%\.claude\hooks` | `%USERPROFILE%\.codex\hooks` |
| 훅 설정 | `%USERPROFILE%\.claude\settings.json` | `%USERPROFILE%\.codex\hooks.json` |
| Codex 기능 설정 | — | `%USERPROFILE%\.codex\config.toml` |
| 프로젝트 스킬 | `.claude\skills` | `.agents\skills` |
| 프로젝트 에이전트 | `.claude\agents` | `.codex\agents` |

Windows 프로젝트 설치에는 훅이 포함되지 않습니다.

### 외부 도구 진단

설치 마지막에 Node.js, PHP, Codex CLI, Context7, agent-browser, Chrome 상태를 보여 줍니다. 설치기는 어떤 도구나 Claude 플러그인도 자동 설치하지 않습니다. 누락 시 표시되는 명령을 검토한 뒤 사용자가 직접 실행합니다.

예시:

```powershell
npm install -g @openai/codex
npm install -g ctx7
npm install -g agent-browser
```

## 3. WSL/Linux 설치

```bash
bash install.sh
```

Bash 설치기는 해당 POSIX 홈/프로젝트에만 설치합니다. Windows 네이티브 프로필에는 쓰지 않습니다. 설치 대상은 PowerShell 설치기와 같은 `components.json`에서 선택하며 Codex 스킬은 공식 `.agents/skills` 경로를 사용합니다.

Codex `config.toml`에서 훅이 비활성화되어 있으면 Bash 설치기는 값을 바꾸지 않고 훅 설치를 건너뜁니다. 설정을 직접 검토해 활성화한 뒤 설치기를 다시 실행하세요.

기존 `~/.codex/skills/local/<name>` 항목은 다음 조건을 모두 만족할 때만 이전합니다.

- 카탈로그에 있는 Codex 스킬이다.
- v1/v2 매니페스트 해시가 현재 내용과 같거나 링크가 이 저장소의 스킬을 가리킨다.
- 새 `~/.agents/skills/<name>` 대상이 없다.

이전은 새 대상에 복사하고 v2 소유권을 기록한 뒤 구 항목을 제거하는 순서입니다. 불명확하거나 수정되었거나 충돌한 항목은 보존합니다.

## 4. 훅 설정

개발 워크플로우 리마인더 훅은 `UserPromptSubmit`에서 요청을 분류하고 필요한 안내만 하나의 `additionalContext`에 실행 순서대로 결합합니다.

- 큰 구현 요청: `plan-and-build`
- 명시적인 읽기 전용·무수정 검토: "작업 모드 먼저, 그다음 범위" 라우팅 안내 (이전 지적 재검토·최종 승인 판정·원본 데이터·비Git 점검이면 범위가 PR·브랜치여도 `evidence-first-review`, 최초 검토이면서 범위가 PR·브랜치·머지 diff이면 `branch-merge-review`를 읽기 전용으로)
- 선택적 커밋·체크포인트·인수인계·재개: `safe-checkpoint`

명시적인 무수정 제약은 구현 관련 단어가 있어도 `plan-and-build`를 억제합니다. 평범한 코드·보안·브랜치 리뷰, 체크포인트나 인수인계의 의미를 묻는 설명 요청, 단순한 퇴근 인사에는 동작하지 않습니다. 훅은 안내만 제공하며 명령, 파일 변경, staging, commit, push를 실행하지 않습니다. malformed JSON이나 지원하지 않는 입력도 프롬프트 처리를 막지 않습니다.

### Claude Desktop Code

Windows 훅은 `workflow-reminder.ps1`을 복사하고 다음 exec 형태를 `UserPromptSubmit`에 병합합니다.

```json
{
  "type": "command",
  "command": "powershell.exe",
  "args": ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "C:\\Users\\USER\\.claude\\hooks\\claude-code-skills-workflow.ps1"],
  "timeout": 5
}
```

다른 이벤트와 외부 훅은 유지됩니다. 기존 `skills`/`agents` 디렉터리가 없어서 새로 만든 경우에만 Claude Desktop 재시작 안내가 표시됩니다.

POSIX 설치에서는 같은 역할의 `workflow-reminder.py`를 복사하고 기존 `settings.json`을 보존하면서 `UserPromptSubmit` 항목을 병합합니다.

### Codex

Windows 훅 항목에는 필수 `command`와 Windows 전용 `commandWindows`가 모두 들어갑니다. 같은 `config.toml`에 인라인 훅이 있으면 기본적으로 건너뜁니다. `[features] hooks = false` 또는 이전 `codex_hooks = false`가 적용되면 활성화할지 별도로 확인합니다.

설치기가 활성화 값을 바꾼 경우 매니페스트에 이전 키/값과 설치 후 값을 기록합니다. 제거기는 현재 값이 여전히 설치 후 값일 때만 이전 `false` 상태를 복원합니다. 사용자가 이후 값을 변경했다면 그대로 둡니다.

POSIX 설치기는 `config.toml`을 자동 변경하지 않습니다. 같은 설정 계층에 인라인 훅이 있거나 훅 기능이 비활성화되어 있으면 이유와 수동 조치만 안내합니다.

설치 후 새 Codex 세션에서 다음을 수행합니다.

1. `/hooks`를 연다.
2. `claude-code-skills-workflow` 경로와 내용을 검토한다.
3. 훅을 신뢰하도록 승인한다.

## 5. Chrome과 `web-browser-preview`

Windows 네이티브에서는 CDP 주소로 `http://127.0.0.1:9333`을 사용합니다. Chrome 136+ 보안 요구에 맞춰 기본 프로필이 아닌 전용 사용자 데이터 디렉터리를 사용해야 합니다.

```powershell
$chrome = "$env:ProgramFiles\Google\Chrome\Application\chrome.exe"
$profile = Join-Path $env:LOCALAPPDATA 'claude-code-skills\chrome-cdp-profile'
& $chrome --remote-debugging-port=9333 --user-data-dir="$profile"
```

스킬과 설치기는 Chrome을 자동 실행하지 않습니다. Chrome과 agent-browser 상태, 필요한 명령만 안내합니다. WSL에서는 Windows 호스트 IP를 런타임에 구해 `<host>:9333`에 연결합니다.

## 6. 제거

Windows:

```powershell
.\uninstall.ps1
```

WSL/Linux:

```bash
bash uninstall.sh
```

제거기는 `.claude-code-skills/manifest.json` v2 또는 안전하게 변환된 v1 기록으로 소유가 확인된 항목만 삭제합니다. 복사본의 현재 해시가 달라졌거나 매니페스트가 없거나 외부 링크/동명 항목이면 보존하고 경고합니다. JSON에서는 정확히 이 설치기가 추가한 훅만 제거합니다.

## 7. 수동 확인 체크리스트

앱은 자동 실행되지 않습니다. 설치 후 직접 확인합니다.

### Codex

- 새 세션에서 `/skills`를 열어 선택한 스킬이 보이는지 확인
- `~/.codex/agents` 또는 프로젝트 `.codex/agents`의 에이전트가 인식되는지 확인
- 전역 설치라면 `/hooks`에서 훅을 검토하고 신뢰 승인
- 큰 구현 프롬프트에서 `plan-and-build` 안내 확인
- “수정하지 말고 브랜치 리뷰해줘” 요청에서 안내가 `branch-merge-review`를 읽기 전용으로 실행하도록 라우팅하는지 확인 (최초 검토 + PR 범위)
- “수정하지 말고 이전 지적을 근거와 함께 재검토해줘” 요청에서 `evidence-first-review` 안내 확인
- “이 PR의 이전 지적을 재검토하고 최종 승인해줘” 요청이 `evidence-first-review`로 라우팅되는지 확인. 무수정 제약 표현이 없으면 훅은 침묵하는 것이 정상이며, 이때는 스킬 description 자동 매칭이 재검토·승인 요청을 `branch-merge-review`가 아니라 `evidence-first-review`로 보내는지 확인 — `branch-merge-review`의 description도 재검토·승인 요청을 제외하고 있어야 함(양쪽 description이 상호 배타적인지 확인)
- “이 PR의 이전 보안 지적을 재검토하고 최종 승인해줘”처럼 스킬 셋 이상과 `security-auditor`까지 동시에 걸리는 요청에서, ①작업 모드가 먼저 적용돼 `evidence-first-review` 하나로 수렴하는지 확인
- “지금 작업 중인 변경 전체를 검토해줘”(미커밋 staged·unstaged·untracked) 요청에서 `branch-merge-review`로 직행하지 않고, 변경 경로를 먼저 열거한 뒤 주제에 맞는 `code-quality-review`·`web-security-review`로 가는지 확인. “검토할 커밋 없음”으로 끝나면 잘못된 라우팅
- 같은 요청에서 경로 열거가 `-z`(NUL 구분)를 쓰는지 확인. 이름변경 항목이 `old -> new` 한 줄로, 공백·한글 경로가 `"\355\225\234..."` 형태로 리뷰어에게 넘어가면 잘못된 수집. 삭제(`D`) 경로를 조용히 건너뛰지 않고 `git diff HEAD -- <path>`로 제거된 내용을 검토하는지도 확인
- “해당 변경만 커밋” 또는 인수인계 요청에서 `safe-checkpoint` 안내 확인
- 평범한 리뷰·설명·작은 수정·단순 퇴근 인사에는 조용한지 확인

### Claude Desktop Code

- Code 탭에서 스킬 목록 확인
- 설치한 에이전트 선택/호출 확인
- 위 세 종류의 워크플로우 리마인더와 무응답 사례 확인
- 기존 외부 훅과 `settings.json`의 다른 키가 유지되는지 확인

## 8. 문제 해결

### 수정한 스킬이 제거되지 않음

정상적인 보호 동작입니다. 제거기는 설치 당시 해시와 달라진 복사본을 삭제하지 않습니다. 필요한 내용을 백업한 뒤 수동 정리하세요.

### 기존 Codex 스킬이 이전되지 않음

새 `.agents/skills` 대상 충돌, 매니페스트 유실, 내용 변경, 외부 링크 중 하나일 수 있습니다. 설치기 경고를 확인하고 두 위치를 수동 비교하세요.

### 훅 설치 중 JSON/TOML 오류

잘못된 기존 설정은 덮어쓰지 않습니다. 설치기는 훅 파일과 설정 변경을 원복합니다. 기존 파일을 유효한 JSON/TOML로 고친 뒤 다시 실행하세요.

### Windows 훅이 보이지 않음

새 Codex 세션을 시작한 뒤 `/hooks`에서 신뢰 상태를 확인하세요. Claude는 처음 디렉터리가 생성된 설치였다면 Desktop을 한 번 재시작하세요.

공식 참고: [Codex skills](https://learn.chatgpt.com/docs/build-skills), [Codex hooks](https://learn.chatgpt.com/docs/hooks), [Codex Windows](https://developers.openai.com/codex/app/windows), [Claude hooks](https://code.claude.com/docs/en/hooks), [Claude Desktop](https://code.claude.com/docs/en/desktop), [Chrome remote debugging](https://developer.chrome.com/blog/remote-debugging-port).
