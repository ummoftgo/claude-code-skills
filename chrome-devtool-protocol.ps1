# =====================================================================
# 1. 환경 및 출력 인코딩 선언 (Data Integrity)
# =====================================================================
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# =====================================================================
# 2. 관리자 권한 자가 승격 (Privilege Escalation)
# =====================================================================
$currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "[!] 관리자 권한이 필요합니다. 승격을 요청합니다..." -ForegroundColor Yellow
    # Bypass 대신 정식 실행 정책을 따르도록 인자 수정
    Start-Process powershell -ArgumentList "-File `"$PSCommandPath`"" -Verb RunAs
    exit
}

# =====================================================================
# 3. 구성 및 변수 최적화 (Configuration)
# =====================================================================
$DebugPort = 9333
$RuleName = "Secure_Chrome_Debug_WSL_Only"
$UserDataDir = "C:\dev\chrome-mcp-secure"

# 데이터 보존 디렉토리 자동 생성
if (-not (Test-Path $UserDataDir)) {
    New-Item -Path $UserDataDir -ItemType Directory -Force | Out-Null
}

# =====================================================================
# 4. 크롬 경로 동적 탐색 (Dynamic Path Discovery)
# =====================================================================
Write-Host "[🔍] 시스템 내 크롬 실행 파일의 논리적 위치를 추적 중..." -ForegroundColor Cyan
$ChromePath = ""
$RegPath = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"

if (Test-Path $RegPath) { $ChromePath = (Get-ItemProperty $RegPath).'(Default)' }
if (-not (Test-Path $ChromePath)) {
    $CommonPaths = @(
        "C:\Program Files\Google\Chrome\Application\chrome.exe",
        "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        "$env:LocalAppData\Google\Chrome\Application\chrome.exe"
    )
    foreach ($Path in $CommonPaths) { if (Test-Path $Path) { $ChromePath = $Path; break } }
}

if (-not (Test-Path $ChromePath)) {
    Write-Error "[오류] 유효한 크롬 설치 경로를 감지하지 못했습니다."
    Pause; exit
}

# =====================================================================
# 5. 포트 $DebugPort portproxy 선택 정리 (Selective Proxy Cleanup)
# =====================================================================
Write-Host "[🧹] 포트 $DebugPort 에 대한 기존 portproxy를 정리합니다." -ForegroundColor Cyan
netsh interface portproxy delete v4tov4 listenport=$DebugPort listenaddress=0.0.0.0 2>$null
netsh interface portproxy delete v4tov4 listenport=$DebugPort listenaddress=127.0.0.1 2>$null
netsh interface portproxy delete v4tov6 listenport=$DebugPort listenaddress=0.0.0.0 2>$null
netsh interface portproxy delete v4tov6 listenport=$DebugPort listenaddress=127.0.0.1 2>$null
Write-Host "[완료] 포트 $DebugPort portproxy 정리됨" -ForegroundColor Green

# =====================================================================
# 6. 네트워크 인프라 구성 (Firewall & Port Proxy)
# =====================================================================
Write-Host "[🛡️] 네트워크 인터페이스 및 보안 성벽을 재구성합니다." -ForegroundColor Cyan

# WSL 가상 어댑터 식별 (IP + 실제 서브넷 마스크 동적 감지)
$WSL_Interface = Get-NetIPAddress | Where-Object { $_.InterfaceAlias -like "*WSL*" -and $_.AddressFamily -eq 'IPv4' }
if (-not $WSL_Interface) {
    Write-Error "[오류] 활성화된 WSL 인스턴스를 찾을 수 없습니다."
    Pause; exit
}
$HostIP = $WSL_Interface.IPAddress
$PrefixLength = $WSL_Interface.PrefixLength  # /20, /24 등 실제 값 사용
$WSL_Subnet = "$HostIP/$PrefixLength"

Write-Host "[감지] WSL 어댑터: $HostIP/$PrefixLength" -ForegroundColor Cyan

# 이전 listenaddress로 등록된 portproxy도 정리
netsh interface portproxy delete v4tov4 listenport=$DebugPort listenaddress=$HostIP 2>$null

# 방화벽 규칙 갱신: WSL 실제 서브넷 대역만 수용
if (Get-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue) {
    Remove-NetFirewallRule -DisplayName $RuleName
}
New-NetFirewallRule -DisplayName $RuleName -Direction Inbound -LocalPort $DebugPort -Protocol TCP -Action Allow -RemoteAddress $WSL_Subnet -Profile Any

# portproxy: WSL(HostIP:9333) → 127.0.0.1:9333 (Chrome 루프백)
netsh interface portproxy add v4tov4 listenport=$DebugPort listenaddress=$HostIP connectport=$DebugPort connectaddress=127.0.0.1

# =====================================================================
# 7. 기존 디버깅 크롬 프로세스 정리 (Process Cleanup)
# =====================================================================
$existingProcs = Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" |
    Where-Object { $_.CommandLine -like "*$UserDataDir*" }
if ($existingProcs) {
    Write-Host "[정리] 기존 디버깅 크롬 프로세스를 종료합니다." -ForegroundColor Yellow
    $existingProcs | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
    Start-Sleep -Seconds 1
}

# =====================================================================
# 8. 엔진 가동 및 검증 (Execution & Validation)
# =====================================================================
Write-Host "[🚀] 크롬 디버깅 인터페이스를 기동합니다." -ForegroundColor Green
Start-Process $ChromePath -ArgumentList "--remote-debugging-port=$DebugPort --user-data-dir=$UserDataDir --no-first-run"

# Chrome 리스닝 검증
Start-Sleep -Seconds 2
$portCheck = Test-NetConnection -ComputerName 127.0.0.1 -Port $DebugPort -WarningAction SilentlyContinue
if ($portCheck.TcpTestSucceeded) {
    Write-Host "[확인] Chrome 127.0.0.1:$DebugPort 리스닝 중" -ForegroundColor Green
} else {
    Write-Host "[경고] 포트 $DebugPort 가 아직 열리지 않았습니다. 크롬 기동 상태를 확인하세요." -ForegroundColor Red
}

# portproxy 경유 검증
$proxyCheck = Test-NetConnection -ComputerName $HostIP -Port $DebugPort -WarningAction SilentlyContinue
if ($proxyCheck.TcpTestSucceeded) {
    Write-Host "[확인] portproxy $HostIP`:$DebugPort → 127.0.0.1:$DebugPort 정상" -ForegroundColor Green
} else {
    Write-Host "[경고] portproxy 경유 접근 실패. 방화벽 또는 프록시 설정을 확인하세요." -ForegroundColor Red
}

# =====================================================================
# 9. 최종 리포트 (Report)
# =====================================================================
Write-Host ("`n" + ("="*60)) -ForegroundColor Gray
Write-Host "[최종 분석 결과 보고]" -ForegroundColor Yellow
Write-Host "1. Chrome 바인딩   : 127.0.0.1:$DebugPort"
Write-Host "2. WSL 엔드포인트  : $HostIP`:$DebugPort (portproxy 중계)"
Write-Host "3. WSL 서브넷      : $WSL_Subnet"
Write-Host "4. 데이터 저장소   : $UserDataDir"
Write-Host "5. 보안 등급       : 격리됨 (WSL Subnet Only)"
Write-Host "`n[WSL 내부 연결 확인 명령어]" -ForegroundColor Yellow
Write-Host "   curl -I http://$HostIP`:$DebugPort/json/version" -ForegroundColor White
Write-Host ("="*60) -ForegroundColor Gray

# Read-Host -Prompt "Press Enter to exit..."
