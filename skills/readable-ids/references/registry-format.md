# Registry Format

One file per identifier set, at `.uniqid/{yyyy-mm-dd}-{slug}.md` under the project root. Committed, like the plan it belongs to.

## File template

```markdown
# <제목 — 이 식별자 집합이 무엇에 관한 것인지>

feature: <짧은 도메인 명사>
문서: <이 식별자들을 정의한 원본 문서 경로, 없으면 ->

| ID | 읽을 수 있는 표식 | 한 줄 설명 | 상태 |
|----|------------------|-----------|------|
| ... | ... | ... | ... |
```

## Columns

| Column | Holds |
|---|---|
| `ID` | The short identifier exactly as it appears in working notes — `A1`, `FR-001`, `CH-2`. |
| `읽을 수 있는 표식` | The label. Hyphenated, unique within the `feature`, two to four words. |
| `한 줄 설명` | One line, enough for a reader to recognise the item. Not a specification. |
| `상태` | One of `open` · `in-progress` · `done` · `withdrawn`. |

`feature` sits in the header rather than in a column because a file normally covers one workstream. When a single file genuinely spans two features, add a `feature` column and drop the header line — but prefer splitting the file, since the file name is what a reader scans first.

`문서` points at the plan, report, or issue that defines these items. It is what a reader follows when the one-line description is not enough. Write `-` when the identifiers were minted in conversation and have no document yet.

## Worked example

`.uniqid/2026-08-29-multilang-review-merge-block.md`

```markdown
# 다국어 리뷰 지원 — 병합 차단 항목

feature: 리뷰신뢰경계
문서: .tasks/plans/2026-08-16-multilang-review-followups.md

| ID | 읽을 수 있는 표식 | 한 줄 설명 | 상태 |
|----|------------------|-----------|------|
| C1 | 신뢰상태-전달-누락 | 오케스트레이터가 READ_ONLY를 하위 리뷰어에 전달하지 않음 | open |
| H1 | 프롬프트-인젝션-경계 | raw diff가 지시와 같은 프롬프트 층에 놓임 | open |
| H4 | npm감사-코드실행 | 근거가 재현되지 않아 철회됨 | withdrawn |
```

A report then writes, on first mention:

> 병합을 막는 것은 `C1(리뷰신뢰경계/신뢰상태-전달-누락)`과 `H1(리뷰신뢰경계/프롬프트-인젝션-경계)`입니다.

and afterwards, in the same document:

> C1을 먼저 닫아야 H1의 경계 설계를 검증할 수 있습니다.

## Choosing the file name

`{yyyy-mm-dd}` is the day the identifier set was opened, not the day it was last touched — which is often *not* the date on the document it serves, since findings about a plan are minted long after the plan is.

`{slug}` names what the set is about. Reuse the serving document's slug where that reads naturally, so a reader who found one can guess the other; where the set covers only part of that document — one review's findings against a longer plan — name the part instead. Matching the document exactly is a convenience, not a rule, and it loses to saying what is in the file.

## Two identifier sets, one topic

Keep them in separate files rather than merging. Identifier sets have different lifetimes: a plan's `FR`/`SC` identifiers survive the branch, a review's finding identifiers usually die at merge. Merging them into one file means the long-lived rows are read past every time.
