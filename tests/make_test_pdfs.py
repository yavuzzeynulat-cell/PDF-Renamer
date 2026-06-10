"""Test PDF uretici - cesitli senaryolar icin ornek PDF'ler olusturur.
fitz (PyMuPDF) kullanir. Bu PDF'ler hem mevcut davranisi dogrulamak
hem de yeni ozellikleri (cok sayfa, OCR, kucuk harf) test etmek icindir.
"""
import os
import fitz  # PyMuPDF

OUT = os.path.join(os.path.dirname(__file__), "sample_pdfs")
os.makedirs(OUT, exist_ok=True)


def _new_doc():
    return fitz.open()


def add_text_page(doc, lines, fontsize=12):
    page = doc.new_page(width=595, height=842)  # A4
    y = 72
    for line in lines:
        page.insert_text((72, y), line, fontsize=fontsize, fontname="helv")
        y += fontsize * 1.8
    return page


def save(doc, name):
    path = os.path.join(OUT, name)
    doc.save(path)
    doc.close()
    print("yazildi:", os.path.basename(path))


# 1) Duz metinde kod (mevcut happy-path) -> 26437-LAB-001.pdf beklenir
d = _new_doc()
add_text_page(d, [
    "LABORATUVAR TEST RAPORU",
    "Musteri: Ornek A.S.",
    "Document No: 26437-LAB-001",
    "Tarih: 06.06.2026",
])
save(d, "01_text_kod.pdf")

# 2) Kod sadece ikinci sayfada (mevcut surum BULAMAZ; yeni surum bulmali)
d = _new_doc()
add_text_page(d, ["KAPAK SAYFASI", "Bu sayfada kod yok."])
add_text_page(d, ["DETAY SAYFASI", "Document No: 26437-LAB-205", "Ek bilgiler..."])
save(d, "02_kod_sayfa2.pdf")

# 3) Kodsuz dosya -> 'bulunamadi' beklenir
d = _new_doc()
add_text_page(d, ["GENEL YAZISMA", "Bu belgede bir lab kodu yer almamaktadir."])
save(d, "03_kodsuz.pdf")

# 4) Kucuk harfli kod (mevcut regex KACIRIR; ignore_case ile bulunmali)
d = _new_doc()
add_text_page(d, ["rapor", "document no: 26437-lab-309", "son"])
save(d, "04_kucuk_harf.pdf")

# 5) Taranmis (image-only) PDF -> metin katmani YOK, sadece OCR bulur.
#    Once metni bir sayfaya yazip resme cevirip yeni PDF'e resim olarak gomeriz.
tmp = _new_doc()
add_text_page(tmp, ["TARANMIS BELGE", "Document No: 26437-LAB-777"], fontsize=20)
pix = tmp[0].get_pixmap(dpi=200)
tmp.close()
img_doc = _new_doc()
page = img_doc.new_page(width=pix.width, height=pix.height)
page.insert_image(page.rect, pixmap=pix)
save(img_doc, "05_taranmis.pdf")

# 6) Ayni koddan iki dosya (cakisma testi) -> numarali cozum beklenir
d = _new_doc()
add_text_page(d, ["Document No: 26437-LAB-001", "kopya senaryosu A"])
save(d, "06_cakisma_a.pdf")
d = _new_doc()
add_text_page(d, ["Document No: 26437-LAB-001", "kopya senaryosu B"])
save(d, "07_cakisma_b.pdf")

print("\nTum test PDF'leri olusturuldu ->", OUT)
