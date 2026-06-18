from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListWidget, QListWidgetItem,
    QCheckBox, QLineEdit, QComboBox, QTextEdit,
    QFileDialog, QFrame, QProgressBar,
)
from PySide6.QtCore import Qt, QThread, Signal, QSize
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QIcon
from app.ui.widgets.file_panel import LrmxFilePanel

from app.core.compat_processor import (
    MALE_LIMIT_OPTIONS, FEMALE_LIMIT_OPTIONS,
    process_file, is_new_version,
)
from app.core.lrmx import LrmxFile

_ASSETS = Path(__file__).parent.parent / 'assets'




# ── background worker ─────────────────────────────────────────────────────────

class _CompatWorker(QThread):
    log = Signal(str)
    finished = Signal(int, int)  # processed, total
    progress = Signal(int)       # current step

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
        for i, f in enumerate(self.files):
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
            self.progress.emit(i + 1)
        self.finished.emit(processed, total)


# ── tab widget ────────────────────────────────────────────────────────────────

class CompatTab(QWidget):
    USES_FILE_PANEL: bool = True
    busy_changed = Signal(bool)

    def __init__(self, file_panel: LrmxFilePanel, parent=None):
        super().__init__(parent)
        self._worker = None
        self._log_entries: list[tuple[str, str]] = []
        self._active_filter = 'all'
        self._file_panel = file_panel
        self._build_ui()
        self.setAcceptDrops(True)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 15, 24, 15)
        layout.setSpacing(12)

        title = QLabel('版本兼容')
        title.setObjectName('sectionTitle')
        layout.addWidget(title)

        sub = QLabel('为旧版任免表补充「改革前任职年龄界限」和「到龄年月」字段')
        sub.setStyleSheet('color: #888880; font-size: 12px;')
        layout.addWidget(sub)

        bot_layout = QVBoxLayout()
        bot_layout.setContentsMargins(0, 0, 0, 0)
        bot_layout.setSpacing(12)
        layout.addLayout(bot_layout, 1)

        # ── 参数设置 ───────────────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        bot_layout.addWidget(sep)

        male_row = QHBoxLayout()
        male_label = QLabel('男性干部原任职年龄界限')
        male_label.setFixedWidth(160)
        self._male_combo = QComboBox()
        for opt in MALE_LIMIT_OPTIONS:
            self._male_combo.addItem(opt)
        self._male_combo.setCurrentText('改革前任职年龄界限为60岁')
        male_row.addWidget(male_label)
        male_row.addWidget(self._male_combo, 1)
        bot_layout.addLayout(male_row)

        female_row = QHBoxLayout()
        female_label = QLabel('女性干部原任职年龄界限')
        female_label.setFixedWidth(160)
        self._female_combo = QComboBox()
        for opt in FEMALE_LIMIT_OPTIONS:
            self._female_combo.addItem(opt)
        self._female_combo.setCurrentText('改革前任职年龄界限为55岁')
        female_row.addWidget(female_label)
        female_row.addWidget(self._female_combo, 1)
        bot_layout.addLayout(female_row)

        self._chk_update_daolignianue = QCheckBox('更新到龄年月（不勾选则清空该字段）')
        self._chk_update_daolignianue.setChecked(True)
        bot_layout.addWidget(self._chk_update_daolignianue)

        # ── 输出选项 ───────────────────────────────────────────────────────────
        self._chk_save_copy = QCheckBox('另存到指定目录（不修改原文件）')
        self._chk_save_copy.setChecked(False)
        self._chk_save_copy.toggled.connect(self._on_save_copy_toggled)
        bot_layout.addWidget(self._chk_save_copy)

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
        bot_layout.addLayout(dir_row)

        # ── 开始按钮 ───────────────────────────────────────────────────────────
        run_row = QHBoxLayout()
        run_row.addStretch()
        self._run_btn = QPushButton('开始兼容处理')
        self._run_btn.setObjectName('primary')
        self._run_btn.setIcon(QIcon(str(_ASSETS / 'start.svg')))
        self._run_btn.setIconSize(QSize(16, 16))
        self._run_btn.clicked.connect(self._run)
        run_row.addWidget(self._run_btn)
        bot_layout.addLayout(run_row)

        self._progress = QProgressBar()
        self._progress.setObjectName('loadingBar')
        self._progress.setFixedHeight(4)
        self._progress.setTextVisible(False)
        self._progress.setVisible(False)
        bot_layout.addWidget(self._progress)

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
        bot_layout.addLayout(log_header)

        self._log = QTextEdit()
        self._log.setObjectName('logView')
        self._log.setReadOnly(True)
        self._log.setMinimumHeight(80)
        bot_layout.addWidget(self._log, 1)


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
                self._file_panel.add_file(path)

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
        files = self._file_panel.files()
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
        self._progress.setRange(0, len(files))
        self._progress.setValue(0)
        self._progress.setVisible(True)

        self._worker.log.connect(self._append_log)
        self._worker.progress.connect(self._progress.setValue)
        self._worker.finished.connect(self._on_finished)
        self.busy_changed.emit(True)
        self._worker.start()

    def _on_finished(self, processed: int, total: int):
        self._progress.setVisible(False)
        self._run_btn.setEnabled(True)
        self.busy_changed.emit(False)
        self._append_log(f'── 完成：共 {total} 个文件，处理 {processed} 个 ──')
