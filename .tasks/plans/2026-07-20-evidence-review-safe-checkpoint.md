# 증거 우선 검토·안전 체크포인트 워크플로우 확장

## 목표와 비목표

- Claude Code와 Codex가 함께 쓰는 `evidence-first-review`, `safe-checkpoint` 스킬을 추가한다.
- 기존 `UserPromptSubmit` 훅을 세 워크플로우 안내를 조합하는 fail-open 분류기로 확장한다.
- 설치·제거 목록과 README/INSTALL 문서를 두 스킬에 맞게 대칭 갱신한다.
- 훅은 안내만 출력하며 명령, 파일 변경, staging, commit, push를 실행하지 않는다.
- `data-contract-auditor`, 새 훅 이벤트·에이전트·자동 Git 작업은 이번 범위에 포함하지 않는다.

## 현재 맥락

- `hooks/workflow-reminder.py`는 현재 `plan-and-build`만 안내하고 Claude의 `user_prompt`와 Codex의 `prompt`를 모두 처리한다.
- `install.sh`와 `uninstall.sh`는 Claude/Codex별 스킬 배열과 단일 워크플로우 훅 설치·제거 흐름을 갖고 있다.
- `tests/test_workflow_reminder.py`, `tests/test_skill_contracts.py`, `tests/test_workflow_hook_config.py`가 훅과 설치 계약을 검증한다.
- 새 스킬은 저장소 관례와 공식 `skill-creator` 초기화·검증 도구를 따르며, 각 디렉터리는 `SKILL.md`, `agents/openai.yaml`, 단일 reference만 둔다.
- 2026-07-20 기준 `main` 작업 트리는 깨끗하고 기존 58개 테스트가 통과한다.

## 명세

### `evidence-first-review`

- 컨텍스트 우선·읽기 전용 설계/코드/데이터 검토, 원본 JSON/CSV/DB 검증, 비-Git 현재 파일 검토, 이전 finding 재검토와 최종 승인 요청에 사용한다.
- 일반 최초 PR/브랜치 머지 검토는 `branch-merge-review`로 라우팅한다.
- 요청에서 `initial`, `recheck`, `final-approval` 모드를 선택한다.
- 명시된 범위와 컨텍스트를 먼저 잠그되 현재 코드, diff, 원본 데이터, 런타임 결과로 독립 검증한다.
- 명시적 읽기 전용 요청에서는 파일·report 생성/수정, 설치, checkout/worktree, staging을 금지한다.
- 사용자 형식이 없으면 심각도, `file:line`, 증거, 영향, 구체 권고, 최종 판정으로 메시지에 보고한다.

### `safe-checkpoint`

- 선택적 커밋, 체크포인트, 퇴근 전 마무리, 재개, 인수인계 요청에 사용한다.
- branch/upstream/status/diff/manifest/기존 handoff를 먼저 읽고 요청 범위, 무관한 dirty 변경, 보존할 생성물을 분리한다.
- 권한을 상태 확인, handoff 작성, commit, push, 실패한 WIP commit으로 분리하고 요청되지 않은 쓰기 권한을 추론하지 않는다.
- 일반 commit은 검증 실패 시 중단하고 명시적 WIP만 `wip:` commit과 실패 기록을 허용한다.
- push 뒤 HEAD/upstream/dirty 상태를 재검증한다.
- handoff는 기존 source of truth를 우선하며, 새 경로는 명시적 작성 요청이 있을 때만 `.tasks/handoffs/YYYY-MM-DD-{slug}.md`를 사용한다.

### 워크플로우 훅

- 분류 결과를 실행 순서대로 `plan-and-build`, `evidence-first-review`, `safe-checkpoint` 안내의 조합으로 출력한다.
- `evidence-first-review`는 명시적인 무수정 제약에만 반응하고 평범한 리뷰 요청에는 침묵한다.
- `safe-checkpoint`는 인수인계·재개·선택적 commit/push·퇴근 마무리 의도가 드러날 때만 반응하고 단순 퇴근 인사에는 침묵한다.
- 프롬프트 전체에 명시적 무수정 제약이 있으면 구현 단어가 있어도 `plan-and-build`를 억제한다.
- malformed/non-object JSON과 비문자열 prompt는 아무 출력 없이 성공 종료한다.

## 구현 계획

1. 훅 조합·억제·fail-open 사례와 두 스킬의 권한/모드/설치 대칭 계약 테스트를 먼저 추가해 예상 실패를 확인한다.
2. 공식 `init_skill.py`로 두 스킬을 초기화하고 승인된 파일 구성만 남긴 뒤 본문·reference·UI 메타데이터를 작성한다.
3. `workflow-reminder.py`를 독립 분류기와 순서 보장 조합 출력으로 리팩터링한다.
4. Claude/Codex 설치·제거 배열과 설치 화면 문구를 대칭 갱신한다.
5. README/INSTALL의 스킬 수, 표, 링크, 트리거 예시, 훅 설명을 갱신한다.
6. 집중 테스트, 전체 테스트, Python 문법 검사, shell 문법 검사, 두 스킬 validator, `git diff --check`를 실행한다.

## TDD 결정

TDD를 적용한다. 훅의 입력/출력과 설치 목록은 부작용 없이 명확한 계약 테스트로 표현할 수 있고, 요구사항이 구체적인 경계 사례를 열거하므로 failing-first가 회귀와 과도한 트리거를 방지한다. 스킬 Markdown과 문서는 계약 테스트를 먼저 추가한 뒤 작성한다.

## 병렬화 결정

순차 진행한다. 훅, 설치 배열, 문서, 계약 테스트가 같은 스킬 이름과 안내 문구를 공유해 파일 소유권이 겹치며, 구현 전 병렬화 이득보다 통합 불일치 위험이 크다. 자동 검증 후의 독립 읽기 전용 서브에이전트 검증은 별도 사용자 승인 후에만 수행한다.

## 설계 승인 결정

추가 승인 체크포인트는 필요하지 않다. 사용자가 이 문서와 동일한 동작·범위·비목표를 담은 이전 계획을 명시적으로 구현하라고 승인했으며, 해결되지 않은 아키텍처·스키마·외부 연동 선택지가 없다.

## 수용 기준

- 두 스킬이 정확한 파일 구성으로 존재하고 `quick_validate.py`를 통과한다.
- 두 `agents/openai.yaml`의 `default_prompt`가 해당 `$skill-name`을 직접 포함한다.
- 훅의 한국어/영어 읽기 전용, 평범한 리뷰 무응답, 체크포인트 의도, 혼합 순서, 억제, fail-open 테스트가 통과한다.
- Claude/Codex 설치·제거 목록에 두 스킬이 대칭 등록되고 문서가 11종과 다중 워크플로우 훅을 설명한다.
- 전체 지정 검증이 통과하며 이번 작업은 commit/push하지 않는다.
