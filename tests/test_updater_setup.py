"""updater.py: tam kurulum (setup.exe) ile guncelleme.

src.zip yalnizca exe'nin YANINDAKI kod dosyalarini degistirir; exe'nin
kendisini degistiremez. Lisans kapisi exe'nin icinde oldugu icin kullanicilara
ancak tam kurulumla ulasir. Bu yuzden updater, release'e eklenmis bir
setup.exe'yi de indirip kurabilmeli.

GUVENLIK: indirilen sey CALISTIRILABILIR bir dosya. Bu yuzden setup, SADECE
release notlarinda 64 haneli gecerli bir SETUP_SHA256 varsa ve indirilen
dosyanin ozeti birebir tutuyorsa teklif edilir/kurulur. Hash yoksa setup hic
teklif edilmez -- src.zip'ten daha kati bir kural, bilerek.
"""
from __future__ import annotations

import hashlib
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import updater  # noqa: E402

SETUP_BYTES = b"MZ sahte kurulum dosyasi"
SETUP_SHA = hashlib.sha256(SETUP_BYTES).hexdigest()
ZIP_SHA = "b" * 64


def _release(notes: str, with_setup: bool = True) -> dict:
    assets = [{"name": "src.zip", "browser_download_url": "https://x/src.zip"}]
    if with_setup:
        assets.append({"name": updater.SETUP_ASSET_NAME,
                       "browser_download_url": "https://x/setup.exe"})
    return {"tag_name": "v9.9.9", "body": notes, "assets": assets}


def _patch_release(monkeypatch, data):
    monkeypatch.setattr(updater, "_fetch_latest_release_json", lambda timeout=5: data)


# -- release'i dogru okuma ---------------------------------------------------

def test_setup_is_offered_when_asset_and_hash_are_both_present(monkeypatch):
    _patch_release(monkeypatch, _release(
        "SHA256: {0}\nSETUP_SHA256: {1}".format(ZIP_SHA, SETUP_SHA)))
    info = updater.check_for_update()
    assert info.setup_url == "https://x/setup.exe"
    assert info.setup_sha256 == SETUP_SHA


def test_setup_is_not_offered_without_a_hash(monkeypatch):
    """Hash'siz calistirilabilir dosya indirilmez."""
    _patch_release(monkeypatch, _release("SHA256: " + ZIP_SHA))
    assert updater.check_for_update().setup_url is None


def test_setup_is_not_offered_when_the_asset_is_missing(monkeypatch):
    _patch_release(monkeypatch, _release(
        "SHA256: {0}\nSETUP_SHA256: {1}".format(ZIP_SHA, SETUP_SHA),
        with_setup=False))
    assert updater.check_for_update().setup_url is None


def test_the_two_hashes_do_not_get_mixed_up(monkeypatch):
    """'SETUP_SHA256:' satiri, src.zip'in 'SHA256:' degeri sanilmamali."""
    _patch_release(monkeypatch, _release(
        "SETUP_SHA256: {0}\nSHA256: {1}".format(SETUP_SHA, ZIP_SHA)))
    info = updater.check_for_update()
    assert info.sha256 == ZIP_SHA
    assert info.setup_sha256 == SETUP_SHA


# -- indirme ve dogrulama ----------------------------------------------------

def _info(sha):
    return updater.UpdateInfo(version="9.9.9", notes="", asset_url="https://x/src.zip",
                              sha256=ZIP_SHA, setup_url="https://x/setup.exe",
                              setup_sha256=sha)


def test_a_matching_setup_is_kept(tmp_path, monkeypatch):
    dest = tmp_path / "setup.exe"
    monkeypatch.setattr(updater, "_http_download",
                        lambda url, d, timeout=30, progress=None: open(d, "wb").write(SETUP_BYTES))
    assert updater.download_setup(_info(SETUP_SHA), str(dest)) is True
    assert dest.read_bytes() == SETUP_BYTES


