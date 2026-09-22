"""code_filter_dialog.py: kod filtresi penceresinin saf mantigi.

Pencerenin kendisi Tk; burada sinanan, Tk'siz calisan karar parcalari:
ornek numaradan kac kutu acilacagi ve bir filtrenin listede nasil yazilacagi.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import code_filter_dialog as dlg  # noqa: E402


# -- ornekten kutular --------------------------------------------------------

def test_the_sample_decides_how_many_boxes_open():
    assert dlg.hints_from_sample("26437-RIA-04C-DR-ID-00022") == [
        "26437", "RIA", "04C", "DR", "ID", "00022"]


def test_a_seven_part_number_opens_seven_boxes():
    """Kullanici 7 bilgi yeri olabilecegini soyledi; sayi sabit degil."""
    assert len(dlg.hints_from_sample("26437-RIA-11A-CA-SP-A-00470")) == 7


def test_dash_variants_split_the_same_way():
    assert dlg.hints_from_sample("26437–RIA–04C") == ["26437", "RIA", "04C"]


def test_spaces_around_the_sample_are_ignored():
    assert dlg.hints_from_sample("  26437-RIA-04C  ") == ["26437", "RIA", "04C"]


def test_an_empty_sample_gives_no_boxes():
    assert dlg.hints_from_sample("") == []
    assert dlg.hints_from_sample(None) == []


def test_empty_pieces_are_dropped():
    assert dlg.hints_from_sample("26437--RIA-") == ["26437", "RIA"]


# -- filtrenin yazilisi ------------------------------------------------------

def test_a_filter_is_named_after_its_filled_boxes():
    assert dlg.filter_label(["", "", "", "", "ID", ""]) == "ID"
    assert dlg.filter_label(["", "", "", "DR", "ID", ""]) == "DR-ID"


def test_an_empty_filter_has_no_name():
    assert dlg.filter_label(["", "", ""]) == ""
    assert dlg.filter_label([]) == ""


def test_the_label_keeps_the_users_letter_case():
    assert dlg.filter_label(["", "id", ""]) == "id"


# -- filtre ozeti (ana sekmede gorunen satir) --------------------------------

def test_the_summary_says_none_when_there_are_no_filters():
    assert dlg.summary([]) == "No code filter."


def test_the_summary_names_a_single_filter():
    assert dlg.summary([["", "", "", "", "ID", ""]]) == "Code filter: ID"


def test_the_summary_lists_several():
    got = dlg.summary([["", "ID"], ["", "CA"]])
    assert "ID" in got and "CA" in got


def test_the_summary_does_not_run_off_the_panel():
    """Cok filtre varsa satir kisaltilir; panel genisligi sabit."""
    many = [["", "F%d" % i] for i in range(12)]
    assert len(dlg.summary(many)) <= 70


# -- bos filtre eklenmemeli --------------------------------------------------

def test_an_all_empty_filter_is_rejected():
    """Hicbir kutusu dolu olmayan filtre HER dosyaya eslesirdi."""
    assert dlg.is_usable(["", "", ""]) is False
    assert dlg.is_usable([]) is False


def test_a_filter_with_one_box_is_usable():
    assert dlg.is_usable(["", "", "ID"]) is True


# -- calisacak bir sey var mi --------------------------------------------

def test_a_code_filter_alone_is_enough_to_run():
    """GERCEK HATA: kullanici 2. yere RIA, 5. yere ID yazip filtreyi
    ekledi; program yine "Add at least one group name" deyip calismayi
    reddetti. Kontrol yalnizca metin listesine bakiyordu, kod filtrelerini
    hic saymiyordu -- yani ozellik eklendi ama onunden gecilemiyordu."""
    assert dlg.has_work([], [["", "RIA", "", "", "ID", ""]]) is True


def test_a_text_name_alone_is_enough():
    assert dlg.has_work(["B0051 Bridge"], []) is True


def test_both_together_are_fine():
    assert dlg.has_work(["B0051 Bridge"], [["", "ID"]]) is True


def test_nothing_at_all_blocks_the_run():
    assert dlg.has_work([], []) is False


def test_an_empty_filter_does_not_count_as_work():
    """Hicbir kutusu dolu olmayan filtre zaten eklenemez; sayilmamali."""
    assert dlg.has_work([], [["", "", ""]]) is False


def test_blank_names_do_not_count():
    assert dlg.has_work(["", "   "], []) is False


# -- acma/kapama -------------------------------------------------------------
#
# Filtreleri silmeden beklemeye almak icin. Silip yeniden kurmak, birkac
# kutulu bir filtre icin gereksiz is.

def test_filters_are_ignored_while_switched_off():
    saved = [["", "", "", "", "ID", ""]]
    assert dlg.active_filters(saved, False) == []


def test_filters_are_used_while_switched_on():
    saved = [["", "", "", "", "ID", ""]]
    assert dlg.active_filters(saved, True) == saved


def test_switching_off_does_not_discard_them():
    """Kapatmak silmek degil: liste oldugu gibi durur."""
    saved = [["", "ID"]]
    dlg.active_filters(saved, False)
    assert saved == [["", "ID"]]


def test_a_switched_off_filter_is_not_work_to_do():
    assert dlg.has_work([], dlg.active_filters([["", "ID"]], False)) is False


def test_the_summary_says_when_it_is_off():
    assert dlg.summary([["", "ID"]], enabled=False) == "Code filter: off"


def test_the_summary_still_names_them_when_on():
    assert "ID" in dlg.summary([["", "ID"]], enabled=True)
