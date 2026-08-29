# 작업 커밋 압축 스킬(`squash-work-commits`) 추가

## 목표와 비목표

- 워크트리·플랜 작업으로 쌓인 잔커밋을 지목된 범위만 안전하게 압축하는 Claude/Codex 공용 스킬을 추가한다.
- 안전 점검 → 범위 확정 → 분할안 → 백업 → 압축 → 트리 대조를 고정 순서로 강제하고, **exit code로 판정한 트리 동일성 없이는 완료 보고를 금지한다.**
- `safe-checkpoint`와의 트리거 중첩을 양쪽 description과 훅에서 결정론적으로 해소한다.
- 현재 훅이 `"이번 변경만 이전 커밋에 fixup으로 넣어줘"`를 `safe-checkpoint`로 오분류하는 문제를 함께 고친다.
- v1은 **선형(머지 없는) 구간 한정**이다. 머지 flatten, 다중 push URL 해석, 재귀 submodule, notes 재매핑, sparse 상태 복원은 이번 범위에 포함하지 않는다.
- 브랜치 전환, main 병합, push·force-push, PR/MR 생성은 스킬이 수행하지 않는다 — 필요한 명령만 제시한다.
- `git stash`는 지원하지 않는다. dirty 워킹트리는 중단이다.
- `refs/plan-base` 같은 장기 커스텀 ref는 도입하지 않는다.

## 현재 맥락

- `skills/`에 스킬 12개, `components.json`이 단일 카탈로그이며 `install.sh`/`install.ps1`은 `catalog_names`로 이를 읽는 카탈로그 구동이라 **설치기 수정이 불필요하다.**
- `tests/test_skill_contracts.py`가 파일 구성·`$skill-name`·대칭 등록·PowerShell 블록·reference orphan을 검사한다. `SkillReferenceIntegrityTest.skill_dirs()`는 `>= 12`를 요구하며 현재 정확히 12개다.
- `agents/openai.yaml`은 12개 중 4개만 보유하고 최신 `report-output`에는 없다 — 살아있는 규약이 아니라 스냅샷이다. 이번 스킬은 보유하는 쪽을 택한다.
- `hooks/workflow-reminder.py`의 `SELECTIVE_GIT_INTENT`(124행)가 `should_safe_checkpoint`(204행)를 통해 rewrite 요청까지 잡는다. `.ps1`도 같은 구조이고 `test_workflow_reminder.py:244`가 parity를 검사한다.
- `safe-checkpoint/SKILL.md` 본문이 "Do not clean up, reset, stash, rewrite"를 명시하므로 히스토리 rewrite를 맡을 수 없다.
- `plan-and-build/SKILL.md`에는 git 관련 지시가 전혀 없다.
- INSTALL.md 공용 스킬 표에 기존 `report-output`이 누락돼 있다(카탈로그에는 존재). 이번 범위 밖으로 둔다.
- 이 계획은 Codex 읽기 전용 검토를 3회 받았고, 검증 가능한 지적은 매번 임시 저장소 실측으로 대조했다. 초안의 git 동작 서술 다수가 실제로 틀렸다.

### 실측 기준 (git 2.52.0)

