@echo off
rem Resmi Setup.exe kurulumu olusturur (Inno Setup gerekir).
rem Once Derle-EXE.bat ile dist\PDF-Renamer.exe olusturulmus olmalidir.
rem Inno Setup: https://jrsoftware.org/isdl.php
cd /d "%~dp0"
where iscc >nul 2>nul
if errorlevel 1 (
  echo [HATA] Inno Setup bulunamadi ^(iscc^).
  echo Kurmak icin: https://jrsoftware.org/isdl.php
  pause
  exit /b 1
)
iscc installer.iss
echo.
echo ============================================
echo  Bitti:  installer_output\PDF-Renamer-Setup.exe
echo ============================================
pause
