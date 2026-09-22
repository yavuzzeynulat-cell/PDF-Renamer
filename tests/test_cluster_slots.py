"""cluster.py, kod filtreleriyle ucdan uca.

Kod filtresi metin kumeleriyle AYNI calistirmada, yan yana calisir ve
birbirlerine karismaz:

    phrases      -> sayfa metninde aranir   (B0051 Bridge)
    code_filters -> belge kodunda YER bazli (5. yerde ID)

Kullanici ikisini ayri yerden yonetir: metin adlari listeden, kod filtreleri
kendi penceresinden.
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
    src = tmp_path / "gelen"
    src.mkdir()
    _pdf(str(src / "a.pdf"), ["26437-RIA-04C-DR-ID-00022", "B0051 Bridge"])
    _pdf(str(src / "b.pdf"), ["26437-RIA-07B-DR-ID-00105"])
    _pdf(str(src / "c.pdf"), ["26437-RIA-11A-CA-SP-00470", "VALID until 2027"])
    return src


def _settings(src, filters=None, phrases=None, **kw):
    base = dict(folder=str(src), phrases=phrases or [],
                code_filters=filters or [], prefix="26437-RIA-",
                move_originals=False, all_pages=True)
    base.update(kw)
    return Settings(**base)


def _names(folder):
    return sorted(os.listdir(folder)) if os.path.isdir(folder) else []


def test_one_slot_gathers_the_matching_documents(ria):
    cluster.cluster_folder(_settings(ria, [["", "", "", "", "ID", ""]]))
    assert _names(ria / "ID") == ["a.pdf", "b.pdf"]


def test_a_document_that_differs_in_that_slot_stays_out(ria):
    cluster.cluster_folder(_settings(ria, [["", "", "", "", "ID", ""]]))
    assert "c.pdf" not in _names(ria / "ID")


def test_two_slots_narrow_the_result(ria):
    cluster.cluster_folder(_settings(ria, [["", "", "04C", "", "ID", ""]]))
    assert _names(ria / "04C-ID") == ["a.pdf"]


def test_two_filters_make_two_folders(ria):
    cluster.cluster_folder(_settings(ria, [["", "", "", "", "ID", ""],
                                           ["", "", "", "CA", "", ""]]))
    assert _names(ria / "ID") == ["a.pdf", "b.pdf"]
    assert _names(ria / "CA") == ["c.pdf"]


def test_text_names_and_code_filters_run_side_by_side(ria):
    """Ayni calistirma: biri metinde, digeri kodda arar."""
    cluster.cluster_folder(_settings(
        ria, filters=[["", "", "", "", "ID", ""]], phrases=["B0051 Bridge"]))
    assert _names(ria / "ID") == ["a.pdf", "b.pdf"]
    assert _names(ria / "B0051 Bridge") == ["a.pdf"]


def test_a_page_word_never_leaks_into_a_code_filter(ria):
    """c.pdf sayfasinda VALID geciyor; kod filtresi metne bakmaz."""
    cluster.cluster_folder(_settings(ria, [["", "", "", "", "VALID", ""]]))
    assert not os.path.isdir(ria / "VALID")


def test_no_filters_and_no_phrases_copies_nothing(ria):
    summary = cluster.cluster_folder(_settings(ria))
    assert all(r.status == "no_match" for r in summary.results)


def test_the_wrong_prefix_reads_no_code(ria):
    cluster.cluster_folder(_settings(ria, [["", "", "", "", "ID", ""]],
                                     prefix="26437-LAB-"))
    assert not os.path.isdir(ria / "ID")


def test_preview_writes_nothing_to_disk(ria):
    summary = cluster.cluster_folder(_settings(ria, [["", "", "", "", "ID", ""]],
                                               dry_run=True))
    assert not os.path.isdir(ria / "ID")
    assert any(r.status == "preview" for r in summary.results)
