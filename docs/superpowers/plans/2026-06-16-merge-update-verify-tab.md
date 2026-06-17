# 批量更新与批量核验合并 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将「批量更新」Tab 并入「批量核验」Tab，共用文件列表与字段映射，通过并排两个操作按钮区分核验与更新；同时修复 ExcelHandler.update() 无法读取真实 Excel 列名的根本问题；并支持向文件列表拖拽目录。

**Architecture:** 删除 `update_tab.py`，在 `verify_tab.py` 中增加 `_UpdateFieldDialog`（字段选择对话框）、`_UpdateWorker`（后台线程）、更新结果滚动区；重构 `ExcelHandler.update()` 接受 `field_mapping` 参数；`file_panel.py` 的拖放逻辑扩展为支持目录；`main_window.py` 移除 UpdateTab 导航入口。

**Tech Stack:** PySide6、openpyxl、Python 3.12

---

## 文件变更总览

| 文件 | 操作 |
|------|------|
| `app/ui/widgets/file_panel.py` | 修改：提取 `_scan_and_add`，`dropEvent` 支持目录 |
| `app/core/excel_handler.py` | 修改：重构 `update()` 接受 `field_mapping` |
| `tests/test_excel_handler.py` | 修改：更新测试以使用新签名 |
| `app/ui/tabs/verify_tab.py` | 修改：增加更新按钮、对话框、后台线程、更新结果视图 |
| `app/ui/tabs/update_tab.py` | 删除 |
| `app/ui/main_window.py` | 修改：移除 UpdateTab 导航入口 |

---

## Task 1: file_panel.py — 目录拖放支持

**Files:**
- Modify: `app/ui/widgets/file_panel.py`

- [ ] **Step 1: 更新 `_FileList._HINT` 提示文字**

将第 62 行：
```python
_HINT = '拖放 .lrmx 文件至此，或点击「添加」'
```
改为：
```python
_HINT = '拖放 .lrmx 文件或文件夹至此，或点击「添加」'
```

- [ ] **Step 2: 将 `_pick_folder` 中的扫描逻辑提取为 `_scan_and_add` 方法**

在 `LrmxFilePanel` 类中，将现有 `_pick_folder`（第 244-259 行）替换为以下两个方法：

```python
def _pick_folder(self):
    folder = QFileDialog.getExistingDirectory(self, '选择包含 lrmx 文件的文件夹')
    if folder:
        self._scan_and_add(folder)

def _scan_and_add(self, folder: str):
    dlg = _LoadingDialog(self.window(), '正在扫描文件夹…')
    self._scan_worker = _FolderScanWorker(folder)

    def on_done(paths):
        if paths:
            self._batch_add(paths, on_finish=dlg.accept)
        else:
            dlg.accept()

    self._scan_worker.done.connect(on_done)
    self._scan_worker.start()
    dlg.exec()
```

- [ ] **Step 3: 更新 `dropEvent` 支持目录**

将现有 `dropEvent`（第 296-300 行）替换为：

```python
def dropEvent(self, event: QDropEvent):
    for url in event.mimeData().urls():
        path = url.toLocalFile()
        if Path(path).is_dir():
            self._scan_and_add(path)
        elif path.lower().endswith('.lrmx'):
            self.add_file(path)
```

- [ ] **Step 4: 手动验证**

运行应用，向文件列表拖入一个包含 `.lrmx` 文件的目录，确认出现扫描 loading 对话框，文件被批量添加；提示文字已更新。

- [ ] **Step 5: Commit**

```bash
git add app/ui/widgets/file_panel.py
git commit -m "feat: 文件列表支持拖拽目录并扫描 lrmx 文件"
```

---

## Task 2: excel_handler.py — 重构 update()

**Files:**
- Modify: `app/core/excel_handler.py`
- Modify: `tests/test_excel_handler.py`

背景：当前 `update()` 假设 Excel 列名 == lrmx 字段名（如 `row.get('XingMing')`），与真实文件不符。新签名接受 `field_mapping: dict[str, str]`（excel列 → lrmx字段）和各匹配列名参数，与 VerifyHandler 的调用方式对齐。

- [ ] **Step 1: 更新测试以使用新签名（TDD — 先写测试）**

将 `tests/test_excel_handler.py` 全部内容替换为：

