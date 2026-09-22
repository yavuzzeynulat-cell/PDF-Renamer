"""Kullanim kilavuzu -- ayri pencere DEGIL, ayni pencerede acilan bir sayfa.

Baslikta "How it works" baglantisina basilinca gelir, sekmelerden birine
basilinca gider. Boylece ekranda kalici hicbir sey kaplamaz: okumak
isteyen acar, isini bilen hic gormez.

Icerik canvas'a yazi olarak cizilir; sarma genisligi verildigi icin pencere
buyuyup kuculdukce satirlar yeniden akar.
"""
from __future__ import annotations

import theme

# Adimlar gercekten SIRALI oldugu icin numaralandiriliyor.
RENAME_STEPS = [
    "Pick the folder your scans are in, or drop PDFs straight onto the window.",
    "Check the code prefix. The example strip shows the name you will get.",
    "Press Preview. Nothing changes on disk; the table shows what would happen.",
    "Press Apply to rename in place. Undo reverts the whole last batch.",
]

CLUSTER_STEPS = [
    "Add the names you file by, one per line: B0051 Bridge, B0052 Tunnel.",
    "Pick the folder holding the PDFs. Group folders appear inside it.",
    "Press Preview to see which file lands in which group.",
    "Press Apply. Matched files are copied into every group they mention, "
    "then removed from the folder.",
]

NOTES = [
    ("Group by one place in the document number.",
     "Press Code filter. Paste a real number and the boxes follow its "
     "dashes: 26437-RIA-04C-DR-ID-00022 opens six. Fill only the place you "
     "care about -- ID in the fifth -- and leave the rest empty; an empty "
     "box means anything. Code filters run beside the group names above, "
     "never mixed with them: those search the page text, these read the "
     "document code. Code prefix decides which code is read and is the same "
     "box as on the Rename tab."),
    ("Turn OCR on for scanned PDFs.",
     "Scans have no text layer. OCR also loses spaces and letter case, so "
     "while it is on, group names match regardless of spacing and case. "
     "With it off, names must match exactly."),
    ("What stays in the folder is what still needs you.",
     "Matched files leave for the Recycle Bin once every copy is verified. "
     "Switch Move originals off if you would rather keep them."),
    ("Nothing is ever overwritten.",
     "If a name is already taken, the new file becomes name (1).pdf."),
    ("The results table is yours to keep.",
     "Filter it, search it, and press Export to save it as CSV. Double-click "
     "a row to open that PDF, right-click for more."),
]


class GuideTab:
    """Kilavuz sayfasi. gui.App tarafindan kurulur, o gizler/gosterir."""

    def __init__(self, app):
        self.app = app
        self.canvas = app.canvas
        self.cl, self.cr = app.cl, app.cr
        self._build()

    def _text(self, x, y, s, font, fill=theme.INK, width=None, anchor="nw"):
        return self.canvas.create_text(x, y, text=s, font=font, fill=fill,
                                       anchor=anchor, width=width or 0)

    def _steps(self, x, y, width, title, steps):
        """Basligi ve numarali adimlari cizer, biten y'yi dondurur."""
        self._text(x, y, title, theme.tkfont(13, "semibold"))
        y += 26
        for index, step in enumerate(steps, start=1):
            self._text(x, y, str(index), theme.tkfont(10, "bold"),
                       theme.ACCENT_HEX)
            item = self._text(x + 20, y, step, theme.tkfont(10), theme.SLATE,
                              width=width - 20)
            y = self.canvas.bbox(item)[3] + 12
        return y

    def _build(self):
        col = (self.cr - self.cl - 48) // 2
        left, right = self.cl, self.cl + col + 48

        self._text(self.cl, 104,
                   "Two jobs, one window. Rename gives a file its number; "
                   "Cluster puts it where it belongs.",
                   theme.tkfont(11), theme.SLATE,
                   width=self.cr - self.cl)

        top = 146
        end_left = self._steps(left, top, col, "Rename", RENAME_STEPS)
        end_right = self._steps(right, top, col, "Cluster", CLUSTER_STEPS)

        y = max(end_left, end_right) + 16
        self.app._tag(
            self.canvas.create_line(self.cl, y, self.cr, y, fill="#CFE0F2"),
            "lw")
        y += 18

        self._text(self.cl, y, "Worth knowing", theme.tkfont(13, "semibold"))
        y += 28
        # Baslik sutunu sabit 300px ve KENDISI DE sariliyor; uzun bir baslik
        # govde metninin ustune binmesin diye satir yuksekligi iki sutunun
        # buyugune gore hesaplaniyor.
        head_w, gap = 300, 24
        for heading, body in NOTES:
            left = self._text(self.cl, y, heading, theme.tkfont(10, "bold"),
                              width=head_w)
            right = self._text(self.cl + head_w + gap, y, body,
                               theme.tkfont(10), theme.SLATE,
                               width=self.cr - self.cl - head_w - gap)
            y = max(self.canvas.bbox(left)[3],
                    self.canvas.bbox(right)[3]) + 14
