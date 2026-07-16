# 팀 스킬 설치 가이드

이 문서는 팀에서 개발한 Claude Code/Codex 스킬 9종과 선택적 워크플로우 훅을 새 개발 환경에 설치하는 방법을 설명합니다.

---

## 스킬 목록

| 스킬 이름 | 역할 |
|-----------|------|
| `use-context7` | 프레임워크 코드 작성 전 최신 공식 문서 조회 |
| `plan-and-build` | 새 프로젝트·기능의 스펙/계획, TDD 판단, 병렬 분할 |
| `systematic-debugging` | 불명확한 장애의 재현·근본 원인 확인·회귀 검증 |
| `web-security-review` | PHP 백엔드 + 프론트엔드 보안 취약점 검토 |
| `web-parallel-dispatch` | 에이전트 병렬 실행으로 개발 속도 향상 |
| `web-browser-preview` | WSL에서 Windows Chrome으로 작업 결과 확인 |
| `codex-delegate` | Codex CLI 서브에이전트에 검토/구현 위임 |
| `code-quality-review` | CLI 도구 기반 코드 품질 종합 검토 |
| `branch-merge-review` | 머지 전 브랜치 변경사항 병렬 리뷰 |

---

## 사전 요구사항

- **Claude Code** 설치 및 로그인 완료
- **Node.js** 18 이상 (npx 사용)
- **PHP 8.1 이상** (`code-quality-review` 스킬의 PHP 도구 사용 시)

---

## 1단계: 스킬 파일 가져오기

스킬 파일을 로컬에 복사합니다.

```bash
# 팀 저장소에서 클론하는 경우 (원하는 디렉토리 이름으로 지정)
git clone <팀-저장소-URL> ~/work/claude-code-skills

# 또는 공유 폴더에서 복사하는 경우
cp -r /경로/to/claude-code-skills ~/work/claude-code-skills
```

---

## 2단계: Claude Code에 스킬 등록

Claude Code는 `~/.claude/skills/` 디렉토리에서 스킬을 로드합니다.
스킬 디렉토리를 심볼릭 링크로 연결하면 파일 수정 시 자동으로 반영됩니다.

```bash
# ~/.claude/skills/ 디렉토리 생성 (없는 경우)
mkdir -p ~/.claude/skills

# SKILLS_DIR을 클론한 경로 아래 skills/ 디렉토리로 지정하세요 (스킬은 저장소의 skills/ 하위에 있습니다)
SKILLS_DIR=~/work/claude-code-skills/skills

# 9개 스킬 모두 심볼릭 링크 등록
ln -s $SKILLS_DIR/use-context7        ~/.claude/skills/use-context7
ln -s $SKILLS_DIR/plan-and-build      ~/.claude/skills/plan-and-build
ln -s $SKILLS_DIR/systematic-debugging ~/.claude/skills/systematic-debugging
ln -s $SKILLS_DIR/web-security-review ~/.claude/skills/web-security-review
ln -s $SKILLS_DIR/web-parallel-dispatch ~/.claude/skills/web-parallel-dispatch
ln -s $SKILLS_DIR/web-browser-preview ~/.claude/skills/web-browser-preview
ln -s $SKILLS_DIR/codex-delegate      ~/.claude/skills/codex-delegate
ln -s $SKILLS_DIR/code-quality-review ~/.claude/skills/code-quality-review
ln -s $SKILLS_DIR/branch-merge-review ~/.claude/skills/branch-merge-review
```

> **팁**: 심볼릭 링크 대신 복사하려면 `ln -s` 대신 `cp -r`을 사용하세요.
> 단, 복사 방식은 원본 파일 수정이 자동 반영되지 않습니다.

등록 후 Claude Code를 재시작하면 스킬이 활성화됩니다.

### `plan-and-build` 리마인더 훅 — Claude Code

`install.sh`는 설치 여부를 확인한 뒤 `hooks/workflow-reminder.py`를 `~/.claude/hooks/`에 복사하고 기존 설정을 보존한 채 `UserPromptSubmit` 훅을 병합합니다. 이 훅은 새 프로젝트·기능 등 명백한 구현 요청에만 계획 워크플로우를 상기시키며, 프롬프트를 차단하지 않습니다.

수동 설치 시에는 훅 파일을 복사한 다음 `~/.claude/settings.json`의 `hooks` 객체에 아래 항목을 병합합니다.

