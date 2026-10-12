"""CineForge entry point."""
from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    if "--selftest" in argv:
        i = argv.index("--selftest")
        out = argv[i + 1] if i + 1 < len(argv) else "cineforge_selftest.mp4"
        from .core.selftest import run_selftest
        return run_selftest(out)
    from PySide6.QtWidgets import QApplication
    from .ui.main_window import MainWindow
    from .ui.theme import apply_dark_theme
    app = QApplication(argv)
    app.setApplicationName("CineForge")
    apply_dark_theme(app)
    win = MainWindow()
    win.show()
    if len(argv) > 1 and argv[1].lower().endswith(".cforge"):
        win.load_from(argv[1])
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
