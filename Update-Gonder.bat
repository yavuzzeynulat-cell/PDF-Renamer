@echo off
rem PDF-Renamer - GUNCELLEME GONDER
rem Kod degisikligini yaptiktan sonra bunu calistir: yeni surumu sorar,
rem src.zip'i paketler ve GitHub'da yeni surum (release) olusturur.
rem Kullanicilarin programi acilista guncellemeyi gorur ve indirir.
cd /d "%~dp0"

echo ================================================
echo   PDF-Renamer - Guncelleme Gonder
echo ================================================
echo.
set /p VER="Yeni surum (or. 2.0.1): "
if "%VER%"=="" (
  echo [IPTAL] Surum girilmedi.
  pause
  exit /b 1
)
set /p NOTES="Degisiklik notu (Enter ile bos birakabilirsin): "

python publish_update.py %VER% "%NOTES%"

echo.
pause
