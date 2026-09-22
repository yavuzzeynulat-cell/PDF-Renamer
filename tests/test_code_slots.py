"""grouper.match_code_slots: belge kodunu tire tire eslestirme.

Kullanicinin modeli su: RIA numarasi sabit sayida "bilgi yeri"nden olusur ve
o yalnizca BIR (ya da birkac) yeri umursar, gerisi degisken.

    26437 - RIA - 04C - DR - ID - 00022
      1      2     3     4    5     6

"5. yerde ID olsun, gerisi fark etmez" demek icin yalnizca o kutuyu doldurur.
Bos kutu = joker. Dolu kutularin HEPSI kendi yerinde tutmali.

Onceki deneme (find_code_segments) terimi kodun HERHANGI bir yerinde ariyordu;
kullanici "tireler arasini edit yaparsam eslesmeli" deyince yer bazli olmasi
gerektigi anlasildi.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import grouper  # noqa: E402
from config import Settings  # noqa: E402

RIA = Settings(prefix="26437-RIA-").build_pattern()
TEXT = "Kapak sayfasi\n26437-RIA-04C-DR-ID-00022\nVALID until 2027"


def hit(slots, text=TEXT, pattern=RIA):
    return grouper.match_code_slots(text, slots, pattern)


# -- tutanlar ----------------------------------------------------------------

def test_one_slot_filled_the_rest_are_wildcards():
    assert hit(["", "", "", "", "ID", ""]) == "ID"


def test_two_slots_must_both_hold():
    assert hit(["", "", "", "DR", "ID", ""]) == "DR-ID"


def test_folder_name_joins_only_the_filled_slots():
    assert hit(["", "RIA", "", "", "ID", ""]) == "RIA-ID"


def test_a_slot_anywhere_works():
    assert hit(["26437", "", "", "", "", ""]) == "26437"
    assert hit(["", "", "", "", "", "00022"]) == "00022"


def test_letter_case_is_ignored():
    assert hit(["", "", "", "", "id", ""]) == "id"


def test_dash_variants_in_the_document_still_line_up():
    text = "26437–RIA–04C–DR–ID–00022"
    assert grouper.match_code_slots(text, ["", "", "", "", "ID", ""], RIA) == "ID"


# -- tutmayanlar -------------------------------------------------------------

def test_a_filled_slot_that_differs_fails_the_whole_filter():
    assert hit(["", "", "", "CA", "ID", ""]) == ""


def test_the_position_matters():
    """ID 5. yerde; 4. yere yazilirsa tutmaz. Eski surum burada tutuyordu."""
    assert hit(["", "", "", "ID", "", ""]) == ""


def test_part_of_a_slot_does_not_count():
    assert hit(["", "", "", "", "I", ""]) == ""
    assert hit(["", "", "", "", "", "0002"]) == ""


def test_all_slots_empty_matches_nothing():
    """Bos filtre her dosyaya eslesmemeli."""
    assert hit(["", "", "", "", "", ""]) == ""
    assert hit([]) == ""


def test_a_slot_past_the_end_of_the_code_fails():
    """Filtre 7 yer bekliyor ama belgede 6 var."""
    assert hit(["", "", "", "", "", "", "X"]) == ""


def test_no_code_in_the_text_means_no_match():
    assert hit(["", "", "", "", "ID", ""], text="Kodsuz sayfa") == ""


def test_empty_text_is_safe():
    assert hit(["", "", "", "", "ID", ""], text="") == ""
    assert grouper.match_code_slots(None, ["", "ID"], RIA) == ""


def test_the_page_text_is_never_consulted():
    """VALID sayfada geciyor ama kodun disinda; hic bakilmaz."""
    assert hit(["", "", "", "", "VALID", ""]) == ""


# -- onek degisebilir --------------------------------------------------------

def test_the_prefix_decides_which_code_is_read():
    lab = Settings(prefix="26437-LAB-").build_pattern()
    text = "26437-LAB-04C-DR-ID-00022"
    assert grouper.match_code_slots(text, ["", "", "", "", "ID", ""], lab) == "ID"
    assert grouper.match_code_slots(text, ["", "", "", "", "ID", ""], RIA) == ""


# -- degisken uzunluk --------------------------------------------------------

def test_a_seven_part_code_is_fine():
    text = "26437-RIA-11A-CA-SP-A-00470"
    assert grouper.match_code_slots(text, ["", "", "", "", "SP", "", ""], RIA) == "SP"


def test_a_shorter_filter_still_checks_its_own_slots():
    """Filtre 5 yer sayiyorsa 6. yere bakmaz."""
    text = "26437-RIA-04C-DR-ID-00022"
    assert grouper.match_code_slots(text, ["", "", "", "", "ID"], RIA) == "ID"


# -- yeri fark etmesin -------------------------------------------------------
#
# Yer sabit degil: ayni projede 26437-RIA-04C-DR-ID-00022 (ID 5. yerde) ve
# 26437-RIA-04C-DR-PR2-ID-00003 (ID 6. yerde) birlikte bulunuyor. Kutu
# numarasina bagli kalmak bu yuzden kirilgan; kullanicinin en bastan beri
# sordugu sey de "kodunda ID gecenleri grupla" idi.

def anywhere(values, text=TEXT, pattern=RIA):
    return grouper.match_code_anywhere(text, values, pattern)


def test_a_value_is_found_wherever_it_sits():
    assert anywhere(["ID"]) == "ID"
    assert anywhere(["ID"], text="26437-RIA-04C-DR-PR2-ID-00003") == "ID"


def test_several_values_must_all_be_present():
    assert anywhere(["DR", "ID"]) == "DR-ID"
    assert anywhere(["DR", "ID"], text="26437-RIA-04C-CA-SP-00470") == ""


def test_order_does_not_matter_here():
    """Yer onemsizse sira da onemsiz."""
    assert anywhere(["ID", "DR"]) == "ID-DR"


def test_a_partial_word_still_does_not_match():
    assert anywhere(["I"]) == ""
    assert anywhere(["VALID"]) == ""


def test_letter_case_is_ignored_too():
    assert anywhere(["id"]) == "id"


def test_nothing_to_look_for_matches_nothing():
    assert anywhere([]) == ""
    assert anywhere(["", "  "]) == ""


def test_no_code_means_no_match():
    assert anywhere(["ID"], text="Kodsuz sayfa") == ""


# -- belgede birden fazla kod ------------------------------------------------
#
# Bir belge birkac RIA numarasi tasiyabiliyor (kendi numarasi + atif verdigi
# baskalari). Eskiden yalnizca ILK kod okunuyordu: aranan parca ikinci
# koddaysa dosya hic bulunamiyordu.

MULTI = ("Kapak\n26437-RIA-04C-DR-PR2-SP-00003\n"
         "Atif: 26437-RIA-11A-CA-ID-00471\nson")


def test_a_later_code_is_read_too():
    assert grouper.match_code_anywhere(MULTI, ["ID"], RIA) == "ID"


def test_a_later_code_works_for_slots_as_well():
    assert grouper.match_code_slots(MULTI, ["", "", "", "", "ID", ""], RIA) == "ID"


def test_the_first_code_still_matches():
    assert grouper.match_code_anywhere(MULTI, ["SP"], RIA) == "SP"


def test_one_filter_may_not_span_two_codes():
    """SP 1. kodda, ID 2. kodda. Bir filtre TEK kodda tutmali; yoksa
    aralarinda hicbir iliski olmayan iki numarayi birlestirmis oluruz."""
    assert grouper.match_code_anywhere(MULTI, ["SP", "ID"], RIA) == ""


def test_still_nothing_when_no_code_matches():
    assert grouper.match_code_anywhere(MULTI, ["ZZZ"], RIA) == ""
