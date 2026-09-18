"""
license_client.py — Lisans kapısı. Tek dosya, sadece standart kütüphane.

Her programa OLDUĞU GİBİ kopyalanır; sadece aşağıdaki üç sabit değişir.
Programın en başında tek satır:

    import license_client
    license_client.require(version=config.VERSION)

İzin varsa sessizce döner. Yoksa kullanıcıya pencere gösterip çıkar.
ANA AKIŞA BAŞKA HİÇBİR DOKUNUŞ YOKTUR.

Tasarım: karar veren her şey saf fonksiyon (decide_action, decide_update,
compare_versions, imza). Pencere açan kısımlar ayrı ve enjekte edilebilir —
gui.py'deki format_feed_line deseninin aynısı. Böylece testler pencere açmadan
tüm davranışı doğrular.

Çevrimdışı çalışma yolu YOKTUR. Bilinçli.
"""

import hashlib
import hmac
import json
import os
import secrets
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

# --- Programa özel — panelde "yeni program" derken üretilir ----------------
# Panel "yeni program" derken bir SECRET üretir; buraya yapıştırılır.
# Yapıştırılana kadar lisans sistemi KURULMAMIŞ sayılır ve kapı devreye girmez.
UNCONFIGURED_SECRET = "PANELDEN_URETILEN_DEGER"

# Panelde "Add a program" ile uretilen kimlik.
# Gercek SECRET kaynak koda YAZILMAZ: bu deponun GitHub uzantisi public
# (guncelleme release'leri oradan iniyor). SECRET sizarsa herkes sahte bir
# sunucu kurup "izinli" cevabini imzalayabilir ve kapi anlamsizlasir.
# Bu yuzden gercek deger, yanindaki license_secret.txt dosyasindan okunur;
# o dosya .gitignore'dadir ve EXE'ye derleme aninda gomulur.
SECRET_FILE = "license_secret.txt"


def _secret_dir() -> str:
    """SECRET dosyasinin bulundugu klasor (PyInstaller'da _MEIPASS)."""
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        return bundled
    return os.path.dirname(os.path.abspath(__file__))


def _load_secret(default: str) -> str:
    """SECRET'i dosyadan okur. Dosya yoksa kapi KAPALI kalir (default doner)."""
    try:
        with open(os.path.join(_secret_dir(), SECRET_FILE), encoding="utf-8") as fh:
            value = fh.read().strip()
    except OSError:
        return default
    return value or default


PROGRAM_ID = "pdf_renamer"
SECRET = _load_secret(UNCONFIGURED_SECRET)
SERVER_URL = os.environ.get(
    "LICENSE_SERVER_URL", "https://license-panel.yavuzzeynulat.workers.dev")

TITLE = "PDF Renamer"

WARN_DAYS = 3         # kalan gün bunun altındaysa uyar ama çalıştır
TIMEOUT = 5           # saniye, tek deneme
ATTEMPTS = 3
RETRY_WAIT = 1.0
DOWNLOAD_TIMEOUT = 300
DOWNLOAD_ATTEMPTS = 3   # kurulum dosyası büyük; kopan indirme yeniden denenir

# Cloudflare, urllib'in varsayılan "Python-urllib/3.x" kimliğini bot sayıp 403
# veriyor. Kendi kimliğimizi göndermezsek program sunucuya HİÇ ulaşamaz.
USER_AGENT = f"{PROGRAM_ID}/1.0 (Windows)"


class LicenseNetworkError(Exception):
    """Sunucuya hiç ulaşılamadı."""


class LicenseTrustError(Exception):
    """Cevap geldi ama imzası/özeti tutmadı — sahte sunucu olabilir."""


# =============================================================== makine kimliği

def format_machine_id(hexdigest: str) -> str:
    """16 hex karakteri, telefonda okunabilecek dört gruba böler."""
    h = hexdigest.upper()[:16]
    return "-".join(h[i:i + 4] for i in range(0, 16, 4))


def _raw_machine_key() -> str:
    """
    Windows'un kalıcı makine kimliği. Kayıt defteri okunamazsa ağ kartı
    adresine düşer — ikisi de aynı makinede kararlıdır.
    """
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography",
            0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        )
        try:
            guid, _ = winreg.QueryValueEx(key, "MachineGuid")
            return str(guid)
        finally:
            winreg.CloseKey(key)
    except Exception:
        return str(uuid.getnode())


def machine_id() -> str:
    raw = f"{_raw_machine_key()}|{os.environ.get('USERNAME', '')}"
    return format_machine_id(hashlib.sha256(raw.encode("utf-8")).hexdigest())


# =============================================================== sürüm

