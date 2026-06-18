from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListWidget, QListWidgetItem,
    QFileDialog, QMenu, QDialog, QProgressBar,
    QStyledItemDelegate, QStyle,
)
from PySide6.QtCore import Qt, QThread, Signal, QSize, QEvent, QTimer, QModelIndex, QRect
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QIcon, QPainter, QColor, QPen

_ASSETS = Path(__file__).parent.parent / 'assets'

_ACCENT       = QColor('#D85A30')
_ACCENT_LIGHT = QColor(216, 90, 48, 26)   # rgba(216,90,48,0.10)


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


class _RowDelegate(QStyledItemDelegate):
    """Paint-only delegate — no per-item QWidget created."""

    remove_requested = Signal(str)

    _SEP_NORMAL = QColor('#E8E6E0')
    _SEP_HOVER  = QColor('#1A1A1A')
    _DEL_ZONE_W = 30      # px — click zone for the × icon on the right

    def __init__(self, parent=None):
        super().__init__(parent)
        self._icon_file   = QIcon(str(_ASSETS / 'rmb.svg'))
        self._icon_rm     = QIcon(str(_ASSETS / 'remove.svg'))
        self._icon_rm_hot = QIcon(str(_ASSETS / 'remove-hover.svg'))
        self._hovered_idx  = QModelIndex()
        self._in_del_zone  = False

    def sizeHint(self, option, index):
        return QSize(0, 34)

    def paint(self, painter: QPainter, option, index: QModelIndex):
        painter.save()

        rect      = option.rect
        is_hover  = (index == self._hovered_idx)
        is_sel    = bool(option.state & QStyle.StateFlag.State_Selected)
        name      = index.data(Qt.ItemDataRole.DisplayRole) or ''

        # ── selection / hover background ──────────────────────────────────────
        if is_sel:
            painter.fillRect(rect, _ACCENT_LIGHT)

        # ── file icon ─────────────────────────────────────────────────────────
        icon_rect = QRect(rect.x() + 10, rect.y() + (rect.height() - 16) // 2, 16, 16)
        self._icon_file.paint(painter, icon_rect)

        # ── filename text ─────────────────────────────────────────────────────
        del_w    = self._DEL_ZONE_W if is_hover else 0
        text_rect = rect.adjusted(36, 0, -(del_w + 8), 0)
        elided   = painter.fontMetrics().elidedText(
            name, Qt.TextElideMode.ElideRight, text_rect.width()
        )
        painter.setPen(_ACCENT if is_sel else QColor('#333330'))
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextSingleLine,
            elided,
        )

        # ── bottom separator ──────────────────────────────────────────────────
        painter.setPen(QPen(self._SEP_HOVER if is_hover else self._SEP_NORMAL, 1))
        y = rect.bottom()
        painter.drawLine(rect.x() + 10, y, rect.right() - 10, y)

        # ── × icon (hovered row only) ─────────────────────────────────────────
        if is_hover:
            rm_icon = self._icon_rm_hot if self._in_del_zone else self._icon_rm
            rm_x    = rect.right() - self._DEL_ZONE_W + (self._DEL_ZONE_W - 16) // 2
            rm_rect = QRect(rm_x, rect.y() + (rect.height() - 16) // 2, 16, 16)
            rm_icon.paint(painter, rm_rect)

        painter.restore()

    def editorEvent(self, event, model, option, index):
        if (event.type() == QEvent.Type.MouseButtonRelease
                and event.button() == Qt.MouseButton.LeftButton
                and event.position().x() >= option.rect.right() - self._DEL_ZONE_W):
            self.remove_requested.emit(index.data(Qt.ItemDataRole.UserRole))
            return True
        return False


class _FileList(QListWidget):
    empty_clicked = Signal()
    _HINT = '拖放 .lrmx 文件或文件夹至此，或点击「添加」'

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.viewport().installEventFilter(self)
        self.viewport().setMouseTracking(True)
        self._delegate: _RowDelegate | None = None

    def set_delegate(self, delegate: _RowDelegate):
        self._delegate = delegate

    def eventFilter(self, obj, event):
        if obj is self.viewport() and self._delegate is not None:
            t = event.type()

            if t == QEvent.Type.MouseMove:
                index   = self.indexAt(event.pos())
                in_del  = False
                if index.isValid() and index == self._delegate._hovered_idx:
                    in_del = event.pos().x() >= self.visualRect(index).right() - _RowDelegate._DEL_ZONE_W

                changed = (index != self._delegate._hovered_idx
                           or in_del != self._delegate._in_del_zone)
                self._delegate._hovered_idx  = index
                self._delegate._in_del_zone  = in_del
                if changed:
                    self.viewport().update()
                self.viewport().setCursor(
                    Qt.CursorShape.PointingHandCursor if in_del else Qt.CursorShape.ArrowCursor
                )

            elif t == QEvent.Type.Leave:
                self._delegate._hovered_idx = QModelIndex()
                self._delegate._in_del_zone = False
                self.viewport().unsetCursor()
                self.viewport().update()

            elif (t == QEvent.Type.MouseButtonPress
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
                self.viewport().rect().adjusted(16, 0, -16, 0),
                Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                self._HINT,
            )
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
        self._path_set: set[str] = set()
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

        self._add_btn = QPushButton('添加')
        self._add_btn.setIcon(QIcon(str(_ASSETS / 'add-btn.svg')))
        self._add_btn.setFixedHeight(26)
        self._add_menu = QMenu(self._add_btn)
        self._add_menu.addAction('选择文件…', self._pick_files)
        self._add_menu.addAction('选择文件夹…', self._pick_folder)
        self._add_btn.setMenu(self._add_menu)

        self._del_btn = QPushButton('删除选中')
        self._del_btn.setIcon(QIcon(str(_ASSETS / 'delete-btn.svg')))
        self._del_btn.setFixedHeight(26)
        self._del_btn.setToolTip('删除选中的文件')
        self._del_btn.clicked.connect(self._remove_selected)

        self._clear_btn = QPushButton('清空')
        self._clear_btn.setIcon(QIcon(str(_ASSETS / 'clear-btn.svg')))
        self._clear_btn.setFixedHeight(26)
        self._clear_btn.setToolTip('清空所有文件')
        self._clear_btn.clicked.connect(self._clear_files)

        header.addWidget(self._add_btn)
        header.addWidget(self._del_btn)
        header.addWidget(self._clear_btn)
        layout.addLayout(header)

        self._delegate = _RowDelegate()
        self._delegate.remove_requested.connect(self._on_path_removed)

        self._list = _FileList()
        self._list.setObjectName('fileList')
        self._list.set_delegate(self._delegate)
        self._list.setItemDelegate(self._delegate)
        self._list.empty_clicked.connect(
            lambda: self._add_menu.exec(
                self._add_btn.mapToGlobal(self._add_btn.rect().bottomLeft())
            )
        )
        layout.addWidget(self._list)

    _BTN_TEXT_THRESHOLD = 230  # px — below this width, hide button labels

    def resizeEvent(self, event):
        super().resizeEvent(event)
        narrow = self.width() < self._BTN_TEXT_THRESHOLD
        for btn, label, icon in (
            (self._add_btn,  '添加',   str(_ASSETS / 'add-btn.svg')),
            (self._del_btn,  '删除选中', str(_ASSETS / 'delete-btn.svg')),
            (self._clear_btn, '清空',  str(_ASSETS / 'clear-btn.svg')),
        ):
            btn.setText('' if narrow else label)
            btn.setIcon(QIcon(icon) if narrow else QIcon())

    # ── public API ─────────────────────────────────────────────────────────────

    def files(self) -> list[str]:
        return [
            self._list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self._list.count())
        ]

    def count(self) -> int:
        return self._list.count()

    def add_file(self, path: str, _emit: bool = True):
        if path in self._path_set:
            return
        self._path_set.add(path)
        item = QListWidgetItem(Path(path).name)
        item.setData(Qt.ItemDataRole.UserRole, path)
        item.setSizeHint(QSize(0, 34))
        self._list.addItem(item)
        if _emit:
            self.files_changed.emit(self.files())

    # ── internals ──────────────────────────────────────────────────────────────

    def _on_path_removed(self, path: str):
        self._path_set.discard(path)
        for i in range(self._list.count()):
            if self._list.item(i).data(Qt.ItemDataRole.UserRole) == path:
                self._list.takeItem(i)
                break
        self.files_changed.emit(self.files())

    def _remove_selected(self):
        for item in self._list.selectedItems():
            self._path_set.discard(item.data(Qt.ItemDataRole.UserRole))
            self._list.takeItem(self._list.row(item))
        self.files_changed.emit(self.files())

    def _clear_files(self):
        self._path_set.clear()
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
                self.add_file(p, _emit=False)
            self.files_changed.emit(self.files())
            return

        dlg = None
        if on_finish is None:
            dlg = _LoadingDialog(self.window(), f'正在添加 {len(paths)} 个文件…')
        remaining = list(paths)

        def add_batch():
            nonlocal remaining
            batch, remaining = remaining[:_BATCH], remaining[_BATCH:]
            for p in batch:
                self.add_file(p, _emit=False)
            if remaining:
                QTimer.singleShot(0, add_batch)
            else:
                self.files_changed.emit(self.files())
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