```python
from pathlib import Path
import openpyxl
import pytest
from app.core.lrmx import LrmxFile
from app.core.excel_handler import ExcelHandler, MatchMode


def make_excel(path: Path, rows: list[dict]) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    headers = list(rows[0].keys())
    ws.append(headers)
    for row in rows:
        ws.append([row[h] for h in headers])
    wb.save(path)
    return path


def test_update_by_id_card(sample_lrmx, tmp_path):
    """Excel 列名不同于 lrmx 字段名时，通过 field_mapping 正确写入"""
    excel = make_excel(tmp_path / 'data.xlsx', [
        {'证件号': '110101199001011234', '现任职务': '副科长'},
    ])
    handler = ExcelHandler(excel, [sample_lrmx], MatchMode.ID_CARD)
    field_mapping = {'证件号': 'ShenFenZheng', '现任职务': 'XianRenZhiWu'}
    logs = handler.update(
        field_mapping=field_mapping,
        fields_to_write=['XianRenZhiWu'],
        match_excel_col_for_id='证件号',
    )
    assert any('张三' in log for log in logs)
    assert any('✓' in log for log in logs)
    updated = LrmxFile(sample_lrmx)
    assert updated.get('XianRenZhiWu') == '副科长'


def test_backup_created_before_update(sample_lrmx, tmp_path):
    excel = make_excel(tmp_path / 'data.xlsx', [
        {'证件号': '110101199001011234', '现任职务': '副科长'},
    ])
    handler = ExcelHandler(excel, [sample_lrmx], MatchMode.ID_CARD)
    field_mapping = {'证件号': 'ShenFenZheng', '现任职务': 'XianRenZhiWu'}
    handler.update(
        field_mapping=field_mapping,
        fields_to_write=['XianRenZhiWu'],
        match_excel_col_for_id='证件号',
    )
    assert sample_lrmx.with_suffix('.lrmx.bak').exists()


def test_unmatched_lrmx_logged(sample_lrmx, tmp_path):
    """名册中没有对应记录时，日志显示 △ 未匹配"""
    excel = make_excel(tmp_path / 'data.xlsx', [
        {'证件号': '000000000000000000', '现任职务': '局长'},
    ])
    handler = ExcelHandler(excel, [sample_lrmx], MatchMode.ID_CARD)
    field_mapping = {'证件号': 'ShenFenZheng', '现任职务': 'XianRenZhiWu'}
    logs = handler.update(
        field_mapping=field_mapping,
        fields_to_write=['XianRenZhiWu'],
        match_excel_col_for_id='证件号',
    )
    assert any('△' in log for log in logs)
    assert any('未在名册中找到' in log for log in logs)


def test_update_by_name(sample_lrmx, tmp_path):
    excel = make_excel(tmp_path / 'data.xlsx', [
        {'姓名': '张三', '健康状况': '良好'},
    ])
    handler = ExcelHandler(excel, [sample_lrmx], MatchMode.NAME)
    field_mapping = {'姓名': 'XingMing', '健康状况': 'JianKangZhuangKuang'}
    handler.update(
        field_mapping=field_mapping,
        fields_to_write=['JianKangZhuangKuang'],
        match_excel_col_for_name='姓名',
    )
    updated = LrmxFile(sample_lrmx)
    assert updated.get('JianKangZhuangKuang') == '良好'


def test_fields_to_write_subset(sample_lrmx, tmp_path):
    """fields_to_write 只写入子集，其他已映射字段不写入"""
    excel = make_excel(tmp_path / 'data.xlsx', [
        {'证件号': '110101199001011234', '现任职务': '副科长', '姓名': '张三'},
    ])
    handler = ExcelHandler(excel, [sample_lrmx], MatchMode.ID_CARD)
    field_mapping = {
        '证件号': 'ShenFenZheng',
        '现任职务': 'XianRenZhiWu',
        '姓名': 'XingMing',
    }
    handler.update(
        field_mapping=field_mapping,
        fields_to_write=['XianRenZhiWu'],  # 只写入现任职务
        match_excel_col_for_id='证件号',
    )
    updated = LrmxFile(sample_lrmx)
    assert updated.get('XianRenZhiWu') == '副科长'
    assert updated.get('XingMing') == '张三'  # 原值不变（sample 本来就是张三）


def test_progress_callback_called(sample_lrmx, tmp_path):
    excel = make_excel(tmp_path / 'data.xlsx', [
        {'证件号': '110101199001011234', '现任职务': '科长'},
    ])
    handler = ExcelHandler(excel, [sample_lrmx], MatchMode.ID_CARD)
    field_mapping = {'证件号': 'ShenFenZheng', '现任职务': 'XianRenZhiWu'}
    calls = []
    handler.update(
        field_mapping=field_mapping,
        fields_to_write=['XianRenZhiWu'],
        match_excel_col_for_id='证件号',
        progress_cb=calls.append,
    )
    assert len(calls) >= 1


def test_header_row_param(sample_lrmx, tmp_path):
    """header_row=2 时跳过第一行"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(['这是说明行，非表头'])
    ws.append(['证件号', '现任职务'])
    ws.append(['110101199001011234', '处长'])
    p = tmp_path / 'data2.xlsx'
    wb.save(p)

    handler = ExcelHandler(p, [sample_lrmx], MatchMode.ID_CARD)
    field_mapping = {'证件号': 'ShenFenZheng', '现任职务': 'XianRenZhiWu'}
    handler.update(
        field_mapping=field_mapping,
        fields_to_write=['XianRenZhiWu'],
        header_row=2,
        match_excel_col_for_id='证件号',
    )
    updated = LrmxFile(sample_lrmx)
    assert updated.get('XianRenZhiWu') == '处长'
```

