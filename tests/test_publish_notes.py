"""publish_update.py: release notlarinin dogru kurulmasi.

Istemci notlardan iki ayri ozeti okuyor: src.zip icin 'SHA256:' ve tam
kurulum icin 'SETUP_SHA256:'. Yanlis yazilirsa istemci ya guncellemeyi
goremez ya da yanlis ozetle dogrulama yapip basarisiz olur.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import publish_update  # noqa: E402
import updater  # noqa: E402

ZIP = "a" * 64
SETUP = "c" * 64


def test_notes_carry_the_zip_hash():
    notes = publish_update.build_notes(ZIP, None, "")
    assert updater._parse_sha256(notes) == ZIP
    assert updater._parse_setup_sha256(notes) is None


def test_notes_carry_both_hashes_without_confusing_them():
    notes = publish_update.build_notes(ZIP, SETUP, "Kumeleme eklendi")
    assert updater._parse_sha256(notes) == ZIP
    assert updater._parse_setup_sha256(notes) == SETUP
    assert "Kumeleme eklendi" in notes


# -- bayat kurulum dosyasi ---------------------------------------------------

def test_a_stale_setup_is_refused(tmp_path):
    """GERCEK OLAY: v2.2.8'den v2.3.2'ye kadar her release'e AYNI setup.exe
    yuklendi -- Derle-EXE + Derle-Installer tekrar calistirilmadigi icin
    icinde hala 2.2.7 vardi. Kullanicinin makinesi 110 MB indirip kuruyor,
    surum degismiyor, guncelleme "hic olmamis" gibi gorunuyordu. Yuklemeden
    ONCE yakalanmali."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "version.txt").write_text("2.2.7")
    problem = publish_update.check_setup_is_fresh("2.3.3", str(tmp_path))
    assert problem
    assert "2.2.7" in problem and "2.3.3" in problem


def test_a_freshly_built_setup_passes(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "version.txt").write_text("2.3.3")
    assert publish_update.check_setup_is_fresh("2.3.3", str(tmp_path)) == ""


def test_a_missing_build_is_refused(tmp_path):
    """dist/ hic yoksa yuklenecek setup baska bir derlemeden kalmadir."""
    problem = publish_update.check_setup_is_fresh("2.3.3", str(tmp_path))
    assert problem
