from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListWidget, QListWidgetItem,
    QFileDialog, QSizePolicy, QMenu, QDialog, QProgressBar,
)
from PySide6.QtCore import Qt, QThread, Signal, QSize, QEvent, QTimer
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QIcon, QPainter, QColor, QPen

_ASSETS = Path(__file__).parent.parent / 'assets'


class _FolderScanWorker(QThread):
    done = Signal(list)

    def __init__(self, folder: str, parent=None):
        super().__init__(parent)
        self._folder = folder

    def run(self):
        paths = sorted(str(p) for p in Path(self._folder).rglob('*.lrmx'))
        self.done.emit(paths)


class _LoadingDialog(QDialog):
    def __init__(self, parent, message: str = '正在处理，请稍候…'):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setModal(True)
        self.setObjectName('loadingDialog')
        self.setFixedSize(260, 90)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 20, 28, 20)
        layout.setSpacing(12)

        lbl = QLabel(message)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setObjectName('loadingLabel')
        layout.addWidget(lbl)

        bar = QProgressBar()
        bar.setRange(0, 0)
        bar.setFixedHeight(4)
        bar.setTextVisible(False)
        bar.setObjectName('loadingBar')
        layout.addWidget(bar)

    def showEvent(self, event):
        super().showEvent(event)
        if self.parent():
            pg = self.parent().frameGeometry()
            self.move(
                pg.center().x() - self.width() // 2,
                pg.center().y() - self.height() // 2,
            )


class _FileList(QListWidget):
    empty_clicked = Signal()
    _HINT = '拖放 .lrmx 文件或文件夹至此，或点击「添加」'

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.viewport().installEventFilter(self)

    def eventFilter(self, obj, event):
        if (obj is self.viewport()
                and event.type() == QEvent.Type.MouseButtonPress
                and event.button() == Qt.MouseButton.LeftButton
                and self.count() == 0):
            self.empty_clicked.emit()
        return super().eventFilter(obj, event)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.count() == 0:
            painter = QPainter(self.viewport())
            painter.setPen(QColor('#BBBBBB'))
            font = self.font()
            font.setPointSize(11)
            painter.setFont(font)
            painter.drawText(
                self.viewport().rect(),
                Qt.AlignmentFlag.AlignCenter,
                self._HINT,
            )
            painter.end()


class _FileRow(QWidget):
    removed = Signal(QListWidgetItem)
    _SEP_NORMAL = QColor('#E8E6E0')
    _SEP_HOVER  = QColor('#1A1A1A')

    def __init__(self, path: str, item: QListWidgetItem, parent=None):
        super().__init__(parent)
        self._item = item
        self._hovered = False
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 8, 6)
        layout.setSpacing(8)

        icon = QLabel()
        icon.setPixmap(QIcon(str(_ASSETS / 'rmb.svg')).pixmap(QSize(16, 16)))
        icon.setFixedWidth(22)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon)

        name = QLabel(Path(path).name)
        name.setObjectName('fileItemName')
        name.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(name, 1)

        btn = QPushButton()
        btn.setObjectName('fileItemRemove')
        btn.setFixedSize(20, 20)
        btn.clicked.connect(lambda: self.removed.emit(self._item))
        layout.addWidget(btn)

    def event(self, e: QEvent) -> bool:
        if e.type() == QEvent.Type.HoverEnter:
            self._hovered = True
            self.update()
        elif e.type() == QEvent.Type.HoverLeave:
            self._hovered = False
            self.update()
        return super().event(e)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        color = self._SEP_HOVER if self._hovered else self._SEP_NORMAL
        painter.setPen(QPen(color, 1))
        y = self.height() - 1
        painter.drawLine(10, y, self.width() - 10, y)
        painter.end()


