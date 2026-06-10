"""Tests for the code_finder module."""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from code_finder import DEFAULT_PATTERN, clean_filename, find_code


# Original reference implementation, kept here to prove identical default behavior.
def _kodu_bul_original(metin):
    match = re.search(r"26437-LAB-[A-Z0-9-]+", metin)
    if match:
        return match.group(0)
    return None


def _temiz_dosya_adi_original(metin):
    return re.sub(r'[\\/*?:"<>|]', "", str(metin)).strip()


def test_basic_match():
    assert find_code("Document No: 26437-LAB-001 ...") == "26437-LAB-001"


def test_case_sensitivity_default():
    assert find_code("26437-lab-309") is None


def test_case_insensitive_matches_lowercase():
    assert find_code("26437-lab-309", ignore_case=True) == "26437-lab-309"


def test_no_match_returns_none():
    assert find_code("no code here") is None


def test_none_text_returns_none():
    assert find_code(None) is None


def test_empty_text_returns_none():
    assert find_code("") is None


def test_custom_pattern():
    assert find_code("INV-2026-42", r"INV-\d{4}-\d+") == "INV-2026-42"


def test_invalid_pattern_raises_valueerror():
    with pytest.raises(ValueError):
        find_code("anything", "[")


def test_clean_filename_removes_illegal_chars():
    assert clean_filename("26437:LAB/001?") == "26437LAB001"


def test_trailing_hyphen_polish():
    assert find_code("code 26437-LAB-001- end") == "26437-LAB-001"


def test_trailing_hyphen_polish_does_not_change_clean_match():
    assert find_code("26437-LAB-001") == "26437-LAB-001"


@pytest.mark.parametrize(
    "text",
    [
        "Document No: 26437-LAB-001 page 2",
        "26437-LAB-ABC-123 trailing",
        "prefix 26437-LAB-309 suffix",
        "no code here",
        "26437-lab-309 lowercase",
        "26437-LAB-",
    ],
)
def test_default_behavior_matches_original(text):
    # With the DEFAULT pattern and ignore_case=False, behavior must be
    # identical to the original kodu_bul (modulo the documented trailing
    # hyphen polish, which only affects matches ending in '-').
    original = _kodu_bul_original(text)
    new = find_code(text, DEFAULT_PATTERN)
    if original is not None and original.endswith("-"):
        assert new == original.rstrip("-")
    else:
        assert new == original


@pytest.mark.parametrize(
    "name",
    ['26437:LAB/001?', 'a\\b*c"d<e>f|g', "  spaced  ", "normal_name.pdf"],
)
def test_clean_filename_matches_original(name):
    assert clean_filename(name) == _temiz_dosya_adi_original(name)
