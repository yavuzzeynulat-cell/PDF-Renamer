"""Metin cikarma katmani (extractor).

PDF'lerden metin cikarir. Orijinal V1 davranisini KORUR: her sayfada once
duz metni (`extract_text`), ardindan tablo hucrelerini (`extract_tables`)
sirayla toplar. Bu sira, "once duz metin, sonra tablo" onceligini korur ki
asagidaki regex eskisiyle ayni ilk eslesmeyi bulsun.

Iyilestirme: varsayilan olarak TUM sayfalar taranir (cok sayfali belgelerde
2. sayfadaki kodlar da bulunur). Taranmis (metin katmani olmayan) PDF'ler icin
OCR gerilemesi vardir.

OCR motoru onceligi:
  1) RapidOCR (rapidocr-onnxruntime) - KENDI ICINDE paketlenir; son kullanici
     ayrica bir sey kurmak zorunda DEGILDIR. Tercih edilen motordur.
  2) Tesseract (pytesseract) - yalnizca kuruluysa yedek olarak kullanilir.
Hicbir motor yoksa OCR SESSIZCE atlanir; asla hata firlatilmaz.
"""
from __future__ import annotations

import os
import pdfplumber

# OCR icin rasterize DPI'si. 300, basili metinde guvenilir okuma saglar.
_OCR_DPI = 300


# --------------------------------------------------------------------------- #
# Tani (diagnostic) gunlugu
# --------------------------------------------------------------------------- #
# Bazi makinelerde (eksik/bozuk kurulum, antivirus karantinasi, eksik cmap)
# metin cikarma SESSIZCE bos doner; uygulama "kod bulunamadi" der ve neden
# oldugu anlasilamaz. Asagidaki gunluk, her dosya icin hangi motorun ne
# kadar metin urettigini ve olusan hatalari %LOCALAPPDATA%\PDF-Renamer\
# diagnostics.log dosyasina yazar. ASLA hata firlatmaz / akisi yavaslatmaz.
def _diag_path() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "PDF-Renamer")
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        pass
    return os.path.join(d, "diagnostics.log")


def _diag(msg: str) -> None:
    """Tek satir tani gunlugu yazar (en iyi caba; asla patlamaz)."""
    try:
        from datetime import datetime
        with open(_diag_path(), "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat(timespec='seconds')}  {msg}\n")
    except Exception:
        pass

# RapidOCR motoru pahalidir; bir kez kurulup tekrar kullanilir (toplu islerde
# her dosya icin yeniden baslatmamak icin).
_RAPID_ENGINE = None
_RAPID_TRIED = False


# --------------------------------------------------------------------------- #
# OCR motor tespiti
# --------------------------------------------------------------------------- #
def _rapidocr_available() -> bool:
    """RapidOCR (self-contained ONNX motoru) ice aktarilabilir mi?"""
    try:
        import rapidocr_onnxruntime  # noqa: F401
        return True
    except Exception:
        return False


def _tesseract_available() -> bool:
    """Tesseract binary'si + pytesseract kullanilabilir mi?"""
    try:
        import pytesseract  # tembel import

        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def ocr_available() -> bool:
    """Herhangi bir OCR motoru (RapidOCR VEYA Tesseract) kullanilabiliyor mu?"""
    return _rapidocr_available() or _tesseract_available()


def _get_rapid_engine():
    """RapidOCR motorunu (tembel + onbellekli) dondurur; basarisizsa None."""
    global _RAPID_ENGINE, _RAPID_TRIED
    if _RAPID_ENGINE is None and not _RAPID_TRIED:
        _RAPID_TRIED = True
        try:
            from rapidocr_onnxruntime import RapidOCR
            _RAPID_ENGINE = RapidOCR()
        except Exception as exc:
            _diag(f"RapidOCR init FAILED: {exc!r}")
            _RAPID_ENGINE = None
    return _RAPID_ENGINE


# --------------------------------------------------------------------------- #
# Duz metin (pdfplumber) - V1 davranisi
# --------------------------------------------------------------------------- #
def _page_text(page) -> str:
    """Tek bir sayfadan once duz metni, sonra tablo hucrelerini toplar."""
    parts: list[str] = []

    text = page.extract_text()
    if text:
        parts.append(text)

    for table in page.extract_tables() or []:
        for row in table:
            for cell in row:
                if cell:
                    parts.append(str(cell))

    return "\n".join(parts)


