# 批量核验 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a 批量核验 tab that lets users select an Excel roster and a batch of .lrmx files, define field mappings, run verification, and view character-level diff results per person.

**Architecture:** Core logic lives in `app/core/verify_handler.py` (Excel header reading, person matching, field comparison with `difflib`). The UI tab `app/ui/tabs/verify_tab.py` follows the same file-list pattern as UpdateTab plus a click-to-match field mapping widget and an expandable result list. The tab is wired into `MainWindow` alongside the existing three tabs.

**Tech Stack:** PySide6 (UI), openpyxl (Excel), difflib (character diff), re (invisible-char stripping) — all already in the project.

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `app/core/verify_handler.py` | **Create** | Data classes, Excel header reader, field comparator, VerifyHandler |
| `app/ui/tabs/verify_tab.py` | **Create** | Full UI for the verify tab |
| `app/ui/main_window.py` | **Modify** | Add nav button + VerifyTab to stack |
| `tests/test_verify_handler.py` | **Create** | Unit tests for core logic |

---

### Task 1: `verify_handler.py` — core logic

**Files:**
- Create: `app/core/verify_handler.py`
- Test: `tests/test_verify_handler.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_verify_handler.py
import openpyxl
import pytest
from pathlib import Path
from app.core.verify_handler import (
    read_excel_headers,
    get_lrmx_fields,
    _strip,
    char_diff_html,
    VerifyHandler,
    PersonResult,
    FieldResult,
)
from app.core.excel_handler import MatchMode


def make_excel(path: Path, rows: list[dict], header_row: int = 1) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    # pad blank rows before header
    for _ in range(header_row - 1):
        ws.append([])
    headers = list(rows[0].keys())
    ws.append(headers)
    for row in rows:
        ws.append([row[h] for h in headers])
    wb.save(path)
    return path


# ── _strip ────────────────────────────────────────────────────────────────────

def test_strip_removes_whitespace():
    assert _strip('张 三') == '张三'

def test_strip_removes_zero_width():
    assert _strip('张​三') == '张三'

def test_strip_removes_newline():
    assert _strip('张\n三') == '张三'


# ── read_excel_headers ────────────────────────────────────────────────────────

def test_read_excel_headers_default_row1(tmp_path):
    make_excel(tmp_path / 'x.xlsx', [{'姓名': '张三', '性别': '男'}])
    headers = read_excel_headers(tmp_path / 'x.xlsx', header_row=1)
    assert headers == ['姓名', '性别']

def test_read_excel_headers_custom_row(tmp_path):
    # header on row 3
    make_excel(tmp_path / 'x.xlsx', [{'身份证': 'abc', '民族': '汉族'}], header_row=3)
    headers = read_excel_headers(tmp_path / 'x.xlsx', header_row=3)
    assert headers == ['身份证', '民族']


# ── get_lrmx_fields ───────────────────────────────────────────────────────────

def test_get_lrmx_fields_excludes_version(sample_lrmx, tmp_path):
    # inject a version element
    from app.core.lrmx import LrmxFile
    lf = LrmxFile(sample_lrmx)
    lf.set('version', '2')
    lf.save()
    fields = get_lrmx_fields(sample_lrmx)
    assert 'version' not in fields

def test_get_lrmx_fields_returns_all_direct_children(sample_lrmx):
    fields = get_lrmx_fields(sample_lrmx)
    assert 'XingMing' in fields
    assert 'ShenFenZheng' in fields

def test_get_lrmx_fields_excludes_nested_containers(sample_lrmx):
    # JiaTingChengYuan is a container, its children should NOT appear flat
    fields = get_lrmx_fields(sample_lrmx)
    # The tag itself may appear but its sub-items should not
    assert 'ChengWei' not in fields
    assert 'GongZuoDanWeiJiZhiWu' not in fields


# ── char_diff_html ────────────────────────────────────────────────────────────

def test_char_diff_html_equal():
    a_html, b_html = char_diff_html('张三', '张三')
    # no span tags for equal content
    assert '<span' not in a_html
    assert '<span' not in b_html
    assert '张三' in a_html

def test_char_diff_html_replace():
    a_html, b_html = char_diff_html('男', '女')
    assert 'del' in a_html or 'background' in a_html
    assert 'ins' in b_html or 'background' in b_html

def test_char_diff_html_partial():
    a_html, b_html = char_diff_html('硕士研究生', '硕士生')
    # '硕士' and '生' are equal; '研究' is extra in a
    assert '硕士' in a_html
    assert '研究' in a_html


# ── VerifyHandler ─────────────────────────────────────────────────────────────

def test_verify_match_by_id(sample_lrmx, tmp_path):
    excel = make_excel(tmp_path / 'd.xlsx', [
        {'身份证': '110101199001011234', '性别': '男'},
    ])
    handler = VerifyHandler(
        excel_path=excel,
        lrmx_files=[sample_lrmx],
        match_mode=MatchMode.ID_CARD,
        header_row=1,
        field_mapping={'身份证': 'ShenFenZheng', '性别': 'XingBie'},
        match_excel_col_for_id='身份证',
        match_excel_col_for_name=None,
    )
    results = handler.verify()
    assert len(results) == 1
    r = results[0]
    assert r.status == 'ok'
    assert all(f.match for f in r.fields)

def test_verify_detects_diff(sample_lrmx, tmp_path):
    excel = make_excel(tmp_path / 'd.xlsx', [
        {'身份证': '110101199001011234', '性别': '女'},
    ])
    handler = VerifyHandler(
        excel_path=excel,
        lrmx_files=[sample_lrmx],
        match_mode=MatchMode.ID_CARD,
        header_row=1,
        field_mapping={'身份证': 'ShenFenZheng', '性别': 'XingBie'},
        match_excel_col_for_id='身份证',
        match_excel_col_for_name=None,
    )
    results = handler.verify()
    r = results[0]
    assert r.status == 'diff'
    diff_fields = [f for f in r.fields if not f.match]
    assert len(diff_fields) == 1
    assert diff_fields[0].field == 'XingBie'

def test_verify_not_found(sample_lrmx, tmp_path):
    excel = make_excel(tmp_path / 'd.xlsx', [
        {'身份证': '000000000000000000', '性别': '男'},
    ])
    handler = VerifyHandler(
        excel_path=excel,
        lrmx_files=[sample_lrmx],
        match_mode=MatchMode.ID_CARD,
        header_row=1,
        field_mapping={'身份证': 'ShenFenZheng', '性别': 'XingBie'},
        match_excel_col_for_id='身份证',
        match_excel_col_for_name=None,
    )
    results = handler.verify()
    # The lrmx person was not in Excel
    assert results[0].status == 'not_found'

def test_verify_strips_invisible(sample_lrmx, tmp_path):
    # Excel value has a zero-width space, lrmx has plain text → should still match
    excel = make_excel(tmp_path / 'd.xlsx', [
        {'身份证': '110101199001011234', '性别': '男​'},
    ])
    handler = VerifyHandler(
        excel_path=excel,
        lrmx_files=[sample_lrmx],
        match_mode=MatchMode.ID_CARD,
        header_row=1,
        field_mapping={'身份证': 'ShenFenZheng', '性别': 'XingBie'},
        match_excel_col_for_id='身份证',
        match_excel_col_for_name=None,
    )
    results = handler.verify()
    assert results[0].status == 'ok'
```

