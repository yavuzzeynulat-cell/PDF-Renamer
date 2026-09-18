"""Lisans kapisinin launcher'a dogru baglandigini dogrular.

Kapi LAUNCHER'da (main.py'de degil): kullanicinin cift tikladigi tek yer
orasi ve src/ yuklenmeden once calismasi gerekir. Ayrica launcher'in
"her cokmede src_backup'a geri don" mantigi, lisans REDDINI bir cokme
sanmamalidir -- yoksa izin verilmeyen makinede program surekli geri
yukleme yapmaya calisir.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import launcher  # noqa: E402


def test_gate_runs_before_the_app_is_loaded(monkeypatch):
    order = []
    monkeypatch.setattr(launcher.license_client, "require",
                        lambda **kw: order.append("gate"))
    monkeypatch.setattr(launcher, "_run_src", lambda: order.append("app"))

    launcher.main()

    assert order == ["gate", "app"]


def test_the_app_never_starts_when_the_licence_is_denied(monkeypatch):
    started = []

    def deny(**kw):
        raise SystemExit(1)

    monkeypatch.setattr(launcher.license_client, "require", deny)
    monkeypatch.setattr(launcher, "_run_src", lambda: started.append(1))

    with pytest.raises(SystemExit):
        launcher.main()

    assert started == []


def test_a_denied_licence_does_not_trigger_a_rollback(monkeypatch):
    """Lisans reddi bir cokme degildir; src_backup'a donulmemeli."""
    rolled = []

    def deny(**kw):
        raise SystemExit(1)

    monkeypatch.setattr(launcher.license_client, "require", deny)
    monkeypatch.setattr(launcher, "_rollback", lambda: rolled.append(1) or True)
    monkeypatch.setattr(launcher, "_run_src", lambda: None)

    with pytest.raises(SystemExit):
        launcher.main()

    assert rolled == []


def test_the_gate_is_told_the_current_version(monkeypatch):
    """Panel hangi surumun calistigini gorebilmeli (guncelleme teklifi icin)."""
    seen = {}
    monkeypatch.setattr(launcher.license_client, "require",
                        lambda **kw: seen.update(kw))
    monkeypatch.setattr(launcher, "_run_src", lambda: None)

    launcher.main()

    assert seen.get("version") == launcher._local_version()


def test_local_version_matches_version_txt():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "version.txt"), encoding="utf-8") as fh:
        expected = fh.read().strip()
    assert launcher._local_version() == expected


def test_the_client_is_wired_to_this_program():
    """Sabitler sablon halinde kalmamali (SECRET haric -- onu panel verir)."""
    import license_client as lc
    assert lc.PROGRAM_ID != "BURAYA_PROGRAM_ID"
    assert lc.TITLE != "BURAYA PROGRAM ADI"