- [ ] **Step 2: 运行测试确认全部失败（签名不匹配）**

```bash
uv run pytest tests/test_excel_handler.py -v
```

预期：所有测试 FAIL（`TypeError: update() got unexpected keyword argument 'field_mapping'`）

- [ ] **Step 3: 重构 `app/core/excel_handler.py`**

将整个文件内容替换为：

```python
from pathlib import Path
from typing import Callable, Optional
import openpyxl
from .lrmx import LrmxFile


class MatchMode:
    ID_CARD = 'ShenFenZheng'
    NAME = 'XingMing'
    NAME_AND_ID = 'both'


class ExcelHandler:
    def __init__(self, excel_path: Path, lrmx_files: list, match_mode: str) -> None:
        self.excel_path = Path(excel_path)
        self.lrmx_files = [Path(f) for f in lrmx_files]
        self.match_mode = match_mode

    def _make_key(self, lf: LrmxFile) -> str:
        """构建 lrmx 文件的匹配 key"""
        if self.match_mode == MatchMode.ID_CARD:
            return lf.get('ShenFenZheng').strip()
        if self.match_mode == MatchMode.NAME:
            return lf.get('XingMing').strip()
        return lf.get('XingMing').strip() + lf.get('ShenFenZheng').strip()

    def _excel_key(
        self,
        row: dict,
        id_col: str | None,
        name_col: str | None,
    ) -> str:
        """构建 Excel 行的匹配 key，与 _make_key 使用相同规则"""
        if self.match_mode == MatchMode.ID_CARD:
            return str(row.get(id_col) or '').strip() if id_col else ''
        if self.match_mode == MatchMode.NAME:
            return str(row.get(name_col) or '').strip() if name_col else ''
        id_val = str(row.get(id_col) or '').strip() if id_col else ''
        name_val = str(row.get(name_col) or '').strip() if name_col else ''
        return name_val + id_val

    def _load_index(self) -> dict[str, LrmxFile]:
        index: dict[str, LrmxFile] = {}
        for f in self.lrmx_files:
            try:
                lf = LrmxFile(f)
                key = self._make_key(lf)
                if key:
                    index[key] = lf
            except Exception:
                pass
        return index

    def update(
        self,
        field_mapping: dict[str, str],
        fields_to_write: list[str],
        header_row: int = 1,
        match_excel_col_for_id: str | None = None,
        match_excel_col_for_name: str | None = None,
        progress_cb: Optional[Callable[[str], None]] = None,
    ) -> list[str]:
        """
        从 Excel 读取数据，更新匹配的 lrmx 文件。

        field_mapping:           excel列名 → lrmx字段名
        fields_to_write:         实际要写入的 lrmx 字段名（field_mapping 值的子集）
        header_row:              Excel 表头行号（1-based）
        match_excel_col_for_id:  用于匹配身份证的 Excel 列名
        match_excel_col_for_name:用于匹配姓名的 Excel 列名
        """
        wb = openpyxl.load_workbook(self.excel_path)
        ws = wb.active

        headers = [
            cell.value
            for cell in next(ws.iter_rows(min_row=header_row, max_row=header_row))
        ]

        excel_index: dict[str, dict] = {}
        for row_values in ws.iter_rows(min_row=header_row + 1, values_only=True):
            row = dict(zip(headers, row_values))
            key = self._excel_key(row, match_excel_col_for_id, match_excel_col_for_name)
            if key:
                excel_index[key] = row

        lrmx_index = self._load_index()
        logs: list[str] = []

        for lrmx_key, lf in lrmx_index.items():
            name = lf.get('XingMing') or lrmx_key
            if lrmx_key not in excel_index:
                msg = f'△ {name}  未在名册中找到匹配记录'
                logs.append(msg)
                if progress_cb:
                    progress_cb(msg)
                continue

            excel_row = excel_index[lrmx_key]
            backup = lf.path.with_suffix('.lrmx.bak')
            lf.path.rename(backup)
            updated = 0
            try:
                for lrmx_field in fields_to_write:
                    excel_col = next(
                        (c for c, f in field_mapping.items() if f == lrmx_field),
                        None,
                    )
                    if excel_col and excel_col in excel_row:
                        val = excel_row[excel_col]
                        if val is not None:
                            lf.set(lrmx_field, str(val))
                            updated += 1
                lf.save(lf.path)
                msg = f'✓ {name}  已更新 {updated} 个字段'
                logs.append(msg)
                if progress_cb:
                    progress_cb(msg)
            except Exception as e:
                msg = f'✗ {name}  {e}'
                logs.append(msg)
                if progress_cb:
                    progress_cb(msg)

        return logs
```

- [ ] **Step 4: 运行测试确认全部通过**

```bash
uv run pytest tests/test_excel_handler.py -v
```