```bash
mkdir -p ~/.claude/hooks
cp hooks/workflow-reminder.py ~/.claude/hooks/claude-code-skills-workflow.py
chmod +x ~/.claude/hooks/claude-code-skills-workflow.py
```

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 /home/USER/.claude/hooks/claude-code-skills-workflow.py",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

`/home/USER`는 실제 홈 경로로 바꿉니다. 기존 `hooks` 설정이 있다면 전체 객체를 덮어쓰지 말고 `UserPromptSubmit` 배열에 항목을 추가해야 합니다.

자동 설치·제거기는 설정 파일이 심볼릭 링크이면 실제 대상 파일을 원자적으로 수정하고 링크 자체는 유지합니다. 설정 또는 훅 파일의 실제 대상이 선택한 전역·프로젝트 범위 밖에 있으면 경로를 알리고 기본값으로 건너뜁니다. dotfiles 저장소처럼 의도한 외부 대상일 때만 명시적으로 허용하세요. 깨진 링크는 안전하게 수정할 수 없으므로 설치·제거를 중단합니다.

Codex용 훅은 아래의 Codex 설치 절에서 별도로 등록합니다. 같은 Python 스크립트가 Claude Code의 `user_prompt` 입력과 Codex의 `prompt` 입력을 모두 처리합니다.

---

## 3단계: 스킬별 외부 의존성 설치

### `use-context7` — context7 설정

**방법 A: MCP (권장)** — Claude Code와 자동 통합, 별도 명령어 불필요

`~/.claude/settings.json`의 `mcpServers` 섹션에 추가:

```json
{
  "mcpServers": {
    "context7": {
      "command": "npx",
      "args": ["-y", "@upstash/context7-mcp"]
    }
  }
}
```

**방법 B: ctx7 CLI** — MCP 설정 없이 사용 가능

```bash
# 전역 설치 (선택)
npm install -g ctx7

# 또는 설치 없이 npx로 바로 사용
npx ctx7 library svelte
npx ctx7 docs /sveltejs/svelte "$state runes"
```

MCP가 설정되어 있으면 스킬이 MCP 도구를 우선 사용하고, 없으면 `ctx7 CLI`로 자동 전환합니다.

---

### `web-browser-preview` — agent-browser 스킬 설치

브라우저 미리보기는 `agent-browser` 스킬에 의존합니다.

```bash
npx skills add vercel-labs/agent-browser --skill agent-browser
```

**Windows Chrome 원격 디버깅 설정** (WSL 환경):

Windows에서 Chrome을 원격 디버깅 포트와 함께 실행해야 합니다.
Chrome 바로가기에 다음 옵션을 추가하거나, PowerShell에서 실행하세요:

```powershell
# PowerShell에서 실행
& "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9333
```

> 포트 9333이 이미 사용 중이면 Chrome을 완전히 종료한 후 다시 실행하세요.

---

### `code-quality-review` — PHP 품질 도구 설치

PHP 코드베이스를 검토할 경우 PHP CLI 도구를 설치합니다.

```bash
# sudo 없이 설치 — ~/.local/bin/ 사용
mkdir -p ~/.local/bin

# PHPStan — 정적 분석
if ! command -v phpstan &>/dev/null; then
  wget -q -O ~/.local/bin/phpstan \
    https://github.com/phpstan/phpstan/releases/latest/download/phpstan.phar
  chmod +x ~/.local/bin/phpstan
fi

# phpcs / phpcbf — 코딩 스타일 검사 및 자동 수정
if ! command -v phpcs &>/dev/null; then
  curl -qsL https://phars.phpcodesniffer.com/phpcs.phar -o ~/.local/bin/phpcs
  curl -qsL https://phars.phpcodesniffer.com/phpcbf.phar -o ~/.local/bin/phpcbf
  chmod +x ~/.local/bin/phpcs ~/.local/bin/phpcbf
fi

# phpmd — 복잡도 및 코드 냄새 감지
if ! command -v phpmd &>/dev/null; then
  wget -q -O ~/.local/bin/phpmd \
    https://github.com/phpmd/phpmd/releases/latest/download/phpmd.phar
  chmod +x ~/.local/bin/phpmd
fi

# phpcpd — 중복 코드 감지
if ! command -v phpcpd &>/dev/null; then
  wget -q -O ~/.local/bin/phpcpd \
    https://phar.phpunit.de/phpcpd.phar
  chmod +x ~/.local/bin/phpcpd
fi
```

