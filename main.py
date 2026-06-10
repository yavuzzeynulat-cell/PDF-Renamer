"""Entry point.

Double-clicking / running 'python main.py' opens the windowed GUI.
For the console version, run: 'python cli.py'.
"""
import sys


def main() -> int:
    try:
        import gui
    except Exception as exc:
        print("Could not start the GUI:", exc)
        print("Try the console version: python cli.py")
        return 1
    gui.main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
