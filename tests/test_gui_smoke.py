import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_window_split_save_open(tmp_path):
    from PySide6.QtWidgets import QApplication
    from cineforge.ui.main_window import MainWindow
    from cineforge.ui.theme import apply_dark_theme

    app = QApplication.instance() or QApplication([])
    apply_dark_theme(app)
    win = MainWindow()
    win.script_edit.setPlainText("First scene here.\n\nSecond scene here.")
    win.scene_list.count()
    from cineforge.core.project import scenes_from_script
    win.project.scenes = scenes_from_script(win.script_edit.toPlainText())
    win._refresh_list(0)
    assert win.scene_list.count() == 2
    win.dur_spin.setValue(6.0)
    assert win.project.scenes[0].duration == 6.0
    f = str(tmp_path / "p.cforge")
    assert win.save_to(f)
    win2 = MainWindow()
    assert win2.load_from(f)
    assert win2.scene_list.count() == 2 and win2.project.scenes[0].duration == 6.0
    win.dirty = win2.dirty = False
    win.close()
    win2.close()
