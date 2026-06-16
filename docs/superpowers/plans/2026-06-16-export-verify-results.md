# 核验结果导出 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在批量核验结果区新增导出功能，支持 Excel（双 Sheet）和 HTML（还原 UI 风格）两种格式，由用户勾选，导出当前筛选可见的结果。

**Architecture:** 新增纯逻辑模块 `app/core/result_exporter.py`（无 Qt 依赖，可独立测试）；`verify_tab.py` 在筛选卡片下方增加导出行 UI，收集可见结果后调用导出函数。

**Tech Stack:** openpyxl（项目已有依赖）、Python 标准库 `html` / `pathlib` / `datetime`

---

## 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `app/core/result_exporter.py` | 新建 | `export_excel` / `export_html` 纯函数，无 Qt |
| `app/ui/tabs/verify_tab.py` | 修改 | 导出行 UI + 调用导出函数 |
| `tests/test_result_exporter.py` | 新建 | 核心逻辑单元测试 |

---

## 背景知识（阅读代码前必看）

**数据模型**（`app/core/verify_handler.py`）：

```python
@dataclass
class FieldResult:
    field: str       # lrmx 字段 tag，如 'ShenFenZheng'、'XingMing'
    excel_val: str   # Excel 名册中该列的值
    lrmx_val: str    # 任免表中该字段的值
    match: bool      # 两者去除不可见字符后是否相等

@dataclass
class PersonResult:
    name: str            # 姓名（来自任免表 XingMing 字段）
    lrmx_path: str       # 任免表文件路径
    status: str          # 'ok' | 'diff' | 'not_found' | 'error'
    fields: list[FieldResult]  # 被核验的字段列表（not_found/error 时为空）
    error_msg: str       # 仅 error 状态有值
```

`char_diff_html(a, b) -> tuple[str, str]` 在 `verify_handler.py` 中已定义，返回 `(a_html, b_html)`，差异字符用 `<span class="del">` / `<span class="ins">` 标记。

**verify_tab.py 相关状态**：
- `self._result_rows: list[_ResultRow]` — 所有结果行 widget
- `self._active_filter: str | None` — 当前筛选状态键，None 表示全部
- `self._summary_lbl: QLabel` — 汇总栏描述文字，用于 HTML 配置摘要
- `_ResultRow._result: PersonResult` — 每行持有的数据

---

## Task 1: result_exporter.py — Excel 导出

**Files:**
- Create: `app/core/result_exporter.py`
- Test: `tests/test_result_exporter.py`

- [ ] **Step 1: 写失败测试**

新建 `tests/test_result_exporter.py`：