预期：所有 7 个测试 PASS

- [ ] **Step 5: 运行完整测试套件确认无回归**

```bash
uv run pytest -v
```

预期：全部通过（test_excel_handler 全部改为新测试；其他测试不受影响）

- [ ] **Step 6: Commit**

```bash
git add app/core/excel_handler.py tests/test_excel_handler.py
git commit -m "refactor: 重构 ExcelHandler.update() 接受 field_mapping 参数，修复列名匹配问题"
```

---

## Task 3: verify_tab.py — 合并更新功能

**Files:**
- Modify: `app/ui/tabs/verify_tab.py`

这是最大的任务，分步骤添加各个组件。

### 3a: 添加 `_UpdateFieldDialog` 类

- [ ] **Step 1: 在 verify_tab.py 顶部 imports 之后，在 `_DiffPanel` 类定义之前，添加必要 imports 和 `_UpdateFieldDialog` 类**

在文件第 26 行（`class _DiffPanel` 前）插入：

```python
from PySide6.QtWidgets import QDialog, QGridLayout
```

注意：先检查这两个类是否已在第 6-12 行的 imports 中。若未导入，则需补充到现有的 `from PySide6.QtWidgets import (...)` 块中。

当前 imports 中已有 `QLabel, QPushButton, QCheckBox`，需要添加 `QDialog, QGridLayout`（若尚未存在）。

在第 25 行（`_ASSETS = ...`）和第 27 行（`class _DiffPanel`）之间插入 `_UpdateFieldDialog` 类：

```python
class _UpdateFieldDialog(QDialog):
    """字段选择对话框，点击「开始更新」后弹出，让用户确认要写入的字段。"""

    def __init__(self, mapped_fields: list[tuple[str, str]], parent=None):
        super().__init__(parent)
        self.setWindowTitle('选择要写入的字段')
        self.setMinimumWidth(400)
        self._checks: dict[str, QCheckBox] = {}
        self._build_ui(mapped_fields)

    def _build_ui(self, mapped_fields: list[tuple[str, str]]):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 16, 20, 16)

        layout.addWidget(QLabel('以下字段已完成映射，勾选后将从名册写入 .lrmx'))

        grid_widget = QWidget()
        grid = QGridLayout(grid_widget)
        grid.setSpacing(8)
        grid.setContentsMargins(0, 0, 0, 0)
        for i, (tag, display) in enumerate(mapped_fields):
            chk = QCheckBox(display)
            chk.setChecked(True)
            chk.toggled.connect(self._refresh_confirm_btn)
            self._checks[tag] = chk
            grid.addWidget(chk, i // 2, i % 2)
        layout.addWidget(grid_widget)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        sel_all = QPushButton('全选')
        sel_all.setFixedHeight(26)
        sel_all.clicked.connect(self._select_all)
        sel_none = QPushButton('全不选')
        sel_none.setFixedHeight(26)
        sel_none.clicked.connect(self._deselect_all)
        btn_row.addWidget(sel_all)
        btn_row.addWidget(sel_none)
        layout.addLayout(btn_row)

        warn = QLabel('⚠ 更新将直接修改 .lrmx 文件，建议先核验确认数据正确后再执行更新。')
        warn.setWordWrap(True)
        warn.setStyleSheet('color: #C07030; font-size: 11px;')
        layout.addWidget(warn)

        action_row = QHBoxLayout()
        action_row.addStretch()
        cancel = QPushButton('取消')
        cancel.setFixedHeight(28)
        cancel.clicked.connect(self.reject)
        self._confirm_btn = QPushButton('确认更新')
        self._confirm_btn.setObjectName('primary')
        self._confirm_btn.setFixedHeight(28)
        self._confirm_btn.clicked.connect(self.accept)
        action_row.addWidget(cancel)
        action_row.addWidget(self._confirm_btn)
        layout.addLayout(action_row)

    def _refresh_confirm_btn(self):
        self._confirm_btn.setEnabled(
            any(c.isChecked() for c in self._checks.values())
        )

    def _select_all(self):
        for chk in self._checks.values():
            chk.setChecked(True)

    def _deselect_all(self):
        for chk in self._checks.values():
            chk.setChecked(False)

    def selected_fields(self) -> list[str]:
        return [tag for tag, chk in self._checks.items() if chk.isChecked()]
```

### 3b: 添加 `_UpdateLogRow` 类和 `_UpdateWorker` 类

- [ ] **Step 2: 在 `_ResultRow` 类定义之前（约第 528 行），插入 `_UpdateLogRow`**