> `~/.local/bin`이 PATH에 없으면 아래를 `~/.bashrc` 또는 `~/.zshrc`에 추가하세요:
> ```bash
> export PATH="$HOME/.local/bin:$PATH"
> ```
> `install.sh`를 사용하면 PATH 설정까지 자동으로 처리됩니다.

JS 도구(ESLint, Biome, knip 등)는 프로젝트 디렉토리에서 스킬이 자동으로 설치합니다.

---

### `codex-delegate` — Codex CLI 설치

```bash
npm install -g @openai/codex
```

설치 후 OpenAI API 키를 설정합니다:

```bash
export OPENAI_API_KEY="sk-..."
# ~/.bashrc 또는 ~/.zshrc에 추가하여 영구 설정
```

> **Claude Code Codex 플러그인 (선택)**
> `install.sh`의 Codex 단계에서 Claude Code용 공식 Codex 플러그인(`codex@openai-codex`) 설치 여부를 묻습니다.
> 설치하면 `codex-delegate` 스킬이 `/codex:review`, `/codex:rescue` 같은 슬래시 커맨드를 우선 사용하고, 없으면 `codex` CLI로 폴백합니다.
> 수동 설치:
>
> ```bash
> claude plugin marketplace add openai/codex-plugin-cc
> claude plugin install codex@openai-codex
> ```

---

### Codex 스킬 설치 (선택)

`install.sh` 실행 시 Codex에도 스킬을 설치할지 묻는 단계가 있습니다. 설치하면 Claude Code와 동일한 스킬을 Codex에서도 사용할 수 있습니다.

- 설치 경로: `~/.codex/skills/local/{스킬명}/`
- `codex-delegate`는 "Claude → Codex 위임" 스킬이므로 Codex 자신에게는 설치되지 않습니다.
- `install.sh`에서 Codex 스킬 설치를 선택하면 Codex용 `UserPromptSubmit` 훅도 별도로 설치할지 묻습니다.

수동으로 설치하려면:

```bash
SKILLS_DIR=~/work/claude-code-skills/skills
mkdir -p ~/.codex/skills/local

ln -s $SKILLS_DIR/use-context7        ~/.codex/skills/local/use-context7
ln -s $SKILLS_DIR/plan-and-build      ~/.codex/skills/local/plan-and-build
ln -s $SKILLS_DIR/systematic-debugging ~/.codex/skills/local/systematic-debugging
ln -s $SKILLS_DIR/web-security-review ~/.codex/skills/local/web-security-review
ln -s $SKILLS_DIR/web-parallel-dispatch ~/.codex/skills/local/web-parallel-dispatch
ln -s $SKILLS_DIR/code-quality-review ~/.codex/skills/local/code-quality-review
ln -s $SKILLS_DIR/branch-merge-review ~/.codex/skills/local/branch-merge-review
ln -s $SKILLS_DIR/web-browser-preview ~/.codex/skills/local/web-browser-preview
```

> `codex-delegate`는 "Claude → Codex 위임" 전용이라 Codex에는 설치하지 않습니다. `web-browser-preview`는 WSL 환경에서만 동작합니다(macOS/네이티브 Linux 미지원).

#### Codex `plan-and-build` 리마인더 훅

자동 설치를 선택하면 훅 스크립트는 `~/.codex/hooks/claude-code-skills-workflow.py`, 설정은 `~/.codex/hooks.json`에 등록됩니다. 프로젝트 설치에서는 각각 `<project>/.codex/hooks/`와 `<project>/.codex/hooks.json`을 사용합니다.

같은 설정 계층의 `config.toml`에 인라인 `[hooks]` 또는 `[[hooks.<Event>]]` 설정이 이미 있으면 자동 설치기가 이를 알리고 기본값으로 `hooks.json` 설치를 건너뜁니다. 두 표현을 함께 사용하려는 경우에만 명시적으로 계속합니다. `[hooks.state.*]` 신뢰 기록은 인라인 훅으로 간주하지 않습니다.

