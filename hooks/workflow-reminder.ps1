$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::InputEncoding = $utf8
[Console]::OutputEncoding = $utf8

$options = [Text.RegularExpressions.RegexOptions]::IgnoreCase -bor [Text.RegularExpressions.RegexOptions]::Singleline

function New-WorkflowRegex {
    param([string]$Pattern)
    return (New-Object -TypeName Text.RegularExpressions.Regex -ArgumentList @($Pattern, $options))
}

$action = New-WorkflowRegex (
    '구현|개발|만들|작성|추가|생성|구축|도입|' +
    '\b(?:implement|build|create|develop|add|scaffold|introduce|set\s*up)\b|' +
    '\bwrite\b.{0,30}\bcode\b'
)

$substantial = New-WorkflowRegex (
    '새(?:로운)?\s*.{0,30}(?:프로젝트|기능|서비스|앱|애플리케이션|api|페이지|컴포넌트|모듈)|' +
    '(?:프로젝트|서비스|앱|애플리케이션).{0,20}(?:새로|처음부터).{0,20}(?:구현|개발|만들|작성|생성|구축)|' +
    '(?:프로젝트|기능|서비스|api|페이지|컴포넌트|모듈).{0,30}(?:구현|개발|만들|추가|생성|구축)|' +
    '(?:TDD|테스트\s*우선).{0,30}프로젝트.{0,50}(?:기능|코드).{0,30}(?:구현|개발|작성|추가|생성)|' +
    '(?:여러|다수|복수|동시에|병렬|나눠서|각각|독립적인?).{0,50}(?:구현|개발|작성|작업|기능|페이지|컴포넌트)|' +
    '\bnew\s+(?:project|feature|service|app|application|api|page|component|module)\b|' +
    '\b(?:from\s+scratch|multiple|in\s+parallel)\b|' +
    '\b(?:implement|build|create|add)\b.{0,40}\b(?:feature|auth|authentication|api|page|component|module|service|project)\b|' +
    '(?:backend|back-end).{0,50}(?:frontend|front-end)|(?:frontend|front-end).{0,50}(?:backend|back-end)'
)

$smallEdit = New-WorkflowRegex (
    '(?:작은|간단한?|사소한?|한\s*줄|한\s*글자|오타|문구만|색상만)|' +
    '\b(?:tiny|small|trivial|one[- ]line|typo|copy[- ]only)\b'
)

$reviewIntent = New-WorkflowRegex (
    '(?:설명|검토|리뷰|감사|분석|조사|점검|확인|검증|대조|반례|검색|찾아|요약|번역|상태)|' +
    '\b(?:explain|review|audit|analy[sz]e|inspect|investigate|verify|validate|' +
    'check|research|search|summari[sz]e|translate|status)\b'
)

$explicitMutation = New-WorkflowRegex (
    '(?:구현|개발|추가|생성|구축|도입|수정)' +
    '(?:해|해줘|해주세요|하자|해라|하고|한\s*(?:뒤|다음)|해서)|' +
    '코드.{0,20}작성(?:해|해줘|해주세요|하자|해라)|' +
    '만들(?:어|어줘|어주세요|고)|고쳐(?:줘|주세요)?|' +
    '(?:^|[,.!?;:]\s*|\b(?:please|and|then|also|now)\s+|' +
    '\b(?:can|could|would|will)\s+you\s+|' +
    '\b(?:need|want)\s+(?:you\s+)?to\s+)' +
    '(?:implement|build|create|develop|add|scaffold|introduce|fix|change|update)\b'
)

