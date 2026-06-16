from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListWidget, QListWidgetItem, QLineEdit,
    QRadioButton, QButtonGroup, QTextEdit, QFileDialog,
    QSizePolicy, QMenu, QDialog, QProgressBar, QFrame,
    QScrollArea, QSpinBox,
)
from PySide6.QtCore import Qt, QThread, Signal, QSize, QEvent, QTimer
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QIcon, QPainter, QColor, QPen

from app.core.excel_handler import MatchMode
from app.core.verify_handler import (
    VerifyHandler, PersonResult, read_excel_headers, get_lrmx_fields, char_diff_html,
)

_ASSETS = Path(__file__).parent.parent / 'assets'

_DIFF_STYLE = """
<style>
  body { font-family: "Microsoft YaHei", "PingFang SC", monospace; font-size: 12px; }
  table { border-collapse: collapse; width: 100%; }
  th { font-size: 11px; color: #666; text-align: left; padding: 4px 8px;
       border-bottom: 1px solid #2a2a2a; background: #111; }
  td { padding: 5px 8px; border-bottom: 1px solid #1e1e1e;
       vertical-align: middle; word-break: break-all; }
  .field { color: #557799; width: 160px; font-size: 11px; }
  .eq    { color: #aaa; }
  .del   { background: #4a1515; color: #ff9090; border-radius: 2px; padding: 0 1px; }
  .ins   { background: #124020; color: #80e0a0; border-radius: 2px; padding: 0 1px; }
  .same  { color: #3a5a3a; font-style: italic; font-size: 10px; }
  tr.diff-row td { background: #111820; }
  .footer { font-size: 10px; color: #555; padding: 4px 8px; }
</style>
"""


def _build_detail_html(result: PersonResult, field_mapping: dict[str, str]) -> str:
    import html as _html_mod
    rows_html = []
    for fr in result.fields:
        if fr.match:
            val = _html_mod.escape(fr.lrmx_val, quote=False)
            rows_html.append(
                f'<tr><td class="field">{fr.field}</td>'
                f'<td colspan="2"><span class="same">{val}（一致）</span></td></tr>'
            )
        else:
            a_html, b_html = char_diff_html(fr.excel_val, fr.lrmx_val)
            rows_html.append(
                f'<tr class="diff-row"><td class="field">{fr.field}</td>'
                f'<td>{a_html}</td><td>{b_html}</td></tr>'
            )
    ok_count  = sum(1 for f in result.fields if f.match)
    err_count = sum(1 for f in result.fields if not f.match)
    body = '\n'.join(rows_html)
    footer = f'共核验 {len(result.fields)} 个字段 · 一致 {ok_count} · 差异 {err_count}'
    return (
        f'{_DIFF_STYLE}'
        f'<table><thead><tr><th>字段</th>'
        f'<th style="color:#5588bb">Excel 名册</th>'
        f'<th style="color:#558855">任免表</th></tr></thead>'
        f'<tbody>{body}</tbody></table>'
        f'<div class="footer">{footer}</div>'
    )


# ── background workers ────────────────────────────────────────────────────────

class _FolderScanWorker(QThread):
    done = Signal(list)

    def __init__(self, folder: str, parent=None):
        super().__init__(parent)
        self._folder = folder

    def run(self):
        paths = sorted(str(p) for p in Path(self._folder).rglob('*.lrmx'))
        self.done.emit(paths)


class _VerifyWorker(QThread):
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


# ── shared list widgets ───────────────────────────────────────────────────────

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


# ── field mapping widgets ─────────────────────────────────────────────────────

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


class _FieldRow(QWidget):
    clicked_field = Signal(str)
    remove_mapping = Signal(str)

    def __init__(self, field: str, parent=None):
        super().__init__(parent)
        self._field = field
        self.setObjectName('fieldRow')
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(6)

        name_lbl = QLabel(field)
        name_lbl.setObjectName('fieldRowName')
        name_lbl.setFixedWidth(180)
        layout.addWidget(name_lbl)

        self._map_lbl = QLabel('未匹配')
        self._map_lbl.setObjectName('fieldRowUnmapped')
        self._map_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(self._map_lbl, 1)

        self._remove_btn = QPushButton('✕')
        self._remove_btn.setObjectName('fileItemRemove')
        self._remove_btn.setFixedSize(20, 20)
        self._remove_btn.hide()
        self._remove_btn.clicked.connect(lambda: self.remove_mapping.emit(self._field))
        layout.addWidget(self._remove_btn)

    def set_mapped(self, excel_col: str | None):
        if excel_col:
            self._map_lbl.setText(excel_col)
            self._map_lbl.setObjectName('fieldRowMapped')
            self._remove_btn.show()
        else:
            self._map_lbl.setText('未匹配')
            self._map_lbl.setObjectName('fieldRowUnmapped')
            self._remove_btn.hide()
        self._map_lbl.style().unpolish(self._map_lbl)
        self._map_lbl.style().polish(self._map_lbl)

    def set_pending(self, pending: bool):
        self.setProperty('pending', pending)
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked_field.emit(self._field)
        super().mousePressEvent(event)


