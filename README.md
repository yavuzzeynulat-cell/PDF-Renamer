# PDF Clerk  ·  v2.2

Taranmış PDF'leri okuyup iki iş yapar:

| Sekme | Ne yapar |
|-------|----------|
| **Rename** | İçindeki doküman kodunu (varsayılan `26437-LAB-...`) okur, dosyayı `<kod>.pdf` olarak **yerinde** yeniden adlandırır. |
| **Cluster** | İçinde geçen *küme adlarını* (örn. `B0051 Bridge`) bulur, dosyayı o adlı klasörlere **dosyalar**. Eşleşenler klasörden kalkar; geriye yalnızca işlenmemişler kalır. |

> Program "PDF Renamer" adıyla, Yavuz'un V1.0 konsol programının üzerine
> modüler mimari, pencereli arayüz, çok sayfalı tarama, OCR ve güvenli
> geri-alma eklenerek doğdu. Kümeleme gelince artık sadece adlandırmadığı
> için **PDF Clerk** adını aldı. **Eski davranış birebir korunmuştur.**
>
> Görünen ad değişti; kurulum kimliği, lisans `PROGRAM_ID`'si, güncelleme
> adresi ve `PDF-Renamer.exe` dosya adı **bilerek** aynı kaldı — bunlar
> değişseydi mevcut kullanıcılarda ikinci bir kurulum olur, lisans kopar ve
> güncelleme dururdu. `tests/test_identity.py` bunu koruyor.

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

### v2.2 ile gelenler

| Özellik | Açıklama |
|---------|----------|
| 🗂️ **Kümeleme (Cluster)** | Başlığın altındaki **Cluster** sekmesi. Yazdığın *küme adlarını* PDF'lerin içinde arar ve her dosyayı, içinde geçen **her** küme adının klasörüne **kopyalar**. Liste, çalıştırdıktan sonra her kümeye kaç dosya düştüğünü gösterir. |

**İki eşleştirme kipi var, seçimi sen yaparsın**

| Kip | Ne yapar |
|-----|----------|
| *Varsayılan* | Yazdığın tümceyi **sayfa metninde** arar. `B0051 Bridge` gibi adlar için doğru olan bu. |
| **Match code segments** | Yalnızca **belge koduna** bakar. Kod tirelerden bölünür ve terimin **ardışık segment dizisi** olarak geçip geçmediğine bakılır. |

Segment kipi, belge numarasının bir bölümüne göre gruplamak için:
`26437-RIA-04C-DR-ID-00022` kodu `26437 · RIA · 04C · DR · ID · 00022`
parçalarına ayrılır.

| Yazdığın | Sonuç | Neden |
|----------|-------|-------|
| `ID` | ✅ | tek segment olarak var |
| `04C-DR-ID` | ✅ | üçü ardışık ve sıralı |
| `DR-ID` | ✅ | ikisi yan yana |
| `RIA-ID` | ❌ | ardışık değil, arada `04C-DR` var |
| `ID-DR` | ❌ | sıra ters |
| `VALID` | ❌ | tam segment değil — segmentin içine bakılmaz |

Sayfada geçen `VALID`, `GRID`, `IDENTIFICATION` gibi kelimeler bu kipte
dosyayı içeri çekmez; düz metin aramasının asıl sorunu buydu.

Hangi kodun okunacağını **Code prefix** belirler (`26437-RIA-` bugün,
`26437-LAB-` yarın). Bu kutu, Rename sekmesindeki önek alanının **aynısıdır**:
birinden değiştirince diğeri de değişir, iki ayrı yerde tutulmaz.

**Kümeleme neyi yapar, neyi yapmaz**

- Dosya **adına dokunmaz** — dosyalar bu aşamaya gelmeden önce zaten
  `26437-LAB-...pdf` diye adlandırılmış oluyor.
- **Orijinaller yerinden oynamaz**, sadece kopya oluşur. Bu yüzden Geri Al yok;
  kaynak hiç değişmiyor.
- Küme klasörleri, seçtiğin **hedef klasörün** içinde açılır — kaynak klasör
  kirlenmez.
- Hiçbir küme adı geçmeyen dosya kopyalanmaz, tabloda *No match* görünür.
- Aynı işi ikinci kez çalıştırırsan koşulsuz tekrar kopyalar; hedefteki dosyanın
  üzerine **yazmaz**, ` (1)` ekleyerek yanına koyar.
- **Preview** diske hiç dokunmadan ne olacağını gösterir.

**Eşleştirme kipi OCR düğmesine bağlıdır** (pencerede hangi kipte olduğun yazar):

| OCR | Eşleştirme |
|-----|------------|
| Kapalı | Birebir — boşluklar ve büyük/küçük harf yazdığın gibi olmalı |
| Açık | Boşluk ve harf duyarsız: `B0051 Bridge` = `B0051Bridge` = `B0051BRIDGE` |

