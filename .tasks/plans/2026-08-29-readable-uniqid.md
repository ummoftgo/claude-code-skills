# 사람이 읽을 수 있는 고유 표식

`feat/readable-uniqid` — `feat/multilang-review-support`(`9777d06`) 위에 쌓음.

## 목표와 비목표

**목표.** 계획·작업·요구사항·리뷰 발견에 부여하는 짧은 식별자(`A1`, `FR-001`, `CH-2`)가
사람에게 보일 때는 항상 뜻을 함께 전달하게 한다. 에이전트가 쓰는 짧은 형태는 그대로 두고,
사람이 읽는 표식을 `.uniqid/` 레지스트리에서 관리한다.

**비목표.** 이슈 트래커를 대체하지 않는다. 한 문서 안에서 소비되고 끝나는 임시 번호까지
등록하게 만들지 않는다. 기존에 발행된 식별자를 소급 재번호하지 않는다.

## 현재 맥락

확인한 사실:

- 식별자를 발행하는 지점은 `plan-and-build`(`FR-001`/`SC-001`), `branch-merge-review`
  (`CH-1`/`M-1`/`L-1`), 그리고 리뷰·검토 과정에서 즉흥으로 만드는 발견 번호다.
- `skills/plan-and-build/SKILL.md`의 "Identify requirements when the work needs tracing"이
  이미 식별자 수명주기(재번호 금지·재사용 금지·`withdrawn` 유지)를 정의한다. 새 규칙은
  이것과 어휘를 맞춘다.
- `tests/test_skill_contracts.py`가 스킬 등록 대칭성, 참조 파일 고아 여부,
  `agents/openai.yaml` 기본 프롬프트를 강제한다. 새 스킬은 이 계약을 통과해야 한다.
- 이 저장소의 계획 문서는 `.tasks/plans/`에 커밋된다. `.uniqid/`도 같은 취급을 한다.

가정:

- 사용자의 주 소비 경로는 대화창 보고와 `.tasks/` 문서다. 외부 트래커 연동은 없다.
  틀리면 레지스트리 형식에 외부 ID 열이 필요해진다.

## 명세

### 레지스트리

- 위치: 프로젝트 루트 `.uniqid/{yyyy-mm-dd}-{slug}.md`. ID 집합 하나당 파일 하나.
- git에 커밋한다.
- 각 파일은 제목, `feature:` 한 줄, `문서:` 한 줄, 표 하나를 가진다.
  열: `ID | 읽을 수 있는 표식 | 한 줄 설명 | 상태`.
  `문서:`는 이 ID들을 정의한 원본 문서 경로다. 없으면 `-`.
- 상태 어휘는 닫힌 집합: `open` · `in-progress` · `done` · `withdrawn`.

### 렌더링

- 사람이 읽는 출력에서 `ID(feature/표식)` 형태로 쓴다. 예: `C1(리뷰신뢰경계/신뢰상태-전달-누락)`.
- 한 문서·한 메시지 안에서 **최초 언급만** 완전형, 이후는 짧은 형태.
- 에이전트 내부 작업·코드·커밋 제목에서는 짧은 형태를 그대로 쓴다.

### 표식 규칙

- 한글 허용. 공백 대신 `-`. `/`는 feature 구분자이므로 표식에 넣지 않는다.
- 2~4 낱말, 대략 20자 이내.
- 같은 feature 안에서 유일해야 한다.
- 내용을 말해야 한다. `문제-1`, `항목-A` 같은 비어 있는 표식은 금지.

### 적용 임계

다음 중 하나라도 참일 때만 등록한다.

- 다른 문서에서 이 ID를 참조하게 된다.
- ID가 한 세션·한 보고서보다 오래 산다.
- 사람에게 이 ID로 결정을 요청한다.

## 요구사항

