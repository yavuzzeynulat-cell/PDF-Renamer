"""publish_update.py: EXE'nin ne zaman yeniden derlenmesi gerektigi.

Guncelleme gondermek tek hareket olmali. Bugune kadar kullanici, exe'yi
yeniden derlemesi gerekip gerekmedigine KENDI karar veriyordu; unutunca
release'e bayat bir setup.exe gidiyordu (v2.2.8'den v2.3.2'ye kadar tam
olarak bu oldu: icinde 2.2.7 olan ayni dosya her release'e yuklendi).

Karar aslinda mekanik: kod dosyalari exe'nin YANINDAKI src/ klasorunde
yasar ve src.zip ile guncellenir -- onlar icin derleme GEREKMEZ. Yalnizca
exe'nin ICINE gomulen seyler degisince derleme gerekir.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import publish_update  # noqa: E402


def why(paths):
    return publish_update.exe_needs_rebuild(paths)


# -- derleme GEREKMEZ --------------------------------------------------------

def test_app_code_ships_without_a_rebuild():
    """gui.py, cluster.py vb. src.zip ile gider; exe'ye dokunmaz."""
    assert why(["gui.py", "cluster.py", "grouper.py", "config.py"]) == ""


def test_tests_and_docs_do_not_trigger_a_rebuild():
    assert why(["tests/test_cluster.py", "README.md", ".gitignore"]) == ""


def test_nothing_changed_needs_no_rebuild():
    assert why([]) == ""


def test_the_updater_itself_ships_in_src_zip():
    """updater.py src/ icinde; kendini src.zip ile gunceller."""
    assert why(["updater.py"]) == ""


# -- derleme GEREKIR ---------------------------------------------------------

def test_the_entry_point_forces_a_rebuild():
    """launcher.py exe'nin ICINDE derlenir; src.zip onu degistiremez."""
    assert "launcher.py" in why(["launcher.py"])


def test_the_licence_client_forces_a_rebuild():
    """Lisans kapisi exe'ye gomulu; kullanicilara ancak kurulumla ulasir."""
    assert "license_client.py" in why(["license_client.py"])


def test_a_new_dependency_forces_a_rebuild():
    assert "requirements.txt" in why(["requirements.txt"])


def test_the_build_recipe_forces_a_rebuild():
    assert "PDF-Renamer.spec" in why(["PDF-Renamer.spec"])


def test_the_installer_script_forces_a_rebuild():
    assert "installer.iss" in why(["installer.iss"])


def test_the_icon_forces_a_rebuild():
    assert "assets/app.ico" in why(["assets/app.ico"])


def test_windows_slashes_are_understood():
    """git '/' verir ama elle cagirmada '\\' gelebilir."""
    assert "launcher.py" in why(["launcher.py"])
    assert "assets/app.ico" in why(["assets\\app.ico"])


def test_one_embedded_file_among_many_is_enough():
    assert "launcher.py" in why(["gui.py", "README.md", "launcher.py"])


def test_the_reason_names_every_file_that_forced_it():
    reason = why(["launcher.py", "requirements.txt", "gui.py"])
    assert "launcher.py" in reason
    assert "requirements.txt" in reason
    assert "gui.py" not in reason, "derlemeyi zorlamayan dosya sebepte olmamali"


# -- Inno Setup'i bulma ------------------------------------------------------

def test_the_compiler_is_found_on_the_path(monkeypatch):
    monkeypatch.setattr(publish_update.shutil, "which",
                        lambda name: r"C:\bin\ISCC.exe")
    assert publish_update.find_iscc() == r"C:\bin\ISCC.exe"


def test_the_usual_install_folder_is_searched_when_the_path_misses(monkeypatch, tmp_path):
    """GERCEK OLAY: Inno Setup kullanici klasorune kurulmustu ve PATH'te
    yoktu; yayinlama, EXE derlendikten SONRA "iscc bulunamadi" deyip
    yarida kaldi."""
    monkeypatch.setattr(publish_update.shutil, "which", lambda name: None)
    exe = tmp_path / "Inno Setup 6" / "ISCC.exe"
    exe.parent.mkdir(parents=True)
    exe.write_text("")
    monkeypatch.setattr(publish_update, "ISCC_DIRS", [str(tmp_path)])
    assert publish_update.find_iscc() == str(exe)


def test_nothing_found_returns_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(publish_update.shutil, "which", lambda name: None)
    monkeypatch.setattr(publish_update, "ISCC_DIRS", [str(tmp_path)])
    assert publish_update.find_iscc() == ""