class _MappingWidget(QWidget):
    mapping_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._selected_col: str | None = None
        self._mapping: dict[str, str] = {}
        self._reverse: dict[str, str] = {}
        self._tags: dict[str, _MatchTag] = {}
        self._field_rows: dict[str, _FieldRow] = {}
        self._build_ui()

    def _build_ui(self):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Left panel
        left = QWidget()
        left.setFixedWidth(200)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 8, 0)
        lv.setSpacing(4)

        left_title = QLabel('Excel 表头')
        left_title.setObjectName('sectionTitle')
        lv.addWidget(left_title)

        self._tags_row = QHBoxLayout()
        self._tags_row.setContentsMargins(0, 0, 0, 0)
        self._tags_row.setSpacing(4)
        self._tags_scroll_widget = QWidget()
        self._tags_scroll_widget.setLayout(self._tags_row)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._tags_scroll_widget)
        scroll.setMaximumHeight(60)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        lv.addWidget(scroll)
        lv.addStretch()

        outer.addWidget(left)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        outer.addWidget(sep)

        # Right panel
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(8, 0, 0, 0)
        rv.setSpacing(2)

        right_title = QLabel('任免表字段')
        right_title.setObjectName('sectionTitle')
        rv.addWidget(right_title)

        self._fields_scroll = QScrollArea()
        self._fields_scroll.setWidgetResizable(True)
        self._fields_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._fields_container = QWidget()
        self._fields_vbox = QVBoxLayout(self._fields_container)
        self._fields_vbox.setContentsMargins(0, 0, 0, 0)
        self._fields_vbox.setSpacing(0)
        self._fields_vbox.addStretch()
        self._fields_scroll.setWidget(self._fields_container)
        rv.addWidget(self._fields_scroll, 1)

        outer.addWidget(right, 1)

    def load_excel_cols(self, cols: list[str]):
        # Clear old tags
        while self._tags_row.count():
            item = self._tags_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._tags.clear()
        self._mapping.clear()
        self._reverse.clear()
        self._selected_col = None

        for col in cols:
            if not col or not col.strip():
                continue
            tag = _MatchTag(col)
            tag.clicked_tag.connect(self._on_tag_clicked)
            self._tags[col] = tag
            self._tags_row.addWidget(tag)
        self._tags_row.addStretch()

        for fr in self._field_rows.values():
            fr.set_mapped(None)
            fr.set_pending(False)

        self.mapping_changed.emit()

    def load_lrmx_fields(self, fields: list[str]):
        # Clear old field rows
        while self._fields_vbox.count():
            item = self._fields_vbox.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._field_rows.clear()
        self._mapping.clear()
        self._reverse.clear()
        self._selected_col = None

        for f in fields:
            row = _FieldRow(f)
            row.clicked_field.connect(self._on_field_clicked)
            row.remove_mapping.connect(self._remove_mapping)
            self._field_rows[f] = row
            self._fields_vbox.addWidget(row)
        self._fields_vbox.addStretch()

        self.mapping_changed.emit()

    def _on_tag_clicked(self, col: str):
        if col in self._mapping:
            return
        if self._selected_col == col:
            # Deselect
            self._tags[col].set_selected(False)
            self._selected_col = None
            self._clear_pending()
        else:
            if self._selected_col and self._selected_col in self._tags:
                self._tags[self._selected_col].set_selected(False)
            self._selected_col = col
            self._tags[col].set_selected(True)
            self._update_pending()

    def _on_field_clicked(self, lrmx_field: str):
        if not self._selected_col:
            return
        if lrmx_field in self._reverse:
            return
        col = self._selected_col
        self._mapping[col] = lrmx_field
        self._reverse[lrmx_field] = col
        self._tags[col].hide()
        self._field_rows[lrmx_field].set_mapped(col)
        self._selected_col = None
        self._tags[col].set_selected(False)
        self._clear_pending()
        self.mapping_changed.emit()

    def _remove_mapping(self, lrmx_field: str):
        if lrmx_field not in self._reverse:
            return
        col = self._reverse.pop(lrmx_field)
        self._mapping.pop(col, None)
        if col in self._tags:
            self._tags[col].show()
            self._tags[col].set_selected(False)
        self._field_rows[lrmx_field].set_mapped(None)
        self.mapping_changed.emit()

    def _update_pending(self):
        for field, row in self._field_rows.items():
            if field not in self._reverse:
                row.set_pending(True)

    def _clear_pending(self):
        for row in self._field_rows.values():
            row.set_pending(False)

    def get_mapping(self) -> dict[str, str]:
        return dict(self._mapping)

    def clear_all(self):
        for lrmx_field in list(self._reverse.keys()):
            self._remove_mapping(lrmx_field)
        self._selected_col = None