```python
class _UpdateLogRow(QWidget):
    """更新结果区的单条日志行：显示图标 + 消息，附带分隔线。"""

    def __init__(self, message: str, kind: str, parent=None):
        super().__init__(parent)
        self._kind = kind  # 'ok' | 'not_found' | 'error'
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        row_w = QWidget()
        rl = QHBoxLayout(row_w)
        rl.setContentsMargins(10, 7, 10, 7)
        lbl = QLabel(message)
        if kind == 'ok':
            lbl.setStyleSheet('color: #1E7A3A;')
        elif kind == 'not_found':
            lbl.setStyleSheet('color: #C07030;')
        else:
            lbl.setStyleSheet('color: #B02020;')
        rl.addWidget(lbl)
        outer.addWidget(row_w)

        sep = QFrame()
        sep.setObjectName('resultSep')
        sep.setFrameShape(QFrame.Shape.HLine)
        outer.addWidget(sep)
```

- [ ] **Step 3: 在 `_VerifyWorker` 类之后（约第 152 行），插入 `_UpdateWorker`**

```python
class _UpdateWorker(QThread):
    log = Signal(str)
    critical = Signal(str)
    finished = Signal()

    def __init__(
        self,
        handler,
        field_mapping: dict,
        fields_to_write: list,
        header_row: int,
        match_excel_col_for_id,
        match_excel_col_for_name,
        parent=None,
    ):
        super().__init__(parent)
        self._handler = handler
        self._field_mapping = field_mapping
        self._fields_to_write = fields_to_write
        self._header_row = header_row
        self._id_col = match_excel_col_for_id
        self._name_col = match_excel_col_for_name

    def run(self):
        try:
            self._handler.update(
                field_mapping=self._field_mapping,
                fields_to_write=self._fields_to_write,
                header_row=self._header_row,
                match_excel_col_for_id=self._id_col,
                match_excel_col_for_name=self._name_col,
                progress_cb=self.log.emit,
            )
        except Exception as e:
            self.critical.emit(str(e))
        self.finished.emit()
```

### 3c: 更新 VerifyTab.__init__ 与 _build_ui

- [ ] **Step 4: 更新 `VerifyTab.__init__` — 添加新属性**

在 `VerifyTab.__init__`（约第 599-608 行）中添加：

```python
def __init__(self, parent=None):
    super().__init__(parent)
    self._worker = None
    self._update_worker = None                              # 新增
    self._settings = QSettings('rmb_helper', 'rmb_helper')
    self._counts = {'ok': 0, 'diff': 0, 'not_found': 0, 'error': 0}
    self._active_filter: str | None = None
    self._result_rows: list[_ResultRow] = []
    self._mode: str = 'verify'                             # 新增
    self._update_counts = {'ok': 0, 'not_found': 0, 'error': 0}   # 新增
    self._update_log_rows: list[_UpdateLogRow] = []        # 新增
    self._update_active_filter: str | None = None          # 新增
    self._build_ui()
    self.setAcceptDrops(True)
```

- [ ] **Step 5: 修改 `_build_ui` — 更新副标题文字**

将约第 626-627 行：
```python
sub = QLabel('对照干部名册（Excel），核验任免审批表中的字段是否一致')
sub.setStyleSheet('color: #888880; font-size: 12px;')
```
改为：
```python
sub = QLabel('对照干部名册，核验或更新任免表字段')
sub.setStyleSheet('color: #888880; font-size: 12px;')
```

- [ ] **Step 6: 修改 `_build_ui` — 储存 back_btn 引用，改为 `self._back_btn`**

将约第 747-750 行：
```python
back_btn = QPushButton('← 重新配置')
back_btn.setFixedHeight(28)
back_btn.clicked.connect(self._back_to_setup)
sb.addWidget(back_btn)
```
改为：
```python
self._back_btn = QPushButton('← 重新配置')
self._back_btn.setFixedHeight(28)
self._back_btn.clicked.connect(self._back_to_setup)
sb.addWidget(self._back_btn)
```

- [ ] **Step 7: 修改 `_build_ui` — 在 run_row 中添加「开始更新」按钮**

将约第 727-733 行的 run_row 构建（从 `run_row = QHBoxLayout()` 到 `bot_layout.addLayout(run_row)`）替换为：

```python
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
self._update_btn = QPushButton('⚠ 开始更新')
self._update_btn.setEnabled(False)
self._update_btn.clicked.connect(self._run_update)
run_row.addWidget(self._update_btn)
run_row.addSpacing(8)
self._run_btn = QPushButton('开始核验')
self._run_btn.setObjectName('primary')
self._run_btn.setEnabled(False)
self._run_btn.clicked.connect(self._run)
run_row.addWidget(self._run_btn)
bot_layout.addLayout(run_row)
```

- [ ] **Step 8: 修改 `_build_ui` — 在结果滚动区之后添加更新结果区**

在 `layout.addWidget(result_scroll, 1)` 和 `self._loading_overlay = ...` 之间，插入更新结果区的 widgets：

