from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt


class _LoadingOverlay(QWidget):
    """Semi-transparent overlay shown while result layout is settling."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet('background: rgba(248, 245, 240, 220);')

        v = QVBoxLayout(self)
        v.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._lbl = QLabel('核验中，请稍候…')
        self._lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl.setStyleSheet('color: #555555; font-size: 14px; background: transparent;')
        v.addWidget(self._lbl)

        self.hide()

    def set_text(self, text: str):
        self._lbl.setText(text)
