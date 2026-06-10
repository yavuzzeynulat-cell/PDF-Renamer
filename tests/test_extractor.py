"""extractor modulu testleri.

tests/sample_pdfs/ altindaki ornek PDF'leri kullanir. OCR (Tesseract) kurulu
degilse ilgili dogrulamalar guvenli sekilde atlanir.
"""
import os
import sys

import pytest

# Proje kokunu import yoluna ekle (extractor.py kok dizinde).
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import extractor  # noqa: E402

SAMPLES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample_pdfs")


def sample(name: str) -> str:
    return os.path.join(SAMPLES, name)


def test_text_kod_first_page():
    """Duz metindeki kod bulunmali."""
    text = extractor.extract_text(sample("01_text_kod.pdf"))
    assert "26437-LAB-001" in text


def test_kod_sayfa2_all_pages_true():
    """2. sayfadaki kod, all_pages=True ile bulunmali."""
    text = extractor.extract_text(sample("02_kod_sayfa2.pdf"), all_pages=True)
    assert "26437-LAB-205" in text


def test_kod_sayfa2_all_pages_false():
    """all_pages=False ile yalnizca 1. sayfa taranir; kod bulunmamali."""
    text = extractor.extract_text(sample("02_kod_sayfa2.pdf"), all_pages=False)
    assert "26437-LAB-205" not in text


def test_kodsuz():
    """Kodsuz belgede metin var ama lab kodu yok."""
    text = extractor.extract_text(sample("03_kodsuz.pdf"))
    assert text.strip() != ""
    assert "26437-LAB" not in text


def test_taranmis_no_ocr_empty():
    """Image-only PDF, OCR'siz bos/bosluk dondurmeli."""
    text = extractor.extract_text(sample("05_taranmis.pdf"), use_ocr=False)
    assert text.strip() == ""


def test_taranmis_use_ocr_does_not_raise():
    """use_ocr=True cagrisi, Tesseract olmasa bile hata firlatmamali."""
    text = extractor.extract_text(sample("05_taranmis.pdf"), use_ocr=True)
    # OCR mevcutsa kodu icermeli; degilse sessizce bos doner.
    if extractor.ocr_available():
        assert "26437-LAB-777" in text
    else:
        assert text.strip() == ""
