"""Working frosted-glass GUI (English) for the PDF renamer.

A short splash ("Produced by Yavuz Zeynula") shows on launch, then the main
window. Fully wired to core.process_folder / core.process_files and
renamer.undo_last.

The results table doubles as a drop zone: PDFs dropped on the window are
previewed and renamed WHERE THEY ARE -- nothing is ever moved or copied.

No Tk objects are created at import time, so `import gui` is side-effect free.
"""
from __future__ import annotations

import os
import csv
import json
import queue
import subprocess
import threading
import traceback
from typing import Optional

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import ImageTk

import theme
from config import Settings, DEFAULT_PREFIX
import core
import dnd
import updater

W, H = 1080, 770

CREDIT = "Developed by Yavuz Zeynula"
DROP_HINT = "Drop PDF files or folders here  -  they are renamed where they are"
NO_MATCH_HINT = "No rows match the current filter."

STATUS_TAGS = {
    "renamed": "ok", "preview": "ok", "restored": "ok", "already": "gray",
    "not_found": "warn", "error": "err",
}
STATUS_LABELS = {
    "renamed": "Renamed", "preview": "Preview", "restored": "Restored",
    "already": "Already OK", "not_found": "Not found", "error": "Error",
}

# Filtre dugmeleri: (anahtar, etiket, bu filtreye giren durumlar).
# None = hepsi. 'Renamed' onizleme ve geri-alma satirlarini da kapsar, cunku
# ozet sayaci da onlari ayni kefeye koyar.
FILTERS = [
    ("all", "All", None),
    ("renamed", "Renamed", {"renamed", "preview", "restored"}),
    ("already", "Already OK", {"already"}),
    ("not_found", "Not found", {"not_found"}),
    ("error", "Error", {"error"}),
]
FILTER_STATES = {key: states for key, _label, states in FILTERS}


# -- kullanici tercihleri (son secilen klasor vb.) kalici saklama -------------
def _prefs_path() -> str:
    """Kullaniciya ozel, kurulumdan/guncellemeden bagimsiz ayar dosyasi yolu."""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "PDF-Renamer")
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        pass
    return os.path.join(d, "prefs.json")


