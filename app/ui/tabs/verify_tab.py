"""批量核验 tab — 核验（LRMX vs Excel）+ 对比（LRMX vs LRMX）。"""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QCheckBox,
    QRadioButton, QButtonGroup, QFileDialog,
    QFrame, QProgressBar,
    QScrollArea, QSpinBox, QTabWidget,
)
from PySide6.QtCore import Qt, Signal, QSize, QEvent, QTimer, QSettings
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QIcon

from app.ui.workers import BaseWorker
from app.ui.widgets.file_panel import LrmxFilePanel
from app.ui.utils import show_warning
from app.ui.widgets.loading_overlay import _LoadingOverlay
from app.ui.widgets.field_mapping import _MappingWidget
from app.ui.widgets.verify_result import _ResultRow

from app.core.lrmx import LrmxFile
from app.core.excel_handler import MatchMode
from app.core.verify_handler import (
    VerifyHandler, PersonResult, FieldResult,
    read_excel_headers, LRMX_FIELDS, DEFAULT_FIELD_ALIASES,
)
from app.core.compare_rules import CompareRule, rules_from_json, apply_rule
from app.core.result_exporter import export_excel, export_html

_ASSETS = Path(__file__).parent.parent / 'assets'


# ═══════════════════════════════════════════════════════════════════════════════
# Workers
# ═══════════════════════════════════════════════════════════════════════════════

class _VerifyWorker(BaseWorker):
    """核验 Worker：LRMX vs Excel。"""
    result_ready = Signal(object)
    finished = Signal()

    def __init__(self, handler: VerifyHandler, parent=None):
        super().__init__(parent)
        self._handler = handler

    def run(self):
        try:
            self._handler.verify(progress_cb=self.result_ready.emit)
        except Exception as e:
            self.result_ready.emit(PersonResult(
                name='', lrmx_path='', status='error', error_msg=str(e)
            ))
        self.finished.emit()


class _CompareWorker(BaseWorker):
    """对比 Worker：LRMX vs LRMX（同名文件逐字段对比）。"""
    result_ready = Signal(object)
    finished = Signal()

    def __init__(self, files: list[str], target_dir: str,
                 field_tags: list[str] | None = None,
                 rules: dict[str, CompareRule] | None = None, parent=None):
        super().__init__(parent)
        self.files = files
        self.target_dir = Path(target_dir)
        self.field_tags = field_tags or [tag for tag, _ in LRMX_FIELDS]
        self.rules = rules or {}

    def run(self):
        diff_targets: list[Path] = []
        for file_path in self.files:
            src = Path(file_path)
            try:
                target = self.target_dir / src.name
                if not target.exists():
                    self.result_ready.emit(PersonResult(
                        name=src.stem, lrmx_path=str(src),
                        status='not_found',
                    ))
                    continue

                lf1 = LrmxFile(src)
                lf2 = LrmxFile(target)

                field_results: list[FieldResult] = []
                for tag in self.field_tags:
                    v1 = (lf1.get(tag) or '').strip()
                    v2 = (lf2.get(tag) or '').strip()
                    match = v1 == v2
                    if not match and tag in self.rules:
                        match = apply_rule(self.rules[tag], v1, v2)
                    field_results.append(FieldResult(
                        field=tag,
                        excel_val=v1, lrmx_val=v2, match=match,
                    ))

                diffs = sum(1 for f in field_results if not f.match)
                status = 'ok' if diffs == 0 else 'diff'
                self.result_ready.emit(PersonResult(
                    name=src.stem, lrmx_path=str(src),
                    status=status, fields=field_results,
                ))
                if status == 'diff':
                    diff_targets.append(target)
            except Exception as e:
                self.result_ready.emit(PersonResult(
                    name=Path(file_path).stem, lrmx_path=str(file_path),
                    status='error', error_msg=str(e),
                ))

        # 将有差异的目标文件复制到同级"有差异"目录
        if diff_targets:
            diff_dir = self.target_dir / '有差异'
            diff_dir.mkdir(parents=True, exist_ok=True)
            copied = 0
            for p in diff_targets:
                try:
                    shutil.copy2(p, diff_dir / p.name)
                    copied += 1
                except Exception:
                    pass
            self.log.emit(f'已将有差异的 {copied} 个文件复制到 {diff_dir}')

        self.finished.emit()