$noChanges = New-WorkflowRegex (
    '읽기\s*전용|무수정|(?:수정|변경)\s*없이|' +
    '(?:파일|코드|내용|작업물)?\s*(?:을|를|은|는)?\s*' +
    '(?:수정|변경|편집)(?:은|는|을|를)?\s*(?:하지\s*말|하지\s*마|금지)|' +
    '(?:파일|코드)\s*(?:생성|작성|수정|변경)\s*금지|' +
    '건드리지\s*마|' +
    '\bread[- ]only\b|\bno\s+changes?\b|' +
    '\bwithout\s+(?:making\s+)?(?:any\s+)?changes?\b|' +
    '\bwithout\s+(?:changing|modifying|editing)\s+(?:any\s+)?(?:code|files?)\b|' +
    '\bdo\s+not\s+(?:modify|edit|change|write)\b|' +
    '\bdo\s+not\s+make\s+(?:any\s+)?changes?\b|' +
    "\bdon['’]t\s+(?:modify|edit|change|write)\b|" +
    "\bdon['’]t\s+make\s+(?:any\s+)?changes?\b|" +
    '\bno\s+(?:file|code)\s+(?:modifications?|edits?|writes?)\b'
)

$evidenceReviewIntent = New-WorkflowRegex (
    '(?:검토|리뷰|감사|분석|조사|점검|확인|검증|대조|반례)|' +
    '\b(?:review|audit|analy[sz]e|inspect|investigate|verify|validate|check)\b'
)

$checkpointOrHandoffAction = New-WorkflowRegex (
    '(?:체크\s*포인트|인수\s*인계).{0,30}' +
    '(?:남기|만들|작성|생성|갱신|업데이트|준비|정리|저장)|' +
    '(?:체크\s*포인트|인수\s*인계)\s*(?:해\s*줘|해주세요|하자|해라)|' +
    '(?:남기|만들|작성|생성|갱신|업데이트|준비|정리|저장).{0,30}' +
    '(?:체크\s*포인트|인수\s*인계)|' +
    '\b(?:create|make|leave|write|update|prepare|record|save|finish)\b' +
    '.{0,50}\b(?:checkpoint|hand[- ]?off|handover)\b|' +
    '\b(?:checkpoint|hand[- ]?off|handover)\b.{0,40}' +
    '\b(?:this|the|my|our)\s+(?:work|changes?|task|project)\b|' +
    '\bWIP\b.{0,20}\b(?:commit|checkpoint)\b|' +
    '(?:WIP|작업\s*중).{0,20}(?:커밋|체크\s*포인트)'
)

$resumeIntent = New-WorkflowRegex (
    '(?:집|다른\s*곳|내일).{0,30}(?:이어|재개)|' +
    '(?:이어|재개).{0,30}(?:집|다른\s*곳|내일)|' +
    '재개\s*(?:지점|명령|방법|할\s*수)|' +
    '\b(?:resume|continue|pick\s+up)\b.{0,40}\b(?:this|the)\s+(?:work|task|project)\b|' +
    '\b(?:tomorrow|later|elsewhere|from\s+home)\b.{0,40}' +
    '\b(?:resume|continue|pick\s+up)\b'
)

$leavingWorkIntent = New-WorkflowRegex (
    '퇴근\s*(?:전|하기\s*전).{0,30}(?:마무리|정리|체크\s*포인트|인수\s*인계|커밋|푸시)|' +
    '(?:마무리|정리|체크\s*포인트|인수\s*인계).{0,30}퇴근'
)

$selectiveGitIntent = New-WorkflowRegex (
    '(?:이|해당|이번|현재|관련|요청한|지정한|선택한).{0,50}' +
    '(?:변경(?:사항)?|파일|내용).{0,12}만.{0,30}(?:커밋|푸시)|' +
    '(?:^|\s)\S+\s*만\s*(?:커밋|푸시)|' +
    '(?:커밋|푸시).{0,30}(?:해당|이번|현재|관련|요청한|지정한|선택한).{0,30}' +
    '(?:변경(?:사항)?|파일|내용).{0,12}만|' +
    '\b(?:commit|push)\s+(?:only\s+)?' +
    '(?:these|those|the|specified|selected|current)\s+(?:changes?|files?)' +
    '(?:\s+only)?\b|' +
    '\b(?:commit|push)\s+only\s+[\w./-]+|' +
    '\b(?:commit|push)\s+[\w./-]+\s+only\b|' +
    '\bonly\s+(?:commit|push)\b.{0,40}\b(?:changes?|files?)\b|' +
    '\b(?:commit|push)\b.{0,30}\b(?:only|specified|selected)\b.{0,30}' +
    '\b(?:changes?|files?)\b'
)

