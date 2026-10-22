@echo off
chcp 65001 >nul
REM ── Agent holati: vazifa + jarayon + oxirgi loglar ──
set TN=MezbonPrinterAgent
echo ===== VAZIFA HOLATI =====
schtasks /Query /TN "%TN%" /V /FO LIST 2>nul | findstr /I "TaskName Status Result Run"
echo.
echo ===== JARAYON (pythonw) =====
powershell -NoProfile -Command "$p = Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*xprinter_agent.py*' }; if ($p) { $p | ForEach-Object { 'ISHLAYAPTI  PID=' + $_.ProcessId } } else { 'Jarayon topilmadi (ishlamayapti)' }"
echo.
echo ===== OXIRGI 20 LOG =====
powershell -NoProfile -Command "$p = Join-Path $env:PROGRAMDATA 'MezbonPrinter\agent.log'; if (Test-Path $p) { Get-Content $p -Tail 20 } else { 'Log topilmadi: ' + $p }"
echo.
pause
