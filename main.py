"""
SigmaScope – Entry Point
Launch the audio visualizer application.
"""

import sys
import os

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPalette, QColor
from PySide6.QtCore import Qt

from audio import AudioEngine
from ui import MainWindow, STYLESHEET


def _dark_palette(app: QApplication):
    """System-wide dark palette (fallback for unstyled widgets / dialogs)."""
    app.setStyle("Fusion")
    p = QPalette()

    bg      = QColor("#07070d")
    panel   = QColor("#0c0c18")
    text    = QColor("#c8c8e0")
    accent  = QColor("#00d4ff")
    dim     = QColor("#606080")

    p.setColor(QPalette.Window,          bg)
    p.setColor(QPalette.WindowText,      text)
    p.setColor(QPalette.Base,            panel)
    p.setColor(QPalette.AlternateBase,   bg)
    p.setColor(QPalette.ToolTipBase,     panel)
    p.setColor(QPalette.ToolTipText,     text)
    p.setColor(QPalette.Text,            text)
    p.setColor(QPalette.Button,          panel)
    p.setColor(QPalette.ButtonText,      text)
    p.setColor(QPalette.BrightText,      accent)
    p.setColor(QPalette.Link,            accent)
    p.setColor(QPalette.Highlight,       accent)
    p.setColor(QPalette.HighlightedText, bg)
    p.setColor(QPalette.PlaceholderText, dim)

    app.setPalette(p)


def main():
    # High-DPI scaling (crisp on 4K/Retina)
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

    app = QApplication(sys.argv)
    _dark_palette(app)
    app.setStyleSheet(STYLESHEET)

    engine = AudioEngine()
    window = MainWindow(engine)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
