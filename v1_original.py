import pdfplumber
import os
import re

def temiz_dosya_adi(metin):
    """Dosya adındaki yasaklı karakterleri siler."""
    return re.sub(r'[\\/*?:"<>|]', "", str(metin)).strip()

def kodu_bul(metin):
    """PDF içindeki metinde 26437- ile başlayan kodu arar."""
    match = re.search(r'26437-LAB-[A-Z0-9-]+', metin)
    if match:
        return match.group(0)
    return None

def baslat():
    print("========================================")
    print("   PDF OTOMATIK ISIMLENDIRICI V1.0")
    print("========================================")

    basarili_sayisi = 0
    hata_sayisi = 0
    mevcut_dizin = os.getcwd()

    # Klasördeki PDF dosyalarını listele
    dosyalar = [f for f in os.listdir(mevcut_dizin) if f.lower().endswith(".pdf")]

    if not dosyalar:
        print("\n[!] HATA: Klasörde hiç PDF dosyası bulunamadı!")
        print(f"Konum: {mevcut_dizin}")
        return

    for dosya in dosyalar:
        print(f"\nİşleniyor: {dosya}")

        try:
            with pdfplumber.open(dosya) as pdf:
                bulunan_kod = None
                sayfa = pdf.pages[0]

                # 1. YÖNTEM: Sayfadaki tüm düz metni tara
                metin = sayfa.extract_text()
                if metin:
                    bulunan_kod = kodu_bul(metin)

                # 2. YÖNTEM: Eğer metinde yoksa tablolara bak
                if not bulunan_kod:
                    tablolar = sayfa.extract_tables()
                    for tablo in tablolar:
                        for satir in tablo:
                            for hucre in satir:
                                if hucre:
                                    bulunan_kod = kodu_bul(str(hucre))
                                    if bulunan_kod: break
                            if bulunan_kod: break
                        if bulunan_kod: break

                if bulunan_kod:
                    yeni_isim = temiz_dosya_adi(bulunan_kod) + ".pdf"
                    pdf.close() # İsmi değiştirmek için dosyayı serbest bırak

                    # Eğer dosya zaten o isimdeyse işlem yapma
                    if dosya == yeni_isim:
                        print(f"[!] Dosya zaten doğru isimlendirilmiş.")
                    else:
                        # Eğer aynı isimde başka dosya varsa çakışmayı önle
                        if os.path.exists(yeni_isim):
                            yeni_isim = "kopya_" + yeni_isim

                        os.rename(dosya, yeni_isim)
                        print(f"[OK] Yeni İsim: {yeni_isim}")
                        basarili_sayisi += 1
                else:
                    print(f"[X] HATA: PDF içinde '26437-' kodu bulunamadı.")
                    hata_sayisi += 1

        except Exception as e:
            print(f"[!] KRITIK HATA: {dosya} dosyası okunamadı. ({e})")
            hata_sayisi += 1

    print("\n" + "="*40)
    print(f"İŞLEM TAMAMLANDI!")
    print(f"Başarıyla Değişen: {basarili_sayisi}")
    print(f"Hatalı/Bulunamayan: {hata_sayisi}")
    print("="*40)

if __name__ == "__main__":
    baslat()
    input("\nÇıkmak için Enter tuşuna basın...")
