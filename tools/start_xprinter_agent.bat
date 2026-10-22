@echo off
chcp 65001 >nul
REM ── QO'LDA / SOZLASH REJIMI (konsol oynasida, ekranga chiqaradi) ──
REM Bu fayl faqat sinab ko'rish/sozlash uchun. Doimiy ishlatish uchun
REM agentni ORQA FONDA o'rnating:  install_agent.bat (administrator).
REM Bu yerda agent ko'rinadigan oynada ishlaydi va uzilsa qayta yoqiladi.

cd /d "%~dp0"
:loop
echo [%date% %time%] Agent ishga tushmoqda (konsol rejimi)...
python xprinter_agent.py
echo [%date% %time%] Agent to'xtadi. 10 soniyadan keyin qayta yoqaman...
timeout /t 10 /nobreak >nul
goto loop
