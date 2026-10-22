@echo off
chcp 65001 >nul
REM ── Agentni to'xtatadi (faqat shu buyruq bilan to'xtaydi) ──
REM To'xtatadi VA o'chiradi: qayta yoqilmaguncha (start_agent.bat) ishlamaydi.
net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)
set TN=MezbonPrinterAgent
echo Agent to'xtatilmoqda...
schtasks /End /TN "%TN%" >nul 2>&1
schtasks /Change /TN "%TN%" /DISABLE >nul 2>&1
REM Faqat shu agentning pythonw jarayonini o'ldiramiz (boshqalariga tegmaymiz)
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*xprinter_agent.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1
echo [OK] Agent to'xtatildi. Qayta yoqish uchun: start_agent.bat
echo.
pause
