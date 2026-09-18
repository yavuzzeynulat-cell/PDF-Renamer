"""cluster.py ucdan uca: tumce bul -> kume klasorune KOPYALA.

Kumeleme yeniden adlandirmadan bagimsiz bir istir:
  - dosya adlari DEGISMEZ (zaten dokuman numarasi ile adlandirilmis olurlar)
  - orijinaller yerinde kalir, yalnizca kopya olusur
  - bir dosya birden cok tumce iceriyorsa her birinin klasorune kopyalanir
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cluster  # noqa: E402
from config import Settings  # noqa: E402

PHRASES = ["B0051 Bridge", "B0052 Tunnel", "C0100 Viaduct"]


def _pdf(path: str, lines: list[str]) -> str:
    """Verilen satirlari iceren gercek bir metin-katmanli PDF yazar."""
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    y = 72
    for line in lines:
        page.insert_text((72, y), line, fontsize=12, fontname="helv")
        y += 22
    doc.save(path)
    doc.close()
    return path


@pytest.fixture
def workspace(tmp_path):
    """Kaynak klasor (3 PDF) + henuz olusmamis hedef klasor."""
    src = tmp_path / "kaynak"
    src.mkdir()
    _pdf(str(src / "26437-LAB-001.pdf"), ["Rapor", "Structure: B0051 Bridge", "son"])
    _pdf(str(src / "26437-LAB-002.pdf"), ["Kapsam: B0051 Bridge ve B0052 Tunnel"])
    _pdf(str(src / "26437-LAB-003.pdf"), ["Bu belgede yapi adi gecmiyor"])
    return src, tmp_path / "Yapilar"


def _settings(target, **kw) -> Settings:
    return Settings(phrases=list(PHRASES), target_folder=str(target), **kw)


def _names(folder) -> set[str]:
    return set(os.listdir(folder)) if os.path.isdir(folder) else set()


# -- temel davranis ----------------------------------------------------------

def test_file_lands_in_the_folder_named_after_the_phrase(workspace):
    src, target = workspace
    cluster.cluster_folder(_settings(target, folder=str(src)))
    assert "26437-LAB-001.pdf" in _names(target / "B0051 Bridge")


def test_copy_mode_leaves_the_original_where_it_was(workspace):
    """Kopyalama kipinde (move_originals=False) kaynak hic degismez.

    Varsayilan kip TASIMA; orada kaynagin bosalmasi beklenir ve bunu
    test_cluster_move.py dogrular. Burada kopyalama kipinin hala calistigini
    sabitliyoruz.
    """
    src, target = workspace
    cluster.cluster_folder(_settings(target, folder=str(src),
                                     move_originals=False))
    assert _names(src) == {"26437-LAB-001.pdf", "26437-LAB-002.pdf",
                           "26437-LAB-003.pdf"}


def test_the_filename_is_not_changed(workspace):
    src, target = workspace
    cluster.cluster_folder(_settings(target, folder=str(src)))
    assert _names(target / "B0051 Bridge") == {"26437-LAB-001.pdf",
                                               "26437-LAB-002.pdf"}


def test_a_file_matching_two_phrases_is_copied_into_both(workspace):
    src, target = workspace
    cluster.cluster_folder(_settings(target, folder=str(src)))
    assert "26437-LAB-002.pdf" in _names(target / "B0051 Bridge")
    assert "26437-LAB-002.pdf" in _names(target / "B0052 Tunnel")


def test_a_file_matching_nothing_is_not_copied(workspace):
    src, target = workspace
    cluster.cluster_folder(_settings(target, folder=str(src)))
    for folder in _names(target):
        assert "26437-LAB-003.pdf" not in _names(target / folder)


def test_a_phrase_nobody_mentions_creates_no_folder(workspace):
    src, target = workspace
    cluster.cluster_folder(_settings(target, folder=str(src)))
    assert "C0100 Viaduct" not in _names(target)


# -- ozet sayaclari ----------------------------------------------------------

def test_summary_counts_files_and_copies(workspace):
    src, target = workspace
    s = cluster.cluster_folder(_settings(target, folder=str(src)))
    assert s.matched == 2      # eslesen DOSYA sayisi
    assert s.copies == 3       # olusan KOPYA sayisi (002 iki kez)
    assert s.no_match == 1
    assert s.errors == 0
    assert s.total == 3


# -- onizleme ----------------------------------------------------------------

def test_preview_writes_nothing_to_disk(workspace):
    src, target = workspace
    s = cluster.cluster_folder(_settings(target, folder=str(src), dry_run=True))
    assert not target.exists()
    assert s.copies == 3       # yine de ne olacagini bildirir


def test_preview_reports_the_groups_per_file(workspace):
    src, target = workspace
    s = cluster.cluster_folder(_settings(target, folder=str(src), dry_run=True))
    by_name = {r.file_name: r.groups for r in s.results}
    assert by_name["26437-LAB-002.pdf"] == ["B0051 Bridge", "B0052 Tunnel"]
    assert by_name["26437-LAB-003.pdf"] == []


# -- kullanicinin karari: kosulsuz kopyala, atlama yok -----------------------

def test_copy_mode_run_twice_copies_again_instead_of_skipping(workspace):
    """Kullanicinin karari: atlama yok. (Kopyalama kipinde gozlenebilir --
    tasima kipinde ikinci calistirmada kaynakta dosya kalmaz.)"""
    src, target = workspace
    opts = dict(folder=str(src), move_originals=False)
    cluster.cluster_folder(_settings(target, **opts))
    cluster.cluster_folder(_settings(target, **opts))
    assert _names(target / "B0051 Bridge") == {
        "26437-LAB-001.pdf", "26437-LAB-002.pdf",
        "26437-LAB-001 (1).pdf", "26437-LAB-002 (1).pdf",
    }


# -- eslestirme kipi OCR dugmesine bagli -------------------------------------

def test_strict_mode_misses_a_differently_cased_phrase(tmp_path):
    src = tmp_path / "k"
    src.mkdir()
    _pdf(str(src / "a.pdf"), ["STRUCTURE: B0051 BRIDGE"])
    target = tmp_path / "out"
    s = cluster.cluster_folder(_settings(target, folder=str(src), use_ocr=False))
    assert s.no_match == 1
    assert not target.exists()


def test_ocr_mode_matches_a_differently_cased_phrase(tmp_path):
    src = tmp_path / "k"
    src.mkdir()
    _pdf(str(src / "a.pdf"), ["STRUCTURE: B0051 BRIDGE"])
    target = tmp_path / "out"
    s = cluster.cluster_folder(_settings(target, folder=str(src), use_ocr=True))
    assert s.matched == 1
    assert "a.pdf" in _names(target / "B0051 Bridge")


# -- arayuzun ihtiyaclari ----------------------------------------------------

def test_progress_is_reported_once_per_file(workspace):
    src, target = workspace
    seen = []
    cluster.cluster_folder(_settings(target, folder=str(src), dry_run=True),
                           progress=lambda i, t, r: seen.append((i, t)))
    assert seen == [(1, 3), (2, 3), (3, 3)]


def test_apply_reuses_the_groups_found_during_preview(workspace):
    """Onizlemede bulunan kumeler Apply'da yeniden taranmamali (OCR pahali)."""
    src, target = workspace
    preview = cluster.cluster_folder(_settings(target, folder=str(src), dry_run=True))

    # Metin cikarimi yapilirsa test patlar: extractor'u bilerek bozuyoruz.
    import extractor
    original = extractor.extract_text
    extractor.extract_text = lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("Apply asamasinda PDF yeniden okundu"))
    try:
        cluster.cluster_folder(_settings(target, folder=str(src)),
                               group_overrides=preview.plan)
    finally:
        extractor.extract_text = original

    assert "26437-LAB-001.pdf" in _names(target / "B0051 Bridge")


def test_an_unreadable_file_is_reported_as_an_error(tmp_path):
    src = tmp_path / "k"
    src.mkdir()
    (src / "bozuk.pdf").write_bytes(b"bu bir PDF degil")
    s = cluster.cluster_folder(_settings(tmp_path / "out", folder=str(src)))
    assert s.errors == 1
    assert s.results[0].status == "error"


def test_explicit_file_list_is_processed(tmp_path):
    """Surukle-birak akisi: klasor degil, acikca verilen dosyalar."""
    src = tmp_path / "k"
    src.mkdir()
    _pdf(str(src / "a.pdf"), ["B0051 Bridge"])
    _pdf(str(src / "b.pdf"), ["B0051 Bridge"])
    target = tmp_path / "out"
    s = cluster.cluster_files([str(src / "a.pdf")], _settings(target))
    assert s.total == 1
    assert _names(target / "B0051 Bridge") == {"a.pdf"}
