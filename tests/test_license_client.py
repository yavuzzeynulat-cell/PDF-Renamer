"""
test_license_client.py — Lisans kapısının testleri.

Çalıştırma:  python -m pytest test_license_client.py -q

Pencere AÇILMAZ: show() enjekte edilir. Ağ testleri localhost'ta gerçek bir
HTTP sunucusu kaldırır — mock değil, gerçek istek/cevap.
"""

import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import license_client as lc


# =============================================================== saf mantık

def test_machine_id_format():
    assert lc.format_machine_id("a4f291c73b08d512ffff") == "A4F2-91C7-3B08-D512"


def test_machine_id_is_stable_on_this_machine():
    assert lc.machine_id() == lc.machine_id()


def test_machine_id_shape():
    parts = lc.machine_id().split("-")
    assert len(parts) == 4
    assert all(len(p) == 4 for p in parts)
    assert all(c in "0123456789ABCDEF" for p in parts for c in p)


def test_compare_versions_is_numeric():
    assert lc.compare_versions("0.10.0", "0.9.0") == 1
    assert lc.compare_versions("0.9.0", "0.10.0") == -1
    assert lc.compare_versions("1.2.3", "1.2.3") == 0


def test_compare_versions_pads_missing_parts():
    assert lc.compare_versions("1.2", "1.2.0") == 0
    assert lc.compare_versions("2", "1.9.9") == 1


def test_compare_versions_survives_garbage():
    # Sunucudan saçma bir sürüm gelirse çökmemeli.
    assert lc.compare_versions("abc", "0.1.0") == -1


# =============================================================== karar

def test_active_with_plenty_of_days_runs_silently():
    action, _title, _msg = lc.decide_action({"status": "active", "days_left": 30})
    assert action == "run"


def test_active_with_few_days_warns_but_runs():
    action, _title, msg = lc.decide_action({"status": "active", "days_left": 2})
    assert action == "warn"
    assert "2" in msg


def test_pending_exits_and_shows_machine_id():
    action, _title, msg = lc.decide_action({"status": "pending"}, machine="A4F2-91C7-3B08-D512")
    assert action == "exit"
    assert "A4F2-91C7-3B08-D512" in msg


def test_expired_exits_with_date():
    action, _title, msg = lc.decide_action({"status": "expired", "expires_at": "2026-10-04"})
    assert action == "exit"
    assert "2026-10-04" in msg


def test_blocked_exits():
    assert lc.decide_action({"status": "blocked"})[0] == "exit"


def test_unknown_status_exits_rather_than_running():
    # Tanımadığı bir cevaba "çalış" DEMEMELİ; güvenli taraf kapalı taraftır.
    assert lc.decide_action({"status": "whatever"})[0] == "exit"
    assert lc.decide_action({})[0] == "exit"


# =============================================================== imza

def test_signature_roundtrip():
    sig = lc.make_signature("s", ["a", "b"])
    assert lc.verify_signature("s", ["a", "b"], sig) is True


def test_signature_rejects_tampering():
    sig = lc.make_signature("s", ["a", "b"])
    assert lc.verify_signature("s", ["a", "c"], sig) is False
    assert lc.verify_signature("wrong", ["a", "b"], sig) is False
    assert lc.verify_signature("s", ["a", "b"], "deadbeef") is False
    assert lc.verify_signature("s", ["a", "b"], None) is False


# =============================================================== güncelleme kararı

def test_no_update_when_field_missing():
    assert lc.decide_update(None, "0.2.0")[0] == "none"
    assert lc.decide_update({}, "0.2.0")[0] == "none"


def test_no_update_when_same_version():
    assert lc.decide_update({"version": "0.2.0", "mandatory": False}, "0.2.0")[0] == "none"


def test_no_update_when_server_is_behind():
    assert lc.decide_update({"version": "0.1.0", "mandatory": False}, "0.2.0")[0] == "none"


def test_offer_when_newer_and_optional():
    action, msg = lc.decide_update(
        {"version": "0.3.0", "notes": "Relations fix", "mandatory": False}, "0.2.0")
    assert action == "offer"
    assert "0.3.0" in msg
    assert "Relations fix" in msg


def test_force_when_mandatory():
    assert lc.decide_update({"version": "0.3.0", "mandatory": True}, "0.2.0")[0] == "force"


def test_update_version_comparison_is_numeric():
    assert lc.decide_update({"version": "0.10.0", "mandatory": False}, "0.9.0")[0] == "offer"


# =============================================================== kurulmamış sistem

def test_is_configured_false_with_placeholder_secret(monkeypatch):
    monkeypatch.setattr(lc, "SECRET", lc.UNCONFIGURED_SECRET)
    assert lc.is_configured() is False


