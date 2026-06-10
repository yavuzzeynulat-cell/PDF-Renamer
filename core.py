"""Orkestrasyon katmani (KOORDINATOR yonetir).

extractor + code_finder + renamer modullerini birlestirir. GUI ve CLI
yalnizca buradaki process_folder / Summary / FileResult arayuzunu kullanir.

Mevcut V1 davranisi KORUNUR: varsayilan desen ayni, "once duz metin sonra
tablo" onceligi extractor tarafindan korunuyor, ve bir koddan birden fazla
dosya cikarsa numarali (' (1)', ' (2)') cozum uygulanir.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Optional
import os

from config import Settings
import extractor
import code_finder
import renamer


# ---- KARARLI VERI SOZLESMESI (GUI/CLI buna guvenebilir) --------------------

@dataclass
class FileResult:
    old_name: str                 # Islem oncesi dosya adi
    new_name: Optional[str]       # Yeni ad (yoksa None)
    code: Optional[str]           # Bulunan kod (yoksa None)
    status: str                   # 'renamed' | 'already' | 'not_found' | 'error' | 'preview'
    message: str                  # Kullaniciya gosterilecek aciklama


@dataclass
class Summary:
    results: list[FileResult] = field(default_factory=list)
    renamed: int = 0
    already: int = 0
    not_found: int = 0
    errors: int = 0
    # Onizlemede bulunan kodlar: tam-yol -> kod (yoksa None).
    # Apply asamasinda tekrar OCR/cikarim yapmamak icin yeniden kullanilir.
    plan: dict = field(default_factory=dict)

    @property
    def total(self) -> int:
        return len(self.results)


# progress(index, total, FileResult) seklinde cagrilir; GUI ilerleme cubugu icin.
ProgressCallback = Callable[[int, int, FileResult], None]


def list_pdfs(folder: str, recursive: bool = False) -> list[str]:
    """Klasordeki PDF dosyalarinin TAM YOLLARINI dondurur."""
    out: list[str] = []
    if recursive:
        for root, _dirs, files in os.walk(folder):
            for f in files:
                if f.lower().endswith(".pdf"):
                    out.append(os.path.join(root, f))
    else:
        for f in os.listdir(folder):
            p = os.path.join(folder, f)
            if os.path.isfile(p) and f.lower().endswith(".pdf"):
                out.append(p)
    return sorted(out)


def process_one(pdf_path: str, settings: Settings,
                code_overrides: Optional[dict] = None) -> FileResult:
    """Tek bir PDF'i isler ve bir FileResult dondurur (yeniden adlandirma dahil).

    `code_overrides` verilirse ve bu yol icin kayit varsa, metin cikarimi ve
    kod arama (OCR dahil) atlanir; kod dogrudan override'dan alinir. Bu sayede
    Onizleme'de bulunan kodlar Apply'da yeniden hesaplanmaz.
    """
    folder = os.path.dirname(pdf_path)
    old_name = os.path.basename(pdf_path)

    if code_overrides is not None and pdf_path in code_overrides:
        # Onizlemede bulunan kodu yeniden kullan: extract + find atlanir.
        code = code_overrides[pdf_path]
    else:
        # Aranan kodu, metin biriktikce kontrol eden hizli bir eslestirici kur.
        # Boylece extractor kod bulundugu an durur (pahali tablo/sayfa taramasi
        # atlanir). Desen gecersizse matcher None birakilir; gecersizlik hatasi
        # asagidaki find_code tarafindan duzgun sekilde raporlanir.
        import re
        pattern = settings.build_pattern()
        try:
            _rx = re.compile(pattern, re.IGNORECASE if settings.ignore_case else 0)
            matcher = lambda s: _rx.search(s) is not None  # noqa: E731
        except re.error:
            matcher = None

        # 1) Extract text (preserves V1 precedence + all pages + optional OCR)
        try:
            text = extractor.extract_text(
                pdf_path,
                all_pages=settings.all_pages,
                use_ocr=settings.use_ocr,
                ocr_lang=settings.ocr_lang,
                match=matcher,
            )
        except Exception as exc:  # corrupt / unreadable PDF
            return FileResult(old_name, None, None, "error",
                              f"Could not read file: {exc}")

        # 2) Find the code (prefix-based pattern + case option)
        try:
            code = code_finder.find_code(
                text, settings.build_pattern(), ignore_case=settings.ignore_case)
        except ValueError as exc:  # invalid regex
            return FileResult(old_name, None, None, "error",
                              f"Invalid code pattern: {exc}")

    if not code:
        return FileResult(old_name, None, None, "not_found",
                          "No document code found.")

    # 3) Safe rename (numbered conflict resolution + dry-run).
    #    The suffix is attached directly to the code (no automatic space).
    new_base = code_finder.clean_filename(code + settings.suffix) + ".pdf"
    outcome = renamer.safe_rename(folder, old_name, new_base,
                                  dry_run=settings.dry_run)

    if outcome.status == "already":
        return FileResult(old_name, outcome.new_name, code, "already",
                          "Already named correctly.")
    if outcome.status == "error":
        return FileResult(old_name, None, code, "error", outcome.message)

    # outcome.status == "renamed"
    if settings.dry_run:
        return FileResult(old_name, outcome.new_name, code, "preview",
                          f"Will become '{outcome.new_name}'")
    return FileResult(old_name, outcome.new_name, code, "renamed",
                      f"Renamed to '{outcome.new_name}'")


def process_folder(settings: Settings,
                   progress: Optional[ProgressCallback] = None,
                   code_overrides: Optional[dict] = None) -> Summary:
    """Klasordeki tum PDF'leri isler ve Summary dondurur.

    Basarili (gercek) yeniden adlandirmalar, GERI ALMA icin her dosyanin
    bulundugu klasore log olarak yazilir (dry_run'da yazilmaz).
    """
    folder = settings.effective_folder()
    summary = Summary()

    paths = list_pdfs(folder, recursive=settings.recursive)
    total = len(paths)

    # Geri-alma logu icin: her klasor icin (eski, yeni) ciftleri
    log_by_folder: dict[str, list[tuple[str, str]]] = {}

    for index, path in enumerate(paths, start=1):
        result = process_one(path, settings, code_overrides=code_overrides)
        # Apply asamasinda yeniden kullanmak icin bulunan kodu kaydet (None dahil).
        summary.plan[path] = result.code

        if result.status in ("renamed", "preview"):
            summary.renamed += 1
            if result.status == "renamed" and result.new_name:
                fdir = os.path.dirname(path)
                log_by_folder.setdefault(fdir, []).append(
                    (result.old_name, result.new_name))
        elif result.status == "already":
            summary.already += 1
        elif result.status == "not_found":
            summary.not_found += 1
        else:  # error
            summary.errors += 1

        summary.results.append(result)
        if progress is not None:
            progress(index, total, result)

    # Geri-alma logunu yaz (yalnizca gercek degisiklikler)
    if not settings.dry_run:
        for fdir, entries in log_by_folder.items():
            if entries:
                renamer.write_log(fdir, entries)

    return summary
