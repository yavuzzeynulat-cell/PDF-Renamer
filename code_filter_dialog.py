"""Kod filtresi penceresi -- Cluster sekmesindeki dugmeye basinca acilir.

Kullanicinin modeli su: belge numarasi sabit sayida "bilgi yeri"nden olusur
ve o yalnizca birini (ya da birkacini) umursar, gerisi degisken.

    26437 - RIA - 04C - DR - ID - 00022
      1      2     3     4    5     6

Bu pencere o yerleri KUTU KUTU gosterir. Umursadigini doldurur, gerisini bos
birakir; bos kutu jokerdir. Kutu sayisi sabit degil -- kullanicinin
yapistirdigi ornek numaradan cikar, cunku numaralar 6 da 7 de parca olabilir.

Metin kumeleriyle (Group names) hic karismaz: onlar sayfa metninde aranir,
bunlar belge kodunda. Ayri yerden yonetilmelerinin sebebi de bu; tek listede
karistirilinca kullanici hangisinin ne yaptigini takip edemiyordu.

Saf yardimcilar (hints_from_sample, filter_label, summary, is_usable) Tk'siz
calisir ve ayri sinanir; Tk yalnizca `open_dialog` icinde.
"""
from __future__ import annotations

import re

import config
import grouper

# Tire varyantlari (en-dash vb.) normal tire gibi ayirir; bazi PDF'ler
# kodlarda bunlari kullaniyor ve kullanici oradan kopyalayip yapistirabilir.
_SPLIT = re.compile("[" + config.DASH_VARIANTS + "-]")

MAX_SUMMARY = 70


def hints_from_sample(sample) -> list:
    """Ornek numaradan kutu ipuclari. Bos parcalar atilir."""
    if not sample:
        return []
    return [p for p in _SPLIT.split(str(sample).strip()) if p]


slots_of = grouper.slots_of
is_anywhere = grouper.is_anywhere


def filter_label(f) -> str:
    """Filtrenin adi = dolu kutularin tire ile birlesimi ("DR-ID")."""
    slots = slots_of(f)
    if not slots:
        return ""
    return "-".join(str(v).strip() for v in slots
                    if v is not None and str(v).strip())


def is_usable(f) -> bool:
    """En az bir kutusu dolu mu?

    Hepsi bos bir filtre HER dosyaya eslesirdi; sessizce butun klasoru
    toplamasin diye eklenmesine izin verilmez.
    """
    return bool(filter_label(f))


def has_work(phrases, filters) -> bool:
    """Calistirmak icin elimizde bir sey var mi?

    Ikisinden BIRI yeter. Kontrol eskiden yalnizca metin listesine bakiyordu
    ve kod filtresi ekleyen kullaniciya "Add at least one group name" deyip
    yolu kesiyordu -- ozellik vardi ama onunden gecilemiyordu.
    """
    if any(str(p).strip() for p in (phrases or []) if p):
        return True
    return any(is_usable(f) for f in (filters or []))


def summary(filters) -> str:
    """Ana sekmede gorunen tek satirlik ozet."""
    names = [filter_label(f) for f in (filters or []) if is_usable(f)]
    if not names:
        return "No code filter."
    line = "Code filter: " + ", ".join(names)
    if len(line) > MAX_SUMMARY:
        line = line[:MAX_SUMMARY - 1].rstrip(", ") + "…"
    return line


# ---------------------------------------------------------------------------
# Pencere
# ---------------------------------------------------------------------------

