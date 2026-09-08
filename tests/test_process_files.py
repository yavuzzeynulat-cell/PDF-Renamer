"""Surukle-birak akisinin cekirdegi: core.process_files / expand_pdf_paths.

Birakilan dosyalar YERINDE islenmelidir: her dosya kendi klasorunde yeniden
adlandirilir, hicbir dosya baska bir yere tasinmaz.
"""
import os
import shutil

import core
from config import Settings

SAMPLES = os.path.join(os.path.dirname(__file__), "sample_pdfs")


def _copy(src_name, dest_dir, dest_name=None):
    os.makedirs(dest_dir, exist_ok=True)
    dst = os.path.join(dest_dir, dest_name or src_name)
    shutil.copy(os.path.join(SAMPLES, src_name), dst)
    return dst


def _files(folder):
    return {f for f in os.listdir(folder) if f.lower().endswith(".pdf")}


# -- expand_pdf_paths -------------------------------------------------------

def test_expand_keeps_only_pdfs(tmp_path):
    pdf = _copy("01_text_kod.pdf", str(tmp_path))
    junk = os.path.join(str(tmp_path), "notes.txt")
    open(junk, "w").close()
    assert core.expand_pdf_paths([pdf, junk]) == [pdf]


def test_expand_unfolds_directories(tmp_path):
    _copy("01_text_kod.pdf", str(tmp_path))
    _copy("02_kod_sayfa2.pdf", str(tmp_path))
    got = {os.path.basename(p) for p in core.expand_pdf_paths([str(tmp_path)])}
    assert got == {"01_text_kod.pdf", "02_kod_sayfa2.pdf"}


def test_expand_drops_duplicates(tmp_path):
    pdf = _copy("01_text_kod.pdf", str(tmp_path))
    # Ayni dosya: dogrudan, klasor uzerinden ve buyuk harfli hali
    out = core.expand_pdf_paths([pdf, str(tmp_path), pdf.upper()])
    assert len(out) == 1


def test_expand_ignores_missing_paths(tmp_path):
    assert core.expand_pdf_paths([str(tmp_path / "yok.pdf"), ""]) == []


# -- process_files ----------------------------------------------------------

def test_renames_in_place_across_two_folders(tmp_path):
    a, b = str(tmp_path / "A"), str(tmp_path / "B")
    p1 = _copy("01_text_kod.pdf", a)
    p2 = _copy("02_kod_sayfa2.pdf", b)

    summary = core.process_files([p1, p2], Settings(all_pages=True))

    assert summary.renamed == 2
    # Her dosya KENDI klasorunde yeniden adlandirildi, tasinmadi.
    assert _files(a) == {"26437-LAB-001.pdf"}
    assert _files(b) == {"26437-LAB-205.pdf"}


def test_ignores_the_folder_setting(tmp_path):
    """settings.folder bos/alakasiz olsa da birakilan dosya islenir."""
    src = str(tmp_path / "elsewhere")
    p = _copy("01_text_kod.pdf", src)
    core.process_files([p], Settings(folder=str(tmp_path / "bos_klasor")))
    assert _files(src) == {"26437-LAB-001.pdf"}


def test_dry_run_touches_nothing(tmp_path):
    p = _copy("01_text_kod.pdf", str(tmp_path))
    summary = core.process_files([p], Settings(dry_run=True))
    assert summary.results[0].status == "preview"
    assert summary.results[0].new_name == "26437-LAB-001.pdf"
    assert _files(str(tmp_path)) == {"01_text_kod.pdf"}


def test_result_carries_full_path(tmp_path):
    """GUI, satira cift tiklayinca dosyayi acabilmek icin tam yola guvenir."""
    p = _copy("01_text_kod.pdf", str(tmp_path))
    summary = core.process_files([p], Settings(dry_run=True))
    assert summary.results[0].path == p


def test_undo_works_per_folder(tmp_path):
    a, b = str(tmp_path / "A"), str(tmp_path / "B")
    p1 = _copy("01_text_kod.pdf", a)
    p2 = _copy("02_kod_sayfa2.pdf", b)
    core.process_files([p1, p2], Settings(all_pages=True))

    from renamer import undo_last
    undo_last(a)
    undo_last(b)
    assert _files(a) == {"01_text_kod.pdf"}
    assert _files(b) == {"02_kod_sayfa2.pdf"}


def test_not_found_is_reported(tmp_path):
    p = _copy("03_kodsuz.pdf", str(tmp_path))
    summary = core.process_files([p], Settings(dry_run=True))
    assert summary.not_found == 1
    assert _files(str(tmp_path)) == {"03_kodsuz.pdf"}


# -- process_folder degismedi ----------------------------------------------

def test_process_folder_still_reports_paths(tmp_path):
    _copy("01_text_kod.pdf", str(tmp_path))
    summary = core.process_folder(Settings(folder=str(tmp_path), dry_run=True))
    assert summary.results[0].path.endswith("01_text_kod.pdf")
    assert os.path.isabs(summary.results[0].path)