def compare_versions(a, b) -> int:
    """Sayısal karşılaştırma: 0.10.0 > 0.9.0. Saçma girdide çökmez."""
    def parts(v):
        out = []
        for chunk in str(v).split("."):
            try:
                out.append(int(chunk))
            except ValueError:
                out.append(0)
        return out

    pa, pb = parts(a), parts(b)
    for i in range(max(len(pa), len(pb))):
        x = pa[i] if i < len(pa) else 0
        y = pb[i] if i < len(pb) else 0
        if x != y:
            return 1 if x > y else -1
    return 0


# =============================================================== imza

def make_signature(secret: str, parts) -> str:
    msg = "|".join(str(p) for p in parts).encode("utf-8")
    return hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def verify_signature(secret: str, parts, signature) -> bool:
    if not isinstance(signature, str):
        return False
    return hmac.compare_digest(make_signature(secret, parts), signature)


# =============================================================== kararlar (saf)

def decide_action(payload, machine: str = ""):
    """
    Sunucu cevabına göre ne yapılacağını söyler.
    Döner: (action, title, message); action ∈ {"run", "warn", "exit"}
    """
    status = (payload or {}).get("status")

    if status == "active":
        days = payload.get("days_left")
        if isinstance(days, int) and days < WARN_DAYS:
            return ("warn", TITLE, f"Your access expires in {days} day(s).")
        return ("run", TITLE, "")

    if status == "pending":
        return ("exit", TITLE,
                "Waiting for approval.\n\n"
                f"Your code:   {machine}\n\n"
                "Send this code to your administrator.")

    if status == "expired":
        when = (payload or {}).get("expires_at") or "an earlier date"
        return ("exit", TITLE,
                f"Your access expired on {when}.\n\nContact your administrator.")

    if status == "blocked":
        return ("exit", TITLE,
                "Your access has been turned off.\n\nContact your administrator.")

    # Tanımadığımız bir cevap: çalıştırmıyoruz. Güvenli taraf kapalı taraftır.
    return ("exit", TITLE, "The licence server sent an unexpected answer.")


def decide_update(update, current_version):
    """
    Güncelleme alanına göre ne yapılacağını söyler.
    Döner: (action, message); action ∈ {"none", "offer", "force"}
    """
    if not update or not isinstance(update, dict):
        return ("none", "")

    version = str(update.get("version", ""))
    if not version or compare_versions(version, current_version) <= 0:
        return ("none", "")

    body = f"Version {version} is available."
    notes = str(update.get("notes", "")).strip()
    if notes:
        body += f"\n\n{notes}"

    if update.get("mandatory"):
        return ("force", body + "\n\nThis update is required to keep using the program.")
    return ("offer", body + "\n\nInstall it now?")


# =============================================================== yerel durum

def _state_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / PROGRAM_ID / "license.json"


def read_user_name() -> str:
    try:
        data = json.loads(_state_path().read_text("utf-8"))
        return str(data.get("user_name", "")).strip()
    except Exception:
        return ""


def write_user_name(name: str) -> None:
    p = _state_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"user_name": name}), encoding="utf-8")
    except Exception:
        pass   # kaydedemezsek her açılışta sorarız; programı durdurmaz


# =============================================================== pencereler

def ask_user_name() -> str:
    """İlk açılışta adı sorar. İptal/boş -> "" döner."""
    import tkinter as tk
    from tkinter import simpledialog

    root = tk.Tk()
    root.withdraw()
    try:
        answer = simpledialog.askstring(TITLE, "Your name and surname:")
        return (answer or "").strip()
    finally:
        root.destroy()


def _show_tk(kind, title, message) -> bool:
    """kind: "info" | "error" | "question". question için Evet/Hayır döner."""
    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.withdraw()
    try:
        if kind == "question":
            return bool(messagebox.askyesno(title, message))
        if kind == "error":
            messagebox.showerror(title, message)
        else:
            messagebox.showinfo(title, message)
        return True
    finally:
        root.destroy()


# =============================================================== ağ

def _new_nonce() -> str:
    return secrets.token_hex(16)


def ask_server(version, user_name, machine, nonce):
    """Sunucuya sorar, imzayı doğrular, cevabı döner."""
    body = json.dumps({
        "program": PROGRAM_ID,
        "machine_id": machine,
        "user_name": user_name,
        "version": version,
        "nonce": nonce,
    }).encode("utf-8")

    payload = None
    last = None
    for attempt in range(ATTEMPTS):
        try:
            req = urllib.request.Request(
                f"{SERVER_URL}/api/check", data=body,
                headers={"content-type": "application/json",
                         "user-agent": USER_AGENT},
                method="POST")
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            break
        except Exception as e:
            last = e
            if attempt < ATTEMPTS - 1:
                time.sleep(RETRY_WAIT)

    if payload is None:
        raise LicenseNetworkError(str(last))

    update = payload.get("update") or {}
    parts = [
        PROGRAM_ID, machine, payload.get("status", ""),
        payload.get("expires_at") or "", nonce,
        update.get("version", "") if update else "",
        update.get("sha256", "") if update else "",
    ]
    if not verify_signature(SECRET, parts, payload.get("signature")):
        raise LicenseTrustError("signature mismatch")
    return payload