- [ ] **Step 2: Run tests to verify they fail**

```
uv run pytest tests/test_verify_handler.py -v 2>&1 | head -30
```

Expected: all fail with `ModuleNotFoundError` or `ImportError`.

- [ ] **Step 3: Implement `app/core/verify_handler.py`**

```python
"""Batch verification: compare lrmx fields against an Excel roster."""
from __future__ import annotations

import difflib
import html as _html
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import openpyxl

from app.core.lrmx import LrmxFile
from app.core.excel_handler import MatchMode

# Strips all whitespace + Unicode invisible/control characters
_INVIS = re.compile(
    r'[\x00-\x1f\x7f-\x9f'
    r'​-‏‪-‮⁠-⁤﻿'
    r'\s]'
)

_EXCLUDED_FIELDS = {'version'}
# Tags that are containers (non-scalar) — exclude from flat field list
_CONTAINER_TAGS = {'JiaTingChengYuan'}


def _strip(s: str) -> str:
    return _INVIS.sub('', s)


def read_excel_headers(path: Path, header_row: int = 1) -> list[str]:
    """Return the list of column headers from the given row (1-indexed)."""
    wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    ws = wb.active
    for i, row in enumerate(ws.iter_rows(min_row=1, values_only=True), 1):
        if i == header_row:
            wb.close()
            return [str(c) if c is not None else '' for c in row]
    wb.close()
    return []


def get_lrmx_fields(path: Path) -> list[str]:
    """Return all direct-child tag names from an lrmx file,
    excluding 'version' and container tags."""
    root = ET.parse(str(path)).getroot()
    seen: list[str] = []
    for elem in root:
        tag = elem.tag
        if tag in _EXCLUDED_FIELDS or tag in _CONTAINER_TAGS:
            continue
        if tag not in seen:
            seen.append(tag)
    return seen


def char_diff_html(a: str, b: str) -> tuple[str, str]:
    """Return (a_html, b_html) with differing character spans highlighted."""
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    ah: list[str] = []
    bh: list[str] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        ea = _html.escape(a[i1:i2], quote=False)
        eb = _html.escape(b[j1:j2], quote=False)
        if tag == 'equal':
            ah.append(ea)
            bh.append(eb)
        elif tag == 'replace':
            ah.append(f'<span class="del">{ea}</span>')
            bh.append(f'<span class="ins">{eb}</span>')
        elif tag == 'delete':
            ah.append(f'<span class="del">{ea}</span>')
        elif tag == 'insert':
            bh.append(f'<span class="ins">{eb}</span>')
    return ''.join(ah), ''.join(bh)


@dataclass
class FieldResult:
    field: str
    excel_val: str      # raw (pre-strip) for display
    lrmx_val: str       # raw (pre-strip) for display
    match: bool


@dataclass
class PersonResult:
    name: str
    lrmx_path: str
    status: str         # 'ok' | 'diff' | 'not_found' | 'error'
    fields: list[FieldResult] = field(default_factory=list)
    error_msg: str = ''


class VerifyHandler:
    def __init__(
        self,
        excel_path: Path,
        lrmx_files: list,
        match_mode: str,
        header_row: int,
        field_mapping: dict[str, str],   # excel_col → lrmx_field
        match_excel_col_for_id: Optional[str],
        match_excel_col_for_name: Optional[str],
    ) -> None:
        self.excel_path = Path(excel_path)
        self.lrmx_files = [Path(f) for f in lrmx_files]
        self.match_mode = match_mode
        self.header_row = header_row
        self.field_mapping = field_mapping
        self._id_col = match_excel_col_for_id
        self._name_col = match_excel_col_for_name

    # ── build Excel index ──────────────────────────────────────────────────────

    def _load_excel_index(self) -> dict[str, dict]:
        """Return {match_key: row_dict} from Excel."""
        wb = openpyxl.load_workbook(str(self.excel_path), read_only=True, data_only=True)
        ws = wb.active
        headers: list[str] = []
        index: dict[str, dict] = {}
        data_start = self.header_row + 1
        for i, row in enumerate(ws.iter_rows(min_row=1, values_only=True), 1):
            if i == self.header_row:
                headers = [str(c) if c is not None else '' for c in row]
                continue
            if i < data_start:
                continue
            row_dict = dict(zip(headers, row))
            key = self._excel_key(row_dict)
            if key:
                index[key] = row_dict
        wb.close()
        return index

    def _excel_key(self, row: dict) -> str:
        name = _strip(str(row.get(self._name_col) or '')) if self._name_col else ''
        id_  = _strip(str(row.get(self._id_col)   or '')) if self._id_col   else ''
        if self.match_mode == MatchMode.ID_CARD:
            return id_
        if self.match_mode == MatchMode.NAME:
            return name
        return name + id_

    def _lrmx_key(self, lf: LrmxFile) -> str:
        name = _strip(lf.get('XingMing'))
        id_  = _strip(lf.get('ShenFenZheng'))
        if self.match_mode == MatchMode.ID_CARD:
            return id_
        if self.match_mode == MatchMode.NAME:
            return name
        return name + id_

    # ── verify ────────────────────────────────────────────────────────────────

    def verify(
        self,
        progress_cb: Optional[Callable[[PersonResult], None]] = None,
    ) -> list[PersonResult]:
        excel_index = self._load_excel_index()
        results: list[PersonResult] = []

        for lrmx_path in self.lrmx_files:
            try:
                lf = LrmxFile(lrmx_path)
            except Exception as e:
                r = PersonResult(
                    name=lrmx_path.stem,
                    lrmx_path=str(lrmx_path),
                    status='error',
                    error_msg=str(e),
                )
                results.append(r)
                if progress_cb:
                    progress_cb(r)
                continue

            name = lf.get('XingMing') or lrmx_path.stem
            key = self._lrmx_key(lf)

            if key not in excel_index:
                r = PersonResult(
                    name=name,
                    lrmx_path=str(lrmx_path),
                    status='not_found',
                )
                results.append(r)
                if progress_cb:
                    progress_cb(r)
                continue

            excel_row = excel_index[key]
            field_results: list[FieldResult] = []
            any_diff = False

            for excel_col, lrmx_field in self.field_mapping.items():
                excel_raw = str(excel_row.get(excel_col) or '')
                lrmx_raw  = lf.get(lrmx_field)
                match = _strip(excel_raw) == _strip(lrmx_raw)
                if not match:
                    any_diff = True
                field_results.append(FieldResult(
                    field=lrmx_field,
                    excel_val=excel_raw,
                    lrmx_val=lrmx_raw,
                    match=match,
                ))

            r = PersonResult(
                name=name,
                lrmx_path=str(lrmx_path),
                status='diff' if any_diff else 'ok',
                fields=field_results,
            )
            results.append(r)
            if progress_cb:
                progress_cb(r)

        return results
```

