# 시니어 코드 작성 기준과 앞뒤 방어를 보는 리뷰

## 목표와 비목표

- **목표 1:** Claude·Codex가 주석 과다, 내부 경로의 중복 방어, 의례적인 실패 먼저 TDD 없이 시니어 개발자처럼 코드를 쓴다.
- **목표 2:** 리뷰가 diff 한 줄만 보고 Critical/High를 매기지 않는다. 앞(진입점)과 뒤(싱크)의 방어를 추적한 뒤 실제 결함인지, 주의만 주면 되는지 판정한다.
- **비목표:** 리뷰봇(`~/work/code-review`) 코드 수정(변경안만 작성), 서드파티 플러그인(ponytail, security-guidance) 수정, 새 심각도 축 도입.

## 현재 맥락

확인한 사실:
- 리뷰 스킬 두 곳이 "의도로 보이면 설명 주석 추가 권고"를 지시한다(`code-quality-review` Documented Intent, `web-security-review` Comment relevance). 리뷰가 주석을 늘린다.
- Codex 전역 지침(`~/.codex/AGENTS.md`)에 주석·경계 검증 규칙이 없다. `comment-style.md`는 Claude 전용(`~/.claude/rules/`).
- `plan-and-build` 검증표가 계산·파싱 등에 "TDD 선호"를 둔다.
- `branch-merge-review` Step 4b grep은 의심 패턴의 존재만 확인하고 다른 층의 방어는 보지 않는다. Common Instructions는 스코프 밖 읽기를 허용만 한다. Severity bar는 Codex 템플릿에만 있다.
- 리뷰봇: 리뷰어·반박·Claude 판정 모두 "DIFF 근거로만"이고, 보안 지적은 `isProtected`로 하향 불가. 리뷰어 cwd는 worktree라 파일 읽기는 가능하다.
- ponytail은 Claude·Codex 모두 활성. security-guidance(Claude)는 턴 종료마다 diff만 보고 high 지적을 되돌려 방어 코드를 유도할 수 있다.
- Claude는 `~/.claude/rules/*.md`를 자동 로드한다. Codex는 `~/.codex/AGENTS.md`를 읽는다(사용자 파일에 ctx7의 `<!-- context7 -->` 마커 블록 선례).

가정:
- Codex 네이티브 리뷰어(`codex exec review`, P0~P3 표기)가 `AGENTS.md`를 읽는지는 미확인. 틀리면 그 경로에는 목표 2 규칙이 닿지 않는다(실측 대상).

## 명세

FR-001(rules/code-writing): 저장소에 `rules/code-writing.md`(한국어, 짧게)를 둔다. 경계에서 한 번 검증, 정당한 상태에만 가드, 에러 삼킴 금지, 보안 방어는 유지, "왜"만 남기는 주석, 동작 테스트와 TDD 한정, 단순함.
FR-002(installer/rule-kind): 설치기가 전역 범위에서 FR-001을 Claude `~/.claude/rules/code-writing.md`(파일, 매니페스트 소유 추적)와 Codex `~/.codex/AGENTS.md` 마커 블록(`<!-- claude-code-skills:code-writing -->` … `<!-- /claude-code-skills:code-writing -->`)으로 배포하고, 제거기가 되돌린다. POSIX·PowerShell 모두. 프로젝트 범위는 설치하지 않고 안내한다.
FR-003(skills/writing-align): `plan-and-build` TDD 문구 한정, 개발 에이전트 2종(Claude·Codex)에 내부 데이터 재검증·나레이션 주석 금지 한 줄.
FR-004(review/no-comment-advice): 두 리뷰 스킬에서 "설명 주석 추가 권고"를 삭제한다.
FR-005(review/context-trace): Critical/High 후보마다 진입점 역추적과 싱크 추적을 하고 셋으로 판정한다. 방어 없음→유지, 모든 경로에서 방어 확인(`file:line`)→지적에서 빼고 Cleared에 "주의"로 남김, 판정 불가→유지+⚠. 비하향 분류(보안 등)는 주석만으로 내릴 수 없고 확인된 방어 코드로만 내린다. 비보호 분류의 문서화된 의도 하향은 기존대로 둔다. 정리한 항목은 Cleared로 남긴다.
FR-006(review/judgment-filters): 가정 대 실제, 코드베이스와 일관된 패턴, 취향은 결함 아님, 지적 부풀리기 금지를 Common Instructions와 리드 판정에 넣는다. Severity bar를 Common Instructions로 옮긴다.
FR-007(review/quality-lens): `code-quality-review`가 내부 중복 방어, 삼킨 에러, 구현에 고정된 테스트를 품질 지적으로 잡는다.
FR-008(review/codex-redesign): Codex 교차 검토에서 합의도 앞뒤 추적을 건너뛰지 않고, Codex 단독 지적은 추적 결과로 판정한다.
FR-009(bot/proposal): 리뷰봇 변경안(바꿀 줄과 이유)을 작성한다. 코드는 고치지 않는다.