```python
from pathlib import Path
import tempfile
import openpyxl
from app.core.verify_handler import PersonResult, FieldResult
from app.core.result_exporter import export_excel


def _sample_results() -> list[PersonResult]:
    ok = PersonResult(
        name='张三', lrmx_path='a.lrmx', status='ok',
        fields=[
            FieldResult(field='XingMing', excel_val='张三', lrmx_val='张三', match=True),
            FieldResult(field='ShenFenZheng', excel_val='110101199001011234',
                        lrmx_val='110101199001011234', match=True),
        ],
    )
    diff = PersonResult(
        name='李四', lrmx_path='b.lrmx', status='diff',
        fields=[
            FieldResult(field='ShenFenZheng', excel_val='110101199001015678',
                        lrmx_val='110101199001015678', match=True),
            FieldResult(field='ChuShengNianYue', excel_val='1990-01',
                        lrmx_val='1990.01', match=False),
        ],
    )
    nf = PersonResult(name='王五', lrmx_path='c.lrmx', status='not_found')
    err = PersonResult(name='赵六', lrmx_path='d.lrmx', status='error',
                       error_msg='文件损坏')
    return [ok, diff, nf, err]


def test_excel_sheet1_headers_and_row_count():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / 'out.xlsx'
        export_excel(_sample_results(), path)
        wb = openpyxl.load_workbook(str(path))
        ws = wb['人员汇总']
        rows = list(ws.iter_rows(values_only=True))
        assert rows[0] == ('姓名', '身份证', '核验状态', '差异字段数', '差异字段', '错误信息')
        assert len(rows) == 5  # 1 header + 4 results


def test_excel_sheet1_status_labels():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / 'out.xlsx'
        export_excel(_sample_results(), path)
        wb = openpyxl.load_workbook(str(path))
        ws = wb['人员汇总']
        rows = list(ws.iter_rows(values_only=True))
        assert rows[1][2] == '一致'
        assert rows[2][2] == '有差异'
        assert rows[2][3] == 1        # 1 差异字段
        assert rows[2][4] == 'ChuShengNianYue'
        assert rows[3][2] == '名册无此人'
        assert rows[4][2] == '错误'
        assert rows[4][5] == '文件损坏'


def test_excel_sheet2_field_rows():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / 'out.xlsx'
        export_excel(_sample_results(), path)
        wb = openpyxl.load_workbook(str(path))
        ws = wb['字段明细']
        rows = list(ws.iter_rows(values_only=True))
        assert rows[0] == ('姓名', '身份证', '字段', '名册值', '任免表值', '是否一致')
        field_col = [r[2] for r in rows[1:]]
        # ok 的 2 个字段 + diff 的 2 个字段 + not_found 1行 + error 1行
        assert len(field_col) == 6
        assert 'ChuShengNianYue' in field_col
        assert '—' in field_col   # not_found / error 占位行


def test_excel_sheet2_match_symbols():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / 'out.xlsx'
        export_excel(_sample_results(), path)
        wb = openpyxl.load_workbook(str(path))
        ws = wb['字段明细']
        rows = list(ws.iter_rows(values_only=True))
        match_col = [r[5] for r in rows[1:] if r[5] in ('✓', '✗')]
        assert '✓' in match_col
        assert '✗' in match_col
```

- [ ] **Step 2: 运行测试，确认失败**

```
uv run pytest tests/test_result_exporter.py -v
```

期望：`ImportError: cannot import name 'export_excel' from 'app.core.result_exporter'`（文件不存在）

- [ ] **Step 3: 实现 export_excel**

新建 `app/core/result_exporter.py`：

```python
"""Export verification results to Excel or self-contained HTML."""
from __future__ import annotations

import html as _html
from datetime import datetime
from pathlib import Path

import openpyxl
from openpyxl.styles import Font, PatternFill

from app.core.verify_handler import PersonResult, char_diff_html

# ── shared constants ──────────────────────────────────────────────────────────

_STATUS_LABELS: dict[str, str] = {
    'ok':        '一致',
    'diff':      '有差异',
    'not_found': '名册无此人',
    'error':     '错误',
}

_STATUS_FILL: dict[str, PatternFill] = {
    'ok':        PatternFill('solid', fgColor='E8F5EC'),
    'diff':      PatternFill('solid', fgColor='FDEAEA'),
    'not_found': PatternFill('solid', fgColor='FFF3E0'),
    'error':     PatternFill('solid', fgColor='F5F5F5'),
}

_DEL_FILL = PatternFill('solid', fgColor='FDEAEA')
_INS_FILL = PatternFill('solid', fgColor='E8F5EC')

_BOLD = Font(bold=True)


def _id_val(result: PersonResult) -> str:
    """Return the Excel value for ShenFenZheng, or '' if not mapped."""
    for fr in result.fields:
        if fr.field == 'ShenFenZheng':
            return fr.excel_val
    return ''


# ── Excel export ──────────────────────────────────────────────────────────────

def export_excel(results: list[PersonResult], path: Path) -> None:
    """Write a dual-sheet workbook. Raises on failure."""
    wb = openpyxl.Workbook()

    # ── Sheet1: 人员汇总 ──────────────────────────────────────────────────────
    ws1 = wb.active
    ws1.title = '人员汇总'
    headers1 = ['姓名', '身份证', '核验状态', '差异字段数', '差异字段', '错误信息']
    ws1.append(headers1)
    for cell in ws1[1]:
        cell.font = _BOLD

    for r in results:
        status = r.status if r.status in _STATUS_LABELS else 'error'
        if r.fields:
            diff_n: int | str = sum(1 for f in r.fields if not f.match)
            diff_names = ', '.join(f.field for f in r.fields if not f.match)
        else:
            diff_n = ''
            diff_names = ''
        ws1.append([
            r.name,
            _id_val(r),
            _STATUS_LABELS[status],
            diff_n,
            diff_names,
            r.error_msg,
        ])
        ws1.cell(ws1.max_row, 3).fill = _STATUS_FILL[status]

    # ── Sheet2: 字段明细 ──────────────────────────────────────────────────────
    ws2 = wb.create_sheet('字段明细')
    headers2 = ['姓名', '身份证', '字段', '名册值', '任免表值', '是否一致']
    ws2.append(headers2)
    for cell in ws2[1]:
        cell.font = _BOLD

    for r in results:
        id_ = _id_val(r)
        status = r.status if r.status in _STATUS_LABELS else 'error'
        if status in ('ok', 'diff') and r.fields:
            for fr in r.fields:
                ws2.append([
                    r.name, id_, fr.field,
                    fr.excel_val, fr.lrmx_val,
                    '✓' if fr.match else '✗',
                ])
                if not fr.match:
                    ws2.cell(ws2.max_row, 4).fill = _DEL_FILL
                    ws2.cell(ws2.max_row, 5).fill = _INS_FILL
        else:
            note = r.error_msg if status == 'error' else _STATUS_LABELS[status]
            ws2.append([r.name, id_, '—', note, '', ''])

    wb.save(path)
```

