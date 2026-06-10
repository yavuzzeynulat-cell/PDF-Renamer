"""
launcher.py - PyInstaller giris noktasi. Uygulamayi disaridaki src/'den yukler.

PyInstaller bunu PDF-Renamer.exe olarak derler. Gorevi:
  1. Calisma-zamani bagimliliklarini pakete kattirmak (force-import).
  2. Calisma aninda exe'nin yanindaki src/main.py'yi yuklemek (dev'de proje koku).
  3. Geri alma: src/ ice aktarimda veya main()'de cokerse src_backup/'i geri
     yukleyip BIR kez yeniden dener.

src/ icindeki kod dosyalari (main, gui, core, extractor, code_finder, renamer,
config, theme, cli, updater, version.txt) pakete GOMULMEZ; exe'nin yaninda durur
ve updater.apply_update() ile guncellenir. Agir bagimliliklar (onnxruntime,
rapidocr, pdfplumber, fitz...) exe'de gomulu kalir.
"""
from __future__ import annotations

# === Hafif calisma-zamani bagimliliklari: baslangicta gerekli, pakete kat ===
import tkinter  # noqa: F401
import tkinter.ttk  # noqa: F401
import PIL.Image  # noqa: F401
import PIL.ImageTk  # noqa: F401
import pdfplumber  # noqa: F401
import fitz  # PyMuPDF  # noqa: F401


def _force_bundle_heavy() -> None:
    """ASLA cagrilmaz. Yalnizca PyInstaller bu agir paketleri pakete katsin
    diye var; boylece OCR bagimliliklari baslangicta YUKLENMEZ (yavaslatmaz),
    ama gerektiginde (OCR acikken) icerden import edilebilir."""
    import numpy  # noqa: F401
    import cv2  # noqa: F401
    import onnxruntime  # noqa: F401
    import rapidocr_onnxruntime  # noqa: F401
    import pypdfium2  # noqa: F401
    import pdfminer  # noqa: F401


import os
import shutil
import sys
import traceback

# src/ guncellenince yeniden yuklenmesi gereken uygulama modulleri.
_APP_MODULES = ("main", "gui", "core", "extractor", "code_finder",
                "renamer", "config", "theme", "cli", "updater")


def _app_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _show_error(message: str) -> None:
    """Son care hata kutusu (src/ VE src_backup/ ikisi de cokerse)."""
    try:
        from tkinter import Tk, messagebox
        root = Tk()
        root.withdraw()
        messagebox.showerror("PDF Renamer - Critical Error", message)
        root.destroy()
    except Exception:
        try:
            with open(os.path.join(_app_dir(), "launcher_crash.log"), "a",
                      encoding="utf-8") as f:
                f.write(message + "\n---\n")
        except OSError:
            pass


def _run_src() -> None:
    """src/'yi sys.path'e ekleyip main()'i calistirir. Dev'de src/ yoksa
    proje kokune duser."""
    app = _app_dir()
    src_dir = os.path.join(app, "src")
    target_dir = src_dir if os.path.isdir(src_dir) else app
    if target_dir not in sys.path:
        sys.path.insert(0, target_dir)
    for mod in _APP_MODULES:
        sys.modules.pop(mod, None)
    import main as _main
    _main.main()


def _rollback() -> bool:
    """src_backup/ -> src/ geri yukler. Yuklediyse True."""
    app = _app_dir()
    src = os.path.join(app, "src")
    backup = os.path.join(app, "src_backup")
    if not os.path.isdir(backup):
        return False
    if os.path.isdir(src):
        shutil.rmtree(src, ignore_errors=True)
    os.rename(backup, src)
    return True


def main() -> None:
    try:
        _run_src()
        return
    except SystemExit:
        raise
    except BaseException:
        first_err = traceback.format_exc()

    if not _rollback():
        _show_error(
            "The app could not start and there is no previous version "
            "to restore.\n\n"
            f"Error:\n{first_err}\n\n"
            "Please run the installer again."
        )
        sys.exit(1)

    try:
        _run_src()
    except SystemExit:
        raise
    except BaseException:
        second_err = traceback.format_exc()
        _show_error(
            "The app could not start (even after rollback).\n\n"
            f"First error:\n{first_err}\n\nSecond error:\n{second_err}"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
