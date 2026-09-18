"""
publish_update.py - PDF-Renamer icin GUNCELLEME GONDERME (yayinlama) araci.

Ne yapar:
  1. version.txt'i verilen surume gunceller.
  2. Guncellenebilir kod dosyalarini `src.zip` icine (zip kokunde) paketler.
  3. SHA256 hesaplar.
  4. GitHub'da `v<surum>` release'i olusturur; src.zip ekler, notlara SHA256 yazar.
  5. (Varsa) degisiklikleri git'e commit + push eder.

Kullanicilarin uygulamasi acilista bu release'i gorur ve src.zip'i indirip
kendini gunceller (EXE degil, yalnizca kucuk kod dosyalari iner).

Kullanim:
    python publish_update.py <surum> [degisiklik-notu]
    python publish_update.py 2.0.1 "Tarama hizi duzeltildi"

Genelde dogrudan calistirmak yerine Update-Gonder.bat'i kullan.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
import zipfile

# src/ icine giden (guncellenebilir) dosyalar. Agir bagimliliklar EXE'de gomulu.
SRC_FILES = [
    "main.py", "gui.py", "core.py", "extractor.py", "code_finder.py",
    "renamer.py", "config.py", "theme.py", "cli.py", "updater.py", "dnd.py",
    "grouper.py", "cluster.py", "cluster_tab.py", "guide_tab.py",
    "exporter.py",
    "version.txt",
]


def build_notes(zip_sha: str, setup_sha, extra: str) -> str:
    """Release notlarini kurar (saf - test edilir).

    Istemci iki ayri satir okuyor: src.zip icin 'SHA256:', tam kurulum icin
    'SETUP_SHA256:'. updater ikisini karistirmayacak sekilde ayristirir.
    """
    lines = []
    if extra:
        lines.append(extra)
        lines.append("")
    lines.append("SHA256: " + zip_sha)
    if setup_sha:
        lines.append("SETUP_SHA256: " + setup_sha)
    return "\n".join(lines)


def _run(cmd, cwd):
    print(">", " ".join(cmd))
    return subprocess.run(cmd, cwd=cwd)


def main() -> int:
    if len(sys.argv) < 2:
        print("Kullanim: python publish_update.py <surum> [degisiklik-notu] "
              "[--setup <kurulum.exe>]")
        print('Ornek   : python publish_update.py 2.0.1 "Tarama hizi duzeltildi"')
        return 1

    version = sys.argv[1].lstrip("v").strip()
    # --setup ve yolu bir "degisiklik notu" sanilmamali.
    extras = [a for a in sys.argv[2:] if a != "--setup"]
    if "--setup" in sys.argv:
        target = sys.argv[sys.argv.index("--setup") + 1]
        extras = [a for a in extras if a != target]
    notes_extra = extras[0].strip() if extras else ""
    root = os.path.dirname(os.path.abspath(__file__))

    # 1) version.txt
    with open(os.path.join(root, "version.txt"), "w", encoding="utf-8") as f:
        f.write(version)
    print(f"version.txt -> {version}")

    # 2) src.zip (dosyalar zip kokunde olmali; updater staging'e acip src/ yapar)
    zip_path = os.path.join(tempfile.gettempdir(), "src.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for name in SRC_FILES:
            p = os.path.join(root, name)
            if not os.path.isfile(p):
                print(f"[HATA] Eksik dosya: {name}")
                return 1
            z.write(p, name)
    print(f"src.zip olusturuldu: {zip_path}")

    # 3) SHA256
    h = hashlib.sha256()
    with open(zip_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    sha = h.hexdigest()
    print(f"SHA256: {sha}")

    # 4) GitHub release
    # 4a) Tam kurulum dosyasi (istege bagli): --setup <yol>
    setup_path = None
    setup_sha = None
    if "--setup" in sys.argv:
        setup_path = sys.argv[sys.argv.index("--setup") + 1]
        if not os.path.isfile(setup_path):
            print(f"[HATA] Kurulum dosyasi yok: {setup_path}")
            return 1
        hs = hashlib.sha256()
        with open(setup_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hs.update(chunk)
        setup_sha = hs.hexdigest()
        print(f"setup: {os.path.basename(setup_path)}  SHA256: {setup_sha}")

    body = build_notes(sha, setup_sha, notes_extra)
    tag = "v" + version
    # Ayni tag varsa once temizle (yeniden yayinlamak icin).
    _run(["gh", "release", "delete", tag, "--yes", "--cleanup-tag"], root)
    upload = [zip_path]
    if setup_path:
        # Varlik adi updater.SETUP_ASSET_NAME ile BIREBIR ayni olmali,
        # yoksa istemci kurulum dosyasini goremez.
        staged = os.path.join(tempfile.gettempdir(), "PDF-Renamer-Setup.exe")
        if os.path.abspath(staged) != os.path.abspath(setup_path):
            import shutil as _sh
            _sh.copy2(setup_path, staged)
        upload.append(staged)
    r = _run(["gh", "release", "create", tag] + upload
             + ["--title", tag, "--notes", body], root)
    if r.returncode != 0:
        print("[HATA] GitHub release olusturulamadi (gh giris yapilmis mi?).")
        return r.returncode

    # 5) Kaynagi da senkron tut (best-effort).
    if os.path.isdir(os.path.join(root, ".git")):
        _run(["git", "add", "-A"], root)
        _run(["git", "commit", "-m", f"Release {tag}"], root)
        _run(["git", "push"], root)

    print(f"\n[OK] {tag} yayinlandi. Kullanicilar acilista guncellemeyi gorecek.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
