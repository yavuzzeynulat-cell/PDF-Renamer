# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:/Users/Yafka/AppData/Local/Temp/claude/C--Users-Yafka-Desktop-PDF-ayirici/695d7d28-6626-485e-9de6-3c29e98663da/scratchpad/probe_secret.py'],
    pathex=['.'],
    binaries=[],
    datas=[('license_secret.txt', '.')],
    hiddenimports=[],
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
    name='probe',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='probe',
)
