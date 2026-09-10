# 워크플로우 규칙 충돌 수정

목표: 검토에서 확인한 설치 권한, 하위 리뷰어의 질문, 브라우저 검토 완료, URL 선택, 자율 설계 위임, WIP 인수인계 규칙과 혼합 요청의 훅 알림을 일관되게 만든다.

현재 상태: `main`, HEAD `89362f7f37c980c43331e42508ee52fdf4415a69`. 기존 미추적 `2026-07-28-squash-work-commits-skill.md`는 보존한다. 사용자가 검토 결과의 수정을 승인했고 프로젝트 지침이 Herdr 병렬 실행을 허용한다. 추가 설계 승인은 필요하지 않다.

## 구현과 소유권

- 보조 에이전트: `skills/code-quality-review/**`, `skills/branch-merge-review/**`. 검토만으로 설치하지 않으며 기존 설치 승인은 재사용한다. 위임된 PHP 리뷰어는 실행 환경 부족을 반환하고 질문은 주 에이전트에게 맡긴다. 완료 판정은 실제 변경에 요구되는 참조를 기준으로 한다.
- 주 에이전트: `skills/plan-and-build/SKILL.md`, `skills/safe-checkpoint/SKILL.md`, `skills/web-browser-preview/SKILL.md`, 양쪽 `hooks/workflow-reminder.*`, `tests/test_workflow_reminder.py`, `tests/test_php_baseline.py`, README/INSTALL 및 이 계획. 위임된 설계 결정은 재승인하지 않고, WIP 커밋만 승인됐다면 실패와 재개 지점을 대화로 남긴다. URL은 제공된 값과 확인 가능한 실행 환경을 우선한다.
- 훅은 권한을 결정하지 않는다. 읽기 전용 검토와 명시적인 구현 요청이 함께 있으면 두 안내를 제공해 에이전트가 범위를 구분하도록 한다. 순수 읽기 전용 요청은 구현 알림을 계속 억제한다. 자연어 전체를 파싱하는 새 계층은 만들지 않는다.

## 검증과 완료 조건

- 한·영 혼합 요청, 순수 읽기 전용 및 작은 수정 사례를 기존 훅 테스트에 묶어 추가한다. Python/PowerShell의 알림 결과가 일치해야 한다.
- 문구를 고정하는 새 테스트는 만들지 않는다. 기존 스킬 계약·PHP 참조 검사와 변경된 스킬의 유효성 검사를 실행한다.
- 도구 설치 승인 유무, 위임된 PHP 환경 부족, 브라우저 자산만의 완료 판정, 알려진 URL, 자율 설계 위임, 문서 없는 WIP 커밋 시나리오를 최종 문구와 대조한다.
- 전체 diff를 통합 시 확인하며 저장소 밖 설치, staging, commit, push는 수행하지 않는다. 실행하지 못한 검증은 완료 근거와 구분한다.

## 완료 결과

- 여섯 규칙과 혼합 요청의 훅 알림을 수정했다. 설치 권한과 브라우저 전용 참조 예외는 실행 단계뿐 아니라 언어 참조·리뷰어 프롬프트·보고서 템플릿에도 반영했다.
- PHP 선택 예제는 호환 버전을 자동 탐색하고 실제 버전을 확인한 뒤 실행한다. 호환 버전이 없으면 후속 명령 전에 실패한다. 이를 확인하는 실행 검사 1개에 시스템/대체 PHP 조합 5건을 묶었다.
- 이전 정책을 요구하던 기존 검사 2개를 갱신했다. 자동 설치 강제는 제거하되 미실행 상태 기록 검사는 유지했고, 보안 참조는 브라우저 전용 및 백엔드별 선택표를 검사한다.
- Python 3.12.3: `python3 -B -m unittest discover -s tests -p test_workflow_reminder.py` — 31개 검사, OK, PowerShell PATH 탐지로 1건 생략. 혼합 요청 4건의 실패를 먼저 재현했다.
- 실제 Windows PowerShell 5.1.26100.9168과 Python 훅을 입력 8건으로 비교해 모두 일치함을 확인했다. PowerShell 파일의 UTF-8 BOM도 유지됐다.
- `python3 -B -m unittest discover -s tests -p test_skill_contracts.py` — 64개 검사, OK.
- `npm_config_offline=true python3 -B -m unittest discover -s tests -p test_php_baseline.py` — 244개 검사, OK, tsc 부재로 1건 생략. Windows 임시 폴더를 사용하는 기존 검사는 해당 접근을 허용한 실행에서 통과했다.
- 변경된 스킬 5개의 `quick_validate.py`와 `git diff --check` 통과. 보조 에이전트가 자율 설계·WIP·알려진 URL·설치 승인 유무의 요청 5건을 현재 규칙에 대조했다.
- 두 에이전트는 분리된 파일 범위에서 작업했고, 주 에이전트가 diff와 검증을 통합했다. 실제 도구 설치·staging·commit·push는 수행하지 않았다. 기존 미추적 계획은 그대로 보존했다.
