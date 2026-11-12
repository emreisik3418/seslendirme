@echo off
REM DocVoice klasor izleyici - cift tiklayarak baslatin, durdurmak icin pencereyi kapatin veya Ctrl+C
REM (app launcher / zamanlayici icin izleyici_servis.bat kullanin)
cd /d "%~dp0"
title DocVoice izleyici
call "%~dp0izleyici_servis.bat" %*
pause
