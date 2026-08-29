# 다국어 리뷰 지원 — 후속 작업

`feat/multilang-review-support` 브랜치에서 남긴 항목.

**상태: P0 닫음.** 19라운드의 단계별 검토는 각 단계의 지적을 닫았지만, 그 뒤 수행한
**독립 병합 리뷰**(Claude·Codex 각자 수행 후 교차 검증)에서 신뢰 경계 계약이
오케스트레이션 단계에서 fail-open 이라는 Critical 이 나왔다 — 하위 게이트는
`READ_ONLY`/`UNTRUSTED_DIFF` 로 켜지는데 상위 dispatch 가 그것을 전달하지 않았다.
단계별 검토가 각 조각을 봤을 뿐 **조각을 잇는 경로**를 보지 않았다는 뜻이었다.

**독립 병합 리뷰의 발견은 전부 닫혔다.** P0 7건(C1·H1·C2·C3·M3·H3·M1)은 `73d92e8`
이후 여러 커밋에서, P1 이하 8건(H2·M2·M4·M5·CR-1·CR-2·L1·CR-3)은 `fix/multilang-review-followups`
브랜치에서 닫았다. 식별자와 표식은 `.uniqid/2026-08-29-multilang-review-merge-block.md`
에 있다.

CR-1 을 닫으면서 실행 검증이 실제로 결함을 잡았다 — Python·Go·Rust 읽기 전용 명령을
문서에서 뽑아 임시 프로젝트에서 돌렸더니, 문자열 검사로는 보이지 않던 것들이 드러난다.
`ruff` 에서 `--no-cache` 를 빼면 `.ruff_cache/` 가 저장소에 생기고, `go build` 에서
`-o` 를 빼면 바이너리가 남는다. 여섯 가지 변이가 전부 RED 다.

아래는 그와 별개로 후속에 남기는 항목이다.

## 1. 네이티브 Windows PHPStan 종단간 검증

`references/php-quality.md` 의 PowerShell 게이트는 **PowerShell 5.1 문법 검증만** 거쳤다.
개발에 쓴 Windows 호스트에 PHP·PHPStan 이 없었다.

문서는 이 상태를 **잠정(provisional)** 으로 명시하고, 신뢰하지 않는 diff 에서는
판정을 흉내내지 않고 무조건 중단(`windows-gate-unverified`)하도록 되어 있다.

승격하려면 Windows 에 PHP + PHPStan 을 두고:

1. `tmpDir` 이 저장소 안을 가리키는 프로젝트에서 읽기 전용 리뷰를 실행
2. `git status` 가 깨끗한지 확인
3. scratch 디렉터리가 정리됐는지 확인
4. 프로젝트의 `level` 등 설정이 그대로 적용됐는지 확인

확인되면 문서의 "잠정" 문구를 걷고, 신뢰 게이트의 `windows-gate-unverified` 무조건
중단도 POSIX 와 같은 per-risk 판정으로 바꿀 수 있다.

## 2. 주석 안의 캐시 설정으로 인한 오탐 (해소됨, 기록만)

라운드12 시점에는 `# tmpDir: .cache` 같은 주석까지 위험으로 잡아 안전한 분석을
건너뛰는 오탐이 있었다. 캐시를 **판정하지 않고 격리**하는 방식으로 바뀌면서
원인이 사라졌다. 되돌아가지 않도록 기록해 둔다.

## 3. D′ 규칙 위반 취급 (보류)

`Rule: <출처 file:line> — violated | unclear; effect: blocking | non-blocking`
형태로 규칙 기반 finding 에 한 줄을 더하는 안. 선행 조건은 Claude 와 Codex 가
공유할 규칙 원천의 합의이며, 이 저장소에 `CLAUDE.md`·`AGENTS.md` 가 없고 스킬이
양쪽 클라이언트에서 돌기 때문에 아직 성립하지 않는다.

심각도는 **영향 기반**을 유지한다 — `php-backend-security.md` 가 같은 `MUST` 문법에
Critical / Medium–High / Medium 을 매기는 것이 문법 기반 승격이 틀렸다는 직접 증거다.

## 4. `web-security-review` 스킬 개명 (별도 작업)

이름이 웹 전용을 시사하지만 이제 CLI·데몬·라이브러리도 다룬다. 개명하려면
카탈로그 `legacyNames` alias 계약, 소유권 검증 후 경로 이동, POSIX·Windows ×
Claude·Codex 네 조합의 설치·재설치·제거 계약 테스트가 필요하다.