def test_a_tampered_setup_is_rejected_and_deleted(tmp_path, monkeypatch):
    dest = tmp_path / "setup.exe"
    monkeypatch.setattr(updater, "_http_download",
                        lambda url, d, timeout=30, progress=None: open(d, "wb").write(b"kotu amacli"))
    assert updater.download_setup(_info(SETUP_SHA), str(dest)) is False
    assert not dest.exists(), "dogrulamayi gecemeyen dosya diskte birakilmamali"


def test_a_setup_without_a_hash_is_never_downloaded(tmp_path, monkeypatch):
    dest = tmp_path / "setup.exe"
    called = []
    monkeypatch.setattr(updater, "_http_download",
                        lambda url, d, timeout=30, progress=None: called.append(1))
    assert updater.download_setup(_info(None), str(dest)) is False
    assert called == [], "hash yokken indirme bile denenmemeli"


# -- kurulumu baslatma -------------------------------------------------------

SETUP = r"C:\tmp\setup.exe"
APP = r"C:\app\PDF-Renamer.exe"
UNINS = r"C:\Users\x\AppData\Local\Programs\PDF Renamer\unins000.exe"


def test_the_command_survives_windows_quoting():
    r"""ESKI HATA: komut ["cmd", "/c", 'ping ... & "setup.exe" /SILENT & ...']
    olarak veriliyordu. Python'un list2cmdline'i icerideki tirnaklari \"
    yapiyor, cmd.exe bunu anlamiyor ve

        '\"C:\tmp\setup.exe\"' is not recognized as an internal command

    deyip cikiyordu. Program coktan kapanmis oldugu icin kullanici yalnizca
    "indi ama kurulmadi" goruyordu. Artik komut bir .bat dosyasina yazilir ve
    cmd'ye SADECE dosya yolu verilir; tirnaklar hic yolculuk etmez.
    """
    import subprocess
    cmd = updater.build_install_command(r"C:\tmp\install.bat")
    line = subprocess.list2cmdline(cmd)
    assert '\\"' not in line, "kacisli tirnak var: cmd.exe bunu calistiramaz"
    assert cmd[0] == "cmd"
    assert cmd[-1].endswith(".bat")


def test_the_installer_writes_a_log_we_can_read_afterwards():
    """Kurulum basarisiz olursa program coktan kapanmis oluyor ve geriye
    hicbir iz kalmiyordu. /LOG ile en azindan neden basarisiz oldugu
    diskte kaliyor."""
    script = updater.build_install_script(SETUP, APP)
    assert "/LOG=" in script
    assert updater.INSTALL_LOG_NAME in script


def test_the_installer_shows_its_progress():
    """/VERYSILENT hicbir sey gostermiyordu: program kapaniyor, arkada
    sessizce kuruluyor, kullanici ne oldugunu anlayamiyordu. /SILENT
    ilerleme penceresini gosterir (sihirbaz sayfalari yine yok)."""
    script = updater.build_install_script(SETUP, APP)
    setup_line = [l for l in script.splitlines() if SETUP in l][0]
    assert "/SILENT" in setup_line
    assert "/VERYSILENT" not in setup_line, "sessiz kurulum takip edilemiyor"
    assert "/NORESTART" in setup_line


def test_the_installer_is_given_time_to_take_the_file_lock():
    script = updater.build_install_script(SETUP, APP)
    assert "ping" in script, "gecikme yok: calisan exe hala kilitli olabilir"


def test_the_app_comes_back_by_itself_after_the_install():
    """installer.iss'teki [Run] satirinda `skipifsilent` var, yani sessiz
    kurulumda program yeniden ACILMIYOR. Geri getirmeyi biz ustleniyoruz."""
    script = updater.build_install_script(SETUP, APP)
    assert APP in script
    assert script.index("setup.exe") < script.index("PDF-Renamer.exe"), \
        "once kurulum bitmeli, sonra program acilmali"


def test_without_a_relaunch_path_nothing_extra_is_started():
    script = updater.build_install_script(SETUP)
    assert "/SILENT" in script
    assert "start" not in script


def test_the_script_never_uses_start_wait():
    """OLCULDU: betik gizli konsollu bir cmd'de calisiyor ve orada
    `start /wait` DONMUYOR. Kaldirma yapiliyor, sonraki satir hic
    calismiyor -- yani kurulum sessizce hic baslamiyor. Kaldirici
    dogrudan cagrilmali."""
    script = updater.build_install_script(SETUP, APP, UNINS)
    assert "start /wait" not in script


