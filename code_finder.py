"""Locate document codes in text and sanitize Windows filenames.

This generalizes the original `kodu_bul` / `temiz_dosya_adi` helpers so the
search pattern is configurable and matching can be case-insensitive, while
keeping the proven default behavior identical.
"""

import re

DEFAULT_PATTERN: str = r"26437-LAB-[A-Z0-9-]+"

# Characters that are illegal in Windows filenames.
_ILLEGAL_FILENAME_CHARS = re.compile(r'[\\/*?:"<>|]')

# Tire/cizgi varyantlari (en-dash, em-dash, kisa cizgi, eksi, bozuk-decode
# yer tutucusu). Bazi PDF'ler kodlarda normal tire yerine bunlari kullanir;
# bulunan kodu dosya adina yazmadan once hepsini NORMAL tire'ye ceviririz ki
# dosya adlari tutarli olsun. Normal tireli kodlar degismeden kalir.
_DASH_VARIANTS = re.compile("[‐‑‒–—―−�]")


def find_code(
    text: str, pattern: str = DEFAULT_PATTERN, *, ignore_case: bool = False
) -> str | None:
    """Return the first regex match of ``pattern`` in ``text``, or ``None``.

    If ``ignore_case`` is True the pattern is matched case-insensitively.
    Returns ``None`` for falsy/``None`` text. Raises ``ValueError`` if
    ``pattern`` is not a valid regular expression.
    """
    if not text:
        return None

    flags = re.IGNORECASE if ignore_case else 0
    try:
        match = re.search(pattern, str(text), flags)
    except re.error as exc:
        raise ValueError(f"Invalid regex pattern {pattern!r}: {exc}") from exc

    if match is None:
        return None

    # Tire/cizgi varyantlarini normal tire'ye normalize et (dosya adi tutarli
    # olsun). Normal tireli kodlar degismez.
    code = _DASH_VARIANTS.sub("-", match.group(0))

    # Safety polish: drop a single trailing hyphen or whitespace left by a
    # greedy match (e.g. "26437-LAB-001-"). Never strips alphanumerics, so
    # matches like "26437-LAB-001" are unchanged.
    return code.rstrip("- \t\r\n") or None


def clean_filename(name: str) -> str:
    """Remove characters illegal in Windows filenames and trim whitespace."""
    return _ILLEGAL_FILENAME_CHARS.sub("", str(name)).strip()
