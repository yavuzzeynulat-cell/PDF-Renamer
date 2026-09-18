"""Sonuc tablosunu diske yazar -- tercihen gercek bir Excel dosyasi.

Neden CSV yetmedi: CSV'de ayrac dosyanin degil, ACAN PROGRAMIN meselesi.
Excel hangi karakterin ayrac oldugunu Windows'un bolgesel ayarindan okur;
tutmazsa butun satir tek hucreye duser ve ortada tablo diye bir sey kalmaz.
Ustelik hucre icindeki bir noktali virgul (hata mesajlarinda sik) satiri
ortadan bolebiliyor.

.xlsx'te boyle bir belirsizlik yok: hucreler dosyanin icinde tanimli.
openpyxl bulunamazsa CSV'ye duseriz, ama o zaman da Excel'e ayraci acikca
soyleyen "sep=;" satirini basa yazariz.
"""
from __future__ import annotations

import csv
import os

# Durum sutunundaki degerlere gore satir rengi -- ekrandaki tabloyla ayni dil.
STATUS_FILLS = {
    "renamed": "DBF5E3",
    "restored": "DBF5E3",
    "preview": "DBF5E3",
    "copied": "DBF5E3",
    "moved": "DBF5E3",
    "already ok": "EDF1F5",
    "no match": "EDF1F5",
    "not found": "FFEAD6",
    "error": "FFD9D9",
}

_MIN_WIDTH = 10
_MAX_WIDTH = 70


def _column_width(header: str, values) -> float:
    longest = max([len(header)] + [len(str(v or "")) for v in values] or [0])
    return max(_MIN_WIDTH, min(_MAX_WIDTH, longest + 2))


def save_table(path: str, headers: list, rows: list,
               status_column: str = "Status", sheet_title: str = "Results"):
    """Tabloyu `path`e yazar. Uzanti .csv ise CSV, degilse .xlsx uretir."""
    if os.path.splitext(path)[1].lower() == ".csv":
        return _save_csv(path, headers, rows)
    return _save_xlsx(path, headers, rows, status_column, sheet_title)


def _save_xlsx(path, headers, rows, status_column, sheet_title):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    book = Workbook()
    sheet = book.active
    sheet.title = sheet_title

    sheet.append(list(headers))
    for row in rows:
        sheet.append(list(row))

    head_font = Font(bold=True, color="13283F")
    head_fill = PatternFill("solid", fgColor="E7F0FB")
    for cell in sheet[1]:
        cell.font = head_font
        cell.fill = head_fill
        cell.alignment = Alignment(vertical="center")

    # Durum sutununa gore satiri renklendir: ekranda hangi renkse o.
    try:
        status_at = list(headers).index(status_column)
    except ValueError:
        status_at = None
    if status_at is not None:
        for index, row in enumerate(rows, start=2):
            key = str(row[status_at] or "").strip().lower()
            color = STATUS_FILLS.get(key)
            if not color:
                continue
            fill = PatternFill("solid", fgColor=color)
            for column in range(1, len(headers) + 1):
                sheet.cell(row=index, column=column).fill = fill

    for index, header in enumerate(headers, start=1):
        values = [row[index - 1] if index - 1 < len(row) else "" for row in rows]
        sheet.column_dimensions[get_column_letter(index)].width = \
            _column_width(header, values)

    # Baslik hep gorunsun ve sutunlar suzulebilsin.
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = "A1:{0}{1}".format(
        get_column_letter(len(headers)), max(len(rows) + 1, 2))

    book.save(path)
    return path


def _save_csv(path, headers, rows):
    """Yedek yol. 'sep=;' satiri Excel'e ayraci acikca soyler."""
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        handle.write("sep=;\n")
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(list(headers))
        for row in rows:
            writer.writerow(list(row))
    return path