def test_the_installer_process_keeps_a_console_it_can_use():
    """DETACHED_PROCESS konsolu tamamen kaldiriyor ve `start` orada
    asili kaliyor; programi geri acan satir `start` kullaniyor.
    CREATE_NO_WINDOW gizli ama GERCEK bir konsol verir."""
    import subprocess
    flags = updater.spawn_flags()
    assert flags & subprocess.CREATE_NO_WINDOW
    assert not (flags & subprocess.DETACHED_PROCESS), \
        "konsolsuz surecte `start` donmuyor"


def test_the_installer_outlives_the_app_that_started_it():
    """Program os._exit(0) ile aninda oluyor. Cocuk surec ona bagli
    kalirsa bazi ortamlarda onunla birlikte olur."""
    import subprocess
    flags = updater.spawn_flags()
    assert flags & subprocess.CREATE_BREAKAWAY_FROM_JOB
    assert flags & subprocess.CREATE_NEW_PROCESS_GROUP


def test_the_script_is_written_where_the_uninstall_cannot_reach_it():
    """Kaldirma adimi kurulum klasorunu siliyor; betik orada dursa
    kendi altindan cekilmis olurdu."""
    import tempfile
    path = updater.write_install_script("@echo off\n")
    assert os.path.dirname(path) == tempfile.gettempdir()
    assert path.endswith(".bat")


# -- eski surumu once kaldirma ----------------------------------------------

def test_the_old_version_is_removed_before_the_new_one_is_installed():
    """Ustune kurmak eski src/ artiklarini birakiyordu. Once kaldir."""
    script = updater.build_install_script(SETUP, APP, UNINS)
    assert UNINS in script
    assert script.index("unins000.exe") < script.index("setup.exe"), \
        "kaldirma kurulumdan ONCE olmali"


def test_the_uninstall_asks_nothing_and_restarts_nothing():
    script = updater.build_install_script(SETUP, APP, UNINS)
    unins_line = [l for l in script.splitlines()
                  if "unins000.exe" in l and "/VERYSILENT" in l][0]
    assert "/VERYSILENT" in unins_line, "kaldirma penceresi kullaniciyi sasirtir"
    assert "/SUPPRESSMSGBOXES" in unins_line, "onay kutusu tum akisi kilitler"
    assert "/NORESTART" in unins_line


def test_a_first_time_install_just_installs():
    """Kaldirilacak bir sey yoksa (ilk kurulum) akis durmamali."""
    script = updater.build_install_script(SETUP, APP, "")
    assert "unins" not in script
    assert SETUP in script
    assert APP in script


def test_the_install_still_runs_if_the_uninstall_hangs():
    """Kaldirma takilirsa kurulum yine de denenmeli; Inno ustune kurabilir."""
    script = updater.build_install_script(SETUP, APP, UNINS)
    assert "goto" in script.lower(), "bekleme dongusunden cikis yok"
    assert script.index(SETUP) > script.index(UNINS)


def test_the_uninstaller_is_found_from_the_registry(monkeypatch):
    """Kaldiriciyi kayit defterinden buluruz; kurulum klasoru tasinmis
    olabilir, sabit yol yazmak kirilgan."""
    monkeypatch.setattr(updater, "_read_registry_value",
                        lambda root, key, name: '"%s" /SILENT' % UNINS)
    assert updater.find_uninstaller() == UNINS


def test_no_uninstaller_means_no_uninstall_step(monkeypatch):
    monkeypatch.setattr(updater, "_read_registry_value",
                        lambda root, key, name: None)
    assert updater.find_uninstaller() == ""


# -- hangi yol secilir -------------------------------------------------------

def test_a_release_with_a_setup_does_not_force_a_full_install(monkeypatch):
    """Eskiden setup'li her release tam kurulum zorluyordu; bu, kapisi olan
    makineleri gereksiz yere kirilgan yoldan gecirip takiyordu."""
    monkeypatch.setattr(updater, "gate_present", lambda: True)
    assert updater.decide_update_kind(_info(SETUP_SHA)) == "code"