- [ ] **Step 4: Run tests to verify they pass**

```
uv run pytest tests/test_verify_handler.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```
git add app/core/verify_handler.py tests/test_verify_handler.py
git commit -m "feat: add verify_handler core logic with char-diff support"
```

---

### Task 2: `verify_tab.py` — full UI

**Files:**
- Create: `app/ui/tabs/verify_tab.py`

The tab has four sections stacked vertically:
1. **文件区** — lrmx file list (same pattern as UpdateTab) + Excel picker + 表头行 spinner
2. **字段匹配区** — click-to-match widget
3. **操作行** — 匹配依据 radios + 开始核验 button + summary counts
4. **结果区** — expandable result list with inline diff detail

- [ ] **Step 1: Create `app/ui/tabs/verify_tab.py`**

```python
"""批量核验 tab — verify lrmx fields against an Excel roster."""
from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import (
    Qt, QThread, Signal, QSize, QEvent, QTimer,
)
from PySide6.QtGui import (
    QColor, QDragEnterEvent, QDropEvent, QIcon, QPainter, QPen,
)
from PySide6.QtWidgets import (
    QButtonGroup, QDialog, QFileDialog, QFrame, QHBoxLayout,
    QLabel, QListWidget, QListWidgetItem, QMenu, QProgressBar,
    QPushButton, QRadioButton, QScrollArea, QSizePolicy,
    QSpinBox, QTextEdit, QVBoxLayout, QWidget,
)

from app.core.excel_handler import MatchMode
from app.core.lrmx import LrmxFile
from app.core.verify_handler import (
    PersonResult, VerifyHandler, char_diff_html,
    get_lrmx_fields, read_excel_headers,
)

_ASSETS = Path(__file__).parent.parent / 'assets'

# ── reused helpers (same as UpdateTab) ────────────────────────────────────────

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
    def event(self, e):
        if e.type() == QEvent.Type.HoverEnter:
            self._hovered = True; self.update()
        elif e.type() == QEvent.Type.HoverLeave:
            self._hovered = False; self.update()
        return super().event(e)
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        color = self._SEP_HOVER if self._hovered else self._SEP_NORMAL
        painter.setPen(QPen(color, 1))
        y = self.height() - 1
        painter.drawLine(10, y, self.width() - 10, y)
        painter.end()


# ── field mapping widget ───────────────────────────────────────────────────────

class _MatchTag(QWidget):
    """Clickable Excel-header tag in the left panel."""
    clicked_tag = Signal(str)

    def __init__(self, col: str, parent=None):
        super().__init__(parent)
        self.col = col
        self._selected = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 3, 8, 3)
        self._lbl = QLabel(col)
        self._lbl.setObjectName('matchTag')
        layout.addWidget(self._lbl)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def set_selected(self, v: bool):
        self._selected = v
        self._lbl.setProperty('selected', v)
        self._lbl.style().unpolish(self._lbl)
        self._lbl.style().polish(self._lbl)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked_tag.emit(self.col)
        super().mousePressEvent(event)


