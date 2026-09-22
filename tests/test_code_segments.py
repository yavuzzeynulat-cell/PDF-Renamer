"""grouper.find_code_segments: belge KODUNUN icinde segment dizisi arama.

Kumeleme bugune kadar tumceyi METNIN tamaminda ariyordu. RIA numaralarini
gruplamak icin bu yetmiyor: "ID" yazinca "VALID", "GRID", "IDENTIFICATION"
gibi kelimelere de takiliyor.

Bu kip farkli: once belge kodu bulunur (26437-RIA-04C-DR-ID-00022), tirelerden
bolunur ve kullanicinin yazdigi terim, segmentler icinde ARDISIK ve SIRALI bir
dizi olarak araniyor mu diye bakilir. Boylece "ID" tam segmenti yakalar,
"04C-DR-ID" de ucluyu birden.

Kod numaralari degisir (RIA -> LAB), bu yuzden desen disaridan verilir:
cagiran taraf Settings.build_pattern() ile kullanicinin yazdigi onekten kurar.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import grouper  # noqa: E402
from config import Settings  # noqa: E402

RIA = Settings(prefix="26437-RIA-").build_pattern()
TEXT = "Sayfa basligi\n26437-RIA-04C-DR-ID-00022\nalt bilgi"


def find(terms, text=TEXT, pattern=RIA):
    return grouper.find_code_segments(text, terms, pattern)


# -- eslesenler --------------------------------------------------------------

def test_a_single_segment_matches():
    assert find(["ID"]) == ["ID"]


def test_a_run_of_segments_matches():
    """Kullanicinin asil istedigi: 04C-DR-ID bolumunu bir butun olarak."""
    assert find(["04C-DR-ID"]) == ["04C-DR-ID"]


def test_a_shorter_run_matches_too():
    assert find(["DR-ID"]) == ["DR-ID"]


def test_the_first_and_last_segments_are_reachable():
    assert find(["26437"]) == ["26437"]
    assert find(["00022"]) == ["00022"]


def test_the_whole_code_matches_itself():
    assert find(["26437-RIA-04C-DR-ID-00022"]) == ["26437-RIA-04C-DR-ID-00022"]


# -- eslesmeyenler -----------------------------------------------------------

def test_a_gapped_run_does_not_match():
    """RIA ile ID arasinda 04C-DR var: ardisik degil."""
    assert find(["RIA-ID"]) == []


def test_a_reversed_run_does_not_match():
    assert find(["ID-DR"]) == []


def test_part_of_a_segment_does_not_match():
    """Asil derdimiz buydu: VALID icindeki ID'ye takilmamak."""
    assert find(["VALID"]) == []
    assert find(["0002"]) == []
    assert find(["D"]) == []


def test_a_segment_only_elsewhere_in_the_page_does_not_match():
    """Kodun DISINDAKI metne hic bakilmaz."""
    text = "GRID-ID-5 basligi\n26437-RIA-04C-DR-CA-00022\n"
    assert grouper.find_code_segments(text, ["ID"], RIA) == []


def test_no_code_in_the_text_means_no_match():
    assert find(["ID"], text="Kodsuz bir sayfa") == []


def test_empty_input_is_safe():
    assert find(["ID"], text="") == []
    assert find([]) == []
    assert grouper.find_code_segments(None, ["ID"], RIA) == []


# -- liste hijyeni -----------------------------------------------------------

def test_blank_terms_are_skipped():
    """Bos satir her dosyaya eslesmemeli."""
    assert find(["", "   ", "ID"]) == ["ID"]


def test_a_term_of_only_dashes_is_skipped():
    assert find(["-", "---"]) == []


def test_surrounding_dashes_are_ignored():
    """Kullanici '-ID-' yazabilir; niyeti belli."""
    assert find(["-ID-"]) == ["-ID-"]


def test_a_repeated_term_is_returned_once():
    assert find(["ID", "ID"]) == ["ID"]


def test_the_order_follows_the_users_list_not_the_code():
    """Klasor adlari tahmin edilebilir olsun diye."""
    assert find(["ID", "26437", "DR"]) == ["ID", "26437", "DR"]


# -- kod bicimindeki varyasyonlar --------------------------------------------

def test_matching_ignores_letter_case():
    assert find(["id"]) == ["id"]
    assert find(["04c-dr-id"]) == ["04c-dr-id"]


def test_dash_variants_in_the_document_still_match():
    """Bazi PDF'ler tire yerine en-dash kullaniyor; code_finder bunlari
    normal tireye cevirir, biz de segmentleri dogru boleriz."""
    text = "26437–RIA–04C–DR–ID–00022"
    assert grouper.find_code_segments(text, ["04C-DR-ID"], RIA) == ["04C-DR-ID"]


# -- onek degisebilir --------------------------------------------------------

def test_the_prefix_decides_which_codes_are_read():
    """RIA'dan LAB'a gecis: kod degistirmeye gerek yok, onek yeter."""
    lab_text = "26437-LAB-04C-DR-ID-00022"
    lab = Settings(prefix="26437-LAB-").build_pattern()
    assert grouper.find_code_segments(lab_text, ["ID"], lab) == ["ID"]
    # RIA deseniyle ayni metin hic okunmaz.
    assert grouper.find_code_segments(lab_text, ["ID"], RIA) == []