| 항목 | 실측 결과 |
|---|---|
| `git rebase --autosquash <base>` | **`-i` 없이 동작한다.** `git rebase -h`의 "under -i"는 요구사항이 아니다 |
| `fixup!` / `amend!` 흡수 | 편집기 불필요 (`amend!`는 `fixup -C`로 처리) |
| `squash!` 흡수 | **편집기 필요** — `GIT_EDITOR=false`면 중단 |
| `git commit --fixup=amend:<sha>` | **생성 시점에** 편집기 필요. `-m`과 동시 사용 불가(`fatal`) |
| `git diff --stat <a> <b>` | 내용이 달라도 **exit 0** — 안전장치가 아니다 |
| `git rev-parse <a>^{tree} <b>^{tree}` | 서로 다른 두 tree도 **exit 0** — 안전장치가 아니다 |
| `git diff --quiet --exit-code` | 다르면 exit 1 |
| 연결 워크트리의 `.git` | **파일**이다. `git rev-parse --git-path <name>`이 필요하다 |
| autosquash matcher | 제목뿐 아니라 **`fixup! <sha>`도 흡수한다** |
| 머지 범위 | `c72db6b^1..c72db6b`가 first-parent 1개 vs 전체 2개 — **first-parent 검사는 side-parent를 놓친다** |
| 후보 집합 | `git rev-list HEAD --not --remotes --tags`가 이 저장소에서 현재 **0개** |
| `for-each-ref --contains HEAD` | **현재 브랜치도 반환한다.** `refs/heads/` 한정 + 현재 브랜치 제외 시 공집합 |
| `git stash create` | 워킹트리를 치우지 않고 `refs/stash`도 만들지 않으며, `git stash drop <oid>`는 **실패한다** |
| `reset --soft` 후 commit 훅 실패 | HEAD는 base, 변경은 staged로 잔류 → "깨끗할 때만 hard reset" 게이트에 걸려 **복구 불가** |
| `reset --soft` 후 commit | **원본 author가 소멸한다** |
| `rebase.updateRefs=true` | **다른 워크트리에서 checkout되지 않은** 로컬 브랜치가 조용히 이동한다 |
| `--reapply-cherry-picks` | 조상 base 토폴로지에서는 **무의미하다** — patch-동일 커밋을 심어도 기본 rebase가 3 → 3으로 유지 |
| `--no-gpg-sign` | 존재하고 동작한다 |
| 탐지 명령 | `is-shallow-repository`·`replace -l`·`info/grafts`·`symbolic-ref -q HEAD`·`--untracked-files=all` 모두 실재 확인. 이 저장소 ignored 5건 |
| 현재 훅 | `"...이전 커밋에 fixup으로 넣어줘"`가 `safe-checkpoint`로 오분류된다. 다만 `"fixup 관련 문서 변경만 커밋해줘"` 등도 `safe-checkpoint`이므로 **단순 억제는 정상 요청까지 죽인다** |

## 명세

### 불변식

1. 현재 브랜치에서만 동작한다. 브랜치 전환·main 병합·push·PR/MR 생성을 하지 않는다.
2. 압축 대상은 사용자가 확인한 **정확한 OID 집합**에 한정한다.
3. 공유 여부는 **`locally-unobserved`로만 보고한다** — "미공유"라고 단정하지 않는다.
4. 백업 ref 생성 성공을 **exit code로 확인하기 전에는** 히스토리를 고치지 않는다.
5. 트리 동일성을 **exit code로 판정하기 전에는** 완료라고 보고하지 않는다.
6. 트리가 같아도 의미 보존은 아니다 — 서명·notes·author·empty commit은 별도로 처리한다.

### 진행 차단 조건

**하드 중단(v1 미지원)** — 머지 커밋 존재 / `task_base`가 조상 아님 / base 부재(루트까지 후보) / 후보 0개 / shallow / replace ref·grafts / detached HEAD / 진행 중 rebase·merge·cherry-pick·revert·bisect / dirty 워킹트리 / dirty submodule / 다른 로컬 브랜치나 워크트리가 선택 OID 포함 / git 2.52 미만.

**중단 후 명시 승인 시에만 진행** — 범위 내 서명 커밋(원본 서명은 항상 소멸) / `git notes` 존재 / 의도적 empty commit / 실행 가능한 커밋·rebase 훅 존재 / `locally-unobserved` 위험 승인.

각 조건에 탐지 명령을 못 박고 **fail-closed**로 둔다(명령 자체가 실패하면 중단).