`config.toml`에 `[features] hooks = false` 또는 이전 호환 키인 `[features] codex_hooks = false`가 적용되어 있으면 `hooks.json` 훅이 실행되지 않습니다. 자동 설치기는 적용된 설정을 알리고, 기본값 `No`로 훅 기능을 활성화한 뒤 설치할지 묻습니다. 동의하면 다른 TOML 설정과 주석을 보존하면서 현재 키인 `hooks = true`로 갱신합니다. 프로젝트 설치에서는 사용자 `~/.codex/config.toml`을 직접 바꾸지 않고 프로젝트 `.codex/config.toml`에 활성화 값을 재정의합니다. `hooks`와 `codex_hooks`가 함께 있으면 현재 키인 `hooks`가 우선합니다.

안전한 TOML 검증과 갱신에는 Python 3.11 이상이 필요합니다. 더 낮은 버전에서는 비활성 상태를 알리되 설정을 자동 수정하지 않습니다.

기업 관리 환경의 `allow_managed_hooks_only`는 `config.toml`이 아니라 관리형 `requirements.toml` 정책입니다. 이 저장소의 개인용 설치기는 관리 정책 탐지를 자동화하지 않습니다.

수동 설치:

```bash
mkdir -p ~/.codex/hooks
cp hooks/workflow-reminder.py ~/.codex/hooks/claude-code-skills-workflow.py
chmod +x ~/.codex/hooks/claude-code-skills-workflow.py
```

`~/.codex/hooks.json`의 기존 설정을 보존하면서 아래 항목을 병합합니다.

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 /home/USER/.codex/hooks/claude-code-skills-workflow.py",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

Codex를 다시 시작한 뒤 `/hooks`에서 새 훅의 내용과 경로를 검토하고 신뢰해야 실행됩니다. 프로젝트 훅은 해당 프로젝트가 신뢰된 경우에만 로드됩니다.

---

## 4단계: 동작 확인

Claude Code를 열고 각 스킬이 정상 인식되는지 확인합니다.

```
/skills list
```

아래 스킬들이 목록에 보이면 설치 완료입니다:
- `use-context7`
- `plan-and-build`
- `systematic-debugging`
- `web-security-review`
- `web-parallel-dispatch`
- `web-browser-preview`
- `codex-delegate`
- `code-quality-review`
- `branch-merge-review`

Codex CLI에서는 `/hooks`를 열어 `claude-code-skills-workflow.py`가 등록됐고 신뢰 상태인지도 확인합니다.

---

## 스킬 사용 예시

| 말하면 | 실행되는 스킬 |
|--------|--------------|
| "Svelte 5 컴포넌트 만들어줘" | `use-context7` — 먼저 Svelte 5 문서 조회 |
| "새 인증 기능을 구현해줘" | `plan-and-build` — 스펙·계획 작성 후 TDD와 병렬화 판단 |
| "원인이 불명확한 오류를 분석하고 고쳐줘" | `systematic-debugging` — 재현과 근본 원인 확인 후 최소 수정 |
| "보안 검토해줘" | `web-security-review` |
| "API 스펙 나왔으니까 백/프론트 동시에 만들어줘" | `web-parallel-dispatch` |
| "브라우저에서 확인해봐" | `web-browser-preview` |
| "코덱스에게 검토해" | `codex-delegate` — 4개 서브에이전트 병렬 검토 |
| "코덱스에게 구현시켜" | `codex-delegate` — 분할 구현 위임 |
| "코드 품질 검토해줘" | `code-quality-review` |
| "머지 전에 브랜치 리뷰해줘" | `branch-merge-review` |

---

## 문제 해결

**스킬이 목록에 안 보임**
→ Claude Code 재시작. 심볼릭 링크 대상 경로가 올바른지 확인: `ls -la ~/.claude/skills/`

**context7 MCP 연결 실패**
→ `npx -y @upstash/context7-mcp` 단독 실행으로 오류 메시지 확인. Node.js 버전 18+ 필요.

**브라우저 CDP 연결 실패**
→ Windows Chrome이 `--remote-debugging-port=9333` 옵션으로 실행 중인지 확인.
→ WSL 방화벽이 포트 9333을 차단하지 않는지 확인.

**PHP PHAR 실행 오류**
→ PHP CLI 설치 확인: `php --version`
→ PHAR 파일 실행 권한 확인: `ls -la ~/.local/bin/phpstan`
