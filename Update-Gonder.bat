@echo off
rem PDF-Renamer - GUNCELLEME GONDER  (tek hareket)
rem
rem Surumu sorar, geri kalan her seyi kendisi yapar:
rem   - src.zip paketler
rem   - EXE'ye gomulu bir sey degistiyse (launcher, lisans, requirements,
rem     spec, installer, ikon) EXE'yi ve kurulum dosyasini YENIDEN DERLER
rem   - GitHub'da release olusturur, commit + push eder
rem
rem Derle-EXE.bat / Derle-Installer.bat'i elle calistirmana gerek yok.
cd /d "%~dp0"

echo ================================================
echo   PDF-Renamer - Guncelleme Gonder
echo ================================================
echo.

rem Simdiki surumu goster ki bir sonrakini secmek kolay olsun.
if exist version.txt (
  set /p CUR=<version.txt
  echo Simdiki surum: %CUR%
  echo.
)

set /p VER="Yeni surum (or. 2.3.4): "
if "%VER%"=="" (
  echo [IPTAL] Surum girilmedi.
  pause
  exit /b 1
)
set /p NOTES="Degisiklik notu (Enter ile bos birakabilirsin): "

echo.
python publish_update.py %VER% "%NOTES%"
if errorlevel 1 (
  echo.
  echo [HATA] Guncelleme gonderilemedi. Yukaridaki mesaja bak.
  pause
  exit /b 1
)

echo.
pause