| 조건 | 탐지 |
|---|---|
| detached HEAD | `git symbolic-ref -q HEAD` (exit 1=detached, 128=오류) |
| 진행 중 작업 | `git rev-parse --git-path <n>`로 경로를 얻어 존재 검사 — `rebase-merge`, `rebase-apply`, `MERGE_HEAD`, `CHERRY_PICK_HEAD`, `REVERT_HEAD`, `sequencer`, `BISECT_START` |
| dirty·submodule | `git status --porcelain=v1 -z --untracked-files=all --ignore-submodules=none` |
| shallow | `git rev-parse --is-shallow-repository`가 정확히 `false` |
| replace·grafts | `git replace -l`이 빈 결과 + `git rev-parse --git-path info/grafts` 부재 |
| 머지 | `git rev-list --merges <task_base>..<original_head>` |
| 다른 로컬 브랜치 | 각 OID마다 `git for-each-ref --contains <oid> refs/heads/`에서 **현재 브랜치 제외** |
| 다른 워크트리 | `git worktree list --porcelain -z`에서 **현재 워크트리를 경로로 제외**하고 각 `HEAD`에 `git merge-base --is-ancestor` |
| 서명 / notes / empty | `%G?` / `refs/notes/*` 열거 / tree와 parent tree 비교 |
| 훅 | `core.hooksPath` 반영해 실행 가능한 훅 열거 |

`for-each-ref`를 `refs/heads/`로 좁히지 않으면 remote-tracking과 tag까지 반환되어 "원격 관찰 커밋은 stop-and-ask"와 "다른 ref 포함 시 하드 중단"이 동시에 성립할 수 없다. remote·tag 도달성은 후보 정의가 이미 처리한다.

### 범위 산출

- `observed_remote_boundary` — 후보 집합을 HEAD에서 first-parent로 따라가다 처음 만나는 비후보 커밋.
- `task_base` — 사용자가 확인한 작업 시작점. 기본값은 위 경계지만 같은 값이 아니다.
- `original_head` — 시작 시점 HEAD. rewrite 직전에 `HEAD == original_head`를 재확인한다.
- `git merge-base --is-ancestor "$task_base" "$original_head"`를 먼저 통과해야 한다.
- 공유 판정은 push 대상을 특정하지 않는다. 선택 OID가 어떤 remote-tracking ref·tag에서도 도달 불가할 때만 후보로 삼는다. `@{push}`·`pushRemote`·다중 push URL 해석은 v1에서 하지 않는다.
- `locally-unobserved`는 원격 안전의 증거가 아니다(stale fetch, fetch refspec 밖 destination, URL 직접 push, 다른 remote 전용 ref). rewrite 전에 non-fast-forward 위험을 별도로 승인받는다.
- plan artifact에서 base를 읽는 경로는 그 값을 기록하는 생산자가 없으므로 v1에 넣지 않는다.

### 실행과 검증

- **범위 검사를 세 모드 전부에 적용한다.** 흡수·N그룹도 범위 전체를 replay해 선택하지 않은 커밋의 OID가 바뀐다. 실행 전 ① 조상 확인 ② `set(git rev-list <task_base>..<original_head>)`와 선택 OID 집합의 set equality ③ `HEAD == original_head` ④ rewrite closure 전체를 사용자에게 제시. first-parent suffix 검사는 쓰지 않는다.
- **세 모드 공통 옵션** — `-c rerere.enabled=false -c submodule.recurse=false -c notes.rewrite.rebase=false --no-update-refs --no-autostash --empty=stop --no-gpg-sign`.
- 흡수는 위 옵션 + `--autosquash <task_base>`. `-i`는 불필요하고 `GIT_EDITOR=true`는 `squash!` 때문에 유지한다.
- 1개 그룹은 `git reset --soft <task_base>` → `git commit -F <file>`. `--author`로 원본 author를 보존하되 author date는 `--date`가 따로 필요하다. author가 섞이면 정책을 확인받는다.
- N개 그룹은 `GIT_SEQUENCE_EDITOR` todo 주입 + `-c rebase.missingCommitsCheck=error`. 이 설정은 삭제된 줄만 검사하므로 todo의 OID 순서·action·그룹 경계를 실행 전에 따로 검증한다.
- `--reapply-cherry-picks`는 조상 base 토폴로지에서 무의미하므로 넣지 않는다.
- 백업은 `backup/squash/<sanitized-branch>-<YYYYMMDDTHHMMSSZ>-<short OID>`. 브랜치명은 ref 무효 문자를 `-`로 치환하고 60자로 절단해 단일 세그먼트로 만든다. `git check-ref-format --branch` 검증, `update-ref` create-only 생성, 생성 후 `original_head`를 가리키는지 확인, 충돌 시 `-2`~`-9` 재시도 후 포기·중단.
- 검증은 `git diff --quiet --exit-code --no-ext-diff <backup> HEAD`의 exit code와 두 tree OID **문자열 비교**로 판정한다.
- 커밋 메시지는 안전한 임시 경로에 쓰고 `-F`로 전달한다(`-m` 금지). POSIX `trap` / PowerShell `finally`로 정리한다.