```python
# ══════════════════════════════════════════════════════════════════════
# 更新结果区（与核验结果区互斥，_mode 决定显示哪个）
# ══════════════════════════════════════════════════════════════════════
self._update_filter_row = QWidget()
self._update_filter_row.hide()
uf = QHBoxLayout(self._update_filter_row)
uf.setContentsMargins(0, 0, 0, 0)
uf.setSpacing(4)
uf.addStretch()
self._update_filter_btns: list[QPushButton] = []
for label, key in [('全部', 'all'), ('成功', 'ok'), ('错误', 'error')]:
    btn = QPushButton(label)
    btn.setFixedHeight(22)
    btn.setCheckable(True)
    btn.setProperty('logFilter', key)
    btn.setObjectName('logFilterBtn')
    btn.clicked.connect(lambda _, k=key: self._set_update_filter(k))
    uf.addWidget(btn)
    self._update_filter_btns.append(btn)
self._update_filter_btns[0].setChecked(True)  # 默认「全部」选中
layout.addWidget(self._update_filter_row)

update_scroll = QScrollArea()
update_scroll.setObjectName('resultScroll')
update_scroll.setWidgetResizable(True)
update_scroll.setFrameShape(QFrame.Shape.NoFrame)
update_container = QWidget()
self._update_log_vbox = QVBoxLayout(update_container)
self._update_log_vbox.setContentsMargins(0, 0, 0, 0)
self._update_log_vbox.setSpacing(0)
self._update_log_vbox.addStretch()
update_scroll.setWidget(update_container)
update_scroll.hide()
self._update_scroll = update_scroll
layout.addWidget(update_scroll, 1)

self._update_loading_overlay = _LoadingOverlay(self._update_scroll)
self._update_scroll.installEventFilter(self)
```

- [ ] **Step 9: 修改 `eventFilter` — 同步处理 `_update_scroll` 的 resize**

将现有 `eventFilter` 方法：
```python
def eventFilter(self, obj, event):
    if obj is self._result_scroll and event.type() == QEvent.Type.Resize:
        self._loading_overlay.resize(self._result_scroll.size())
    return super().eventFilter(obj, event)
```
改为：
```python
def eventFilter(self, obj, event):
    if event.type() == QEvent.Type.Resize:
        if obj is self._result_scroll:
            self._loading_overlay.resize(self._result_scroll.size())
        elif obj is self._update_scroll:
            self._update_loading_overlay.resize(self._update_scroll.size())
    return super().eventFilter(obj, event)
```

### 3d: 添加更新操作方法

- [ ] **Step 10: 修改 `_update_run_btn` — 同步启用/禁用「开始更新」按钮**

将现有 `_update_run_btn` 方法末尾的：
```python
self._run_btn.setEnabled(has_files and has_excel and has_mapping and key_ok)
if has_mapping and not key_ok:
    self._run_btn.setToolTip('请将匹配依据对应的字段（身份证/姓名）映射到某个 Excel 列')
else:
    self._run_btn.setToolTip('')
```
改为：
```python
ready = has_files and has_excel and has_mapping and key_ok
self._run_btn.setEnabled(ready)
self._update_btn.setEnabled(ready)
if has_mapping and not key_ok:
    tip = '请将匹配依据对应的字段（身份证/姓名）映射到某个 Excel 列'
    self._run_btn.setToolTip(tip)
    self._update_btn.setToolTip(tip)
else:
    self._run_btn.setToolTip('')
    self._update_btn.setToolTip('')
```

- [ ] **Step 11: 添加 `_run_update()` 方法**

在 `_run()` 方法之后，添加：

```python
def _run_update(self):
    files = self._file_panel.files()
    excel_path = self._xl_edit.text()
    mapping = self._mapping_widget.get_mapping()  # {excel_col: lrmx_field}

    field_display = dict(LRMX_FIELDS)
    mapped_fields = [
        (lrmx_f, field_display.get(lrmx_f, lrmx_f))
        for lrmx_f in mapping.values()
    ]

    from PySide6.QtWidgets import QDialog as _QDialog
    dlg = _UpdateFieldDialog(mapped_fields, self)
    if dlg.exec() != _QDialog.DialogCode.Accepted:
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

    from app.core.excel_handler import ExcelHandler
    handler = ExcelHandler(excel_path, files, match_mode)

    self._mode = 'update'
    self._clear_update_results()

    xl_name = Path(excel_path).name
    n_files = len(files)
    n_fields = len(fields_to_write)
    self._summary_lbl.setText(
        f'{n_files} 个任免表  ·  名册：{xl_name}  ·  写入 {n_fields} 个字段'
    )
    self._back_btn.setText('← 返回')

    self._setup_panel.hide()
    self._summary_bar.show()
    self._result_top_sep.show()
    self._summary_cards_widget.hide()
    self._export_row.hide()
    self._result_scroll.hide()
    self._update_filter_row.show()
    self._update_scroll.show()

    self._update_loading_overlay.set_text('更新中，请稍候…')
    self._update_loading_overlay.resize(self._update_scroll.size())
    self._update_loading_overlay.raise_()
    self._update_loading_overlay.show()

    self._update_worker = _UpdateWorker(
        handler=handler,
        field_mapping=mapping,
        fields_to_write=fields_to_write,
        header_row=self._header_spin.value(),
        match_excel_col_for_id=id_col,
        match_excel_col_for_name=name_col,
    )
    self._update_worker.log.connect(self._on_update_log)
    self._update_worker.critical.connect(self._on_update_critical)
    self._update_worker.finished.connect(self._on_update_finished)
    self._update_worker.start()
```

