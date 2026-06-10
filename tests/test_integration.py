"""Uctan uca entegrasyon testi.

Ornek PDF'leri gecici klasore kopyalar, core.process_folder'i GERCEKTEN
calistirip dosya adlarini kontrol eder. Hem mevcut V1 davranisinin korundugunu
hem de yeni ozelliklerin (cok sayfa, kucuk harf, cakisma, geri-al) calistigini
dogrular.
"""
import os
import shutil

import pytest

import core
import renamer
from config import Settings

SAMPLES = os.path.join(os.path.dirname(__file__), "sample_pdfs")


def _seed(tmp_path, names):
    for n in names:
        shutil.copy(os.path.join(SAMPLES, n), os.path.join(tmp_path, n))


def _files(folder):
    return {f for f in os.listdir(folder) if f.lower().endswith(".pdf")}


def test_preserves_v1_happy_path(tmp_path):
    # 01_text_kod.pdf -> 26437-LAB-001.pdf (mevcut surumun de yaptigi)
    _seed(tmp_path, ["01_text_kod.pdf"])
    summary = core.process_folder(Settings(folder=str(tmp_path)))
    assert "26437-LAB-001.pdf" in _files(tmp_path)
    assert summary.renamed == 1


def test_finds_code_on_page_two(tmp_path):
    # Yeni ozellik: kod 2. sayfada (V1 bulamazdi)
    _seed(tmp_path, ["02_kod_sayfa2.pdf"])
    core.process_folder(Settings(folder=str(tmp_path), all_pages=True))
    assert "26437-LAB-205.pdf" in _files(tmp_path)


def test_only_first_page_when_disabled(tmp_path):
    # all_pages=False -> 2. sayfadaki kodu bulMAMALI (V1 kapsami)
    _seed(tmp_path, ["02_kod_sayfa2.pdf"])
    summary = core.process_folder(Settings(folder=str(tmp_path), all_pages=False))
    assert "02_kod_sayfa2.pdf" in _files(tmp_path)
    assert summary.not_found == 1


def test_lowercase_with_ignore_case(tmp_path):
    # Yeni ozellik: kucuk harfli kod ignore_case ile bulunur
    _seed(tmp_path, ["04_kucuk_harf.pdf"])
    core.process_folder(Settings(folder=str(tmp_path), ignore_case=True))
    assert "26437-lab-309.pdf" in _files(tmp_path)


def test_codeless_reported_not_found(tmp_path):
    _seed(tmp_path, ["03_kodsuz.pdf"])
    summary = core.process_folder(Settings(folder=str(tmp_path)))
    assert summary.not_found == 1
    assert "03_kodsuz.pdf" in _files(tmp_path)  # dokunulmadi


def test_conflict_numbering(tmp_path):
    # Ayni koddan iki dosya -> '... (1).pdf'
    _seed(tmp_path, ["06_cakisma_a.pdf", "07_cakisma_b.pdf"])
    core.process_folder(Settings(folder=str(tmp_path)))
    files = _files(tmp_path)
    assert "26437-LAB-001.pdf" in files
    assert "26437-LAB-001 (1).pdf" in files


def test_dry_run_changes_nothing(tmp_path):
    _seed(tmp_path, ["01_text_kod.pdf"])
    before = _files(tmp_path)
    summary = core.process_folder(Settings(folder=str(tmp_path), dry_run=True))
    assert _files(tmp_path) == before  # disk degismedi
    assert summary.renamed == 1        # ama onizleme sayiyor


def test_suffix_attached_without_space(tmp_path):
    # Suffix is glued directly to the code (no automatic space)
    _seed(tmp_path, ["01_text_kod.pdf"])
    core.process_folder(Settings(folder=str(tmp_path), suffix="-REV"))
    assert "26437-LAB-001-REV.pdf" in _files(tmp_path)


def test_changed_prefix(tmp_path):
    # Changing the prefix builds a new pattern; default code no longer matches
    _seed(tmp_path, ["01_text_kod.pdf"])
    summary = core.process_folder(Settings(folder=str(tmp_path), prefix="99999-XX-"))
    assert summary.not_found == 1
    assert "01_text_kod.pdf" in _files(tmp_path)  # untouched


def test_undo_restores_names(tmp_path):
    _seed(tmp_path, ["01_text_kod.pdf"])
    core.process_folder(Settings(folder=str(tmp_path)))
    assert "26437-LAB-001.pdf" in _files(tmp_path)
    outcomes = renamer.undo_last(str(tmp_path))
    assert any(o.status == "renamed" for o in outcomes)
    assert "01_text_kod.pdf" in _files(tmp_path)
