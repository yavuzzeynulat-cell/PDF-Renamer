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
