# 사용 패턴·모델 지침 정합 교정

목표: 실사용 데이터와 현재 모델 지침 가이드에 맞춰 환경 오류를 고치고, 스킬·훅·에이전트 지시문의 중복·이력 서술을 줄인다. 동작 규칙(읽기 전용 경계, 신뢰 게이트, 라우팅 우선순위)은 유지한다.

현재 상태: `main`, HEAD `023eb0e`, clean. codex-cli 0.154.0, Claude Code 2.1.273. 사용자가 교정 진행과 Codex 의논을 승인했고 Herdr 병렬 실행 지침이 있다. Codex 1차 검토(브리프 `codex-brief-01.md`) 결과 차단 사유 없음, 조건 3개.

범위 밖: 커밋·푸시, 에이전트 삭제, Claude 전용 frontmatter(`disallowed-tools`·`context`·`agent`·`paths`) 추가, `permissionMode: plan` 추가, 리뷰 스킬의 실행 구조 변경.

## Codex 조건

- (4) 부모가 auto 모드면 서브에이전트 `permissionMode: plan`이 무시된다. 읽기 전용 보장으로 쓰지 않고 금지 지침을 유지한다.
- (7) code-quality-review 본문에 `READ_ONLY`·`UNTRUSTED_DIFF` 결정과 export 절차는 남긴다. 불신 코드 실행 상세만 참조로 분리한다.
- (B-a) Claude 전용 frontmatter는 Codex 로더 호환 확인 전까지 추가하지 않는다.
- (3) `< /dev/null`은 프롬프트를 인자로 넘기는 형식에만 붙인다. stdin `-` 형식에는 붙이지 않는다.

## 단계

1. 환경: `~/.claude.json`의 `codex` MCP 서버 제거, `~/.claude/settings.json`의 죽은 `mcpServers.context7`·`mcp__codex__codex`·잔재 허용 항목 제거, Claude 측 `find-docs` 스킬 제거(전역 규칙과 중복). 검증: 다음 세션 MCP 연결 오류 소멸은 재시작 후 확인.
2. codex-delegate: `< /dev/null`·백그라운드 실행 안내, 이력 서술을 현재 규칙으로 전환, `codex review` 최상위 서브커맨드 언급. use-context7: CLI 우선 축약. README·INSTALL의 security-auditor 실행 단위 설명을 실제(인라인 persona)에 맞춤. security-auditor claude.md에 `skills: [web-security-review]` 사전 로드.
3. code-quality-review: 불신 코드 실행 상세를 `references/untrusted-execution.md`로 이동, 본문에는 게이트 결정·export 유지. 스킬 전반의 이력·재현 서술을 현재 규칙으로 전환.
4. description 축약(branch-merge-review·evidence-first-review 양방향 반복 제거), 훅 리마인더 문안 축약(Python·PowerShell 동일), 관련 테스트 문구 조정.
5. 검증: 전체 테스트, 변경 스킬 `quick_validate.py`, `git diff --check`. 각 단계 후 Codex 계획 대비 검토, 최종 검토.

## 진행 기록

- 1단계: Claude Code auto 모드 분류기가 사용자 홈 설정 수정을 "자기 수정"으로 거부. 실행 명령을 최종 보고에 정리해 사용자 결정으로 넘김.
- 2단계 완료. Codex 검토 HOLD 1건(구현 예제 `< /dev/null` 누락)·Low 3건(사전 로드는 Claude 한정 명시, stdin 문구 한정) 반영.
- 3단계: 불신 실행 상세를 `references/untrusted-execution.md`로 이동. 해당 계약 테스트 클래스의 읽기 위치를 참조 파일로 변경(게이트 결정·export·run-state는 본문 유지). PHP 기준 249건·스킬 계약 64건 통과.
- 4단계: description 2개와 훅 리마인더 3종(Python·PowerShell) 축약. 실제 powershell.exe로 3건 대조 일치.
- 5단계: 전체 445 테스트 OK, 변경 스킬 5개 quick_validate 통과, `git diff --check` 통과. Codex 최종 검토 GO. Low 1건(내부 브랜치의 새 빌드 훅 예외 문장을 본문에도 유지) 반영. references/ 안의 실측 서술("Measured on …")은 근거 문서 성격이라 이번 범위에서 제외.
- 커밋·푸시는 하지 않음(사용자 요청 없음).
