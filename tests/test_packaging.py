"""Paketleme listeleri kod tabaniyla ayni kalsin.

Uygulama kodu EXE'ye gomulmez; exe'nin yanindaki src/ klasorunde durur ve
oradan guncellenir. Hangi dosyalarin src/'ye girecegi UC AYRI yerde elle
yazilmistir:

    Derle-EXE.bat        -> dist/PDF-Renamer/src/ icine kopyalanacaklar
    launcher.py          -> _APP_MODULES (guncelleme sonrasi yeniden yuklenecekler)
    publish_update.py    -> SRC_FILES (src.zip icine girecekler)

Yeni bir modul eklenip bu listelerden biri unutulursa, kullanicilar
guncellemede YARIM bir src/ alir ve uygulama acilista ImportError ile coker.
Bu test tam olarak onu engeller.
"""
from __future__ import annotations

import io
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# src/'ye GIRMEYEN, kok dizinde yasayan dosyalar:
#   launcher.py       EXE'nin kendisi, src/'den yuklenmez
#   publish_update.py yalnizca gelistirici araci
#   kod_teshis.py     yalnizca teshis araci; uygulama onu import etmez
#   v1_original.py    tarihsel yedek, uygulama onu import etmez
#   license_client.py lisans kapisi. BILEREK src/ disinda: launcher.py onu
#                     import ettigi icin EXE'ye gomulur. src/ dosyalari
#                     exe'nin yaninda DUZ METIN durur; SECRET oraya konursa
#                     Not Defteri ile okunur. Ayrica kapinin kendisi,
#                     kapinin denetledigi guncelleme kanaliyla degismemeli.
NOT_SHIPPED = {"launcher.py", "publish_update.py", "kod_teshis.py",
               "v1_original.py", "license_client.py"}


def _app_modules() -> set:
    """Kok dizindeki, src/ ile gonderilmesi gereken .py dosyalari."""
    return {
        name for name in os.listdir(ROOT)
        if name.endswith(".py") and name not in NOT_SHIPPED
        and os.path.isfile(os.path.join(ROOT, name))
    }


def _read(name: str) -> str:
    with io.open(os.path.join(ROOT, name), encoding="utf-8") as fh:
        return fh.read()


def test_publish_update_ships_every_app_module():
    src_files = set(re.findall(r'"([A-Za-z_][A-Za-z0-9_]*\.py)"',
                               _read("publish_update.py")))
    missing = sorted(_app_modules() - src_files)
    assert not missing, (
        "publish_update.py SRC_FILES eksik: " + ", ".join(missing)
        + " -- guncelleme yarim src/ gonderir, uygulama acilmaz.")


def test_build_script_copies_every_app_module():
    bat = _read("Derle-EXE.bat")
    copied = set(re.findall(r'copy /Y\s+([A-Za-z_][A-Za-z0-9_]*\.py)', bat))
    missing = sorted(_app_modules() - copied)
    assert not missing, (
        "Derle-EXE.bat eksik: " + ", ".join(missing)
        + " -- derlenen EXE yaninda bu dosyalar olmaz.")


def test_launcher_reloads_every_app_module():
    text = _read("launcher.py")
    block = re.search(r"_APP_MODULES\s*=\s*\((.*?)\)", text, re.S)
    assert block, "launcher.py icinde _APP_MODULES bulunamadi"
    listed = set(re.findall(r'"([A-Za-z_][A-Za-z0-9_]*)"', block.group(1)))
    expected = {name[:-3] for name in _app_modules()}
    missing = sorted(expected - listed)
    assert not missing, (
        "launcher.py _APP_MODULES eksik: " + ", ".join(missing)
        + " -- guncelleme sonrasi eski modul bellekte kalabilir.")


# ---------------------------------------------------------------------------
# Onek kalici olmali
#
# GERCEK HATA: kullanici Code prefix'i 26437-RIA- yapiyor, programi
# kapatiyor, tekrar aciyor ve deger 26437-LAB-'a donmus oluyordu. Kod
# filtresi o zaman LAB kodunu okuyor, onda ID gecmedigi icin "hicbir sey
# bulamiyor". Bulmasi imkansiz bir ayari her acilista sifirlamak, hatayi
# da gorunmez kiliyordu.
# ---------------------------------------------------------------------------

def test_the_code_prefix_is_saved_and_restored():
    gui = _read("gui.py")
    assert '_prefs["prefix"]' in gui, \
        "onek prefs'e yazilmiyor: her acilista varsayilana doner"
    assert '_prefs.get("prefix"' in gui, \
        "onek prefs'ten okunmuyor: kaydedilse bile geri gelmez"
