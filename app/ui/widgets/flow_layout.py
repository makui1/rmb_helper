from PySide6.QtWidgets import QWidget, QLayout, QHBoxLayout, QLabel, QSizePolicy
from PySide6.QtCore import Qt, Signal, QSize, QRect, QPoint


class _FlowLayout(QLayout):
    """Left-to-right wrapping flow layout; hidden items are skipped."""

    def __init__(self, parent=None, h_spacing: int = 6, v_spacing: int = 6):
        super().__init__(parent)
        self._h = h_spacing
        self._v = v_spacing
        self._items: list = []

    def addItem(self, item):
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, w: int) -> int:
        return self._arrange(QRect(0, 0, w, 0), dry=True)

    def setGeometry(self, rect: QRect):
        super().setGeometry(rect)
        self._arrange(rect, dry=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        m = self.contentsMargins()
        # Returning only the margin size lets QScrollArea(setWidgetResizable=True)
        # set the container width to the viewport width instead of the widest tag,
        # which would break wrapping by putting all items on one row.
        return QSize(m.left() + m.right(), m.top() + m.bottom())

    def _arrange(self, rect: QRect, dry: bool) -> int:
        m = self.contentsMargins()
        r = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x, y, row_h = r.x(), r.y(), 0
        for item in self._items:
            w = item.widget()
            if w is None or not w.isVisible():
                continue
            hint = item.sizeHint()
            nx = x + hint.width() + self._h
            if nx - self._h > r.right() and row_h > 0:
                x = r.x()
                y += row_h + self._v
                nx = x + hint.width() + self._h
                row_h = 0
            if not dry:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = nx
            row_h = max(row_h, hint.height())
        return y + row_h - rect.y() + m.bottom()


class _MatchTag(QWidget):
    clicked_tag = Signal(str)

    def __init__(self, col: str, parent=None):
        super().__init__(parent)
        self._col = col
        self._selected = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._label = QLabel(col)
        self._label.setObjectName('matchTag')
        layout.addWidget(self._label)

    def set_selected(self, v: bool):
        self._selected = v
        self._label.setProperty('selected', v)
        self._label.style().unpolish(self._label)
        self._label.style().polish(self._label)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked_tag.emit(self._col)
        super().mousePressEvent(event)
