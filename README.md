# 팀 AI 스킬 & 에이전트 모음

PHP 백엔드 + 바닐라 JS / jQuery / Svelte / HTMX 프론트엔드 개발팀을 위한 Claude Code / Codex 스킬 및 에이전트 모음입니다.

> **지원 환경**: 현재 **WSL (Windows Subsystem for Linux)** 환경을 기준으로 작성되었습니다.
> macOS / 네이티브 Linux에서는 `web-browser-preview` 스킬 및 `chrome-devtool-protocol.ps1`이 동작하지 않습니다. 나머지 스킬은 정상 사용 가능합니다.

---

## 구조

```
.
├── skills/       Claude + Codex 공용 스킬
├── agents/       역할별 에이전트 (Claude .md + Codex .toml)
├── install.sh    자동 설치 스크립트
├── uninstall.sh  자동 제거 스크립트
└── chrome-devtool-protocol.ps1   Windows Chrome CDP 실행 스크립트
```

---

## Skills

| 스킬 | Claude | Codex | 역할 |
|------|:------:|:-----:|------|
| `use-context7` | ✅ | ✅ | 프레임워크 코드 작성 전 최신 공식 문서 조회 |
| `web-security-review` | ✅ | ✅ | PHP 백엔드 + 프론트엔드 보안 취약점 검토 |
| `web-parallel-dispatch` | ✅ | ✅ | 에이전트 병렬 디스패치로 개발 속도 향상 |
| `code-quality-review` | ✅ | ✅ | PHP/JS CLI 도구 기반 품질 종합 검토 |
| `branch-merge-review` | ✅ | ✅ | 머지 전 3인 병렬 리뷰어 팀 실행 |
| `web-browser-preview` | ✅ | — | WSL → Windows Chrome CDP 미리보기 |
| `codex-delegate` | ✅ | — | Codex CLI 서브에이전트 검토/구현 위임 |

### 트리거 예시

| 말하면 | 실행 |
|--------|------|
| "Svelte 5 컴포넌트 만들어줘" | `use-context7` |
| "보안 검토해줘" | `web-security-review` |
| "백/프론트 동시에 만들어줘" | `web-parallel-dispatch` |
| "코드 품질 검토해줘" | `code-quality-review` |
| "머지 전에 리뷰해줘" | `branch-merge-review` |
| "브라우저에서 확인해" | `web-browser-preview` |
| "코덱스에게 검토해" | `codex-delegate` |

---

## Agents

역할별 에이전트 페르소나입니다. Claude (`claude.md`)와 Codex (`codex.toml`) 형식으로 각각 제공됩니다.

| 에이전트 | Claude | Codex | 역할 |
|----------|:------:|:-----:|------|
| `php-backend-developer` | ✅ | ✅ | PHP/PDO 백엔드 개발 전문가 |
| `frontend-developer` | ✅ | ✅ | Vanilla JS / jQuery / Svelte 5 / HTMX 프론트엔드 전문가 |
| `security-auditor` | ✅ | ✅ | PHP + 프론트엔드 보안 감사 전문가 (읽기 전용) |

### 설치 위치

| | Claude | Codex |
|---|---|---|
| 스킬 | `~/.claude/skills/` | `~/.codex/skills/local/` |
| 에이전트 | `~/.claude/agents/*.md` | `~/.codex/agents/*.toml` |

---

## 설치

```bash
bash install.sh
```

상세 내용은 [INSTALL.md](./INSTALL.md)를 참고하세요.

---

## 부록: Chrome CDP 스크립트 (Windows)

`chrome-devtool-protocol.ps1` — `web-browser-preview` 스킬 사용을 위한 Windows PowerShell 스크립트입니다.

- Chrome을 원격 디버깅 포트(9333)로 실행
- WSL 서브넷만 허용하는 방화벽 규칙 자동 설정
- WSL → Windows portproxy 자동 구성

`install.sh` 실행 시 Windows 바탕화면으로 자동 복사할 수 있습니다.
Windows에서 우클릭 → **PowerShell로 실행** (관리자 권한 자동 요청).

---

## 파일 구조

```
.
├── README.md
├── INSTALL.md
├── install.sh
├── uninstall.sh
├── chrome-devtool-protocol.ps1
│
├── skills/
│   ├── use-context7/
│   ├── web-security-review/
│   │   └── references/
│   ├── web-parallel-dispatch/
│   │   └── references/
│   ├── web-browser-preview/
│   ├── codex-delegate/
│   ├── code-quality-review/
│   │   └── references/
│   └── branch-merge-review/
│
└── agents/
    ├── php-backend-developer/
    │   ├── claude.md
    │   └── codex.toml
    ├── frontend-developer/
    │   ├── claude.md
    │   └── codex.toml
    └── security-auditor/
        ├── claude.md
        └── codex.toml
```