$planReminder = 'This appears to be substantial implementation work. Invoke the plan-and-build ' +
    'skill before editing implementation code. Inspect the repository first, write one ' +
    'lightweight specification and plan, get design approval when architecture or contracts ' +
    'materially change, decide whether TDD applies, and split only truly independent work ' +
    'with stable contracts. Get explicit user approval before dispatching parallel workers. ' +
    'If inspection proves the change is small and localized, exit the workflow and proceed ' +
    'directly.'

$evidenceReviewReminder = 'This request explicitly requires a non-mutating review. Invoke the ' +
    'evidence-first-review skill before reviewing. Lock the user-supplied context and scope ' +
    'first, then independently verify claims against current files, relevant diffs, raw data, ' +
    'and runtime evidence. Respect the read-only boundary: do not modify or create files, ' +
    'install tools, create checkouts or worktrees, stage changes, or save a report. Return ' +
    'the evidence-backed result in the user''s language as a message only.'

$safeCheckpointReminder = 'This request appears to need a scoped checkpoint or resumable handoff. Invoke the ' +
    'safe-checkpoint skill before any Git or handoff write. Inspect branch, upstream, status, ' +
    'diffs, runtime manifests, and existing handoff sources; separate intended changes from ' +
    'unrelated dirty work and generated files. Require matching authorization for handoff ' +
    'writes, staging and commit, remote push, and failed WIP commits. After any authorized ' +
    'push, re-read HEAD, upstream synchronization, and remaining dirty state.'

try {
    $raw = [Console]::In.ReadToEnd()
    $payload = $raw | ConvertFrom-Json -ErrorAction Stop
    if ($null -eq $payload -or $payload -isnot [pscustomobject]) { exit 0 }

    $prompt = ''
    if ($payload.PSObject.Properties.Name -contains 'user_prompt') { $prompt = $payload.user_prompt }
    elseif ($payload.PSObject.Properties.Name -contains 'prompt') { $prompt = $payload.prompt }
    if ($prompt -isnot [string]) { exit 0 }

    $text = (($prompt -split '\s+') -join ' ').Trim()
    if ([string]::IsNullOrEmpty($text)) { exit 0 }

    $reminders = @()

    $shouldPlan = $false
    if (-not $noChanges.IsMatch($text) -and $action.IsMatch($text)) {
        $isSubstantial = $substantial.IsMatch($text)
        $isSmallOnly = $smallEdit.IsMatch($text) -and -not $isSubstantial
        $isReviewOnly = $reviewIntent.IsMatch($text) -and -not $explicitMutation.IsMatch($text)
        $shouldPlan = -not $isSmallOnly -and -not $isReviewOnly -and (
            $isSubstantial -or $text.Length -ge 180
        )
    }
    if ($shouldPlan) {
        $reminders += $planReminder
    }

    if ($noChanges.IsMatch($text) -and $evidenceReviewIntent.IsMatch($text)) {
        $reminders += $evidenceReviewReminder
    }

    if (
        $checkpointOrHandoffAction.IsMatch($text) -or
        $resumeIntent.IsMatch($text) -or
        $leavingWorkIntent.IsMatch($text) -or
        $selectiveGitIntent.IsMatch($text)
    ) {
        $reminders += $safeCheckpointReminder
    }

    if ($reminders.Count -eq 0) { exit 0 }

    $output = [ordered]@{
        hookSpecificOutput = [ordered]@{
            hookEventName = 'UserPromptSubmit'
            additionalContext = [string]::Join("`n`n", $reminders)
        }
    }
    [Console]::Out.WriteLine(($output | ConvertTo-Json -Depth 5 -Compress))
} catch {
    # Reminder failures must never block a submitted prompt.
    exit 0
}

exit 0