- [ ] **Step 12: 添加 `_on_update_log()`、`_on_update_critical()`、`_on_update_finished()`**

```python
def _on_update_log(self, message: str):
    if message.startswith('✓'):
        kind = 'ok'
        self._update_counts['ok'] += 1
    elif message.startswith('△'):
        kind = 'not_found'
        self._update_counts['not_found'] += 1
    else:
        kind = 'error'
        self._update_counts['error'] += 1

    row = _UpdateLogRow(message, kind)
    self._update_log_rows.append(row)
    idx = self._update_log_vbox.count() - 1
    self._update_log_vbox.insertWidget(idx, row)

    if self._update_active_filter is not None:
        show = (
            (self._update_active_filter == 'ok' and kind == 'ok')
            or (self._update_active_filter == 'error' and kind in ('not_found', 'error'))
        )
        row.setVisible(show)

def _on_update_critical(self, msg: str):
    self._update_loading_overlay.hide()
    from PySide6.QtWidgets import QMessageBox
    QMessageBox.critical(self, 'Excel 读取失败', msg)

def _on_update_finished(self):
    QTimer.singleShot(400, self._update_loading_overlay.hide)
    ok = self._update_counts['ok']
    not_found = self._update_counts['not_found']
    error = self._update_counts['error']
    self._summary_lbl.setText(
        f'已更新 {ok} 个  ·  未匹配 {not_found} 个  ·  失败 {error} 个'
    )
```

- [ ] **Step 13: 添加 `_set_update_filter()` 和 `_clear_update_results()`**

```python
def _set_update_filter(self, key: str):
    self._update_active_filter = None if key == 'all' else key
    for btn in self._update_filter_btns:
        btn.setChecked(btn.property('logFilter') == key)
    for row in self._update_log_rows:
        if self._update_active_filter is None:
            row.show()
        elif self._update_active_filter == 'ok':
            row.setVisible(row._kind == 'ok')
        else:  # 'error' → 包含 not_found 和 error
            row.setVisible(row._kind in ('not_found', 'error'))

def _clear_update_results(self):
    self._update_counts = {'ok': 0, 'not_found': 0, 'error': 0}
    self._update_log_rows = []
    self._update_active_filter = None
    for btn in self._update_filter_btns:
        btn.setChecked(btn.property('logFilter') == 'all')
    while self._update_log_vbox.count() > 1:
        item = self._update_log_vbox.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
```

- [ ] **Step 14: 修改 `_back_to_setup()` — 同时清理更新结果视图**

将现有 `_back_to_setup` 替换为：

```python
def _back_to_setup(self):
    self._loading_overlay.hide()
    self._update_loading_overlay.hide()
    self._setup_panel.show()
    self._back_btn.setText('← 重新配置')
    self._summary_bar.hide()
    self._result_top_sep.hide()
    self._summary_cards_widget.hide()
    self._export_row.hide()
    self._result_scroll.hide()
    self._update_filter_row.hide()
    self._update_scroll.hide()
    self._clear_results()
    self._clear_update_results()
    self._mode = 'verify'
```

- [ ] **Step 15: 修改 `dropEvent` — 支持拖拽目录**

将现有 `dropEvent`（最后约 5 行）替换为：

```python
def dropEvent(self, event: QDropEvent):
    for url in event.mimeData().urls():
        path = url.toLocalFile()
        if Path(path).is_dir():
            self._file_panel._scan_and_add(path)
        elif path.lower().endswith('.lrmx'):
            self._file_panel.add_file(path)
```

- [ ] **Step 16: 手动验证核验功能仍正常**

运行应用，完成一次完整核验流程，确认：
- 副标题已更新为"对照干部名册，核验或更新任免表字段"
- 「开始核验」按钮仍为橙色，右侧位置
- 「开始更新」按钮在核验按钮左侧，灰色
- 两个按钮状态随配置一起启用/禁用
- 核验结果正常显示，导出功能正常

- [ ] **Step 17: 手动验证更新功能**

运行应用，配置文件 + Excel + 字段映射后：
- 点击「开始更新」，弹出字段选择对话框
- 确认字段选择对话框样式与整体一致（无内联 styleSheet 差异）
- 全选/全不选按钮工作
- 全不选时「确认更新」禁用
- 点击确认后切换到更新结果视图
- loading 遮罩显示"更新中，请稍候…"
- 日志行实时显示（✓/△/✗ 对应颜色）
- 过滤按钮「全部/成功/错误」正常工作
- 返回配置后结果清空

- [ ] **Step 18: Commit**