class _FieldRow(QWidget):
    """One lrmx field row in the right panel."""
    clicked_field = Signal(str)
    remove_mapping = Signal(str)   # emits lrmx_field

    def __init__(self, field: str, parent=None):
        super().__init__(parent)
        self.field = field
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        self._field_lbl = QLabel(field)
        self._field_lbl.setFixedWidth(180)
        self._field_lbl.setObjectName('fieldRowName')
        layout.addWidget(self._field_lbl)

        self._status_lbl = QLabel('未匹配')
        self._status_lbl.setObjectName('fieldRowUnmapped')
        layout.addWidget(self._status_lbl, 1)

        self._del_btn = QPushButton('✕')
        self._del_btn.setObjectName('fileItemRemove')
        self._del_btn.setFixedSize(20, 20)
        self._del_btn.hide()
        self._del_btn.clicked.connect(lambda: self.remove_mapping.emit(self.field))
        layout.addWidget(self._del_btn)

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName('fieldRow')

    def set_mapped(self, excel_col: str | None):
        if excel_col:
            self._status_lbl.setText(excel_col)
            self._status_lbl.setObjectName('fieldRowMapped')
            self._del_btn.show()
        else:
            self._status_lbl.setText('未匹配')
            self._status_lbl.setObjectName('fieldRowUnmapped')
            self._del_btn.hide()
        self._status_lbl.style().unpolish(self._status_lbl)
        self._status_lbl.style().polish(self._status_lbl)

    def set_pending(self, pending: bool):
        self.setProperty('pending', pending)
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked_field.emit(self.field)
        super().mousePressEvent(event)


class _MappingWidget(QWidget):
    """Click-to-match field mapping: left = Excel headers, right = lrmx fields."""
    mapping_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._selected_col: str | None = None
        # excel_col → lrmx_field
        self._mapping: dict[str, str] = {}
        # lrmx_field → excel_col (reverse)
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
        lv.addWidget(QLabel('Excel 表头'))
        self._tag_container = QWidget()
        self._tag_layout = _FlowLayout(self._tag_container, spacing=4)
        lv.addWidget(self._tag_container)
        lv.addStretch()
        outer.addWidget(left)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        outer.addWidget(sep)

        # Right panel
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(8, 0, 0, 0)
        rv.setSpacing(2)
        rv.addWidget(QLabel('任免表字段'))
        self._field_container = QWidget()
        self._field_vbox = QVBoxLayout(self._field_container)
        self._field_vbox.setContentsMargins(0, 0, 0, 0)
        self._field_vbox.setSpacing(2)
        rv.addWidget(self._field_container)
        rv.addStretch()
        outer.addWidget(right, 1)

    def load_excel_cols(self, cols: list[str]):
        """Populate left panel with Excel column tags."""
        # clear existing tags
        for tag in self._tags.values():
            tag.deleteLater()
        self._tags.clear()
        while self._tag_layout.count():
            self._tag_layout.takeAt(0)
        # reset mapping
        self._mapping.clear()
        self._reverse.clear()
        self._selected_col = None
        for col in cols:
            if not col.strip():
                continue
            tag = _MatchTag(col)
            tag.clicked_tag.connect(self._on_tag_clicked)
            self._tags[col] = tag
            self._tag_layout.addWidget(tag)
        self.mapping_changed.emit()

    def load_lrmx_fields(self, fields: list[str]):
        """Populate right panel with lrmx field rows."""
        for row in self._field_rows.values():
            row.deleteLater()
        self._field_rows.clear()
        for i in reversed(range(self._field_vbox.count())):
            self._field_vbox.itemAt(i).widget().deleteLater() if self._field_vbox.itemAt(i).widget() else None
        # rebuild
        for f in fields:
            row = _FieldRow(f)
            row.clicked_field.connect(self._on_field_clicked)
            row.remove_mapping.connect(self._remove_mapping)
            self._field_rows[f] = row
            self._field_vbox.addWidget(row)

    def _on_tag_clicked(self, col: str):
        if col in self._mapping:
            return  # already mapped; ignore
        # toggle selection
        if self._selected_col == col:
            self._selected_col = None
            self._tags[col].set_selected(False)
            self._clear_pending()
        else:
            if self._selected_col and self._selected_col in self._tags:
                self._tags[self._selected_col].set_selected(False)
            self._selected_col = col
            self._tags[col].set_selected(True)
            self._update_pending()

    def _on_field_clicked(self, lrmx_field: str):
        if self._selected_col is None:
            return
        if lrmx_field in self._reverse:
            return  # already mapped; ignore
        # create mapping
        self._mapping[self._selected_col] = lrmx_field
        self._reverse[lrmx_field] = self._selected_col
        # hide tag
        self._tags[self._selected_col].hide()
        # update field row
        self._field_rows[lrmx_field].set_mapped(self._selected_col)
        self._field_rows[lrmx_field].set_pending(False)
        # reset selection
        self._selected_col = None
        self._clear_pending()
        self.mapping_changed.emit()

    def _remove_mapping(self, lrmx_field: str):
        if lrmx_field not in self._reverse:
            return
        excel_col = self._reverse.pop(lrmx_field)
        self._mapping.pop(excel_col, None)
        self._field_rows[lrmx_field].set_mapped(None)
        if excel_col in self._tags:
            self._tags[excel_col].show()
        self.mapping_changed.emit()

    def _update_pending(self):
        for field, row in self._field_rows.items():
            row.set_pending(field not in self._reverse)

    def _clear_pending(self):
        for row in self._field_rows.values():
            row.set_pending(False)

    def get_mapping(self) -> dict[str, str]:
        """Return {excel_col: lrmx_field}."""
        return dict(self._mapping)

    def clear_all(self):
        for lrmx_field in list(self._reverse.keys()):
            self._remove_mapping(lrmx_field)
        if self._selected_col and self._selected_col in self._tags:
            self._tags[self._selected_col].set_selected(False)
            self._selected_col = None


