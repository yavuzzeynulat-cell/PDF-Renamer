"""Kumeleme sekmesi -- ANA pencerenin icinde yasar, ayri pencere acmaz.

Widget'larini gui.py'in canvas'ina cizer; sekme degisince gui.py bunlari
gizler/gosterir. Boylece tek pencere, tek gorev cubugu girdisi olur.

Yaptigi is: PDF metninde gecen kume adlarini bulup dosyayi o adli klasorlere
KOPYALAR. Dosya adi degismez, orijinal yerinden oynamaz. Butun karar mantigi
grouper.py ve cluster.py icinde; burasi yalnizca sunum.
"""
from __future__ import annotations

import os
import queue
import subprocess
import threading
import traceback

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import theme
import cluster
import exporter
from config import Settings

STATUS_TAGS = {"copied": "ok", "preview": "ok", "no_match": "gray", "error": "err"}
STATUS_LABELS = {"copied": "Copied", "preview": "Preview",
                 "no_match": "No match", "error": "Error"}


class ClusterTab:
    """Kumeleme sekmesinin butun arayuzu. gui.App tarafindan kurulur."""

    def __init__(self, app):
        self.app = app
        self.root = app.root
        self.canvas = app.canvas
        self.cl, self.cr = app.cl, app.cr

        # Iki sutun: solda kullanicinin bakimini yaptigi liste, sagda klasorler.
        self.lw = 468                       # sol sutun genisligi
        self.rx = self.cl + self.lw + 40    # sag sutunun sol kenari
        self.rw = self.cr - self.rx

        self._queue: "queue.Queue[tuple]" = queue.Queue()
        self._running = False
        self._btn = {}
        self._cached_plan = None
        self._cached_sig = None
        self._counts = {}                   # kume adi -> kopya sayisi

        self._build()
        self._restore()
        self.root.after(120, self._drain)

    # -- kisa yardimcilar ---------------------------------------------------
    def _text(self, x, y, s, f, fill=theme.INK, anchor="nw", width=None):
        """Canvas yazisi. `width` verilirse o genislikte SARILIR; uzun
        aciklamalar pencere kenarindan tasmaz."""
        return self.canvas.create_text(x, y, text=s, font=f, fill=fill,
                                       anchor=anchor,
                                       width=width if width else 0)

    def _entry_kw(self):
        return dict(relief="flat", bd=0, highlightthickness=2,
                    highlightbackground="#C5D8EC",
                    highlightcolor=theme.ACCENT_HEX,
                    font=theme.tkfont(12), fg=theme.INK, bg="white",
                    insertbackground=theme.ACCENT_HEX)

    # -- kurulum ------------------------------------------------------------
    def _build(self):
        self._build_groups()
        self._build_folders()
        self._build_actions()
        self._build_results()

    def _build_groups(self):
        cl = self.cl
        self._text(cl, 104, "GROUP NAMES", theme.tkfont(9, "bold"), theme.SLATE)

        self.var_new = tk.StringVar()
        entry = tk.Entry(self.root, textvariable=self.var_new, **self._entry_kw())
        self.canvas.create_window(cl, 122, anchor="nw", window=entry,
                                  width=self.lw - 134, height=38)
        entry.bind("<Return>", lambda _e: self.on_add())
        self._entry = entry

        bid = self.canvas.create_image(
            cl + self.lw - 120, 122, anchor="nw",
            image=self.app._mk(theme.button_image(120, 38, "Add", "ghost")))
        self.canvas.tag_bind(bid, "<Button-1>", lambda _e: self.on_add())
        self.app._cursor(bid)

        # Liste bir Treeview: ad + o kumeye dusen dosya sayisi. Calistirdiktan
        # sonra kullanicinin bakmak istedigi sey tam olarak bu sayilar.
        frame = tk.Frame(self.root, bg="white", highlightthickness=1,
                         highlightbackground="#C5D8EC")
        self.groups = ttk.Treeview(frame, columns=("name", "n"), show="headings",
                                   style="Frost.Treeview", selectmode="browse")
        self.groups.heading("name", text="Group name")
        self.groups.heading("n", text="Files")
        self.groups.column("name", width=self.lw - 92, anchor="w")
        self.groups.column("n", width=72, anchor="e")
        vsb = ttk.Scrollbar(frame, orient="vertical", command=self.groups.yview)
        self.groups.configure(yscrollcommand=vsb.set)
        self.groups.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.app._tag(self.canvas.create_window(cl, 172, anchor="nw",
                                                window=frame, width=self.lw,
                                                height=196), "sw")
        # Teker teker silme: cift tik, Delete tusu veya sag tik menusu.
        self.groups.bind("<Double-1>", lambda _e: self.on_remove())
        self.groups.bind("<Delete>", lambda _e: self.on_remove())
        self.groups.bind("<Button-3>", self._on_menu)

        self._menu = tk.Menu(self.root, tearoff=0)
        self._menu.add_command(label="Remove", command=self.on_remove)
        self._menu.add_command(label="Remove all", command=self.on_clear)

        self._count_id = self._text(cl, 378, "", theme.tkfont(9), theme.SLATE)
        # Toplu silme gorunur bir baglanti; teker teker silme satirin kendisinde.
        clear_id = self.app._tag(
            self._text(cl + self.lw, 378, "Clear all",
                       theme.tkfont(9, "bold"), theme.ACCENT_HEX,
                       anchor="ne"), "ar")
        self.canvas.tag_bind(clear_id, "<Button-1>", lambda _e: self.on_clear())
        self.app._cursor(clear_id)
        box = self.canvas.bbox(clear_id)
        self.app._tag(self._text(box[0] - 12, 378,
                                 "Double-click a name to remove one",
                                 theme.tkfont(9), theme.MUTED, anchor="ne"),
                      "ar")

    def _on_menu(self, event):
        row = self.groups.identify_row(event.y)
        if row:
            self.groups.selection_set(row)
        self._menu.entryconfig("Remove", state="normal" if row else "disabled")
        self._menu.tk_popup(event.x_root, event.y_root)

    def _build_folders(self):
        rx, rw = self.rx, self.rw
        bw = 112

        # TEK klasor. Kume klasorleri bunun icinde acilir; kokte kalanlar
        # "henuz islenmemis" demektir. Ikinci bir hedef secmek gereksizdi.
        self.app._tag(self._text(rx, 104, "FOLDER", theme.tkfont(9, "bold"),
                                 theme.SLATE), "ar")
        open_id = self.app._tag(
            self._text(self.cr, 104, "Open", theme.tkfont(9, "bold"),
                       theme.ACCENT_HEX, anchor="ne"), "ar")
        self.canvas.tag_bind(open_id, "<Button-1>", lambda _e: self.on_open_target())
        self.app._cursor(open_id)

        self.var_src = tk.StringVar()
        entry = tk.Entry(self.root, textvariable=self.var_src, **self._entry_kw())
        self.app._tag(self.canvas.create_window(rx, 122, anchor="nw",
                                                window=entry,
                                                width=rw - bw - 10, height=38),
                      "ar")
        browse = self.app._tag(self.canvas.create_image(
            self.cr, 122, anchor="ne",
            image=self.app._mk(theme.button_image(bw, 38, "Browse", "soft"))),
            "ar")
        self.canvas.tag_bind(browse, "<Button-1>", lambda _e: self.on_browse_src())
        self.app._cursor(browse)

        self.app._tag(self._text(rx, 176,
                                 "Group folders are created inside this folder.",
                                 theme.tkfont(9), theme.MUTED, width=rw), "ar")

        # OCR dugmesi ayni zamanda ESLESTIRME KIPINI belirler.
        self.var_ocr = tk.BooleanVar(value=False)
        self._toggle(rx, 214, "OCR (scanned PDFs)", self.var_ocr,
                     self._on_ocr_flip)
        # Sayfanin tek canli cumlesi: ne bulacagini belirleyen sey bu.
        self._mode_id = self.app._tag(
            self._text(rx, 252, "", theme.tkfont(11), theme.ACCENT_HEX,
                       width=rw), "ar")
        self._paint_mode()

        # Tasima varsayilan: kaynakta yalnizca islenmemisler kalsin diye.
        self.var_move = tk.BooleanVar(value=True)
        self._toggle(rx, 300, "Move originals out of the folder",
                     self.var_move, self._paint_move)
        self._move_id = self.app._tag(
            self._text(rx, 338, "", theme.tkfont(9), theme.SLATE,
                       width=rw), "ar")
        self._paint_move()

    def _toggle(self, x, y, label, var, after, anchor_right=True):
        """Tiklanabilir anahtar. Ana penceredeki _toggle ile ayni gorunum."""
        iid = self.app._tag(self.canvas.create_image(
            x, y, anchor="nw",
            image=self.app.tog_on if var.get() else self.app.tog_off),
            *(("ar",) if anchor_right else ()))
        tid = self.app._tag(self._text(x + 52, y + 3, label, theme.tkfont(11)),
                            *(("ar",) if anchor_right else ()))

        def flip(_e):
            if self._running:
                return
            var.set(not var.get())
            self.canvas.itemconfig(
                iid, image=self.app.tog_on if var.get() else self.app.tog_off)
            after()

        for item in (iid, tid):
            self.canvas.tag_bind(item, "<Button-1>", flip)
            self.app._cursor(item)
        return iid

    def _on_ocr_flip(self):
        self._invalidate()
        self._paint_mode()

    def _paint_move(self):
        if self.var_move.get():
            msg = ("Matched files go to the Recycle Bin once their copies are "
                   "verified, so only unprocessed files stay in the folder.")
        else:
            msg = "Every file stays where it is; only copies are made."
        self.canvas.itemconfig(self._move_id, text=msg)

    def _paint_mode(self):
        if self.var_ocr.get():
            msg = "Spaces and letter case are ignored while matching."
        else:
            msg = "Names must match exactly, including spaces and case."
        self.canvas.itemconfig(self._mode_id, text=msg)

    def _build_actions(self):
        # Eylemler saga yaslanir: solda liste, sagda klasorler ve eylemler.
        # Boylece satir iki kenardan da baglanir, ortada bosluk kalmaz.
        y = 392
        x = self.cr - (150 + 14 + 150)
        for name, label, kind, w, cmd in [
                ("preview", "Preview", "ghost", 150, self.on_preview),
                ("apply", "Apply", "accent", 150, self.on_apply)]:
            normal = self.app._mk(theme.button_image(w, 40, label, kind))
            disabled = self.app._mk(theme.button_image(w, 40, label, "disabled"))
            iid = self.app._tag(
                self.canvas.create_image(x, y, anchor="nw", image=normal), "ar")
            self._btn[name] = (iid, normal, disabled)
            self.canvas.tag_bind(iid, "<Button-1>", lambda _e, c=cmd: c())
            self.app._cursor(iid)
            x += w + 14

        self.progress = ttk.Progressbar(
            self.root, style="Frost.Horizontal.TProgressbar", mode="determinate")
        self.app._tag(self.canvas.create_window(
            self.cl, 448, anchor="nw", window=self.progress,
            width=self.cr - self.cl, height=8), "sw")

    def _build_results(self):
        self._text(self.cl, 466, "RESULTS", theme.tkfont(9, "bold"), theme.SLATE)
        export = self.app._tag(self.canvas.create_image(
            self.cr, 458, anchor="ne",
            image=self.app._mk(theme.button_image(110, 28, "Export", "soft"))),
            "ar")
        self.canvas.tag_bind(export, "<Button-1>", lambda _e: self.on_export())
        self.app._cursor(export)
        top = 486
        full = self.cr - self.cl
        cols = ("file", "groups", "status", "msg")
        heads = ("File", "Copied into", "Status", "Detail")
        widths = (300, 330, 110, full - 300 - 330 - 110 - 18)
        frame = tk.Frame(self.root, bg="white", highlightthickness=1,
                         highlightbackground="#C5D8EC")
        self.tree = ttk.Treeview(frame, columns=cols, show="headings",
                                 style="Frost.Treeview", selectmode="browse")
        for col, head, wide in zip(cols, heads, widths):
            self.tree.heading(col, text=head)
            # Yalnizca Detail esner: pencere buyuyunce kazanilan yer uzun
            # mesajlara gider, diger sutunlar okunakli genisligini korur.
            self.tree.column(col, width=wide, anchor="w",
                             stretch=(col == "msg"))
        vsb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.app._tag(self.canvas.create_window(
            self.cl, top, anchor="nw", window=frame, width=full,
            height=self.app.H - top - 52), "sw", "sh")
        self.tree.tag_configure("ok", background="#DBF5E3")
        self.tree.tag_configure("gray", background="#EDF1F5")
        self.tree.tag_configure("err", background="#FFD9D9")

    # -- kalici tercihler ---------------------------------------------------
    def _restore(self):
        for name in self.app._prefs.get("cluster_phrases", []):
            self.groups.insert("", "end", values=(name, ""))
        folder = (self.app._prefs.get("cluster_folder")
                  or self.app._prefs.get("folder", ""))
        if folder and os.path.isdir(folder):
            self.var_src.set(folder)
        self._paint_count()

    def _remember(self):
        self.app._prefs["cluster_phrases"] = self.phrases()
        self.app._prefs["cluster_folder"] = self.var_src.get().strip()
        self.app.save_prefs()

    def phrases(self) -> list:
        return [self.groups.item(i, "values")[0]
                for i in self.groups.get_children()]

    def _paint_count(self):
        n = len(self.groups.get_children())
        if n == 0:
            text = "No group names yet"
        elif n == 1:
            text = "1 group name"
        else:
            text = str(n) + " group names"
        self.canvas.itemconfig(self._count_id, text=text)

    def _paint_group_counts(self):
        """Her kume adinin yanina o kumeye dusen dosya sayisini yazar."""
        for item in self.groups.get_children():
            name = self.groups.item(item, "values")[0]
            n = self._counts.get(name, 0)
            self.groups.item(item, values=(name, str(n) if n else ""))

    # -- kume adi ekle / sil ------------------------------------------------
    def on_add(self):
        name = self.var_new.get().strip()
        if not name:
            return
        if name in self.phrases():
            self.var_new.set("")
            self.app._set_status("'" + name + "' is already in the list.")
            return
        self.groups.insert("", "end", values=(name, ""))
        self.var_new.set("")
        self._entry.focus_set()
        self._invalidate()
        self._paint_count()
        self._remember()

    def on_remove(self):
        sel = self.groups.selection()
        if not sel:
            return
        self.groups.delete(sel[0])
        self._invalidate()
        self._paint_count()
        self._remember()

    def on_clear(self):
        """Butun kume adlarini siler. Uzun bir listeyi kaybetmek can sikici
        oldugu icin once onay ister."""
        items = self.groups.get_children()
        if not items:
            return
        if not messagebox.askyesno(
                "Remove all",
                "Remove all {0} group name(s)?".format(len(items)),
                parent=self.root):
            return
        self.groups.delete(*items)
        self._invalidate()
        self._paint_count()
        self._remember()

    # -- klasorler ----------------------------------------------------------
    def on_browse_src(self):
        if self._running:
            return
        folder = filedialog.askdirectory(
            parent=self.root, title="Choose the folder with the PDFs",
            initialdir=self.var_src.get() or os.getcwd())
        if folder:
            self.var_src.set(folder)
            self._invalidate()
            self._remember()

    def on_open_target(self):
        target = self.var_src.get().strip()
        if not target or not os.path.isdir(target):
            self.app._set_status("Choose a folder first.")
            return
        try:
            os.startfile(target)
        except Exception:
            subprocess.Popen(["explorer", target])

    # -- calistirma ---------------------------------------------------------
    def _settings(self, dry_run: bool) -> Settings:
        # target_folder BOS: kumeler dosyanin kendi klasorunde acilir.
        return Settings(
            folder=self.var_src.get().strip(),
            phrases=self.phrases(),
            use_ocr=self.var_ocr.get(),
            move_originals=self.var_move.get(),
            all_pages=True,
            dry_run=dry_run,
        )

    def _sig(self, s: Settings):
        return (s.effective_folder(), tuple(s.phrases), s.use_ocr, s.all_pages)

    def _invalidate(self):
        self._cached_plan = None
        self._cached_sig = None

    def on_preview(self):
        if not self._running:
            self._run(dry_run=True)

    def on_apply(self):
        if self._running:
            return
        if self.var_move.get():
            question = ("Files that match a group name are copied into that "
                        "group folder, then removed from the folder.\n\n"
                        "Removed files go to the Recycle Bin, and a file is "
                        "only removed once every copy is verified.\n\n"
                        "Continue?")
        else:
            question = ("Files that match a group name are copied into that "
                        "group folder.\nOriginals stay where they are.\n\n"
                        "Continue?")
        if messagebox.askyesno("Cluster files", question, parent=self.root):
            self._run(dry_run=False)

    def _run(self, dry_run: bool):
        if not os.path.isdir(self.var_src.get().strip()):
            messagebox.showerror("Cluster", "Choose a folder that exists.",
                                 parent=self.root)
            return
        if not self.phrases():
            messagebox.showerror("Cluster", "Add at least one group name.",
                                 parent=self.root)
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
                    "OCR is on but no OCR engine was found, so scanned "
                    "(image-only) PDFs cannot be read.", parent=self.root)

        self._remember()
        self.tree.delete(*self.tree.get_children())
        self._counts = {}
        self._paint_group_counts()
        self.progress.configure(value=0, maximum=100)
        self._set_running(True)
        self.app._set_status("Working...")
        threading.Thread(target=self._worker, args=(settings, overrides),
                         daemon=True).start()

    def _worker(self, settings, overrides=None):
        def progress(index, total, result):
            self._queue.put(("progress", index, total, result))
        try:
            summary = cluster.cluster_folder(settings, progress,
                                             group_overrides=overrides)
            self._queue.put(("done", summary, settings))
        except Exception as exc:
            self._queue.put(("error", exc, traceback.format_exc()))

    def _drain(self):
        try:
            while True:
                self._handle(self._queue.get_nowait())
        except queue.Empty:
            pass
        finally:
            self.root.after(120, self._drain)

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
            self._set_running(False)
            self.app._set_status("Failed.")
            messagebox.showerror("Cluster", str(msg[1]) + "\n\n" + msg[2],
                                 parent=self.root)

    def _add_row(self, result):
        for name in result.groups:
            self._counts[name] = self._counts.get(name, 0) + 1
        self.tree.insert("", "end", values=(
            result.file_name,
            ", ".join(result.groups) if result.groups else "-",
            STATUS_LABELS.get(result.status, result.status),
            result.message,
        ), tags=(STATUS_TAGS.get(result.status, "gray"),))

    def _on_done(self, summary, settings):
        self._set_running(False)
        self._paint_group_counts()
        if settings.dry_run:
            self._cached_plan = summary.plan
            self._cached_sig = self._sig(settings)
            verb = "would be copied"
        else:
            self._invalidate()
            verb = "copied"
        self.app._set_status(
            "{0} of {1} file(s) matched  -  {2} copy(ies) {3}  -  "
            "{4} no match, {5} error(s)".format(
                summary.matched, summary.total, summary.copies, verb,
                summary.no_match, summary.errors))

    def on_export(self):
        """Kumeleme sonuclarini Excel dosyasi olarak kaydeder."""
        items = self.tree.get_children()
        if not items:
            messagebox.showinfo("Export", "There is nothing to export yet.",
                                parent=self.root)
            return
        path = filedialog.asksaveasfilename(
            parent=self.root, title="Export results",
            defaultextension=".xlsx",
            initialfile="pdf-clerk-clustered.xlsx",
            initialdir=self.var_src.get() or os.getcwd(),
            filetypes=[("Excel workbook", "*.xlsx"), ("CSV", "*.csv")])
        if not path:
            return
        headers = ["File", "Copied into", "Status", "Detail"]
        table = [list(self.tree.item(i, "values")) for i in items]
        try:
            exporter.save_table(path, headers, table, sheet_title="Clustered")
        except Exception as exc:
            messagebox.showerror("Export", "Could not write the file:\n"
                                 + str(exc), parent=self.root)
            return
        self.app._set_status("Exported {0} row(s) to {1}".format(
            len(table), os.path.basename(path)))

    def _set_running(self, on: bool):
        self._running = on
        for _name, (iid, normal, disabled) in self._btn.items():
            self.canvas.itemconfig(iid, image=disabled if on else normal)