- [ ] **Step 4: 运行测试，确认通过**

```
uv run pytest tests/test_result_exporter.py::test_excel_sheet1_headers_and_row_count tests/test_result_exporter.py::test_excel_sheet1_status_labels tests/test_result_exporter.py::test_excel_sheet2_field_rows tests/test_result_exporter.py::test_excel_sheet2_match_symbols -v
```

期望：4 个测试全部 PASS

- [ ] **Step 5: 提交**

```bash
git add app/core/result_exporter.py tests/test_result_exporter.py
git commit -m "feat: add export_excel to result_exporter with dual-sheet output"
```

---

## Task 2: result_exporter.py — HTML 导出

**Files:**
- Modify: `app/core/result_exporter.py`
- Modify: `tests/test_result_exporter.py`

- [ ] **Step 1: 追加失败测试**

在 `tests/test_result_exporter.py` 末尾追加：

```python
from app.core.result_exporter import export_html


def test_html_creates_valid_file():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / 'out.html'
        export_html(_sample_results(), path, config_summary='测试摘要')
        content = path.read_text(encoding='utf-8')
        assert content.startswith('<!DOCTYPE html>')
        assert '测试摘要' in content
        assert '张三' in content
        assert '李四' in content
        assert 'class="badge ok"' in content
        assert 'class="badge diff"' in content
        assert 'class="badge not_found"' in content
        assert 'class="badge error"' in content


def test_html_diff_highlighting():
    results = [PersonResult(
        name='测试人', lrmx_path='x.lrmx', status='diff',
        fields=[FieldResult(
            field='ChuShengNianYue',
            excel_val='1990-01',
            lrmx_val='1990.01',
            match=False,
        )],
    )]
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / 'out.html'
        export_html(results, path)
        content = path.read_text(encoding='utf-8')
        assert 'class="del"' in content
        assert 'class="ins"' in content


def test_html_diff_open_by_default():
    """'有差异'的 details 块默认 open，'一致'的不展开。"""
    results = _sample_results()
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / 'out.html'
        export_html(results, path)
        content = path.read_text(encoding='utf-8')
        # diff entry should have <details open>
        assert '<details open>' in content
        # ok entry should just be <details>
        assert '<details>' in content


def test_html_not_found_and_error_note():
    results = [
        PersonResult(name='王五', lrmx_path='c.lrmx', status='not_found'),
        PersonResult(name='赵六', lrmx_path='d.lrmx', status='error', error_msg='文件损坏'),
    ]
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / 'out.html'
        export_html(results, path)
        content = path.read_text(encoding='utf-8')
        assert '未找到匹配记录' in content
        assert '文件损坏' in content
```

