from pathlib import Path

import difflib
import html as _html_lib

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit,
    QRadioButton, QButtonGroup, QFileDialog,
    QSizePolicy, QFrame,
    QScrollArea, QSpinBox, QLayout, QSplitter,
)
from PySide6.QtCore import Qt, QThread, Signal, QSize, QEvent, QRect, QPoint, QTimer
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QIcon, QPainter, QColor, QPen
from app.ui.widgets.file_panel import LrmxFilePanel

from PySide6.QtCore import QSettings

from app.core.excel_handler import MatchMode
from app.core.verify_handler import (
    VerifyHandler, PersonResult, FieldResult,
    read_excel_headers, LRMX_FIELDS, DEFAULT_FIELD_ALIASES,
)

_ASSETS = Path(__file__).parent.parent / 'assets'

class _DiffPanel(QWidget):
    """Native-widget diff panel — replaces the HTML QTextEdit approach."""

    _DEL = 'background:#FDEAEA;color:#B02020;border-radius:2px;padding:0 2px'
    _INS = 'background:#E8F5EC;color:#1E7A3A;border-radius:2px;padding:0 2px'

    def __init__(self, result: PersonResult, parent=None):
        super().__init__(parent)
        self.setObjectName('diffPanel')
        self._build(result)

    def _build(self, result: PersonResult):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── table header ──────────────────────────────────────────────────
        hdr = QWidget()
        hdr.setObjectName('diffHeader')
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(10, 5, 10, 5)
        hl.setSpacing(0)
        for text, color, w in [('字段', '#888880', 150),
                                ('Excel 名册', '#2060A0', None),
                                ('任免表', '#1E7A3A', None)]:
            lbl = QLabel(text)
            lbl.setStyleSheet(f'color:{color};font-size:11px;font-weight:500;'
                              f'background:transparent;')
            if w:
                lbl.setFixedWidth(w)
            hl.addWidget(lbl, 0 if w else 1)
        outer.addWidget(hdr)

        hdr_sep = QFrame()
        hdr_sep.setFrameShape(QFrame.Shape.HLine)
        hdr_sep.setStyleSheet('color:#E8E4DE;')
        outer.addWidget(hdr_sep)

        # ── field rows ────────────────────────────────────────────────────
        for fr in result.fields:
            outer.addWidget(self._make_row(fr))
            row_sep = QFrame()
            row_sep.setFrameShape(QFrame.Shape.HLine)
            row_sep.setStyleSheet('color:#F0EDEA;')
            outer.addWidget(row_sep)

        # ── footer ────────────────────────────────────────────────────────
        ok_n  = sum(1 for f in result.fields if f.match)
        err_n = sum(1 for f in result.fields if not f.match)
        footer = QLabel(f'共核验 {len(result.fields)} 个字段 · 一致 {ok_n} · 差异 {err_n}')
        footer.setStyleSheet('color:#AAAAAA;font-size:10px;padding:4px 10px;'
                             'background:transparent;')
        outer.addWidget(footer)

    def _make_row(self, fr: FieldResult) -> QWidget:
        row = QWidget()
        if not fr.match:
            row.setStyleSheet('QWidget{background:#FFFAF8;}')
        rl = QHBoxLayout(row)
        rl.setContentsMargins(10, 5, 10, 5)
        rl.setSpacing(8)

        field_lbl = QLabel(fr.field)
        field_lbl.setFixedWidth(150)
        field_lbl.setWordWrap(True)
        field_lbl.setStyleSheet('color:#888880;font-size:11px;background:transparent;')
        rl.addWidget(field_lbl)

        if fr.match:
            val = _html_lib.escape(fr.lrmx_val or '', quote=False)
            same = QLabel(f'<span style="color:#AAAAAA;font-style:italic">'
                          f'{val}（一致）</span>')
            same.setTextFormat(Qt.TextFormat.RichText)
            same.setWordWrap(True)
            same.setStyleSheet('background:transparent;')
            rl.addWidget(same, 2)
        else:
            a_html, b_html = self._diff_inline(fr.excel_val, fr.lrmx_val)
            for html_str in (a_html, b_html):
                lbl = QLabel(html_str)
                lbl.setTextFormat(Qt.TextFormat.RichText)
                lbl.setWordWrap(True)
                lbl.setStyleSheet('font-size:12px;background:transparent;')
                rl.addWidget(lbl, 1)

        return row

    @classmethod
    def _diff_inline(cls, a: str, b: str) -> tuple[str, str]:
        m = difflib.SequenceMatcher(None, a, b, autojunk=False)
        ah, bh = [], []
        for tag, i1, i2, j1, j2 in m.get_opcodes():
            ea = _html_lib.escape(a[i1:i2], quote=False)
            eb = _html_lib.escape(b[j1:j2], quote=False)
            if tag == 'equal':
                ah.append(ea); bh.append(eb)
            elif tag == 'replace':
                ah.append(f'<span style="{cls._DEL}">{ea}</span>')
                bh.append(f'<span style="{cls._INS}">{eb}</span>')
            elif tag == 'delete':
                ah.append(f'<span style="{cls._DEL}">{ea}</span>')
            elif tag == 'insert':
                bh.append(f'<span style="{cls._INS}">{eb}</span>')
        return ''.join(ah), ''.join(bh)


