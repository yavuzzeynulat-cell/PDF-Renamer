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
_UA = "PDF-Renamer-Updater"


@dataclass
class UpdateInfo:
    version: str            # ornek "2.0.1" ("v" onsuz)
    notes: str              # release aciklamasi (Turkce, cok satirli)
    asset_url: str          # src.zip dogrudan indirme URL'si
    sha256: Optional[str]   # notlardan okunur; yoksa None


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
    m = re.search(r"SHA256\s*[:=]\s*([0-9a-fA-F]{64}|[0-9a-fA-F]+)", body)
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
        return UpdateInfo(
            version=remote_v,
            notes=data.get("body", "") or "",
            asset_url=asset_url,
            sha256=_parse_sha256(data.get("body", "")),
        )
    except Exception:
        return None


def _http_download(url: str, dest: str, timeout: int = 30) -> None:
    """`url`'i `dest`'e akitarak indirir. Hata durumunda OSError."""
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        with open(dest, "wb") as f:
            while True:
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                f.write(chunk)


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

    tmp_zip = os.path.join(tempfile.gettempdir(), "PDF-Renamer_update.zip")
    if not download_update(info, tmp_zip):
        messagebox.showerror(
            "Guncelleme basarisiz",
            "Indirme veya dogrulama basarisiz. Internet baglantisini kontrol et.",
            parent=parent_window,
        )
        return False

    try:
        apply_update(tmp_zip)
    except Exception as e:
        log_path = _log_update_error()
        messagebox.showerror(
            "Guncelleme basarisiz",
            f"Dosyalar yazilamadi: {e}\n\n"
            f"Detaylar: {log_path}\n\n"
            "Onceki surum korundu.",
            parent=parent_window,
        )
        return False
    finally:
        _safe_remove(tmp_zip)

    messagebox.showinfo(
        "Guncelleme tamam",
        f"Surum {info.version} kuruldu. Uygulama yeniden baslatilacak.",
        parent=parent_window,
    )
    restart_app()
    return True  # ulasilmaz