def test_is_configured_true_with_real_secret(monkeypatch):
    monkeypatch.setattr(lc, "SECRET", "a" * 64)
    assert lc.is_configured() is True


def test_require_does_nothing_when_not_configured(monkeypatch):
    """
    Panel henüz yayına alınmadıysa kapı DEVREYE GİRMEZ.
    Aksi hâlde program, var olmayan bir sunucuya sorup hiç açılmaz — çalışan
    bir programı kurulum tamamlanmadan kilitlememeliyiz.
    """
    monkeypatch.setattr(lc, "SECRET", lc.UNCONFIGURED_SECRET)
    asked = []
    monkeypatch.setattr(lc, "ask_server", lambda *a, **k: asked.append(1))
    monkeypatch.setattr(lc, "read_user_name", lambda: "")
    show = _Recorder()
    lc.require(version="0.2.0", show=show)      # SystemExit YOK
    assert asked == []                          # sunucuya hiç sorulmadı
    assert show.calls == []                     # isim bile sorulmadı


def test_gate_is_enforced_once_configured(server, named):
    """SECRET doldurulduğu an kapı normal çalışır."""
    server.reply = _reply("pending", lc.machine_id())
    with pytest.raises(SystemExit):
        lc.require(version="0.2.0", show=_Recorder())


# =============================================================== ağ

