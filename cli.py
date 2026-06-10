"""Console version (old V1-style flow), in English.

Scans the PDFs in a folder and renames them, with the same '[OK] / [X]' style
output. All improvements (all pages, prefix/suffix, safe conflicts, log/undo)
apply here too.

Usage:
    python cli.py                 # process the current folder
    python cli.py C:\\path         # process a specific folder
    python cli.py --preview       # show what would happen, change nothing
    python cli.py --undo          # undo the last batch
    python cli.py --suffix -REV   # append text after the code (no space)
"""
import argparse
import os
import sys

from config import Settings
import core
import renamer


def _print_result(r: core.FileResult) -> None:
    if r.status == "renamed":
        print(f"[OK] {r.old_name}  ->  {r.new_name}")
    elif r.status == "preview":
        print(f"[~~] {r.old_name}  ->  {r.new_name}  (preview)")
    elif r.status == "already":
        print(f"[=] {r.old_name}  (already correct)")
    elif r.status == "not_found":
        print(f"[X] {r.old_name}  (no code found)")
    else:
        print(f"[!] {r.old_name}  (ERROR: {r.message})")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="PDF Auto Renamer")
    parser.add_argument("folder", nargs="?", default=os.getcwd(),
                        help="Folder to process (default: current folder)")
    parser.add_argument("--preview", action="store_true",
                        help="Show what would happen, change nothing")
    parser.add_argument("--undo", action="store_true",
                        help="Undo the last rename batch")
    parser.add_argument("--all-pages", dest="all_pages",
                        action=argparse.BooleanOptionalAction, default=True,
                        help="Scan all pages (default: on)")
    parser.add_argument("--ocr", action="store_true",
                        help="Try OCR for scanned PDFs (needs Tesseract)")
    parser.add_argument("--prefix", default=None, help="Document code prefix")
    parser.add_argument("--suffix", default="",
                        help="Text appended after the code (no space)")
    args = parser.parse_args(argv)

    print("=" * 44)
    print("   PDF AUTO RENAMER  V2.0  (console)")
    print("=" * 44)

    if args.undo:
        print(f"\nUndoing: {args.folder}")
        outcomes = renamer.undo_last(args.folder)
        if not outcomes:
            print("[i] Nothing to undo.")
            return 0
        for o in outcomes:
            if o.status == "renamed":
                print(f"[OK] {o.old_name}  ->  {o.new_name}")
            else:
                print(f"[!] {o.old_name}  (ERROR: {o.message})")
        return 0

    settings = Settings(
        folder=args.folder,
        all_pages=args.all_pages,
        use_ocr=args.ocr,
        suffix=args.suffix,
        dry_run=args.preview,
    )
    if args.prefix:
        settings.prefix = args.prefix

    pdfs = core.list_pdfs(settings.effective_folder(), settings.recursive)
    if not pdfs:
        print("\n[!] No PDF files found in this folder!")
        print(f"Location: {settings.effective_folder()}")
        return 0

    summary = core.process_folder(
        settings,
        progress=lambda i, n, r: (print(f"\nProcessing ({i}/{n}): {r.old_name}"),
                                  _print_result(r)),
    )

    print("\n" + "=" * 44)
    print("DONE!")
    print(f"  Renamed     : {summary.renamed}")
    print(f"  Already OK  : {summary.already}")
    print(f"  Not found   : {summary.not_found}")
    print(f"  Errors      : {summary.errors}")
    print("=" * 44)
    return 0


if __name__ == "__main__":
    code = main()
    if sys.stdin is not None and sys.stdin.isatty():
        try:
            input("\nPress Enter to exit...")
        except EOFError:
            pass
    sys.exit(code)
