# -*- mode: python ; coding: utf-8 -*-
# launcher modu (onedir): EXE bir baslaticidir; uygulama kodu yanindaki src/
# klasorunden calisir ve updater ile guncellenir. Agir bagimliliklar burada
# pakete gomulur.
from PyInstaller.utils.hooks import collect_all

datas = []
# Lisans anahtari: depoda yok, derleme aninda EXE'ye gomulur.
# Yoksa derleme surer ama uretilen EXE'de lisans kapisi KAPALI olur.
import os as _os
if _os.path.exists('license_secret.txt'):
    datas += [('license_secret.txt', '.')]
else:
    print('[UYARI] license_secret.txt yok - EXE lisans kapisi OLMADAN derlenecek.')
binaries = []
hiddenimports = []
for _pkg in ('pdfplumber', 'pypdfium2', 'pdfminer', 'fitz',
             'rapidocr_onnxruntime', 'onnxruntime', 'cv2', 'numpy', 'PIL',
             'openpyxl'):
    _d, _b, _h = collect_all(_pkg)
    datas += _d
    binaries += _b
    hiddenimports += _h


a = Analysis(
    ['launcher.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PDF-Renamer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets\\app.ico'],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='PDF-Renamer',
)
