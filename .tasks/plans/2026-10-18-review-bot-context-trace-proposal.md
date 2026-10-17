# 리뷰봇 변경: 앞뒤 방어 추적 (승인됨, 봇 브랜치 `feat/context-trace`)

대상: `~/work/code-review` (원격 merge-review-bot). 사양 원본은 이 저장소의 `skills/branch-merge-review/references/reviewer-prompts.md` CONTEXT TRACE·JUDGMENT 블록이다. 아래 "바꿀 곳"은 승인 전 초안이고, 실제 구현은 맨 아래 "구현 시 확정한 규칙"이 우선한다.

## 왜

봇은 리뷰어, 반박 검증, Claude 판정 모두 "DIFF 근거로만" 판단하게 지시한다. 리뷰어 cwd가 worktree라 파일을 읽을 수 있는데도 그렇다. 그래서 앞뒤 방어를 확인할 수 없고, 애매하면 keep으로 남아 High가 된다. 보안 지적은 하향 자체가 막혀 있다.

## 바꿀 곳

1. `src/codex/profiles.js` `COMMON_INSTRUCTIONS`
   - CONTEXT TRACE·JUDGMENT 블록을 한국어로 옮겨 추가한다. 스코프 밖 읽기를 "허용"에서 "Critical/High 전 필수"로 바꾼다.
   - JSON 스키마에 `trace`(`undefended` | `defended` | `undecidable`)와 `defenceAt`(문자열, `file:line`)를 추가한다. `defended`면 리뷰어가 low로 보고한다.
   - 응답에 `cleared` 배열(후보, 방어 위치)을 추가해 보고서 "확인 후 제외" 절로 낸다.
2. `INTENSIVE_INSTRUCTIONS`: "diff로 뒷받침되는 것만 보고"를 "diff와 저장소 코드 추적으로 뒷받침되는 것만"으로 바꾼다.
3. `buildRefutePrompt`: "DIFF 근거로만"을 "DIFF와 worktree 코드(호출부·싱크)를 근거로"로 바꾼다. 모든 경로에서 확인된 방어를 `file:line`으로 제시할 수 있으면 `refuted`가 아니라 새 판정 `defended`(→ low로 하향)를 낸다. 애매하면 지금처럼 `uncertain`.
4. `src/review/adjudicate.js`
   - `buildAdjudicatePrompt`의 "판정은 오직 DIFF 코드 증거로만"을 "DIFF와 worktree 코드 추적으로"로 바꾼다. 도구 허용(`CLAUDE_ADJUDICATE_TOOLS`)과 read-guard는 이미 있다.
   - (구현에서 변경) `isProtected`는 그대로 두고, `defended` 판정은 하향 대신 두 번째 독립 판정으로 기록한다. 이동은 `splitCleared`가 인용 검증 후 결정한다.
   - Claude 제한시간(`CLAUDE_TIMEOUT_MS` 90초)은 추적에 짧을 수 있다. 실측 후 조정한다.
5. 보고서 빌더: 지적마다 추적 결과 한 줄, "확인 후 제외" 절 추가.

## 검증

이 저장소에서 쓴 세 사례 저장소(상위 `(int)` 캐스팅, 방어 없음, 이름만 sanitize인 no-op)를 봇 테스트 픽스처로 옮겨, 각각 low·high·high가 나오는지 확인한다.

## 구현 시 확정한 규칙 (2026-10-18)

- 리뷰어는 severity를 바꾸지 않고 `trace`·`defenceAt`만 표시한다. 이동은 `src/review/contextTrace.js`의 `splitCleared`가 결정론적으로 한다(기존 documentedIntent 원칙과 같은 구조).
- 인용 검증: 상대경로, worktree 안(심볼릭 링크 해석 후), secret 파일 아님, 파일 존재, 줄 범위 안. 하나라도 어긋나면 finding 유지.
- 보안 리뷰어 지적·critical은 리뷰어 trace에 더해 두 번째 독립 판정(Claude 교차검증 `defended` 또는 강화 모드 반박 `defended`, 인용 검증 포함)이 있어야 옮긴다. 조건을 못 채우면 "주의 후보"로 표시한 finding으로 남는다. 하나의 LLM 판단만으로 보안 지적을 빼지 않기 위함이다.
- 요청자 참고가 반영된 finding은 옮기지 않는다(keep-only).
- 사본 병합 시 가장 보수적인 trace(undefended > undecidable > defended)를 남긴다. trace가 없는 지적은 undefended로 본다.
- 옮긴 항목은 counts·verdict에서 빠지고 리포트 "확인 후 제외 — 주의: 다른 층에서 방어됨" 절과 Slack 요약 한 줄에 나온다.
