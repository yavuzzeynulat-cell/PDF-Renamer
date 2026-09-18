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
