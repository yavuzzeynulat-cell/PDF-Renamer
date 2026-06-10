"""Working frosted-glass GUI (English) for the PDF renamer.

A short splash ("Produced by Yavuz Zeynula") shows on launch, then the main
window. Fully wired to core.process_folder and renamer.undo_last.

No Tk objects are created at import time, so `import gui` is side-effect free.
"""
from __future__ import annotations

import os
import json
import queue
import threading
import traceback
from typing import Optional

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import ImageTk

import theme
from config import Settings, DEFAULT_PREFIX
import core
import updater

W, H = 1080, 700

STATUS_TAGS = {
    "renamed": "ok", "preview": "ok", "already": "gray",
    "not_found": "warn", "error": "err",
}
STATUS_LABELS = {
    "renamed": "Renamed", "preview": "Preview", "already": "Already OK",
    "not_found": "Not found", "error": "Error",
}


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
        _apply_window_effects(root)
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
                 ("undo", "Undo", "ghost", 130, self.on_undo)]
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
        self.var_status = tk.StringVar(value="Ready.")
        self._status_id = self._text(self.cr, 406, "Ready.", theme.tkfont(10),
                                     theme.SLATE, anchor="ne")

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
        self.canvas.create_window(self.cl, 424, anchor="nw", window=frame,
                                  width=self.fullw, height=H - 424 - 22)

        self.tree.tag_configure("ok", background="#DBF5E3")
        self.tree.tag_configure("warn", background="#FFEAD6")
        self.tree.tag_configure("err", background="#FFD9D9")
        self.tree.tag_configure("gray", background="#EDF1F5")

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
                settings.use_ocr, settings.recursive)

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
        folder = self.var_folder.get().strip() or os.getcwd()
        if not messagebox.askyesno("Confirm",
                                   "Undo the last rename batch in this folder?"):
            return
        try:
            from renamer import undo_last
            outcomes = undo_last(folder)
        except Exception as exc:
            messagebox.showerror("Undo", f"Undo failed:\n{exc}")
            return
        self._clear()
        for o in outcomes:
            tag = "ok" if getattr(o, "status", "") == "renamed" else "err"
            self.tree.insert("", "end", tags=(tag,), values=(
                getattr(o, "new_name", "") or "", getattr(o, "old_name", "") or "",
                "Restored" if tag == "ok" else "Error", getattr(o, "message", "")))
        self._set_status(f"Undo finished: {len(outcomes)} item(s).")

    # -- run worker ---------------------------------------------------------
    def _run(self, dry_run):
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
        threading.Thread(target=self._worker, args=(s, overrides),
                         daemon=True).start()

    def _worker(self, settings, overrides=None):
        def progress(i, n, r):
            self._ui_queue.put(("progress", i, n, r))
        try:
            summary = core.process_folder(settings, progress,
                                          code_overrides=overrides)
            self._ui_queue.put(("done", summary))
        except Exception as exc:
            self._ui_queue.put(("error", exc, traceback.format_exc()))

    def _drain_queue(self):
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
        tag = STATUS_TAGS.get(r.status, "")
        self.tree.insert("", "end", tags=(tag,) if tag else (), values=(
            r.old_name, r.new_name or "", STATUS_LABELS.get(r.status, r.status),
            r.message))

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