class LrmxFilePanel(QWidget):
    """lrmx 文件面板：添加/删除/清空按钮 + 文件列表 + 拖放支持。

    放入 QSplitter 使用，QSplitter 的拖动手柄即文件列表底边。
    files_changed(list[str]) 在列表变化时触发。
    """
    files_changed = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scan_worker = None
        self.setAcceptDrops(True)
        self.setMinimumHeight(60)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(6)
        header.addStretch()

        self._add_btn = QPushButton('+ 添加')
        self._add_btn.setFixedHeight(26)
        self._add_menu = QMenu(self._add_btn)
        self._add_menu.addAction('选择文件…', self._pick_files)
        self._add_menu.addAction('选择文件夹…', self._pick_folder)
        self._add_btn.setMenu(self._add_menu)

        del_btn = QPushButton('删除选中')
        del_btn.setFixedHeight(26)
        del_btn.clicked.connect(self._remove_selected)

        clear_btn = QPushButton('清空')
        clear_btn.setFixedHeight(26)
        clear_btn.clicked.connect(self._clear_files)

        header.addWidget(self._add_btn)
        header.addWidget(del_btn)
        header.addWidget(clear_btn)
        layout.addLayout(header)

        self._list = _FileList()
        self._list.setObjectName('fileList')
        self._list.empty_clicked.connect(
            lambda: self._add_menu.exec(
                self._add_btn.mapToGlobal(self._add_btn.rect().bottomLeft())
            )
        )
        layout.addWidget(self._list)

    # ── public API ─────────────────────────────────────────────────────────────

    def files(self) -> list[str]:
        return [
            self._list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self._list.count())
        ]

    def count(self) -> int:
        return self._list.count()

    def add_file(self, path: str):
        for i in range(self._list.count()):
            if self._list.item(i).data(Qt.ItemDataRole.UserRole) == path:
                return
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, path)
        item.setSizeHint(QSize(0, 34))
        self._list.addItem(item)
        row = _FileRow(path, item)
        row.removed.connect(self._on_row_removed)
        self._list.setItemWidget(item, row)
        self.files_changed.emit(self.files())

    # ── internals ──────────────────────────────────────────────────────────────

    def _on_row_removed(self, item: QListWidgetItem):
        self._list.takeItem(self._list.row(item))
        self.files_changed.emit(self.files())

    def _remove_selected(self):
        for item in self._list.selectedItems():
            self._list.takeItem(self._list.row(item))
        self.files_changed.emit(self.files())

    def _clear_files(self):
        self._list.clear()
        self.files_changed.emit(self.files())

    def _pick_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, '选择 lrmx 文件', '', '任免审批表 (*.lrmx)'
        )
        if paths:
            self._batch_add(paths)

    def _pick_folder(self):
        folder = QFileDialog.getExistingDirectory(self, '选择包含 lrmx 文件的文件夹')
        if folder:
            self._scan_and_add(folder)

    def _scan_and_add(self, folder: str):
        dlg = _LoadingDialog(self.window(), '正在扫描文件夹…')
        self._scan_worker = _FolderScanWorker(folder)

        def on_done(paths):
            if paths:
                self._batch_add(paths, on_finish=dlg.accept)
            else:
                dlg.accept()

        self._scan_worker.done.connect(on_done)
        self._scan_worker.start()
        dlg.exec()

    def _batch_add(self, paths: list[str], on_finish=None):
        _BATCH = 20
        if len(paths) <= _BATCH and on_finish is None:
            for p in paths:
                self.add_file(p)
            return

        dlg = None
        if on_finish is None:
            dlg = _LoadingDialog(self.window(), f'正在添加 {len(paths)} 个文件…')
        remaining = list(paths)

        def add_batch():
            nonlocal remaining
            batch, remaining = remaining[:_BATCH], remaining[_BATCH:]
            for p in batch:
                self.add_file(p)
            if remaining:
                QTimer.singleShot(0, add_batch)
            else:
                if on_finish:
                    on_finish()
                elif dlg:
                    dlg.accept()

        QTimer.singleShot(0, add_batch)
        if dlg:
            dlg.exec()

    # ── drag & drop ────────────────────────────────────────────────────────────

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if Path(path).is_dir():
                self._scan_and_add(path)
            elif path.lower().endswith('.lrmx'):
                self.add_file(path)