### 복구 상태 머신

분기 기준은 active rebase 여부, 현재 HEAD, branch attach 여부, index/worktree 상태다.

| 도달 상태 | 복구 |
|---|---|
| rebase 충돌 진행 중 | `git rebase --abort` |
| `pre-rebase` 실패로 rebase 미시작 | 상태 변화 없음 — 보고만 |
| `reset --soft` 후 commit이 훅 실패로 죽음 | **`git reset --soft <backup>`** — index/worktree 보존 |
| rebase 성공 후 트리 검증만 실패 | 워킹트리가 완전히 깨끗할 때만 `git reset --hard <backup>` |
| 예상 밖 dirty·unmerged index | **파괴적 복구 금지** — 백업 ref와 수동 복구 정보를 남기고 종료 |
| ignored·untracked 존재 | `reset --hard`가 삭제할 수 있으므로 위 비파괴 종료로 보낸다 |

`post-commit`·`post-rewrite`·`reference-transaction`의 외부 부작용은 브랜치 복구로 되돌릴 수 없음을 보고에 명시한다.

### 훅 오분류 수정

억제는 **관계 패턴**으로 좁힌다 — 대상 커밋 지시(`이전/그/아까/특정 커밋에`)와 흡수 동사(`넣어`·`흡수`·`합쳐`·`fixup`·`amend`·`squash`)가 **양방향 24자 이내**에서 성립할 때만. 두 어순과 한국어·영어 경계를 같은 정규식 문법으로 `.py`·`.ps1`에 넣는다. **신규 리마인더는 추가하지 않는다.**

| 프롬프트 | 기대 |
|---|---|
| 이번 변경만 이전 커밋에 fixup으로 넣어줘 | 침묵(억제) |
| 이 변경만 이전 커밋에 흡수해줘 | 침묵(억제) |
| fixup 관련 문서 변경만 커밋해줘 | `safe-checkpoint` 유지 |
| rebase 가이드 파일만 커밋해줘 | `safe-checkpoint` 유지 |
| squash 테스트 변경만 커밋해줘 | `safe-checkpoint` 유지 |
| 해당 변경만 커밋해줘 | `safe-checkpoint` 유지 |

## 구현 계획

1. **계약 테스트 선행** — `tests/test_skill_contracts.py` 5곳(파일 구성 dict, `default_prompt` 튜플, 대칭 등록 튜플, PowerShell 목록, 신규 `test_squash_work_commits_enforces_verified_invariants`). 검증: 새 테스트가 스킬 부재로 실패하는지 확인.
2. **전제 회귀 테스트 선행** — `tests/test_squash_premises.py`. `shutil.which("git")` 없으면 skip, `GIT_CONFIG_GLOBAL`/`GIT_CONFIG_SYSTEM`을 `os.devnull`로 차단, git 2.52 hard gate. 위 실측 기준 표의 모든 행을 케이스로 고정한다. 검증: 단독 실행 통과.
3. **스킬 작성** — `skills/squash-work-commits/SKILL.md`(영문 본문, description에 한글 트리거·배제), `agents/openai.yaml`(`short_description` 39자, `$squash-work-commits` 포함), `references/squash-recipes.md`(POSIX + PowerShell 명령 전문). reference 링크는 코드펜스 밖 산문에 둔다. 검증: 1·2의 테스트 통과.
4. **카탈로그 등록** — `components.json`에 `kind: skill`, `source: "skills/squash-work-commits"`, 네 support 셀 모두 `true`. 설치기는 수정하지 않는다. 검증: `test_installer_contracts.py` 통과.
5. **훅 수정** — `hooks/workflow-reminder.py`와 `.ps1`에 관계 패턴 억제 추가, `tests/test_workflow_reminder.py`에 위 6개 fixture와 parity 항목 추가. 검증: 기존 29건 + 신규 통과.
6. **경계 문서화** — `plan-and-build/SKILL.md` §5에 위임 한 문장, `safe-checkpoint/SKILL.md` description과 §5에 라우팅 경계. 기존 검사 문구는 건드리지 않는다.
7. **문서 갱신** — README/INSTALL 스킬 표, 트리거 예시, 커밋 스킬 2개 경계, v1 미지원 목록, INSTALL §7 검증 항목.
8. **전체 검증** — 아래 수용 기준.