SC-001 (FR-002) — 검증: 설치기 계약 테스트와 임시 HOME에서 install→재설치→uninstall 실행, AGENTS.md 기존 내용 보존.
SC-002 (FR-005, FR-006) — 검증: 같은 SQL 싱크를 가진 두 저장소(상위 방어 있음/없음)에 새 Common Instructions로 Codex 실행. 방어 있음은 Low/Info+방어 `file:line`, 없음은 High 유지.
SC-003 (FR-003, FR-004, FR-007, FR-008) — 검증: 계약 테스트로 핵심 문장 고정, 전체 테스트 통과.

## 구현 단계

1. `rules/code-writing.md` 작성 — covers: FR-001 — 검증: 직접 검토.
2. 설치기 rule 종류 — covers: FR-002 — 검증: SC-001. (워크스트림 A)
3. 리뷰 스킬 개정 — covers: FR-004~FR-008 — 검증: SC-002, SC-003. (워크스트림 B)
4. 작성 스킬·에이전트 정렬 — covers: FR-003 — 검증: SC-003. (워크스트림 B)
5. 리뷰봇 변경안 — covers: FR-009 — 검증: 직접 검토.
6. 통합: A 병합, README 반영, 전체 테스트, Codex 계획 대비 검토.

## 검증 전략

문서·지시문 변경은 계약 테스트로 핵심 문장만 고정한다. 설치기는 실행 계약이 바뀌므로 기존 설치기 테스트 방식으로 검증한다. 목표 2는 실측(SC-002)이 핵심 증거다. TDD는 쓰지 않는다.

## 병렬화

A(설치기: `install.sh`, `uninstall.sh`, `scripts/`, `install.ps1`, `uninstall.ps1`, `components.json`, `tests/test_installer_contracts.py`, `tests/windows/`, `INSTALL.md`, README 설치 절)와 B(스킬·에이전트·`tests/test_skill_contracts.py`)는 파일이 겹치지 않는다. 공유 계약은 `rules/code-writing.md` 경로와 마커 이름뿐이고 1단계에서 먼저 커밋한다. A는 Herdr 패널의 Codex에 별도 워크트리로 맡기고, B는 메인이 진행한다. 병합 전에 메인이 A의 diff를 검토한다.

## 설계 승인

사용자가 배포 방식(저장소 원본+설치기)과 리뷰봇 범위(변경안만)를 정했다. 나머지는 그 안의 설계라 추가 승인 없이 진행한다.

## Clarifications

- Q: 공통 작성 규칙을 어디에 둘까 → A: 저장소가 원본, 설치기가 배포.
- Q: 리뷰봇 반영 범위 → A: 스킬 먼저, 봇은 변경안만.

## Deferred

- 프로젝트 범위 rule 설치: 전역만 지원. 팀원이 프로젝트 범위만 쓰면 규칙이 닿지 않는다.
- security-guidance 플러그인 조정: 사용자 판단으로 넘긴다.

## 진행 기록
- 1단계: `rules/code-writing.md` 작성(`9757d25`). 이후 "리뷰할 때" 절 추가.
- 실측(가정 검증): Codex 네이티브 리뷰어는 프로젝트 `AGENTS.md`를 찾아 읽었으나 그 안의 리뷰 지시(첫 줄 표식)는 따르지 않았다. 그래서 `codex-delegate` Mode 1에 머지 판단용 리뷰는 `branch-merge-review`나 Common Instructions를 실은 plain `exec`로 하라는 안내를 넣었다.
- 3·4단계(B, `20ad2a4`): Common Instructions에 CONTEXT TRACE·JUDGMENT, Step 4 재구성(Codex 병합 → 모든 Critical/High 추적 검증), 리뷰 두 곳의 주석 추가 권고 삭제, 품질 범주 5(과잉 방어·테스트 적합성), plan-and-build TDD 한정, 개발 에이전트 정렬. 계약 테스트 1개 추가.
- SC-002 실측: 세 사례 저장소(다른 파일의 `(int)` 캐스팅 / 방어 없음 / `trim`뿐인 `sanitize`)에 새 지침으로 Codex 실행. 결과는 각각 Cleared+"주의: 다른 층에서 방어됨"(방어 `routes/report_route.php:3`) / High 유지+경로 / High 유지("trim은 SQL 삽입을 막지 못함"). 기대와 일치.
- 2단계(A, Herdr 패널 Codex, 워크트리 `wt-rules-installer`, `94c34e0`): rule 종류, `scripts/rule_block.py`, POSIX·PowerShell 설치·제거, 테스트. 메인 검토 중 Windows 실제 실행에서 빈 `AGENTS.md`를 비정상 파일로 판정하는 결함 발견. 원인은 공용 `Get-FileSnapshot`이 빈 byte[]를 `$null`로 풀던 PowerShell 동작이라 그 함수에서 수정. 이후 Windows 통합 테스트 통과, 전체 455 테스트 OK.
- 5단계: 리뷰봇 변경안 `.tasks/plans/2026-10-18-review-bot-context-trace-proposal.md`. 봇 코드는 수정하지 않음.
- Codex 계획 대비 검토: 차단 사유 없음. 개선 4건 반영(방어 확인 항목은 지적에서 빼고 Cleared에 "주의"로 통일, 4a 심각도 예시는 JUDGMENT가 우선, FR-005 문구를 보호 분류 한정으로 정정, FR-003 계약 테스트 추가). 전체 테스트 OK.
