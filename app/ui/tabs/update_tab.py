"""双向批量更新 tab：Excel→LRMX（导入）和 LRMX→Excel（导出）。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QFileDialog,
    QFrame, QProgressBar,
    QScrollArea, QSpinBox,
    QRadioButton, QButtonGroup, QDialog,
)
from PySide6.QtCore import Qt, Signal, QSize, QEvent, QTimer, QSettings
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QIcon

from app.ui.workers import BaseWorker
from app.ui.widgets.file_panel import LrmxFilePanel
from app.ui.utils import show_error, show_warning
from app.ui.widgets.loading_overlay import _LoadingOverlay
from app.ui.widgets.field_mapping import _MappingWidget
from app.ui.widgets.update_log import _UpdateLogRow, _UpdateFieldDialog

from app.core.excel_handler import ExcelHandler, MatchMode
from app.core.verify_handler import read_excel_headers, LRMX_FIELDS, DEFAULT_FIELD_ALIASES
from app.core.converters import get_all_converters

_ASSETS = Path(__file__).parent.parent / 'assets'

# ── direction constants ─────────────────────────────────────────────────────

DIRECTION_IMPORT = 0  # Excel → LRMX
DIRECTION_EXPORT = 1  # LRMX → Excel


# ── background workers ──────────────────────────────────────────────────────


class _ImportWorker(BaseWorker):
    """Excel → LRMX"""
    finished = Signal()

    def __init__(self, handler, field_mapping, fields_to_write, header_row,
                 match_excel_col_for_id, match_excel_col_for_name, parent=None):
        super().__init__(parent)
        self._handler = handler
        self._field_mapping = field_mapping
        self._fields_to_write = fields_to_write
        self._header_row = header_row
        self._id_col = match_excel_col_for_id
        self._name_col = match_excel_col_for_name

    def work(self):
        self._handler.update(
            field_mapping=self._field_mapping,
            fields_to_write=self._fields_to_write,
            header_row=self._header_row,
            match_excel_col_for_id=self._id_col,
            match_excel_col_for_name=self._name_col,
            progress_cb=self.log.emit,
        )
        self.finished.emit()


class _ExportWorker(BaseWorker):
    """LRMX → Excel"""
    finished = Signal()

    def __init__(self, handler, field_mapping, fields_to_write, converters,
                 header_row, match_excel_col_for_id, match_excel_col_for_name, parent=None):
        super().__init__(parent)
        self._handler = handler
        self._field_mapping = field_mapping       # {lrmx_field: excel_col}
        self._fields_to_write = fields_to_write
        self._converters = converters              # {lrmx_field: converter_code}
        self._header_row = header_row
        self._id_col = match_excel_col_for_id
        self._name_col = match_excel_col_for_name

    def work(self):
        self._handler.export_to_excel(
            field_mapping=self._field_mapping,
            fields_to_write=self._fields_to_write,
            converters=self._converters,
            header_row=self._header_row,
            match_excel_col_for_id=self._id_col,
            match_excel_col_for_name=self._name_col,
            progress_cb=self.log.emit,
        )
        self.finished.emit()


# ── main tab ────────────────────────────────────────────────────────────────


class UpdateTab(QWidget):
    USES_FILE_PANEL: bool = True
    busy_changed = Signal(bool)

    def __init__(self, file_panel: LrmxFilePanel, parent=None):
        super().__init__(parent)
        self._worker = None
        self._direction = DIRECTION_IMPORT
        self._settings = QSettings('rmb_helper', 'rmb_helper')
        self._counts = {'ok': 0, 'not_found': 0, 'error': 0}
        self._log_rows: list[_UpdateLogRow] = []
        self._active_filter: str | None = None
        self._file_panel = file_panel
        self._build_ui()
        self._file_panel.files_changed.connect(self._on_files_changed)
        self.setAcceptDrops(True)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 15, 24, 15)
        layout.setSpacing(12)

        # ══════════════════════════════════════════════════════════════════════
        # 设置面板（更新开始后隐藏）
        # ══════════════════════════════════════════════════════════════════════
        self._setup_panel = QWidget()
        sp = QVBoxLayout(self._setup_panel)
        sp.setContentsMargins(0, 0, 0, 0)
        sp.setSpacing(12)

        # ── 方向切换按钮 ───────────────────────────────────────────────────
        dir_row = QHBoxLayout()
        self._dir_import_btn = QPushButton('Excel → LRMX  从名册更新任免表')
        self._dir_import_btn.setCheckable(True)
        self._dir_import_btn.setChecked(True)
        self._dir_import_btn.clicked.connect(lambda: self._switch_direction(DIRECTION_IMPORT))
        self._dir_export_btn = QPushButton('LRMX → Excel  从任免表更新名册')
        self._dir_export_btn.setCheckable(True)
        self._dir_export_btn.clicked.connect(lambda: self._switch_direction(DIRECTION_EXPORT))
        dir_row.addWidget(self._dir_import_btn)
        dir_row.addWidget(self._dir_export_btn)
        dir_row.addStretch()
        sp.addLayout(dir_row)

        sep0 = QFrame()
        sep0.setFrameShape(QFrame.Shape.HLine)
        sp.addWidget(sep0)

        title = QLabel('批量更新')
        title.setObjectName('sectionTitle')
        sp.addWidget(title)

        sub = QLabel('利用字段匹配双向同步干部名册与任免表')
        sub.setStyleSheet('color: #888880; font-size: 12px;')
        sp.addWidget(sub)

        bottom_pane = QWidget()
        bot_layout = QVBoxLayout(bottom_pane)
        bot_layout.setContentsMargins(0, 0, 0, 0)
        bot_layout.setSpacing(12)
        sp.addWidget(bottom_pane, 1)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.HLine)
        bot_layout.addWidget(sep1)

        # ── Excel 文件 ─────────────────────────────────────────────────────
        xl_row = QHBoxLayout()
        xl_label = QLabel('干部名册')
        xl_label.setFixedWidth(60)
        self._xl_edit = QLineEdit()
        self._xl_edit.setReadOnly(True)
        self._xl_edit.setPlaceholderText('选择 .xlsx 文件…')
        xl_btn = QPushButton('浏览')
        xl_btn.setIcon(QIcon(str(_ASSETS / 'folder.svg')))
        xl_btn.setIconSize(QSize(15, 15))
        xl_btn.clicked.connect(self._pick_excel)
        xl_row.addWidget(xl_label)
        xl_row.addWidget(self._xl_edit)
        xl_row.addWidget(xl_btn)
        xl_row.addSpacing(12)
        xl_row.addWidget(QLabel('表头行'))
        self._header_spin = QSpinBox()
        self._header_spin.setMinimum(1)
        self._header_spin.setMaximum(20)
        self._header_spin.setValue(1)
        self._header_spin.setFixedWidth(80)
        self._header_spin.valueChanged.connect(self._reload_excel_headers)
        xl_row.addWidget(self._header_spin)
        bot_layout.addLayout(xl_row)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        bot_layout.addWidget(sep2)

        # ── 字段匹配 ────────────────────────────────────────────────────────
        map_title = QLabel('字段匹配')
        map_title.setObjectName('sectionTitle')
        bot_layout.addWidget(map_title)

        map_sub = QLabel('点击左侧 Excel 表头选中 → 点击右侧字段完成匹配')
        map_sub.setStyleSheet('color: #888880; font-size: 12px;')
        bot_layout.addWidget(map_sub)

        self._mapping_widget = _MappingWidget()
        self._mapping_widget.setMinimumHeight(80)
        self._mapping_widget.mapping_changed.connect(self._update_run_btn)
        bot_layout.addWidget(self._mapping_widget, 1)

        clear_map_row = QHBoxLayout()
        clear_map_row.addStretch()
        clear_map_btn = QPushButton('清除全部匹配')
        clear_map_btn.setFixedHeight(24)
        clear_map_btn.clicked.connect(self._mapping_widget.clear_all)
        clear_map_row.addWidget(clear_map_btn)
        bot_layout.addLayout(clear_map_row)

        sep3 = QFrame()
        sep3.setFrameShape(QFrame.Shape.HLine)
        bot_layout.addWidget(sep3)

        # ── 匹配依据 + 开始按钮 ─────────────────────────────────────────────
        run_row = QHBoxLayout()
        match_label = QLabel('匹配依据')
        match_label.setFixedWidth(60)
        self._match_group = QButtonGroup(self)
        self._rb_id = QRadioButton('身份证号（推荐）')
        self._rb_id.setChecked(True)
        self._rb_name = QRadioButton('姓名')
        self._rb_both = QRadioButton('姓名+身份证号')
        self._match_group.addButton(self._rb_id)
        self._match_group.addButton(self._rb_name)
        self._match_group.addButton(self._rb_both)
        for rb in (self._rb_id, self._rb_name, self._rb_both):
            rb.toggled.connect(self._update_run_btn)
        run_row.addWidget(match_label)
        run_row.addWidget(self._rb_id)
        run_row.addSpacing(12)
        run_row.addWidget(self._rb_name)
        run_row.addSpacing(12)
        run_row.addWidget(self._rb_both)
        run_row.addStretch()
        self._run_btn = QPushButton('开始更新')
        self._run_btn.setObjectName('primary')
        self._run_btn.setIcon(QIcon(str(_ASSETS / 'update.svg')))
        self._run_btn.setIconSize(QSize(14, 14))
        self._run_btn.setEnabled(False)
        self._run_btn.clicked.connect(self._run)
        run_row.addWidget(self._run_btn)
        bot_layout.addLayout(run_row)

        layout.addWidget(self._setup_panel, 1)

        # ══════════════════════════════════════════════════════════════════════
        # 配置摘要栏（更新开始后显示，替代设置面板）
        # ══════════════════════════════════════════════════════════════════════
        self._summary_bar = QWidget()
        self._summary_bar.setObjectName('summaryBar')
        self._summary_bar.hide()
        sb = QHBoxLayout(self._summary_bar)
        sb.setContentsMargins(0, 0, 0, 0)
        sb.setSpacing(12)

        self._back_btn = QPushButton('← 重新配置')
        self._back_btn.setFixedHeight(28)
        self._back_btn.clicked.connect(self._back_to_setup)
        sb.addWidget(self._back_btn)

        sep_v = QFrame()
        sep_v.setFrameShape(QFrame.Shape.VLine)
        sep_v.setFixedHeight(18)
        sb.addWidget(sep_v, 0, Qt.AlignmentFlag.AlignVCenter)

        self._summary_lbl = QLabel()
        self._summary_lbl.setStyleSheet('color: #888880; font-size: 12px;')
        sb.addWidget(self._summary_lbl, 1)

        layout.addWidget(self._summary_bar)

        self._progress = QProgressBar()
        self._progress.setObjectName('loadingBar')
        self._progress.setFixedHeight(4)
        self._progress.setTextVisible(False)
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        sep_result = QFrame()
        sep_result.setFrameShape(QFrame.Shape.HLine)
        sep_result.setObjectName('resultTopSep')
        sep_result.hide()
        self._result_top_sep = sep_result
        layout.addWidget(sep_result)

        # ══════════════════════════════════════════════════════════════════════
        # 日志过滤按钮 + 滚动区
        # ══════════════════════════════════════════════════════════════════════
        self._filter_row = QWidget()
        self._filter_row.hide()
        uf = QHBoxLayout(self._filter_row)
        uf.setContentsMargins(0, 0, 0, 0)
        uf.setSpacing(4)
        uf.addStretch()
        self._filter_btns: list[QPushButton] = []
        for label, key in [('全部', 'all'), ('成功', 'ok'), ('错误', 'error')]:
            btn = QPushButton(label)
            btn.setFixedHeight(22)
            btn.setCheckable(True)
            btn.setProperty('logFilter', key)
            btn.setObjectName('logFilterBtn')
            btn.clicked.connect(lambda _, k=key: self._set_filter(k))
            uf.addWidget(btn)
            self._filter_btns.append(btn)
        self._filter_btns[0].setChecked(True)
        layout.addWidget(self._filter_row)

        self._log_scroll = QScrollArea()
        self._log_scroll.setObjectName('resultScroll')
        self._log_scroll.setWidgetResizable(True)
        self._log_scroll.setFrameShape(QFrame.Shape.NoFrame)
        log_container = QWidget()
        self._log_vbox = QVBoxLayout(log_container)
        self._log_vbox.setContentsMargins(0, 0, 0, 0)
        self._log_vbox.setSpacing(0)
        self._log_vbox.addStretch()
        self._log_scroll.setWidget(log_container)
        self._log_scroll.hide()
        layout.addWidget(self._log_scroll, 1)

        self._loading_overlay = _LoadingOverlay(self._log_scroll)
        self._log_scroll.installEventFilter(self)

        # Load fixed field list with converters — all widgets now exist
        self._converters = get_all_converters(self._settings)
        self._mapping_widget.load_lrmx_fields(LRMX_FIELDS, self._converters)

    def showEvent(self, event):
        super().showEvent(event)
        self._converters = get_all_converters(self._settings)
        self._mapping_widget.load_lrmx_fields(LRMX_FIELDS, self._converters)

    # ── event filter (overlay resize) ────────────────────────────────────────

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Resize:
            if obj is self._log_scroll:
                self._loading_overlay.resize(self._log_scroll.size())
        return super().eventFilter(obj, event)

    # ── direction switching ──────────────────────────────────────────────────

    def _switch_direction(self, direction: int):
        self._direction = direction
        self._dir_import_btn.setChecked(direction == DIRECTION_IMPORT)
        self._dir_export_btn.setChecked(direction == DIRECTION_EXPORT)
        self._mapping_widget.set_converters_visible(direction == DIRECTION_EXPORT)
        self._update_run_btn()

    # ── file panel helpers ────────────────────────────────────────────────────

    def _on_files_changed(self, _files: list[str]):
        self._update_run_btn()

    # ── Excel helpers ─────────────────────────────────────────────────────────

    def _pick_excel(self):
        path, _ = QFileDialog.getOpenFileName(
            self, '选择 Excel 文件', '', 'Excel 文件 (*.xlsx *.xls)'
        )
        if path:
            self._xl_edit.setText(path)
            self._reload_excel_headers()

    def _reload_excel_headers(self):
        path = self._xl_edit.text()
        if not path:
            return
        try:
            headers = read_excel_headers(Path(path), self._header_spin.value())
            filtered = [h for h in headers if h and h.strip()]
            self._mapping_widget.load_excel_cols(filtered)
            self._apply_auto_mapping()
        except Exception:
            pass
        self._update_run_btn()

    def _apply_auto_mapping(self):
        import json
        raw = self._settings.value('verify_field_aliases', '')
        if raw:
            try:
                stored = json.loads(raw)
                presets = {tag: [a.strip() for a in csv.split(',') if a.strip()]
                           for tag, csv in stored.items()}
            except Exception:
                presets = DEFAULT_FIELD_ALIASES
        else:
            presets = DEFAULT_FIELD_ALIASES
        self._mapping_widget.apply_presets(presets)

    # ── run button state ──────────────────────────────────────────────────────

    def _update_run_btn(self):
        has_files = self._file_panel.count() > 0
        has_excel = bool(self._xl_edit.text())
        mapping = self._mapping_widget.get_mapping()
        has_mapping = bool(mapping)
        id_col, name_col = self._match_excel_cols()
        if self._rb_id.isChecked():
            key_ok = id_col is not None
        elif self._rb_name.isChecked():
            key_ok = name_col is not None
        else:
            key_ok = id_col is not None and name_col is not None
        ready = has_files and has_excel and has_mapping and key_ok
        self._run_btn.setEnabled(ready)
        if has_mapping and not key_ok:
            tip = '请将匹配依据对应的字段（身份证/姓名）映射到某个 Excel 列'
            self._run_btn.setToolTip(tip)
        else:
            self._run_btn.setToolTip('')

    def _match_excel_cols(self) -> tuple[str | None, str | None]:
        mapping = self._mapping_widget.get_mapping()
        id_col = None
        name_col = None
        for excel_col, lrmx_field in mapping.items():
            if lrmx_field == 'ShenFenZheng':
                id_col = excel_col
            elif lrmx_field == 'XingMing':
                name_col = excel_col
        return id_col, name_col

    # ── run ───────────────────────────────────────────────────────────────────

    def _run(self):
        if self._worker and self._worker.isRunning():
            show_warning(self, '请等待当前更新完成')
            return
        files = self._file_panel.files()
        excel_path = self._xl_edit.text()
        mapping = self._mapping_widget.get_mapping()  # {excel_col: lrmx_field}

        field_display = dict(LRMX_FIELDS)
        mapped_fields = [
            (lrmx_f, field_display.get(lrmx_f, lrmx_f))
            for lrmx_f in mapping.values()
        ]

        dlg = _UpdateFieldDialog(mapped_fields, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        fields_to_write = dlg.selected_fields()
        if not fields_to_write:
            return

        id_col, name_col = self._match_excel_cols()
        if self._rb_id.isChecked():
            match_mode = MatchMode.ID_CARD
        elif self._rb_name.isChecked():
            match_mode = MatchMode.NAME
        else:
            match_mode = MatchMode.NAME_AND_ID

        handler = ExcelHandler(excel_path, files, match_mode)

        self._clear_results()

        xl_name = Path(excel_path).name
        n_files = len(files)
        n_fields = len(fields_to_write)
        self._summary_lbl.setText(
            f'{n_files} 个任免表  ·  名册：{xl_name}  ·  写入 {n_fields} 个字段'
        )

        self._setup_panel.hide()
        self._summary_bar.show()
        self._result_top_sep.show()
        self._filter_row.show()
        self._log_scroll.show()

        self._loading_overlay.set_text('更新中，请稍候…')
        self._loading_overlay.resize(self._log_scroll.size())
        self._loading_overlay.raise_()
        self._loading_overlay.show()

        if self._direction == DIRECTION_IMPORT:
            self._worker = _ImportWorker(
                handler=handler,
                field_mapping=mapping,
                fields_to_write=fields_to_write,
                header_row=self._header_spin.value(),
                match_excel_col_for_id=id_col,
                match_excel_col_for_name=name_col,
            )
        else:
            # 反转映射方向: {excel_col: lrmx_field} → {lrmx_field: excel_col}
            reversed_mapping = {v: k for k, v in mapping.items()}
            converter_mapping = self._mapping_widget.get_converter_mapping()
            self._worker = _ExportWorker(
                handler=handler,
                field_mapping=reversed_mapping,
                fields_to_write=fields_to_write,
                converters=converter_mapping,
                header_row=self._header_spin.value(),
                match_excel_col_for_id=id_col,
                match_excel_col_for_name=name_col,
            )
        self._worker.log.connect(self._on_log)
        self._worker.error.connect(self._on_critical)
        self._worker.finished.connect(self._on_finished)
        self.busy_changed.emit(True)
        self._worker.start()

    # ── log handling ──────────────────────────────────────────────────────────

    def _on_log(self, message: str):
        if message.startswith('✓'):
            kind = 'ok'
            self._counts['ok'] += 1
        elif message.startswith('△'):
            kind = 'not_found'
            self._counts['not_found'] += 1
        elif message.startswith('共处理'):
            # summary line, skip logging as a row
            return
        else:
            kind = 'error'
            self._counts['error'] += 1

        row = _UpdateLogRow(message, kind)
        self._log_rows.append(row)
        idx = self._log_vbox.count() - 1
        self._log_vbox.insertWidget(idx, row)

        if self._active_filter is not None:
            show = (
                (self._active_filter == 'ok' and kind == 'ok')
                or (self._active_filter == 'error' and kind in ('not_found', 'error'))
            )
            row.setVisible(show)

    def _on_critical(self, msg: str):
        self.busy_changed.emit(False)
        self._loading_overlay.hide()
        show_error(self, msg)
        self._back_to_setup()

    def _on_finished(self):
        self.busy_changed.emit(False)
        QTimer.singleShot(400, self._loading_overlay.hide)
        ok = self._counts['ok']
        not_found = self._counts['not_found']
        error = self._counts['error']
        # Exclude summary line from counts if present
        self._summary_lbl.setText(
            f'已更新 {ok} 个  ·  未匹配 {not_found} 个  ·  失败 {error} 个'
        )

    # ── filter ────────────────────────────────────────────────────────────────

    def _set_filter(self, key: str):
        self._active_filter = None if key == 'all' else key
        for btn in self._filter_btns:
            btn.setChecked(btn.property('logFilter') == key)
        for row in self._log_rows:
            if self._active_filter is None:
                row.show()
            elif self._active_filter == 'ok':
                row.setVisible(row._kind == 'ok')
            else:  # 'error' → 包含 not_found 和 error
                row.setVisible(row._kind in ('not_found', 'error'))

    # ── clear / back ──────────────────────────────────────────────────────────

    def _clear_results(self):
        self._counts = {'ok': 0, 'not_found': 0, 'error': 0}
        self._log_rows = []
        self._active_filter = None
        for btn in self._filter_btns:
            btn.setChecked(btn.property('logFilter') == 'all')
        while self._log_vbox.count() > 1:
            item = self._log_vbox.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _back_to_setup(self):
        self._progress.setVisible(False)
        self.busy_changed.emit(False)
        self._loading_overlay.hide()
        if self._worker and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(3000)
            self._worker.log.disconnect()
            self._worker.error.disconnect()
            self._worker.finished.disconnect()
        self._setup_panel.show()
        self._summary_bar.hide()
        self._result_top_sep.hide()
        self._filter_row.hide()
        self._log_scroll.hide()
        self._clear_results()

    # ── drag & drop ───────────────────────────────────────────────────────────

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if Path(path).is_dir():
                self._file_panel._scan_and_add(path)
            elif path.lower().endswith('.lrmx'):
                self._file_panel.add_file(path)