class _Handler(BaseHTTPRequestHandler):
    """Sahte lisans sunucusu — cevabı sınıf değişkeninden verir."""

    reply = {}
    status = 200
    raw_body = None
    last_headers = {}

    def do_POST(self):
        self._respond()

    def do_GET(self):
        self._respond()

    def _respond(self):
        _Handler.last_headers = dict(self.headers)
        n = int(self.headers.get("content-length", 0) or 0)
        if n:
            self.rfile.read(n)
        payload = (_Handler.raw_body if _Handler.raw_body is not None
                   else json.dumps(_Handler.reply).encode("utf-8"))
        self.send_response(_Handler.status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


@pytest.fixture
def server(monkeypatch):
    _Handler.reply = {}
    _Handler.status = 200
    _Handler.raw_body = None
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setattr(lc, "SERVER_URL", f"http://127.0.0.1:{srv.server_port}")
    monkeypatch.setattr(lc, "SECRET", "test-secret")
    yield _Handler
    srv.shutdown()
    srv.server_close()


def _reply(status, machine, nonce="fixed", expires="", update=None):
    """Sunucunun üreteceği cevabı ve imzayı birebir taklit eder."""
    uver = update["version"] if update else ""
    usha = update["sha256"] if update else ""
    return {
        "status": status,
        "expires_at": expires or None,
        "days_left": 30,
        "message": None,
        "update": update,
        "signature": lc.make_signature(
            "test-secret",
            [lc.PROGRAM_ID, machine, status, expires, nonce, uver, usha]),
    }


class _Recorder:
    """show() yerine geçer — hangi pencere açıldığını kaydeder."""

    def __init__(self, answer=True):
        self.calls = []
        self.answer = answer

    def __call__(self, kind, title, message):
        self.calls.append((kind, title, message))
        return self.answer


@pytest.fixture
def named(monkeypatch):
    """Ad zaten kayıtlı — isim sorma akışını devre dışı bırakır."""
    monkeypatch.setattr(lc, "read_user_name", lambda: "Test User")
    monkeypatch.setattr(lc, "_new_nonce", lambda: "fixed")


def test_require_runs_when_active(server, named):
    server.reply = _reply("active", lc.machine_id())
    show = _Recorder()
    lc.require(version="0.2.0", show=show)          # SystemExit BEKLENMİYOR
    assert show.calls == []


def test_require_exits_when_pending(server, named):
    machine = lc.machine_id()
    server.reply = _reply("pending", machine)
    show = _Recorder()
    with pytest.raises(SystemExit):
        lc.require(version="0.2.0", show=show)
    assert machine in show.calls[0][2]


def test_require_exits_when_expired(server, named):
    server.reply = _reply("expired", lc.machine_id(), expires="2026-01-01")
    show = _Recorder()
    with pytest.raises(SystemExit):
        lc.require(version="0.2.0", show=show)
    assert "2026-01-01" in show.calls[0][2]


def test_require_exits_when_signature_is_wrong(server, named):
    server.reply = {"status": "active", "days_left": 30, "signature": "de" * 32}
    show = _Recorder()
    with pytest.raises(SystemExit):
        lc.require(version="0.2.0", show=show)
    assert "verif" in show.calls[0][2].lower()


def test_require_exits_when_server_unreachable(monkeypatch):
    monkeypatch.setattr(lc, "SECRET", "a" * 64)                   # sistem kurulmuş
    monkeypatch.setattr(lc, "SERVER_URL", "http://127.0.0.1:9")   # kapalı port
    monkeypatch.setattr(lc, "ATTEMPTS", 1)
    monkeypatch.setattr(lc, "RETRY_WAIT", 0)
    monkeypatch.setattr(lc, "read_user_name", lambda: "Test User")
    show = _Recorder()
    with pytest.raises(SystemExit):
        lc.require(version="0.2.0", show=show)
    assert "internet" in show.calls[0][2].lower()


def test_require_exits_when_server_returns_error(server, named):
    server.status = 404
    server.raw_body = b'{"error":"unknown program"}'
    show = _Recorder()
    with pytest.raises(SystemExit):
        lc.require(version="0.2.0", show=show)


def test_require_asks_for_name_when_missing(server, monkeypatch):
    monkeypatch.setattr(lc, "read_user_name", lambda: "")
    monkeypatch.setattr(lc, "_new_nonce", lambda: "fixed")
    monkeypatch.setattr(lc, "ask_user_name", lambda: "Yeni Kullanici")
    written = {}
    monkeypatch.setattr(lc, "write_user_name", lambda n: written.update(name=n))
    server.reply = _reply("active", lc.machine_id())
    lc.require(version="0.2.0", show=_Recorder())
    assert written["name"] == "Yeni Kullanici"


def test_require_exits_when_name_is_refused(server, monkeypatch):
    monkeypatch.setattr(lc, "read_user_name", lambda: "")
    monkeypatch.setattr(lc, "ask_user_name", lambda: "")     # kullanıcı iptal etti
    with pytest.raises(SystemExit):
        lc.require(version="0.2.0", show=_Recorder())


def test_warn_then_run_when_expiring_soon(server, named):
    reply = _reply("active", lc.machine_id())
    reply["days_left"] = 2
    server.reply = reply
    show = _Recorder()
    lc.require(version="0.2.0", show=show)                   # çıkmamalı
    assert show.calls[0][0] == "info"


def test_requests_send_a_real_user_agent(server, named):
    """
    Cloudflare, varsayılan "Python-urllib/3.x" kimliğini bot sayıp 403 veriyor.
    Program bu yüzden hiç bağlanamıyordu — kendi kimliğini göndermeli.
    """
    server.reply = _reply("active", lc.machine_id())
    lc.require(version="0.2.0", show=_Recorder())
    ua = server.last_headers.get("User-Agent", "")
    assert "python-urllib" not in ua.lower()
    assert lc.PROGRAM_ID in ua or "EDMS" in ua


# =============================================================== indirme

def test_download_rejects_wrong_hash(tmp_path, monkeypatch):
    monkeypatch.setattr(lc, "_fetch_bytes", lambda url, progress=None: b"gercek icerik")
    dest = tmp_path / "Setup.exe"
    with pytest.raises(lc.LicenseTrustError):
        lc.download_update("http://x", "0" * 64, dest)
    assert not dest.exists()          # bozuk dosya diskte bırakılmaz


def test_download_accepts_correct_hash(tmp_path, monkeypatch):
    payload = b"hello setup"
    monkeypatch.setattr(lc, "_fetch_bytes", lambda url, progress=None: payload)
    dest = tmp_path / "Setup.exe"
    got = lc.download_update("http://x", hashlib.sha256(payload).hexdigest(), dest)
    assert got.read_bytes() == payload


def test_download_hash_check_is_case_insensitive(tmp_path, monkeypatch):
    payload = b"abc"
    monkeypatch.setattr(lc, "_fetch_bytes", lambda url, progress=None: payload)
    dest = tmp_path / "Setup.exe"
    lc.download_update("http://x", hashlib.sha256(payload).hexdigest().upper(), dest)
    assert dest.exists()


def test_download_retries_after_a_truncated_attempt(tmp_path, monkeypatch):
    """
    Büyük dosyada bağlantı kopabiliyor (yerel denemede 58 MB'lık kurulumda
    görüldü). İlk deneme eksik gelirse yeniden denenmeli.
    """
    payload = b"complete setup file"
    attempts = []

    def flaky(url, progress=None):
        attempts.append(1)
        if len(attempts) == 1:
            return payload[:5]           # kopmuş indirme
        return payload

    monkeypatch.setattr(lc, "_fetch_bytes", flaky)
    monkeypatch.setattr(lc, "RETRY_WAIT", 0)
    dest = tmp_path / "Setup.exe"
    got = lc.download_update("http://x", hashlib.sha256(payload).hexdigest(), dest)
    assert got.read_bytes() == payload
    assert len(attempts) == 2


def test_download_gives_up_after_all_attempts(tmp_path, monkeypatch):
    monkeypatch.setattr(lc, "_fetch_bytes", lambda url, progress=None: b"always wrong")
    monkeypatch.setattr(lc, "RETRY_WAIT", 0)
    dest = tmp_path / "Setup.exe"
    with pytest.raises(lc.LicenseTrustError):
        lc.download_update("http://x", "0" * 64, dest)
    assert not dest.exists()


def test_download_retries_on_network_error(tmp_path, monkeypatch):
    payload = b"setup"
    attempts = []

    def flaky(url, progress=None):
        attempts.append(1)
        if len(attempts) == 1:
            raise ConnectionResetError("10054")
        return payload

    monkeypatch.setattr(lc, "_fetch_bytes", flaky)
    monkeypatch.setattr(lc, "RETRY_WAIT", 0)
    dest = tmp_path / "Setup.exe"
    lc.download_update("http://x", hashlib.sha256(payload).hexdigest(), dest)
    assert len(attempts) == 2


# =============================================================== güncelleme akışı

UPDATE = {"version": "0.3.0", "notes": "fix", "mandatory": False,
          "url": "http://x/download", "sha256": "ab" * 32}


def test_optional_update_declined_continues(server, named):
    server.reply = _reply("active", lc.machine_id(), update=dict(UPDATE))
    show = _Recorder(answer=False)                # kullanıcı "Later" dedi
    lc.require(version="0.2.0", show=show)        # SystemExit YOK
    assert show.calls[0][0] == "question"


def test_mandatory_update_refused_exits(server, named):
    server.reply = _reply("active", lc.machine_id(),
                          update=dict(UPDATE, mandatory=True))
    show = _Recorder(answer=False)                # kullanıcı "hayır" dedi
    with pytest.raises(SystemExit):
        lc.require(version="0.2.0", show=show)


def test_accepted_update_downloads_and_installs(server, named, monkeypatch, tmp_path):
    payload = b"setup bytes"
    monkeypatch.setattr(lc, "_fetch_bytes", lambda url, progress=None: payload)
    # sha256 imzaya girdiği için önce onu kurup sonra cevabı üretiyoruz.
    update = dict(UPDATE, sha256=hashlib.sha256(payload).hexdigest())
    server.reply = _reply("active", lc.machine_id(), update=update)

    installed = {}
    monkeypatch.setattr(lc, "install_update", lambda p: installed.update(path=p))
    monkeypatch.setattr(lc, "_download_dir", lambda: tmp_path)

    lc.require(version="0.2.0", show=_Recorder(answer=True))
    assert installed["path"].exists()
    assert installed["path"].read_bytes() == payload


def test_update_with_bad_hash_does_not_install(server, named, monkeypatch, tmp_path):
    server.reply = _reply("active", lc.machine_id(), update=dict(UPDATE))
    monkeypatch.setattr(lc, "_fetch_bytes", lambda url, progress=None: b"wrong bytes")
    installed = {}
    monkeypatch.setattr(lc, "install_update", lambda p: installed.update(path=p))
    monkeypatch.setattr(lc, "_download_dir", lambda: tmp_path)

    show = _Recorder(answer=True)
    lc.require(version="0.2.0", show=show)        # isteğe bağlıydı -> devam eder
    assert installed == {}
    assert any("verif" in m.lower() or "download" in m.lower() for _k, _t, m in show.calls)


def test_mandatory_update_with_bad_hash_exits(server, named, monkeypatch, tmp_path):
    server.reply = _reply("active", lc.machine_id(), update=dict(UPDATE, mandatory=True))
    monkeypatch.setattr(lc, "_fetch_bytes", lambda url, progress=None: b"wrong bytes")
    monkeypatch.setattr(lc, "install_update", lambda p: None)
    monkeypatch.setattr(lc, "_download_dir", lambda: tmp_path)
    with pytest.raises(SystemExit):
        lc.require(version="0.2.0", show=_Recorder(answer=True))


def test_update_is_checked_only_after_licence_passes(server, named, monkeypatch, tmp_path):
    """Lisans kapalıysa güncelleme hiç sorulmamalı."""
    server.reply = _reply("blocked", lc.machine_id(), update=dict(UPDATE))
    show = _Recorder(answer=True)
    with pytest.raises(SystemExit):
        lc.require(version="0.2.0", show=show)
    assert all(kind != "question" for kind, _t, _m in show.calls)
