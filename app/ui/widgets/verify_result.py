import difflib
import html as _html_lib

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
)
from PySide6.QtCore import Qt

from app.core.verify_handler import PersonResult, FieldResult


class _DiffPanel(QWidget):
    """Native-widget diff panel — replaces the HTML QTextEdit approach."""

    _DEL = 'background:#FDEAEA;color:#B02020;border-radius:2px;padding:0 2px'
    _INS = 'background:#E8F5EC;color:#1E7A3A;border-radius:2px;padding:0 2px'

    def __init__(self, result: PersonResult, parent=None,
                 col_a_label: str = 'Excel 名册', col_b_label: str = '任免表',
                 footer_prefix: str = '共核验'):
        super().__init__(parent)
        self.setObjectName('diffPanel')
        self._col_a = col_a_label
        self._col_b = col_b_label
        self._footer_prefix = footer_prefix
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
                                (self._col_a, '#2060A0', None),
                                (self._col_b, '#1E7A3A', None)]:
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
        footer = QLabel(f'{self._footer_prefix} {len(result.fields)} 个字段 · 一致 {ok_n} · 差异 {err_n}')
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


class _ResultRow(QWidget):
    def __init__(self, result: PersonResult, parent=None,
                 col_a_label: str = 'Excel 名册', col_b_label: str = '任免表',
                 footer_prefix: str = '共核验',
                 not_found_text: str = '名册无此人'):
        super().__init__(parent)
        self._result = result
        self._expanded = False
        self._col_a = col_a_label
        self._col_b = col_b_label
        self._footer_prefix = footer_prefix
        self._not_found_text = not_found_text
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
            badge_text, color = self._not_found_text, '#C07030'
        else:
            badge_text, color = '错误', '#888880'

        badge = QLabel(badge_text)
        badge.setStyleSheet(f'color:{color};font-size:11px;font-weight:600;')
        hl.addWidget(badge)

        outer.addWidget(self._header)

        # Diff panel (native widgets — auto-sizes, no HTML QTextEdit)
        self._diff_panel = _DiffPanel(self._result,
                                      col_a_label=self._col_a,
                                      col_b_label=self._col_b,
                                      footer_prefix=self._footer_prefix)
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