`plan-and-build`에는 위임 한 문장만 넣는다. fixup 자동 사용 지시는 `safe-checkpoint`의 staging 권한 계약을 우회하고, "merge 대신 rebase"는 그 자체가 rewrite라 자기모순이며, 완료마다 압축을 권하는 문구는 단발 수정에 과잉 발동한다.

## TDD 결정

TDD를 적용한다. 이 작업의 실패 모드가 전부 "git 동작에 대한 잘못된 전제"였고 실제로 초안에서 여섯 건이 틀렸다. 계약 테스트와 전제 회귀 테스트는 부작용 없이 표현 가능하며 failing-first가 회귀를 막는다. 스킬 Markdown보다 테스트를 먼저 쓴다.

정책 로직을 실행 가능한 helper로 배포하는 방안은 택하지 않는다. 테스트가 정책을 재구현하면 레시피가 틀려도 통과하므로, 테스트는 **레시피가 의존하는 git 사실**만 고정하고 정책은 다른 스킬과 마찬가지로 산문이 담당한다.

## 병렬화 결정

순차 진행한다. 스킬 본문, 카탈로그, 계약 테스트, 훅, 문서가 같은 스킬 이름과 안내 문구를 공유해 파일 소유권이 겹치고, 통합 불일치 위험이 병렬 이득보다 크다.

## 설계 승인 결정

추가 승인 체크포인트는 필요하지 않다. 사용자가 v1 범위(선형 한정), 테스트 구조(전제 회귀 전용), `openai.yaml` 보유, 훅 수정 여부, `plan-and-build` 축소를 각각 명시적으로 결정했고 미해결 아키텍처 선택지가 없다.

## 수용 기준

- `skills/squash-work-commits/`가 `SKILL.md`, `agents/openai.yaml`, `references/squash-recipes.md` 정확히 세 파일로 존재하고 `quick_validate.py`를 통과한다.
- `default_prompt`가 `$squash-work-commits`를 직접 포함하고 `short_description`이 25–64자다.
- 신규 불변식 계약 테스트가 `--quiet --exit-code`, `merge-base --is-ancestor`, set equality, `--no-update-refs`, `--no-autostash`, `--no-gpg-sign`, `--empty=stop`, `--git-path`, `--untracked-files=all`, `refs/heads/`, `check-ref-format`, `reset --soft <backup>`, v1 중단 조건을 고정한다.
- `tests/test_squash_premises.py`가 실측 기준 표의 각 행을 실제 git으로 재현한다.
- 훅 fixture 6종이 Python에서 통과하고 parity 항목에 등록된다.
- `components.json`에 대칭 등록되고 `install.sh`/`install.ps1`/`uninstall.*`는 변경되지 않는다.
- `python3 -m unittest discover -s tests -t .` 전체 통과.
- 네이티브 Windows에서 `git.exe`로 `tests.test_squash_premises`와 PowerShell parity 1건을 실행해야 `windows: true` 등록 근거가 성립한다.
- 세션 라우팅 확인: "이번 작업 내역 하나로 합쳐줘" → 이 스킬 / "이 변경만 커밋해줘" → `safe-checkpoint` / "fixup 관련 문서 변경만 커밋해줘" → `safe-checkpoint` 유지.
- 이번 작업은 commit/push하지 않는다.
