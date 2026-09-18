"""Kumeleme: orijinalleri tasima (kopyalama degil).

Amac kullanicinin kaynak klasorde NE KALDIGINI gorebilmesi. Bu yuzden bir
dosya kumelere girdikten sonra kaynaktan kalkar; geriye yalnizca hicbir
kumeye girmeyenler kalir.

Bir dosya birden cok kumeye girebildigi icin "tasima" sirayla su demek:
once her eslesen kumeye kopyala, KOPYALARI DOGRULA, ancak ondan sonra
orijinali kaldir. Tek bir kopya bile dogrulanamazsa orijinal yerinde kalir --
hicbir kosulda elimizde tek nusha kalmamali.

Orijinal kalici silinmez, Geri Donusum Kutusu'na gider.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cluster  # noqa: E402
import renamer  # noqa: E402
from config import Settings  # noqa: E402

PHRASES = ["B0051 Bridge", "B0052 Tunnel", "C0100 Viaduct"]


def _pdf(path, lines):
    import fitz
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    y = 72
    for line in lines:
        page.insert_text((72, y), line, fontsize=12, fontname="helv")
        y += 22
    doc.save(path)
    doc.close()


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """3 PDF + gercek Geri Donusum Kutusu'na dokunmayan sahte bir kaldirici."""
    src = tmp_path / "kaynak"
    src.mkdir()
    _pdf(str(src / "bir.pdf"), ["Structure: B0051 Bridge"])
    _pdf(str(src / "iki.pdf"), ["B0051 Bridge ve B0052 Tunnel"])
    _pdf(str(src / "uc.pdf"), ["Hicbir yapi adi yok"])

    recycled = []

    def fake_recycle(path):
        recycled.append(os.path.basename(path))
        os.remove(path)
        return True

    monkeypatch.setattr(renamer, "recycle", fake_recycle)
    return src, tmp_path / "Yapilar", recycled


def _settings(target, **kw):
    return Settings(phrases=list(PHRASES), target_folder=str(target), **kw)


def _names(folder):
    return set(os.listdir(folder)) if os.path.isdir(folder) else set()


# -- temel tasima ------------------------------------------------------------

def test_a_matched_file_leaves_the_source_folder(workspace):
    src, target, _ = workspace
    cluster.cluster_folder(_settings(target, folder=str(src)))
    assert "bir.pdf" not in _names(src)


def test_only_the_unmatched_file_is_left_behind(workspace):
    """Kaynakta kalanlar = kullanicinin hala ilgilenmesi gerekenler."""
    src, target, _ = workspace
    cluster.cluster_folder(_settings(target, folder=str(src)))
    assert _names(src) == {"uc.pdf"}


def test_a_file_in_two_groups_reaches_both_before_it_is_removed(workspace):
    src, target, _ = workspace
    cluster.cluster_folder(_settings(target, folder=str(src)))
    assert "iki.pdf" in _names(target / "B0051 Bridge")
    assert "iki.pdf" in _names(target / "B0052 Tunnel")
    assert "iki.pdf" not in _names(src)


def test_originals_go_to_the_recycle_bin_not_oblivion(workspace):
    src, target, recycled = workspace
    cluster.cluster_folder(_settings(target, folder=str(src)))
    assert sorted(recycled) == ["bir.pdf", "iki.pdf"]


# -- guvenlik ----------------------------------------------------------------

def test_the_original_survives_when_a_copy_cannot_be_verified(workspace,
                                                              monkeypatch):
    """Kopya diske tam yazilamadiysa orijinal ASLA kaldirilmaz."""
    src, target, recycled = workspace

    real_copy = renamer.safe_copy

    def broken_copy(src_path, dest_folder, **kw):
        out = real_copy(src_path, dest_folder, **kw)
        if out.status == "copied" and out.dest and os.path.isfile(out.dest):
            with open(out.dest, "wb") as fh:      # yarim dosya taklidi
                fh.write(b"yarim")
        return out

    monkeypatch.setattr(renamer, "safe_copy", broken_copy)
    cluster.cluster_folder(_settings(target, folder=str(src)))

    assert recycled == []
    assert "bir.pdf" in _names(src)


def test_preview_never_removes_anything(workspace):
    src, target, recycled = workspace
    cluster.cluster_folder(_settings(target, folder=str(src), dry_run=True))
    assert recycled == []
    assert _names(src) == {"bir.pdf", "iki.pdf", "uc.pdf"}


def test_copy_mode_leaves_every_original_in_place(workspace):
    src, target, recycled = workspace
    cluster.cluster_folder(_settings(target, folder=str(src),
                                     move_originals=False))
    assert recycled == []
    assert _names(src) == {"bir.pdf", "iki.pdf", "uc.pdf"}
    assert "bir.pdf" in _names(target / "B0051 Bridge")


# -- ozet ve mesaj -----------------------------------------------------------

def test_the_summary_counts_the_files_that_were_moved(workspace):
    src, target, _ = workspace
    summary = cluster.cluster_folder(_settings(target, folder=str(src)))
    assert summary.moved == 2
    assert summary.matched == 2
    assert summary.copies == 3


def test_the_message_says_moved_not_copied(workspace):
    src, target, _ = workspace
    summary = cluster.cluster_folder(_settings(target, folder=str(src)))
    by_name = {r.file_name: r.message for r in summary.results}
    assert "Moved" in by_name["bir.pdf"]
    assert "Copied" not in by_name["bir.pdf"]


def test_copy_mode_still_says_copied(workspace):
    src, target, _ = workspace
    summary = cluster.cluster_folder(_settings(target, folder=str(src),
                                               move_originals=False))
    by_name = {r.file_name: r.message for r in summary.results}
    assert "Copied" in by_name["bir.pdf"]


# -- Geri Donusum Kutusu'nun kendisi ----------------------------------------

def test_recycle_removes_the_file_from_disk(tmp_path):
    """Gercek kancayi bir kez dene: dosya diskten kalkmali."""
    victim = tmp_path / "gecici-test.pdf"
    victim.write_bytes(b"%PDF-1.4 test")
    assert renamer.recycle(str(victim)) is True
    assert not victim.exists()


def test_recycle_reports_failure_for_a_missing_file(tmp_path):
    assert renamer.recycle(str(tmp_path / "olmayan.pdf")) is False