# =============================================================== güncelleme

def _fetch_bytes(url, progress=None):
    req = urllib.request.Request(url, headers={"user-agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT) as resp:
        return resp.read()


def _download_dir() -> Path:
    return Path(tempfile.gettempdir())


def download_update(url, expected_sha256, dest, progress=None) -> Path:
    """
    İndirir ve sha256 doğrular. Tutmazsa dosyayı bırakmaz ve hata fırlatır —
    yarım/sahte bir kurulum dosyası diskte kalmasın.

    Kurulum dosyası büyük (~60 MB) ve bağlantı kopabiliyor; yarım inen dosya
    zaten sha256'da yakalanıyor ama kullanıcıyı boşuna hata ekranına düşürmemek
    için birkaç kez deneniyor.
    """
    dest = Path(dest)
    want = str(expected_sha256).lower()
    last = None

    for attempt in range(DOWNLOAD_ATTEMPTS):
        try:
            data = _fetch_bytes(url, progress)
        except Exception as e:          # kopan bağlantı, zaman aşımı, ...
            last = e
        else:
            if hashlib.sha256(data).hexdigest().lower() == want:
                dest.write_bytes(data)
                return dest
            last = LicenseTrustError("checksum mismatch")

        if attempt < DOWNLOAD_ATTEMPTS - 1:
            time.sleep(RETRY_WAIT)

    try:
        dest.unlink()
    except OSError:
        pass
    raise LicenseTrustError(f"download failed after {DOWNLOAD_ATTEMPTS} attempts: {last}")


def install_update(setup_path) -> None:
    """
    Kurulumu sessiz başlatır ve programdan çıkar.

    Çalışan program kendi dosyalarını değiştiremez; bu yüzden önce çıkıyoruz.
    Inno Setup kurulumu bitirince programı kendisi yeniden başlatır.
    """
    subprocess.Popen([str(setup_path), "/VERYSILENT", "/NORESTART"], close_fds=True)
    sys.exit(0)


def _handle_update(payload, current_version, show) -> None:
    action, message = decide_update(payload.get("update"), current_version)
    if action == "none":
        return

    update = payload["update"]
    if not show("question", TITLE, message):
        if action == "force":
            show("error", TITLE, "This update is required. The program will now close.")
            sys.exit(1)
        return

    dest = _download_dir() / f"{PROGRAM_ID}_setup_{update['version']}.exe"
    try:
        download_update(update["url"], update["sha256"], dest)
    except Exception:
        show("error", TITLE,
             "The update could not be downloaded or verified.\n\nTry again later.")
        if action == "force":
            sys.exit(1)
        return

    install_update(dest)


# =============================================================== kapı

def is_configured() -> bool:
    """
    Lisans sistemi kurulmuş mu? SECRET hâlâ yer tutucu ise HAYIR.

    Panel yayına alınmadan önce kapıyı işletirsek program, var olmayan bir
    sunucuya sorup hiç açılmaz. Çalışan bir programı kurulum tamamlanmadan
    kilitlememek için bu kontrol var. SECRET doldurulduğu an kapı normal çalışır.
    """
    return bool(SECRET) and SECRET != UNCONFIGURED_SECRET


def require(version: str = "", show=None) -> None:
    """
    Lisans kapısı. İzin varsa sessizce döner; yoksa pencere gösterip çıkar.
    show: (kind, title, message) -> bool   — test için enjekte edilebilir.
    """
    if not is_configured():
        return

    if show is None:
        show = _show_tk

    machine = machine_id()

    name = read_user_name()
    if not name:
        name = ask_user_name()
        if not name:
            show("error", TITLE, "A name is required to use this program.")
            sys.exit(1)
        write_user_name(name)

    try:
        payload = ask_server(version, name, machine, _new_nonce())
    except LicenseNetworkError:
        show("error", TITLE,
             "An internet connection is required.\n\n"
             "This program cannot start without reaching the licence server.")
        sys.exit(1)
    except LicenseTrustError:
        show("error", TITLE,
             "The licence server could not be verified.\n\n"
             "Contact your administrator.")
        sys.exit(1)

    action, title, message = decide_action(payload, machine=machine)
    if action == "exit":
        show("error", title, message)
        sys.exit(1)
    if action == "warn":
        show("info", title, message)

    # Güncelleme SADECE lisans geçtikten sonra sorulur.
    _handle_update(payload, version, show)