- [ ] **Step 2: 运行测试，确认失败**

```
uv run pytest tests/test_result_exporter.py::test_html_creates_valid_file -v
```

期望：`ImportError: cannot import name 'export_html'`

- [ ] **Step 3: 实现 export_html**

在 `app/core/result_exporter.py` 末尾追加（`export_excel` 之后）：

```python
# ── HTML export ───────────────────────────────────────────────────────────────

_HTML_CSS = """\
body{font-family:system-ui,sans-serif;margin:24px;color:#333;background:#F8F5F0}
.header{margin-bottom:16px}
.meta{font-size:12px;color:#888880;margin-bottom:8px}
.counts{display:flex;gap:12px;flex-wrap:wrap}
.badge{font-size:12px;font-weight:600;padding:2px 8px;border-radius:4px;white-space:nowrap}
.badge.ok{color:#1E7A3A;background:#E8F5EC}
.badge.diff{color:#B02020;background:#FDEAEA}
.badge.not_found{color:#C07030;background:#FFF3E0}
.badge.error{color:#555;background:#F5F5F5}
details{background:#fff;border-radius:6px;margin-bottom:6px;border:1px solid #E8E4DE}
summary{padding:8px 12px;cursor:pointer;display:flex;align-items:center;gap:8px;
        list-style:none;user-select:none}
summary::-webkit-details-marker{display:none}
.arrow{font-size:10px;color:#888}
.name{font-weight:500;flex:1}
table{width:100%;border-collapse:collapse;font-size:12px}
th{background:#F5F2EE;color:#888880;font-weight:500;padding:5px 10px;text-align:left}
td{padding:5px 10px;border-top:1px solid #F0EDEA;vertical-align:top;word-break:break-all}
.field-col{color:#888880;width:160px;word-break:normal}
.del{background:#FDEAEA;color:#B02020;border-radius:2px;padding:0 2px}
.ins{background:#E8F5EC;color:#1E7A3A;border-radius:2px;padding:0 2px}
.same{color:#AAAAAA;font-style:italic}
.note{padding:8px 12px;font-size:12px;color:#888}
"""


def export_html(
    results: list[PersonResult],
    path: Path,
    config_summary: str = '',
) -> None:
    """Write a self-contained HTML file reproducing the verify-tab diff view."""
    counts: dict[str, int] = {'ok': 0, 'diff': 0, 'not_found': 0, 'error': 0}
    for r in results:
        counts[r.status if r.status in counts else 'error'] += 1

    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    meta_text = f'导出时间：{now}'
    if config_summary:
        meta_text += f'　·　{config_summary}'

    parts: list[str] = [
        '<!DOCTYPE html><html lang="zh"><head>'
        '<meta charset="utf-8"><title>核验结果</title>'
        f'<style>{_HTML_CSS}</style></head><body>',
        '<div class="header">',
        f'<div class="meta">{_html.escape(meta_text)}</div>',
        '<div class="counts">',
    ]
    for key, label in _STATUS_LABELS.items():
        parts.append(
            f'<span class="badge {key}">{counts[key]} {label}</span>'
        )
    parts.append('</div></div>')

    for r in results:
        status = r.status if r.status in _STATUS_LABELS else 'error'
        label = _STATUS_LABELS[status]
        open_attr = ' open' if status == 'diff' else ''
        name_escaped = _html.escape(r.name or r.lrmx_path)

        parts.append(f'<details{open_attr}>')
        parts.append(
            f'<summary>'
            f'<span class="arrow">▶</span>'
            f'<span class="name">{name_escaped}</span>'
            f'<span class="badge {status}">{label}</span>'
            f'</summary>'
        )

        if status in ('ok', 'diff') and r.fields:
            parts.append(
                '<table><tr><th>字段</th><th>名册值</th><th>任免表值</th></tr>'
            )
            for fr in r.fields:
                field_esc = _html.escape(fr.field)
                if fr.match:
                    val = _html.escape(fr.lrmx_val or '')
                    parts.append(
                        f'<tr><td class="field-col">{field_esc}</td>'
                        f'<td colspan="2" class="same">{val}（一致）</td></tr>'
                    )
                else:
                    a_html, b_html = char_diff_html(fr.excel_val, fr.lrmx_val)
                    parts.append(
                        f'<tr><td class="field-col">{field_esc}</td>'
                        f'<td>{a_html}</td><td>{b_html}</td></tr>'
                    )
            parts.append('</table>')
        elif status == 'not_found':
            parts.append('<div class="note">该人员在名册中未找到匹配记录。</div>')
        else:  # error
            parts.append(
                f'<div class="note">错误：{_html.escape(r.error_msg)}</div>'
            )

        parts.append('</details>')

    parts.append('</body></html>')
    path.write_text(''.join(parts), encoding='utf-8')
```

