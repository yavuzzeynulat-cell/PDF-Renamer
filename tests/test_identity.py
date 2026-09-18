"""Gorunen ad degisebilir; TEKNIK KIMLIKLER degisemez.

Program "PDF Renamer" adiyla dogdu, sonra "PDF Clerk" oldu. Gorunen adi
degistirmek zararsizdir, ama asagidaki kimliklerden birini degistirmek
kullanicida SESSIZCE bir seyi kirar:

    AppId (installer.iss)   Windows kurulumu bununla taniyor. Degisirse
                            mevcut kullanicida IKI ayri kurulum olusur.
    PROGRAM_ID              Lisans kaydi buna bagli. Degisirse herkesin
                            izni gider, program acilmaz.
    GITHUB_REPO             Guncelleme adresi. Degisirse guncelleme durur.
    SETUP_ASSET_NAME        Yayinlanan dosyanin adiyla birebir ayni olmali.
    exe adi                 Kurulum mevcut exe'nin uzerine yazamaz olur.
    prefs klasoru           Kullanicinin kayitli klasoru ve kume adlari
                            burada; degisirse hepsi "kaybolur".
"""
from __future__ import annotations

import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(name: str) -> str:
    with io.open(os.path.join(ROOT, name), encoding="utf-8") as fh:
        return fh.read()


def test_installer_keeps_the_original_upgrade_identity():
    iss = _read("installer.iss")
    assert "AppId=PDF Renamer" in iss, (
        "installer.iss icinde AppId yok ya da degismis. Inno Setup AppId "
        "verilmediginde uygulamayi AppName ile tanir; gorunen adi "
        "degistirdigimiz an mevcut kullanicida ikinci bir kurulum olusur.")


def test_the_licence_program_id_is_unchanged():
    assert 'PROGRAM_ID = "pdf_renamer"' in _read("license_client.py")


def test_the_update_source_is_unchanged():
    upd = _read("updater.py")
    assert 'GITHUB_REPO = "PDF-Renamer"' in upd
    assert 'SETUP_ASSET_NAME = "PDF-Renamer-Setup.exe"' in upd


def test_the_published_setup_is_named_what_the_client_expects():
    """publish_update.py'nin yukledigi ad ile updater'in aradigi ad ayni mi?"""
    import re
    import sys
    sys.path.insert(0, ROOT)
    import updater
    pub = _read("publish_update.py")
    staged = re.search(r'tempfile\.gettempdir\(\),\s*"([^"]+\.exe)"', pub)
    assert staged, "publish_update.py icinde kurulum dosyasi adi bulunamadi"
    assert staged.group(1) == updater.SETUP_ASSET_NAME


def test_the_executable_name_is_unchanged():
    spec = _read("PDF-Renamer.spec")
    assert "name='PDF-Renamer'" in spec
    assert '#define MyAppExe "PDF-Renamer.exe"' in _read("installer.iss")


def test_the_settings_folder_is_unchanged():
    """Kullanicinin kayitli klasoru ve kume adlari bu klasorde yasiyor."""
    assert 'os.path.join(base, "PDF-Renamer")' in _read("gui.py")
