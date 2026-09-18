"""Sonuc tablosunu Excel'e duzgun bir tablo olarak cikarma.

Eskiden CSV yaziliyordu ve ayrac olarak noktali virgul kullaniliyordu.
Excel'in ayraci BOLGESEL AYARDAN geliyor: tutmazsa butun satir tek hucreye
dusuyor ve tablo diye bir sey kalmiyor. Ayrica hucre icinde noktali virgul
gecen bir metin (hata mesajlari gibi) satiri ortadan bolebiliyor.

Gercek bir .xlsx yazinca bu belirsizligin tamami ortadan kalkar: hucreler
dosyanin kendisinde tanimli, ayrac diye bir kavram yok.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

openpyxl = pytest.importorskip("openpyxl")

import exporter  # noqa: E402

HEADERS = ["File", "New name", "Status", "Detail"]
ROWS = [
    ["scan1.pdf", "26437-LAB-001.pdf", "Renamed", "Renamed to 26437-LAB-001.pdf"],
    ["scan2.pdf", "", "Error", "Could not read file: broken; code 5, denied"],
    ["scan3.pdf", "", "Not found", "No document code found."],
]


def _sheet(path):
    return openpyxl.load_workbook(path).active


def test_every_value_lands_in_its_own_cell(tmp_path):
    out = tmp_path / "r.xlsx"
    exporter.save_table(str(out), HEADERS, ROWS)
    ws = _sheet(out)
    assert [c.value for c in ws[1]] == HEADERS
    assert [c.value for c in ws[2]] == ROWS[0]


def test_a_semicolon_inside_a_value_does_not_split_the_row(tmp_path):
    """CSV'nin asil kirildigi yer buydu."""
    out = tmp_path / "r.xlsx"
    exporter.save_table(str(out), HEADERS, ROWS)
    ws = _sheet(out)
    assert ws.cell(row=3, column=4).value == ROWS[1][3]
    assert ws.max_column == len(HEADERS)


def test_the_row_count_matches_what_was_given(tmp_path):
    out = tmp_path / "r.xlsx"
    exporter.save_table(str(out), HEADERS, ROWS)
    ws = _sheet(out)
    assert ws.max_row == len(ROWS) + 1        # + baslik satiri


def test_the_header_stays_visible_while_scrolling(tmp_path):
    out = tmp_path / "r.xlsx"
    exporter.save_table(str(out), HEADERS, ROWS)
    assert _sheet(out).freeze_panes == "A2"


def test_the_table_can_be_filtered(tmp_path):
    out = tmp_path / "r.xlsx"
    exporter.save_table(str(out), HEADERS, ROWS)
    assert _sheet(out).auto_filter.ref is not None


def test_columns_are_wide_enough_to_read(tmp_path):
    """Varsayilan genislikte uzun Detail sutunu '####' gibi kirpik durur."""
    out = tmp_path / "r.xlsx"
    exporter.save_table(str(out), HEADERS, ROWS)
    ws = _sheet(out)
    assert ws.column_dimensions["D"].width > ws.column_dimensions["C"].width


def test_the_header_row_is_emphasised(tmp_path):
    out = tmp_path / "r.xlsx"
    exporter.save_table(str(out), HEADERS, ROWS)
    assert _sheet(out)["A1"].font.bold is True


def test_an_empty_table_still_produces_a_usable_sheet(tmp_path):
    out = tmp_path / "r.xlsx"
    exporter.save_table(str(out), HEADERS, [])
    ws = _sheet(out)
    assert [c.value for c in ws[1]] == HEADERS
    assert ws.max_row == 1


def test_a_csv_path_still_writes_csv(tmp_path):
    """Kullanici .csv secerse istedigini alir; ayrac belirsizligi olmasin
    diye Excel'e ayraci soyleyen satir basa yazilir."""
    out = tmp_path / "r.csv"
    exporter.save_table(str(out), HEADERS, ROWS)
    text = out.read_text(encoding="utf-8-sig")
    assert text.startswith("sep=;")
    assert "scan1.pdf" in text
