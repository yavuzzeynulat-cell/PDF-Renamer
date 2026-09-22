@echo off
rem PDF-Renamer - KOD TESHISI
rem
rem "Bir sey bulamiyor" dendiginde ilk bakilacak yer burasi. Klasordeki her
rem PDF icin: metin okunabiliyor mu, kod bulunabiliyor mu, bulunan kod kac
rem parca ve hangi parcada ne var.
cd /d "%~dp0"

echo ================================================
echo   PDF-Renamer - Kod Teshisi
echo ================================================
echo.
set /p KLASOR="PDF klasorunun yolu: "
if "%KLASOR%"=="" (
  echo [IPTAL] Klasor girilmedi.
  pause
  exit /b 1
)
set /p ONEK="Code prefix (Enter = 26437-RIA-): "
if "%ONEK%"=="" set ONEK=26437-RIA-

set /p ADLAR="Kume adlari (virgulle, Enter = atla): "

echo.
python kod_teshis.py "%KLASOR%" "%ONEK%" "%ADLAR%"
echo.
pause
