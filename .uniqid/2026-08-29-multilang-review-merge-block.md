# 다국어 리뷰 지원 — 독립 병합 리뷰 발견

feature: 다국어리뷰
문서: .tasks/plans/2026-08-16-multilang-review-followups.md

Claude·Codex가 각자 수행한 뒤 교차 검증한 독립 병합 리뷰의 발견. 식별자는 각 리뷰가
발행한 그대로 보존한다(재번호 금지). `CR-`은 교차 검증 라운드에서 새로 나온 것이다.

| ID | 읽을 수 있는 표식 | 한 줄 설명 | 상태 |
|----|------------------|-----------|------|
| C1 | 신뢰상태-전달-누락 | 오케스트레이터가 `READ_ONLY`/`UNTRUSTED_DIFF`를 하위 리뷰어에 전달하지 않아 게이트가 기본 비활성 | done |
| H1 | 프롬프트-인젝션-경계 | raw diff가 지시와 같은 프롬프트 층에 놓여 데이터 전용 경계가 없음 | done |
| C2 | go테스트-레이스-허용 | 읽기 전용에서 `go test -race`를 명시적으로 허용 | done |
| C3 | cargo감사-설정-미점검 | cargo 설정 사전 점검 없이 `cargo audit` 실행 | done |
| M3 | go툴체인-고정-누락 | `GOTOOLCHAIN=local` 미지정으로 툴체인을 diff가 좌우할 수 있음 | done |
| H3 | 실행선택-파일-분류누락 | `.cargo/config`, `rust-toolchain.toml`, `go.work`, `*.jsx`, lockfile, `.npmrc` 미분류 | done |
| M1 | rename수집-NUL안전위반 | rename 수집이 `cut -f2`를 써서 NUL-safe 규칙과 모순 | done |
| H2 | psr4-배열값-타입오류 | PSR-4 값이 배열이면 TypeError, prefix가 여럿이면 첫 번째만 사용 | open |
| M2 | 설정명-개수-모순 | 리뷰어 프롬프트는 세 개, php-quality는 여섯 개로 설정 파일명을 다르게 셈 | open |
| M4 | windows-널장치-표기 | `go build -o`의 Windows 대상이 `/dev/null`로 적혀 있음 | open |
| M5 | 저장소불변-경로만비교 | `repo_unchanged`가 경로 집합만 보고 기존 파일 내용 해시는 비교하지 않음 | open |
| CR-1 | 다언어-실행테스트-부재 | Python·Go·Rust는 명령 문자열만 검사하고 실제 실행 회귀 방어가 없음 | open |
| CR-2 | rg-경로인자-누락 | 첫 검색 `rg` 43개가 경로 인자 없이 stdin을 읽을 수 있음 | open |
| L1 | readme-스킬설명-낡음 | README가 `web-security-review`를 여전히 PHP/프론트엔드로만 설명 | open |
| CR-3 | description-길이-증가 | `code-quality-review` description 699→1080자, 라우팅 악화는 미측정 | open |
| H4 | npm감사-코드실행 | `.npmrc`의 `node-options`가 `npm audit` 자체에는 적용되지 않음이 확인되어 철회 | withdrawn |
