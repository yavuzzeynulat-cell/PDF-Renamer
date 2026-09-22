"""Hicbir yazi bir digerinin ustune binmesin.

Arayuz canvas'a MUTLAK koordinatlarla ciziliyor; bir yaziyi uzatmak ya da
bir ogeyi kaydirmak sessizce bir baskasinin ustune bindirebiliyor. Goz
karariyla yakalanmiyor, o yuzden makine bakiyor: her sekme icin gorunur
butun yazilarin sinir kutulari ikiser ikiser karsilastiriliyor.

Gorsel ogeler (arka plan, dugmeler, seritler) disarida: onlarin yazinin
ALTINDA olmasi zaten tasarimin bir parcasi. Sorun yazi-yazi cakismasi.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

tk = pytest.importorskip("tkinter")


@pytest.fixture(scope="module")
def app():
    import tkinter
    try:
        root = tkinter.Tk()
    except tkinter.TclError:  # ekransiz ortam
        pytest.skip("Tk penceresi acilamiyor")
    root.geometry("1080x880+0+0")
    import gui
    application = gui.App(root)
    root.update_idletasks()
    yield application
    root.destroy()


def _visible_texts(application):
    """Su an gorunur olan yazi ogeleri: (item_id, metin, bbox)."""
    canvas = application.canvas
    out = []
    for item in canvas.find_all():
        if canvas.type(item) != "text":
            continue
        if canvas.itemcget(item, "state") == "hidden":
            continue
        if not canvas.itemcget(item, "text").strip():
            continue      # bos yer tutucular (durum satiri vb.)
        box = canvas.bbox(item)
        if box:
            out.append((item, canvas.itemcget(item, "text"), box))
    return out


def _overlap(a, b, slack=2):
    """Iki sinir kutusu ANLAMLI olcude kesisiyor mu?"""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    dx = min(ax2, bx2) - max(ax1, bx1)
    dy = min(ay2, by2) - max(ay1, by1)
    return dx > slack and dy > slack


# Kullanici pencereyi buyutebiliyor; yeniden akis yeni cakismalar
# dogurabilir, o yuzden iki olcuye de bakiyoruz.
SIZES = [(1080, 880), (1520, 1000)]


@pytest.mark.parametrize("size", SIZES, ids=["tasarim-olcusu", "buyutulmus"])
@pytest.mark.parametrize("tab", ["rename", "cluster", "guide"])
def test_no_two_labels_sit_on_top_of_each_other(app, tab, size):
    width, height = size
    app.root.geometry("%dx%d+0+0" % (width, height))
    app.root.update_idletasks()
    app._relayout(width, height)
    app.show_tab(tab)
    app.root.update_idletasks()

    items = _visible_texts(app)
    clashes = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            _, text_a, box_a = items[i]
            _, text_b, box_b = items[j]
            if _overlap(box_a, box_b):
                clashes.append("{0!r} <-> {1!r}".format(
                    text_a[:42], text_b[:42]))

    assert not clashes, (
        "'" + tab + "' sekmesinde ust uste binen yazilar:\n  "
        + "\n  ".join(clashes))


# ---------------------------------------------------------------------------
# Gomulu pencereler (Entry, liste, ilerleme cubugu) yukaridaki kontrolun
# disindaydi: canvas onlari "window" olarak tutuyor, "text" olarak degil.
# Oysa asil sessiz hata orada: bir listeyi uzatmak ya da araya yeni bir alan
# koymak, altindaki kutunun uzerine biner ve GORUNMEZ olur -- yazi cakismasi
# gibi goze de batmaz, cunku ustteki widget digerini tamamen orter.
# ---------------------------------------------------------------------------

def _visible_windows(application):
    """Su an gorunur olan gomulu widget'lar: (metin-etiketi, bbox)."""
    canvas = application.canvas
    out = []
    for item in canvas.find_all():
        if canvas.type(item) != "window":
            continue
        if canvas.itemcget(item, "state") == "hidden":
            continue
        widget = canvas.itemcget(item, "window")
        box = canvas.bbox(item)
        if box:
            out.append((widget or ("window#%d" % item), box))
    return out


@pytest.mark.parametrize("size", SIZES, ids=["tasarim-olcusu", "buyutulmus"])
@pytest.mark.parametrize("tab", ["rename", "cluster", "guide"])
def test_no_two_input_boxes_sit_on_top_of_each_other(app, tab, size):
    width, height = size
    app.root.geometry("%dx%d+0+0" % (width, height))
    app.root.update_idletasks()
    app._relayout(width, height)
    app.show_tab(tab)
    app.root.update_idletasks()

    items = _visible_windows(app)
    clashes = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            name_a, box_a = items[i]
            name_b, box_b = items[j]
            if _overlap(box_a, box_b):
                clashes.append("{0} <-> {1}".format(name_a, name_b))

    assert not clashes, (
        "'" + tab + "' sekmesinde ust uste binen kutular:\n  "
        + "\n  ".join(clashes))


@pytest.mark.parametrize("size", SIZES, ids=["tasarim-olcusu", "buyutulmus"])
@pytest.mark.parametrize("tab", ["rename", "cluster", "guide"])
def test_no_input_box_covers_a_label(app, tab, size):
    """Bir kutu bir yazinin ustune binerse yazi tamamen kaybolur."""
    width, height = size
    app.root.geometry("%dx%d+0+0" % (width, height))
    app.root.update_idletasks()
    app._relayout(width, height)
    app.show_tab(tab)
    app.root.update_idletasks()

    clashes = []
    for name, box_w in _visible_windows(app):
        for _, text, box_t in _visible_texts(app):
            if _overlap(box_w, box_t):
                clashes.append("{0} ustune biniyor: {1!r}".format(
                    name, text[:42]))

    assert not clashes, (
        "'" + tab + "' sekmesinde yaziyi orten kutular:\n  "
        + "\n  ".join(clashes))