# --------------------------------------------------------------------------- #
# Yedek metin motoru (PyMuPDF / fitz) - OCR DEGIL, sadece farkli bir okuyucu
# --------------------------------------------------------------------------- #
def _text_with_fitz(pdf_path: str, all_pages: bool) -> str:
    """PDF metnini PyMuPDF (fitz) ile cikarir; pdfplumber/pdfminer'a YEDEK.

    pdfplumber, pdfminer.six uzerinden okur. Bazi makinelerde pdfminer
    sessizce bos doner (bozuk/eksik kurulum, AV karantinasi, eksik cmap
    verisi). fitz tamamen ayri bir motordur (pdfium tabanli); o makinede
    saglamsa basili metni yine de cikarir. Bu sayede tek bir bilesen bozulsa
    bile uygulama sessizce "kod bulunamadi" demez.

    OCR DEGILDIR: yalnizca metin katmani olan PDF'lerden hizlica metin okur.
    """
    try:
        import fitz  # PyMuPDF
    except Exception as exc:
        _diag(f"fitz import FAILED: {exc!r}")
        return ""

    parts: list[str] = []
    try:
        with fitz.open(pdf_path) as doc:
            pages = list(doc) if all_pages else [doc[0]]
            for page in pages:
                t = page.get_text()
                if t:
                    parts.append(t)
    except Exception as exc:
        _diag(f"fitz get_text FAILED on {os.path.basename(pdf_path)}: {exc!r}")
        return "\n".join(parts)

    return "\n".join(parts)


# --------------------------------------------------------------------------- #
# OCR yollari
# --------------------------------------------------------------------------- #
def _ocr_with_rapidocr(pdf_path: str, all_pages: bool) -> str:
    """Sayfalari PyMuPDF ile rasterize edip RapidOCR ile okur.

    Okunan metin parcalari, sayfadaki konumlarina gore (ust->alt, sol->sag)
    siralanir; boylece kod basina gelen basili etiketler dogru sirayla birikir.
    """
    try:
        import fitz  # PyMuPDF
        import numpy as np
    except Exception:
        return ""

    engine = _get_rapid_engine()
    if engine is None:
        return ""

    parts: list[str] = []
    try:
        with fitz.open(pdf_path) as doc:
            pages = list(doc) if all_pages else [doc[0]]
            for page in pages:
                pix = page.get_pixmap(dpi=_OCR_DPI)
                img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                    pix.height, pix.width, pix.n)
                if pix.n == 4:          # alfa kanalini at
                    img = img[:, :, :3]
                elif pix.n == 1:        # gri tonlamayi 3 kanala genislet
                    img = np.repeat(img, 3, axis=2)

                result, _ = engine(img)
                if not result:
                    continue
                # box = 4 nokta; ust-y ardindan sol-x ile okuma sirasi kur.
                items = sorted(
                    result,
                    key=lambda r: (round(min(p[1] for p in r[0]) / 10),
                                   min(p[0] for p in r[0])))
                parts.append("\n".join(it[1] for it in items))
    except Exception:
        # OCR en iyi caba ile yapilir; elimizdekini dondururuz.
        return "\n".join(parts)

    return "\n".join(parts)


def _ocr_with_tesseract(pdf_path: str, all_pages: bool, ocr_lang: str) -> str:
    """PyMuPDF ile sayfalari rasterize edip pytesseract ile okur (yedek motor)."""
    try:
        import fitz  # PyMuPDF
        import pytesseract
        from PIL import Image
        import io
    except Exception:
        return ""

    parts: list[str] = []
    try:
        with fitz.open(pdf_path) as doc:
            pages = list(doc) if all_pages else [doc[0]]
            for page in pages:
                pix = page.get_pixmap(dpi=_OCR_DPI)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                text = pytesseract.image_to_string(img, lang=ocr_lang)
                if text:
                    parts.append(text)
    except Exception:
        return "\n".join(parts)

    return "\n".join(parts)


def _ocr_pages(pdf_path: str, all_pages: bool, ocr_lang: str) -> str:
    """Mevcut en iyi OCR motoruyla sayfalari okur.

    Once RapidOCR (kendi icinde paketli) denenir; yoksa Tesseract'a duser.
    Hicbiri yoksa bos string doner; asla hata firlatmaz.
    """
    if _rapidocr_available():
        text = _ocr_with_rapidocr(pdf_path, all_pages)
        if text.strip():
            return text
        # RapidOCR bos dondurduyse ve Tesseract da varsa onu da dene.
        if _tesseract_available():
            return _ocr_with_tesseract(pdf_path, all_pages, ocr_lang)
        return text
    if _tesseract_available():
        return _ocr_with_tesseract(pdf_path, all_pages, ocr_lang)
    return ""


