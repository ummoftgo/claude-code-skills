# 팀 스킬 설치 가이드

이 문서는 팀에서 개발한 Claude Code 스킬 6종을 새 개발 환경에 설치하는 방법을 설명합니다.

---

## 스킬 목록

| 스킬 이름 | 역할 |
|-----------|------|
| `use-context7` | 프레임워크 코드 작성 전 최신 공식 문서 조회 |
| `web-security-review` | PHP 백엔드 + 프론트엔드 보안 취약점 검토 |
| `web-parallel-dispatch` | 에이전트 병렬 실행으로 개발 속도 향상 |
| `web-browser-preview` | WSL에서 Windows Chrome으로 작업 결과 확인 |
| `codex-delegate` | Codex CLI 서브에이전트에 검토/구현 위임 |
| `code-quality-review` | CLI 도구 기반 코드 품질 종합 검토 |

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

# SKILLS_DIR을 클론한 실제 경로로 변경하세요
SKILLS_DIR=~/work/claude-code-skills

# 6개 스킬 모두 심볼릭 링크 등록
ln -s $SKILLS_DIR/use-context7        ~/.claude/skills/use-context7
ln -s $SKILLS_DIR/web-security-review ~/.claude/skills/web-security-review
ln -s $SKILLS_DIR/web-parallel-dispatch ~/.claude/skills/web-parallel-dispatch
ln -s $SKILLS_DIR/web-browser-preview ~/.claude/skills/web-browser-preview
ln -s $SKILLS_DIR/codex-delegate      ~/.claude/skills/codex-delegate
ln -s $SKILLS_DIR/code-quality-review ~/.claude/skills/code-quality-review
```

> **팁**: 심볼릭 링크 대신 복사하려면 `ln -s` 대신 `cp -r`을 사용하세요.
> 단, 복사 방식은 원본 파일 수정이 자동 반영되지 않습니다.

등록 후 Claude Code를 재시작하면 스킬이 활성화됩니다.

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
    https://static.phpmd.org/php/latest/phpmd.phar
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

---

## 4단계: 동작 확인

Claude Code를 열고 각 스킬이 정상 인식되는지 확인합니다.

```
/skills list
```

아래 스킬들이 목록에 보이면 설치 완료입니다:
- `use-context7`
- `web-security-review`
- `web-parallel-dispatch`
- `web-browser-preview`
- `codex-delegate`
- `code-quality-review`

---

## 스킬 사용 예시

| 말하면 | 실행되는 스킬 |
|--------|--------------|
| "Svelte 5 컴포넌트 만들어줘" | `use-context7` — 먼저 Svelte 5 문서 조회 |
| "보안 검토해줘" | `web-security-review` |
| "API 스펙 나왔으니까 백/프론트 동시에 만들어줘" | `web-parallel-dispatch` |
| "브라우저에서 확인해봐" | `web-browser-preview` |
| "코덱스에게 검토해" | `codex-delegate` — 4개 서브에이전트 병렬 검토 |
| "코덱스에게 구현시켜" | `codex-delegate` — 분할 구현 위임 |
| "코드 품질 검토해줘" | `code-quality-review` |

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
→ PHAR 파일 실행 권한 확인: `ls -la /usr/local/bin/phpstan`
