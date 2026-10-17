# branch-merge-review에 Codex 교차 검토 추가

목표: pstack `interrogate`의 핵심(서로 다른 모델이 같은 기준으로 독립 검토하고, 둘 다 찾은 발견을 가장 강한 신호로 본다)을 Codex를 두 번째 모델로 써서 `branch-merge-review`에 흡수한다.

현재 상태: 브랜치 `feat/codex-cross-review`(main `7986b60`에서 분기). codex-cli 0.163.0. 전체 테스트 445건 OK. 리뷰봇(`~/slack-bot/review-bot/code-review`)은 범위 계산과 프로필만 이식하고 보고서 형식은 파싱하지 않는다.

결정:
- 리드가 Claude이고 `codex`가 PATH에 있으면 기본으로 실행한다. 리드가 Codex(리뷰봇 포함)이거나 사용자가 제외를 요청하면 건너뛰고 보고서에 밝힌다.
- Codex 1명이 전체 범위(`CHANGED_SEC`)를 검토한다. 언어별 Codex 리뷰어는 만들지 않는다.
- 프롬프트는 Claude 리뷰어와 같은 Common Instructions와 같은 diff를 쓰고, Claude의 발견은 넣지 않는다. Claude 패스와 같은 시점에 백그라운드로 시작한다.
- 범위 플래그와 커스텀 프롬프트는 함께 쓸 수 없으므로 plain `exec`에 stdin(`-`)으로 넘긴다. 실행·수집 배관은 `codex-delegate` 계약을 따른다.
- 네이티브 Windows PowerShell은 긴 프롬프트 stdin 전달이 검증되지 않았으므로 건너뛰고 밝힌다.
- 완료 게이트에는 넣지 않는다(추가 신호). 실패·미완료는 보고서에 밝히고, 그 경우 단일 모델 검토였다고 적는다.
- pstack의 Act on/Consider 버킷은 들이지 않는다. 기존 심각도·식별자에 `Source` 태그와 합의 지도로 대응시킨다.

범위 밖: evidence-first-review·plan-and-build의 Codex 연동, reflect·blast-radius 이식, 커밋 외 원격 작업.

## 단계

1. SKILL.md Step 2.6(Codex 교차 검토), Step 3 처리, Step 4e(교차 모델 병합) 추가.
2. reviewer-prompts.md에 Codex 프롬프트 템플릿, consolidated-report-template.md에 Source·합의 지도·부록 추가.
3. README 한 줄, 계약 테스트 1개.
4. 검증: 스킬이 지시하는 Codex 명령을 이 브랜치에 실제 실행, 전체 테스트, `git diff --check`, Codex 계획 대비 검토.

## 진행 기록
- 1~3단계 완료(`bfe6c04`). 전체 446 테스트 OK, `git diff --check` 통과.
- 4단계: 템플릿 그대로 조립한 프롬프트(약 2만 자, diff에 마커 문자열이 있어 Step 2 규칙대로 마커 연장)를 `codex -a never -s read-only exec -`에 stdin으로 실제 실행. exit 0, 한국어 보고, `code-quality-review`·`web-security-review` 로드 확인. 발견 0건이라 발견 형식 자체는 미관찰.
- Codex 계획 대비 검토: 차단 사유 없음. 개선 제안(단일 모델 공개 문구 고정) 반영.
- 리뷰봇(`~/work/code-review`)은 Codex 발견 + Claude 판정 구조라 이번 변경과 겹치지 않음. 변경 없음.
- 보완: Step 3 대기 문구를 "4e 전에 Step 2.6 상한 안에서 기다림"으로 정정, 결과는 trap 때문에 파일이 아니라 백그라운드 출력에서 읽도록 명시, Codex 프롬프트에 `branch-merge-review`·`evidence-first-review` 호출 금지 추가(첫 실행에서 Codex가 evidence-first-review를 스스로 로드함).
- 결함 저장소(PHP SQLi·XSS) 실측: codex-delegate 블록 모양 그대로 백그라운드 실행, exit 0, 백그라운드 출력에 High 2건이 심각도·유형·`file:line`·근거·권고 형식으로 나옴, run 디렉터리 삭제 확인, evidence-first-review 미로드 확인.