# ── result widgets ────────────────────────────────────────────────────────────

class _ResultRow(QWidget):
    def __init__(self, result: PersonResult, field_mapping: dict[str, str], parent=None):
        super().__init__(parent)
        self._result = result
        self._field_mapping = field_mapping
        self._expanded = False
        self._html_loaded = False
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Header
        self._header = QWidget()
        self._header.setObjectName('resultRowHeader')
        self._header.setCursor(Qt.CursorShape.PointingHandCursor)
        hl = QHBoxLayout(self._header)
        hl.setContentsMargins(10, 6, 10, 6)
        hl.setSpacing(6)

        self._arrow = QLabel('▶')
        self._arrow.setObjectName('resultArrow')
        self._arrow.setFixedWidth(12)
        hl.addWidget(self._arrow)

        name_lbl = QLabel(self._result.name or self._result.lrmx_path)
        name_lbl.setObjectName('resultName')
        hl.addWidget(name_lbl)
        hl.addStretch()

        status = self._result.status
        if status == 'ok':
            badge_text = '一致'
            color = '#5db880'
        elif status == 'diff':
            n_diff = sum(1 for f in self._result.fields if not f.match)
            badge_text = f'{n_diff} 处差异'
            color = '#e06060'
        elif status == 'not_found':
            badge_text = '名册无此人'
            color = '#d4a55a'
        else:
            badge_text = '错误'
            color = '#888'

        badge = QLabel(badge_text)
        badge.setStyleSheet(f'color: {color}; font-size: 11px; font-weight: 600;')
        hl.addWidget(badge)

        outer.addWidget(self._header)

        self._detail = QTextEdit()
        self._detail.setObjectName('diffDetail')
        self._detail.setReadOnly(True)
        self._detail.hide()
        outer.addWidget(self._detail)

        sep = QFrame()
        sep.setObjectName('resultSep')
        sep.setFrameShape(QFrame.Shape.HLine)
        outer.addWidget(sep)

        if status not in ('not_found', 'error'):
            self._header.mousePressEvent = self._toggle

    def _toggle(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._expanded = not self._expanded
        self._arrow.setText('▼' if self._expanded else '▶')
        if self._expanded and not self._html_loaded:
            self._detail.setHtml(_build_detail_html(self._result, self._field_mapping))
            self._html_loaded = True
            doc_h = int(self._detail.document().size().height()) + 16
            self._detail.setFixedHeight(max(80, min(400, doc_h)))
        self._detail.setVisible(self._expanded)


# ── main tab ──────────────────────────────────────────────────────────────────

class VerifyTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._scan_worker = None
        self._counts = {'ok': 0, 'diff': 0, 'not_found': 0, 'error': 0}
        self._build_ui()
        self.setAcceptDrops(True)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        title = QLabel('批量核验')
        title.setObjectName('sectionTitle')
        layout.addWidget(title)

        sub = QLabel('对照干部名册（Excel），核验任免审批表中的字段是否一致')
        sub.setStyleSheet('color: #888880; font-size: 12px;')
        layout.addWidget(sub)

        # ── lrmx 文件列表 ───────────────────────────────────────────────────────
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
        self._file_list.setMinimumHeight(80)
        self._file_list.setMaximumHeight(140)
        self._file_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self._file_list.empty_clicked.connect(lambda: add_menu.exec(
            add_btn.mapToGlobal(add_btn.rect().bottomLeft())
        ))
        layout.addWidget(self._file_list)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep1)

        # ── Excel 文件 ─────────────────────────────────────────────────────────
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
        layout.addLayout(xl_row)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep2)

        # ── 字段匹配 ───────────────────────────────────────────────────────────
        map_title = QLabel('字段匹配')
        map_title.setObjectName('sectionTitle')
        layout.addWidget(map_title)

        map_sub = QLabel('点击左侧 Excel 表头选中 → 点击右侧字段完成匹配')
        map_sub.setStyleSheet('color: #888880; font-size: 12px;')
        layout.addWidget(map_sub)

        self._mapping_widget = _MappingWidget()
        self._mapping_widget.mapping_changed.connect(self._update_run_btn)
        layout.addWidget(self._mapping_widget)

        clear_map_row = QHBoxLayout()
        clear_map_row.addStretch()
        clear_map_btn = QPushButton('清除全部匹配')
        clear_map_btn.setFixedHeight(24)
        clear_map_btn.clicked.connect(self._mapping_widget.clear_all)
        clear_map_row.addWidget(clear_map_btn)
        layout.addLayout(clear_map_row)

        sep3 = QFrame()
        sep3.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep3)

        # ── 匹配依据 + 开始按钮 ────────────────────────────────────────────────
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
        layout.addLayout(run_row)

        # ── 汇总卡片 ───────────────────────────────────────────────────────────
        summary_row = QHBoxLayout()
        summary_row.setSpacing(12)
        self._count_labels: dict[str, QLabel] = {}
        cards = [
            ('ok',        '0', '一致'),
            ('diff',      '0', '有差异'),
            ('not_found', '0', '名册无此人'),
            ('error',     '0', '错误'),
        ]
        for key, count, desc in cards:
            card = QWidget()
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
            summary_row.addWidget(card)
        summary_row.addStretch()
        layout.addLayout(summary_row)

        # ── 结果滚动区 ─────────────────────────────────────────────────────────
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
        layout.addWidget(result_scroll, 1)

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
        if self._file_list.count() == 1:
            self._load_lrmx_fields(path)
        self._update_run_btn()

    def _load_lrmx_fields(self, path: str):
        try:
            fields = get_lrmx_fields(Path(path))
            self._mapping_widget.load_lrmx_fields(fields)
        except Exception:
            pass

    def _remove_item(self, item: QListWidgetItem):
        self._file_list.takeItem(self._file_list.row(item))
        self._update_run_btn()

    def _remove_selected(self):
        for item in self._file_list.selectedItems():
            self._file_list.takeItem(self._file_list.row(item))
        self._update_run_btn()

    def _clear_files(self):
        self._file_list.clear()
        self._update_run_btn()

    def _pick_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, '选择 lrmx 文件', '', '任免审批表 (*.lrmx)'
        )
        for p in paths:
            self._add_file(p)

    def _pick_folder(self):
        folder = QFileDialog.getExistingDirectory(self, '选择包含 lrmx 文件的文件夹')
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

    def _files(self) -> list[str]:
        return [
            self._file_list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self._file_list.count())
        ]

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
        except Exception:
            pass
        self._update_run_btn()

    # ── run button state ──────────────────────────────────────────────────────

    def _update_run_btn(self):
        has_files = self._file_list.count() > 0
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
        self._run_btn.setEnabled(has_files and has_excel and has_mapping and key_ok)
        if has_mapping and not key_ok:
            self._run_btn.setToolTip('请将匹配依据对应的字段（身份证/姓名）映射到某个 Excel 列')
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

    # ── verify ────────────────────────────────────────────────────────────────

    def _run(self):
        files = self._files()
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
        )

        self._clear_results()
        self._run_btn.setEnabled(False)

        self._worker = _VerifyWorker(handler)
        self._worker.result_ready.connect(self._on_result)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _on_result(self, result: PersonResult):
        status = result.status if result.status in self._counts else 'error'
        self._counts[status] += 1
        self._count_labels[status].setText(str(self._counts[status]))

        row_widget = _ResultRow(result, self._mapping_widget.get_mapping())
        idx = self._result_vbox.count() - 1
        self._result_vbox.insertWidget(idx, row_widget)

    def _on_finished(self):
        self._run_btn.setEnabled(True)

    def _clear_results(self):
        self._counts = {'ok': 0, 'diff': 0, 'not_found': 0, 'error': 0}
        for key, lbl in self._count_labels.items():
            lbl.setText('0')
        while self._result_vbox.count() > 1:
            item = self._result_vbox.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    # ── drag & drop ───────────────────────────────────────────────────────────

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith('.lrmx'):
                self._add_file(path)
