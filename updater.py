"""
updater.py - PDF-Renamer icin otomatik guncelleme (GitHub Releases tabanli).

CubeLogReader'daki kanitlanmis sistemin aynisi: EXE'nin yanindaki `src/`
klasorundeki kod dosyalari `src.zip` ile guncellenir; agir bagimliliklar
(onnxruntime, pdfplumber vb.) EXE'de gomulu kalir, internetten YALNIZCA kucuk
kod dosyalari iner.

Public API:
    check_for_update(timeout=5) -> Optional[UpdateInfo]
    download_update(info, dest_path) -> bool
    apply_update(zip_path) -> None
    restart_app() -> NoReturn
    run_update_flow(info, parent_window=None) -> bool
    current_version() -> str

Tum ag hatalari sessizce yutulur (None/False doner) ki cevrimdisi olsa bile
uygulama calismaya devam etsin.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.request
import zipfile
from dataclasses import dataclass
from typing import Optional

# === CONFIG ===
GITHUB_OWNER = "yavuzzeynulat-cell"
GITHUB_REPO = "PDF-Renamer"
RELEASE_API = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
ASSET_NAME = "src.zip"
# Tam kurulum dosyasi. src.zip exe'nin YANINDAKI kodu degistirir; exe'nin
# kendisi (ve icine gomulu lisans kapisi) ancak bununla yenilenir.
SETUP_ASSET_NAME = "PDF-Renamer-Setup.exe"
# Kurulum logu: basarisiz bir guncellemeden geriye tek kalan sey.
INSTALL_LOG_NAME = "install.log"
# Release notlarina bu yazilirsa, kapisi olan makineler de tam kurulum
# yapar. Yalnizca EXE'nin kendisi degistiginde (yeni agir bagimlilik,
# lisans istemcisinde degisiklik) gerekir.
FULL_INSTALL_MARKER = "FULL_INSTALL"
_UA = "PDF-Renamer-Updater"


@dataclass
class UpdateInfo:
    version: str            # ornek "2.0.1" ("v" onsuz)
    notes: str              # release aciklamasi (Turkce, cok satirli)
    asset_url: str          # src.zip dogrudan indirme URL'si
    sha256: Optional[str]   # notlardan okunur; yoksa None
    # Tam kurulum (istege bagli). SADECE hem dosya hem 64 haneli gecerli bir
    # SETUP_SHA256 varsa doldurulur; biri eksikse ikisi de None kalir, cunku
    # dogrulanamayan bir calistirilabilir dosya asla teklif edilmemeli.
    setup_url: Optional[str] = None
    setup_sha256: Optional[str] = None


def _app_dir() -> str:
    """Calisan exe'nin (veya dev'de bu dosyanin) klasoru."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _read_local_version() -> str:
    """version.txt'i src/ (frozen) ya da bu dosyanin yanindan (dev) okur."""
    candidates = [
        os.path.join(_app_dir(), "src", "version.txt"),
        os.path.join(_app_dir(), "version.txt"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "version.txt"),
    ]
    for p in candidates:
        if os.path.isfile(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return f.read().strip()
            except OSError:
                pass
    return "0.0.0"


def current_version() -> str:
    """Yerel surum (ornek '2.0.0')."""
    return _read_local_version()


def _parse_version(s: str) -> tuple:
    """'2.0.1' -> (2,0,1). Gecersiz -> (0,0,0)."""
    try:
        return tuple(int(x) for x in s.strip().lstrip("v").split("."))
    except (ValueError, AttributeError):
        return (0, 0, 0)


def _fetch_latest_release_json(timeout: int = 5) -> dict:
    """Son release'i GET eder. Ag hatasinda OSError firlatir."""
    req = urllib.request.Request(
        RELEASE_API,
        headers={"Accept": "application/vnd.github+json", "User-Agent": _UA},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _parse_sha256(body: str) -> Optional[str]:
    """Release notlarinda 'SHA256: <hex>' arar (buyuk/kucuk harf duyarsiz)."""
    if not body:
        return None
    # Onunde harf/rakam/alt-cizgi OLMAYAN bir SHA256 ara; boylece
    # "SETUP_SHA256: ..." satiri src.zip'in ozeti sanilmaz.
    m = re.search(r"(?<![A-Za-z0-9_])SHA256\s*[:=]\s*([0-9a-fA-F]+)", body)
    return m.group(1).lower() if m else None


def _parse_setup_sha256(body: str) -> Optional[str]:
    """Notlarda 'SETUP_SHA256: <64 hane>' arar. Tam 64 hane sart."""
    if not body:
        return None
    m = re.search(r"SETUP_SHA256\s*[:=]\s*([0-9a-fA-F]{64})", body)
    return m.group(1).lower() if m else None


def check_for_update(timeout: int = 5) -> Optional[UpdateInfo]:
    """Daha yeni bir release varsa UpdateInfo doner; yoksa None.

    Herhangi bir hatada (ag, parse, eksik alan) SESSIZCE None doner.
    """
    try:
        data = _fetch_latest_release_json(timeout=timeout)
        tag = data.get("tag_name")
        if not tag:
            return None
        remote_v = tag.lstrip("v")
        if _parse_version(remote_v) <= _parse_version(_read_local_version()):
            return None
        asset_url = None
        for a in data.get("assets", []):
            if a.get("name") == ASSET_NAME:
                asset_url = a.get("browser_download_url")
                break
        if not asset_url:
            return None
        body = data.get("body", "") or ""

        # Tam kurulum: dosya VE gecerli ozet birlikte olmali.
        setup_url = None
        for a in data.get("assets", []):
            if a.get("name") == SETUP_ASSET_NAME:
                setup_url = a.get("browser_download_url")
                break
        setup_sha = _parse_setup_sha256(body)
        if not (setup_url and setup_sha):
            setup_url = setup_sha = None

        return UpdateInfo(
            version=remote_v,
            notes=body,
            asset_url=asset_url,
            sha256=_parse_sha256(body),
            setup_url=setup_url,
            setup_sha256=setup_sha,
        )
    except Exception:
        return None


def _http_download(url: str, dest: str, timeout: int = 30,
                   progress=None) -> None:
    """`url`'i `dest`'e akitarak indirir. Hata durumunda OSError.

    `progress(inen_bayt, toplam_bayt)` her parcada cagrilir. Kurulum dosyasi
    ~110 MB; ilerleme bildirilmezse program uzun sure donmus gorunuyor.
    Toplam bilinmiyorsa 0 gonderilir.
    """
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        try:
            total = int(resp.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            total = 0
        done = 0
        with open(dest, "wb") as f:
            while True:
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if progress is not None:
                    progress(done, total)


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(64 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download_update(info: "UpdateInfo", dest_path: str, timeout: int = 30) -> bool:
    """src.zip'i indirir, SHA256 (varsa) ve zip butunlugunu dogrular."""
    try:
        _http_download(info.asset_url, dest_path, timeout=timeout)
    except Exception:
        _safe_remove(dest_path)
        return False

    if info.sha256:
        actual = _sha256_file(dest_path)
        if actual.lower() != info.sha256.lower():
            _safe_remove(dest_path)
            return False

    try:
        with zipfile.ZipFile(dest_path, "r") as zf:
            bad = zf.testzip()
            if bad is not None:
                raise zipfile.BadZipFile(f"corrupt entry: {bad}")
    except Exception:
        _safe_remove(dest_path)
        return False

    return True


def _safe_remove(path: str) -> None:
    if os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            pass


def _force_writable(path: str) -> None:
    try:
        os.chmod(path, stat.S_IWRITE)
    except OSError:
        pass


def _rmtree_onerror(func, path, _exc) -> None:
    _force_writable(path)
    try:
        func(path)
    except OSError:
        pass


def _robust_rmtree(path: str, attempts: int = 5) -> None:
    """Salt-okunur dosyalara ve gecici antivirus kilitlerine ragmen siler."""
    for _ in range(attempts):
        if not os.path.isdir(path):
            return
        shutil.rmtree(path, onerror=_rmtree_onerror)
        if not os.path.isdir(path):
            return
        time.sleep(0.4)
    if os.path.isdir(path):
        raise OSError(f"Klasor silinemedi (kilitli?): {path}")


def _robust_rename(src: str, dst: str, attempts: int = 5) -> None:
    """Yeniden deneme ile os.rename - antivirus taze dosyalari kisa sure kilitler."""
    last_err: Optional[OSError] = None
    for _ in range(attempts):
        try:
            os.rename(src, dst)
            return
        except OSError as e:
            last_err = e
            time.sleep(0.4)
    raise last_err if last_err else OSError(f"rename failed: {src} -> {dst}")


def _log_update_error() -> str:
    """Hatayi exe yanindaki update_error.log'a ekler. Asla firlatmaz."""
    log_path = os.path.join(_app_dir(), "update_error.log")
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write("=== update failed ===\n")
            f.write(traceback.format_exc())
            f.write("\n")
    except OSError:
        pass
    return log_path


def apply_update(zip_path: str) -> None:
    """src/'yi zip icerigiyle degistirir; eski src/'yi src_backup/ olarak tutar.

    Windows icin saglamlastirilmis: once staging klasorune acar (kilitli/bozuk
    acma calisan src/'ye zarar vermez), sonra yalnizca hizli klasor rename'leri
    yapar. Basarisizsa src/'yi geri yukler ve OSError firlatir.
    """
    app_dir = _app_dir()
    src = os.path.join(app_dir, "src")
    backup = os.path.join(app_dir, "src_backup")
    staging = os.path.join(app_dir, "src_new")

    _robust_rmtree(staging)
    os.makedirs(staging, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(staging)
    except Exception:
        _robust_rmtree(staging)
        raise

    try:
        _robust_rmtree(backup)
        if os.path.isdir(src):
            _robust_rename(src, backup)
    except OSError:
        _robust_rmtree(staging)
        raise

    try:
        _robust_rename(staging, src)
    except OSError:
        if not os.path.isdir(src) and os.path.isdir(backup):
            _robust_rename(backup, src)
        _robust_rmtree(staging)
        raise


def restart_app() -> "NoReturn":
    """Calisan exe'nin yeni bir surecini baslatir ve cikar."""
    if getattr(sys, "frozen", False):
        subprocess.Popen([sys.executable], close_fds=True)
    else:
        subprocess.Popen([sys.executable] + sys.argv, close_fds=True)
    sys.exit(0)


def run_update_flow(info: "UpdateInfo", parent_window=None) -> bool:
    """Indir + uygula + yeniden baslat. Ilerleme/hata kutulari gosterir.

    Basarisizsa False doner. Basarida bu fonksiyon DONMEZ - restart_app() ile
    surec yeniden baslar.
    """
    from tkinter import messagebox

    if decide_update_kind(info) in ("setup", "required"):
        return _run_setup_flow(info, parent_window)

    tmp_zip = os.path.join(tempfile.gettempdir(), "PDF-Renamer_update.zip")
    if not download_update(info, tmp_zip):
        messagebox.showerror(
            "Update failed",
            "Download or verification failed. Check your internet connection.",
            parent=parent_window,
        )
        return False

    try:
        apply_update(tmp_zip)
    except Exception as e:
        log_path = _log_update_error()
        messagebox.showerror(
            "Update failed",
            f"Could not write files: {e}\n\n"
            f"Details saved to:\n{log_path}\n\n"
            "Previous version kept.",
            parent=parent_window,
        )
        return False
    finally:
        _safe_remove(tmp_zip)

    messagebox.showinfo(
        "Update complete",
        f"Version {info.version} installed. The app will now restart.",
        parent=parent_window,
    )
    restart_app()
    return True  # ulasilmaz


# ---------------------------------------------------------------------------
# Tam kurulum (setup.exe) ile guncelleme
#
# src.zip yalnizca exe'nin yanindaki .py dosyalarini degistirir. Exe'nin
# kendisi -- ve icine gomulu lisans kapisi -- ancak kurulum dosyasiyla
# yenilenir. Indirilen sey CALISTIRILABILIR oldugu icin kural daha kati:
# SHA256 zorunludur, tutmazsa dosya diskte birakilmaz ve hicbir sey calismaz.
# ---------------------------------------------------------------------------

def _import_license_client():
    """Lisans kapisini import etmeyi dener (test icin ayri tutuldu)."""
    import license_client
    return license_client


def gate_present() -> bool:
    """Bu EXE lisans kapisiyla mi derlenmis?

    license_client SADECE kapili EXE'lerin icine gomulur; src.zip ile
    dagitilmaz. Bu yuzden import edilebiliyorsa kapi vardir.
    """
    try:
        _import_license_client()
    except Exception:
        return False
    return True


def decide_update_kind(info: "UpdateInfo") -> str:
    """'required' | 'setup' | 'code' (saf - test edilir).

    required : bu EXE kapisiz ve kurulacak bir setup var. Kapi EXE'nin
               icinde oldugu icin src.zip onu getiremez; atlanirsa program
               izinsiz calismaya devam ederdi. Bu yuzden zorunlu.
    setup    : kapi var ama notlar acikca tam kurulum istiyor (EXE'nin
               kendisi degismis demektir).
    code     : normal hal. Yalnizca src.zip iner.

    ONEMLI: once "setup varsa hep tam kurulum" deniyordu. Yanlisti --
    kapisi olan bir makinenin EXE'sini degistirmeye gerek yok ve 110 MB'lik
    kurulum yolu, calisan src.zip yolundan cok daha kirilgan. Gereksiz yere
    o yola sokulan makineler guncellenemeden takildi.
    """
    has_setup = bool(info.setup_url and info.setup_sha256)
    if not has_setup:
        return "code"
    if not gate_present():
        return "required"
    if FULL_INSTALL_MARKER in (info.notes or ""):
        return "setup"
    return "code"


def _visible_notes(body: str) -> str:
    """Notlardan makineye ait satirlari ayiklar.

    'SHA256:' ve 'SETUP_SHA256:' satirlari dogrulama icin var; kullaniciya
    gosterilen pencerede yalnizca gurultu yapiyorlar.
    """
    kept = []
    for line in (body or "").splitlines():
        if re.match(r"\s*(SETUP_)?SHA256\s*[:=]", line, re.IGNORECASE):
            continue
        kept.append(line)
    return "\n".join(kept).strip()


def update_prompt(info: "UpdateInfo") -> str:
    """Kullaniciya gosterilecek onay metni (saf - test edilir)."""
    parts = ["New version: " + info.version]
    notes = _visible_notes(info.notes)
    if notes:
        parts.append(notes)
    kind = decide_update_kind(info)
    if kind == "required":
        parts.append("This update is required. This copy was installed "
                     "before licence checking was added, so it still opens "
                     "without permission. The app will close and the "
                     "installer will run.")
    elif kind == "setup":
        parts.append("This is a full install: the app will close and the "
                     "installer will run. It may take a few minutes.")
    else:
        parts.append("The app will restart after the update.")
    return "\n\n".join(parts)


def download_setup(info: "UpdateInfo", dest_path: str, timeout: int = 300,
                   progress=None) -> bool:
    """Kurulum dosyasini indirir ve SHA256'yi dogrular.

    Ozet yoksa indirme DENENMEZ bile. Tutmazsa dosya silinir ve False doner;
    yarim ya da degistirilmis bir kurulumcu diskte kalmaz.
    """
    if not info.setup_url or not info.setup_sha256:
        return False
    try:
        _http_download(info.setup_url, dest_path, timeout=timeout,
                       progress=progress)
    except Exception:
        _safe_remove(dest_path)
        return False
    try:
        actual = _sha256_file(dest_path)
    except OSError:
        _safe_remove(dest_path)
        return False
    if actual.lower() != info.setup_sha256.lower():
        _safe_remove(dest_path)
        return False
    return True


def build_install_command(setup_path: str, relaunch_path: str = "") -> list:
    """Kurulumu baslatan komut (saf - test edilir).

    Uc ayri sorunu birlikte cozuyor:

    1. Gecikme. Calisan surec tkinter icin tcl/tk DLL'lerini yuklu tutuyor.
       Hemen baslatilan Inno Setup, DLL henuz serbest kalmadigi icin
       "DeleteFile failed; code 5" veriyor (EDMS_RIA_Print'te gercek
       kurulumda goruldu). `timeout` degil `ping`: konsolsuz (pythonw)
       sureclerde `timeout` "Input redirection is not supported" deyip
       hemen cikiyor.

    2. Gorunurluk. Eskiden /VERYSILENT kullaniliyordu: program kapaniyor,
       arkada hicbir sey gostermeden kuruluyordu ve kullanici ne oldugunu
       anlayamiyordu. /SILENT ilerleme penceresini gosterir.

    3. Geri donus. installer.iss'teki [Run] satiri `skipifsilent` tasiyor,
       yani sessiz kurulumdan sonra programi ACMAZ. cmd komutlari `&` ile
       SIRAYLA calistigi icin kurulum bitince programi biz aciyoruz.
    """
    parts = ['ping 127.0.0.1 -n 3 >nul',
             '"' + setup_path + '" /SILENT /NORESTART /LOG="'
             + install_log_path() + '"']
    if relaunch_path:
        parts.append('start "" "' + relaunch_path + '"')
    return ["cmd", "/c", " & ".join(parts)]


def install_log_path() -> str:
    """Kurulum logunun yolu. Kullanici ayarlariyla ayni klasorde durur ki
    kurulum programi silse bile kaybolmasin."""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    folder = os.path.join(base, "PDF-Renamer")
    try:
        os.makedirs(folder, exist_ok=True)
    except OSError:
        folder = tempfile.gettempdir()
    return os.path.join(folder, INSTALL_LOG_NAME)


def install_setup(setup_path: str):
    """Kurulumu baslatir ve programdan hemen cikar.

    Calisan program kendi exe'sini degistiremez, once cikmak sart.
    os._exit(): Tcl/Tk kapanis temizligi gecikebiliyor; bu, sureci ve DLL
    kilitlerini aninda birakir.
    """
    # Ana program hemen cikiyor. Cocuk surec ondan BAGIMSIZ baslamali,
    # yoksa bazi ortamlarda (is nesnesine bagli oturumlarda) ebeveynle
    # birlikte oluyor ve kurulum hic calismamis gibi gorunuyor.
    kwargs = {"close_fds": True}
    flags = 0
    for name in ("DETACHED_PROCESS", "CREATE_NEW_PROCESS_GROUP",
                 "CREATE_BREAKAWAY_FROM_JOB"):
        flags |= getattr(subprocess, name, 0)
    if flags:
        kwargs["creationflags"] = flags
    # Kurulum bitince geri acilacak program: donmus halde kendi exe'miz.
    relaunch = sys.executable if getattr(sys, "frozen", False) else ""
    subprocess.Popen(build_install_command(setup_path, relaunch), **kwargs)
    os._exit(0)


def _run_setup_flow(info: "UpdateInfo", parent_window=None) -> bool:
    """Indir, dogrula, kurulumcuyu baslat, cik. Basarida DONMEZ.

    Indirme ya da ozet dogrulamasi tutmazsa hicbir sey calistirilmaz ve
    False doner; mevcut kurulum oldugu gibi kalir.
    """
    from tkinter import messagebox

    dest = os.path.join(tempfile.gettempdir(), SETUP_ASSET_NAME)
    if not download_setup(info, dest):
        _safe_remove(dest)
        messagebox.showerror(
            "Update failed",
            "The installer could not be downloaded or verified.\n\n"
            "Nothing was changed. Check your internet connection "
            "and try again.",
            parent=parent_window,
        )
        return False

    messagebox.showinfo(
        "Installing update",
        "Version " + info.version + " will now be installed.\n\n"
        "This window closes, the installer shows its progress, and the app "
        "opens again by itself when it is done.",
        parent=parent_window,
    )
    install_setup(dest)   # geri donmez
    return True
