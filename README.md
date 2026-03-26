# 팀 Claude Code 스킬 모음

PHP 백엔드 + 바닐라 JS / jQuery / Svelte / HTMX 프론트엔드 개발팀을 위한 Claude Code 스킬 모음입니다.

> **지원 환경**: 현재 **WSL (Windows Subsystem for Linux)** 환경을 기준으로 작성되었습니다.
> macOS / 네이티브 Linux에서는 `web-browser-preview` 스킬 및 `chrome-devtool-protocol.ps1`이 동작하지 않습니다. 나머지 스킬은 정상 사용 가능합니다.

## 스킬 목록

### 1. `use-context7` — 최신 공식 문서 조회

프레임워크·라이브러리 코드를 작성하기 전에 context7 MCP(또는 ctx7 CLI)로 최신 공식 문서를 자동 조회합니다. 오래된 API, 잘못된 시그니처, deprecated 패턴 사용을 예방합니다.

**트리거**: Svelte, HTMX, jQuery, PDO 등 외부 라이브러리 코드 작성 시 자동 동작

---

### 2. `web-security-review` — 웹 보안 검토

PHP 백엔드와 프론트엔드 전반의 보안 취약점을 탐지합니다. 심각도별(Critical / High / Medium / Low)로 분류된 리포트를 생성합니다.

**검토 항목 (PHP)**: SQL Injection, XSS 출력 인코딩, CSRF, 세션 보안, 파일 업로드, 인증, 입력 검증, 디렉토리 순회, 에러 노출

**검토 항목 (프론트엔드)**: DOM XSS, jQuery `.html()` 위험, Svelte `{@html}`, HTMX CSRF 설정, localStorage 인증 토큰, AJAX CSRF 헤더

**트리거**: "보안 검토해줘", "security review", 신규 기능 완료 후 보안 점검

---

### 3. `web-parallel-dispatch` — 병렬 에이전트 디스패치

독립적으로 작업 가능한 파트를 여러 서브에이전트에 동시에 맡겨 개발 속도를 높입니다.

| 패턴 | 언제 사용 |
|------|-----------|
| API First | API 스펙 확정 후 PHP 백엔드 + 프론트엔드 동시 구현 |
| Frontend Split | 레이아웃(HTML/CSS)과 JS 로직을 동시에 작성 |
| Multi-Page | 2개 이상의 독립 페이지를 동시에 구현 |
| Full-Stack 3-Way | DB 스키마 설계 → API + 프론트엔드 병렬 구현 |

**트리거**: "백/프론트 동시에 만들어줘", "여러 페이지 병렬로 작업해줘"

---

### 4. `web-browser-preview` — WSL → Windows 브라우저 미리보기

WSL 개발 환경에서 작업 결과를 Windows Chrome CDP로 즉시 확인합니다. Windows 호스트 IP를 동적으로 조회하므로 IP가 바뀌어도 자동으로 대응합니다.

**의존**: `agent-browser` 스킬 + Windows Chrome (`--remote-debugging-port=9333`)

**트리거**: "브라우저에서 확인해", "브라우저로 열어줘", "check in browser"

---

### 5. `codex-delegate` — Codex CLI 위임

Codex CLI 서브에이전트에게 검토 또는 구현을 위임합니다. `.agent-works/` 디렉토리에 컨텍스트 파일을 생성하여 프로젝트 맥락을 전달합니다.

- **검토 모드**: 코드 품질(가독성·구조·중복) + 코드 품질(성능·유지보수) + 보안(PHP 백엔드) + 보안(프론트엔드) — 4개 에이전트 병렬 실행
- **구현 모드**: 작업 범위를 분석하여 백엔드/프론트엔드 또는 레이아웃/로직으로 분할 후 병렬 구현

**트리거**: "코덱스에게 검토해", "코덱스에게 구현시켜"

---

### 6. `code-quality-review` — 코드 품질 검토

CLI 도구를 자동 실행한 뒤 도구가 잡지 못하는 패턴을 추가로 수동 검토합니다.

**PHP 도구**: PHPStan(정적 분석) · phpcs(스타일) · phpmd(복잡도) · phpcpd(중복)

**JS 도구**: ESLint / Biome / Oxlint(프로젝트 설정에 따라 선택) · svelte-check · knip

**검토 카테고리**:
1. 불필요한 주석 (코드 재서술, 주석 처리된 데드 코드)
2. 스타일 불일치 (프로젝트 다수결 기준 이탈)
3. 중복 코드 (copy-paste 패턴, 유사 쿼리)
4. 성능·평가 순서 (값싼 검사를 비싼 연산보다 앞에)

**트리거**: "코드 품질 검토해줘", "리팩토링 포인트 찾아줘"

---

### 7. `branch-merge-review` — 브랜치 통합 리뷰

main/master 브랜치와의 차이를 분석하여 머지 전 품질·보안을 병렬로 검토합니다. 3인 리뷰어 팀(백엔드 품질, 보안, 프론트 품질)이 동시에 검토하고, 팀장이 Critical/High 발견을 교차 검증한 뒤 통합 보고서를 생성합니다.

**리뷰어 구성**:
- 백엔드 품질 리뷰어 — PHP 전문, `code-quality-review` 스킬 사용
- 보안 리뷰어 — OWASP Top10 전문, `web-security-review` 스킬 사용 (전체 파일 담당)
- 프론트 품질 리뷰어 — Svelte/jQuery/HTMX 전문, `code-quality-review` 스킬 사용

**특징**: 리뷰어는 코드를 절대 수정하지 않고 보고만 함. 팀장이 grep 패턴으로 교차 검증 후 최종 확정.

**트리거**: "브랜치 리뷰해줘", "머지 전에 리뷰해줘", "PR 리뷰해줘", "branch review"

---

## 설치

```bash
bash install.sh
```

상세 내용은 [INSTALL.md](./INSTALL.md)를 참고하세요.

## 부록: Chrome CDP 스크립트 (Windows)

`chrome-devtool-protocol.ps1` — `web-browser-preview` 스킬 사용을 위한 Windows PowerShell 스크립트입니다.

- Chrome을 원격 디버깅 포트(9333)로 실행
- WSL 서브넷만 허용하는 방화벽 규칙 자동 설정
- WSL → Windows portproxy 자동 구성

`install.sh` 실행 시 Windows 바탕화면으로 자동 복사할 수 있습니다.
Windows에서 우클릭 → **PowerShell로 실행** (관리자 권한 자동 요청).

## 파일 구조

```
.
├── README.md
├── INSTALL.md                        # 상세 설치 가이드
├── install.sh                        # 자동 설치 스크립트
├── chrome-devtool-protocol.ps1       # Windows Chrome CDP 실행 스크립트
├── use-context7/
│   └── SKILL.md
├── web-security-review/
│   ├── SKILL.md
│   └── references/
│       ├── php-backend-security.md
│       └── web-frontend-security.md
├── web-parallel-dispatch/
│   ├── SKILL.md
│   └── references/
│       └── dispatch-patterns.md
├── web-browser-preview/
│   └── SKILL.md
├── codex-delegate/
│   └── SKILL.md
├── code-quality-review/
│   ├── SKILL.md
│   └── references/
│       ├── php-quality.md
│       ├── js-quality.md
│       └── css-quality.md
└── branch-merge-review/
    └── SKILL.md
```