class _FlowLayout:
    """Minimal wrapper that adds widgets to a QWidget using a wrapping HBox approach."""
    def __init__(self, parent: QWidget, spacing: int = 4):
        self._parent = parent
        self._spacing = spacing
        self._rows: list[QHBoxLayout] = []
        self._outer = QVBoxLayout(parent)
        self._outer.setContentsMargins(0, 0, 0, 0)
        self._outer.setSpacing(spacing)
        self._widgets: list[QWidget] = []

    def addWidget(self, w: QWidget):
        self._widgets.append(w)
        self._reflow()

    def takeAt(self, i: int):
        pass  # used only to clear

    def count(self) -> int:
        return len(self._widgets)

    def _reflow(self):
        # Clear current rows
        while self._outer.count():
            item = self._outer.takeAt(0)
            if item.layout():
                while item.layout().count():
                    item.layout().takeAt(0)
        self._rows.clear()
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(self._spacing)
        self._rows.append(row)
        self._outer.addLayout(row)
        for w in self._widgets:
            row.addWidget(w)
        row.addStretch()


# ── result widgets ────────────────────────────────────────────────────────────

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
    """Build HTML for the diff detail panel of one person."""
    # invert mapping: lrmx_field → excel_col label
    lrmx_to_excel = {v: k for k, v in field_mapping.items()}
    rows_html = []
    for fr in result.fields:
        excel_label = lrmx_to_excel.get(fr.field, fr.field)
        if fr.match:
            import html as _html_mod
            val = _html_mod.escape(fr.lrmx_val, quote=False)
            rows_html.append(
                f'<tr><td class="field">{fr.field}</td>'
                f'<td><span class="same">{val}（一致）</span></td>'
                f'<td></td></tr>'
            )
        else:
            a_html, b_html = char_diff_html(fr.excel_val, fr.lrmx_val)
            rows_html.append(
                f'<tr class="diff-row"><td class="field">{fr.field}</td>'
                f'<td>{a_html}</td>'
                f'<td>{b_html}</td></tr>'
            )
    ok_count  = sum(1 for f in result.fields if f.match)
    err_count = sum(1 for f in result.fields if not f.match)
    body = '\n'.join(rows_html)
    footer = f'共核验 {len(result.fields)} 个字段 · 一致 {ok_count} · 差异 {err_count}'
    return (
        f'{_DIFF_STYLE}'
        f'<table>'
        f'<thead><tr><th>字段</th><th style="color:#5588bb">Excel 名册</th>'
        f'<th style="color:#558855">任免表</th></tr></thead>'
        f'<tbody>{body}</tbody></table>'
        f'<div class="footer">{footer}</div>'
    )


class _ResultRow(QWidget):
    """One row in the result list; click to expand/collapse diff detail."""

    _STATUS_COLOR = {
        'ok':        '#5db880',
        'diff':      '#e06060',
        'not_found': '#d4a55a',
        'error':     '#e06060',
    }
    _STATUS_TEXT = {
        'ok':        '一致',
        'diff':      '有差异',
        'not_found': '名册无此人',
        'error':     '错误',
    }

    def __init__(self, result: PersonResult, field_mapping: dict[str, str], parent=None):
        super().__init__(parent)
        self._result = result
        self._field_mapping = field_mapping
        self._expanded = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Summary header row
        header = QWidget()
        header.setCursor(Qt.CursorShape.PointingHandCursor)
        header.setObjectName('resultRowHeader')
        hl = QHBoxLayout(header)
        hl.setContentsMargins(10, 6, 10, 6)
        hl.setSpacing(8)

        self._arrow = QLabel('▶')
        self._arrow.setFixedWidth(12)
        self._arrow.setObjectName('resultArrow')
        hl.addWidget(self._arrow)

        name_lbl = QLabel(result.name)
        name_lbl.setObjectName('resultName')
        hl.addWidget(name_lbl)

        n_diff = sum(1 for f in result.fields if not f.match)
        if result.status == 'diff':
            badge_text = f'{n_diff} 处差异'
        else:
            badge_text = self._STATUS_TEXT.get(result.status, result.status)

        color = self._STATUS_COLOR.get(result.status, '#888')
        badge = QLabel(badge_text)
        badge.setStyleSheet(
            f'color: {color}; font-size: 11px; font-weight: 600;'
        )
        hl.addStretch()
        hl.addWidget(badge)

        outer.addWidget(header)

        # Detail panel (hidden by default)
        self._detail = QTextEdit()
        self._detail.setObjectName('diffDetail')
        self._detail.setReadOnly(True)
        self._detail.hide()
        outer.addWidget(self._detail)

        # make header clickable
        header.mousePressEvent = self._toggle

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName('resultSep')
        outer.addWidget(sep)

    def _toggle(self, event=None):
        if self._result.status == 'not_found':
            return
        self._expanded = not self._expanded
        self._arrow.setText('▼' if self._expanded else '▶')
        if self._expanded and not self._detail.toPlainText():
            self._detail.setHtml(_build_detail_html(self._result, self._field_mapping))
            # auto-size height
            doc_h = int(self._detail.document().size().height()) + 16
            self._detail.setFixedHeight(min(max(doc_h, 80), 400))
        self._detail.setVisible(self._expanded)


# ── background worker ─────────────────────────────────────────────────────────

class _VerifyWorker(QThread):
    result_ready = Signal(object)   # PersonResult
    finished = Signal()

    def __init__(self, handler: VerifyHandler, parent=None):
        super().__init__(parent)
        self._handler = handler

    def run(self):
        try:
            self._handler.verify(progress_cb=self.result_ready.emit)
        except Exception as e:
            from app.core.verify_handler import PersonResult
            self.result_ready.emit(PersonResult(
                name='', lrmx_path='', status='error', error_msg=str(e)
            ))
        self.finished.emit()


