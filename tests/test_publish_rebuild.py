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