def test_a_release_without_a_setup_stays_on_the_code_only_path():
    assert updater.decide_update_kind(_info(None)) == "code"


def test_the_user_is_told_a_full_install_is_coming(monkeypatch):
    """Tam kurulum programi kapatip installer calistirir; surpriz olmamali."""
    monkeypatch.setattr(updater, "gate_present", lambda: True)
    info = _info(SETUP_SHA)
    info.notes = updater.FULL_INSTALL_MARKER
    msg = updater.update_prompt(info)
    assert "9.9.9" in msg
    low = msg.lower()
    assert "install" in low and "close" in low


def test_the_code_only_prompt_does_not_promise_an_install(monkeypatch):
    monkeypatch.setattr(updater, "gate_present", lambda: True)
    low = updater.update_prompt(_info(None)).lower()
    assert "restart" in low


def test_hash_lines_are_hidden_from_the_user():
    """Notlardaki SHA256 satirlari makine icin; kullaniciya gosterilmez."""
    info = updater.UpdateInfo(
        version="9.9.9",
        notes="Kumeleme eklendi\n\nSHA256: " + ZIP_SHA + "\nSETUP_SHA256: " + SETUP_SHA,
        asset_url="u", sha256=ZIP_SHA, setup_url="s", setup_sha256=SETUP_SHA)
    msg = updater.update_prompt(info)
    assert "Kumeleme eklendi" in msg
    assert "SHA256" not in msg
    assert ZIP_SHA not in msg and SETUP_SHA not in msg


# -- kapisiz EXE'yi yakalama -------------------------------------------------
#
# Lisans kapisi EXE'nin ICINE gomulu; src.zip guncellemesi EXE'yi
# degistiremez. Yani eski bir EXE en guncel kodu alsa bile kapisiz kalir ve
# kullanici guncellemeyi reddederse sonsuza kadar izinsiz calisir.
#
# updater artik src/ icinde ve guncel oldugu icin kendi EXE'sini sorgulayabilir:
# license_client SADECE kapili EXE'lerin icinde bulunur, dolayisiyla import
# denemesi "bu EXE kapili mi?" sorusunu cevaplar.

class _Client:
    """Sahte license_client."""

    def __init__(self, configured):
        self._configured = configured

    def is_configured(self):
        return self._configured


def test_a_bundled_client_without_a_secret_is_NOT_a_gate(monkeypatch):
    """ESKI VARSAYIM YANLISTI: "license_client sadece kapili EXE'lerin
    icindedir" deniyordu. launcher.py onu KOSULSUZ import ediyor, yani
    PyInstaller her derlemeye koyuyor. Kosullu olan tek sey
    license_secret.txt; o yoksa PDF-Renamer.spec uyari basip devam ediyor
    ve require() `is_configured()` False oldugu icin hicbir sey sormadan
    donuyor -- kapi KAPALI. Eski kontrol bu EXE'ye "kapisi var" diyor,
    dolayisiyla tam kuruluma hic zorlanmiyor ve makine sonsuza kadar
    lisanssiz calisiyordu."""
    monkeypatch.setattr(updater, "_import_license_client",
                        lambda: _Client(configured=False))
    assert updater.gate_present() is False


def test_a_client_with_a_secret_is_a_real_gate(monkeypatch):
    monkeypatch.setattr(updater, "_import_license_client",
                        lambda: _Client(configured=True))
    assert updater.gate_present() is True


def test_an_exe_whose_gate_is_off_must_take_the_full_install(monkeypatch):
    """Kapiyi ancak setup.exe getirebilir: src.zip EXE'nin icine
    dokunamaz."""
    monkeypatch.setattr(updater, "_import_license_client",
                        lambda: _Client(configured=False))
    assert updater.decide_update_kind(_info(SETUP_SHA)) == "required"


def test_an_old_client_that_cannot_be_asked_counts_as_no_gate(monkeypatch):
    """Yeni updater (src.zip'ten) eski bir EXE'nin icindeki
    license_client ile karsilasabilir; onda is_configured olmayabilir.
    Emin olamadigimizda GUVENLI yon: kapi yok say, tam kurulum zorla."""
    monkeypatch.setattr(updater, "_import_license_client", lambda: object())
    assert updater.gate_present() is False


