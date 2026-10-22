@echo off
chcp 65001 >nul
REM ── Agentni (qayta) ishga tushiradi ──
net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)
set TN=MezbonPrinterAgent
schtasks /Change /TN "%TN%" /ENABLE >nul 2>&1
schtasks /Run /TN "%TN%" >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Agent ishga tushdi (orqa fonda).
) else (
    echo [XATO] Vazifa topilmadi. Avval install_agent.bat ni ishga tushiring.
)
echo.
pause
