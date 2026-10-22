# Mezbon chek-printer agentini Windows Vazifa Rejalashtiruvchiga o'rnatadi.
#   - Orqa fonda, OYNASIZ ishlaydi (pythonw.exe)
#   - Kompyuter yonishi bilan (boot) o'zi ishga tushadi — login shart emas
#   - Agent ishlamay qolsa Windows o'zi qayta tiklaydi (auto-restart)
#   - Faqat stop_agent.bat orqali to'xtaydi
# Bu skript install_agent.bat tomonidan administrator huquqi bilan chaqiriladi.
$ErrorActionPreference = 'Stop'

$TaskName  = 'MezbonPrinterAgent'
$ScriptDir = $PSScriptRoot
$AgentPy   = Join-Path $ScriptDir 'xprinter_agent.py'

if (-not (Test-Path $AgentPy)) {
    Write-Host "[XATO] Topilmadi: $AgentPy" -ForegroundColor Red
    exit 1
}

# ── pythonw.exe ni topish (oynasiz Python) ────────────────────────────────
function Find-Pythonw {
    $c = Get-Command pythonw.exe -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    $py = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($py) {
        $cand = Join-Path (Split-Path $py.Source) 'pythonw.exe'
        if (Test-Path $cand) { return $cand }
    }
    $globs = @(
        "$env:LOCALAPPDATA\Programs\Python\Python3*\pythonw.exe",
        "$env:ProgramFiles\Python3*\pythonw.exe",
        "${env:ProgramFiles(x86)}\Python3*\pythonw.exe",
        "C:\Python3*\pythonw.exe"
    )
    foreach ($g in $globs) {
        $hit = Get-ChildItem $g -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($hit) { return $hit.FullName }
    }
    return $null
}

$Pythonw = Find-Pythonw
if (-not $Pythonw) {
    Write-Host "[XATO] pythonw.exe topilmadi." -ForegroundColor Red
    Write-Host "       Python o'rnating (python.org) va 'Add Python to PATH' ni belgilang." -ForegroundColor Yellow
    exit 1
}
Write-Host "pythonw : $Pythonw"
Write-Host "agent   : $AgentPy"

# ── Vazifa XML (SID S-1-5-18 = LocalSystem — til/locale'dan mustaqil) ─────
function XmlEsc([string]$s) {
    return $s.Replace('&', '&amp;').Replace('<', '&lt;').Replace('>', '&gt;')
}
$cmdEsc = XmlEsc $Pythonw
$argEsc = '"' + (XmlEsc $AgentPy) + '"'
$dirEsc = XmlEsc $ScriptDir

$xml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Mezbon chek-printer agenti (orqa fonda)</Description>
  </RegistrationInfo>
  <Triggers>
    <BootTrigger><Enabled>true</Enabled></BootTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>S-1-5-18</UserId>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>7</Priority>
    <RestartOnFailure>
      <Interval>PT1M</Interval>
      <Count>999</Count>
    </RestartOnFailure>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>$cmdEsc</Command>
      <Arguments>$argEsc</Arguments>
      <WorkingDirectory>$dirEsc</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"@

$xmlPath = Join-Path $env:TEMP 'mezbon_printer_task.xml'
[System.IO.File]::WriteAllText($xmlPath, $xml, [System.Text.Encoding]::Unicode)

# Eski vazifa bo'lsa olib tashlaymiz, keyin qayta yaratamiz
schtasks /Delete /TN "$TaskName" /F 2>$null | Out-Null
Write-Host ""
Write-Host "Vazifa yaratilmoqda..."
$out = schtasks /Create /TN "$TaskName" /XML "$xmlPath" /F 2>&1
Write-Host $out
Remove-Item $xmlPath -ErrorAction SilentlyContinue

if ($LASTEXITCODE -ne 0) {
    Write-Host "[XATO] Vazifa yaratilmadi. Yuqoridagi xabarni tekshiring." -ForegroundColor Red
    exit 1
}

# Hozir ishga tushiramiz
schtasks /Run /TN "$TaskName" 2>&1 | Out-Null
Start-Sleep -Seconds 2

$logPath = Join-Path $env:PROGRAMDATA 'MezbonPrinter\agent.log'
Write-Host ""
Write-Host "[OK] '$TaskName' o'rnatildi va ishga tushdi." -ForegroundColor Green
Write-Host "  - Orqa fonda, oynasiz ishlaydi (pythonw)."
Write-Host "  - Kompyuter yonganda o'zi avtomatik ishga tushadi."
Write-Host "  - Ishlamay qolsa Windows uni o'zi qayta tiklaydi."
Write-Host "  - To'xtatish: stop_agent.bat  |  Qayta: start_agent.bat  |  Holat: status_agent.bat"
Write-Host "  - Log fayli: $logPath"
