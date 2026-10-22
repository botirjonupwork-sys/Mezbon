@echo off
chcp 65001 >nul
REM ── Agentni butunlay olib tashlaydi (vazifa o'chiriladi) ──
net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)
set TN=MezbonPrinterAgent
schtasks /End /TN "%TN%" >nul 2>&1
schtasks /Delete /TN "%TN%" /F >nul 2>&1
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*xprinter_agent.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1
echo [OK] Agent butunlay olib tashlandi.
echo.
pause
