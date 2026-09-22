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
    "code_filter_dialog.py",
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


# EXE'nin ICINE gomulen seyler. Bunlardan biri degisirse kullanicilara
# ancak yeni bir kurulum dosyasiyla ulasir; src.zip exe'nin icine dokunamaz.
# Geri kalan her sey (gui, cluster, updater...) exe'nin YANINDAKI src/
# klasorunde yasar ve src.zip ile gider -- onlar icin derleme gereksiz.
EXE_EMBEDDED = (
    "launcher.py",        # PyInstaller giris noktasi
    "license_client.py",  # lisans kapisi
    "license_secret.txt",  # kapinin sirri (derleme aninda gomulur)
    "PDF-Renamer.spec",   # derleme tarifi
    "requirements.txt",   # agir bagimliliklar
    "installer.iss",      # kurulum betigi
)
EXE_EMBEDDED_DIRS = ("assets/",)   # ikon vb.


def exe_needs_rebuild(changed_paths) -> str:
    """Bu degisiklikler EXE'yi yeniden derlemeyi gerektiriyor mu?

    Gerekiyorsa sebebi (dosya adlari) doner, gerekmiyorsa bos dize.

    Karar mekanik ama bugune kadar KULLANICIYA birakilmisti ve unutulunca
    release'e bayat bir setup.exe gidiyordu -- v2.2.8'den v2.3.2'ye kadar
    her release'e icinde 2.2.7 olan ayni dosya yuklendi. Guncelleme
    gondermek tek hareket olmali; bu yuzden karari araca verdik.
    """
    hits = []
    for raw in changed_paths or ():
        path = str(raw).replace("\\", "/").strip()
        name = path.rsplit("/", 1)[-1]
        if name in EXE_EMBEDDED or path in EXE_EMBEDDED:
            hits.append(path)
        elif any(path.startswith(d) for d in EXE_EMBEDDED_DIRS):
            hits.append(path)
    return ", ".join(hits)


def changed_since_last_release(root: str) -> list:
    """Son release etiketinden bu yana degisen dosyalar.

    Etiket yoksa (ilk yayin) bos liste doner: elde karsilastiracak bir sey
    olmadan derlemeye zorlamanin anlami yok.

    ONCE `git fetch --tags`: release'ler `gh` ile UZAKTA olusuyor, yerel
    depoya etiket inmiyor. Olculdu -- yerel etiketler v2.2.3'te kalmisken
    uzakta v2.3.3 vardi, yani karsilastirma tabani dokuz surum eskiydi ve
    degismemis dosyalar degismis gorunup gereksiz yere derleme tetikliyordu.
    """
    try:
        subprocess.run(["git", "fetch", "--tags", "--quiet"],
                       cwd=root, capture_output=True, text=True)
        tag = subprocess.run(["git", "describe", "--tags", "--abbrev=0"],
                             cwd=root, capture_output=True, text=True)
        if tag.returncode != 0 or not tag.stdout.strip():
            return []
        diff = subprocess.run(
            ["git", "diff", "--name-only", tag.stdout.strip() + "..HEAD"],
            cwd=root, capture_output=True, text=True)
        if diff.returncode != 0:
            return []
        return [line for line in diff.stdout.splitlines() if line.strip()]
    except OSError:
        return []


def check_setup_is_fresh(version: str, dist_dir: str) -> str:
    """Kurulum dosyasi bu surum icin mi derlenmis? Sorun varsa aciklamasi.

    Kurulum dosyasi `dist/PDF-Renamer/` klasorunden paketlenir, yani icindeki
    `src/version.txt` setup.exe'nin GERCEKTEN kuracagi surumdur.

    Bu kontrol bir gercek olaydan dogdu: v2.2.8'den v2.3.2'ye kadar her
    release'e ayni setup.exe yuklendi, cunku aradaki surumler icin
    Derle-EXE/Derle-Installer tekrar calistirilmamisti. Kullanicinin makinesi
    110 MB indiriyor, kuruyor, surum yine eski kaliyordu -- disaridan bakinca
    "guncelleme inmiyor/kurulmuyor" gibi gorunuyor ve hatayi bulmak cok zor.
    """
    vfile = os.path.join(dist_dir, "src", "version.txt")
    if not os.path.isfile(vfile):
        return ("Kurulum dosyasinin kaynagi yok: %s\n"
                "Once Derle-EXE.bat, sonra Derle-Installer.bat calistir."
                % vfile)
    with open(vfile, "r", encoding="utf-8") as f:
        built = f.read().strip()
    if built != version:
        return ("Kurulum dosyasi BAYAT: icinde %s var, yayinlanan surum %s.\n"
                "Once Derle-EXE.bat, sonra Derle-Installer.bat calistir."
                % (built, version))
    return ""


def _run(cmd, cwd):
    print(">", " ".join(cmd))
    return subprocess.run(cmd, cwd=cwd)


def build_exe_and_installer(root: str) -> str:
    """EXE'yi ve kurulum dosyasini derler. Hata varsa aciklamasi doner.

    Kullanicinin elle iki bat calistirmasi gerekmesin diye burada:
    "guncelleme gonder" tek hareket olmali.
    """
    print("\n=== EXE yeniden derleniyor (birkac dakika surebilir) ===")
    r = _run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
              "PDF-Renamer.spec"], root)
    if r.returncode != 0:
        return "PyInstaller derlemesi basarisiz."

    # Derle-EXE.bat'in yaptigi kopyalama: guncellenebilir kod dist'e gider.
    # Ayni listeden beslenir, yoksa ikisi birbirinden kayar.
    dist_src = os.path.join(root, "dist", "PDF-Renamer", "src")
    os.makedirs(dist_src, exist_ok=True)
    import shutil
    for name in SRC_FILES:
        shutil.copy2(os.path.join(root, name), os.path.join(dist_src, name))
    print(f"src/ -> {dist_src}")

    print("\n=== Kurulum dosyasi olusturuluyor ===")
    if not shutil.which("iscc"):
        return ("Inno Setup bulunamadi (iscc). "
                "https://jrsoftware.org/isdl.php")
    r = _run(["iscc", "installer.iss"], root)
    if r.returncode != 0:
        return "Inno Setup derlemesi basarisiz."
    return ""


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

    # 1) version.txt -- derlemeden ONCE yazilmali, yoksa uretilen exe eski
    #    surumu tasir ve check_setup_is_fresh onu hakli olarak reddeder.
    with open(os.path.join(root, "version.txt"), "w", encoding="utf-8") as f:
        f.write(version)
    print(f"version.txt -> {version}")

    # 1b) EXE'yi yeniden derlemek gerekiyor mu? Karari arac verir; kullaniciya
    #     birakildiginda unutuluyor ve release'e bayat bir setup gidiyordu.
    if "--setup" not in sys.argv:
        reason = exe_needs_rebuild(changed_since_last_release(root))
        if reason:
            print("EXE'ye gomulu dosyalar degismis: " + reason)
            problem = build_exe_and_installer(root)
            if problem:
                print("[HATA] " + problem)
                return 1
            sys.argv += ["--setup", os.path.join(root, "installer_output",
                                                 "PDF-Renamer-Setup.exe")]
        else:
            print("EXE'ye gomulu hicbir sey degismemis; "
                  "yalnizca kod gonderilecek.")

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
        stale = check_setup_is_fresh(version, os.path.join(root, "dist",
                                                           "PDF-Renamer"))
        if stale:
            print("[HATA] " + stale)
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
