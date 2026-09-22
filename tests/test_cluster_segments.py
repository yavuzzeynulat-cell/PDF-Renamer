"""cluster.py, kod segmenti kipinde ucdan uca.

Kumeleme iki sekilde eslestirebilir ve secimi KULLANICI yapar:

  match_code_segments=False   tumce METNIN tamaminda aranir (eski davranis)
  match_code_segments=True    yalnizca BELGE KODUNA bakilir, terim tam
                              segment(ler) olarak aranir

Ikinci kip RIA numaralarini gruplamak icin var: "ID" yazinca 26437-RIA-...-ID-
kodlu belgeler toplanir, "VALID" gecen sayfalar toplanmaz.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cluster  # noqa: E402
from config import Settings  # noqa: E402


def _pdf(path: str, lines: list[str]) -> str:
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
def ria(tmp_path):
    """Uc RIA belgesi: ikisi ID'li, biri degil."""
    src = tmp_path / "gelen"
    src.mkdir()
    _pdf(str(src / "a.pdf"), ["26437-RIA-04C-DR-ID-00022", "Kapak"])
    _pdf(str(src / "b.pdf"), ["26437-RIA-07B-DR-ID-00105"])
    # Kodunda ID yok ama SAYFADA "VALID" geciyor: duz metin aramasi buna
    # takilirdi, segment kipi takilmamali.
    _pdf(str(src / "c.pdf"), ["26437-RIA-11A-CA-SP-00470", "VALID until 2027"])
    return src


def _settings(src, terms, **kw):
    base = dict(folder=str(src), phrases=terms, prefix="26437-RIA-",
                match_code_segments=True, move_originals=False,
                all_pages=True)
    base.update(kw)
    return Settings(**base)


def _names(folder):
    return sorted(os.listdir(folder)) if os.path.isdir(folder) else []


# -- temel davranis ----------------------------------------------------------

def test_documents_with_the_segment_are_gathered(ria):
    cluster.cluster_folder(_settings(ria, ["ID"]))
    assert _names(ria / "ID") == ["a.pdf", "b.pdf"]


def test_a_document_without_the_segment_is_left_alone(ria):
    cluster.cluster_folder(_settings(ria, ["ID"]))
    assert "c.pdf" not in _names(ria / "ID")


def test_the_word_valid_on_the_page_does_not_pull_a_file_in(ria):
    """Bu ozelligin varlik sebebi: duz metin aramasi c.pdf'i ID klasorune
    atiyordu, cunku sayfada "VALID" geciyor."""
    cluster.cluster_folder(_settings(ria, ["ID"]))
    assert "c.pdf" not in _names(ria / "ID")


def test_a_run_of_segments_gets_its_own_folder(ria):
    cluster.cluster_folder(_settings(ria, ["04C-DR-ID"]))
    assert _names(ria / "04C-DR-ID") == ["a.pdf"]


def test_a_file_matching_two_terms_goes_into_both(ria):
    cluster.cluster_folder(_settings(ria, ["ID", "04C-DR-ID"]))
    assert "a.pdf" in _names(ria / "ID")
    assert "a.pdf" in _names(ria / "04C-DR-ID")


def test_the_filename_is_not_changed(ria):
    cluster.cluster_folder(_settings(ria, ["ID"]))
    assert "a.pdf" in _names(ria / "ID")


# -- eski davranis korunuyor -------------------------------------------------

def test_plain_text_matching_is_unchanged_when_the_mode_is_off(ria):
    """Kutu kapaliyken bugunku davranis birebir kalmali: "VALID" sayfada
    geciyor diye c.pdf toplanir."""
    cluster.cluster_folder(_settings(ria, ["VALID"], match_code_segments=False))
    assert _names(ria / "VALID") == ["c.pdf"]


def test_the_segment_mode_ignores_that_same_phrase(ria):
    cluster.cluster_folder(_settings(ria, ["VALID"]))
    assert not os.path.isdir(ria / "VALID")


# -- onek degisebilir --------------------------------------------------------

def test_the_wrong_prefix_reads_no_codes_at_all(ria):
    """Onek LAB iken RIA belgelerinde kod bulunmaz, hicbir sey toplanmaz."""
    cluster.cluster_folder(_settings(ria, ["ID"], prefix="26437-LAB-"))
    assert not os.path.isdir(ria / "ID")


def test_switching_the_prefix_switches_which_codes_are_read(tmp_path):
    src = tmp_path / "lab"
    src.mkdir()
    _pdf(str(src / "x.pdf"), ["26437-LAB-04C-DR-ID-00022"])
    cluster.cluster_folder(_settings(src, ["ID"], prefix="26437-LAB-"))
    assert _names(src / "ID") == ["x.pdf"]


# -- onizleme ----------------------------------------------------------------

def test_preview_writes_nothing_to_disk(ria):
    summary = cluster.cluster_folder(_settings(ria, ["ID"], dry_run=True))
    assert not os.path.isdir(ria / "ID")
    assert any(r.status == "preview" for r in summary.results)
