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
                        lambda url, d, timeout=30: open(d, "wb").write(SETUP_BYTES))
    assert updater.download_setup(_info(SETUP_SHA), str(dest)) is True
    assert dest.read_bytes() == SETUP_BYTES


def test_a_tampered_setup_is_rejected_and_deleted(tmp_path, monkeypatch):
    dest = tmp_path / "setup.exe"
    monkeypatch.setattr(updater, "_http_download",
                        lambda url, d, timeout=30: open(d, "wb").write(b"kotu amacli"))
    assert updater.download_setup(_info(SETUP_SHA), str(dest)) is False
    assert not dest.exists(), "dogrulamayi gecemeyen dosya diskte birakilmamali"


def test_a_setup_without_a_hash_is_never_downloaded(tmp_path, monkeypatch):
    dest = tmp_path / "setup.exe"
    called = []
    monkeypatch.setattr(updater, "_http_download",
                        lambda url, d, timeout=30: called.append(1))
    assert updater.download_setup(_info(None), str(dest)) is False
    assert called == [], "hash yokken indirme bile denenmemeli"


# -- kurulumu baslatma -------------------------------------------------------

SETUP = r"C:\tmp\setup.exe"
APP = r"C:\app\PDF-Renamer.exe"


def test_the_installer_shows_its_progress():
    """/VERYSILENT hicbir sey gostermiyordu: program kapaniyor, arkada
    sessizce kuruluyor, kullanici ne oldugunu anlayamiyordu. /SILENT
    ilerleme penceresini gosterir (sihirbaz sayfalari yine yok)."""
    joined = " ".join(updater.build_install_command(SETUP, APP))
    assert "/SILENT" in joined
    assert "/VERYSILENT" not in joined, "sessiz kurulum takip edilemiyor"
    assert "/NORESTART" in joined
    assert SETUP in joined


def test_the_installer_is_given_time_to_take_the_file_lock():
    joined = " ".join(updater.build_install_command(SETUP, APP))
    assert "ping" in joined, "gecikme yok: calisan exe hala kilitli olabilir"


def test_the_app_comes_back_by_itself_after_the_install():
    """installer.iss'teki [Run] satirinda `skipifsilent` var, yani sessiz
    kurulumda program yeniden ACILMIYOR. Geri getirmeyi biz ustleniyoruz."""
    joined = " ".join(updater.build_install_command(SETUP, APP))
    assert APP in joined
    assert joined.index("setup.exe") < joined.index("PDF-Renamer.exe"), \
        "once kurulum bitmeli, sonra program acilmali"


def test_without_a_relaunch_path_nothing_extra_is_started():
    joined = " ".join(updater.build_install_command(SETUP))
    assert "/SILENT" in joined
    assert "start" not in joined


# -- hangi yol secilir -------------------------------------------------------

def test_a_release_with_a_setup_takes_the_full_install_path():
    assert updater.decide_update_kind(_info(SETUP_SHA)) == "setup"


def test_a_release_without_a_setup_stays_on_the_code_only_path():
    assert updater.decide_update_kind(_info(None)) == "code"


def test_the_user_is_told_a_full_install_is_coming():
    """Tam kurulum programi kapatip installer calistirir; surpriz olmamali."""
    msg = updater.update_prompt(_info(SETUP_SHA))
    assert "9.9.9" in msg
    low = msg.lower()
    assert "install" in low and "close" in low


def test_the_code_only_prompt_does_not_promise_an_install():
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

def test_the_gate_is_detected_when_the_client_can_be_imported(monkeypatch):
    monkeypatch.setattr(updater, "_import_license_client", lambda: object())
    assert updater.gate_present() is True


def test_a_missing_client_means_the_exe_has_no_gate(monkeypatch):
    def boom():
        raise ImportError("no module named license_client")
    monkeypatch.setattr(updater, "_import_license_client", boom)
    assert updater.gate_present() is False


def test_a_gateless_exe_must_take_the_full_install(monkeypatch):
    monkeypatch.setattr(updater, "gate_present", lambda: False)
    assert updater.decide_update_kind(_info(SETUP_SHA)) == "required"


def test_a_gated_exe_is_merely_offered_the_full_install(monkeypatch):
    monkeypatch.setattr(updater, "gate_present", lambda: True)
    assert updater.decide_update_kind(_info(SETUP_SHA)) == "setup"


def test_without_a_setup_a_gateless_exe_is_not_nagged(monkeypatch):
    """Kuracak bir sey yoksa zorunlu demenin anlami yok."""
    monkeypatch.setattr(updater, "gate_present", lambda: False)
    assert updater.decide_update_kind(_info(None)) == "code"


def test_a_required_update_says_it_cannot_be_skipped(monkeypatch):
    monkeypatch.setattr(updater, "gate_present", lambda: False)
    low = updater.update_prompt(_info(SETUP_SHA)).lower()
    assert "required" in low
