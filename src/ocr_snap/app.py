import sys

from dotenv import load_dotenv
from PyQt6.QtWidgets import QApplication

from ocr_snap.config import load_app_settings
from ocr_snap.main_window import MainWindow


def main():
    load_dotenv()
    app = QApplication(sys.argv)
    app.setApplicationName("OCR Snap")
    settings = load_app_settings()
    window = MainWindow(settings)
    window.show()
    sys.exit(app.exec())
