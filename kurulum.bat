@echo off
REM DocVoice kurulum: proje klasorune .venv (ayri Python ortami) olusturur ve paketleri oraya kurar.
REM Bir kez calistirin (requirements.txt degisirse tekrar). pip ayarlari %APPDATA%\pip\pip.ini'den okunur.
REM Farkli bir Python ile kurmak icin: kurulum.bat "C:\Program Files\Python312\python.exe"
setlocal
cd /d "%~dp0"
set "TABAN=python"
if not "%~1"=="" set "TABAN=%~1"

if exist ".venv\Scripts\python.exe" goto paketler
echo Sanal ortam olusturuluyor: %~dp0.venv
"%TABAN%" -m venv .venv
if errorlevel 1 goto hata_venv

:paketler
echo Paketler kuruluyor...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto hata_pip
echo.
".venv\Scripts\python.exe" dosya_kontrol.py
echo.
echo Kurulum tamam. Bat dosyalari artik .venv icindeki Python'u kullanir.
pause
exit /b 0

:hata_venv
echo HATA: sanal ortam olusturulamadi. Python yolu: %TABAN%
echo Python kurulu degilse kurun veya yolunu verin: kurulum.bat "C:\...\python.exe"
pause
exit /b 1

:hata_pip
echo HATA: paketler kurulamadi. pip.ini ayarini kontrol edin: pip config list
pause
exit /b 1