# ── main tab ──────────────────────────────────────────────────────────────────

class VerifyTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker: _VerifyWorker | None = None
        self._scan_worker: _FolderScanWorker | None = None
        self._results: list[PersonResult] = []
        self._counts = {'ok': 0, 'diff': 0, 'not_found': 0, 'error': 0}
        self._build_ui()
        self.setAcceptDrops(True)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)

        title = QLabel('批量核验')
        title.setObjectName('sectionTitle')
        root.addWidget(title)

        sub = QLabel('对照干部名册（Excel），核验任免审批表中的字段是否一致')
        sub.setStyleSheet('color: #888880; font-size: 12px;')
        root.addWidget(sub)

        # ── lrmx file list ─────────────────────────────────────────────────────
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
        root.addLayout(list_header)

        self._file_list = _FileList()
        self._file_list.setObjectName('fileList')
        self._file_list.setMinimumHeight(80)
        self._file_list.setMaximumHeight(140)
        self._file_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self._file_list.empty_clicked.connect(lambda: add_menu.exec(
            add_btn.mapToGlobal(add_btn.rect().bottomLeft())
        ))
        root.addWidget(self._file_list)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(sep1)

        # ── Excel picker + 表头行 ──────────────────────────────────────────────
        xl_row = QHBoxLayout()
        xl_lbl = QLabel('干部名册')
        xl_lbl.setFixedWidth(60)
        self._xl_edit = _ReadOnlyLineEdit()
        self._xl_edit.setPlaceholderText('选择 .xlsx 文件…')
        xl_btn = QPushButton('浏览')
        xl_btn.setIcon(QIcon(str(_ASSETS / 'folder.svg')))
        xl_btn.setIconSize(QSize(15, 15))
        xl_btn.clicked.connect(self._pick_excel)
        xl_row.addWidget(xl_lbl)
        xl_row.addWidget(self._xl_edit, 1)
        xl_row.addWidget(xl_btn)
        xl_row.addSpacing(12)
        xl_row.addWidget(QLabel('表头行'))
        self._header_spin = QSpinBox()
        self._header_spin.setMinimum(1)
        self._header_spin.setMaximum(20)
        self._header_spin.setValue(1)
        self._header_spin.setFixedWidth(55)
        self._header_spin.valueChanged.connect(self._reload_excel_headers)
        xl_row.addWidget(self._header_spin)
        root.addLayout(xl_row)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(sep2)

        # ── field mapping ─────────────────────────────────────────────────────
        mapping_lbl = QLabel('字段匹配')
        mapping_lbl.setObjectName('sectionTitle')
        root.addWidget(mapping_lbl)

        mapping_hint = QLabel('点击左侧 Excel 表头选中 → 点击右侧字段完成匹配')
        mapping_hint.setStyleSheet('color: #888; font-size: 11px;')
        root.addWidget(mapping_hint)

        self._mapping_widget = _MappingWidget()
        self._mapping_widget.mapping_changed.connect(self._update_run_btn)
        root.addWidget(self._mapping_widget)

        clear_map_btn = QPushButton('清除全部匹配')
        clear_map_btn.setFixedHeight(24)
        clear_map_btn.clicked.connect(self._mapping_widget.clear_all)
        h = QHBoxLayout()
        h.addStretch()
        h.addWidget(clear_map_btn)
        root.addLayout(h)

        sep3 = QFrame()
        sep3.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(sep3)

        # ── 匹配依据 + 开始按钮 ────────────────────────────────────────────────
        run_row = QHBoxLayout()
        match_lbl = QLabel('匹配依据')
        match_lbl.setFixedWidth(60)
        self._match_group = QButtonGroup(self)
        self._rb_id   = QRadioButton('身份证号（推荐）')
        self._rb_name = QRadioButton('姓名')
        self._rb_both = QRadioButton('姓名+身份证号')
        self._rb_id.setChecked(True)
        for rb in (self._rb_id, self._rb_name, self._rb_both):
            self._match_group.addButton(rb)
        run_row.addWidget(match_lbl)
        run_row.addWidget(self._rb_id)
        run_row.addSpacing(10)
        run_row.addWidget(self._rb_name)
        run_row.addSpacing(10)
        run_row.addWidget(self._rb_both)
        run_row.addStretch()
        self._run_btn = QPushButton('开始核验')
        self._run_btn.setObjectName('primary')
        self._run_btn.setEnabled(False)
        self._run_btn.clicked.connect(self._run)
        run_row.addWidget(self._run_btn)
        root.addLayout(run_row)

        # ── summary cards ──────────────────────────────────────────────────────
        self._summary_row = QHBoxLayout()
        self._count_labels: dict[str, QLabel] = {}
        for status, label, color in [
            ('ok',        '完全一致', '#5db880'),
            ('diff',      '有差异',   '#e06060'),
            ('not_found', '名册无此人','#d4a55a'),
            ('error',     '错误',     '#888888'),
        ]:
            card = QWidget()
            card.setObjectName('summaryCard')
            cv = QVBoxLayout(card)
            cv.setContentsMargins(12, 6, 12, 6)
            num = QLabel('0')
            num.setAlignment(Qt.AlignmentFlag.AlignCenter)
            num.setStyleSheet(f'font-size: 20px; font-weight: 700; color: {color};')
            lbl = QLabel(label)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet('font-size: 10px; color: #666;')
            cv.addWidget(num)
            cv.addWidget(lbl)
            self._count_labels[status] = num
            self._summary_row.addWidget(card)
        root.addLayout(self._summary_row)

        # ── result list (scrollable) ───────────────────────────────────────────
        self._result_scroll = QScrollArea()
        self._result_scroll.setWidgetResizable(True)
        self._result_scroll.setObjectName('resultScroll')
        self._result_container = QWidget()
        self._result_vbox = QVBoxLayout(self._result_container)
        self._result_vbox.setContentsMargins(0, 0, 0, 0)
        self._result_vbox.setSpacing(0)
        self._result_vbox.addStretch()
        self._result_scroll.setWidget(self._result_container)
        root.addWidget(self._result_scroll, 1)

    # ── file list helpers (same pattern as UpdateTab) ─────────────────────────

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
        # load lrmx fields from first file
        if self._file_list.count() == 1:
            self._load_lrmx_fields(path)

    def _load_lrmx_fields(self, path: str):
        try:
            fields = get_lrmx_fields(Path(path))
            self._mapping_widget.load_lrmx_fields(fields)
        except Exception:
            pass

    def _remove_item(self, item: QListWidgetItem):
        self._file_list.takeItem(self._file_list.row(item))

    def _remove_selected(self):
        for item in self._file_list.selectedItems():
            self._file_list.takeItem(self._file_list.row(item))

    def _clear_files(self):
        self._file_list.clear()
        self._mapping_widget.load_lrmx_fields([])

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
                batch.clear(); batch.extend(rest)
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

    # ── drag & drop ───────────────────────────────────────────────────────────

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith('.lrmx'):
                self._add_file(path)

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
            self._mapping_widget.load_excel_cols([h for h in headers if h.strip()])
        except Exception:
            pass
        self._update_run_btn()

    # ── run ───────────────────────────────────────────────────────────────────

    def _update_run_btn(self):
        mapping = self._mapping_widget.get_mapping()
        has_files  = self._file_list.count() > 0
        has_excel  = bool(self._xl_edit.text())
        has_mapping = bool(mapping)
        self._run_btn.setEnabled(has_files and has_excel and has_mapping)

    def _match_excel_cols(self) -> tuple[str | None, str | None]:
        """Return (id_col, name_col) for person matching from mapping."""
        mapping = self._mapping_widget.get_mapping()
        # find which excel col maps to ShenFenZheng / XingMing
        id_col   = next((c for c, f in mapping.items() if f == 'ShenFenZheng'), None)
        name_col = next((c for c, f in mapping.items() if f == 'XingMing'), None)
        return id_col, name_col

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

        # reset UI
        self._clear_results()
        self._run_btn.setEnabled(False)
        self._results.clear()

        self._worker = _VerifyWorker(handler)
        self._worker.result_ready.connect(self._on_result)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _on_result(self, result: PersonResult):
        self._results.append(result)
        self._counts[result.status] = self._counts.get(result.status, 0) + 1
        self._count_labels[result.status].setText(
            str(self._counts[result.status])
        )
        mapping = self._mapping_widget.get_mapping()
        row_widget = _ResultRow(result, mapping)
        # insert before the stretch
        idx = self._result_vbox.count() - 1
        self._result_vbox.insertWidget(idx, row_widget)

    def _on_finished(self):
        self._run_btn.setEnabled(True)

    def _clear_results(self):
        self._counts = {'ok': 0, 'diff': 0, 'not_found': 0, 'error': 0}
        for lbl in self._count_labels.values():
            lbl.setText('0')
        while self._result_vbox.count() > 1:
            item = self._result_vbox.takeAt(0)
            if item.widget():
                item.widget().deleteLater()