# --------------------------------------------------------------------------- #
# Genel API
# --------------------------------------------------------------------------- #
def extract_text(pdf_path: str, *, all_pages: bool = True,
                 use_ocr: bool = False, ocr_lang: str = "tur+eng",
                 match=None) -> str:
    """PDF'ten birlestirilmis tek bir metin string'i dondurur.

    Sayfa sirasini koruyarak, her sayfa icin ONCE duz metni ARDINDAN tablo
    hucrelerini ekler. `all_pages` False ise yalnizca 0. sayfa islenir.

    HIZ: `match` bir callable ise (ornegin "aranan kod su ana kadarki metinde
    var mi?"), kod bulundugu an islem durur. Bu sayede kod 1. sayfanin duz
    metnindeyse o sayfanin PAHALI tablo cikarimi ve sonraki sayfalar atlanir
    (orijinal V1 hizina yakin). Eslesme sirasi birebir korunur: her sayfada
    once duz metin sonra tablolar eklenir, ve ilk eslesme noktasinda donulur.
    `match` None ise davranis eskisiyle aynidir (tam tarama).

    pdfplumber metni bos/bosluk ise ve `use_ocr` True ve bir OCR motoru
    (RapidOCR veya Tesseract) mevcutsa, sayfalar rasterize edilip OCR denenir.
    OCR motoru yoksa SESSIZCE atlanir; bu durumda hata firlatilmaz.
    """
    parts: list[str] = []

    with pdfplumber.open(pdf_path) as pdf:
        pages = pdf.pages if all_pages else pdf.pages[:1]
        for page in pages:
            text = page.extract_text()
            if text:
                parts.append(text)
                # Erken cikis: kod duz metinde bulunduysa tablolari/sonraki
                # sayfalari (pahali) tarama.
                if match is not None and match("\n".join(parts)):
                    return "\n".join(parts)

            for table in page.extract_tables() or []:
                for row in table:
                    for cell in row:
                        if cell:
                            parts.append(str(cell))

            if match is not None and match("\n".join(parts)):
                return "\n".join(parts)

    text = "\n".join(parts)

    name = os.path.basename(pdf_path)
    matched = (match is not None and match(text))

    # YEDEK MOTOR (ucuz, OCR DEGIL): pdfplumber/pdfminer hicbir sey bulamadiysa
    # (bos metin VEYA aranan kod yok), tamamen ayri bir motorla (PyMuPDF/fitz)
    # tekrar dene. Bazi makinelerde pdfminer sessizce bos doner; fitz saglamsa
    # basili metni yine de cikarir. Yalnizca hizli yol basarisiz oldugunda
    # calisir; bu yuzden olagan durumda hiz etkilenmez.
    if (not text.strip()) or (match is not None and not matched):
        pp_chars = len(text)
        ftext = _text_with_fitz(pdf_path, all_pages)
        if ftext.strip():
            fitz_has_code = (match is not None and match(ftext))
            if not text.strip():
                # pdfplumber bostu: fitz metnini kullan.
                text = ftext
                _diag(f"{name}: pdfplumber=EMPTY fitz_chars={len(ftext)} "
                      f"fitz_has_code={fitz_has_code}")
            elif fitz_has_code:
                # pdfplumber kodu bulamadi ama fitz buldu: birlestir.
                text = text + "\n" + ftext
                _diag(f"{name}: pdfplumber_no_code fitz RESCUED code "
                      f"(pp_chars={pp_chars} fitz_chars={len(ftext)})")
            else:
                _diag(f"{name}: pdfplumber_no_code fitz_no_code "
                      f"pp_chars={pp_chars} fitz_chars={len(ftext)}")
        else:
            _diag(f"{name}: pdfplumber_chars={pp_chars} fitz=EMPTY "
                  f"(metin katmani yok olabilir; OCR gerekebilir)")

    # OCR (pahali): metin katmani olmayan TARANMIS sayfalar icin son care.
    if not text.strip() and use_ocr and ocr_available():
        text = _ocr_pages(pdf_path, all_pages, ocr_lang)
        _diag(f"{name}: OCR ran -> chars={len(text)}")

    return text
