"""Central settings shared by all modules.

This file is owned by the coordinator. It now supports a user-friendly
`prefix` (the changeable "26437-LAB-" part) and a `suffix` (text appended
directly after the found document number, with no automatic space).
"""
from dataclasses import dataclass
import re

# Original V1 default prefix.
DEFAULT_PREFIX = "26437-LAB-"
# What follows the prefix inside the document (letters, digits, dashes).
CODE_BODY = r"[A-Z0-9-]+"
# Backwards-compatible full default pattern (identical to V1).
DEFAULT_PATTERN = DEFAULT_PREFIX + CODE_BODY

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
        return re.escape(p) + CODE_BODY
