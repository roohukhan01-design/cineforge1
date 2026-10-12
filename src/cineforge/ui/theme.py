from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


def apply_dark_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    pal = QPalette()
    bg, base, text, accent = QColor(30, 31, 36), QColor(22, 23, 27), QColor(230, 232, 238), QColor(232, 93, 4)
    pal.setColor(QPalette.Window, bg)
    pal.setColor(QPalette.WindowText, text)
    pal.setColor(QPalette.Base, base)
    pal.setColor(QPalette.AlternateBase, bg)
    pal.setColor(QPalette.Text, text)
    pal.setColor(QPalette.Button, QColor(45, 47, 55))
    pal.setColor(QPalette.ButtonText, text)
    pal.setColor(QPalette.ToolTipBase, base)
    pal.setColor(QPalette.ToolTipText, text)
    pal.setColor(QPalette.Highlight, accent)
    pal.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    pal.setColor(QPalette.PlaceholderText, QColor(130, 134, 145))
    pal.setColor(QPalette.Disabled, QPalette.Text, QColor(110, 113, 122))
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(110, 113, 122))
    app.setPalette(pal)
    app.setStyleSheet(
        "QGroupBox{border:1px solid #3a3d47;border-radius:6px;margin-top:10px;padding-top:8px}"
        "QGroupBox::title{subcontrol-origin:margin;left:8px;padding:0 4px}"
        "QPushButton{padding:5px 12px;border-radius:4px}"
        "QPushButton#primary{background:#e85d04;color:white;font-weight:bold;padding:7px 18px}"
        "QPushButton#primary:disabled{background:#5a3a22;color:#999}"
        "QProgressBar{border:1px solid #3a3d47;border-radius:4px;text-align:center}"
        "QProgressBar::chunk{background:#e85d04}"
    )