# ═══════════════════════════════════════════════════════════════════════════════
# _ResultPanelMixin — 共享的结果展示逻辑
# ═══════════════════════════════════════════════════════════════════════════════

class _ResultPanelMixin:
    """Mixin：为核验/对比面板提供统一的结果展示（汇总卡片、筛选、导出）。"""

    def _build_result_area(self, parent_layout: QVBoxLayout):
        """在 parent_layout 中构建结果区域控件，设置实例属性。"""
        # 进度条
        self._progress = QProgressBar()
        self._progress.setObjectName('loadingBar')
        self._progress.setFixedHeight(4)
        self._progress.setTextVisible(False)
        self._progress.setVisible(False)
        parent_layout.addWidget(self._progress)

        sep_result = QFrame()
        sep_result.setFrameShape(QFrame.Shape.HLine)
        sep_result.setObjectName('resultTopSep')
        sep_result.hide()
        self._result_top_sep = sep_result
        parent_layout.addWidget(sep_result)

        # 汇总卡片
        summary_row = QHBoxLayout()
        summary_row.setSpacing(12)
        self._count_labels: dict[str, QLabel] = {}
        self._card_widgets: dict[str, QWidget] = {}
        cards = [
            ('ok',        '0', '一致'),
            ('diff',      '0', '有差异'),
            ('not_found', '0', '未找到'),
            ('error',     '0', '错误'),
        ]
        for key, count, desc in cards:
            card = QWidget()
            card.setCursor(Qt.CursorShape.PointingHandCursor)
            card.setObjectName('summaryCard')
            card.setStyleSheet('border-radius: 4px; padding: 2px;')
            cl = QHBoxLayout(card)
            cl.setContentsMargins(8, 4, 8, 4)
            cl.setSpacing(4)
            cnt_lbl = QLabel(count)
            cnt_lbl.setObjectName(f'countLabel_{key}')
            desc_lbl = QLabel(desc)
            desc_lbl.setStyleSheet('color: #888880; font-size: 11px;')
            cl.addWidget(cnt_lbl)
            cl.addWidget(desc_lbl)
            self._count_labels[key] = cnt_lbl
            self._card_widgets[key] = card
            card.mousePressEvent = lambda e, k=key: self._set_result_filter(k)
            summary_row.addWidget(card)
        summary_row.addStretch()
        self._summary_cards_widget = QWidget()
        self._summary_cards_widget.setLayout(summary_row)
        self._summary_cards_widget.hide()
        parent_layout.addWidget(self._summary_cards_widget)

        # 导出行
        self._export_row = QWidget()
        self._export_row.hide()
        er = QHBoxLayout(self._export_row)
        er.setContentsMargins(0, 2, 0, 2)
        er.setSpacing(12)
        self._chk_excel = QCheckBox('Excel')
        self._chk_excel.setChecked(True)
        self._chk_html = QCheckBox('HTML')
        self._chk_html.setChecked(True)
        self._chk_excel.toggled.connect(self._update_export_btn)
        self._chk_html.toggled.connect(self._update_export_btn)
        er.addWidget(self._chk_excel)
        er.addWidget(self._chk_html)
        self._export_btn = QPushButton('导出当前结果')
        self._export_btn.setIcon(QIcon(str(_ASSETS / 'export.svg')))
        self._export_btn.clicked.connect(self._export_results)
        er.addWidget(self._export_btn)
        self._export_status_lbl = QLabel('')
        self._export_status_lbl.setStyleSheet('color: #1E7A3A; font-size: 12px;')
        er.addWidget(self._export_status_lbl, 1)
        parent_layout.addWidget(self._export_row)

        # 结果滚动区
        result_scroll = QScrollArea()
        result_scroll.setObjectName('resultScroll')
        result_scroll.setWidgetResizable(True)
        result_scroll.setFrameShape(QFrame.Shape.NoFrame)
        result_container = QWidget()
        self._result_vbox = QVBoxLayout(result_container)
        self._result_vbox.setContentsMargins(0, 0, 0, 0)
        self._result_vbox.setSpacing(0)
        self._result_vbox.addStretch()
        result_scroll.setWidget(result_container)
        result_scroll.hide()
        self._result_scroll = result_scroll
        parent_layout.addWidget(result_scroll, 1)

        self._loading_overlay = _LoadingOverlay(self._result_scroll)
        self._result_scroll.installEventFilter(self)

    def _init_result_state(self):
        self._counts = {'ok': 0, 'diff': 0, 'not_found': 0, 'error': 0}
        self._result_rows: list[_ResultRow] = []
        self._active_filter: str | None = None

    def _show_results_view(self):
        self._setup_panel.hide()
        self._summary_bar.show()
        self._result_top_sep.show()
        self._summary_cards_widget.show()
        self._export_row.show()
        self._update_export_btn()
        self._result_scroll.show()

    def _hide_results_view(self):
        self._progress.setVisible(False)
        self._loading_overlay.hide()
        self._setup_panel.show()
        self._summary_bar.hide()
        self._result_top_sep.hide()
        self._summary_cards_widget.hide()
        self._export_row.hide()
        self._result_scroll.hide()

    def _on_result(self, result: PersonResult):
        self._progress.setValue(self._progress.value() + 1)
        status = result.status if result.status in self._counts else 'error'
        self._counts[status] += 1
        self._count_labels[status].setText(str(self._counts[status]))
        row_widget = _ResultRow(result,
                                col_a_label=self._diff_col_a,
                                col_b_label=self._diff_col_b,
                                footer_prefix=self._diff_footer,
                                not_found_text=self._diff_not_found)
        self._result_rows.append(row_widget)
        idx = self._result_vbox.count() - 1
        self._result_vbox.insertWidget(idx, row_widget)

    def _on_finished(self):
        self._progress.setVisible(False)
        self.busy_changed.emit(False)
        QTimer.singleShot(400, self._loading_overlay.hide)
        self._update_export_btn()

    def _clear_results(self):
        self._counts = {'ok': 0, 'diff': 0, 'not_found': 0, 'error': 0}
        self._result_rows = []
        self._active_filter = None
        for key, lbl in self._count_labels.items():
            lbl.setText('0')
        for card in self._card_widgets.values():
            card.setStyleSheet('border-radius: 4px; padding: 2px;')
        while self._result_vbox.count() > 1:
            item = self._result_vbox.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _update_export_btn(self):
        has_format = self._chk_excel.isChecked() or self._chk_html.isChecked()
        visible_count = sum(1 for r in self._result_rows if r.isVisible())
        self._export_btn.setEnabled(has_format and visible_count > 0)

    def _set_result_filter(self, key: str):
        if self._active_filter == key:
            self._active_filter = None
        else:
            self._active_filter = key
        for k, card in self._card_widgets.items():
            if self._active_filter == k:
                card.setStyleSheet(
                    'background: #EEF3FF; border: 1.5px solid #7090C8; border-radius: 4px;'
                )
            else:
                card.setStyleSheet('border-radius: 4px; padding: 2px;')
        self._loading_overlay.resize(self._result_scroll.size())
        self._loading_overlay.raise_()
        self._loading_overlay.show()
        QTimer.singleShot(0, self._apply_result_filter)

    def _apply_result_filter(self):
        for row in self._result_rows:
            if self._active_filter is None:
                row.show()
            else:
                row.setVisible(row._result.status == self._active_filter)
        self._update_export_btn()
        QTimer.singleShot(300, self._loading_overlay.hide)

    def _export_results(self):
        visible = [r._result for r in self._result_rows if r.isVisible()]
        if not visible:
            return
        directory = QFileDialog.getExistingDirectory(self, '选择导出目录')
        if not directory:
            return
        self._loading_overlay.set_text('导出中，请稍候…')
        self._loading_overlay.resize(self._result_scroll.size())
        self._loading_overlay.raise_()
        self._loading_overlay.show()

        def _do():
            filter_label = {
                'ok': '一致', 'diff': '有差异',
                'not_found': '未找到', 'error': '错误',
            }.get(self._active_filter, '全部')
            date_str = datetime.now().strftime('%Y%m%d')
            stem = f'{self._export_prefix}_{date_str}_{filter_label}'
            out_dir = Path(directory)
            errors: list[str] = []
            saved: list[str] = []
            if self._chk_excel.isChecked():
                try:
                    p = out_dir / f'{stem}.xlsx'
                    export_excel(visible, p)
                    saved.append(p.name)
                except Exception as e:
                    errors.append(f'Excel: {e}')
            if self._chk_html.isChecked():
                try:
                    p = out_dir / f'{stem}.html'
                    export_html(visible, p, self._summary_lbl.text())
                    saved.append(p.name)
                except Exception as e:
                    errors.append(f'HTML: {e}')
            self._loading_overlay.hide()
            self._loading_overlay.set_text('处理中，请稍候…')
            if errors:
                show_warning(self, '\n'.join(errors))
            if saved:
                self._export_status_lbl.setText(f'✓ 已保存到 {directory}')
                QTimer.singleShot(3000, lambda: self._export_status_lbl.setText(''))

        QTimer.singleShot(0, _do)

    def _on_overlay_resize(self, obj, event):
        """子类 eventFilter 中调用，处理 loading overlay 尺寸跟随。"""
        if event.type() == QEvent.Type.Resize:
            if obj is self._result_scroll:
                self._loading_overlay.resize(self._result_scroll.size())
        return False  # 未处理则交由子类 super().eventFilter()