class _ReadOnlyLineEdit(QWidget):
    """QLineEdit-like read-only display that shows placeholder text."""
    def __init__(self, parent=None):
        super().__init__(parent)
        from PySide6.QtWidgets import QLineEdit as _QLE
        self._edit = _QLE(self)
        self._edit.setReadOnly(True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._edit)

    def setPlaceholderText(self, t: str):
        self._edit.setPlaceholderText(t)

    def setText(self, t: str):
        self._edit.setText(t)

    def text(self) -> str:
        return self._edit.text()
```

- [ ] **Step 2: Commit**

```
git add app/ui/tabs/verify_tab.py
git commit -m "feat: add verify_tab UI with click-to-match field mapping and diff result view"
```

---

### Task 3: Wire VerifyTab into MainWindow

**Files:**
- Modify: `app/ui/main_window.py`

- [ ] **Step 1: Add nav button and stack entry**

In `app/ui/main_window.py`, in `_build_ui`, in the nav button loop, add `('批量核验', 'verify.svg')` after `('版本兼容', 'compat.svg')`:

```python
        for label, icon in [
            ('批量转换', 'convert.svg'),
            ('批量更新', 'update.svg'),
            ('版本兼容', 'compat.svg'),
            ('批量核验', 'verify.svg'),   # ← add this line
        ]:
```

Then add `VerifyTab` to the stack (after `CompatTab()`):

```python
        from app.ui.tabs.convert_tab import ConvertTab
        from app.ui.tabs.update_tab import UpdateTab
        from app.ui.tabs.compat_tab import CompatTab
        from app.ui.tabs.verify_tab import VerifyTab   # ← add

        self._stack = QStackedWidget()
        self._stack.addWidget(ConvertTab())
        self._stack.addWidget(UpdateTab())
        self._stack.addWidget(CompatTab())
        self._stack.addWidget(VerifyTab())             # ← add
        self._stack.addWidget(SettingsTab())
