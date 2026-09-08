# PDF Otomatik İsimlendirici V2.1

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
| 🔍 **OCR** | Taranmış/resim PDF'lerden de kod okur (RapidOCR programla birlikte gelir). |

### v2.1 ile gelenler

| Özellik | Açıklama |
|---------|----------|
| 🖱️ **Sürükle-bırak** | PDF'leri (veya klasörleri) pencereye bırak — hepsi listeye düşer ve önizlenir. **Dosyalar yerinden oynamaz**, bulundukları klasörde yeniden adlandırılır. |
| ➕ **+ Add PDFs** | Sürükle-bırak yerine dosya seçme penceresiyle de aynı işi yapar. |
| 👆 **Çift tık / sağ tık** | Satıra çift tıkla PDF açılır; sağ tık menüsünde *PDF'i aç*, *Klasörde göster*, *Yeni adı kopyala*. |
| 🔎 **Filtre + arama** | `All / Renamed / Already OK / Not found / Error` düğmeleri (canlı sayaçlı) ve anlık arama kutusu. |
| 📤 **Export** | Görünen satırları CSV olarak kaydeder (UTF-8 BOM + `;` — Excel'de çift tıkla düzgün açılır). |

---

## Kurulum

```powershell
python -m pip install -r requirements.txt
```

`pdfplumber`, `PyMuPDF`, `Pillow` zorunludur. `pytesseract` yalnızca OCR için.

### OCR (yalnızca taranmış PDF'ler için)

Taranmış (resim) PDF'lerde metin katmanı yoktur. Bunlar için **RapidOCR**
kullanılır ve kurulum paketinin içinde gelir — son kullanıcının ayrıca
bir şey kurması gerekmez (Tesseract gerekmez).

Arayüzde **OCR (scanned PDFs)** düğmesini açmanız yeterli. OCR yavaş
olduğu için varsayılan olarak kapalıdır.

---

## Proje Yapısı

```
config.py        # Merkezi ayarlar (Settings)
extractor.py     # PDF'ten metin çıkarma (tüm sayfalar + OCR yedeği)
code_finder.py   # Kod tanıma (esnek desen) + dosya adı temizleme
renamer.py       # Güvenli yeniden adlandırma + log + geri-alma
core.py          # Orkestrasyon: klasör (process_folder) + dosya listesi (process_files)
gui.py           # Tkinter pencereli arayüz
dnd.py           # Windows sürükle-bırak kancası (WM_DROPFILES, ek paket yok)
updater.py       # GitHub release'lerinden otomatik güncelleme
launcher.py      # EXE giriş noktası: uygulamayı src/ klasöründen yükler
cli.py           # Konsol sürümü (eski tarz)
main.py          # Giriş noktası (GUI'yi açar)
v1_original.py   # Orijinal V1.0 kodu (yedek)
tests/           # Birim + entegrasyon testleri ve örnek PDF'ler
```

## Testler

```powershell
python -m pytest tests\ -v
```

67 test: birim (extractor, code_finder, renamer, sürükle-bırak kancası) +
uçtan uca entegrasyon (eski davranışın korunması, çok sayfa, çakışma,
önizleme, geri-alma, dosyaların yerinde işlenmesi).

---

## .exe Olarak Paketleme (isteğe bağlı)

Python kurulu olmayan bilgisayarlarda çalıştırmak için:

```powershell
python -m pip install pyinstaller
pyinstaller --onefile --windowed --name "PDF-Isimlendirici" main.py
```

Çıktı `dist\PDF-Isimlendirici.exe` olur. (OCR kullanılacaksa Tesseract yine
ayrıca hedef bilgisayara kurulmalıdır.)