def test_a_gateless_exe_must_take_the_full_install(monkeypatch):
    monkeypatch.setattr(updater, "gate_present", lambda: False)
    assert updater.decide_update_kind(_info(SETUP_SHA)) == "required"


def test_without_a_setup_a_gateless_exe_is_not_nagged(monkeypatch):
    """Kuracak bir sey yoksa zorunlu demenin anlami yok."""
    monkeypatch.setattr(updater, "gate_present", lambda: False)
    assert updater.decide_update_kind(_info(None)) == "code"


def test_a_required_update_does_not_reveal_that_it_is_forced(monkeypatch):
    """Zorunluluk kullaniciya SOYLENMEZ; metin normal tam kurulum gibidir."""
    monkeypatch.setattr(updater, "gate_present", lambda: False)
    low = updater.update_prompt(_info(SETUP_SHA)).lower()
    assert "required" not in low
    assert "licence" not in low
    assert "full install" in low


# -- indirme ilerlemesi ------------------------------------------------------
#
# Kurulum dosyasi ~110 MB. Eskiden arayuz is parcaciginda, ilerleme
# bildirmeden iniyordu: kullanici "evet" dedikten sonra program dakikalarca
# donmus gorunuyor, cogu zaman kapatiliyordu.

def test_the_download_reports_how_far_it_has_got(tmp_path, monkeypatch):
    seen = []
    payload = b"x" * (200 * 1024)          # 64 KB'lik parcalardan birkac tane

    class FakeResponse:
        def __init__(self):
            self._data = payload
            self._at = 0
            self.headers = {"Content-Length": str(len(payload))}

        def read(self, size):
            chunk = self._data[self._at:self._at + size]
            self._at += len(chunk)
            return chunk

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(updater.urllib.request, "urlopen",
                        lambda *a, **k: FakeResponse())
    dest = tmp_path / "f.bin"
    updater._http_download("https://x/f", str(dest),
                           progress=lambda done, total: seen.append((done, total)))

    assert dest.read_bytes() == payload
    assert seen, "hic ilerleme bildirilmedi"
    assert seen[-1][0] == len(payload)
    assert seen[-1][1] == len(payload), "toplam boyut bildirilmeli"


def test_download_setup_passes_the_progress_through(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(
        updater, "_http_download",
        lambda url, d, timeout=30, progress=None: (
            open(d, "wb").write(SETUP_BYTES),
            progress and progress(len(SETUP_BYTES), len(SETUP_BYTES))))
    updater.download_setup(_info(SETUP_SHA), str(tmp_path / "s.exe"),
                           progress=lambda d, t: seen.append((d, t)))
    assert seen


# -- tam kurulum ISTISNA olmali, kural degil --------------------------------
#
# Once her setup'li release tam kurulum zorluyordu. Oysa kapisi olan bir
# makinenin exe'sini degistirmeye gerek yok: calisan src.zip yolu dururken
# 110 MB'lik kirilgan yoldan gecirmek yanlisti. Artik tam kurulum yalnizca
# kapisiz makinelerde, ya da notlarda acikca istendiginde yapiliyor.

def test_a_gated_machine_takes_the_light_code_update(monkeypatch):
    monkeypatch.setattr(updater, "gate_present", lambda: True)
    assert updater.decide_update_kind(_info(SETUP_SHA)) == "code"


def test_a_gateless_machine_still_must_do_the_full_install(monkeypatch):
    monkeypatch.setattr(updater, "gate_present", lambda: False)
    assert updater.decide_update_kind(_info(SETUP_SHA)) == "required"


def test_notes_can_demand_a_full_install(monkeypatch):
    """Exe'nin kendisi degistiginde (yeni bagimlilik gibi) zorunlu kilinabilir."""
    monkeypatch.setattr(updater, "gate_present", lambda: True)
    info = _info(SETUP_SHA)
    info.notes = "Yeni surum\n\n" + updater.FULL_INSTALL_MARKER
    assert updater.decide_update_kind(info) == "setup"
