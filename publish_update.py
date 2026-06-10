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
    "renamer.py", "config.py", "theme.py", "cli.py", "updater.py", "version.txt",
]


def _run(cmd, cwd):
    print(">", " ".join(cmd))
    return subprocess.run(cmd, cwd=cwd)


def main() -> int:
    if len(sys.argv) < 2:
        print("Kullanim: python publish_update.py <surum> [degisiklik-notu]")
        print('Ornek   : python publish_update.py 2.0.1 "Tarama hizi duzeltildi"')
        return 1

    version = sys.argv[1].lstrip("v").strip()
    notes_extra = sys.argv[2].strip() if len(sys.argv) > 2 else ""
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
    body = (notes_extra + "\n\n" if notes_extra else "") + f"SHA256: {sha}"
    tag = "v" + version
    # Ayni tag varsa once temizle (yeniden yayinlamak icin).
    _run(["gh", "release", "delete", tag, "--yes", "--cleanup-tag"], root)
    r = _run(["gh", "release", "create", tag, zip_path,
              "--title", tag, "--notes", body], root)
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
