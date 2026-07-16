# 설치 및 검증 가이드

## 1. Windows 네이티브와 WSL 중 선택

먼저 실제 Claude/Codex 프로세스가 파일을 읽는 환경을 기준으로 설치기를 고릅니다.

- Windows Claude Desktop Code 또는 Windows Codex 앱/CLI: Windows PowerShell에서 `.\install.ps1`
- WSL 배포판 안의 Claude/Codex: WSL 셸에서 `bash install.sh`
- 네이티브 Linux: `bash install.sh`

Windows 설치기는 WSL 경로를 대상으로 하지 않습니다. WSL 모드를 쓰는 앱에는 배포판 내부 설치기를 별도로 실행하세요.

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

### Codex

Windows 훅 항목에는 필수 `command`와 Windows 전용 `commandWindows`가 모두 들어갑니다. 같은 `config.toml`에 인라인 훅이 있으면 기본적으로 건너뜁니다. `[features] hooks = false` 또는 이전 `codex_hooks = false`가 적용되면 활성화할지 별도로 확인합니다.

설치기가 활성화 값을 바꾼 경우 매니페스트에 이전 키/값과 설치 후 값을 기록합니다. 제거기는 현재 값이 여전히 설치 후 값일 때만 이전 `false` 상태를 복원합니다. 사용자가 이후 값을 변경했다면 그대로 둡니다.

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
- 큰 구현 프롬프트에는 계획 리마인더가 나오고 리뷰/설명/작은 수정에는 조용한지 확인

### Claude Desktop Code

- Code 탭에서 스킬 목록 확인
- 설치한 에이전트 선택/호출 확인
- 큰 구현 프롬프트에서 훅 리마인더 확인
- 기존 외부 훅과 settings.json의 다른 키가 유지되는지 확인

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
