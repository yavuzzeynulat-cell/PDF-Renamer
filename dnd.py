"""Windows'ta pencereye dosya surukleyip birakma destegi -- ek paket YOK.

Tk kendi basina surukle-birak bilmez. Burada Windows'un kendi WM_DROPFILES
mekanizmasini dogrudan ctypes ile dinliyoruz. Boylece EXE'ye tkinterdnd2 gibi
ek ikili dosyalar girmez ve otomatik guncelleme paketi buyumez.

Kanca kurulamazsa `install()` None doner; cagiran taraf o zaman sessizce
"dosya sec" penceresine duser -- program yine calisir.

DIKKAT: Pencere yordami, Tk'nin olay dongusunun ICINDEN cagrilir ve o sirada
Tcl kilidi bizde degildir. Bu yuzden yordamin icinden Tk'ye DOKUNULMAZ
(root.after dahil -- yorumlayiciyi cokertir). Gelen yollar saf-Python bir
kuyruga yazilir; onlari Tk tarafinda kendi zamanlayicinizla bosaltirsiniz.
"""
from __future__ import annotations

import ctypes
import queue
from ctypes import wintypes

WM_DROPFILES = 0x0233
GWLP_WNDPROC = -4

# WNDPROC imzasi: LRESULT (HWND, UINT, WPARAM, LPARAM)
_WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, ctypes.c_uint,
                              wintypes.WPARAM, wintypes.LPARAM)


def _win_api():
    user32 = ctypes.windll.user32
    shell32 = ctypes.windll.shell32

    # 64-bit'te pencere yordami isaretcisi 8 bayt: ...LongPtrW kullanilmali.
    if ctypes.sizeof(ctypes.c_void_p) == 8:
        get_long, set_long = user32.GetWindowLongPtrW, user32.SetWindowLongPtrW
    else:
        get_long, set_long = user32.GetWindowLongW, user32.SetWindowLongW
    get_long.restype = ctypes.c_void_p
    get_long.argtypes = [wintypes.HWND, ctypes.c_int]
    set_long.restype = ctypes.c_void_p
    set_long.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]

    user32.CallWindowProcW.restype = ctypes.c_ssize_t
    user32.CallWindowProcW.argtypes = [ctypes.c_void_p, wintypes.HWND,
                                       ctypes.c_uint, wintypes.WPARAM,
                                       wintypes.LPARAM]
    shell32.DragQueryFileW.restype = wintypes.UINT
    shell32.DragQueryFileW.argtypes = [wintypes.HANDLE, wintypes.UINT,
                                       wintypes.LPWSTR, wintypes.UINT]
    shell32.DragFinish.argtypes = [wintypes.HANDLE]
    shell32.DragAcceptFiles.argtypes = [wintypes.HWND, wintypes.BOOL]
    return user32, shell32, get_long, set_long


def _dropped_paths(shell32, hdrop) -> list[str]:
    """HDROP icindeki tum yollari okur."""
    out: list[str] = []
    count = shell32.DragQueryFileW(hdrop, 0xFFFFFFFF, None, 0)
    for i in range(count):
        need = shell32.DragQueryFileW(hdrop, i, None, 0)
        buf = ctypes.create_unicode_buffer(need + 1)
        shell32.DragQueryFileW(hdrop, i, buf, need + 1)
        if buf.value:
            out.append(buf.value)
    return out


class _DropHook:
    """Kurulan kancayi (ve callback referansini) canli tutan tasiyici.

    ctypes callback'i cop toplayiciya yem olursa Windows cokebilecegi icin
    bu nesnenin cagiran tarafta saklanmasi ZORUNLUDUR.
    """

    def __init__(self, hwnd, old_proc, new_proc, pending):
        self.hwnd = hwnd
        self.pending = pending  # queue.Queue[list[str]] -- birakilan yol gruplari
        self._old = old_proc
        self._new = new_proc  # referansi tut!

    def drain(self):
        """Bekleyen tum birakma gruplarini dondurur (Tk tarafindan cagrilir)."""
        out = []
        while True:
            try:
                out.append(self.pending.get_nowait())
            except queue.Empty:
                return out

    def uninstall(self) -> None:
        try:
            _, shell32, _, set_long = _win_api()
            shell32.DragAcceptFiles(self.hwnd, False)
            set_long(self.hwnd, GWLP_WNDPROC, self._old)
        except Exception:
            pass


def install(widget, on_drop=None):
    """`widget`in penceresine dosya birakmayi acar.

    Birakilan yollar `hook.pending` kuyruguna konur; Tk tarafinda `hook.drain()`
    ile alinir. `on_drop` verilirse yordamin icinden cagrilir -- bu yuzden
    SADECE saf-Python islere izin verilir (Queue.put gibi); Tk'ye dokunamaz.

    Basarili olursa saklanmasi gereken bir nesne, aksi halde None doner.
    """
    try:
        user32, shell32, get_long, set_long = _win_api()
        hwnd = user32.GetParent(widget.winfo_id()) or widget.winfo_id()
        if not hwnd:
            return None

        old_proc = get_long(hwnd, GWLP_WNDPROC)
        if not old_proc:
            return None

        pending: "queue.Queue[list[str]]" = queue.Queue()

        def _proc(h, msg, wparam, lparam):
            if msg == WM_DROPFILES:
                try:
                    paths = _dropped_paths(shell32, wparam)
                finally:
                    shell32.DragFinish(wparam)
                if paths:
                    # Tk'ye BURADA dokunulmaz; sadece kuyruga birak.
                    pending.put(paths)
                    if on_drop is not None:
                        try:
                            on_drop(paths)
                        except Exception:
                            pass
                return 0
            return user32.CallWindowProcW(ctypes.c_void_p(old_proc), h, msg,
                                          wparam, lparam)

        new_proc = _WNDPROC(_proc)
        if not set_long(hwnd, GWLP_WNDPROC, ctypes.cast(new_proc,
                                                        ctypes.c_void_p)):
            # 0 donusu hem hata hem "eski deger 0" olabilir; eskisi 0 degildi.
            pass
        shell32.DragAcceptFiles(hwnd, True)
        return _DropHook(hwnd, old_proc, new_proc, pending)
    except Exception:
        return None