```

> **Note:** The settings button index also shifts — it was `idx 3` before, now it's `idx 4`. The settings button is added separately after `addStretch()`, so `_switch_tab` is driven by the button's captured index `i` at creation time. Verify that `settings_btn` is added to `self._nav_btns` last and the SettingsTab is also added last to `self._stack`, so indices stay aligned.

- [ ] **Step 2: Add `verify.svg` placeholder icon**

Create a minimal SVG so the app doesn't crash at startup:

```
# In PowerShell or Bash:
cp app/ui/assets/compat.svg app/ui/assets/verify.svg
```

(Replace with a proper icon later.)

- [ ] **Step 3: Run the app and verify tab appears**

```
uv run python -m app
```

Expected: 批量核验 nav button appears in sidebar. Clicking it shows the tab. No Python errors in console.

- [ ] **Step 4: Commit**

```
git add app/ui/main_window.py app/ui/assets/verify.svg
git commit -m "feat: wire VerifyTab into MainWindow as fourth tab"
```

---

### Task 4: QSS styles for new elements

**Files:**
- Modify: `app/ui/style.py`

The new widgets use these `objectName` / class selectors that need styles:

- `QLabel#matchTag` — Excel header tag (pill shape, blue tint; `selected` property variant)
- `QWidget#fieldRow` — lrmx field row (hover border; `pending` property variant)
- `QLabel#fieldRowName` — field name label in right panel
- `QLabel#fieldRowMapped` — mapped Excel col label (green tint)
- `QLabel#fieldRowUnmapped` — unmapped hint (dim)
- `QWidget#summaryCard` — result summary card (bordered box)
- `QWidget#resultRowHeader` — result row header (hover highlight)
- `QLabel#resultArrow` — ▶/▼ arrow
- `QLabel#resultName` — person name in result
- `QTextEdit#diffDetail` — diff HTML view (dark background, no border radius)
- `QFrame#resultSep` — thin separator between result rows

- [ ] **Step 1: Open `app/ui/style.py` and append the following block at the end of the `QSS` string (before the closing `"""`)**

```python
# ── verify tab ──────────────────────────────────────────────────────────────
"""
QLabel#matchTag {
    background: #1a3a5c;
    color: #7bb3e8;
    border: 1px solid #2d5a8e;
    border-radius: 10px;
    padding: 2px 8px;
    font-size: 11px;
}
QLabel#matchTag[selected="true"] {
    background: #2d5a8e;
    color: #c8e0ff;
    border-color: #5ba0e0;
}
QWidget#fieldRow {
    background: #242424;
    border: 1px solid transparent;
    border-radius: 4px;
}
QWidget#fieldRow:hover {
    border-color: #2d5a8e;
}
QWidget#fieldRow[pending="true"] {
    border-color: #3a5070;
}
QLabel#fieldRowName  { color: #ccc; font-size: 11px; }
QLabel#fieldRowMapped   { color: #5db880; font-size: 11px;
                          background: #1a3a24; border: 1px solid #2d6a4f;
                          border-radius: 8px; padding: 1px 6px; }
QLabel#fieldRowUnmapped { color: #555; font-size: 11px; font-style: italic; }
QWidget#summaryCard {
    background: #1e1e1e;
    border: 1px solid #2a2a2a;
    border-radius: 5px;
}
QWidget#resultRowHeader:hover { background: #1e2530; }
QLabel#resultArrow  { color: #555; font-size: 11px; }
QLabel#resultName   { color: #ccc; font-weight: 600; }
QTextEdit#diffDetail {
    background: #111518;
    border: none;
    border-radius: 0;
    font-family: "Microsoft YaHei", "PingFang SC", monospace;
    font-size: 12px;
}
QFrame#resultSep {
    color: #1e1e1e;
    background: #1e1e1e;
    max-height: 1px;
}
QScrollArea#resultScroll { border: none; background: transparent; }
"""
```

> **Implementation note:** `app/ui/style.py` holds `QSS` as a multi-line string. Append the new block inside the same string — do not create a second `QSS` variable.

- [ ] **Step 2: Run the app and visually check the verify tab**

```
uv run python -m app
```

Expected: Tags render as pills, field rows have hover border, result rows show correct colors.

- [ ] **Step 3: Commit**

```
git add app/ui/style.py
git commit -m "feat: add QSS styles for verify tab elements"
```

---

## Self-Review

**Spec coverage check:**

| Requirement | Covered by |
|-------------|-----------|
| lrmx file list (same pattern as UpdateTab) | Task 2 — `_FileList`, `_FileRow`, `_FolderScanWorker`, drag-drop |
| Excel file picker + 表头行 spinner | Task 2 — `_pick_excel`, `_header_spin`, `_reload_excel_headers` |
| Dynamic lrmx field list (all fields, excl. version + containers) | Task 1 — `get_lrmx_fields`; Task 2 — `_load_lrmx_fields` on first file add |
| Click-to-match field mapping | Task 2 — `_MappingWidget`, `_MatchTag`, `_FieldRow` |
| One-to-one only, ✕ to remove | Task 2 — guard in `_on_tag_clicked` / `_on_field_clicked`; `_del_btn` |
| Person matching (same as UpdateTab) | Task 1 — `VerifyHandler._lrmx_key` / `_excel_key` + `MatchMode`; Task 2 — radios |
| Strip invisible chars before compare | Task 1 — `_strip`, used in `verify()` and `_excel_key` |
| Summary cards (ok/diff/not_found/error) | Task 2 — `_counts`, `_count_labels` |
| Expandable diff detail per person | Task 2 — `_ResultRow._toggle`, `_build_detail_html` |
| Character-level diff with `difflib` | Task 1 — `char_diff_html` |
| Nav button + stack integration | Task 3 |
| QSS styles | Task 4 |

**Placeholder scan:** No TBDs or vague steps found.

**Type consistency:**
- `VerifyHandler` takes `field_mapping: dict[str, str]` (excel_col→lrmx_field) — consistent with `_MappingWidget.get_mapping()` return type.
- `PersonResult.fields: list[FieldResult]` — consistent with `_build_detail_html(result.fields)` iteration.
- `char_diff_html(a, b) -> tuple[str, str]` — consistent with `_build_detail_html` call signature.
- `get_lrmx_fields(path: Path) -> list[str]` — consistent with `_MappingWidget.load_lrmx_fields(fields)`.
- `read_excel_headers(path, header_row) -> list[str]` — consistent with `_MappingWidget.load_excel_cols(headers)`.
