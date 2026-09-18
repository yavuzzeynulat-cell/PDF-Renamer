"""Kumeleme penceresi -- yeniden adlandirmadan AYRI bir is.

Ana pencereden 'Cluster' dugmesiyle acilir ve kendi basina yasar; gui.py
akisina hic karismaz. Yaptigi is tek cumleyle: PDF metninde gecen kume
adlarini bulup dosyayi o adli klasorlere KOPYALAR. Dosya adi degismez,
orijinal yerinden oynamaz.

Butun karar mantigi grouper.py ve cluster.py icinde; burasi yalnizca sunum.
"""
from __future__ import annotations

import os
import queue
import subprocess
import threading
import traceback

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import ImageTk

import theme
import cluster
from config import Settings

# Yukseklik ana pencereyle ayni (770): %125 olcekli ekranda gorev cubuguna
# degmedigi zaten kanitli. Genislik iki sutun sigsin diye biraz daha dar.
W, H = 980, 770
CL, CR = 46, W - 46
FULLW = CR - CL
COL2 = 486                       # sag sutunun sol kenari
LIST_HINT = "Double-click a name to remove it"

STATUS_TAGS = {"copied": "ok", "preview": "ok", "no_match": "gray", "error": "err"}
STATUS_LABELS = {"copied": "Copied", "preview": "Preview",
                 "no_match": "No match", "error": "Error"}

_OPEN = None


def open_window(parent, prefs: dict, save_prefs) -> None:
    """Kumeleme penceresini acar; zaten acikse one getirir."""
    global _OPEN
    if _OPEN is not None and _OPEN.alive():
        _OPEN.focus()
        return
    _OPEN = ClusterWindow(parent, prefs, save_prefs)


