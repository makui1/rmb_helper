import time
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListWidget, QListWidgetItem,
    QCheckBox, QLineEdit, QComboBox, QTextEdit,
    QFileDialog, QSizePolicy, QMenu, QDialog, QProgressBar,
)
from PySide6.QtCore import Qt, QSettings, QThread, Signal, QSize, QEvent, QTimer
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QIcon, QPixmap, QPainter, QFont, QColor, QPen

from app.core.lrmx import LrmxFile
from app.core.docx_exporter import DocxExporter
from app.core.pdf_exporter import PdfExporter
from app.utils.naming import apply_rule, PRESETS

_ASSETS = Path(__file__).parent.parent / 'assets'


class _FolderScanWorker(QThread):
    """Recursively scans a folder for .lrmx files on a background thread."""
    done = Signal(list)

    def __init__(self, folder: str, parent=None):
        super().__init__(parent)
        self._folder = folder

    def run(self):
        paths = sorted(str(p) for p in Path(self._folder).rglob('*.lrmx'))
        self.done.emit(paths)


class _LoadingDialog(QDialog):
    """Frameless modal overlay with an indeterminate progress bar."""

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


class _Worker(QThread):
    log = Signal(str)                   # message (prefixed with ✓ / △ / ✗)
    finished = Signal(int, int, float)  # done, total, elapsed_seconds

    def __init__(self, files, output_dir, naming_rule, do_docx, do_pdf, template_path,
                 sibling_dir=False):
        super().__init__()
        self.files = files
        self.output_dir = Path(output_dir) if output_dir else None
        self.naming_rule = naming_rule
        self.do_docx = do_docx
        self.do_pdf = do_pdf
        self.template_path = template_path
        self.sibling_dir = sibling_dir

    def run(self):
        start = time.monotonic()
        total = len(self.files)
        done = 0

        pdf_exporter = PdfExporter()
        if self.do_pdf:
            pdf_ok = pdf_exporter.available()
            if not pdf_ok:
                self.log.emit('△ 未检测到可用 PDF 渲染引擎，本次所有 PDF 输出已跳过')
        else:
            pdf_ok = False

        for lrmx_path in self.files:
            try:
                lf = LrmxFile(Path(lrmx_path))
                stem = apply_rule(self.naming_rule, lf.as_dict()) or Path(lrmx_path).stem
                out_dir = Path(lrmx_path).parent if self.sibling_dir else self.output_dir
                ok = True

                if self.do_docx:
                    if not self.template_path:
                        self.log.emit(f'✗ {stem} → docx 失败（未配置模板路径）')
                        ok = False
                    else:
                        DocxExporter(self.template_path).export(lf, out_dir / (stem + '.docx'))
                        self.log.emit(f'✓ {stem} → docx 完成')

                if self.do_pdf and pdf_ok:
                    if not self.template_path:
                        self.log.emit(f'✗ {stem} → pdf 失败（未配置模板路径）')
                        ok = False
                    else:
                        tmp_docx = out_dir / (stem + '_tmp.docx')
                        DocxExporter(self.template_path).export(lf, tmp_docx)
                        pdf_exporter.export(tmp_docx, out_dir)
                        tmp_docx.unlink(missing_ok=True)
                        self.log.emit(f'✓ {stem} → pdf 完成')

                if ok:
                    done += 1
            except Exception as e:
                self.log.emit(f'✗ {Path(lrmx_path).name}: {e}')

        self.finished.emit(done, total, time.monotonic() - start)


def _text_icon(char: str, color: str = '#888880', size: int = 15) -> QIcon:
    """Render a Unicode character as a QIcon for use as a QLineEdit leading action."""
    pm = QPixmap(size, size)
    pm.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pm)
    font = QFont('Microsoft YaHei UI', -1)
    font.setPixelSize(size)
    painter.setFont(font)
    painter.setPen(QColor(color))
    painter.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, char)
    painter.end()
    return QIcon(pm)


class _FileList(QListWidget):
    """File list that paints a drop hint when empty and emits empty_clicked on click."""
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
    """Single row: icon + filename + × button, with a hover-sensitive bottom separator."""
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


class ConvertTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._settings = QSettings('rmb_helper', 'rmb_helper')
        self._worker = None
        self._build_ui()
        self.setAcceptDrops(True)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        title = QLabel('批量转换')
        title.setObjectName('sectionTitle')
        layout.addWidget(title)

        sub = QLabel('lrmx → docx / pdf 批量转换')
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

        # ── 输出选项 ───────────────────────────────────────────────────────────
        fmt_row = QHBoxLayout()
        fmt_label = QLabel('输出选项')
        fmt_label.setFixedWidth(64)
        self._chk_docx = QCheckBox('docx')
        self._chk_docx.setChecked(True)
        self._chk_pdf = QCheckBox('pdf')
        self._chk_pdf.setChecked(False)
        self._chk_pdf.toggled.connect(self._on_pdf_toggled)
        self._chk_sibling = QCheckBox('输出到任免表同级目录')
        self._chk_sibling.setChecked(False)
        self._chk_sibling.toggled.connect(self._on_sibling_toggled)
        fmt_row.addWidget(fmt_label)
        fmt_row.addWidget(self._chk_docx)
        fmt_row.addSpacing(16)
        fmt_row.addWidget(self._chk_pdf)
        fmt_row.addSpacing(16)
        fmt_row.addWidget(self._chk_sibling)
        fmt_row.addStretch()
        layout.addLayout(fmt_row)

        self._pdf_hint = QLabel('需要安装 WPS / Office / LibreOffice，且导出速度较慢，建议使用第三方工具转换成pdf')
        self._pdf_hint.setObjectName('pdfHint')
        self._pdf_hint.setVisible(False)
        layout.addWidget(self._pdf_hint)

        # ── 输出目录 ───────────────────────────────────────────────────────────
        dir_row = QHBoxLayout()
        dir_label = QLabel('输出目录')
        dir_label.setFixedWidth(64)
        self._dir_edit = QLineEdit()
        self._dir_edit.setPlaceholderText('选择输出目录…')
        self._dir_edit.setReadOnly(True)
        self._dir_edit.addAction(
            QIcon(str(_ASSETS / 'folder.svg')), QLineEdit.ActionPosition.LeadingPosition
        )
        self._dir_btn = QPushButton('浏览')
        self._dir_btn.setIcon(QIcon(str(_ASSETS / 'folder.svg')))
        self._dir_btn.setIconSize(QSize(15, 15))
        self._dir_btn.clicked.connect(self._pick_dir)
        dir_row.addWidget(dir_label)
        dir_row.addWidget(self._dir_edit)
        dir_row.addWidget(self._dir_btn)
        layout.addLayout(dir_row)

        # ── 命名规则 + 开始按钮 ────────────────────────────────────────────────
        rule_row = QHBoxLayout()
        rule_label = QLabel('命名规则')
        rule_label.setFixedWidth(64)
        self._rule_combo = QComboBox()
        self._rule_combo.setEditable(False)
        self._refresh_rules()
        self._custom_edit = QLineEdit()
        self._custom_edit.setPlaceholderText('自定义：{XingMing}_{ShenFenZheng}')
        self._custom_edit.setVisible(False)
        custom_btn = QPushButton('自定义')
        custom_btn.setCheckable(True)
        custom_btn.toggled.connect(self._toggle_custom)
        self._run_btn = QPushButton('开始转换')
        self._run_btn.setIcon(QIcon(str(_ASSETS / 'start.svg')))
        self._run_btn.setIconSize(QSize(16, 16))
        self._run_btn.setObjectName('primary')
        self._run_btn.clicked.connect(self._run)
        rule_row.addWidget(rule_label)
        rule_row.addWidget(self._rule_combo)
        rule_row.addWidget(self._custom_edit)
        rule_row.addWidget(custom_btn)
        rule_row.addStretch()
        rule_row.addWidget(self._run_btn)
        layout.addLayout(rule_row)

        # ── 日志 ───────────────────────────────────────────────────────────────
        log_header = QHBoxLayout()
        log_header.setContentsMargins(0, 0, 0, 0)
        log_header.setSpacing(4)
        log_header.addStretch()
        self._log_filter_btns: list[QPushButton] = []
        for label, key in [('全部', 'all'), ('成功', 'ok'), ('错误', 'error')]:
            btn = QPushButton(label)
            btn.setFixedHeight(22)
            btn.setCheckable(True)
            btn.setProperty('logFilter', key)
            btn.setObjectName('logFilterBtn')
            btn.clicked.connect(lambda _, k=key: self._set_log_filter(k))
            log_header.addWidget(btn)
            self._log_filter_btns.append(btn)
        self._log_filter_btns[0].setChecked(True)
        self._active_filter = 'all'
        layout.addLayout(log_header)

        self._log = QTextEdit()
        self._log.setObjectName('logView')
        self._log.setReadOnly(True)
        self._log.setMinimumHeight(100)
        layout.addWidget(self._log)
        self._log_entries: list[tuple[str, str]] = []  # (html_span, type: ok|error|warn)

    # ── helpers ───────────────────────────────────────────────────────────────

    def _refresh_rules(self):
        rules = self._settings.value('naming_rules', [p[0] for p in PRESETS])
        if isinstance(rules, str):
            rules = [rules]
        self._rule_combo.clear()
        for r in rules:
            self._rule_combo.addItem(r)

    def _toggle_custom(self, checked):
        self._rule_combo.setVisible(not checked)
        self._custom_edit.setVisible(checked)

    def _on_pdf_toggled(self, checked: bool):
        self._pdf_hint.setVisible(checked)

    def _on_sibling_toggled(self, checked: bool):
        self._dir_edit.setEnabled(not checked)
        self._dir_btn.setEnabled(not checked)

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
        self._file_list.takeItem(self._file_list.row(item))

    def _remove_selected(self):
        for item in self._file_list.selectedItems():
            self._file_list.takeItem(self._file_list.row(item))

    def _clear_files(self):
        self._file_list.clear()

    def _pick_files(self, *_):
        paths, _ = QFileDialog.getOpenFileNames(
            self, '选择 lrmx 文件', '', '任免审批表 (*.lrmx)'
        )
        if paths:
            self._batch_add(paths, f'正在添加 {len(paths)} 个文件…')

    def _pick_folder(self):
        folder = QFileDialog.getExistingDirectory(self, '选择包含 lrmx 文件的文件夹')
        if not folder:
            return
        dlg = _LoadingDialog(self.window(), '正在扫描文件夹…')
        worker = _FolderScanWorker(folder)

        def on_done(paths):
            if paths:
                self._batch_add(paths, f'正在添加 {len(paths)} 个文件…',
                                on_finish=dlg.accept)
            else:
                dlg.accept()

        worker.done.connect(on_done)
        worker.start()
        self._scan_worker = worker
        dlg.exec()

    def _batch_add(self, paths: list[str], message: str = '正在添加文件…',
                   on_finish=None):
        """Add paths to the list in batches, keeping the event loop alive."""
        _BATCH = 20
        if len(paths) <= _BATCH and on_finish is None:
            for p in paths:
                self._add_file(p)
            return

        dlg = None
        if on_finish is None:
            dlg = _LoadingDialog(self.window(), message)
        remaining = list(paths)

        def add_batch():
            nonlocal remaining
            batch, remaining = remaining[:_BATCH], remaining[_BATCH:]
            for p in batch:
                self._add_file(p)
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

    def _pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, '选择输出目录')
        if d:
            self._dir_edit.setText(d)

    def _files(self) -> list[str]:
        return [
            self._file_list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self._file_list.count())
        ]

    # ── drag & drop ───────────────────────────────────────────────────────────

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.endswith('.lrmx'):
                self._add_file(path)

    # ── log helpers ───────────────────────────────────────────────────────────

    def _append_log(self, message: str):
        if message.startswith('✓'):
            color, kind = '#2e7d32', 'ok'
        elif message.startswith('✗'):
            color, kind = '#c62828', 'error'
        elif message.startswith('△') or message.startswith('⚠'):
            color, kind = '#e65100', 'warn'
        else:
            color, kind = '#888880', 'info'
        self._log_entries.append((f'<span style="color:{color}">{message}</span>', kind))
        if self._active_filter == 'all' or (
            self._active_filter == 'ok' and kind == 'ok'
        ) or (
            self._active_filter == 'error' and kind in ('error', 'warn')
        ):
            self._log.append(self._log_entries[-1][0])

    def _set_log_filter(self, key: str):
        self._active_filter = key
        for btn in self._log_filter_btns:
            btn.setChecked(btn.property('logFilter') == key)
        self._render_log()

    def _render_log(self):
        self._log.clear()
        for html, kind in self._log_entries:
            if self._active_filter == 'all':
                self._log.append(html)
            elif self._active_filter == 'ok' and kind == 'ok':
                self._log.append(html)
            elif self._active_filter == 'error' and kind in ('error', 'warn'):
                self._log.append(html)

    # ── run ───────────────────────────────────────────────────────────────────

    def _run(self):
        files = self._files()
        if not files:
            self._append_log('⚠ 请先添加 .lrmx 文件')
            return
        sibling = self._chk_sibling.isChecked()
        output_dir = self._dir_edit.text()
        if not sibling and not output_dir:
            self._append_log('⚠ 请选择输出目录，或勾选「输出到任免表同级目录」')
            return

        naming_rule = (
            self._custom_edit.text().strip()
            if self._custom_edit.isVisible()
            else self._rule_combo.currentText()
        ) or PRESETS[0][0]

        template_path = self._settings.value('template_path', '')
        self._run_btn.setEnabled(False)
        self._log.clear()
        self._log_entries.clear()

        self._worker = _Worker(
            files=files,
            output_dir=output_dir,
            naming_rule=naming_rule,
            do_docx=self._chk_docx.isChecked(),
            do_pdf=self._chk_pdf.isChecked(),
            template_path=template_path,
            sibling_dir=sibling,
        )
        self._worker.log.connect(self._append_log)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _on_finished(self, done: int, total: int, elapsed: float):
        self._run_btn.setEnabled(True)
        self._append_log(f'完成 {done}/{total}，耗时 {elapsed:.1f}s')