Gerekçesi: taranmış belgelerde OCR boşlukları yiyor. Gerçek bir örnekte
`CORRIDOR 8 AND CORRIDOR 10D` metni `CORRIDOR8ANDCORRIDOR1OD` olarak çıkıyor.
Birebir eşleştirme bu belgelerde hiçbir şey bulamazdı. Metin katmanı olan
PDF'lerde ise boşluklar güvenilir olduğu için gevşetmeye gerek yok.
Bulanık/kısmi eşleşme hiçbir kipte yoktur.

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
grouper.py       # Kümeleme: metinde küme adlarını bulma (saf mantık)
cluster.py       # Kümeleme orkestrasyonu: bul + hedef klasörlere kopyala
cluster_tab.py   # Kümeleme sekmesi (ana pencerede yaşar, sunum katmanı)
updater.py       # GitHub release'lerinden otomatik güncelleme
launcher.py      # EXE giriş noktası: uygulamayı src/ klasöründen yükler
cli.py           # Konsol sürümü (eski tarz)
main.py          # Giriş noktası (GUI'yi açar)
v1_original.py   # Orijinal V1.0 kodu (yedek)
tests/           # Birim + entegrasyon testleri ve örnek PDF'ler
```

## Lisans kapısı

Program açılışında `LisansPaneli` sunucusuna sorar; izin yoksa açılmaz.
Kapı `launcher.py` içindedir — kullanıcının çift tıkladığı tek yer orası, ve
`src/` yüklenmeden önce çalışır.

`license_client.py` bilerek `src/` **dışındadır**: `launcher.py` onu import
ettiği için EXE'ye gömülür. `src/` dosyaları exe'nin yanında düz metin durur,
`SECRET` oraya konsaydı Not Defteri ile okunabilirdi. Ayrıca kapının kendisi,
kapının denetlediği güncelleme kanalıyla değişmemeli.

**Kurulum tamamlanmadan kapı devreye girmez.** `SECRET` yer tutucu olduğu
sürece `require()` sessizce döner ve program normal açılır. Gerçek `SECRET`
yapıştırıldığı an kapı çalışmaya başlar.

Açmak için:

1. Panele gir → **Add a program** → `PROGRAM_ID` ve `SECRET` al
2. `license_client.py` içindeki `SECRET` satırını doldur
   (`PROGRAM_ID` şu an `pdf_renamer` — panel farklı verirse onu da düzelt)
3. `python -m pytest tests	est_license_gate.py tests	est_license_client.py -q`
4. Programı çalıştır → panelde cihaz **Pending** görünür → **+30d** ver

Bu makinenin kodu: `9A71-7EB9-E3A1-6748`

### Kapısız kurulumlar nasıl kapatılıyor

Lisans kapısı **EXE'nin içinde**; `src.zip` güncellemesi EXE'yi değiştiremez.
Yani kapı eklenmeden önce kurulmuş bir kopya, en güncel kodu alsa bile
izinsiz açılmaya devam eder — diğer bilgisayarda tam olarak bu oldu.

`updater.py` artık `src/` ile güncellendiği için kendi EXE'sini sorgulayabiliyor:
`license_client` **yalnızca** kapılı EXE'lerin içine gömülür, `src.zip` ile
dağıtılmaz. Dolayısıyla import edilebiliyorsa kapı vardır.

| Durum | Davranış |
|-------|----------|
| Kapı var, release'te setup var | Tam kurulum **teklif** edilir |
| Kapı **yok**, release'te setup var | Tam kurulum **zorunlu** — reddedilirse program kapanır |
| Release'te setup yok | Yalnızca kod güncellenir |

Bu yüzden **her release'e setup eklenmeli**; aksi halde kapısız kopyalar
kendiliğinden kapanamaz.

> **Dikkat — iki güncelleme sistemi.** Bu program kendi `updater.py`'ı ile
> GitHub release'lerinden güncelleniyor. `license_client` de panel üzerinden
> güncelleme teklif edebiliyor. Panelde R2 henüz açık olmadığı için şu an
> çakışma yok; R2 açılırsa birinden vazgeçilmeli, yoksa kullanıcıya bir
> açılışta iki güncelleme sorulur.

## Testler

```powershell
python -m pytest tests\ -v
```

110 test: birim (extractor, code_finder, renamer, grouper, sürükle-bırak
kancası) + uçtan uca entegrasyon (eski davranışın korunması, çok sayfa,
çakışma, önizleme, geri-alma, dosyaların yerinde işlenmesi, kümeleme) +
paketleme koruması (yeni bir modül src/ listelerinden birine eklenmeyi
unutursa test kırılır).

---

## .exe Olarak Paketleme (isteğe bağlı)

Python kurulu olmayan bilgisayarlarda çalıştırmak için:

```powershell
python -m pip install pyinstaller
pyinstaller --onefile --windowed --name "PDF-Isimlendirici" main.py
```

Çıktı `dist\PDF-Isimlendirici.exe` olur. (OCR kullanılacaksa Tesseract yine
ayrıca hedef bilgisayara kurulmalıdır.)
