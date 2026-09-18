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

def test_the_installer_is_started_silently_after_a_delay():
    cmd = updater.build_install_command(r"C:\tmp\setup.exe")
    joined = " ".join(cmd)
    assert "ping" in joined, "gecikme yok: calisan exe hala kilitli olabilir"
    assert "/VERYSILENT" in joined
    assert "/NORESTART" in joined
    assert r"C:\tmp\setup.exe" in joined


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
