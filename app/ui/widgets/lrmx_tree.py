from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTreeWidget, QTreeWidgetItem, QLabel,
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QIcon, QDragEnterEvent, QDropEvent

_ASSETS = Path(__file__).parent.parent / 'assets'

_ROLE_PATH = Qt.ItemDataRole.UserRole       # full file path (lrmx nodes)
_ROLE_DIR  = Qt.ItemDataRole.UserRole + 1  # full dir path (folder nodes)


class LrmxTreePanel(QWidget):
    """左侧 lrmx 文件树面板，支持拖放文件夹/文件。"""

    file_selected = Signal(str)  # 点击 lrmx 节点时发出绝对路径

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._added: set[str] = set()  # canonical paths already in tree
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        header = QWidget()
        header.setObjectName('filePanelHeader')
        hl = QHBoxLayout(header)
        hl.setContentsMargins(10, 6, 10, 6)
        lbl = QLabel('文件列表')
        lbl.setStyleSheet('font-size: 12px; color: #888;')
        clear_btn = QPushButton('清空')
        clear_btn.setObjectName('smallBtn')
        clear_btn.setFixedHeight(22)
        clear_btn.clicked.connect(self.clear)
        hl.addWidget(lbl)
        hl.addStretch()
        hl.addWidget(clear_btn)
        lay.addWidget(header)

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setObjectName('lrmxFileTree')
        self._tree.setIconSize(QSize(16, 16))
        self._tree.itemClicked.connect(self._on_clicked)
        lay.addWidget(self._tree, 1)

        hint = QLabel('拖放 .lrmx 文件\n或文件夹至此')
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet('color: #bbb; font-size: 11px; padding: 8px;')
        lay.addWidget(hint)

    def clear(self):
        self._tree.clear()
        self._added.clear()

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

    def _add_folder(self, folder: Path) -> None:
        item = QTreeWidgetItem([folder.name])
        item.setData(0, _ROLE_DIR, str(folder))
        item.setIcon(0, QIcon(str(_ASSETS / 'folder.svg')))
        self._fill_dir(item, folder)
        if item.childCount() > 0:
            self._tree.addTopLevelItem(item)
            item.setExpanded(True)

    def _fill_dir(self, parent: QTreeWidgetItem, folder: Path) -> None:
        try:
            entries = sorted(folder.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
        except PermissionError:
            return
        for entry in entries:
            if entry.is_dir():
                child = QTreeWidgetItem([entry.name])
                child.setData(0, _ROLE_DIR, str(entry))
                child.setIcon(0, QIcon(str(_ASSETS / 'folder.svg')))
                self._fill_dir(child, entry)
                if child.childCount() > 0:
                    parent.addChild(child)
                    child.setExpanded(True)
            elif entry.suffix.lower() == '.lrmx':
                parent.addChild(self._make_file_item(entry))

    def _make_file_item(self, path: Path) -> QTreeWidgetItem:
        item = QTreeWidgetItem([path.stem])
        item.setData(0, _ROLE_PATH, str(path))
        item.setIcon(0, QIcon(str(_ASSETS / 'rmb.svg')))
        return item

    def _on_clicked(self, item: QTreeWidgetItem, _col: int) -> None:
        path = item.data(0, _ROLE_PATH)
        if path:
            self.file_selected.emit(path)

    def set_modified(self, path: str, modified: bool) -> None:
        self._visit(self._tree.invisibleRootItem(), path, modified)

    def _visit(self, parent: QTreeWidgetItem, path: str, modified: bool) -> bool:
        for i in range(parent.childCount()):
            item = parent.child(i)
            if item.data(0, _ROLE_PATH) == path:
                stem = Path(path).stem
                item.setText(0, f'● {stem}' if modified else stem)
                return True
            if self._visit(item, path, modified):
                return True
        return False

    def dragEnterEvent(self, ev: QDragEnterEvent) -> None:
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()

    def dropEvent(self, ev: QDropEvent) -> None:
        for url in ev.mimeData().urls():
            self.add_path(url.toLocalFile())