def open_dialog(parent, prefix: str, filters, sample: str = ""):
    """Filtreleri duzenlemek icin pencereyi acar.

    Kapatilinca yeni filtre listesini doner; Cancel'da None.
    """
    import tkinter as tk
    from tkinter import ttk
    import theme

    current = [dict(f) if isinstance(f, dict) else list(f)
               for f in (filters or [])]
    result = {"value": None}

    win = tk.Toplevel(parent)
    win.title("Code filter")
    win.configure(bg="#F4F9FF")
    win.resizable(False, False)
    win.transient(parent)

    pad = {"padx": 18}

    tk.Label(win, text="Paste a real document number. The boxes follow it.",
             bg="#F4F9FF", fg=theme.SLATE, font=theme.tkfont(9),
             anchor="w").pack(fill="x", pady=(16, 6), **pad)

    var_sample = tk.StringVar(value=sample or (prefix + "04C-DR-ID-00022"))
    tk.Entry(win, textvariable=var_sample, relief="flat", bd=0,
             highlightthickness=2, highlightbackground="#C5D8EC",
             highlightcolor=theme.ACCENT_HEX, font=theme.tkfont(11),
             fg=theme.INK, bg="white").pack(fill="x", ipady=7, **pad)

    tk.Label(win, text="Fill only the places you care about. "
                       "Empty box = anything.",
             bg="#F4F9FF", fg=theme.SLATE, font=theme.tkfont(9),
             anchor="w").pack(fill="x", pady=(16, 6), **pad)

    boxes = tk.Frame(win, bg="#F4F9FF")
    boxes.pack(fill="x", **pad)
    slot_vars: list = []

    # Kutular satira bolunur. Tek sirada dizilince pencere kutu sayisiyla
    # birlikte suresiz genisliyordu: olculdu, 9 kutu 826 px; yanlis bir
    # yapistirma ekrani asabilirdi.
    PER_ROW = 7

    def rebuild(*_args):
        for child in boxes.winfo_children():
            child.destroy()
        slot_vars.clear()
        hints = hints_from_sample(var_sample.get())
        for i, hint in enumerate(hints):
            var = tk.StringVar()
            slot_vars.append(var)
            row_no, col = divmod(i, PER_ROW)
            cell = tk.Frame(boxes, bg="#F4F9FF")
            cell.grid(row=row_no, column=col * 2, pady=3)
            tk.Label(cell, text=str(i + 1), bg="#F4F9FF", fg=theme.MUTED,
                     font=theme.tkfont(8)).pack()
            entry = tk.Entry(cell, textvariable=var, width=8, justify="center",
                             relief="flat", bd=0, highlightthickness=2,
                             highlightbackground="#DCE9F8",
                             highlightcolor=theme.ACCENT_HEX,
                             font=theme.tkfont(11), fg=theme.INK, bg="white")
            entry.pack(ipady=5)
            tk.Label(cell, text=hint, bg="#F4F9FF", fg=theme.MUTED,
                     font=theme.tkfont(8)).pack()
            if i < len(hints) - 1 and col < PER_ROW - 1:
                tk.Label(boxes, text="–", bg="#F4F9FF", fg="#C5D8EC",
                         font=theme.tkfont(12)).grid(row=row_no, column=col * 2 + 1,
                                                     padx=3)

    var_sample.trace_add("write", rebuild)
    rebuild()

    listbox = tk.Listbox(win, height=5, relief="flat", bd=0,
                         highlightthickness=1, highlightbackground="#C5D8EC",
                         font=theme.tkfont(10), fg=theme.INK, bg="white",
                         activestyle="none")
    status = tk.Label(win, text="", bg="#F4F9FF", fg=theme.ACCENT_HEX,
                      font=theme.tkfont(9), anchor="w")

    def refresh_list():
        listbox.delete(0, "end")
        for f in current:
            listbox.insert("end", filter_label(f)
                           + ("   · anywhere" if is_anywhere(f) else ""))

    def on_add():
        slots = [v.get().strip() for v in slot_vars]
        if not is_usable(slots):
            status.config(text="Fill at least one box first.")
            return
        item = ({"slots": slots, "anywhere": True} if var_any.get()
                else slots)
        current.append(item)
        refresh_list()
        status.config(text="Added: " + filter_label(item)
                      + (" (anywhere)" if var_any.get() else ""))
        for v in slot_vars:
            v.set("")

    def on_remove():
        sel = listbox.curselection()
        if not sel:
            return
        del current[sel[0]]
        refresh_list()
        status.config(text="")

    # Yer sabit degil: ayni projede ID kimi belgede 5., kimindeyse 6.
    # parcada duruyor. Kutu numarasina bagli kalmak o belgelerin yarisini
    # kaciriyordu, bu yuzden yerden bagimsiz arama secenegi var.
    var_any = tk.BooleanVar(value=False)
    tk.Checkbutton(win, variable=var_any, bg="#F4F9FF", fg=theme.INK,
                   activebackground="#F4F9FF", selectcolor="white",
                   font=theme.tkfont(10), anchor="w",
                   text="Position does not matter "
                        "(find these anywhere in the code)").pack(
        fill="x", pady=(14, 0), **pad)

    row = tk.Frame(win, bg="#F4F9FF")
    row.pack(fill="x", pady=(8, 4), **pad)
    ttk.Button(row, text="Add filter", command=on_add).pack(side="left")
    ttk.Button(row, text="Remove selected",
               command=on_remove).pack(side="left", padx=8)

    status.pack(fill="x", pady=(2, 8), **pad)
    tk.Label(win, text="FILTERS", bg="#F4F9FF", fg=theme.SLATE,
             font=theme.tkfont(9, "bold"), anchor="w").pack(fill="x", **pad)
    listbox.pack(fill="x", pady=(4, 0), **pad)
    refresh_list()

    def on_ok():
        result["value"] = [dict(f) if isinstance(f, dict) else list(f)
                           for f in current]
        win.destroy()

    def on_cancel():
        result["value"] = None
        win.destroy()

    foot = tk.Frame(win, bg="#F4F9FF")
    foot.pack(fill="x", pady=16, **pad)
    ttk.Button(foot, text="Cancel", command=on_cancel).pack(side="right")
    ttk.Button(foot, text="OK", command=on_ok).pack(side="right", padx=8)

    win.protocol("WM_DELETE_WINDOW", on_cancel)
    win.update_idletasks()
    x = parent.winfo_rootx() + (parent.winfo_width() - win.winfo_width()) // 2
    y = parent.winfo_rooty() + 90
    win.geometry("+{0}+{1}".format(max(x, 0), max(y, 0)))
    win.grab_set()
    parent.wait_window(win)
    return result["value"]
