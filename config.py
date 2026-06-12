"""Central settings shared by all modules.

This file is owned by the coordinator. It now supports a user-friendly
`prefix` (the changeable "26437-LAB-" part) and a `suffix` (text appended
directly after the found document number, with no automatic space).
"""
from dataclasses import dataclass
import re

# Original V1 default prefix.
DEFAULT_PREFIX = "26437-LAB-"

# Bazi belgeler kodlarda normal tire (-, U+002D) yerine en-dash (–),
# em-dash (—), kisa cizgi vb. KULLANIR ve pdfminer bunlari oldugu gibi
# cikarir. Bu yuzden onek/kod icindeki "tire"yi bu varyantlara TOLERANSLI
# eslestiririz; aksi halde "26437–LAB–..." gibi kodlar hic bulunmaz.
# (Bulunan kod, dosya adina yazilirken code_finder tarafindan normal tireye
#  geri normalize edilir; boylece dosya adlari tutarli kalir.) Normal tireli
# belgelerde davranis BIREBIR ayni kalir.
DASH_VARIANTS = "‐‑‒–—―−�"
# Herhangi bir tire/cizgi turunu eslestiren karakter sinifi ("-" sona konur).
_DASH_CLASS = "[" + DASH_VARIANTS + "-]"
# What follows the prefix inside the document (letters, digits, dashes/variants).
CODE_BODY = "[A-Z0-9" + DASH_VARIANTS + "-]+"
# Backwards-compatible full default pattern (tire'ye toleransli; normal tireli
# belgelerde V1 ile birebir ayni eslesir).
DEFAULT_PATTERN = "26437" + _DASH_CLASS + "LAB" + _DASH_CLASS + CODE_BODY

DEFAULT_OCR_LANG = "tur+eng"


@dataclass
class Settings:
    folder: str = ""                    # Folder to process (empty = current dir)
    prefix: str = DEFAULT_PREFIX        # Document-code prefix to search for
    suffix: str = ""                    # Text appended after the code (no space)
    pattern: str = ""                   # Advanced: full regex override (optional)
    ignore_case: bool = True            # Case-insensitive search
    all_pages: bool = True              # Scan every page (False = first page only)
    use_ocr: bool = False               # OCR for scanned PDFs (only runs when a
                                        # page has no text layer; self-contained
                                        # RapidOCR engine, no extra install).
                                        # Default off; the GUI exposes a toggle.
    ocr_lang: str = DEFAULT_OCR_LANG    # OCR language(s)
    recursive: bool = False             # Also scan subfolders
    dry_run: bool = False               # Preview only: don't modify files

    def effective_folder(self) -> str:
        import os
        return self.folder or os.getcwd()

    def build_pattern(self) -> str:
        """Return the regex to search for.

        An explicit `pattern` (advanced) wins; otherwise the pattern is built
        from `prefix` + the standard code body. An empty prefix falls back to
        the original default so we never match random text.
        """
        if self.pattern.strip():
            return self.pattern
        p = self.prefix.strip()
        if not p:
            return DEFAULT_PATTERN
        # Onekteki her "tire"yi (kullanicinin yazdigi normal -) tum tire/cizgi
        # varyantlarina toleransli hale getir: oneki tirelerden bol, parcalari
        # guvenle escape et, aralarina dash-sinifini koy. Boylece "26437-LAB-"
        # oneki belgedeki "26437–LAB–..." (en-dash) kodunu da yakalar. Tiresiz
        # onekte sonuc, eski davranisla birebir aynidir.
        parts = re.split("[" + DASH_VARIANTS + "-]", p)
        return _DASH_CLASS.join(re.escape(part) for part in parts) + CODE_BODY
