import os
import sys

from dotenv import load_dotenv
from PyQt6.QtWidgets import QApplication

from ocr_snap.main_window import MainWindow


def main():
    load_dotenv()
    app = QApplication(sys.argv)
    app.setApplicationName("OCR Snap")
    window = MainWindow(translate_api_key=os.environ.get("DEEPL_API_KEY", ""))
    window.show()
    sys.exit(app.exec())
