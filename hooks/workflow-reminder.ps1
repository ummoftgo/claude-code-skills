$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::InputEncoding = $utf8
[Console]::OutputEncoding = $utf8

$options = [Text.RegularExpressions.RegexOptions]::IgnoreCase -bor [Text.RegularExpressions.RegexOptions]::Singleline
$actionPattern = '구현|개발|만들|작성|추가|생성|구축|도입|\b(?:implement|build|create|develop|add|scaffold|introduce|set\s*up)\b|\bwrite\b.{0,30}\bcode\b'
$action = New-Object -TypeName Text.RegularExpressions.Regex -ArgumentList @($actionPattern, $options)
$substantialPattern = '새(?:로운)?\s*.{0,30}(?:프로젝트|기능|서비스|앱|애플리케이션|api|페이지|컴포넌트|모듈)|' +
    '(?:프로젝트|서비스|앱|애플리케이션).{0,20}(?:새로|처음부터).{0,20}(?:구현|개발|만들|작성|생성|구축)|' +
    '(?:프로젝트|기능|서비스|api|페이지|컴포넌트|모듈).{0,30}(?:구현|개발|만들|추가|생성|구축)|' +
    '(?:TDD|테스트\s*우선).{0,30}프로젝트.{0,50}(?:기능|코드).{0,30}(?:구현|개발|작성|추가|생성)|' +
    '(?:여러|다수|복수|동시에|병렬|나눠서|각각|독립적인?).{0,50}(?:구현|개발|작성|작업|기능|페이지|컴포넌트)|' +
    '\bnew\s+(?:project|feature|service|app|application|api|page|component|module)\b|' +
    '\b(?:from\s+scratch|multiple|in\s+parallel)\b|' +
    '\b(?:implement|build|create|add)\b.{0,40}\b(?:feature|auth|authentication|api|page|component|module|service|project)\b|' +
    '(?:backend|back-end).{0,50}(?:frontend|front-end)|(?:frontend|front-end).{0,50}(?:backend|back-end)'
$substantial = New-Object -TypeName Text.RegularExpressions.Regex -ArgumentList @($substantialPattern, $options)
$smallEditPattern = '(?:작은|간단한?|사소한?|한\s*줄|한\s*글자|오타|문구만|색상만)|\b(?:tiny|small|trivial|one[- ]line|typo|copy[- ]only)\b'
$smallEdit = New-Object -TypeName Text.RegularExpressions.Regex -ArgumentList @($smallEditPattern, [Text.RegularExpressions.RegexOptions]::IgnoreCase)
$readOnlyPattern = '(?:설명|검토|리뷰|분석|조사|검색|찾아|요약|번역|상태)|\b(?:explain|review|audit|analy[sz]e|inspect|research|search|summari[sz]e|translate|status)\b'
$readOnly = New-Object -TypeName Text.RegularExpressions.Regex -ArgumentList @($readOnlyPattern, [Text.RegularExpressions.RegexOptions]::IgnoreCase)
$explicitMutationPattern = '(?:구현|개발|추가|생성|구축|도입|수정)(?:해|해줘|해주세요|하자|해라)|' +
    '코드.{0,20}작성(?:해|해줘|해주세요|하자|해라)|만들(?:어|어줘|어주세요)|고쳐(?:줘|주세요)?|' +
    '(?:^|[,.!?;:]\s*|\b(?:please|and|then|also|now)\s+|\b(?:can|could|would|will)\s+you\s+|' +
    '\b(?:need|want)\s+(?:you\s+)?to\s+)(?:implement|build|create|develop|add|scaffold|introduce|fix|change|update)\b'
$explicitMutation = New-Object -TypeName Text.RegularExpressions.Regex -ArgumentList @($explicitMutationPattern, [Text.RegularExpressions.RegexOptions]::IgnoreCase)

$reminder = 'This appears to be substantial implementation work. Invoke the plan-and-build ' +
    'skill before editing implementation code. Inspect the repository first, write one ' +
    'lightweight specification and plan, get design approval when architecture or contracts ' +
    'materially change, decide whether TDD applies, and split only truly independent work ' +
    'with stable contracts. Get explicit user approval before dispatching parallel workers. ' +
    'If inspection proves the change is small and localized, exit the workflow and proceed directly.'

try {
    $raw = [Console]::In.ReadToEnd()
    $payload = $raw | ConvertFrom-Json -ErrorAction Stop
    if ($null -eq $payload -or $payload -isnot [pscustomobject]) { exit 0 }

    $prompt = ''
    if ($payload.PSObject.Properties.Name -contains 'user_prompt') { $prompt = $payload.user_prompt }
    elseif ($payload.PSObject.Properties.Name -contains 'prompt') { $prompt = $payload.prompt }
    if ($prompt -isnot [string]) { exit 0 }

    $text = (($prompt -split '\s+') -join ' ').Trim()
    if ([string]::IsNullOrEmpty($text) -or -not $action.IsMatch($text)) { exit 0 }
    $isSubstantial = $substantial.IsMatch($text)
    if ($smallEdit.IsMatch($text) -and -not $isSubstantial) { exit 0 }
    if ($readOnly.IsMatch($text) -and -not $explicitMutation.IsMatch($text)) { exit 0 }
    if (-not $isSubstantial -and $text.Length -lt 180) { exit 0 }

    $output = [ordered]@{
        hookSpecificOutput = [ordered]@{
            hookEventName = 'UserPromptSubmit'
            additionalContext = $reminder
        }
    }
    [Console]::Out.WriteLine(($output | ConvertTo-Json -Depth 5 -Compress))
} catch {
    # Reminder failures must never block a submitted prompt.
    exit 0
}

exit 0