# ── background workers ────────────────────────────────────────────────────────



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




# ── loading overlay ───────────────────────────────────────────────────────────

class _LoadingOverlay(QWidget):
    """Semi-transparent overlay shown while result layout is settling."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet('background: rgba(248, 245, 240, 220);')

        v = QVBoxLayout(self)
        v.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lbl = QLabel('核验中，请稍候…')
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet('color: #555555; font-size: 14px; background: transparent;')
        v.addWidget(lbl)

        self.hide()


# ── field mapping widgets ─────────────────────────────────────────────────────

class _FlowLayout(QLayout):
    """Left-to-right wrapping flow layout; hidden items are skipped."""

    def __init__(self, parent=None, h_spacing: int = 6, v_spacing: int = 6):
        super().__init__(parent)
        self._h = h_spacing
        self._v = v_spacing
        self._items: list = []

    def addItem(self, item):
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, w: int) -> int:
        return self._arrange(QRect(0, 0, w, 0), dry=True)

    def setGeometry(self, rect: QRect):
        super().setGeometry(rect)
        self._arrange(rect, dry=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        sz = QSize()
        for item in self._items:
            sz = sz.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        return sz + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _arrange(self, rect: QRect, dry: bool) -> int:
        m = self.contentsMargins()
        r = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x, y, row_h = r.x(), r.y(), 0
        for item in self._items:
            w = item.widget()
            if w is None or not w.isVisible():
                continue
            hint = item.sizeHint()
            nx = x + hint.width() + self._h
            if nx - self._h > r.right() and row_h > 0:
                x = r.x()
                y += row_h + self._v
                nx = x + hint.width() + self._h
                row_h = 0
            if not dry:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = nx
            row_h = max(row_h, hint.height())
        return y + row_h - rect.y() + m.bottom()


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

    def __init__(self, tag: str, display: str, parent=None):
        super().__init__(parent)
        self._field = tag
        self.setObjectName('fieldRow')
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(6)

        name_lbl = QLabel(display)
        name_lbl.setObjectName('fieldRowName')
        name_lbl.setFixedWidth(180)
        layout.addWidget(name_lbl)

        self._map_lbl = QLabel('未匹配')
        self._map_lbl.setObjectName('fieldRowUnmapped')
        self._map_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
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

        # ── Left panel — Excel header tags (flow layout, equal width) ──────
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 10, 0)
        lv.setSpacing(4)

        left_title = QLabel('Excel 表头  （点击选中）')
        left_title.setObjectName('sectionTitle')
        lv.addWidget(left_title)

        # Tags container uses flow layout; placed inside a vertical-only scroll area
        self._tags_container = QWidget()
        self._flow_layout = _FlowLayout(self._tags_container, h_spacing=6, v_spacing=6)
        self._flow_layout.setContentsMargins(2, 4, 2, 4)

        tags_scroll = QScrollArea()
        tags_scroll.setObjectName('tagsScroll')
        tags_scroll.setWidgetResizable(True)
        tags_scroll.setWidget(self._tags_container)
        tags_scroll.setFrameShape(QFrame.Shape.NoFrame)
        tags_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        tags_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        lv.addWidget(tags_scroll, 1)

        outer.addWidget(left, 1)  # equal stretch

        # ── Separator ──────────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        outer.addWidget(sep)

        # ── Right panel — lrmx field rows ──────────────────────────────────
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(10, 0, 0, 0)
        rv.setSpacing(4)

        right_title = QLabel('任免表字段  （点击接收匹配）')
        right_title.setObjectName('sectionTitle')
        rv.addWidget(right_title)

        self._fields_scroll = QScrollArea()
        self._fields_scroll.setWidgetResizable(True)
        self._fields_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._fields_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._fields_container = QWidget()
        self._fields_vbox = QVBoxLayout(self._fields_container)
        self._fields_vbox.setContentsMargins(0, 0, 0, 0)
        self._fields_vbox.setSpacing(2)
        self._fields_vbox.addStretch()
        self._fields_scroll.setWidget(self._fields_container)
        rv.addWidget(self._fields_scroll, 1)

        outer.addWidget(right, 1)  # equal stretch

    def load_excel_cols(self, cols: list[str]):
        while self._flow_layout.count():
            item = self._flow_layout.takeAt(0)
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
            self._flow_layout.addWidget(tag)

        self._tags_container.updateGeometry()

        for fr in self._field_rows.values():
            fr.set_mapped(None)
            fr.set_pending(False)

        self.mapping_changed.emit()

    def load_lrmx_fields(self, fields: list[tuple[str, str]]):
        while self._fields_vbox.count():
            item = self._fields_vbox.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._field_rows.clear()
        self._mapping.clear()
        self._reverse.clear()
        self._selected_col = None

        for tag, display in fields:
            row = _FieldRow(tag, display)
            row.clicked_field.connect(self._on_field_clicked)
            row.remove_mapping.connect(self._remove_mapping)
            self._field_rows[tag] = row
            self._fields_vbox.addWidget(row)
        self._fields_vbox.addStretch()

        self.mapping_changed.emit()

    def apply_presets(self, presets: dict[str, list[str]]):
        """Auto-map excel cols to lrmx fields using alias presets.
        Only maps where both sides are currently unmapped."""
        col_set = set(self._tags.keys())
        for lrmx_tag, aliases in presets.items():
            if lrmx_tag in self._reverse:
                continue
            if lrmx_tag not in self._field_rows:
                continue
            for alias in aliases:
                alias = alias.strip()
                if alias in col_set and alias not in self._mapping:
                    self._mapping[alias] = lrmx_tag
                    self._reverse[lrmx_tag] = alias
                    self._tags[alias].hide()
                    self._field_rows[lrmx_tag].set_mapped(alias)
                    break
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
    def __init__(self, result: PersonResult, parent=None):
        super().__init__(parent)
        self._result = result
        self._expanded = False
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
        hl.setContentsMargins(10, 7, 10, 7)
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
            badge_text, color = '一致', '#1E7A3A'
        elif status == 'diff':
            n_diff = sum(1 for f in self._result.fields if not f.match)
            badge_text, color = f'{n_diff} 处差异', '#B02020'
        elif status == 'not_found':
            badge_text, color = '名册无此人', '#C07030'
        else:
            badge_text, color = '错误', '#888880'

        badge = QLabel(badge_text)
        badge.setStyleSheet(f'color:{color};font-size:11px;font-weight:600;')
        hl.addWidget(badge)

        outer.addWidget(self._header)

        # Diff panel (native widgets — auto-sizes, no HTML QTextEdit)
        self._diff_panel = _DiffPanel(self._result)
        self._diff_panel.hide()
        outer.addWidget(self._diff_panel)

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
        self._diff_panel.setVisible(self._expanded)


# ── main tab ──────────────────────────────────────────────────────────────────

class VerifyTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._settings = QSettings('rmb_helper', 'rmb_helper')
        self._counts = {'ok': 0, 'diff': 0, 'not_found': 0, 'error': 0}
        self._active_filter: str | None = None
        self._result_rows: list[_ResultRow] = []
        self._build_ui()
        self.setAcceptDrops(True)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        # ══════════════════════════════════════════════════════════════════════
        # 设置面板（核验开始后隐藏）
        # ══════════════════════════════════════════════════════════════════════
        self._setup_panel = QWidget()
        sp = QVBoxLayout(self._setup_panel)
        sp.setContentsMargins(0, 0, 0, 0)
        sp.setSpacing(12)

        title = QLabel('批量核验')
        title.setObjectName('sectionTitle')
        sp.addWidget(title)

        sub = QLabel('对照干部名册（Excel），核验任免审批表中的字段是否一致')
        sub.setStyleSheet('color: #888880; font-size: 12px;')
        sp.addWidget(sub)

        # ── 分割器：上方文件面板 / 下方控件 ──────────────────────────────
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        sp.addWidget(splitter, 1)

        self._file_panel = LrmxFilePanel()
        splitter.addWidget(self._file_panel)
        self._file_panel.files_changed.connect(self._on_files_changed)

        bottom_pane = QWidget()
        bot_layout = QVBoxLayout(bottom_pane)
        bot_layout.setContentsMargins(0, 0, 0, 0)
        bot_layout.setSpacing(12)
        splitter.addWidget(bottom_pane)

        splitter.setSizes([140, 400])
        splitter.setHandleWidth(4)

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
        self._run_btn = QPushButton('开始核验')
        self._run_btn.setObjectName('primary')
        self._run_btn.setEnabled(False)
        self._run_btn.clicked.connect(self._run)
        run_row.addWidget(self._run_btn)
        bot_layout.addLayout(run_row)

        layout.addWidget(self._setup_panel, 1)

        # ══════════════════════════════════════════════════════════════════════
        # 配置摘要栏（核验开始后显示，替代设置面板）
        # ══════════════════════════════════════════════════════════════════════
        self._summary_bar = QWidget()
        self._summary_bar.setObjectName('summaryBar')
        self._summary_bar.hide()
        sb = QHBoxLayout(self._summary_bar)
        sb.setContentsMargins(0, 0, 0, 0)
        sb.setSpacing(12)

        back_btn = QPushButton('← 重新配置')
        back_btn.setFixedHeight(28)
        back_btn.clicked.connect(self._back_to_setup)
        sb.addWidget(back_btn)

        sep_v = QFrame()
        sep_v.setFrameShape(QFrame.Shape.VLine)
        sep_v.setFixedHeight(18)
        sb.addWidget(sep_v, 0, Qt.AlignmentFlag.AlignVCenter)

        self._summary_lbl = QLabel()
        self._summary_lbl.setStyleSheet('color: #888880; font-size: 12px;')
        sb.addWidget(self._summary_lbl, 1)

        layout.addWidget(self._summary_bar)

        sep_result = QFrame()
        sep_result.setFrameShape(QFrame.Shape.HLine)
        sep_result.setObjectName('resultTopSep')
        sep_result.hide()
        self._result_top_sep = sep_result
        layout.addWidget(sep_result)

        # ══════════════════════════════════════════════════════════════════════
        # 汇总卡片 + 结果滚动区（始终存在，核验前空白）
        # ══════════════════════════════════════════════════════════════════════
        summary_row = QHBoxLayout()
        summary_row.setSpacing(12)
        self._count_labels: dict[str, QLabel] = {}
        self._card_widgets: dict[str, QWidget] = {}
        cards = [
            ('ok',        '0', '一致'),
            ('diff',      '0', '有差异'),
            ('not_found', '0', '名册无此人'),
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
        self._summary_cards_row = summary_row
        self._summary_cards_widget = QWidget()
        self._summary_cards_widget.setLayout(summary_row)
        self._summary_cards_widget.hide()
        layout.addWidget(self._summary_cards_widget)

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
        layout.addWidget(result_scroll, 1)

        self._loading_overlay = _LoadingOverlay(self._result_scroll)
        self._result_scroll.installEventFilter(self)

        # Load fixed field list — all widgets now exist
        self._mapping_widget.load_lrmx_fields(LRMX_FIELDS)

    # ── event filter (overlay resize) ────────────────────────────────────────

    def eventFilter(self, obj, event):
        if obj is self._result_scroll and event.type() == QEvent.Type.Resize:
            self._loading_overlay.resize(self._result_scroll.size())
        return super().eventFilter(obj, event)

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
        )

        self._clear_results()

        # 切换到结果视图
        xl_name = Path(excel_path).name
        n_files = len(files)
        n_mapped = len(mapping)
        self._summary_lbl.setText(
            f'{n_files} 个任免表  ·  名册：{xl_name}  ·  已匹配 {n_mapped} 个字段'
        )
        self._setup_panel.hide()
        self._summary_bar.show()
        self._result_top_sep.show()
        self._summary_cards_widget.show()
        self._result_scroll.show()

        self._loading_overlay.resize(self._result_scroll.size())
        self._loading_overlay.raise_()
        self._loading_overlay.show()

        self._worker = _VerifyWorker(handler)
        self._worker.result_ready.connect(self._on_result)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _back_to_setup(self):
        self._loading_overlay.hide()
        self._setup_panel.show()
        self._summary_bar.hide()
        self._result_top_sep.hide()
        self._summary_cards_widget.hide()
        self._result_scroll.hide()
        self._clear_results()

    def _on_result(self, result: PersonResult):
        status = result.status if result.status in self._counts else 'error'
        self._counts[status] += 1
        self._count_labels[status].setText(str(self._counts[status]))

        row_widget = _ResultRow(result)
        self._result_rows.append(row_widget)
        idx = self._result_vbox.count() - 1
        self._result_vbox.insertWidget(idx, row_widget)

    def _on_finished(self):
        QTimer.singleShot(400, self._loading_overlay.hide)

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

        # Show overlay first so it paints before the row show/hide triggers layout
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
        QTimer.singleShot(300, self._loading_overlay.hide)

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

    # ── drag & drop ───────────────────────────────────────────────────────────

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith('.lrmx'):
                self._file_panel.add_file(path)
