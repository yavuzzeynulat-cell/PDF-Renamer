"""Tests for grouper.py: kume adlarini (tumceleri) PDF metninde bulma.

Iki kip vardir ve ayrimi KULLANICI belirler (OCR dugmesi):
  tolerant=False  -> metin katmani guvenilir: birebir eslesme
  tolerant=True   -> OCR: bosluklari yiyor ve harf boyunu bozuyor
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from grouper import find_groups  # noqa: E402

PHRASES = ["B0051 Bridge", "B0052 Tunnel", "C0100 Viaduct"]


# -- birebir kip (OCR kapali) ------------------------------------------------

def test_exact_phrase_is_found():
    assert find_groups("Report for B0051 Bridge, section 2", PHRASES) == ["B0051 Bridge"]


def test_text_without_any_phrase_returns_empty():
    assert find_groups("Nothing relevant here", PHRASES) == []


def test_strict_mode_is_case_sensitive():
    assert find_groups("REPORT FOR B0051 BRIDGE", PHRASES) == []


def test_strict_mode_requires_the_space():
    # OCR bosluk yer; birebir kipte bu eslesmemeli.
    assert find_groups("B0051Bridge", PHRASES) == []


# -- toleransli kip (OCR acik) -----------------------------------------------

def test_tolerant_matches_when_ocr_ate_the_space():
    assert find_groups("B0051Bridge", PHRASES, tolerant=True) == ["B0051 Bridge"]


def test_tolerant_matches_uppercase():
    assert find_groups("REPORT FOR B0051 BRIDGE", PHRASES, tolerant=True) == ["B0051 Bridge"]


def test_tolerant_matches_across_a_line_break():
    assert find_groups("B0051\nBridge", PHRASES, tolerant=True) == ["B0051 Bridge"]


def test_tolerant_matches_doubled_spaces():
    assert find_groups("B0051   Bridge", PHRASES, tolerant=True) == ["B0051 Bridge"]


def test_tolerant_still_rejects_a_different_code():
    assert find_groups("B0059 Bridge", PHRASES, tolerant=True) == []


# -- coklu eslesme ve sira ---------------------------------------------------

def test_every_matching_phrase_is_returned():
    text = "Covers C0100 Viaduct and B0051 Bridge"
    assert find_groups(text, PHRASES) == ["B0051 Bridge", "C0100 Viaduct"]


def test_order_follows_the_phrase_list_not_the_document():
    text = "C0100 Viaduct appears before B0051 Bridge"
    assert find_groups(text, PHRASES) == ["B0051 Bridge", "C0100 Viaduct"]


def test_returned_name_is_the_users_spelling_not_the_documents():
    # Klasor adi kullanicinin yazdigi gibi olmali, belgedeki gibi degil.
    assert find_groups("b0051bridge", PHRASES, tolerant=True) == ["B0051 Bridge"]


# -- bozuk / kenar girdiler --------------------------------------------------

def test_empty_text_returns_empty():
    assert find_groups("", PHRASES) == []


def test_none_text_returns_empty():
    assert find_groups(None, PHRASES) == []


def test_blank_entries_in_the_list_are_ignored():
    # Kullanici listede bos satir birakirsa her dosya eslesmemeli.
    assert find_groups("anything at all", ["", "   ", "B0051 Bridge"]) == []


def test_a_phrase_listed_twice_is_reported_once():
    assert find_groups("B0051 Bridge", ["B0051 Bridge", "B0051 Bridge"]) == ["B0051 Bridge"]


def test_no_phrases_returns_empty():
    assert find_groups("B0051 Bridge", []) == []
