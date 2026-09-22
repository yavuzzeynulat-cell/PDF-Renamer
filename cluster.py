"""Kumeleme orkestrasyonu: tumce bul -> kume klasorune kopyala.

`core.py`'in kardesi ama AYRI bir is yapar ve ona hic karismaz:

    core     PDF'teki dokuman kodunu bulur ve dosyayi YERINDE yeniden adlandirir.
    cluster  PDF'te kume adlarini arar ve dosyayi hedef klasorlere KOPYALAR.

Kumeleme dosya adina dokunmaz: dosyalar bu asamaya gelmeden once zaten
dokuman numarasi ile adlandirilmis oluyor. Orijinaller her zaman yerinde
kalir; yalnizca kopya olusur. Geri alma yoktur -- kaynak hic degismedigi
icin gerekmez.

Eslestirmenin kati mi toleransli mi olacagini KULLANICI belirler: arayuzdeki
OCR dugmesi acikken toleransli, kapaliyken birebir eslesme yapilir. Gerekcesi
`grouper.py` basinda anlatiliyor.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional
import os

from config import Settings
import code_finder
import core
import extractor
import grouper
import renamer


# ---- KARARLI VERI SOZLESMESI (GUI buna guvenebilir) -----------------------

@dataclass
class ClusterResult:
    file_name: str                # islenen dosyanin adi
    groups: list                  # eslesen kume adlari (yoksa bos liste)
    status: str                   # 'copied' | 'preview' | 'no_match' | 'error'
    message: str                  # kullaniciya gosterilecek aciklama
    path: str = ""                # kaynak dosyanin TAM YOLU
    copies: list = field(default_factory=list)  # olusan/olusacak tam yollar
    moved: bool = False           # orijinal kaynaktan kaldirildi mi


@dataclass
class ClusterSummary:
    results: list = field(default_factory=list)
    matched: int = 0              # en az bir kumeye giren DOSYA sayisi
    copies: int = 0               # olusan KOPYA sayisi (bir dosya birkac kez)
    moved: int = 0                # kaynaktan kaldirilan DOSYA sayisi
    no_match: int = 0
    errors: int = 0
    # Onizlemede bulunan kumeler: tam-yol -> [kume adlari].
    # Apply asamasinda tekrar okuma/OCR yapmamak icin yeniden kullanilir.
    plan: dict = field(default_factory=dict)

    @property
    def total(self) -> int:
        return len(self.results)


# progress(index, total, ClusterResult) seklinde cagrilir; ilerleme cubugu icin.
ProgressCallback = Callable[[int, int, ClusterResult], None]


def _match(text, settings: Settings) -> list:
    """Bu metinde hangi kume adlari geciyor?

    Iki bagimsiz kaynak, AYNI calistirmada yan yana:

      settings.phrases       sayfa METNINDE aranan tumceler (B0051 Bridge).
                             Toleransi OCR dugmesi belirler (bkz. grouper.py).
      settings.code_filters  belge KODUNDA yer bazli filtreler. Metne hic
                             bakmazlar, bu yuzden sayfada gecen "VALID" gibi
                             kelimeler bir kod filtresine sizamaz.

    Ikisi birbirine karismaz; kullanici da onlari ayri yerden yonetir.
    """
    found = grouper.find_groups(text, settings.phrases,
                                tolerant=settings.use_ocr)
    if settings.code_filters:
        pattern = settings.build_pattern()
        for f in settings.code_filters:
            slots = grouper.slots_of(f)
            if grouper.is_anywhere(f):
                # Yer onemsiz: ID kimi belgede 5., kimindeyse 6. parcada.
                finder = grouper.match_code_anywhere
            else:
                finder = grouper.match_code_slots
            name = finder(text, slots, pattern,
                          ignore_case=settings.ignore_case)
            if name and name not in found:
                found.append(name)
    return found


def cluster_one(pdf_path: str, settings: Settings,
                group_overrides: Optional[dict] = None) -> ClusterResult:
    """Tek bir PDF'i isler: kumeleri bulur ve kopyalarini olusturur.

    `group_overrides` verilir ve bu yol icin kayit varsa metin cikarimi (ve
    varsa OCR) tamamen atlanir; kumeler dogrudan oradan alinir.
    """
    name = os.path.basename(pdf_path)

    if group_overrides is not None and pdf_path in group_overrides:
        groups = list(group_overrides[pdf_path] or [])
    else:
        try:
            text = extractor.extract_text(
                pdf_path,
                all_pages=settings.all_pages,
                use_ocr=settings.use_ocr,
                ocr_lang=settings.ocr_lang,
            )
        except Exception as exc:  # bozuk / okunamayan PDF
            return ClusterResult(name, [], "error",
                                 f"Could not read file: {exc}", pdf_path)
        groups = _match(text, settings)

    if not groups:
        return ClusterResult(name, [], "no_match",
                             "No group name found.", pdf_path)

    # Hedef verilmediyse kumeler dosyanin KENDI klasorunde acilir: arayuzde
    # tek klasor secilir, islenenler alt klasorlere gider, kokte kalanlar
    # "henuz islenmemis" demektir.
    target_root = settings.target_folder or os.path.dirname(pdf_path)

    made: list[str] = []
    for group in groups:
        # Kume adi klasor adi olacak: Windows'ta yasak karakterleri at.
        folder_name = code_finder.clean_filename(group)
        if not folder_name:
            continue
        outcome = renamer.safe_copy(pdf_path,
                                    os.path.join(target_root, folder_name),
                                    dry_run=settings.dry_run)
        if outcome.status == "error":
            return ClusterResult(name, groups, "error", outcome.message,
                                 pdf_path, made)
        made.append(outcome.dest)

    # Mesaj, kume adlarini TEKRARLAMAZ: onlar zaten kendi sutununda duruyor.
    count = len(made)
    plural = "" if count == 1 else "s"
    if settings.dry_run:
        verb = "Will be moved" if settings.move_originals else "Will be copied"
        return ClusterResult(name, groups, "preview",
                             "{0} into {1} folder{2}.".format(verb, count, plural),
                             pdf_path, made)

    # Tasima = once kopyala, KOPYALARI DOGRULA, sonra orijinali kaldir. Sira
    # boyle olmali: dogrulama gecmezse orijinal yerinde kalir ve hicbir
    # kosulda elimizde tek nusha kalmaz.
    moved = False
    if settings.move_originals:
        if _copies_are_sound(pdf_path, made):
            moved = renamer.recycle(pdf_path)

    if moved:
        message = "Moved into {0} folder{1}.".format(count, plural)
    elif settings.move_originals:
        # Tasima istendi ama olmadi. Kullanici listede neden bazi satirlarin
        # "Moved", birinin "Copied" oldugunu anlayamiyordu; sebebi yaziyoruz.
        message = ("Copied into {0} folder{1} - original kept because it "
                   "could not be removed; the file may be open."
                   .format(count, plural))
    else:
        message = "Copied into {0} folder{1}.".format(count, plural)

    return ClusterResult(name, groups, "copied", message,
                         pdf_path, made, moved)


def _cluster_paths(paths: list, settings: Settings,
                   progress: Optional[ProgressCallback] = None,
                   group_overrides: Optional[dict] = None) -> ClusterSummary:
    """Verilen PDF yollarini sirayla kumeler (ortak cekirdek)."""
    summary = ClusterSummary()
    total = len(paths)

    for index, path in enumerate(paths, start=1):
        result = cluster_one(path, settings, group_overrides=group_overrides)
        summary.plan[path] = result.groups

        if result.status in ("copied", "preview"):
            summary.matched += 1
            summary.copies += len(result.copies)
            if result.moved:
                summary.moved += 1
        elif result.status == "no_match":
            summary.no_match += 1
        else:
            summary.errors += 1

        summary.results.append(result)
        if progress is not None:
            progress(index, total, result)

    return summary


def cluster_folder(settings: Settings,
                   progress: Optional[ProgressCallback] = None,
                   group_overrides: Optional[dict] = None) -> ClusterSummary:
    """`settings.folder` icindeki tum PDF'leri kumeler."""
    paths = core.list_pdfs(settings.effective_folder(),
                           recursive=settings.recursive)
    return _cluster_paths(paths, settings, progress, group_overrides)


def cluster_files(paths, settings: Settings,
                  progress: Optional[ProgressCallback] = None,
                  group_overrides: Optional[dict] = None) -> ClusterSummary:
    """Acikca verilen PDF'leri (veya klasorleri) kumeler -- surukle-birak icin."""
    return _cluster_paths(core.expand_pdf_paths(paths, settings.recursive),
                          settings, progress, group_overrides)


def _copies_are_sound(src_path: str, made: list) -> bool:
    """Her kopya diskte var mi ve boyutu orijinalle ayni mi?

    Orijinali kaldirmadan onceki tek kontrol noktasi burasi. Tek bir kopya
    bile eksik ya da yarim ise False doner ve orijinale dokunulmaz.
    """
    if not made:
        return False
    try:
        size = os.path.getsize(src_path)
    except OSError:
        return False
    for dest in made:
        try:
            if not os.path.isfile(dest) or os.path.getsize(dest) != size:
                return False
        except OSError:
            return False
    return True