# ═══════════════════════════════════════════════════════════════════════════════
# _VerifyPanel — 核验（LRMX vs Excel）
# ═══════════════════════════════════════════════════════════════════════════════

class _VerifyPanel(QWidget, _ResultPanelMixin):
    busy_changed = Signal(bool)

    def __init__(self, file_panel: LrmxFilePanel, parent=None):
        super().__init__(parent)
        self._worker = None
        self._settings = QSettings('rmb_helper', 'rmb_helper')
        self._file_panel = file_panel
        self._export_prefix = '核验结果'
        self._diff_col_a = 'Excel 名册'
        self._diff_col_b = '任免表'
        self._diff_footer = '共核验'
        self._diff_not_found = '名册无此人'
        self._build_ui()
        self._init_result_state()
        self._file_panel.files_changed.connect(self._on_files_changed)
        self.setAcceptDrops(True)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # ── 设置面板 ──────────────────────────────────────────────────────
        self._setup_panel = QWidget()
        sp = QVBoxLayout(self._setup_panel)
        sp.setContentsMargins(0, 0, 0, 0)
        sp.setSpacing(12)

        title = QLabel('批量核验')
        title.setObjectName('sectionTitle')
        sp.addWidget(title)

        sub = QLabel('对照干部名册，核验任免表字段')
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

        # Excel 文件
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

        # 字段匹配
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

        # 匹配依据 + 开始按钮
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
        self._run_btn = QPushButton('开始核验')
        self._run_btn.setObjectName('primary')
        self._run_btn.setEnabled(False)
        self._run_btn.clicked.connect(self._run)
        run_row.addWidget(self._run_btn)
        bot_layout.addLayout(run_row)

        layout.addWidget(self._setup_panel, 1)

        # ── 摘要栏 ────────────────────────────────────────────────────────
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

        # ── 结果区域 ──────────────────────────────────────────────────────
        self._build_result_area(layout)

        # 初始加载
        self._mapping_widget.load_lrmx_fields(LRMX_FIELDS)
        self._refresh_rules()

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_rules()

    def _refresh_rules(self):
        rules = rules_from_json(self._settings.value('compare_rules', ''))
        self._mapping_widget.set_available_rules(rules)

    def _on_files_changed(self, _files: list[str]):
        self._update_run_btn()

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
            self._run_btn.setToolTip('请将匹配依据对应的字段（身份证/姓名）映射到某个 Excel 列')
        else:
            self._run_btn.setToolTip('')

    def eventFilter(self, obj, event):
        self._on_overlay_resize(obj, event)
        return super().eventFilter(obj, event)

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

    def _run(self):
        rule_mapping = self._mapping_widget.get_rule_mapping()
        files = self._file_panel.files()
        excel_path = self._xl_edit.text()
        mapping = self._mapping_widget.get_mapping()

        if self._rb_id.isChecked():
            match_mode = MatchMode.ID_CARD
        elif self._rb_name.isChecked():
            match_mode = MatchMode.NAME
        else:
            match_mode = MatchMode.NAME_AND_ID

        id_col, name_col = self._match_excel_cols()

        handler = VerifyHandler(
            excel_path=excel_path,
            lrmx_files=files,
            match_mode=match_mode,
            header_row=self._header_spin.value(),
            field_mapping=mapping,
            match_excel_col_for_id=id_col,
            match_excel_col_for_name=name_col,
            compare_rules=rule_mapping,
        )

        self._clear_results()

        xl_name = Path(excel_path).name
        n_files = len(files)
        n_mapped = len(mapping)
        self._summary_lbl.setText(
            f'{n_files} 个任免表  ·  名册：{xl_name}  ·  已匹配 {n_mapped} 个字段'
        )
        self._show_results_view()

        self._loading_overlay.resize(self._result_scroll.size())
        self._loading_overlay.raise_()
        self._loading_overlay.show()

        self._progress.setRange(0, len(files))
        self._progress.setValue(0)
        self._progress.setVisible(True)

        self._worker = _VerifyWorker(handler)
        self._worker.result_ready.connect(self._on_result)
        self._worker.finished.connect(self._on_finished)
        self.busy_changed.emit(True)
        self._worker.start()

    def _back_to_setup(self):
        self._progress.setVisible(False)
        self.busy_changed.emit(False)
        self._hide_results_view()
        self._back_btn.setText('← 重新配置')
        self._clear_results()

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