def _load_prefs() -> dict:
    try:
        with open(_prefs_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_prefs(prefs: dict) -> None:
    try:
        with open(_prefs_path(), "w", encoding="utf-8") as f:
            json.dump(prefs, f)
    except Exception:
        pass


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("PDF Renamer")
        root.geometry(f"{W}x{H}")
        root.resizable(False, False)
        self._imgrefs = []
        self._ui_queue: "queue.Queue[tuple]" = queue.Queue()
        self._running = False
        self._ocr_warned = False  # show "OCR unavailable" warning at most once
        self._prefs = _load_prefs()  # son secilen klasor burada saklanir
        # Onizleme onbellegi: Apply'da tekrar OCR/cikarim yapmamak icin.
        self._cached_plan = None   # son onizlemede bulunan {yol: kod}
        self._cached_sig = None    # o onizlemenin girdi imzasi
        self._last_settings = None  # son calistirilan Settings (dry_run bilgisi icin)
        self._btn = {}  # name -> (item_id, normal_img, disabled_img)

        # -- sonuc satirlari: tablo filtreye gore yeniden cizilir ----------
        self._rows = []       # tum satirlar (filtreden bagimsiz), sirali
        self._row_meta = {}   # tablodaki item_id -> satir sozlugu
        self._filter = "all"
        self._counts = {key: 0 for key, _lbl, _st in FILTERS}
        self._chip = {}       # filtre anahtari -> canvas metin id'si

        # -- surukle-birak: birakilan dosyalar burada birikir --------------
        # Bos ise klasor modundayiz; doluysa YALNIZCA bu dosyalar islenir.
        self._pending = []
        self._dnd = None

        self.cl, self.cr = 46, W - 46
        self.fullw = self.cr - self.cl

        self.canvas = tk.Canvas(root, width=W, height=H, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)

        self.tog_on = self._mk(theme.toggle_image(True))
        self.tog_off = self._mk(theme.toggle_image(False))

        self._style()
        self._draw_static()
        self._build_inputs()
        self._build_options()
        self._build_buttons()
        self._build_results()
        self._update_example()
        self._build_menu()
        _apply_window_effects(root)
        # Surukle-birak: kurulamazsa "Add PDFs" dugmesi ayni isi gorur.
        self._dnd = dnd.install(root)
        self.root.after(100, self._drain_queue)
        # Acilista sessiz guncelleme kontrolu (cevrimdisi ise hicbir sey olmaz).
        threading.Thread(target=self._check_update_worker, args=(False,),
                         daemon=True).start()

    # -- helpers ------------------------------------------------------------
    def _mk(self, pil):
        t = ImageTk.PhotoImage(pil)
        self._imgrefs.append(t)
        return t

    def _text(self, x, y, s, f, fill=theme.INK, anchor="nw", width=None):
        return self.canvas.create_text(x, y, text=s, font=f, fill=fill,
                                       anchor=anchor, width=width)

    def _style(self):
        st = ttk.Style()
        try:
            st.theme_use("clam")
        except Exception:
            pass
        st.configure("Frost.Treeview", background="#FFFFFF",
                     fieldbackground="#FFFFFF", foreground=theme.INK,
                     rowheight=27, borderwidth=0, font=("Segoe UI", 10))
        st.configure("Frost.Treeview.Heading", font=("Segoe UI Semibold", 10),
                     background="#E7F0FB", foreground=theme.SLATE,
                     borderwidth=0, relief="flat")
        st.map("Frost.Treeview", background=[("selected", "#CFE3FF")],
               foreground=[("selected", theme.INK)])
        st.configure("Frost.Horizontal.TProgressbar", troughcolor="#E2ECF7",
                     background=theme.ACCENT_HEX, borderwidth=0, thickness=8)

    # -- static art ---------------------------------------------------------
    def _draw_static(self):
        # Tek temiz yuzey: icerik dogrudan arka plan uzerinde (ic ice cerceve yok).
        self.canvas.create_image(0, 0, image=self._mk(theme.make_background(W, H)),
                                 anchor="nw")

        self._text(self.cl, 32, "PDF Renamer", theme.tkfont(21, "semibold"))
        self._text(self.cl, 64, "Read the document number  →  rename the file automatically",
                   theme.tkfont(10), theme.SLATE)
        badge = theme.pill("v" + updater.current_version(),
                           theme.font(theme.SEGOE_SB, 10),
                           (255, 255, 255, 255), theme.ACCENT + (235,))
        self.canvas.create_image(self.cr, 30, image=self._mk(badge), anchor="ne")
        # Guncelleme linki (rozetin altinda, sag ust)
        self.upd_id = self._text(self.cr, 60, "Check for updates",
                                 theme.tkfont(9, "bold"), theme.ACCENT_HEX,
                                 anchor="ne")
        self.canvas.tag_bind(self.upd_id, "<Button-1>",
                             lambda e: self.on_check_update())
        self._cursor(self.upd_id)
        self.canvas.create_line(self.cl, 88, self.cr, 88, fill="#CFE0F2")

        self._text(self.cl, 100, "FOLDER", theme.tkfont(9, "bold"), theme.SLATE)
        self._text(self.cl, 166, "DOCUMENT CODE PREFIX  (editable)",
                   theme.tkfont(9, "bold"), theme.SLATE)
        self._text(366, 166, "TEXT TO ADD  (after the number, no space)",
                   theme.tkfont(9, "bold"), theme.SLATE)

        # example box (slim, single row) - icerik seride DIKEY ORTALI (anchor=w)
        self.ex_y = 230
        box_h = 42
        cy = self.ex_y + box_h // 2
        box = theme.rounded_rect((self.fullw, box_h), 12,
                                 (theme.ACCENT[0], theme.ACCENT[1], theme.ACCENT[2], 22),
                                 theme.ACCENT + (90,), 1)
        self.canvas.create_image(self.cl, self.ex_y, image=self._mk(box), anchor="nw")
        self._text(self.cl + 16, cy, "EXAMPLE OUTPUT",
                   theme.tkfont(8, "bold"), theme.ACCENT_HEX, anchor="w")
        # Dosya adi seritte hem dikey hem yatay ORTALI.
        self.ex_id = self._text(self.cl + self.fullw // 2, cy, "",
                                theme.tkfont(13, "semibold"), theme.INK,
                                anchor="center")

        self._text(self.cl, 284, "OPTIONS", theme.tkfont(9, "bold"), theme.SLATE)

        # Pencerenin en altinda kalici yazar bilgisi (acilistaki splash'a ek).
        self.canvas.create_line(self.cl, H - 40, self.cr, H - 40, fill="#DCE7F3")
        self._text(W // 2, H - 24, CREDIT, theme.tkfont(9), theme.SLATE,
                   anchor="center")

    # -- inputs -------------------------------------------------------------
    def _build_inputs(self):
        kw = dict(relief="flat", bd=0, highlightthickness=2,
                  highlightbackground="#C5D8EC", highlightcolor=theme.ACCENT_HEX,
                  font=theme.tkfont(12), fg=theme.INK, bg="white",
                  insertbackground=theme.ACCENT_HEX)

        # Acilista son secilen klasoru getir (varsa ve hala mevcutsa).
        last = self._prefs.get("folder")
        start_folder = last if (last and os.path.isdir(last)) else os.getcwd()
        self.var_folder = tk.StringVar(value=start_folder)
        e1 = tk.Entry(self.root, textvariable=self.var_folder, **kw)
        self.canvas.create_window(self.cl, 118, anchor="nw", window=e1,
                                  width=self.fullw - 118, height=36)
        bid = self.canvas.create_image(self.cr, 118, image=self._mk(
            theme.button_image(108, 36, "Browse", "soft")), anchor="ne")
        self.canvas.tag_bind(bid, "<Button-1>", lambda e: self.on_browse())
        self._cursor(bid)

        self.var_prefix = tk.StringVar(value=DEFAULT_PREFIX)
        self.var_suffix = tk.StringVar(value="")
        self.var_prefix.trace_add("write", lambda *_: self._update_example())
        self.var_suffix.trace_add("write", lambda *_: self._update_example())

        e2 = tk.Entry(self.root, textvariable=self.var_prefix, **kw)
        self.canvas.create_window(self.cl, 184, anchor="nw", window=e2,
                                  width=300, height=36)
        e3 = tk.Entry(self.root, textvariable=self.var_suffix, **kw)
        self.canvas.create_window(366, 184, anchor="nw", window=e3,
                                  width=self.cr - 366, height=36)

    # -- options (clickable toggles) ---------------------------------------
    def _build_options(self):
        self.var_all = tk.BooleanVar(value=True)
        self.var_ci = tk.BooleanVar(value=True)
        self.var_ocr = tk.BooleanVar(value=False)
        self._toggle(self.cl, 304, "Scan all pages", self.var_all)
        self._toggle(330, 304, "Case-insensitive", self.var_ci)
        self._toggle(590, 304, "OCR (scanned PDFs)", self.var_ocr)

    def _toggle(self, x, y, label, var):
        iid = self.canvas.create_image(x, y, image=self._tog(var.get()), anchor="nw")
        tid = self._text(x + 52, y + 3, label, theme.tkfont(11))

        def flip(_e):
            if self._running:
                return
            var.set(not var.get())
            self.canvas.itemconfig(iid, image=self._tog(var.get()))
        for t in (iid, tid):
            self.canvas.tag_bind(t, "<Button-1>", flip)
            self._cursor(t)

    def _tog(self, on):
        return self.tog_on if on else self.tog_off

    # -- buttons ------------------------------------------------------------
    def _build_buttons(self):
        y = 342
        specs = [("preview", "Preview", "ghost", 150, self.on_preview),
                 ("apply", "Apply", "accent", 150, self.on_apply),
                 ("undo", "Undo", "ghost", 130, self.on_undo),
                 ("add", "+ Add PDFs", "ghost", 150, self.on_add_files)]
        x = self.cl
        for name, text, kind, w, cmd in specs:
            normal = self._mk(theme.button_image(w, 40, text, kind))
            disabled = self._mk(theme.button_image(w, 40, text, "disabled"))
            iid = self.canvas.create_image(x, y, image=normal, anchor="nw")
            self._btn[name] = (iid, normal, disabled)
            self.canvas.tag_bind(iid, "<Button-1>", lambda e, c=cmd: c())
            self._cursor(iid)
            x += w + 14

        # progress bar
        self.progress = ttk.Progressbar(self.root, style="Frost.Horizontal.TProgressbar",
                                        mode="determinate")
        self.canvas.create_window(self.cl, 392, anchor="nw", window=self.progress,
                                  width=self.fullw, height=8)

    def _cursor(self, item):
        self.canvas.tag_bind(item, "<Enter>",
                             lambda e: self.canvas.config(cursor="hand2"))
        self.canvas.tag_bind(item, "<Leave>",
                             lambda e: self.canvas.config(cursor=""))

    # -- results table ------------------------------------------------------
    def _build_results(self):
        self._text(self.cl, 406, "RESULTS", theme.tkfont(9, "bold"), theme.SLATE)
        # Durum yazisi en altta, kunyenin solunda: arac cubugunu kalabaliklastirmaz.
        self.var_status = tk.StringVar(value="Ready.")
        self._status_id = self._text(self.cl, H - 24, "Ready.", theme.tkfont(9),
                                     theme.SLATE, anchor="w")

        # Birakma modu uyarisi ("N dosya birakildi ...") -- normalde gizli.
        self._drop_id = self._text(self.cl + 68, 406, "", theme.tkfont(9, "bold"),
                                   theme.ACCENT_HEX)
        self._dropx_id = self._text(0, 406, "", theme.tkfont(9, "bold"), "#C0392B")
        self.canvas.tag_bind(self._dropx_id, "<Button-1>",
                             lambda e: self.on_clear_drop())
        self._cursor(self._dropx_id)

        self._build_toolbar()

        top = 460
        cols = ("old", "new", "status", "msg")
        heads = ("Original", "New name", "Status", "Detail")
        widths = (300, 360, 110, self.fullw - 300 - 360 - 110 - 18)
        frame = tk.Frame(self.root, bg="white", highlightthickness=1,
                         highlightbackground="#C5D8EC")
        self.tree = ttk.Treeview(frame, columns=cols, show="headings",
                                 style="Frost.Treeview", selectmode="browse")
        for c, hd, wd in zip(cols, heads, widths):
            self.tree.heading(c, text=hd)
            self.tree.column(c, width=wd, anchor="w")
        vsb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.canvas.create_window(self.cl, top, anchor="nw", window=frame,
                                  width=self.fullw, height=H - top - 52)

        self.tree.tag_configure("ok", background="#DBF5E3")
        self.tree.tag_configure("warn", background="#FFEAD6")
        self.tree.tag_configure("err", background="#FFD9D9")
        self.tree.tag_configure("gray", background="#EDF1F5")

        self.tree.bind("<Double-1>", self._on_row_activate)
        self.tree.bind("<Return>", self._on_row_activate)
        self.tree.bind("<Button-3>", self._on_row_menu)

        # Tablo bosken ortada duran ipucu (ayni zamanda birakma davetiyesi).
        self.hint = tk.Label(frame, text=DROP_HINT, bg="white", fg="#93AAC0",
                             font=theme.tkfont(11))
        self._paint_hint()

    # -- filter chips + search + export ------------------------------------
    def _build_toolbar(self):
        y = 430
        self._chip_font = (theme.tkfont(9, "bold"), theme.tkfont(9))
        x = self.cl
        for key, label, _states in FILTERS:
            tid = self._text(x, y, label, self._chip_font[1], theme.SLATE,
                             anchor="w")
            self.canvas.tag_bind(tid, "<Button-1>",
                                 lambda e, k=key: self.on_filter(k))
            self._cursor(tid)
            self._chip[key] = tid
            x += 112

        self._text(640, y, "SEARCH", theme.tkfont(9, "bold"), theme.SLATE,
                   anchor="w")
        self.var_search = tk.StringVar(value="")
        self.var_search.trace_add("write", lambda *_: self._refresh_table())
        se = tk.Entry(self.root, textvariable=self.var_search, relief="flat",
                      bd=0, highlightthickness=2, highlightbackground="#C5D8EC",
                      highlightcolor=theme.ACCENT_HEX, font=theme.tkfont(10),
                      fg=theme.INK, bg="white", insertbackground=theme.ACCENT_HEX)
        self.canvas.create_window(706, y - 14, anchor="nw", window=se,
                                  width=204, height=28)

        eid = self.canvas.create_image(self.cr, y - 14, image=self._mk(
            theme.button_image(110, 28, "Export", "soft")), anchor="ne")
        self.canvas.tag_bind(eid, "<Button-1>", lambda e: self.on_export())
        self._cursor(eid)

        self._paint_chips()

    def _paint_chips(self):
        bold, normal = self._chip_font
        for key, label, _states in FILTERS:
            active = key == self._filter
            self.canvas.itemconfig(
                self._chip[key],
                text=f"{label} ({self._counts[key]})",
                font=bold if active else normal,
                fill=theme.ACCENT_HEX if active else theme.SLATE)

    def _paint_hint(self):
        """Tablo bosken ipucunu goster, doluyken gizle."""
        if self.tree.get_children():
            self.hint.place_forget()
            return
        self.hint.configure(text=NO_MATCH_HINT if self._rows else DROP_HINT)
        self.hint.place(relx=0.5, rely=0.5, anchor="center")

    def _paint_drop_banner(self):
        """Birakma modu uyarisini ve yanindaki temizleme baglantisini tazeler."""
        text = (f"{len(self._pending)} dropped file(s) - the folder box is ignored"
                if self._pending else "")
        self.canvas.itemconfig(self._drop_id, text=text)
        if text:
            box = self.canvas.bbox(self._drop_id)
            self.canvas.coords(self._dropx_id, box[2] + 14, 406)
            self.canvas.itemconfig(self._dropx_id, text="clear")
        else:
            self.canvas.itemconfig(self._dropx_id, text="")

    # -- filters ------------------------------------------------------------
    def on_filter(self, key):
        if key != self._filter:
            self._filter = key
            self._paint_chips()
            self._refresh_table()

    def _matches(self, row):
        states = FILTER_STATES[self._filter]
        if states is not None and row["status"] not in states:
            return False
        needle = self.var_search.get().strip().casefold()
        if not needle:
            return True
        hay = f"{row['old']} {row['new']} {row['detail']}".casefold()
        return needle in hay

    def _refresh_table(self):
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self._row_meta.clear()
        for row in self._rows:
            if self._matches(row):
                self._insert_row(row)
        self._paint_hint()

    def _insert_row(self, row):
        iid = self.tree.insert(
            "", "end", tags=(row["tag"],) if row["tag"] else (),
            values=(row["old"], row["new"], row["label"], row["detail"]))
        self._row_meta[iid] = row

    def _push_row(self, row):
        """Satiri kaydeder, sayaclari artirir, filtreye uyuyorsa gosterir."""
        self._rows.append(row)
        for key, _label, states in FILTERS:
            if states is None or row["status"] in states:
                self._counts[key] += 1
        self._paint_chips()
        if self._matches(row):
            self._insert_row(row)
        self._paint_hint()

    # -- example ------------------------------------------------------------
    def _update_example(self):
        name = f"{self.var_prefix.get()}001{self.var_suffix.get()}.pdf"
        self.canvas.itemconfig(self.ex_id, text=name)

    # -- actions ------------------------------------------------------------
    def on_browse(self):
        if self._running:
            return
        d = filedialog.askdirectory(initialdir=self.var_folder.get() or os.getcwd(),
                                    title="Choose folder")
        if d:
            self.var_folder.set(d)
            self._remember_folder(d)

    def _remember_folder(self, folder):
        """Secilen klasoru kalici kaydet ki bir sonraki acilista secili gelsin."""
        if folder and os.path.isdir(folder):
            self._prefs["folder"] = folder
            _save_prefs(self._prefs)

    def _settings(self, dry_run):
        return Settings(
            folder=self.var_folder.get().strip(),
            prefix=self.var_prefix.get(),
            suffix=self.var_suffix.get(),
            ignore_case=self.var_ci.get(),
            all_pages=self.var_all.get(),
            use_ocr=self.var_ocr.get(),
            dry_run=dry_run,
        )

    def _sig(self, settings):
        """Sonucu etkileyen girdilerin imzasi (dry_run HARIC).

        Onizleme onbelleginin Apply icin hala gecerli olup olmadigini bu imza
        belirler; sadece dry_run degisirse onbellek gecerli kalir.
        """
        return (settings.effective_folder(), settings.prefix, settings.suffix,
                settings.pattern, settings.ignore_case, settings.all_pages,
                settings.use_ocr, settings.recursive, tuple(self._pending))

    def on_preview(self):
        if not self._running:
            self._run(dry_run=True)

    def on_apply(self):
        if self._running:
            return
        if messagebox.askyesno("Confirm", "Files will be renamed for real.\nContinue?"):
            self._run(dry_run=False)

    def on_undo(self):
        if self._running:
            return
        # Birakma modunda dosyalar birden cok klasorde olabilir; her birinin
        # kendi geri-alma logu vardir, hepsi tek tek geri alinir.
        folders = self._active_folders()
        question = ("Undo the last rename batch in this folder?" if len(folders) == 1
                    else f"Undo the last rename batch in {len(folders)} folders?")
        if not messagebox.askyesno("Confirm", question):
            return

        restored = []  # (klasor, RenameOutcome) -- satirdan dosyaya donebilmek icin
        try:
            from renamer import undo_last
            for folder in folders:
                restored += [(folder, o) for o in undo_last(folder)]
        except Exception as exc:
            messagebox.showerror("Undo", f"Undo failed:\n{exc}")
            return

        self._clear()
        for folder, o in restored:
            ok = getattr(o, "status", "") == "renamed"
            back_to = getattr(o, "old_name", "") or ""
            self._push_row({
                "old": getattr(o, "new_name", "") or "",
                "new": back_to,
                "status": "restored" if ok else "error",
                "label": "Restored" if ok else "Error",
                "detail": getattr(o, "message", "") or "",
                "path": os.path.join(folder, back_to) if back_to else folder,
                "tag": "ok" if ok else "err",
            })
        self._set_status(f"Undo finished: {len(restored)} item(s).")

    def _active_folders(self):
        """Su an uzerinde calisilan klasorler (birakma modunda birden fazla)."""
        if self._pending:
            seen, out = set(), []
            for path in self._pending:
                d = os.path.dirname(path)
                key = os.path.normcase(d)
                if key not in seen:
                    seen.add(key)
                    out.append(d)
            return out
        return [self.var_folder.get().strip() or os.getcwd()]

    # -- run worker ---------------------------------------------------------
    def _run(self, dry_run):
        # Birakilan dosyalar varsa YALNIZCA onlar islenir; klasor kutusu yok
        # sayilir. Aksi halde eskiden beri calisan klasor akisi aynen surer.
        paths = list(self._pending) if self._pending else None
        if paths is None:
            folder = self.var_folder.get().strip() or os.getcwd()
            if not os.path.isdir(folder):
                messagebox.showerror("Error", "Please choose a valid folder.")
                return
            self._remember_folder(folder)
        s = self._settings(dry_run)
        self._last_settings = s
        # Apply ise ve gecerli (ayni imzali) bir onizleme onbellegi varsa,
        # kodlari yeniden kullan; aksi halde normal (override'siz) calistir.
        overrides = None
        if (not dry_run and self._cached_plan is not None
                and self._sig(s) == self._cached_sig):
            overrides = self._cached_plan
        # If the user wants OCR but no engine is present, say so once instead of
        # silently skipping scanned PDFs (the old confusing behavior).
        if s.use_ocr and not self._ocr_warned:
            import extractor
            if not extractor.ocr_available():
                self._ocr_warned = True
                messagebox.showwarning(
                    "OCR unavailable",
                    "OCR is enabled but no OCR engine was found, so scanned "
                    "(image-only) PDFs cannot be read.\n\n"
                    "Reinstall the app, or run: pip install rapidocr-onnxruntime")
        self._clear()
        self.progress.configure(value=0, maximum=100)
        self._set_running(True)
        self._set_status("Working...")
        threading.Thread(target=self._worker, args=(s, overrides, paths),
                         daemon=True).start()

    def _worker(self, settings, overrides=None, paths=None):
        def progress(i, n, r):
            self._ui_queue.put(("progress", i, n, r))
        try:
            if paths is None:
                summary = core.process_folder(settings, progress,
                                              code_overrides=overrides)
            else:
                summary = core.process_files(paths, settings, progress,
                                             code_overrides=overrides)
            self._ui_queue.put(("done", summary))
        except Exception as exc:
            self._ui_queue.put(("error", exc, traceback.format_exc()))

    def _drain_queue(self):
        # Surukle-birak kancasi Tk'ye dokunamaz, sadece kuyruga yazar; onu
        # burada, guvenli tarafta bosaltiyoruz.
        if self._dnd is not None:
            for paths in self._dnd.drain():
                self._on_dropped(paths)
        try:
            while True:
                self._handle(self._ui_queue.get_nowait())
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self._drain_queue)

    def _handle(self, msg):
        kind = msg[0]
        if kind == "progress":
            _, i, n, r = msg
            if n:
                self.progress.configure(maximum=n, value=i)
            self._add_row(r)
        elif kind == "done":
            self._on_done(msg[1])
        elif kind == "error":
            self._on_error(msg[1], msg[2])
        elif kind == "update":
            self._on_update(msg[1], msg[2])

    def _add_row(self, r):
        self._push_row({
            "old": r.old_name,
            "new": r.new_name or "",
            "status": r.status,
            "label": STATUS_LABELS.get(r.status, r.status),
            "detail": r.message,
            "path": getattr(r, "path", "") or "",
            "tag": STATUS_TAGS.get(r.status, ""),
        })

    def _on_done(self, s):
        self._set_running(False)
        # Onizleme sonucunu onbellege al; gercek Apply sonrasi onbellegi gecersiz kil
        # (dosyalar artik yeniden adlandirildi, eski plan bayatladi).
        if self._last_settings is not None:
            if self._last_settings.dry_run:
                self._cached_plan = s.plan
                self._cached_sig = self._sig(self._last_settings)
            else:
                self._cached_plan = None
                self._cached_sig = None
                # Gercek Apply'dan sonra birakilan dosyalarin adlari degisti;
                # listeyi yeni adlarla tazele ki Undo/Preview tutarli kalsin.
                if self._pending:
                    self._pending = self._renamed_paths(s)
                    self._paint_drop_banner()
        try:
            self.progress.configure(value=self.progress["maximum"])
        except Exception:
            pass
        self._set_status(f"Renamed: {s.renamed}   Already OK: {s.already}   "
                         f"Not found: {s.not_found}   Errors: {s.errors}")

    def _on_error(self, exc, tb):
        self._set_running(False)
        self.progress.configure(value=0)
        self._set_status(f"Error: {exc}")
        messagebox.showerror("Run error", f"{exc}\n\n{tb}")

    def _renamed_paths(self, summary):
        """Islem sonrasi diskte GERCEKTEN var olan dosya yollari."""
        out = []
        for r in summary.results:
            path = getattr(r, "path", "") or ""
            if not path:
                continue
            if r.new_name:
                moved = os.path.join(os.path.dirname(path), r.new_name)
                if os.path.exists(moved):
                    out.append(moved)
                    continue
            if os.path.exists(path):
                out.append(path)
        return out

    # -- drag & drop / adding files ----------------------------------------
    def _on_dropped(self, paths):
        """Pencereye birakilan yollari kuyruga alip onizlemeyi baslatir."""
        if self._running:
            self._set_status("Busy - drop the files again when this run ends.")
            return
        dropped = core.expand_pdf_paths(paths)
        if not dropped:
            self._set_status("No PDF files in that drop.")
            return
        # Onceki birakilanlarin ustune ekle (tekrarlar elenir).
        self._pending = core.expand_pdf_paths(list(self._pending) + dropped)
        self._cached_plan = None
        self._cached_sig = None
        self._paint_drop_banner()
        self._run(dry_run=True)   # once onizleme; degisiklik Apply ile olur

    def on_add_files(self):
        """Surukle-birak calismazsa (veya tercih edilmezse) ayni is."""
        if self._running:
            return
        picked = filedialog.askopenfilenames(
            title="Add PDF files",
            initialdir=self.var_folder.get() or os.getcwd(),
            filetypes=[("PDF files", "*.pdf")])
        if picked:
            self._on_dropped(list(picked))

    def on_clear_drop(self):
        """Birakma modundan cikip klasor moduna doner."""
        if self._running or not self._pending:
            return
        self._pending = []
        self._cached_plan = None
        self._cached_sig = None
        self._paint_drop_banner()
        self._clear()
        self._set_status("Back to folder mode.")

    # -- row actions --------------------------------------------------------
    def _build_menu(self):
        self.menu = tk.Menu(self.root, tearoff=0)
        self.menu.add_command(label="Open PDF", command=self._open_selected)
        self.menu.add_command(label="Show in folder", command=self._reveal_selected)
        self.menu.add_separator()
        self.menu.add_command(label="Copy new name", command=self._copy_selected)

    def _selected_row(self):
        sel = self.tree.selection()
        return self._row_meta.get(sel[0]) if sel else None

    def _row_file(self, row):
        """Satirin diskteki karsiligi: once yeni ad, yoksa eski yol."""
        path = row.get("path") or ""
        if not path:
            return None
        if row.get("new"):
            moved = os.path.join(os.path.dirname(path), row["new"])
            if os.path.exists(moved):
                return moved
        return path if os.path.exists(path) else None

    def _on_row_activate(self, _event=None):
        self._open_selected()

    def _on_row_menu(self, event):
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        self.tree.selection_set(iid)
        self.tree.focus(iid)
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def _open_selected(self):
        row = self._selected_row()
        if not row:
            return
        path = self._row_file(row)
        if not path:
            self._set_status("That file is no longer where it was.")
            return
        try:
            os.startfile(path)  # varsayilan PDF goruntuleyici
        except OSError as exc:
            messagebox.showerror("Open PDF", f"Could not open the file:\n{exc}")

    def _reveal_selected(self):
        row = self._selected_row()
        if not row:
            return
        path = self._row_file(row)
        if not path:
            self._set_status("That file is no longer where it was.")
            return
        try:
            # Explorer dosyayi secili halde acar; donus kodu 1 olsa da normaldir.
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        except OSError as exc:
            messagebox.showerror("Show in folder", f"Could not open Explorer:\n{exc}")

    def _copy_selected(self):
        row = self._selected_row()
        if not row:
            return
        name = row.get("new") or row.get("old") or ""
        if not name:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(name)
        self._set_status(f"Copied: {name}")

    # -- export -------------------------------------------------------------
    def on_export(self):
        """Tabloda GORUNEN satirlari CSV olarak kaydeder.

        UTF-8 BOM + noktali virgul: Excel dosyayi cift tiklayinca dogru
        sutunlara ve bozulmamis Turkce karakterlerle acar.
        """
        rows = [self._row_meta[iid] for iid in self.tree.get_children()]
        if not rows:
            messagebox.showinfo("Export", "There is nothing to export yet.")
            return
        path = filedialog.asksaveasfilename(
            title="Export results",
            defaultextension=".csv",
            initialfile="pdf-renamer-results.csv",
            initialdir=self.var_folder.get() or os.getcwd(),
            filetypes=[("CSV (opens in Excel)", "*.csv")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as fh:
                writer = csv.writer(fh, delimiter=";")
                writer.writerow(["Original", "New name", "Status", "Detail",
                                 "Folder"])
                for row in rows:
                    writer.writerow([row["old"], row["new"], row["label"],
                                     row["detail"],
                                     os.path.dirname(row.get("path") or "")])
        except OSError as exc:
            messagebox.showerror("Export", f"Could not write the file:\n{exc}")
            return
        self._set_status(f"Exported {len(rows)} row(s) to "
                         f"{os.path.basename(path)}")

    # -- updates ------------------------------------------------------------
    def on_check_update(self):
        """Kullanici 'Check for updates' linkine bastiginda (elle kontrol)."""
        if self._running:
            return
        self._set_status("Checking for updates...")
        threading.Thread(target=self._check_update_worker, args=(True,),
                         daemon=True).start()

    def _check_update_worker(self, manual):
        """Arka planda GitHub'a sorar; sonucu UI thread'ine kuyrukla iletir."""
        try:
            info = updater.check_for_update(timeout=8)
        except Exception:
            info = None
        self._ui_queue.put(("update", info, manual))

    def _on_update(self, info, manual):
        """UI thread: guncelleme sonucu. manual=True ise 'guncel' bilgisi gosterir."""
        if info is None:
            if manual:
                messagebox.showinfo(
                    "Updates",
                    f"You are on the latest version (v{updater.current_version()}).")
            self._set_status("Ready.")
            return
        if messagebox.askyesno(
                "New version available",
                f"New version: {info.version}\n\n{info.notes}\n\nUpdate now?"):
            updater.run_update_flow(info, parent_window=self.root)
        else:
            self._set_status("Ready.")

    # -- ui state -----------------------------------------------------------
    def _clear(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        self._row_meta.clear()
        self._rows.clear()
        for key in self._counts:
            self._counts[key] = 0
        self._paint_chips()
        self._paint_hint()

    def _set_status(self, text):
        self.canvas.itemconfig(self._status_id, text=text)

    def _set_running(self, running):
        self._running = running
        for name, (iid, normal, disabled) in self._btn.items():
            self.canvas.itemconfig(iid, image=disabled if running else normal)


# ---------------------------------------------------------------------------
# Splash + entry point
# ---------------------------------------------------------------------------
def _apply_window_effects(root):
    try:
        import ctypes
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        backdrop = ctypes.c_int(3)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 38, ctypes.byref(backdrop), ctypes.sizeof(backdrop))
        # DWMWA_WINDOW_CORNER_PREFERENCE = 33, DWMWCP_ROUND = 2 -> yuvarlak kose
        corner = ctypes.c_int(2)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 33, ctypes.byref(corner), ctypes.sizeof(corner))
    except Exception:
        pass


def _show_splash(root, on_done):
    sw, sh = 460, 240
    splash = tk.Toplevel(root)
    x = (splash.winfo_screenwidth() - sw) // 2
    y = (splash.winfo_screenheight() - sh) // 2
    splash.geometry(f"{sw}x{sh}+{x}+{y}")
    splash.overrideredirect(True)
    splash.attributes("-topmost", True)
    # Yuvarlak koseler icin: kose pikselleri anahtar renk -> saydam.
    KEY = "#ff00fe"
    splash.configure(bg=KEY)
    try:
        splash.attributes("-transparentcolor", KEY)
    except Exception:
        pass
    cv = tk.Canvas(splash, width=sw, height=sh, highlightthickness=0, bd=0, bg=KEY)
    cv.pack(fill="both", expand=True)
    img = ImageTk.PhotoImage(theme.splash_image(sw, sh, "PDF Renamer",
                                                "Produced by Yavuz Zeynula"))
    cv.create_image(0, 0, image=img, anchor="nw")
    cv.image = img  # keep ref
    # force it to actually paint and come to the front
    splash.lift()
    splash.update()
    splash.after(2200, lambda: (splash.destroy(), on_done()))


def main():
    root = tk.Tk()
    root.withdraw()

    def start():
        root.deiconify()
        root.lift()
        root.focus_force()
        App(root)

    _show_splash(root, start)
    root.mainloop()


if __name__ == "__main__":
    main()
