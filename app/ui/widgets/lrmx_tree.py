from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTreeWidget, QTreeWidgetItem, QLabel,
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QIcon, QColor, QFont, QDragEnterEvent, QDragLeaveEvent, QDropEvent

_ASSETS = Path(__file__).parent.parent / 'assets'

_ROLE_PATH = Qt.ItemDataRole.UserRole       # full file path (lrmx nodes)
_ROLE_DIR  = Qt.ItemDataRole.UserRole + 1  # full dir path (folder nodes)

_ACCENT = QColor('#D85A30')


class _Tree(QTreeWidget):
    """空状态绘制拖放提示文字。"""
    _HINT = '拖放 .lrmx 文件\n或文件夹至此'

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.topLevelItemCount() == 0:
            from PySide6.QtGui import QPainter
            painter = QPainter(self.viewport())
            painter.setPen(QColor('#BBBBB4'))
            f = self.font()
            f.setPointSize(10)
            painter.setFont(f)
            painter.drawText(
                self.viewport().rect().adjusted(16, 0, -16, 0),
                Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                self._HINT,
            )
            painter.end()


class LrmxTreePanel(QWidget):
    """左侧 lrmx 文件树面板，支持拖放文件夹/文件。"""

    file_selected = Signal(str)  # 点击 lrmx 节点时发出绝对路径

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('lrmxTreePanel')
        self.setAcceptDrops(True)
        self._added: set[str] = set()   # canonical paths already in tree
        self._file_count = 0
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ── 头部：标题 + 计数徽标 + 清空 ────────────────────────────────
        header = QWidget()
        header.setObjectName('lrmxTreeHeader')
        header.setFixedHeight(38)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(12, 0, 8, 0)
        hl.setSpacing(6)

        title = QLabel('文件列表')
        title.setObjectName('lrmxTreeTitle')
        hl.addWidget(title)

        self._count = QLabel('0')
        self._count.setObjectName('lrmxTreeCount')
        self._count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._count.setVisible(False)
        hl.addWidget(self._count)

        hl.addStretch()

        self._clear_btn = QPushButton('清空')
        self._clear_btn.setObjectName('lrmxTreeClear')
        self._clear_btn.setFixedHeight(24)
        self._clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_btn.clicked.connect(self.clear)
        hl.addWidget(self._clear_btn)
        lay.addWidget(header)

        # ── 文件树 ──────────────────────────────────────────────────────
        self._tree = _Tree()
        self._tree.setObjectName('lrmxFileTree')
        self._tree.setHeaderHidden(True)
        self._tree.setIconSize(QSize(16, 16))
        self._tree.setIndentation(14)
        self._tree.setAnimated(True)
        self._tree.setFrameShape(QTreeWidget.Shape.NoFrame)
        self._tree.setVerticalScrollMode(QTreeWidget.ScrollMode.ScrollPerPixel)
        self._tree.itemClicked.connect(self._on_clicked)
        lay.addWidget(self._tree, 1)

    # ── public API ──────────────────────────────────────────────────────────

    def clear(self):
        self._tree.clear()
        self._added.clear()
        self._file_count = 0
        self._update_count()

    def add_path(self, path: str) -> None:
        p = Path(path)
        canonical = str(p.resolve()).lower()
        if canonical in self._added:
            return
        self._added.add(canonical)
        if p.is_dir():
            self._add_folder(p)
        elif p.suffix.lower() == '.lrmx':
            self._tree.addTopLevelItem(self._make_file_item(p))
            self._file_count += 1
        self._update_count()

    def set_modified(self, path: str, modified: bool) -> None:
        self._visit(self._tree.invisibleRootItem(), path, modified)

    # ── internals ───────────────────────────────────────────────────────────

    def _update_count(self):
        self._count.setText(str(self._file_count))
        self._count.setVisible(self._file_count > 0)

    def _add_folder(self, folder: Path) -> None:
        item = QTreeWidgetItem([folder.name])
        item.setData(0, _ROLE_DIR, str(folder))
        item.setIcon(0, QIcon(str(_ASSETS / 'folder.svg')))
        added = self._fill_dir(item, folder)
        if added > 0:
            self._tree.addTopLevelItem(item)
            item.setExpanded(True)
            self._file_count += added

    def _fill_dir(self, parent: QTreeWidgetItem, folder: Path) -> int:
        try:
            entries = sorted(folder.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
        except PermissionError:
            return 0
        count = 0
        for entry in entries:
            if entry.is_dir():
                child = QTreeWidgetItem([entry.name])
                child.setData(0, _ROLE_DIR, str(entry))
                child.setIcon(0, QIcon(str(_ASSETS / 'folder.svg')))
                sub = self._fill_dir(child, entry)
                if sub > 0:
                    parent.addChild(child)
                    child.setExpanded(True)
                    count += sub
            elif entry.suffix.lower() == '.lrmx':
                parent.addChild(self._make_file_item(entry))
                count += 1
        return count

    def _make_file_item(self, path: Path) -> QTreeWidgetItem:
        item = QTreeWidgetItem([path.stem])
        item.setData(0, _ROLE_PATH, str(path))
        item.setIcon(0, QIcon(str(_ASSETS / 'rmb.svg')))
        item.setToolTip(0, str(path))
        return item

    def _on_clicked(self, item: QTreeWidgetItem, _col: int) -> None:
        path = item.data(0, _ROLE_PATH)
        if path:
            self.file_selected.emit(path)

    def _visit(self, parent: QTreeWidgetItem, path: str, modified: bool) -> bool:
        for i in range(parent.childCount()):
            item = parent.child(i)
            if item.data(0, _ROLE_PATH) == path:
                stem = Path(path).stem
                item.setText(0, f'• {stem}' if modified else stem)
                font = item.font(0)
                font.setWeight(QFont.Weight.DemiBold if modified else QFont.Weight.Normal)
                item.setFont(0, font)
                item.setForeground(0, _ACCENT if modified else QColor('#555550'))
                return True
            if self._visit(item, path, modified):
                return True
        return False

    # ── drag & drop ─────────────────────────────────────────────────────────

    def _set_drag(self, active: bool):
        self.setProperty('dragActive', active)
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, ev: QDragEnterEvent) -> None:
        if ev.mimeData().hasUrls():
            self._set_drag(True)
            ev.acceptProposedAction()

    def dragLeaveEvent(self, ev: QDragLeaveEvent) -> None:
        self._set_drag(False)
        super().dragLeaveEvent(ev)

    def dropEvent(self, ev: QDropEvent) -> None:
        self._set_drag(False)
        for url in ev.mimeData().urls():
            self.add_path(url.toLocalFile())
