@echo off
rem PDF-Renamer.exe'yi launcher modunda (onedir) derler ve guncellenebilir
rem kod dosyalarini dist\PDF-Renamer\src\ icine kopyalar.
rem Sonuc klasoru: dist\PDF-Renamer\  (installer bu klasoru paketler)
cd /d "%~dp0"

python -m PyInstaller --noconfirm --clean PDF-Renamer.spec
if errorlevel 1 (
  echo.
  echo [HATA] Derleme basarisiz.
  pause
  exit /b 1
)

echo.
echo src/ dosyalari dist'e kopyalaniyor...
set SRCDIR=dist\PDF-Renamer\src
if not exist "%SRCDIR%" mkdir "%SRCDIR%"
copy /Y main.py        "%SRCDIR%\" >nul
copy /Y gui.py         "%SRCDIR%\" >nul
copy /Y core.py        "%SRCDIR%\" >nul
copy /Y extractor.py   "%SRCDIR%\" >nul
copy /Y code_finder.py "%SRCDIR%\" >nul
copy /Y renamer.py     "%SRCDIR%\" >nul
copy /Y config.py      "%SRCDIR%\" >nul
copy /Y theme.py       "%SRCDIR%\" >nul
copy /Y cli.py         "%SRCDIR%\" >nul
copy /Y updater.py     "%SRCDIR%\" >nul
copy /Y version.txt    "%SRCDIR%\" >nul

echo.
echo ============================================
echo  Bitti:  dist\PDF-Renamer\PDF-Renamer.exe
echo  Kaynak: dist\PDF-Renamer\src\
echo ============================================
pause
