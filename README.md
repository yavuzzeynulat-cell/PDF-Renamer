# PDF Otomatik İsimlendirici V2.0

PDF'lerin içindeki doküman kodunu (varsayılan: `26437-LAB-...`) okuyup dosyayı
otomatik olarak `<kod>.pdf` şeklinde yeniden adlandıran araç.

> Bu sürüm, Yavuz'un V1.0 konsol programının üzerine modüler mimari, pencereli
> arayüz, çok sayfalı tarama, OCR desteği ve güvenli geri-alma eklenerek
> geliştirilmiştir. **Eski davranış birebir korunmuştur.**

---

## Hızlı Başlangıç

| Ne istiyorsun | Ne yap |
|---------------|--------|
| **Pencereli arayüz** | `Baslat-Arayuz.bat` dosyasına çift tıkla (veya `python main.py`) |
| **Eski tarz konsol** | `Baslat-Konsol.bat` dosyasına çift tıkla (veya `python cli.py`) |

---

## Yeni Neler Var?

| Özellik | Açıklama |
|---------|----------|
| 🖼️ **Pencereli arayüz (GUI)** | Klasör seç, önizle, uygula, geri al — hepsi tıkla-çalıştır. |
| 📄 **Tüm sayfaları tara** | Kod 2., 3. sayfada olsa bile bulunur (V1 sadece 1. sayfaya bakıyordu). |
| 🔠 **Esnek kod tanıma** | Kod deseni ayarlanabilir; küçük/büyük harf duyarsız arama. |
| 🔁 **Güvenli çakışma** | Aynı koddan çok dosya → `kod (1).pdf`, `kod (2).pdf` (eskisi tek `kopya_` ile bozuluyordu). |
| 👁️ **Önizleme (dry-run)** | Hiçbir şeyi değiştirmeden ne olacağını gösterir. |
| ↩️ **Geri Al** | Son toplu yeniden adlandırmayı tek tıkla geri alır (log dosyası ile). |
| 🔍 **OCR (opsiyonel)** | Taranmış/resim PDF'lerden de kod okur (Tesseract gerekir). |

---

## Kurulum

```powershell
python -m pip install -r requirements.txt
```

`pdfplumber`, `PyMuPDF`, `Pillow` zorunludur. `pytesseract` yalnızca OCR için.

### OCR Kurulumu (yalnızca taranmış PDF'ler için, opsiyonel)

Taranmış (resim) PDF'lerde metin katmanı yoktur; bunları okumak için Tesseract
motoru gerekir. **Kurulu değilse program bozulmaz — sadece o tür dosyaları
"bulunamadı" olarak işaretler.**

1. Tesseract'ı indir ve kur: https://github.com/UB-Mannheim/tesseract/wiki
   (Kurulumda **Turkish** dil paketini de seçin.)
2. Kurulum dizinini PATH'e ekleyin (örn. `C:\Program Files\Tesseract-OCR`).
3. `python -m pip install pytesseract`
4. Arayüzde **"Taranmış PDF için OCR dene"** kutusunu işaretleyin.

---

## Proje Yapısı

```
config.py        # Merkezi ayarlar (Settings)
extractor.py     # PDF'ten metin çıkarma (tüm sayfalar + OCR yedeği)
code_finder.py   # Kod tanıma (esnek desen) + dosya adı temizleme
renamer.py       # Güvenli yeniden adlandırma + log + geri-alma
core.py          # Orkestrasyon: yukarıdakileri birleştirir (process_folder)
gui.py           # Tkinter pencereli arayüz
cli.py           # Konsol sürümü (eski tarz)
main.py          # Giriş noktası (GUI'yi açar)
v1_original.py   # Orijinal V1.0 kodu (yedek)
tests/           # Birim + entegrasyon testleri ve örnek PDF'ler
```

## Testler

```powershell
python -m pytest tests\ -v
```

44 test: birim (extractor, code_finder, renamer) + uçtan uca entegrasyon
(eski davranışın korunması, çok sayfa, çakışma, önizleme, geri-alma).

---

## .exe Olarak Paketleme (isteğe bağlı)

Python kurulu olmayan bilgisayarlarda çalıştırmak için:

```powershell
python -m pip install pyinstaller
pyinstaller --onefile --windowed --name "PDF-Isimlendirici" main.py
```

Çıktı `dist\PDF-Isimlendirici.exe` olur. (OCR kullanılacaksa Tesseract yine
ayrıca hedef bilgisayara kurulmalıdır.)
