from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListWidget, QListWidgetItem,
    QCheckBox, QLineEdit, QComboBox, QTextEdit,
    QFileDialog, QSizePolicy, QMenu, QDialog, QProgressBar,
)
from PySide6.QtCore import Qt, QThread, Signal, QSize, QEvent, QTimer
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QIcon, QPixmap, QPainter, QFont, QColor, QPen

from app.core.compat_processor import (
    MALE_LIMIT_OPTIONS, FEMALE_LIMIT_OPTIONS,
    process_file, is_new_version,
)
from app.core.lrmx import LrmxFile

_ASSETS = Path(__file__).parent.parent / 'assets'


# ── shared file-list widgets (same pattern as ConvertTab) ─────────────────────

class _FolderScanWorker(QThread):
    done = Signal(list)

    def __init__(self, folder: str, parent=None):
        super().__init__(parent)
        self._folder = folder

    def run(self):
        paths = sorted(str(p) for p in Path(self._folder).rglob('*.lrmx'))
        self.done.emit(paths)


class _LoadingDialog(QDialog):
    def __init__(self, parent, message: str = '正在扫描，请稍候…'):
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
    _HINT = '拖放 .lrmx 文件至此，或点击「添加」'

    def __init__(self, parent=None):
        super().__init__(parent)
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

        icon = QLabel('📄')
        icon.setFixedWidth(18)
        layout.addWidget(icon)

        name = QLabel(Path(path).name)
        name.setObjectName('fileItemName')
        name.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(name, 1)

        btn = QPushButton('×')
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


# ── background worker ─────────────────────────────────────────────────────────

class _CompatWorker(QThread):
    log = Signal(str)
    finished = Signal(int, int)  # processed, total

    def __init__(self, files, male_limit, female_limit, output_dir=None, sibling=False, update_daolignianue=True):
        super().__init__()
        self.files = files
        self.male_limit = male_limit
        self.female_limit = female_limit
        self.output_dir = Path(output_dir) if output_dir else None
        self.sibling = sibling
        self.update_daolignianue = update_daolignianue

    def run(self):
        total = len(self.files)
        processed = 0
        for f in self.files:
            path = Path(f)
            if self.sibling or self.output_dir is None:
                out_path = None           # overwrite in-place
            else:
                self.output_dir.mkdir(parents=True, exist_ok=True)
                out_path = self.output_dir / path.name
            try:
                status, msg = process_file(path, self.male_limit, self.female_limit, out_path, self.update_daolignianue)
                if status == 'ok':
                    self.log.emit(f'✓ {msg}')
                    processed += 1
                elif status == 'skip':
                    self.log.emit(f'△ {msg}')
                    processed += 1
                else:
                    self.log.emit(f'✗ {msg}')
            except Exception as e:
                self.log.emit(f'✗ {path.name}：{e}')
        self.finished.emit(processed, total)


# ── tab widget ────────────────────────────────────────────────────────────────

class CompatTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._scan_worker = None
        self._log_entries: list[tuple[str, str]] = []
        self._active_filter = 'all'
        self._build_ui()
        self.setAcceptDrops(True)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        title = QLabel('版本兼容')
        title.setObjectName('sectionTitle')
        layout.addWidget(title)

        sub = QLabel('为旧版任免表补充「改革前任职年龄界限」和「到龄年月」字段')
        sub.setStyleSheet('color: #888880; font-size: 12px;')
        layout.addWidget(sub)

        # ── 文件列表 ────────────────────────────────────────────────────────────
        list_header = QHBoxLayout()
        list_header.setContentsMargins(0, 0, 0, 0)
        list_header.setSpacing(6)
        list_header.addStretch()

        add_btn = QPushButton('+ 添加')
        add_btn.setFixedHeight(26)
        add_menu = QMenu(add_btn)
        add_menu.addAction('选择文件…', self._pick_files)
        add_menu.addAction('选择文件夹…', self._pick_folder)
        add_btn.setMenu(add_menu)

        del_btn = QPushButton('删除选中')
        del_btn.setFixedHeight(26)
        del_btn.clicked.connect(self._remove_selected)

        clear_btn = QPushButton('清空')
        clear_btn.setFixedHeight(26)
        clear_btn.clicked.connect(self._clear_files)

        list_header.addWidget(add_btn)
        list_header.addWidget(del_btn)
        list_header.addWidget(clear_btn)
        layout.addLayout(list_header)

        self._file_list = _FileList()
        self._file_list.setObjectName('fileList')
        self._file_list.setMinimumHeight(100)
        self._file_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self._file_list.empty_clicked.connect(lambda: add_menu.exec(
            add_btn.mapToGlobal(add_btn.rect().bottomLeft())
        ))
        layout.addWidget(self._file_list)

        # ── 参数设置 ───────────────────────────────────────────────────────────
        from PySide6.QtWidgets import QFrame
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep)

        male_row = QHBoxLayout()
        male_label = QLabel('男性干部原任职年龄界限')
        male_label.setFixedWidth(160)
        self._male_combo = QComboBox()
        for opt in MALE_LIMIT_OPTIONS:
            self._male_combo.addItem(opt)
        self._male_combo.setCurrentText('改革前任职年龄界限为60岁')
        male_row.addWidget(male_label)
        male_row.addWidget(self._male_combo, 1)
        layout.addLayout(male_row)

        female_row = QHBoxLayout()
        female_label = QLabel('女性干部原任职年龄界限')
        female_label.setFixedWidth(160)
        self._female_combo = QComboBox()
        for opt in FEMALE_LIMIT_OPTIONS:
            self._female_combo.addItem(opt)
        self._female_combo.setCurrentText('改革前任职年龄界限为55岁')
        female_row.addWidget(female_label)
        female_row.addWidget(self._female_combo, 1)
        layout.addLayout(female_row)

        self._chk_update_daolignianue = QCheckBox('更新到龄年月（不勾选则清空该字段）')
        self._chk_update_daolignianue.setChecked(True)
        layout.addWidget(self._chk_update_daolignianue)

        # ── 输出选项 ───────────────────────────────────────────────────────────
        self._chk_save_copy = QCheckBox('另存到指定目录（不修改原文件）')
        self._chk_save_copy.setChecked(False)
        self._chk_save_copy.toggled.connect(self._on_save_copy_toggled)
        layout.addWidget(self._chk_save_copy)

        dir_row = QHBoxLayout()
        dir_icon = QIcon(str(_ASSETS / 'folder.svg'))
        self._dir_edit = QLineEdit()
        self._dir_edit.setReadOnly(True)
        self._dir_edit.setPlaceholderText('选择输出目录…')
        self._dir_edit.setEnabled(False)
        action = self._dir_edit.addAction(dir_icon, QLineEdit.ActionPosition.LeadingPosition)
        action.setEnabled(False)
        self._dir_btn = QPushButton('浏览')
        self._dir_btn.setIcon(dir_icon)
        self._dir_btn.setIconSize(QSize(15, 15))
        self._dir_btn.setEnabled(False)
        self._dir_btn.clicked.connect(self._pick_dir)
        dir_row.addWidget(self._dir_edit)
        dir_row.addWidget(self._dir_btn)
        layout.addLayout(dir_row)

        # ── 开始按钮 ───────────────────────────────────────────────────────────
        run_row = QHBoxLayout()
        run_row.addStretch()
        self._run_btn = QPushButton('开始兼容处理')
        self._run_btn.setObjectName('primary')
        self._run_btn.setIcon(QIcon(str(_ASSETS / 'start.svg')))
        self._run_btn.setIconSize(QSize(16, 16))
        self._run_btn.clicked.connect(self._run)
        run_row.addWidget(self._run_btn)
        layout.addLayout(run_row)

        # ── 日志 ───────────────────────────────────────────────────────────────
        log_header = QHBoxLayout()
        log_header.setContentsMargins(0, 0, 0, 0)
        log_header.setSpacing(4)
        log_header.addStretch()
        self._log_filter_btns: list[QPushButton] = []
        for label, key in [('全部', 'all'), ('成功', 'ok'), ('跳过/警告', 'skip'), ('错误', 'error')]:
            btn = QPushButton(label)
            btn.setFixedHeight(22)
            btn.setCheckable(True)
            btn.setProperty('logFilter', key)
            btn.setObjectName('logFilterBtn')
            btn.clicked.connect(lambda _, k=key: self._set_log_filter(k))
            log_header.addWidget(btn)
            self._log_filter_btns.append(btn)
        self._log_filter_btns[0].setChecked(True)
        layout.addLayout(log_header)

        self._log = QTextEdit()
        self._log.setObjectName('logView')
        self._log.setReadOnly(True)
        self._log.setMinimumHeight(100)
        layout.addWidget(self._log)

    # ── file list helpers ─────────────────────────────────────────────────────

    def _add_file(self, path: str):
        for i in range(self._file_list.count()):
            if self._file_list.item(i).data(Qt.ItemDataRole.UserRole) == path:
                return
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, path)
        item.setSizeHint(QSize(0, 34))
        self._file_list.addItem(item)
        row = _FileRow(path, item)
        row.removed.connect(self._remove_item)
        self._file_list.setItemWidget(item, row)

    def _remove_item(self, item: QListWidgetItem):
        row = self._file_list.row(item)
        if row >= 0:
            self._file_list.takeItem(row)

    def _remove_selected(self):
        for item in self._file_list.selectedItems():
            self._file_list.takeItem(self._file_list.row(item))

    def _clear_files(self):
        self._file_list.clear()

    def _pick_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, '选择 lrmx 文件', '', 'lrmx 文件 (*.lrmx)'
        )
        for p in paths:
            self._add_file(p)

    def _pick_folder(self):
        folder = QFileDialog.getExistingDirectory(self, '选择文件夹')
        if not folder:
            return
        dlg = _LoadingDialog(self, '正在扫描文件夹…')
        self._scan_worker = _FolderScanWorker(folder)

        def _on_done(paths):
            batch = list(paths)
            def add_batch():
                chunk, rest = batch[:20], batch[20:]
                for p in chunk:
                    self._add_file(p)
                batch.clear()
                batch.extend(rest)
                if batch:
                    QTimer.singleShot(0, add_batch)
                else:
                    dlg.accept()
            QTimer.singleShot(0, add_batch)

        self._scan_worker.done.connect(_on_done)
        self._scan_worker.start()
        dlg.exec()

    def _pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, '选择输出目录')
        if d:
            self._dir_edit.setText(d)

    # ── drag & drop ───────────────────────────────────────────────────────────

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith('.lrmx'):
                self._add_file(path)

    # ── output option ─────────────────────────────────────────────────────────

    def _on_save_copy_toggled(self, checked: bool):
        self._dir_edit.setEnabled(checked)
        self._dir_btn.setEnabled(checked)

    # ── log helpers ───────────────────────────────────────────────────────────

    def _append_log(self, message: str):
        if message.startswith('✓'):
            color, kind = '#2e7d32', 'ok'
        elif message.startswith('✗'):
            color, kind = '#c62828', 'error'
        elif message.startswith('△'):
            color, kind = '#e65100', 'skip'
        else:
            color, kind = '#888880', 'info'
        html = f'<span style="color:{color}">{message}</span>'
        self._log_entries.append((html, kind))
        if self._matches_filter(kind):
            self._log.append(html)

    def _matches_filter(self, kind: str) -> bool:
        if self._active_filter == 'all':
            return True
        if self._active_filter == 'ok':
            return kind == 'ok'
        if self._active_filter == 'skip':
            return kind == 'skip'
        if self._active_filter == 'error':
            return kind == 'error'
        return True

    def _set_log_filter(self, key: str):
        self._active_filter = key
        for btn in self._log_filter_btns:
            btn.setChecked(btn.property('logFilter') == key)
        self._log.clear()
        for html, kind in self._log_entries:
            if self._matches_filter(kind):
                self._log.append(html)

    # ── run ───────────────────────────────────────────────────────────────────

    def _run(self):
        files = [
            self._file_list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self._file_list.count())
        ]
        if not files:
            self._append_log('△ 请先添加 lrmx 文件')
            return

        save_copy = self._chk_save_copy.isChecked()
        output_dir = self._dir_edit.text() if save_copy else None
        if save_copy and not output_dir:
            self._append_log('△ 请选择输出目录')
            return

        self._run_btn.setEnabled(False)
        self._log.clear()
        self._log_entries.clear()

        self._worker = _CompatWorker(
            files=files,
            male_limit=self._male_combo.currentText(),
            female_limit=self._female_combo.currentText(),
            output_dir=output_dir,
            sibling=not save_copy,
            update_daolignianue=self._chk_update_daolignianue.isChecked(),
        )
        self._worker.log.connect(self._append_log)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _on_finished(self, processed: int, total: int):
        self._run_btn.setEnabled(True)
        self._append_log(f'── 完成：共 {total} 个文件，处理 {processed} 个 ──')
