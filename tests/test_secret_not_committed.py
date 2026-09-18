"""Gercek SECRET depoya girmemeli.

Bu deponun GitHub uzantisi PUBLIC (otomatik guncelleme release'leri oradan
iniyor, bu yuzden private yapilamaz). SECRET istemci ile sunucu arasindaki
ortak HMAC anahtaridir: sizarsa herkes sahte bir sunucu kurup "izinli"
cevabini imzalayabilir ve lisans kapisi tamamen anlamsizlasir.

Bu yuzden license_client.py depoda YER TUTUCU ile durur; gercek deger
yanindaki license_secret.txt dosyasindan okunur ve o dosya .gitignore'dadir.
"""
from __future__ import annotations

import io
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECRET_FILE = "license_secret.txt"


def _read(name: str) -> str:
    with io.open(os.path.join(ROOT, name), encoding="utf-8") as fh:
        return fh.read()


def test_license_client_source_holds_no_real_secret():
    source = _read("license_client.py")
    leaked = [m for m in re.findall(r'"([0-9a-fA-F]{64})"', source)]
    assert not leaked, (
        "license_client.py icinde 64 haneli gercek bir anahtar var; "
        "depo public, bu deger disari sizar.")


def test_the_secret_file_is_git_ignored():
    ignored = _read(".gitignore").splitlines()
    assert SECRET_FILE in [line.strip() for line in ignored], (
        SECRET_FILE + " .gitignore icinde degil; yanlislikla commitlenebilir.")


def test_the_secret_is_loaded_from_the_untracked_file(tmp_path, monkeypatch):
    import sys
    sys.path.insert(0, ROOT)
    import license_client as lc

    fake = tmp_path / SECRET_FILE
    fake.write_text("a" * 64, encoding="utf-8")
    monkeypatch.setattr(lc, "_secret_dir", lambda: str(tmp_path))

    assert lc._load_secret(lc.UNCONFIGURED_SECRET) == "a" * 64


def test_a_missing_secret_file_leaves_the_gate_switched_off(tmp_path, monkeypatch):
    """Dosya yoksa kapi devreye GIRMEZ; program calismaya devam eder."""
    import sys
    sys.path.insert(0, ROOT)
    import license_client as lc

    monkeypatch.setattr(lc, "_secret_dir", lambda: str(tmp_path))

    assert lc._load_secret(lc.UNCONFIGURED_SECRET) == lc.UNCONFIGURED_SECRET


def test_no_tracked_file_anywhere_contains_a_64_hex_key():
    """git'in gorebildigi HICBIR dosyada 64 haneli anahtar olmamali.

    publish_update.py yayinlarken `git add -A` calistiriyor: gitignore'da
    olmayan her dosya public depoya gider. Bu test, anahtarin yanlislikla
    baska bir dosyayla (yedek, not, log) disari sizmasini engeller.
    """
    import subprocess
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT, capture_output=True, text=True)
    leaked = []
    for name in out.stdout.splitlines():
        path = os.path.join(ROOT, name)
        if not os.path.isfile(path) or os.path.getsize(path) > 2_000_000:
            continue
        try:
            with io.open(path, encoding="utf-8", errors="ignore") as fh:
                body = fh.read()
        except OSError:
            continue
        if re.search(r"[0-9a-f]{64}", body):
            leaked.append(name)
    assert not leaked, "64 haneli anahtar icerebilecek commitlenebilir dosyalar: " + ", ".join(leaked)
