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
    """Bu EXE'de lisans kapisi GERCEKTEN etkin mi?

    Eskiden yalnizca `import license_client` deneniyordu; gerekce
    "license_client SADECE kapili EXE'lerin icine gomulur" idi. Bu
    YANLISTI: launcher.py onu kosulsuz import ediyor, dolayisiyla
    PyInstaller HER derlemeye koyuyor. Kosullu olan tek sey
    license_secret.txt -- PDF-Renamer.spec o yoksa

        [UYARI] license_secret.txt yok - EXE lisans kapisi OLMADAN derlenecek

    basip devam ediyor. Boyle bir EXE'de license_client yine var ama
    require() ilk satirda `if not is_configured(): return` deyip hicbir
    sey sormadan donuyor -- yani kapi KAPALI. Eski kontrol bu EXE'ye
    "kapisi var" diyordu, dolayisiyla decide_update_kind onu 'required'
    saymiyor ve makine tam kuruluma hic zorlanmiyordu: lisanssiz
    calismaya sonsuza kadar devam ediyordu.

    Dogru soru "modul var mi" degil, "sir gomulu mu": is_configured().
    Cevabi alamazsak (eski bir EXE'nin icindeki license_client'ta bu
    fonksiyon olmayabilir) GUVENLI yone dusuyoruz: kapi yok say, tam
    kurulum zorla.
    """
    try:
        client = _import_license_client()
        return bool(client.is_configured())
    except Exception:
        return False


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
    # "required" da "setup" gibi anlatilir: kullaniciya zorunlu oldugu
    # SOYLENMEZ, sadece normal bir tam kurulum gibi gorunur.
    if kind in ("required", "setup"):
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


# --- eski surumu bulma ------------------------------------------------------
# Inno Setup kurulumu kendini buraya yazar. AppId installer.iss'te
# "PDF Renamer" ve Inno sonuna "_is1" ekler; gorunen ad degisse bile bu
# anahtar sabit kalir.
UNINSTALL_KEY = (r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
                 r"\PDF Renamer_is1")


def _read_registry_value(root, key: str, name: str) -> Optional[str]:
    """Tek bir kayit defteri degeri okur. Yoksa/okunamazsa None."""
    try:
        import winreg
    except ImportError:
        return None
    try:
        with winreg.OpenKey(root, key) as k:
            value, _ = winreg.QueryValueEx(k, name)
        return value if isinstance(value, str) else None
    except OSError:
        return None


def find_uninstaller() -> str:
    r"""Kurulu surumun unins000.exe yolu; kurulu degilse "" .

    Kurulum kullanici bazinda (HKCU) yapiliyor ama eski/admin kurulumlar
    HKLM'de olabilir; ikisine de bakariz. Deger '"...\unins000.exe" /SILENT'
    seklinde geldigi icin ilk tirnakli parca ayiklanir.
    """
    try:
        import winreg
    except ImportError:
        return ""
    roots = [getattr(winreg, "HKEY_CURRENT_USER"),
             getattr(winreg, "HKEY_LOCAL_MACHINE")]
    for root in roots:
        raw = _read_registry_value(root, UNINSTALL_KEY, "UninstallString")
        if not raw:
            continue
        path = raw.strip()
        if path.startswith('"'):
            path = path[1:].split('"', 1)[0]
        else:
            path = path.split(" ")[0]
        # Dosya var mi diye BURADA bakmiyoruz: betikteki `if not exist`
        # korumasi bunu zaten yapiyor ve kayit defteri okumasini tek
        # sorumluluga indirgemek fonksiyonu test edilebilir birakiyor.
        if path:
            return path
    return ""