- [ ] **Step 4: 运行所有测试，确认全部通过**

```
uv run pytest tests/test_result_exporter.py -v
```

期望：8 个测试全部 PASS

- [ ] **Step 5: 提交**

```bash
git add app/core/result_exporter.py tests/test_result_exporter.py
git commit -m "feat: add export_html to result_exporter with inline diff highlighting"
```

---

## Task 3: verify_tab.py — 导出行 UI

**Files:**
- Modify: `app/ui/tabs/verify_tab.py`

> UI 变更不写自动化测试，由人工验证。

- [ ] **Step 1: 添加缺失的 Qt imports**

`verify_tab.py` 第 6 行的 `QWidget, QVBoxLayout, ...` 导入块，添加 `QCheckBox` 和 `QMessageBox`：

```python
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QCheckBox, QMessageBox,
    QRadioButton, QButtonGroup, QFileDialog,
    QSizePolicy, QFrame,
    QScrollArea, QSpinBox, QLayout, QSplitter,
)
```

- [ ] **Step 2: 在 `_build_ui` 中添加导出行**

找到 `_build_ui` 中这段代码（在 `layout.addWidget(self._summary_cards_widget)` 之后，`result_scroll = QScrollArea()` 之前）：

```python
        self._summary_cards_widget.hide()
        layout.addWidget(self._summary_cards_widget)

        result_scroll = QScrollArea()
```

替换为：

```python
        self._summary_cards_widget.hide()
        layout.addWidget(self._summary_cards_widget)

        # ── 导出行 ─────────────────────────────────────────────────────────
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
        self._export_btn.clicked.connect(self._export_results)
        er.addWidget(self._export_btn)

        self._export_status_lbl = QLabel('')
        self._export_status_lbl.setStyleSheet('color: #1E7A3A; font-size: 12px;')
        er.addWidget(self._export_status_lbl, 1)

        layout.addWidget(self._export_row)

        result_scroll = QScrollArea()
```

- [ ] **Step 3: 在 `_run` 中显示导出行**

找到 `_run` 方法中：

```python
        self._result_scroll.show()

        self._loading_overlay.resize(self._result_scroll.size())
```

替换为：

```python
        self._export_row.show()
        self._update_export_btn()
        self._result_scroll.show()

        self._loading_overlay.resize(self._result_scroll.size())
```

- [ ] **Step 4: 在 `_back_to_setup` 中隐藏导出行**

找到：

```python
    def _back_to_setup(self):
        self._loading_overlay.hide()
        self._setup_panel.show()
        self._summary_bar.hide()
        self._result_top_sep.hide()
        self._summary_cards_widget.hide()
        self._result_scroll.hide()
        self._clear_results()
```

替换为：

```python
    def _back_to_setup(self):
        self._loading_overlay.hide()
        self._setup_panel.show()
        self._summary_bar.hide()
        self._result_top_sep.hide()
        self._summary_cards_widget.hide()
        self._export_row.hide()
        self._result_scroll.hide()
        self._clear_results()
```