class ClusterWindow:
    def __init__(self, parent, prefs: dict, save_prefs):
        self._prefs = prefs
        self._save_prefs = save_prefs
        self._imgrefs = []
        self._ui_queue = queue.Queue()
        self._running = False
        self._btn = {}
        self._cached_plan = None
        self._cached_sig = None

        self.top = tk.Toplevel(parent)
        self.top.title("Cluster PDFs")
        self.top.geometry(str(W) + "x" + str(H))
        self.top.resizable(False, False)
        self.top.transient(parent)

        self.canvas = tk.Canvas(self.top, width=W, height=H,
                                highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)

        self.tog_on = self._mk(theme.toggle_image(True))
        self.tog_off = self._mk(theme.toggle_image(False))

        self._draw_static()
        self._build_groups()
        self._build_folders()
        self._build_buttons()
        self._build_results()
        self._restore()
        self.top.after(100, self._drain_queue)

    # -- kucuk yardimcilar --------------------------------------------------
    def alive(self) -> bool:
        try:
            return bool(self.top.winfo_exists())
        except tk.TclError:
            return False

    def focus(self) -> None:
        self.top.lift()
        self.top.focus_force()

    def _mk(self, pil):
        img = ImageTk.PhotoImage(pil)
        self._imgrefs.append(img)
        return img

    def _text(self, x, y, s, f, fill=theme.INK, anchor="nw"):
        return self.canvas.create_text(x, y, text=s, font=f, fill=fill,
                                       anchor=anchor)

    def _cursor(self, item):
        self.canvas.tag_bind(item, "<Enter>",
                             lambda e: self.canvas.config(cursor="hand2"))
        self.canvas.tag_bind(item, "<Leave>",
                             lambda e: self.canvas.config(cursor=""))

    def _entry_kw(self):
        return dict(relief="flat", bd=0, highlightthickness=2,
                    highlightbackground="#C5D8EC",
                    highlightcolor=theme.ACCENT_HEX,
                    font=theme.tkfont(12), fg=theme.INK, bg="white",
                    insertbackground=theme.ACCENT_HEX)

    # -- sabit cizim --------------------------------------------------------
    def _draw_static(self):
        self.canvas.create_image(0, 0, anchor="nw",
                                 image=self._mk(theme.make_background(W, H)))
        self._text(CL, 32, "Cluster PDFs", theme.tkfont(21, "semibold"))
        self._text(CL, 64,
                   "Copy each PDF into folders named after the phrases it "
                   "contains  -  originals are never moved or renamed",
                   theme.tkfont(10), theme.SLATE)
        self.canvas.create_line(CL, 88, CR, 88, fill="#CFE0F2")

        self._text(CL, 104, "GROUP NAMES", theme.tkfont(9, "bold"), theme.SLATE)
        self._text(COL2, 104, "SOURCE FOLDER", theme.tkfont(9, "bold"), theme.SLATE)
        self._text(COL2, 170, "TARGET FOLDER  (group folders are created here)",
                   theme.tkfont(9, "bold"), theme.SLATE)

        self.canvas.create_line(CL, H - 40, CR, H - 40, fill="#DCE7F3")
        self._status_id = self._text(CL, H - 24, "Ready.", theme.tkfont(9),
                                     theme.SLATE, anchor="w")

    # -- kume adlari: ekle / sil / kaydir -----------------------------------
    def _build_groups(self):
        self.var_new = tk.StringVar()
        entry = tk.Entry(self.top, textvariable=self.var_new, **self._entry_kw())
        self.canvas.create_window(CL, 122, anchor="nw", window=entry,
                                  width=286, height=36)
        entry.bind("<Return>", lambda _e: self.on_add_group())
        self._entry_new = entry

        bid = self.canvas.create_image(
            CL + 300, 122, anchor="nw",
            image=self._mk(theme.button_image(146, 36, "+ Add name", "ghost")))
        self.canvas.tag_bind(bid, "<Button-1>", lambda _e: self.on_add_group())
        self._cursor(bid)

        # Liste sinirsiz sayida ad alir; tasarsa kaydirma cubugu cikar.
        frame = tk.Frame(self.top, bg="white", highlightthickness=1,
                         highlightbackground="#C5D8EC")
        self.listbox = tk.Listbox(
            frame, bg="white", fg=theme.INK, font=theme.tkfont(11),
            relief="flat", bd=0, highlightthickness=0, activestyle="none",
            selectbackground="#CFE3FF", selectforeground=theme.INK)
        vsb = ttk.Scrollbar(frame, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=vsb.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.canvas.create_window(CL, 170, anchor="nw", window=frame,
                                  width=400, height=176)
        self.listbox.bind("<Double-1>", lambda _e: self.on_remove_group())
        self.listbox.bind("<Delete>", lambda _e: self.on_remove_group())

        self._count_id = self._text(CL, 354, "", theme.tkfont(9), theme.SLATE)
        self._text(CL + 400, 354, LIST_HINT, theme.tkfont(9), theme.MUTED,
                   anchor="ne")

    def _build_folders(self):
        width = CR - COL2 - 118

        self.var_src = tk.StringVar()
        e1 = tk.Entry(self.top, textvariable=self.var_src, **self._entry_kw())
        self.canvas.create_window(COL2, 122, anchor="nw", window=e1,
                                  width=width, height=36)
        b1 = self.canvas.create_image(CR, 122, anchor="ne", image=self._mk(
            theme.button_image(108, 36, "Browse", "soft")))
        self.canvas.tag_bind(b1, "<Button-1>", lambda _e: self.on_browse_src())
        self._cursor(b1)

        self.var_dst = tk.StringVar()
        e2 = tk.Entry(self.top, textvariable=self.var_dst, **self._entry_kw())
        self.canvas.create_window(COL2, 188, anchor="nw", window=e2,
                                  width=width, height=36)
        b2 = self.canvas.create_image(CR, 188, anchor="ne", image=self._mk(
            theme.button_image(108, 36, "Browse", "soft")))
        self.canvas.tag_bind(b2, "<Button-1>", lambda _e: self.on_browse_dst())
        self._cursor(b2)

        # OCR dugmesi ayni zamanda ESLESTIRME KIPINI belirler; altindaki yazi
        # hangi kipte oldugunu acikca soyler ki kullanici tahmin etmesin.
        self.var_ocr = tk.BooleanVar(value=False)
        iid = self.canvas.create_image(COL2, 248, anchor="nw", image=self.tog_off)
        tid = self._text(COL2 + 52, 251, "OCR (scanned PDFs)", theme.tkfont(11))

        def flip(_e):
            if self._running:
                return
            self.var_ocr.set(not self.var_ocr.get())
            self.canvas.itemconfig(
                iid, image=self.tog_on if self.var_ocr.get() else self.tog_off)
            self._invalidate()
            self._paint_mode()

        for item in (iid, tid):
            self.canvas.tag_bind(item, "<Button-1>", flip)
            self._cursor(item)

        self._mode_id = self._text(COL2, 286, "", theme.tkfont(9), theme.ACCENT_HEX)
        self._paint_mode()

    def _paint_mode(self):
        """Eslestirmenin katiligini yaz -- kullanici tahmin etmek zorunda kalmasin."""
        if self.var_ocr.get():
            msg = "Matching: ignores spaces and letter case  (OCR output is messy)"
        else:
            msg = "Matching: exact  -  spaces and letter case must match"
        self.canvas.itemconfig(self._mode_id, text=msg)

    def _build_buttons(self):
        y = 380
        specs = [("preview", "Preview", "ghost", 150, self.on_preview),
                 ("apply", "Apply", "accent", 150, self.on_apply),
                 ("open", "Open target folder", "soft", 190, self.on_open_target)]
        x = CL
        for name, label, kind, w, cmd in specs:
            normal = self._mk(theme.button_image(w, 40, label, kind))
            disabled = self._mk(theme.button_image(w, 40, label, "disabled"))
            iid = self.canvas.create_image(x, y, anchor="nw", image=normal)
            self._btn[name] = (iid, normal, disabled)
            self.canvas.tag_bind(iid, "<Button-1>", lambda _e, c=cmd: c())
            self._cursor(iid)
            x += w + 14

        self.progress = ttk.Progressbar(
            self.top, style="Frost.Horizontal.TProgressbar", mode="determinate")
        self.canvas.create_window(CL, 434, anchor="nw", window=self.progress,
                                  width=FULLW, height=8)

    def _build_results(self):
        self._text(CL, 452, "RESULTS", theme.tkfont(9, "bold"), theme.SLATE)
        top = 476
        cols = ("file", "groups", "status", "msg")
        heads = ("File", "Groups", "Status", "Detail")
        widths = (270, 300, 100, FULLW - 270 - 300 - 100 - 18)
        frame = tk.Frame(self.top, bg="white", highlightthickness=1,
                         highlightbackground="#C5D8EC")
        self.tree = ttk.Treeview(frame, columns=cols, show="headings",
                                 style="Frost.Treeview", selectmode="browse")
        for col, head, wide in zip(cols, heads, widths):
            self.tree.heading(col, text=head)
            self.tree.column(col, width=wide, anchor="w")
        vsb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.canvas.create_window(CL, top, anchor="nw", window=frame,
                                  width=FULLW, height=H - top - 52)
        self.tree.tag_configure("ok", background="#DBF5E3")
        self.tree.tag_configure("gray", background="#EDF1F5")
        self.tree.tag_configure("err", background="#FFD9D9")

    # -- kalici tercihler ---------------------------------------------------
    def _restore(self):
        for name in self._prefs.get("cluster_phrases", []):
            self.listbox.insert("end", name)
        target = self._prefs.get("cluster_target", "")
        if target:
            self.var_dst.set(target)
        source = self._prefs.get("folder", "")
        if source and os.path.isdir(source):
            self.var_src.set(source)
        self._paint_count()

    def _remember(self):
        self._prefs["cluster_phrases"] = self._phrases()
        self._prefs["cluster_target"] = self.var_dst.get().strip()
        self._save_prefs(self._prefs)

    def _phrases(self) -> list:
        return list(self.listbox.get(0, "end"))

    def _paint_count(self):
        count = self.listbox.size()
        if count == 0:
            text = "No group names yet"
        elif count == 1:
            text = "1 group name"
        else:
            text = str(count) + " group names"
        self.canvas.itemconfig(self._count_id, text=text)

    # -- kume adi ekle / sil ------------------------------------------------
    def on_add_group(self):
        name = self.var_new.get().strip()
        if not name:
            return
        if name in self._phrases():          # ayni ad listede iki kez durmasin
            self.var_new.set("")
            self._set_status("'" + name + "' is already in the list.")
            return
        self.listbox.insert("end", name)
        self.var_new.set("")
        self._entry_new.focus_set()
        self._invalidate()
        self._paint_count()
        self._remember()

    def on_remove_group(self):
        selection = self.listbox.curselection()
        if not selection:
            return
        self.listbox.delete(selection[0])
        self._invalidate()
        self._paint_count()
        self._remember()

    # -- klasor secimi ------------------------------------------------------
    def on_browse_src(self):
        if self._running:
            return
        folder = filedialog.askdirectory(
            parent=self.top, title="Choose source folder",
            initialdir=self.var_src.get() or os.getcwd())
        if folder:
            self.var_src.set(folder)
            self._invalidate()

    def on_browse_dst(self):
        if self._running:
            return
        folder = filedialog.askdirectory(
            parent=self.top, title="Choose target folder",
            initialdir=self.var_dst.get() or os.getcwd())
        if folder:
            self.var_dst.set(folder)
            self._remember()

    def on_open_target(self):
        target = self.var_dst.get().strip()
        if not target or not os.path.isdir(target):
            messagebox.showinfo("Nothing to open",
                                "The target folder does not exist yet.",
                                parent=self.top)
            return
        try:
            os.startfile(target)
        except Exception:
            subprocess.Popen(["explorer", target])

    # -- calistirma ---------------------------------------------------------
    def _settings(self, dry_run: bool) -> Settings:
        return Settings(
            folder=self.var_src.get().strip(),
            target_folder=self.var_dst.get().strip(),
            phrases=self._phrases(),
            use_ocr=self.var_ocr.get(),
            all_pages=True,
            dry_run=dry_run,
        )

    def _sig(self, settings: Settings):
        """Onizleme onbelleginin Apply icin hala gecerli olup olmadiginin imzasi."""
        return (settings.effective_folder(), tuple(settings.phrases),
                settings.use_ocr, settings.all_pages)

    def _invalidate(self):
        self._cached_plan = None
        self._cached_sig = None

    def on_preview(self):
        if not self._running:
            self._run(dry_run=True)

    def on_apply(self):
        if self._running:
            return
        if messagebox.askyesno(
                "Confirm",
                "Files will be copied into the group folders.\n"
                "Originals stay where they are.\n\nContinue?",
                parent=self.top):
            self._run(dry_run=False)

    def _run(self, dry_run: bool):
        if not os.path.isdir(self.var_src.get().strip()):
            messagebox.showerror("Error", "Please choose a valid source folder.",
                                 parent=self.top)
            return
        if not self._phrases():
            messagebox.showerror("Error", "Add at least one group name.",
                                 parent=self.top)
            return
        if not self.var_dst.get().strip():
            messagebox.showerror("Error", "Please choose a target folder.",
                                 parent=self.top)
            return

        settings = self._settings(dry_run)
        overrides = None
        if (not dry_run and self._cached_plan is not None
                and self._sig(settings) == self._cached_sig):
            overrides = self._cached_plan

        if settings.use_ocr:
            import extractor
            if not extractor.ocr_available():
                messagebox.showwarning(
                    "OCR unavailable",
                    "OCR is enabled but no OCR engine was found, so scanned "
                    "(image-only) PDFs cannot be read.", parent=self.top)

        self._remember()
        self.tree.delete(*self.tree.get_children())
        self.progress.configure(value=0, maximum=100)
        self._set_running(True)
        self._set_status("Working...")
        threading.Thread(target=self._worker, args=(settings, overrides),
                         daemon=True).start()

    def _worker(self, settings, overrides=None):
        def progress(index, total, result):
            self._ui_queue.put(("progress", index, total, result))
        try:
            summary = cluster.cluster_folder(settings, progress,
                                             group_overrides=overrides)
            self._ui_queue.put(("done", summary, settings))
        except Exception as exc:
            self._ui_queue.put(("error", exc, traceback.format_exc()))

    def _drain_queue(self):
        if not self.alive():
            return
        try:
            while True:
                self._handle(self._ui_queue.get_nowait())
        except queue.Empty:
            pass
        finally:
            self.top.after(100, self._drain_queue)

    def _handle(self, msg):
        kind = msg[0]
        if kind == "progress":
            _, index, total, result = msg
            if total:
                self.progress.configure(maximum=total, value=index)
            self._add_row(result)
        elif kind == "done":
            self._on_done(msg[1], msg[2])
        elif kind == "error":
            self._on_error(msg[1], msg[2])

    def _add_row(self, result):
        self.tree.insert("", "end", values=(
            result.file_name,
            ", ".join(result.groups) if result.groups else "-",
            STATUS_LABELS.get(result.status, result.status),
            result.message,
        ), tags=(STATUS_TAGS.get(result.status, "gray"),))

    def _on_done(self, summary, settings):
        self._set_running(False)
        if settings.dry_run:
            self._cached_plan = summary.plan
            self._cached_sig = self._sig(settings)
            verb = "would be copied"
        else:
            self._invalidate()
            verb = "copied"
        self._set_status(
            "{0} of {1} file(s) matched  -  {2} copy(ies) {3}  -  "
            "{4} no match, {5} error(s)".format(
                summary.matched, summary.total, summary.copies, verb,
                summary.no_match, summary.errors))

    def _on_error(self, exc, tb):
        self._set_running(False)
        self._set_status("Failed.")
        messagebox.showerror("Error", str(exc) + "\n\n" + tb, parent=self.top)

    def _set_running(self, on: bool):
        self._running = on
        for _name, (iid, normal, disabled) in self._btn.items():
            self.canvas.itemconfig(iid, image=disabled if on else normal)

    def _set_status(self, text: str):
        self.canvas.itemconfig(self._status_id, text=text)