def build_install_script(setup_path: str, relaunch_path: str = "",
                         uninstaller: str = "") -> str:
    r"""Kurulumu yapan .bat dosyasinin icerigi (saf - test edilir).

    Neden .bat? Eskiden komut tek satir halinde
    `subprocess.Popen(["cmd", "/c", '... & "setup.exe" /SILENT & ...'])`
    olarak veriliyordu. Python'un list2cmdline'i o satirdaki tirnaklari
    \\" diye kacirir, cmd.exe ise \\" bilmez; sonuc:

        '\\"C:\...\PDF-Renamer-Setup.exe\\"' is not recognized as an
        internal or external command

    Program o anda coktan kapanmis oldugu icin geriye hicbir iz kalmiyor,
    kullanici sadece "guncelleme indi ama kurulmadi" goruyordu. Komutu
    dosyaya yazip cmd'ye yalnizca DOSYA YOLUNU vermek bu sinifi tamamen
    ortadan kaldirir.

    Akis:
      1. ping ile gecikme -- calisan surec tkinter'in tcl/tk DLL'lerini
         birakana kadar Inno "DeleteFile failed; code 5" veriyor.
         `timeout` degil `ping`: konsolsuz sureclerde timeout
         "Input redirection is not supported" deyip hemen cikar.
      2. Varsa eski surumu sessizce kaldir ve gercekten bitmesini bekle.
         Inno kaldiriciyi %TEMP%'e kopyalayip oradan calistirdigi icin
         cagri hemen doner; unins000.exe kaybolana kadar yoklariz.
         Ilk kez kuruluyorsa bu adim hic yazilmaz.
      3. /SILENT ile kur (/VERYSILENT degil: kullanici ilerlemeyi gormeli)
         ve /LOG birak -- basarisiz kurulumdan geriye kalan tek sey.
      4. Programi geri ac. installer.iss'teki [Run] satirinda `skipifsilent`
         var, yani sessiz kurulumdan sonra Inno programi ACMAZ.
    """
    lines = ["@echo off", "ping 127.0.0.1 -n 3 >nul"]
    if uninstaller:
        # Kaldirici DOGRUDAN cagrilir, `start /wait` ile degil. Betik gizli
        # konsollu bir cmd'de calisiyor ve olculdu: `start /wait` orada
        # donmuyor -- kaldirma yapiliyor ama betik o satirda sonsuza kadar
        # asili kaliyor, kurulum hic baslamiyor.
        lines += [
            'if not exist "%s" goto install' % uninstaller,
            '"%s" /VERYSILENT /NORESTART /SUPPRESSMSGBOXES' % uninstaller,
            'for /L %%i in (1,1,60) do (',
            '  if not exist "%s" goto install' % uninstaller,
            '  ping 127.0.0.1 -n 2 >nul',
            ')',
            ':install',
        ]
    lines.append('"%s" /SILENT /NORESTART /LOG="%s"'
                 % (setup_path, install_log_path()))
    if relaunch_path:
        lines.append('start "" "%s"' % relaunch_path)
    return "\n".join(lines) + "\n"


def write_install_script(text: str) -> str:
    """Betigi diske yazar ve yolunu doner.

    Kurulum klasorunun degil %TEMP%'in altinda durur: kaldirma adimi
    kurulum klasorunu silecegi icin betik kendi altindan cekilmis olurdu.
    """
    path = os.path.join(tempfile.gettempdir(), "PDF-Renamer_install.bat")
    with open(path, "w", encoding="ascii", errors="replace", newline="\r\n") as f:
        f.write(text)
    return path


def build_install_command(script_path: str) -> list:
    """Betigi calistiran komut (saf - test edilir).

    cmd'ye giden tek argüman bir dosya yolu: icinde tirnak yok, dolayisiyla
    list2cmdline kacisli tirnak uretemez.
    """
    return ["cmd", "/c", script_path]


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


# Kurulum betigini baslatirken kullanilan surec bayraklari.
#
# CREATE_NO_WINDOW: betige GIZLI bir konsol verir. DETACHED_PROCESS
#   denendi ve olculdu -- orada konsol HIC olmadigi icin `start` komutu
#   donmuyor, betik o satirda sonsuza kadar asili kaliyor. Programi
#   kurulumdan sonra geri acan satir `start` kullaniyor.
# CREATE_BREAKAWAY_FROM_JOB / CREATE_NEW_PROCESS_GROUP: ana program
#   hemen os._exit(0) yapiyor; cocuk ondan bagimsiz olmazsa bazi
#   ortamlarda (is nesnesine bagli oturumlarda) onunla birlikte oluyor
#   ve kurulum hic calismamis gibi gorunuyor.
_SPAWN_FLAG_NAMES = ("CREATE_NO_WINDOW", "CREATE_NEW_PROCESS_GROUP",
                     "CREATE_BREAKAWAY_FROM_JOB")


def spawn_flags() -> int:
    """Kurulum betiginin surec bayraklari (saf - test edilir)."""
    flags = 0
    for name in _SPAWN_FLAG_NAMES:
        flags |= getattr(subprocess, name, 0)
    return flags


def install_setup(setup_path: str):
    """Kurulumu baslatir ve programdan hemen cikar.

    Calisan program kendi exe'sini degistiremez, once cikmak sart.
    os._exit(): Tcl/Tk kapanis temizligi gecikebiliyor; bu, sureci ve DLL
    kilitlerini aninda birakir.
    """
    kwargs = {"close_fds": True}
    flags = spawn_flags()
    if flags:
        kwargs["creationflags"] = flags
    # Kurulum bitince geri acilacak program: donmus halde kendi exe'miz.
    relaunch = sys.executable if getattr(sys, "frozen", False) else ""
    script = write_install_script(
        build_install_script(setup_path, relaunch, find_uninstaller()))
    subprocess.Popen(build_install_command(script), **kwargs)
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
