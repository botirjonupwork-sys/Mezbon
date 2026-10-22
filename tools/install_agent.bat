@echo off
chcp 65001 >nul
REM ── Mezbon printer agentini ORQA FONDA xizmat sifatida o'rnatadi ──
REM Administrator huquqi kerak — quyida o'zi so'raydi.
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Administrator huquqi so'ralmoqda...
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_agent.ps1"
echo.
pause
