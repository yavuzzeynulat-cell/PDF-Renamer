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


def _segments(code: str) -> list[str]:
    """Kodu tirelerden boler; bos parcalari atar.

    code_finder.find_code tire varyantlarini (en-dash vb.) normal tireye
    cevirdigi icin burada tek ayirac yeter.
    """
    return [part for part in code.split("-") if part]


# ---------------------------------------------------------------------------
# Kod filtresi: tire tire, YER bazli eslestirme
#
# Kullanicinin modeli: RIA numarasi sabit sayida "bilgi yeri"nden olusur ve
# o yalnizca birini umursar, gerisi degisken.
#
#     26437 - RIA - 04C - DR - ID - 00022
#       1      2     3     4    5     6
#
# "5. yerde ID olsun, gerisi fark etmez" = yalnizca o kutuyu doldur.
#
# Bir onceki deneme (find_code_segments) terimi kodun HERHANGI bir yerinde
# ariyordu ve yer bilgisini tasimiyordu; kullanici "tireler arasini edit
# yaparsam eslesmeli" deyince dogru modelin bu oldugu anlasildi.
# ---------------------------------------------------------------------------

def _codes_in(text, pattern: str, ignore_case: bool) -> list:
    """Metindeki tum kodlar. Bozuk desen kumelemeyi cokturmez."""
    try:
        return code_finder.find_all_codes(text, pattern,
                                          ignore_case=ignore_case)
    except ValueError:
        return []


def _slots_fit(parts, filled, ignore_case: bool) -> bool:
    """Dolu kutularin hepsi bu kodda kendi yerinde tutuyor mu?"""
    for index, want in filled:
        if index >= len(parts):
            return False   # filtre kodun sonunu asiyor
        have = parts[index]
        if ignore_case:
            if have.casefold() != want.casefold():
                return False
        elif have != want:
            return False
    return True


def match_code_slots(text: str | None, slots, pattern: str,
                     *, ignore_case: bool = True) -> str:
    """Dolu kutularin hepsi kendi yerinde tutuyorsa klasor adini doner.

    `slots` kutu degerleridir; BOS kutu jokerdir. Hicbiri dolu degilse ""
    doner -- bos bir filtre her dosyaya eslesmemeli.

    Klasor adi, dolu kutularin tire ile birlestirilmis halidir
    (ornek: 4. ve 5. kutu dolu -> "DR-ID").
    """
    if not text or not slots:
        return ""

    filled = [(i, str(v).strip()) for i, v in enumerate(slots)
              if v is not None and str(v).strip()]
    if not filled:
        return ""

    # Belgedeki TUM kodlara bakilir: bir belge kendi numarasinin yaninda
    # atif verdigi baskalarini da tasiyabilir ve aranan parca onlardan
    # birinde olabilir. Bir filtre TEK bir kodda tutmali -- yoksa
    # aralarinda iliski olmayan iki numarayi birlestirmis oluruz.
    for code in _codes_in(text, pattern, ignore_case):
        parts = _segments(code)
        if _slots_fit(parts, filled, ignore_case):
            return "-".join(want for _, want in filled)
    return ""


def match_code_anywhere(text: str | None, values, pattern: str,
                        *, ignore_case: bool = True) -> str:
    """Verilen degerlerin HEPSI kodda geciyorsa klasor adini doner.

    Yer onemsizdir. Gerekcesi: ayni projede
    26437-RIA-04C-DR-ID-00022 (ID 5. yerde) ve
    26437-RIA-04C-DR-PR2-ID-00003 (ID 6. yerde) birlikte bulunuyor -- kutu
    numarasina bagli kalmak bu belgelerin yarisini kaciriyordu.

    Tam SEGMENT aranir: "VALID" icindeki ID sayilmaz.
    """
    if not text or not values:
        return ""

    wanted = [str(v).strip() for v in values if v is not None and str(v).strip()]
    if not wanted:
        return ""

    need = [s.casefold() for s in wanted] if ignore_case else list(wanted)
    for code in _codes_in(text, pattern, ignore_case):
        have = _segments(code)
        if ignore_case:
            have = [s.casefold() for s in have]
        if all(s in have for s in need):
            return "-".join(wanted)
    return ""


def slots_of(f) -> list:
    """Bir filtrenin kutu degerleri.

    Filtre iki bicimde olabilir: duz liste (yer bazli, eski kayitlar) ya da
    {"slots": [...], "anywhere": bool}. Ikisi de okunur.
    """
    if isinstance(f, dict):
        return list(f.get("slots") or [])
    return list(f or [])


def is_anywhere(f) -> bool:
    """Bu filtre yerden bagimsiz mi aransin?"""
    return bool(isinstance(f, dict) and f.get("anywhere"))
