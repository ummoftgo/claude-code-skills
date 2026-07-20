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
| `codex-delegate` | ✓ | — | Claude에서 Codex로 위임 |

### 트리거 예시

| 요청 예시 | 스킬 |
|---|---|
| “새 인증 기능을 구현해줘” | `plan-and-build` |
| “컨텍스트 문서부터 읽고 수정 없이 이전 지적을 재검토해줘” | `evidence-first-review` |
| “해당 변경만 커밋하고 내일 재개할 인수인계를 남겨줘” | `safe-checkpoint` |
| “원인이 불명확한 오류를 분석하고 고쳐줘” | `systematic-debugging` |
| “머지 전에 브랜치 리뷰해줘” | `branch-merge-review` |

일반적인 최초 PR·브랜치 머지 검토는 `branch-merge-review`가 담당합니다. `evidence-first-review`는 명시적인 무수정 검토, 이전 지적 재검토, 최종 승인 검토처럼 현재 파일과 원본 증거를 독립 검증하는 요청에 사용합니다.

### 에이전트

- `php-backend-developer`
- `frontend-developer`
- `security-auditor`

각 에이전트는 Claude용 `.md`와 Codex용 `.toml`을 제공합니다.

## 훅과 재시작

개발 워크플로우 리마인더 훅은 요청에 따라 다음 안내를 실행 순서대로 결합하며, 오류가 나도 프롬프트를 차단하지 않습니다.

- 큰 구현 요청: `plan-and-build`
- 명시적인 읽기 전용·무수정 검토: `evidence-first-review`
- 선택적 커밋·체크포인트·인수인계·재개: `safe-checkpoint`

명시적인 무수정 제약이 있으면 구현 관련 단어가 포함되어도 `plan-and-build`를 억제합니다. 평범한 코드·보안·브랜치 리뷰, 체크포인트에 관한 설명 요청, 단순한 퇴근 인사에는 동작하지 않습니다. 훅은 안내만 제공하며 명령, 파일 변경, staging, commit, push를 실행하지 않습니다.

- Claude: Windows에서는 `powershell.exe`와 `args`를 사용하는 exec 훅으로 등록합니다. 처음으로 `skills` 또는 `agents` 디렉터리를 만든 경우에만 Claude Desktop을 한 번 재시작하라는 안내가 표시됩니다.
- Codex: `command`와 `commandWindows`를 함께 등록합니다. 새 Codex 세션을 시작하고 `/hooks`에서 경로와 내용을 검토한 뒤 신뢰를 승인해야 합니다.
- 기존 JSON/TOML과 외부 훅은 보존합니다. 설정 병합이 실패하면 새 훅 파일과 설정 변경을 함께 원복합니다.
- Windows 설치기가 Codex 훅 기능을 `false`에서 `true`로 바꾼 경우에만 이전 상태를 기록하며, 제거 시 값이 여전히 설치 후 상태일 때만 복원합니다. POSIX 설치기는 `config.toml`을 자동 변경하지 않고 수동 활성화를 안내합니다.

## 소유권과 안전 제거

설치 기록은 범위 루트의 `.claude-code-skills/manifest.json` v2에 저장됩니다. 플랫폼, 범위, 클라이언트, 컴포넌트, 대상, 설치 방식, 해시, 설정 변경 전후 상태를 기록합니다. 이전 `manifest.tsv` v1도 POSIX 기록으로 읽습니다.

제거기는 매니페스트와 현재 해시 또는 저장소 링크 대상을 함께 확인합니다. 외부 동명 파일, 사용자가 수정한 복사본, 매니페스트 유실 항목, 확인할 수 없는 링크는 삭제하지 않습니다.

자세한 설치·검증 절차는 [INSTALL.md](./INSTALL.md)를 참고하세요.

관련 공식 문서: [Codex skills](https://learn.chatgpt.com/docs/build-skills), [Codex hooks](https://learn.chatgpt.com/docs/hooks), [Codex Windows](https://developers.openai.com/codex/app/windows), [Claude hooks](https://code.claude.com/docs/en/hooks), [Claude Desktop](https://code.claude.com/docs/en/desktop), [Chrome remote debugging](https://developer.chrome.com/blog/remote-debugging-port).