# ═══════════════════════════════════════════════════════════════════════════════
# _ComparePanel — 对比（LRMX vs LRMX）
# ═══════════════════════════════════════════════════════════════════════════════

class _ComparePanel(QWidget, _ResultPanelMixin):
    busy_changed = Signal(bool)

    def __init__(self, file_panel: LrmxFilePanel, parent=None):
        super().__init__(parent)
        self._worker = None
        self._settings = QSettings('rmb_helper', 'rmb_helper')
        self._file_panel = file_panel
        self._export_prefix = '对比结果'
        self._diff_col_a = '当前任免表'
        self._diff_col_b = '对比任免表'
        self._diff_footer = '共对比'
        self._diff_not_found = '未找到'
        self._selected_fields: list[str] = [tag for tag, _ in LRMX_FIELDS]
        self._build_ui()
        self._update_field_label()
        self._init_result_state()
        self._file_panel.files_changed.connect(self._on_files_changed)
        self.setAcceptDrops(True)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # ── 设置面板 ──────────────────────────────────────────────────────
        self._setup_panel = QWidget()
        sp = QVBoxLayout(self._setup_panel)
        sp.setContentsMargins(0, 0, 0, 0)
        sp.setSpacing(12)

        title = QLabel('任免表对比')
        title.setObjectName('sectionTitle')
        sp.addWidget(title)

        sub = QLabel(
            '将侧边栏中的每个任免表与指定目录中同名任免表逐字段对比，'
            '找出有差异的文件。'
        )
        sub.setStyleSheet('color: #888880; font-size: 12px;')
        sub.setWordWrap(True)
        sp.addWidget(sub)

        sp.addSpacing(8)

        # 对比目录
        dir_row = QHBoxLayout()
        dir_label = QLabel('对比目录')
        dir_label.setFixedWidth(60)
        self._dir_edit = QLineEdit()
        self._dir_edit.setReadOnly(True)
        self._dir_edit.setPlaceholderText('选择包含同名任免表的目录…')
        dir_btn = QPushButton('浏览')
        dir_btn.setIcon(QIcon(str(_ASSETS / 'folder.svg')))
        dir_btn.setIconSize(QSize(15, 15))
        dir_btn.clicked.connect(self._pick_dir)
        dir_row.addWidget(dir_label)
        dir_row.addWidget(self._dir_edit)
        dir_row.addWidget(dir_btn)
        sp.addLayout(dir_row)

        sp.addSpacing(8)

        # 对比字段选择
        field_row = QHBoxLayout()
        field_row.addWidget(QLabel('对比字段'))
        self._field_info_lbl = QLabel()
        self._field_info_lbl.setStyleSheet('color: #888880; font-size: 12px;')
        field_row.addWidget(self._field_info_lbl, 1)
        field_btn = QPushButton('选择字段…')
        field_btn.clicked.connect(self._select_fields)
        field_row.addWidget(field_btn)
        sp.addLayout(field_row)

        sp.addSpacing(8)

        # 开始按钮
        run_row = QHBoxLayout()
        run_row.addStretch()
        self._run_btn = QPushButton('开始对比')
        self._run_btn.setObjectName('primary')
        self._run_btn.setEnabled(False)
        self._run_btn.clicked.connect(self._run)
        run_row.addWidget(self._run_btn)
        sp.addLayout(run_row)

        sp.addStretch()
        layout.addWidget(self._setup_panel, 1)

        # ── 摘要栏 ────────────────────────────────────────────────────────
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

        # ── 结果区域 ──────────────────────────────────────────────────────
        self._build_result_area(layout)

    def _on_files_changed(self, _files: list[str]):
        self._update_run_btn()

    def _pick_dir(self):
        directory = QFileDialog.getExistingDirectory(self, '选择对比目录')
        if directory:
            self._dir_edit.setText(directory)
            self._update_run_btn()

    def _update_run_btn(self):
        has_files = self._file_panel.count() > 0
        has_dir = bool(self._dir_edit.text())
        self._run_btn.setEnabled(has_files and has_dir)

    def _update_field_label(self):
        n = len(self._selected_fields)
        total = len(LRMX_FIELDS)
        self._field_info_lbl.setText(f'{n}/{total} 个字段')

    def _select_fields(self):
        """打开字段选择对话框。"""
        from PySide6.QtWidgets import QDialog, QCheckBox, QDialogButtonBox
        dlg = QDialog(self)
        dlg.setWindowTitle('选择对比字段')
        dlg.setMinimumWidth(280)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(4)

        checks: dict[str, QCheckBox] = {}
        for tag, display in LRMX_FIELDS:
            cb = QCheckBox(display)
            cb.setChecked(tag in self._selected_fields)
            checks[tag] = cb
            layout.addWidget(cb)

        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(dlg.accept)
        btn_box.rejected.connect(dlg.reject)
        layout.addWidget(btn_box)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._selected_fields = [tag for tag, cb in checks.items() if cb.isChecked()]
            self._update_field_label()

    def _run(self):
        files = self._file_panel.files()
        target_dir = self._dir_edit.text()

        # 加载比较规则
        raw = self._settings.value('compare_rules', '')
        rule_list = rules_from_json(raw)
        rules: dict[str, CompareRule] = {}
        for rule in rule_list:
            # 比较规则应用于所有字段
            rules[rule.name] = rule

        self._clear_results()

        n_files = len(files)
        dir_name = Path(target_dir).name
        self._summary_lbl.setText(
            f'{n_files} 个任免表  ·  对比目录：{dir_name}'
        )
        self._show_results_view()

        self._loading_overlay.resize(self._result_scroll.size())
        self._loading_overlay.raise_()
        self._loading_overlay.show()

        self._progress.setRange(0, len(files))
        self._progress.setValue(0)
        self._progress.setVisible(True)

        self._worker = _CompareWorker(files=files, target_dir=target_dir,
                                      field_tags=list(self._selected_fields),
                                      rules=rules)
        self._worker.result_ready.connect(self._on_result)
        self._worker.log.connect(lambda msg: self._summary_lbl.setText(
            self._summary_lbl.text() + f'  ·  {msg}'
        ))
        self._worker.finished.connect(self._on_finished)
        self.busy_changed.emit(True)
        self._worker.start()

    def _back_to_setup(self):
        self._progress.setVisible(False)
        self.busy_changed.emit(False)
        self._hide_results_view()
        self._back_btn.setText('← 重新配置')
        self._clear_results()

    def eventFilter(self, obj, event):
        self._on_overlay_resize(obj, event)
        return super().eventFilter(obj, event)

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


# ═══════════════════════════════════════════════════════════════════════════════
# VerifyTab — 容器
# ═══════════════════════════════════════════════════════════════════════════════

class VerifyTab(QWidget):
    USES_FILE_PANEL: bool = True
    busy_changed = Signal(bool)

    def __init__(self, file_panel: LrmxFilePanel, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 15, 24, 15)
        layout.setSpacing(0)

        tabs = QTabWidget()

        self._verify_panel = _VerifyPanel(file_panel)
        self._verify_panel.busy_changed.connect(self.busy_changed)
        tabs.addTab(self._verify_panel, '核验')

        self._compare_panel = _ComparePanel(file_panel)
        self._compare_panel.busy_changed.connect(self.busy_changed)
        tabs.addTab(self._compare_panel, '对比')

        layout.addWidget(tabs)