- [ ] **Step 5: 在 `_apply_result_filter` 末尾刷新导出按钮状态**

找到：

```python
    def _apply_result_filter(self):
        for row in self._result_rows:
            if self._active_filter is None:
                row.show()
            else:
                row.setVisible(row._result.status == self._active_filter)
        QTimer.singleShot(300, self._loading_overlay.hide)
```

替换为：

```python
    def _apply_result_filter(self):
        for row in self._result_rows:
            if self._active_filter is None:
                row.show()
            else:
                row.setVisible(row._result.status == self._active_filter)
        self._update_export_btn()
        QTimer.singleShot(300, self._loading_overlay.hide)
```

- [ ] **Step 6: 添加 `_update_export_btn` 方法**

在 `_on_finished` 方法之后添加：

```python
    def _update_export_btn(self):
        has_format = self._chk_excel.isChecked() or self._chk_html.isChecked()
        visible_count = sum(1 for r in self._result_rows if r.isVisible())
        self._export_btn.setEnabled(has_format and visible_count > 0)
```

- [ ] **Step 7: 添加 `_export_results` 方法**

在 `_update_export_btn` 方法之后添加：

```python
    def _export_results(self):
        from datetime import datetime
        from app.core.result_exporter import export_excel, export_html

        visible = [r._result for r in self._result_rows if r.isVisible()]
        if not visible:
            return

        directory = QFileDialog.getExistingDirectory(self, '选择导出目录')
        if not directory:
            return

        filter_label = {
            'ok': '一致', 'diff': '有差异',
            'not_found': '名册无此人', 'error': '错误',
        }.get(self._active_filter, '全部')
        date_str = datetime.now().strftime('%Y%m%d')
        stem = f'核验结果_{date_str}_{filter_label}'
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

        if errors:
            QMessageBox.warning(self, '导出失败', '\n'.join(errors))

        if saved:
            self._export_status_lbl.setText(f'✓ 已保存到 {directory}')
            QTimer.singleShot(3000, lambda: self._export_status_lbl.setText(''))
```

- [ ] **Step 8: 语法检查**

```
uv run python -c "from app.ui.tabs.verify_tab import VerifyTab; print('OK')"
```

期望输出：`OK`

- [ ] **Step 9: 提交**

```bash
git add app/ui/tabs/verify_tab.py
git commit -m "feat: add export row UI to verify tab (Excel + HTML format selection)"
```

---

## Task 4: 手工验收测试

> 无自动化测试；按以下清单手工验证。

- [ ] **Step 1: 启动应用**

```
uv run python -m app
```

- [ ] **Step 2: 正常导出流程**

1. 进入「批量核验」，添加若干 `.lrmx` 文件，选择 Excel 名册，完成字段匹配
2. 点击「开始核验」
3. 确认筛选卡片下方出现导出行（两个勾选框默认勾选，按钮可用）
4. 点击「导出当前结果」，选择目录
5. 确认同时生成 `核验结果_YYYYMMDD_全部.xlsx` 和 `.html`
6. 打开 Excel：Sheet1 列名正确，状态列有背景色；Sheet2 差异行有红/绿背景
7. 打开 HTML：顶部有计数徽章，有差异的条目默认展开，差异字符红/绿高亮

- [ ] **Step 3: 筛选后导出**

1. 点击「有差异」筛选卡片
2. 确认导出按钮仍可用
3. 导出 → 文件名含 `有差异`
4. 确认 Excel/HTML 中只含有差异的人员

- [ ] **Step 4: 边界情况**

1. 取消两个勾选框 → 导出按钮变灰
2. 重新勾选一个 → 按钮恢复
3. 点击「← 重新配置」→ 导出行消失
4. 再次核验 → 导出行重新出现，状态标签已清空

- [ ] **Step 5: 最终提交（若有遗漏修复）**

```bash
git add -u
git commit -m "fix: verify export edge cases"
```
