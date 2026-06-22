"""打印预览对话框：用 QtPdf.QPdfView 显示临时 PDF，用户确认后打印。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtPrintSupport import QPrinter, QPrintDialog
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
)


class PrintPreviewDialog(QDialog):
    """显示 pdf_path 的预览，用户点「打印…」后弹系统打印对话框。
    关闭（无论是否打印）后删除 pdf_path。
    """

    def __init__(self, pdf_path: Path, parent=None):
        super().__init__(parent)
        self._pdf_path = pdf_path
        self.setWindowTitle('打印预览')
        self.resize(800, 1000)
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 8)
        lay.setSpacing(0)

        self._doc = QPdfDocument(self)
        self._doc.load(str(self._pdf_path))

        self._view = QPdfView(self)
        self._view.setDocument(self._doc)
        self._view.setPageMode(QPdfView.PageMode.MultiPage)
        self._view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        lay.addWidget(self._view, 1)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(12, 6, 12, 0)
        btn_row.setSpacing(8)
        hint = QLabel('确认无误后点击「打印…」选择打印机')
        hint.setStyleSheet('color: #888; font-size: 11px;')
        btn_row.addWidget(hint, 1)

        cancel_btn = QPushButton('取消')
        cancel_btn.setFixedHeight(28)
        cancel_btn.clicked.connect(self.reject)

        print_btn = QPushButton('打印…')
        print_btn.setObjectName('primary')
        print_btn.setFixedHeight(28)
        print_btn.clicked.connect(self._do_print)

        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(print_btn)
        lay.addLayout(btn_row)

    def _do_print(self):
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dlg = QPrintDialog(printer, self)
        if dlg.exec() != QPrintDialog.DialogCode.Accepted:
            return

        from PySide6.QtGui import QPainter
        painter = QPainter(printer)
        page_count = self._doc.pageCount()
        for i in range(page_count):
            if i > 0:
                printer.newPage()
            rect = painter.viewport()
            img = self._doc.render(i, rect.size())
            painter.drawImage(rect, img)
        painter.end()
        self.accept()

    def closeEvent(self, ev):
        self._doc.close()
        try:
            self._pdf_path.unlink(missing_ok=True)
        except OSError:
            pass
        super().closeEvent(ev)