```bash
git add app/ui/tabs/verify_tab.py
git commit -m "feat: 将批量更新合并入批量核验 Tab，增加字段选择对话框和更新结果视图"
```

---

## Task 4: 移除 UpdateTab — main_window.py + 删除 update_tab.py

**Files:**
- Modify: `app/ui/main_window.py`
- Delete: `app/ui/tabs/update_tab.py`

- [ ] **Step 1: 修改 `main_window.py` — 移除「批量更新」导航条目**

将约第 183-192 行的导航按钮循环：
```python
for label, icon in [
    ('批量转换', 'convert.svg'),
    ('批量更新', 'update.svg'),
    ('版本兼容', 'compat.svg'),
    ('批量核验', 'verify.svg'),
]:
```
改为：
```python
for label, icon in [
    ('批量转换', 'convert.svg'),
    ('版本兼容', 'compat.svg'),
    ('批量核验', 'verify.svg'),
]:
```

- [ ] **Step 2: 修改 `main_window.py` — 移除 UpdateTab 的 import 和 stack 添加**

将约第 203-213 行的 imports 和 stack 构建：
```python
from app.ui.tabs.convert_tab import ConvertTab
from app.ui.tabs.update_tab import UpdateTab
from app.ui.tabs.compat_tab import CompatTab
from app.ui.tabs.verify_tab import VerifyTab

self._stack = QStackedWidget()
self._stack.addWidget(ConvertTab())
self._stack.addWidget(UpdateTab())
self._stack.addWidget(CompatTab())
self._stack.addWidget(VerifyTab())
self._stack.addWidget(SettingsTab())
```
改为：
```python
from app.ui.tabs.convert_tab import ConvertTab
from app.ui.tabs.compat_tab import CompatTab
from app.ui.tabs.verify_tab import VerifyTab

self._stack = QStackedWidget()
self._stack.addWidget(ConvertTab())   # index 0 → 批量转换
self._stack.addWidget(CompatTab())    # index 1 → 版本兼容
self._stack.addWidget(VerifyTab())    # index 2 → 批量核验
self._stack.addWidget(SettingsTab())  # index 3 → 设置
```

此时导航按钮 `_switch_tab(i)` 中的 `i` 由 `_make_nav_btn` 的 `idx = len(self._nav_btns)` 在循环时计算。三个普通导航按钮索引为 0/1/2，设置按钮索引为 3，与 stack 一致。

- [ ] **Step 3: 删除 `update_tab.py`**

```bash
git rm app/ui/tabs/update_tab.py
```

- [ ] **Step 4: 手动验证启动**

运行应用，确认：
- 左侧导航只有三项（批量转换、版本兼容、批量核验）+ 设置
- 点击每个导航按钮正常切换内容
- 无 ImportError

- [ ] **Step 5: Commit**

```bash
git add app/ui/main_window.py
git commit -m "refactor: 移除批量更新独立 Tab，导航精简为三项"
```

---

## 自检（self-review）

**Spec coverage:**
- ✅ 导航从四项变三项：Task 4
- ✅ ExcelHandler.update() 新签名：Task 2
- ✅ `_UpdateFieldDialog`：Task 3a
- ✅ `_UpdateWorker`：Task 3b  
- ✅ 「开始更新」按钮（左侧，灰色）：Task 3 Step 7
- ✅ 「开始核验」按钮（右侧，橙色），共用前置校验：Task 3 Step 7 + 10
- ✅ 更新结果视图（过滤按钮、日志行）：Task 3 Step 8
- ✅ loading 遮罩（更新中）：Task 3 Step 11
- ✅ `_back_to_setup` 清理更新视图：Task 3 Step 14
- ✅ file_panel.py 目录拖拽：Task 1
- ✅ verify_tab.py tab 级别 dropEvent 目录支持：Task 3 Step 15
- ✅ Excel 读取失败 → QMessageBox.critical：Task 3 Step 12 (`_on_update_critical`)
- ✅ 写入失败 → ✗ 日志行（实现在 ExcelHandler.update() 的 per-file try/except）：Task 2 Step 3
- ✅ 未匹配 → △ 日志行：Task 2 Step 3
- ✅ 写入前备份 .lrmx.bak：Task 2 Step 3
- ✅ 对话框样式无内联 styleSheet：`_UpdateFieldDialog` 不添加内联样式，只用 objectName='primary'

**Type consistency check:**
- `_UpdateWorker.log = Signal(str)` → `_on_update_log(self, message: str)` ✅
- `_UpdateWorker.critical = Signal(str)` → `_on_update_critical(self, msg: str)` ✅
- `_UpdateFieldDialog.selected_fields() -> list[str]` → `fields_to_write: list[str]` ✅
- `_UpdateLogRow._kind: str` → `_set_update_filter` 中 `row._kind` ✅
- `ExcelHandler.update(field_mapping, fields_to_write, ...)` → `_UpdateWorker.run()` 中调用方式 ✅
