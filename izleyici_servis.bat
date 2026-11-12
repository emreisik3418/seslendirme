@echo off
REM DocVoice klasor izleyici - app launcher / Gorev Zamanlayici / hizmet icin (sonunda tus beklemez)
REM Elle baslatmak icin izleyici_baslat.bat dosyasini kullanin.
setlocal
cd /d "%~dp0"
REM Python secimi: 1) proje icindeki .venv (kurulum.bat olusturur)  2) DOCVOICE_PYTHON ortam degiskeni  3) PATH'teki python
set "PY="
if exist "%~dp0.venv\Scripts\python.exe" set "PY=%~dp0.venv\Scripts\python.exe"
if not defined PY if defined DOCVOICE_PYTHON set "PY=%DOCVOICE_PYTHON%"
if not defined PY set "PY=python"
echo Python: %PY%
"%PY%" "%~dp0izleyici.py" %*
exit /b %ERRORLEVEL%
