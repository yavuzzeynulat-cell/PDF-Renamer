"""Safe rename + conflict resolution + logging/undo for the PDF renamer tool.

Design goals (fixing the v1 weaknesses):
- Never overwrite an existing file and never lose data.
- Robust conflict numbering: ' (1)', ' (2)', ... instead of a single 'kopya_'.
- Every successful batch is logged as JSON lines so renames can be undone.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import os
import uuid

LOG_NAME = "_rename_log.jsonl"


@dataclass
class RenameOutcome:
    old_name: str            # basename before
    new_name: str | None     # basename after (None if not renamed)
    status: str              # 'renamed' | 'already' | 'error'
    message: str


def _listdir_lower(folder: str) -> set[str]:
    """Return the set of existing basenames in `folder`, lower-cased."""
    try:
        return {name.lower() for name in os.listdir(folder)}
    except OSError:
        return set()


def resolve_conflict(folder: str, desired_basename: str) -> str:
    """Return a basename in `folder` that does not collide with existing files.

    If `desired_basename` is free, return it unchanged; otherwise append
    ' (1)', ' (2)', ... before the extension until a free name is found.
    Collision check is case-insensitive (Windows filesystem).
    """
    existing = _listdir_lower(folder)
    if desired_basename.lower() not in existing:
        return desired_basename

    stem, ext = os.path.splitext(desired_basename)
    counter = 1
    while True:
        candidate = f"{stem} ({counter}){ext}"
        if candidate.lower() not in existing:
            return candidate
        counter += 1


def safe_rename(folder: str, old_basename: str, new_basename: str, *,
                dry_run: bool = False) -> RenameOutcome:
    """Rename folder/old_basename -> a non-colliding name based on new_basename.

    - 'already' (no disk change) if the file is already correctly named
      (case-insensitive equal).
    - Otherwise resolve conflicts then os.rename.
    - dry_run reports the name it WOULD use without touching disk.
    - Any OS error is returned as status 'error' (never raised).
    """
    if old_basename.lower() == new_basename.lower():
        return RenameOutcome(old_basename, old_basename, "already",
                             "Already named correctly.")

    target = resolve_conflict(folder, new_basename)

    if dry_run:
        return RenameOutcome(old_basename, target, "renamed",
                             f"Would rename to '{target}'.")

    try:
        src = os.path.join(folder, old_basename)
        dst = os.path.join(folder, target)
        # Guard against a race between resolve_conflict and rename.
        if os.path.exists(dst):
            target = resolve_conflict(folder, new_basename)
            dst = os.path.join(folder, target)
        os.rename(src, dst)
    except OSError as exc:
        return RenameOutcome(old_basename, None, "error", str(exc))

    return RenameOutcome(old_basename, target, "renamed",
                         f"Renamed to '{target}'.")


def _read_log(path: str) -> list[dict]:
    """Read the JSONL log, tolerating a missing or corrupt file (-> empty)."""
    records: list[dict] = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except (ValueError, json.JSONDecodeError):
                    continue  # skip corrupt line
    except OSError:
        return []
    return records


def _write_log(path: str, records: list[dict]) -> None:
    """Overwrite the JSONL log with `records`."""
    with open(path, "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def write_log(folder: str, entries: list[tuple[str, str]]) -> str:
    """Append successful renames to '_rename_log.jsonl' as one undo batch.

    Each entry is (old_basename, new_basename). Each record carries an ISO
    timestamp and a shared batch id. Returns the log file path.
    """
    path = os.path.join(folder, LOG_NAME)
    batch_id = uuid.uuid4().hex
    timestamp = datetime.now().isoformat()

    with open(path, "a", encoding="utf-8") as fh:
        for old_name, new_name in entries:
            rec = {
                "batch": batch_id,
                "timestamp": timestamp,
                "old_name": old_name,
                "new_name": new_name,
                "undone": False,
            }
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return path


def undo_last(folder: str) -> list[RenameOutcome]:
    """Revert the most recent not-yet-undone batch in '_rename_log.jsonl'.

    Renames each new_name back to old_name. Skips (with an 'error' outcome) any
    entry whose source is missing or whose target already exists. The batch is
    flagged 'undone' so a subsequent call affects the previous batch.
    """
    path = os.path.join(folder, LOG_NAME)
    records = _read_log(path)
    if not records:
        return []

    # Find the last batch that has not been undone, preserving file order.
    pending = [r for r in records if not r.get("undone")]
    if not pending:
        return []
    target_batch = pending[-1]["batch"]
    batch_records = [r for r in records if r.get("batch") == target_batch
                     and not r.get("undone")]

    outcomes: list[RenameOutcome] = []
    # Revert in reverse order so numbered conflicts unwind cleanly.
    for rec in reversed(batch_records):
        old_name = rec["old_name"]
        new_name = rec["new_name"]
        src = os.path.join(folder, new_name)
        dst = os.path.join(folder, old_name)

        if not os.path.exists(src):
            outcomes.append(RenameOutcome(
                new_name, None, "error",
                f"Source '{new_name}' missing; cannot undo."))
            continue
        if os.path.exists(dst) and new_name.lower() != old_name.lower():
            outcomes.append(RenameOutcome(
                new_name, None, "error",
                f"Target '{old_name}' already exists; cannot undo."))
            continue
        try:
            os.rename(src, dst)
        except OSError as exc:
            outcomes.append(RenameOutcome(new_name, None, "error", str(exc)))
            continue
        outcomes.append(RenameOutcome(
            new_name, old_name, "renamed", f"Restored to '{old_name}'."))

    # Mark the whole batch as undone regardless of per-file errors so a second
    # undo moves on to the previous batch.
    for rec in records:
        if rec.get("batch") == target_batch:
            rec["undone"] = True
    _write_log(path, records)

    return outcomes