```
FR-001: `.uniqid/` 레지스트리 파일 형식과 상태 어휘를 정의한다.
FR-002: `ID(feature/표식)` 렌더링 규칙과 최초 언급 규칙을 정의한다.
FR-003: 표식을 부여할 임계와 표식 작성 규칙을 정의한다.
FR-004: 수명주기(재번호·재사용 금지, `withdrawn` 보존)를 plan-and-build와 같은 어휘로 정의한다.
FR-005: 식별자를 발행하는 기존 스킬이 이 규칙을 참조하게 한다.
FR-006: 새 스킬을 설치 대상으로 등록한다(components.json, Claude·Codex 양쪽).

SC-001 (verifies FR-001) — 검증: 스킬 본문이 `.uniqid/{yyyy-mm-dd}-{slug}.md`와 네 상태 어휘를 모두 담는지 계약 테스트로 확인
SC-002 (verifies FR-002) — 검증: 스킬 본문이 완전형 예시와 "최초 언급" 규칙을 담는지 계약 테스트로 확인
SC-003 (verifies FR-003) — 검증: 스킬 본문이 세 임계 조건과 `/` 금지 규칙을 담는지 계약 테스트로 확인
SC-004 (verifies FR-004) — 검증: 스킬 본문이 `withdrawn`과 재번호 금지를 담는지 계약 테스트로 확인
SC-005 (verifies FR-005) — 검증: plan-and-build·branch-merge-review·evidence-first-review·
        report-output·safe-checkpoint가 각각 `readable-ids`를 이름으로 참조하는지 테스트로 확인
SC-006 (verifies FR-006) — 검증: components.json에 한 항목만 있고 claude/codex × posix/windows가
        모두 true인지, 스킬 디렉터리 파일 집합이 승인 목록과 일치하는지 테스트로 확인
```

## 구현 계획

1. 새 스킬 `skills/readable-ids/` 작성 — `SKILL.md`, `agents/openai.yaml`,
   `references/registry-format.md`. covers: FR-001, FR-002, FR-003, FR-004
   — 검증: `python -m unittest tests.test_skill_contracts`
2. `components.json` 등록. covers: FR-006 — 검증: 같은 테스트의 등록 대칭성 검사
3. 발행 지점 연결 — plan-and-build, branch-merge-review(SKILL + 통합 보고 템플릿),
   evidence-first-review, report-output, safe-checkpoint 핸드오프 템플릿.
   covers: FR-005 — 검증: 새 계약 테스트
4. 계약 테스트 추가 — SC-001~006의 검사를 `tests/test_skill_contracts.py`에 넣고,
   거부 검증(구현을 되돌리면 RED)까지 확인. covers: FR-001~FR-006
   — 검증: 저장소 전체 테스트
5. README 스킬 설명 갱신. covers: FR-005
6. 현재 열려 있는 다국어 리뷰 P0 발견을 `.uniqid/`에 백필. covers: FR-001, FR-002
   — 검증: 후속 작업 문서의 ID가 레지스트리에서 해석되는지 눈으로 확인

## TDD 결정

**적용한다(계약 테스트 한정).** 이 저장소의 스킬은 문서이고, 이미 문서 내용을 계약으로
고정하는 테스트 관행이 있다. 6단계 중 4단계에서 테스트를 먼저 쓰지 않고 구현 뒤에 붙이면
"통과하지만 아무것도 지키지 않는 테스트"가 되기 쉬우므로, 각 검사를 넣은 직후
해당 문장을 제거해 RED를 확인한다. 프로덕션 코드가 아니므로 red-green-refactor 전체
사이클은 적용하지 않는다.

## 병렬화 결정

**순차.** 3단계가 1단계의 스킬 이름과 참조 표기에 의존하고, 4단계가 1~3단계 산출물을
모두 읽는다. 독립 워크스트림이 없다.

## 설계 승인 결정

**받았다.** 배포 범위(저장소 스킬), 레지스트리 형식(ID 집합별 파일), 커밋 여부(커밋)
세 가지를 사용자가 명시적으로 선택했다. 남은 것은 스킬 이름과 문장 배치 같은 통상적
판단이므로 추가 승인 지점을 두지 않는다.

## Deferred

- 레지스트리 표를 검사하는 도구(중복 표식·미등록 ID 탐지). 지금은 규칙만 있고 강제는 없다.
  규칙이 실제로 쓰이는지 몇 번 확인한 뒤에 만드는 편이 낫다.
- 이미 발행된 과거 문서의 ID 전면 백필. 6단계는 **현재 열려 있는** P0 항목만 다룬다.
