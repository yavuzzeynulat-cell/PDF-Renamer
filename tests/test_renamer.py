"""Tests for renamer.py: conflict numbering, safe rename, log + undo round trip."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from renamer import (  # noqa: E402
    RenameOutcome,
    resolve_conflict,
    safe_rename,
    write_log,
    undo_last,
)

TARGET = "26437-LAB-001.pdf"


def _make_pdf(folder, name: str) -> None:
    with open(os.path.join(str(folder), name), "wb") as fh:
        fh.write(b"%PDF-1.4 dummy")


def test_basic_rename(tmp_path):
    _make_pdf(tmp_path, "a.pdf")
    out = safe_rename(str(tmp_path), "a.pdf", TARGET)
    assert out.status == "renamed"
    assert out.new_name == TARGET
    assert os.path.exists(tmp_path / TARGET)
    assert not os.path.exists(tmp_path / "a.pdf")


def test_conflict_numbering(tmp_path):
    folder = str(tmp_path)
    expected = [TARGET, "26437-LAB-001 (1).pdf", "26437-LAB-001 (2).pdf"]
    for i, exp in enumerate(expected):
        src = f"src{i}.pdf"
        _make_pdf(tmp_path, src)
        out = safe_rename(folder, src, TARGET)
        assert out.status == "renamed"
        assert out.new_name == exp
        assert os.path.exists(tmp_path / exp)


def test_resolve_conflict_free(tmp_path):
    assert resolve_conflict(str(tmp_path), TARGET) == TARGET


def test_already_status_case_insensitive(tmp_path):
    _make_pdf(tmp_path, "26437-LAB-001.PDF")
    out = safe_rename(str(tmp_path), "26437-LAB-001.PDF", "26437-lab-001.pdf")
    assert out.status == "already"
    assert out.new_name == "26437-LAB-001.PDF"
    # disk untouched
    assert os.path.exists(tmp_path / "26437-LAB-001.PDF")


def test_dry_run_does_not_touch_disk(tmp_path):
    _make_pdf(tmp_path, "a.pdf")
    out = safe_rename(str(tmp_path), "a.pdf", TARGET, dry_run=True)
    assert out.status == "renamed"
    assert out.new_name == TARGET
    assert os.path.exists(tmp_path / "a.pdf")
    assert not os.path.exists(tmp_path / TARGET)


def test_error_on_missing_source(tmp_path):
    out = safe_rename(str(tmp_path), "missing.pdf", TARGET)
    assert out.status == "error"
    assert out.new_name is None


def test_log_and_undo_round_trip(tmp_path):
    folder = str(tmp_path)
    # batch 1: rename two files
    _make_pdf(tmp_path, "a.pdf")
    _make_pdf(tmp_path, "b.pdf")
    o1 = safe_rename(folder, "a.pdf", "26437-LAB-001.pdf")
    o2 = safe_rename(folder, "b.pdf", "26437-LAB-002.pdf")
    log_path = write_log(folder, [
        (o1.old_name, o1.new_name),
        (o2.old_name, o2.new_name),
    ])
    assert os.path.exists(log_path)

    # batch 2: rename another file
    _make_pdf(tmp_path, "c.pdf")
    o3 = safe_rename(folder, "c.pdf", "26437-LAB-003.pdf")
    write_log(folder, [(o3.old_name, o3.new_name)])

    # undo most recent batch (batch 2)
    res2 = undo_last(folder)
    assert all(isinstance(r, RenameOutcome) for r in res2)
    assert all(r.status == "renamed" for r in res2)
    assert os.path.exists(tmp_path / "c.pdf")
    assert not os.path.exists(tmp_path / "26437-LAB-003.pdf")

    # undo previous batch (batch 1)
    res1 = undo_last(folder)
    assert all(r.status == "renamed" for r in res1)
    assert os.path.exists(tmp_path / "a.pdf")
    assert os.path.exists(tmp_path / "b.pdf")
    assert not os.path.exists(tmp_path / "26437-LAB-001.pdf")
    assert not os.path.exists(tmp_path / "26437-LAB-002.pdf")

    # nothing left to undo
    res_none = undo_last(folder)
    assert res_none == []


def test_undo_corrupt_log_is_empty(tmp_path):
    log_path = os.path.join(str(tmp_path), "_rename_log.jsonl")
    with open(log_path, "w", encoding="utf-8") as fh:
        fh.write("not valid json\n{also bad}\n")
    assert undo_last(str(tmp_path)) == []


def test_undo_missing_log_is_empty(tmp_path):
    assert undo_last(str(tmp_path)) == []
