"""Kod teshisi: "bir sey bulamiyor" dendiginde ilk bakilacak yer.

Klasordeki her PDF icin sirayla sunu yazar:

  1. metin okunabildi mi (kac karakter)
  2. verilen onekle kod BULUNABILDI mi
  3. bulunan kod kac parca ve hangi parcada ne var

Boylece sorunun nerede oldugu tek bakista gorunur: metin mi cikmiyor
(taranmis PDF, OCR gerekir), onek mi tutmuyor, yoksa aranan sey baska bir
parcada mi duruyor.

Kullanim:
    python kod_teshis.py "<klasor>" [onek]
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Konsol cp1252; desen tire varyantlarini iceriyor ve yazdirinca cokuyordu.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

import code_finder
import core
import extractor
from config import Settings


def main() -> int:
    if len(sys.argv) < 2:
        print('Kullanim: python kod_teshis.py "<klasor>" [onek]')
        return 1

    folder = sys.argv[1].strip('"').strip()
    prefix = sys.argv[2].strip() if len(sys.argv) > 2 else "26437-RIA-"

    if not os.path.isdir(folder):
        print("[HATA] Klasor yok:", folder)
        return 1

    settings = Settings(folder=folder, prefix=prefix, all_pages=True)
    pattern = settings.build_pattern()
    print("Klasor :", folder)
    print("Onek   :", prefix)
    print("Desen  :", pattern)
    print()

    pdfs = core.list_pdfs(folder)
    if not pdfs:
        print("[!] Klasorde hic PDF yok.")
        return 1

    found = 0
    sizes = {}
    for path in pdfs:
        name = os.path.basename(path)
        try:
            text = extractor.extract_text(path, all_pages=True, use_ocr=False)
        except Exception as exc:
            print("%-42s OKUNAMADI: %s" % (name[:42], exc))
            continue

        chars = len(text or "")
        code = code_finder.find_code(text, pattern, ignore_case=True)
        if not code:
            if chars == 0:
                print("%-42s metin YOK (taranmis olabilir; OCR gerekir)"
                      % name[:42])
            else:
                print("%-42s kod BULUNAMADI (%d karakter okundu)"
                      % (name[:42], chars))
                snippet = " ".join((text or "").split())[:70]
                print("%-42s   ilk satirlar: %s" % ("", snippet))
            continue

        found += 1
        parts = [p for p in code.split("-") if p]
        sizes[len(parts)] = sizes.get(len(parts), 0) + 1
        print("%-42s %s" % (name[:42], code))
        print("%-42s   %s" % ("", "  ".join(
            "%d:%s" % (i + 1, p) for i, p in enumerate(parts))))

    print()
    print("Kod bulunan: %d / %d dosya" % (found, len(pdfs)))
    if sizes:
        print("Parca sayilari:", ", ".join(
            "%d parca -> %d dosya" % (k, v) for k, v in sorted(sizes.items())))
        if len(sizes) > 1:
            print("[!] Parca sayisi DEGISIYOR. Kutu numaralari her belgede")
            print("    ayni seyi gostermez; filtreyi buna gore kur.")
    if found == 0:
        print("[!] Hicbir kod bulunamadi. Onek yanlis olabilir: yukaridaki")
        print("    'ilk satirlar' ciktisina bakip numaranin gercek basini yaz.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
