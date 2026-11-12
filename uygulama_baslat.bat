@echo off
REM DocVoice arayuzu (Streamlit) - cift tiklayarak baslatin, kapatmak icin Ctrl+C
setlocal
cd /d "%~dp0"
title DocVoice
REM Python secimi: 1) proje icindeki .venv (kurulum.bat olusturur)  2) DOCVOICE_PYTHON ortam degiskeni  3) PATH'teki python
set "PY="
if exist "%~dp0.venv\Scripts\python.exe" set "PY=%~dp0.venv\Scripts\python.exe"
if not defined PY if defined DOCVOICE_PYTHON set "PY=%DOCVOICE_PYTHON%"
if not defined PY set "PY=python"
echo Python: %PY%
"%PY%" -m streamlit run "%~dp0app.py"
pause
