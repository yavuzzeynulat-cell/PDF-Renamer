"""dnd.install() gercekten dosya birakmayi yakaliyor mu?

Elle surukleyip birakmadan dogrulamak icin Windows'a GERCEK bir WM_DROPFILES
mesaji gonderiyoruz (HDROP'u kendimiz kuruyoruz). Boylece kanca, yol cozumu ve
kuyruga aktarim uctan uca sinaniyor.

Not: Mesajlar yalnizca GORUNUR pencerelere dagitilir, bu yuzden testler
pencereyi gizlemez.
"""
import ctypes
import struct
import sys

import pytest

if sys.platform != "win32":
    pytest.skip("Windows'a ozgu", allow_module_level=True)

tk = pytest.importorskip("tkinter")
import dnd

GMEM_MOVEABLE, GMEM_ZEROINIT = 0x0002, 0x0040


@pytest.fixture(scope="module")
def root():
    """Tek bir pencere tum testlerde paylasilir.

    Ayni surecte pesi sira Tk koku acip kapatmak Windows'ta guvenilmez; her
    test kendi kancasini kurup kaldirdigi icin paylasim sorun degil.
    """
    try:
        r = tk.Tk()
    except tk.TclError:  # ekransiz ortam
        pytest.skip("Tk penceresi acilamiyor")
    r.geometry("320x200+0+0")
    r.update()
    yield r
    try:
        r.destroy()
    except tk.TclError:
        pass


def _post_drop(hwnd, paths):
    """Verilen yollari iceren gercek bir HDROP olusturup pencereye gonderir."""
    k32 = ctypes.windll.kernel32
    k32.GlobalAlloc.restype = ctypes.c_void_p
    k32.GlobalLock.restype = ctypes.c_void_p
    k32.GlobalLock.argtypes = [ctypes.c_void_p]
    k32.GlobalUnlock.argtypes = [ctypes.c_void_p]

    body = ("\0".join(paths) + "\0\0").encode("utf-16-le")
    # DROPFILES: pFiles(DWORD) pt.x pt.y(LONG) fNC(BOOL) fWide(BOOL) = 20 bayt
    blob = struct.pack("<IiiiI", 20, 0, 0, 0, 1) + body

    handle = k32.GlobalAlloc(GMEM_MOVEABLE | GMEM_ZEROINIT, len(blob))
    ptr = k32.GlobalLock(handle)
    ctypes.memmove(ptr, blob, len(blob))
    k32.GlobalUnlock(handle)

    user32 = ctypes.windll.user32
    user32.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                    ctypes.c_size_t, ctypes.c_ssize_t]
    # HDROP'u DragFinish serbest birakir; biz GlobalFree cagirmiyoruz.
    user32.PostMessageW(ctypes.c_void_p(hwnd), dnd.WM_DROPFILES, handle, 0)


def _pump(root, times=10):
    for _ in range(times):
        root.update()


def test_install_returns_a_hook(root):
    hook = dnd.install(root)
    assert hook is not None, "WM_DROPFILES kancasi kurulamadi"
    hook.uninstall()


def test_dropped_paths_reach_the_queue(root):
    hook = dnd.install(root)
    _post_drop(hook.hwnd, [r"C:\a\bir.pdf", r"C:\b\iki.pdf"])
    _pump(root)
    assert hook.drain() == [[r"C:\a\bir.pdf", r"C:\b\iki.pdf"]]
    hook.uninstall()


def test_drain_empties_the_queue(root):
    hook = dnd.install(root)
    _post_drop(hook.hwnd, [r"C:\a\bir.pdf"])
    _pump(root)
    assert hook.drain()          # ilk cagri veriyi alir
    assert hook.drain() == []    # ikincisi bos doner
    hook.uninstall()


def test_two_drops_are_kept_separate(root):
    hook = dnd.install(root)
    _post_drop(hook.hwnd, [r"C:\a\bir.pdf"])
    _post_drop(hook.hwnd, [r"C:\b\iki.pdf"])
    _pump(root)
    assert hook.drain() == [[r"C:\a\bir.pdf"], [r"C:\b\iki.pdf"]]
    hook.uninstall()


def test_unicode_paths_survive(root):
    hook = dnd.install(root)
    _post_drop(hook.hwnd, r"C:\Belgeler\ÖĞÜT-ışık.pdf".split("|"))
    _pump(root)
    assert hook.drain() == [[r"C:\Belgeler\ÖĞÜT-ışık.pdf"]]
    hook.uninstall()


def test_window_still_works_after_hook(root):
    """Kanca, Tk'nin kendi mesajlarini eski yordama iletmeye devam etmeli."""
    hook = dnd.install(root)
    root.geometry("400x260")
    _pump(root)
    assert root.winfo_width() > 1  # pencere hala yasiyor ve cizilebiliyor
    root.geometry("320x200+0+0")
    hook.uninstall()


def test_uninstall_stops_delivery(root):
    hook = dnd.install(root)
    hwnd = hook.hwnd
    hook.uninstall()
    _post_drop(hwnd, [r"C:\a\bir.pdf"])
    _pump(root)
    assert hook.drain() == []
