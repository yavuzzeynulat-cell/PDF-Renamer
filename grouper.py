"""Kume adlarini (tumceleri) PDF metninde bulur.

Tek is: verilen metinde, kullanicinin yazdigi tumcelerden hangileri geciyor?
Dosya sistemine dokunmaz, PDF bilmez -- sadece metin.

Iki kip vardir ve ayrimi KULLANICI yapar (arayuzdeki OCR dugmesi):

  tolerant=False (OCR kapali)
      Metin katmani olan PDF'lerde bosluklar ve harf boyu guvenilirdir,
      bu yuzden birebir alt-dizge aranir. Yanlis eslesme riski en dusuk.

  tolerant=True (OCR acik)
      OCR bosluklari yiyor ve harf boyunu bozuyor; ornegin taranmis bir
      belgede "CORRIDOR 8 AND CORRIDOR 10D" metni
      "CORRIDOR8ANDCORRIDOR1OD" olarak cikiyor. Bu yuzden iki taraftan da
      TUM bosluklar silinir ve karsilastirma harf boyuna duyarsiz yapilir.
      Baska hicbir esneklik yoktur: bulanik/kismi eslesme yok.
"""
from __future__ import annotations

import code_finder


def _normalize(s: str) -> str:
    """Tum bosluklari (satir sonu dahil) silip harf boyunu esitler."""
    return "".join(s.split()).casefold()


def find_groups(text: str | None, phrases, *, tolerant: bool = False) -> list[str]:
    """`text` icinde gecen tumceleri dondurur.

    Donen adlar KULLANICININ yazdigi haliyle gelir (belgedeki haliyle degil),
    cunku klasor adi olarak kullanilacaklar. Sira, belgedeki sira degil,
    `phrases` listesindeki siradir; boylece cikti tahmin edilebilir olur.
    Ayni tumce listede iki kez varsa bir kez dondurulur.
    """
    if not text or not phrases:
        return []

    haystack = str(text)
    if tolerant:
        haystack = _normalize(haystack)

    found: list[str] = []
    seen: set[str] = set()

    for raw in phrases:
        phrase = str(raw).strip() if raw else ""
        if not phrase or phrase in seen:
            continue  # bos satirlar her dosyaya eslesmemeli
        needle = _normalize(phrase) if tolerant else phrase
        if needle and needle in haystack:
            seen.add(phrase)
            found.append(phrase)

    return found


# ---------------------------------------------------------------------------
# Kod segmentiyle eslestirme
#
# find_groups tumceyi METNIN tamaminda arar. Belge numarasinin bir bolumunu
# aramak icin bu yetersiz: "ID" yazinca "VALID", "GRID", "IDENTIFICATION"
# gibi kelimelere de takilir. Asagidaki kip yalnizca BELGE KODUNA bakar ve
# terimi tam segment(ler) olarak arar.
# ---------------------------------------------------------------------------

def _segments(code: str) -> list[str]:
    """Kodu tirelerden boler; bos parcalari atar.

    code_finder.find_code tire varyantlarini (en-dash vb.) normal tireye
    cevirdigi icin burada tek ayirac yeter.
    """
    return [part for part in code.split("-") if part]


def _contains_run(haystack: list[str], needle: list[str]) -> bool:
    """`needle`, `haystack` icinde ARDISIK ve SIRALI bir dizi mi?

    Ardisiklik sart: "RIA-ID" istendiginde 26437-RIA-04C-DR-ID-00022
    eslesmemeli, cunku aradaki 04C-DR atlanmis olur -- kullanici oyle bir
    bolum yazmadi.
    """
    if not needle or len(needle) > len(haystack):
        return False
    last = len(haystack) - len(needle)
    return any(haystack[i:i + len(needle)] == needle
               for i in range(last + 1))


def find_code_segments(text: str | None, terms, pattern: str,
                       *, ignore_case: bool = True) -> list[str]:
    """Belge kodunun segmentleri icinde gecen terimleri dondurur.

    `pattern` disaridan gelir: kod numaralari degisir (26437-RIA- bugun,
    26437-LAB- yarin) ve deseni kullanicinin yazdigi onekten kuran yer
    Settings.build_pattern(). Burasi yalnizca eslestirmeyi bilir.

    Metinde birden fazla kod varsa ILKI kullanilir -- yeniden adlandirma da
    ilk kodu kullaniyor, dosyanin adi ile girdigi klasor boylece ayni koddan
    gelir.

    Donen adlar KULLANICININ yazdigi haliyle gelir (klasor adi olacaklar) ve
    sira `terms` listesindeki siradir; boylece cikti tahmin edilebilir kalir.
    """
    if not text or not terms:
        return []

    try:
        code = code_finder.find_code(text, pattern, ignore_case=ignore_case)
    except ValueError:
        return []          # bozuk desen: kumeleme cokmesin
    if not code:
        return []

    have = _segments(code)
    if ignore_case:
        have = [s.casefold() for s in have]

    found: list[str] = []
    seen: set[str] = set()

    for raw in terms:
        term = str(raw).strip() if raw else ""
        if not term or term in seen:
            continue        # bos satirlar her dosyaya eslesmemeli
        want = _segments(term)
        if ignore_case:
            want = [s.casefold() for s in want]
        if _contains_run(have, want):
            seen.add(term)
            found.append(term)

    return found
