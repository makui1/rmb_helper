# 工程重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 消除四类工程债务（重复 Worker 样板、过大文件、过长方法、分散错误处理），同时保持所有用户可见行为和现有测试不变。

**Architecture:** 先建横切基础设施（BaseWorker + 统一错误工具函数），再拆分 verify_tab.py 为多个 widget 文件，再分解 editor_tab.py 和 docx_exporter.py 的长方法。每个任务独立提交，通过 `uv run pytest` 验证（基准：6 个预存失败、100 个通过——重构后保持此数不变）。

**Tech Stack:** Python 3.12, PySide6, uv（测试运行器：`uv run pytest`）

---

## 文件结构

```
app/ui/
├── workers.py          ← 新建：BaseWorker 基类
├── utils.py            ← 新建：show_error / show_warning
├── tabs/
│   ├── compat_tab.py   ← 修改：_CompatWorker 继承 BaseWorker
│   ├── convert_tab.py  ← 修改：_Worker 继承 BaseWorker
│   ├── family_tab.py   ← 修改：_FamilyWorker 继承 BaseWorker
│   ├── verify_tab.py   ← 修改：Worker 迁移 + 导入重组 + build_ui 无变化
│   └── editor_tab.py   ← 修改：三个长方法分解
├── widgets/
│   ├── file_panel.py   ← 修改：_FolderScanWorker 继承 BaseWorker
│   ├── flow_layout.py  ← 新建：_FlowLayout, _MatchTag
│   ├── field_mapping.py← 新建：_NoScrollCombo, _FieldRow, _MappingWidget
│   ├── verify_result.py← 新建：_DiffPanel, _ResultRow
│   ├── update_log.py   ← 新建：_HoverIconButton, _UpdateLogRow, _UpdateFieldDialog
│   └── loading_overlay.py ← 新建：_LoadingOverlay
app/core/
└── docx_exporter.py    ← 修改：三个长方法分解
```

---

## Task 1：新建 workers.py + utils.py

**Files:**
- Create: `app/ui/workers.py`
- Create: `app/ui/utils.py`

- [ ] **Step 1: 新建 app/ui/workers.py**

```python
from PySide6.QtCore import QThread, Signal


class BaseWorker(QThread):
    """所有后台 Worker 的基类。提供统一的 log / progress / error 信号，
    消除各 Tab 重复声明的样板代码。

    子类选择两种模式之一：
    a) 简单任务：实现 work()，run() 自动包裹 try/except → emits error
    b) 复杂循环任务（per-file try/except）：直接 override run()，
       仅复用信号声明，无需调用 super().run()
    """
    log      = Signal(str)
    progress = Signal(int)   # 0–100
    error    = Signal(str)   # 统一错误信号；UI 层连接到 show_error

    def run(self):
        try:
            self.work()
        except Exception as e:
            self.error.emit(str(e))

    def work(self):
        raise NotImplementedError
```

- [ ] **Step 2: 新建 app/ui/utils.py**

```python
from PySide6.QtWidgets import QMessageBox


def show_error(parent, msg: str) -> None:
    """在所有 UI 层错误提示中统一使用此函数，代替散落的 QMessageBox.critical。"""
    QMessageBox.critical(parent, '错误', msg)


def show_warning(parent, msg: str) -> None:
    """在所有 UI 层警告提示中统一使用此函数，代替散落的 QMessageBox.warning。"""
    QMessageBox.warning(parent, '警告', msg)
```

- [ ] **Step 3: 验证测试基准不变**

```
uv run pytest -q --ignore=tests/test_verify_handler.py
```

Expected: 6 failed（预存）, 100 passed

- [ ] **Step 4: 提交**

```
git add app/ui/workers.py app/ui/utils.py
git commit -m "refactor: 新建 BaseWorker 基类和统一错误提示工具函数"
```

---

## Task 2：迁移 file_panel._FolderScanWorker

**Files:**
- Modify: `app/ui/widgets/file_panel.py`

`_FolderScanWorker` 是最简单的 Worker（单次操作，无内层 try/except），用 `work()` 模式。

- [ ] **Step 1: 在 file_panel.py 顶部添加导入**

在 `from PySide6.QtCore import Qt, QThread, Signal, ...` 这行之后添加：
```python
from app.ui.workers import BaseWorker
```

- [ ] **Step 2: 修改 _FolderScanWorker**

将：
```python
class _FolderScanWorker(QThread):
    done = Signal(list)

    def __init__(self, folder: str, parent=None):
        super().__init__(parent)
        self._folder = folder

    def run(self):
        paths = sorted(str(p) for p in Path(self._folder).rglob('*.lrmx'))
        self.done.emit(paths)
```

改为：
```python
class _FolderScanWorker(BaseWorker):
    done = Signal(list)

    def __init__(self, folder: str, parent=None):
        super().__init__(parent)
        self._folder = folder

    def work(self):
        paths = sorted(str(p) for p in Path(self._folder).rglob('*.lrmx'))
        self.done.emit(paths)
```

- [ ] **Step 3: 从 QtCore 导入中删除 QThread（若仅此处使用）**

检查 file_panel.py 中是否还有其他 `QThread` 用法；若无，将：
```python
from PySide6.QtCore import Qt, QThread, Signal, QSize, QEvent, QTimer, QModelIndex, QRect
```
改为：
```python
from PySide6.QtCore import Qt, Signal, QSize, QEvent, QTimer, QModelIndex, QRect
```

- [ ] **Step 4: 验证**

```
uv run pytest -q --ignore=tests/test_verify_handler.py
```
Expected: 6 failed（预存）, 100 passed

- [ ] **Step 5: 提交**

```
git add app/ui/widgets/file_panel.py
git commit -m "refactor: _FolderScanWorker 改继承 BaseWorker"
```

---

## Task 3：迁移 compat_tab._CompatWorker

**Files:**
- Modify: `app/ui/tabs/compat_tab.py`

`_CompatWorker` 有 per-file 的 try/except 循环，使用模式 b（override run()，仅复用信号声明）。

- [ ] **Step 1: 添加导入**

在 compat_tab.py 的导入区（`from PySide6.QtCore import ...` 之后）添加：
```python
from app.ui.workers import BaseWorker
```

- [ ] **Step 2: 修改类定义，删除重复信号声明**

将：
```python
class _CompatWorker(QThread):
    log = Signal(str)
    finished = Signal(int, int)  # processed, total
    progress = Signal(int)       # current step
```

改为：
```python
class _CompatWorker(BaseWorker):
    finished = Signal(int, int)  # processed, total
    # log 和 progress 已由 BaseWorker 声明
```

- [ ] **Step 3: run() 保持不变（per-file 循环，不改为 work()）**

`_CompatWorker.run()` 的内部逻辑不变，继续 override run()。

- [ ] **Step 4: 删除 QThread 导入（若仅此处使用）**

检查 compat_tab.py 中其他 QThread 用法；若无，从 QtCore 导入中删除 `QThread`。

- [ ] **Step 5: 验证**

```
uv run pytest -q --ignore=tests/test_verify_handler.py
```
Expected: 6 failed（预存）, 100 passed

- [ ] **Step 6: 提交**

```
git add app/ui/tabs/compat_tab.py
git commit -m "refactor: _CompatWorker 改继承 BaseWorker，删除重复信号声明"
```

---

## Task 4：迁移 convert_tab._Worker

**Files:**
- Modify: `app/ui/tabs/convert_tab.py`

`_Worker` 也是 per-file 循环，使用模式 b。

- [ ] **Step 1: 添加导入**

```python
from app.ui.workers import BaseWorker
```

- [ ] **Step 2: 修改类定义**

将：
```python
class _Worker(QThread):
    log = Signal(str)
    finished = Signal(int, int, float)
    progress = Signal(int)
```

改为：
```python
class _Worker(BaseWorker):
    finished = Signal(int, int, float)
    # log 和 progress 已由 BaseWorker 声明
```

- [ ] **Step 3: run() 保持不变**

`_Worker.run()` 的全部逻辑不变，继续 override run()。

- [ ] **Step 4: 从 QtCore 导入中删除 QThread（若无其他使用）**

- [ ] **Step 5: 验证**

```
uv run pytest -q --ignore=tests/test_verify_handler.py
```
Expected: 6 failed（预存）, 100 passed

- [ ] **Step 6: 提交**

```
git add app/ui/tabs/convert_tab.py
git commit -m "refactor: convert_tab._Worker 改继承 BaseWorker，删除重复信号声明"
```

---

## Task 5：迁移 family_tab._FamilyWorker

**Files:**
- Modify: `app/ui/tabs/family_tab.py`

- [ ] **Step 1: 添加导入**

```python
from app.ui.workers import BaseWorker
```

- [ ] **Step 2: 修改类定义**

将：
```python
class _FamilyWorker(QThread):
    log      = Signal(str)
    progress = Signal(int)
    finished = Signal(int, int, int, int)
```

改为：
```python
class _FamilyWorker(BaseWorker):
    finished = Signal(int, int, int, int)  # ok, skip, error, total
    # log 和 progress 已由 BaseWorker 声明
```

- [ ] **Step 3: run() 保持不变（per-file 循环）**

- [ ] **Step 4: 从 QtCore 导入中删除 QThread（若无其他使用）**

- [ ] **Step 5: 验证**

```
uv run pytest -q --ignore=tests/test_verify_handler.py
```
Expected: 6 failed（预存）, 100 passed

- [ ] **Step 6: 提交**

```
git add app/ui/tabs/family_tab.py
git commit -m "refactor: _FamilyWorker 改继承 BaseWorker，删除重复信号声明"
```

---

## Task 6：迁移 verify_tab._UpdateWorker + _VerifyWorker

**Files:**
- Modify: `app/ui/tabs/verify_tab.py`

`_UpdateWorker` 可以改为 `work()` 模式，将 `critical` 信号替换为 BaseWorker 的 `error` 信号。`_VerifyWorker` 错误处理特殊（emit PersonResult），使用模式 b。

- [ ] **Step 1: 添加导入**

在 verify_tab.py 顶部导入区（`from PySide6.QtCore import ...` 之后）添加：
```python
from app.ui.workers import BaseWorker
```

- [ ] **Step 2: 修改 _VerifyWorker（模式 b，仅删除无用信号）**

`_VerifyWorker` 没有 log / progress 信号，不需要删除。只改继承：
```python
class _VerifyWorker(BaseWorker):
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
```

- [ ] **Step 3: 修改 _UpdateWorker（模式 a，work() + error 信号替代 critical）**

将：
```python
class _UpdateWorker(QThread):
    log = Signal(str)
    critical = Signal(str)
    finished = Signal()

    def __init__(self, handler, field_mapping, fields_to_write,
                 header_row, match_excel_col_for_id, match_excel_col_for_name, parent=None):
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

改为：
```python
class _UpdateWorker(BaseWorker):
    finished = Signal()
    # log 由 BaseWorker 声明；critical 重命名为 BaseWorker.error

    def __init__(self, handler, field_mapping, fields_to_write,
                 header_row, match_excel_col_for_id, match_excel_col_for_name, parent=None):
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
```

- [ ] **Step 4: 更新 VerifyTab 中 critical 信号的连接点**

在 `VerifyTab` 中找到 `_update_worker.critical.connect(...)` 的连接，将其改为 `_update_worker.error.connect(...)`。

搜索关键字 `critical` 并替换所有调用方。

- [ ] **Step 5: 从 QtCore 导入中删除 QThread（若无其他使用）**

- [ ] **Step 6: 验证**

```
uv run pytest -q --ignore=tests/test_verify_handler.py
```
Expected: 6 failed（预存）, 100 passed

- [ ] **Step 7: 提交**

```
git add app/ui/tabs/verify_tab.py
git commit -m "refactor: verify_tab Worker 改继承 BaseWorker，_UpdateWorker.critical 重命名为 error"
```

---

## Task 7：统一 UI 层错误提示调用

**Files:**
- Modify: `app/ui/tabs/compat_tab.py`
- Modify: `app/ui/tabs/convert_tab.py`
- Modify: `app/ui/tabs/family_tab.py`
- Modify: `app/ui/tabs/verify_tab.py`
- Modify: `app/ui/tabs/editor_tab.py`
- Modify: `app/ui/tabs/settings_tab.py`

- [ ] **Step 1: 在每个 tab 文件中添加 utils 导入**

在每个需要修改的文件的导入区末尾添加：
```python
from app.ui.utils import show_error, show_warning
```

- [ ] **Step 2: 替换 compat_tab.py 中的 QMessageBox 调用**

查找所有 `QMessageBox.warning(self, ...` 和 `QMessageBox.critical(self, ...`，替换为 `show_warning(self, ...)` 和 `show_error(self, ...)`（只传消息正文，去掉标题参数）。

- [ ] **Step 3: 替换 convert_tab.py 中的 QMessageBox 调用**

同 Step 2。

- [ ] **Step 4: 替换 family_tab.py 中的 QMessageBox 调用**

同 Step 2。

- [ ] **Step 5: 替换 verify_tab.py 中的 QMessageBox 调用**

同 Step 2；同时找到 `_update_worker.error.connect(...)` 并确认连接到 `lambda msg: show_error(self, msg)`。

- [ ] **Step 6: 替换 editor_tab.py 中的 QMessageBox 调用**

同 Step 2。

- [ ] **Step 7: 替换 settings_tab.py 中的 QMessageBox 调用**

同 Step 2。

- [ ] **Step 8: 验证**

```
uv run pytest -q --ignore=tests/test_verify_handler.py
```
Expected: 6 failed（预存）, 100 passed

- [ ] **Step 9: 提交**

```
git add app/ui/tabs/compat_tab.py app/ui/tabs/convert_tab.py app/ui/tabs/family_tab.py app/ui/tabs/verify_tab.py app/ui/tabs/editor_tab.py app/ui/tabs/settings_tab.py
git commit -m "refactor: 统一 UI 层错误提示，全部改用 show_error / show_warning"
```

---

## Task 8：提取 flow_layout.py + loading_overlay.py

**Files:**
- Create: `app/ui/widgets/flow_layout.py`
- Create: `app/ui/widgets/loading_overlay.py`
- Modify: `app/ui/tabs/verify_tab.py`

- [ ] **Step 1: 新建 app/ui/widgets/flow_layout.py**

从 verify_tab.py 中剪切 `_FlowLayout`（L323-L383）和 `_MatchTag`（L386-L412）两个类，粘贴到新文件，在文件顶部补齐导入：

```python
from PySide6.QtWidgets import QWidget, QLayout, QHBoxLayout, QLabel, QSizePolicy
from PySide6.QtCore import Qt, Signal, QSize, QRect, QPoint
```

然后粘贴两个类的完整代码（原样复制，不修改任何逻辑）。

- [ ] **Step 2: 新建 app/ui/widgets/loading_overlay.py**

从 verify_tab.py 中剪切 `_LoadingOverlay`（L299-L318）类，粘贴到新文件：

```python
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt
```

然后粘贴类的完整代码（原样复制）。

- [ ] **Step 3: 在 verify_tab.py 中替换为导入**

在 verify_tab.py 导入区添加：
```python
from app.ui.widgets.flow_layout import _FlowLayout, _MatchTag
from app.ui.widgets.loading_overlay import _LoadingOverlay
```

删除原来的类定义。

- [ ] **Step 4: 验证**

```
uv run pytest -q --ignore=tests/test_verify_handler.py
```
Expected: 6 failed（预存）, 100 passed

- [ ] **Step 5: 提交**

```
git add app/ui/widgets/flow_layout.py app/ui/widgets/loading_overlay.py app/ui/tabs/verify_tab.py
git commit -m "refactor: 提取 _FlowLayout / _MatchTag 到 flow_layout.py，_LoadingOverlay 到 loading_overlay.py"
```

---

## Task 9：提取 field_mapping.py

**Files:**
- Create: `app/ui/widgets/field_mapping.py`
- Modify: `app/ui/tabs/verify_tab.py`

- [ ] **Step 1: 新建 app/ui/widgets/field_mapping.py**

从 verify_tab.py 中剪切 `_NoScrollCombo`（L30-L35）、`_FieldRow`（L415-L497）、`_MappingWidget`（L500-L710）三个类，在文件顶部补齐导入：

```python
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QScrollArea, QFrame, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QIcon

from app.core.compare_rules import CompareRule
from app.ui.widgets.flow_layout import _FlowLayout, _MatchTag

_ASSETS = Path(__file__).parent.parent / 'assets'
```

然后粘贴三个类的完整代码（原样复制）。

**注意**：`_FieldRow` 中使用了 `_HoverIconButton`，Task 10 提取后需添加导入。暂时保留 `_HoverIconButton` 在 verify_tab.py，Task 10 完成后再更新。

- [ ] **Step 2: 在 verify_tab.py 中替换为导入**

```python
from app.ui.widgets.field_mapping import _NoScrollCombo, _FieldRow, _MappingWidget
```

删除三个类的原定义。

- [ ] **Step 3: 验证**

```
uv run pytest -q --ignore=tests/test_verify_handler.py
```
Expected: 6 failed（预存）, 100 passed

- [ ] **Step 4: 提交**

```
git add app/ui/widgets/field_mapping.py app/ui/tabs/verify_tab.py
git commit -m "refactor: 提取 _NoScrollCombo / _FieldRow / _MappingWidget 到 field_mapping.py"
```

---

## Task 10：提取 update_log.py + verify_result.py，整理 HoverIconButton

**Files:**
- Create: `app/ui/widgets/update_log.py`
- Create: `app/ui/widgets/verify_result.py`
- Modify: `app/ui/widgets/field_mapping.py`（添加 _HoverIconButton 导入）
- Modify: `app/ui/tabs/verify_tab.py`

- [ ] **Step 1: 新建 app/ui/widgets/update_log.py**

从 verify_tab.py 中剪切 `_HoverIconButton`（L38-L52）、`_UpdateFieldDialog`（L55-L128）、`_UpdateLogRow`（L715-L741）三个类，在文件顶部补齐导入：

```python
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QCheckBox, QDialog, QGridLayout, QFrame,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon

_ASSETS = Path(__file__).parent.parent / 'assets'
```

然后粘贴三个类的完整代码（原样复制）。

- [ ] **Step 2: 新建 app/ui/widgets/verify_result.py**

从 verify_tab.py 中剪切 `_DiffPanel`（L131-L234）、`_ResultRow`（L744-L809）两个类，在文件顶部补齐导入：

```python
import difflib
import html as _html_lib

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
)
from PySide6.QtCore import Qt

from app.core.verify_handler import PersonResult, FieldResult
```

然后粘贴两个类的完整代码（原样复制）。

- [ ] **Step 3: 更新 field_mapping.py 中的 _HoverIconButton 来源**

在 field_mapping.py 导入区添加：
```python
from app.ui.widgets.update_log import _HoverIconButton
```

- [ ] **Step 4: 在 verify_tab.py 中替换为导入**

```python
from app.ui.widgets.update_log import _HoverIconButton, _UpdateLogRow, _UpdateFieldDialog
from app.ui.widgets.verify_result import _DiffPanel, _ResultRow
```

删除这五个类的原定义。

- [ ] **Step 5: 验证**

```
uv run pytest -q --ignore=tests/test_verify_handler.py
```
Expected: 6 failed（预存）, 100 passed

- [ ] **Step 6: 验证 verify_tab.py 行数**

```
python -c "print(sum(1 for _ in open('app/ui/tabs/verify_tab.py', encoding='utf-8')))"
```
Expected: ≤ 750 行

- [ ] **Step 7: 提交**

```
git add app/ui/widgets/update_log.py app/ui/widgets/verify_result.py app/ui/widgets/field_mapping.py app/ui/tabs/verify_tab.py
git commit -m "refactor: 提取 _UpdateLogRow/_UpdateFieldDialog/_HoverIconButton 到 update_log.py，_DiffPanel/_ResultRow 到 verify_result.py"
```

---

## Task 11：分解 editor_tab._build_layout_a

**Files:**
- Modify: `app/ui/tabs/editor_tab.py`

`_build_layout_a` 当前 159 行，构建双栏严格表格布局。按左栏内的逻辑块拆分：

- [ ] **Step 1: 提取 _build_la_info_grid() — 基本信息网格（左栏顶部）**

```python
def _build_la_info_grid(self, lbl_cell) -> QHBoxLayout:
    """返回含基本信息网格+照片的水平布局。lbl_cell 为调用方提供的标签构造函数。"""
    info_outer = QHBoxLayout()
    info_outer.setSpacing(0)
    info_outer.setContentsMargins(0, 0, 0, 0)
    info_grid = QGridLayout()
    info_grid.setSpacing(0)
    info_grid.setContentsMargins(0, 0, 0, 0)
    info_grid.setColumnStretch(1, 1)
    info_grid.setColumnStretch(3, 1)
    for (r, c, lbl_text, w) in [
        (0, 0, '姓名',    self._xing_ming),
        (0, 2, '性别',    self._xing_bie),
        (1, 0, '出生年月', self._chu_sheng),
        (1, 2, '民族',    self._min_zu),
        (2, 0, '籍贯',    self._ji_guan),
        (2, 2, '出生地',  self._chu_di),
        (3, 0, '入党时间', self._ru_dang),
        (3, 2, '参工时间', self._can_jia),
        (4, 0, '到龄时间', self._dao_ling),
        (4, 2, '健康状况', self._jian_kang),
        (5, 0, '专技职务', self._zhuan_ye),
        (5, 2, '熟悉专业', self._shu_xi),
    ]:
        info_grid.addWidget(lbl_cell(lbl_text), r, c)
        info_grid.addWidget(w, r, c + 1)
    info_outer.addLayout(info_grid, 1)
    info_outer.addWidget(self._photo, 0, Qt.AlignmentFlag.AlignCenter)
    return info_outer
```

- [ ] **Step 2: 提取 _build_la_left() — 左栏容器**

```python
def _build_la_left(self, lbl_cell, sec_cell) -> QWidget:
    left = QWidget()
    left_lay = QVBoxLayout(left)
    left_lay.setContentsMargins(0, 0, 0, 0)
    left_lay.setSpacing(0)

    left_lay.addWidget(sec_cell('基本信息'))
    left_lay.addLayout(self._build_la_info_grid(lbl_cell))

    left_lay.addWidget(sec_cell('学历学位'))
    left_lay.addLayout(self._build_la_edu_grid(lbl_cell))

    left_lay.addWidget(sec_cell('职务'))
    left_lay.addLayout(self._build_la_pos_grid(lbl_cell))

    left_lay.addWidget(sec_cell('简历'))
    left_lay.addWidget(self._jian_li, 1)

    left.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
    return left
```

- [ ] **Step 3: 提取 _build_la_edu_grid() — 学历学位网格**

```python
def _build_la_edu_grid(self, lbl_cell) -> QGridLayout:  # lbl_cell 同 _build_la_info_grid
    edu_grid = QGridLayout()
    edu_grid.setSpacing(0)
    edu_grid.setContentsMargins(0, 0, 0, 0)
    edu_grid.setColumnMinimumWidth(0, 44)
    edu_grid.setColumnMinimumWidth(1, 40)
    edu_grid.setColumnStretch(2, 1)
    edu_grid.setColumnMinimumWidth(3, 92)
    edu_grid.setColumnStretch(4, 2)
    for row, (type_lbl, kind_lbl, combo_w, yuan_w) in enumerate([
        ('全日制', '学历', self._qrz_xueli,  self._qrz_xueli_yuan),
        ('全日制', '学位', self._qrz_xuewei, self._qrz_xuewei_yuan),
        ('在职',   '学历', self._zzj_xueli,  self._zzj_xueli_yuan),
        ('在职',   '学位', self._zzj_xuewei, self._zzj_xuewei_yuan),
    ]):
        edu_grid.addWidget(lbl_cell(type_lbl, 44), row, 0)
        edu_grid.addWidget(lbl_cell(kind_lbl, 40), row, 1)
        edu_grid.addWidget(combo_w, row, 2)
        edu_grid.addWidget(lbl_cell('毕业院校系及专业', 92), row, 3)
        edu_grid.addWidget(yuan_w, row, 4)
    return edu_grid
```

- [ ] **Step 4: 提取 _build_la_pos_grid() — 职务网格**

```python
def _build_la_pos_grid(self, lbl_cell) -> QGridLayout:  # lbl_cell 同上
    pos_grid = QGridLayout()
    pos_grid.setSpacing(0)
    pos_grid.setContentsMargins(0, 0, 0, 0)
    pos_grid.setColumnMinimumWidth(0, _LW2)
    pos_grid.setColumnStretch(1, 1)
    for r, (lbl_text, w) in enumerate([
        ('现任职务', self._xian_ren),
        ('拟任职务', self._ni_ren),
        ('拟免职务', self._ni_mian),
    ]):
        pos_grid.addWidget(lbl_cell(lbl_text), r, 0)
        pos_grid.addWidget(w, r, 1)
    return pos_grid
```

- [ ] **Step 5: 提取 _build_la_right() — 右栏容器**

```python
def _build_la_right(self, lbl_cell, sec_cell) -> QWidget:
    right = QWidget()
    right_lay = QVBoxLayout(right)
    right_lay.setContentsMargins(0, 0, 0, 0)
    right_lay.setSpacing(0)

    right_lay.addWidget(sec_cell('奖惩情况'))
    right_lay.addWidget(self._jiang_cheng)
    right_lay.addWidget(sec_cell('年度考核结果'))
    right_lay.addWidget(self._nian_du)
    right_lay.addWidget(sec_cell('任免理由'))
    right_lay.addWidget(self._ren_mian)
    right_lay.addWidget(sec_cell('家庭主要成员'))
    right_lay.addWidget(self._family, 1)
    right_lay.addWidget(sec_cell('底部信息'))
    right_lay.addLayout(self._build_la_bot_grid(lbl_cell))

    right.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
    return right
```

- [ ] **Step 6: 提取 _build_la_bot_grid() — 底部信息网格**

```python
def _build_la_bot_grid(self, lbl_cell) -> QGridLayout:  # lbl_cell 同上
    bot_grid = QGridLayout()
    bot_grid.setSpacing(0)
    bot_grid.setContentsMargins(0, 0, 0, 0)
    bot_grid.setColumnMinimumWidth(0, 80)
    bot_grid.setColumnMinimumWidth(2, _LW2)
    bot_grid.setColumnStretch(1, 1)
    bot_grid.setColumnStretch(3, 1)
    bot_grid.addWidget(lbl_cell('呈报单位', 80), 0, 0)
    bot_grid.addWidget(self._cheng_bao, 0, 1, 1, 3)
    bot_grid.addWidget(lbl_cell('改革前年龄', 80), 1, 0)
    bot_grid.addWidget(self._gai_ge_nll, 1, 1, 1, 3)
    bot_grid.addWidget(lbl_cell('身份证号', 80), 2, 0)
    bot_grid.addWidget(self._shen_fen, 2, 1)
    bot_grid.addWidget(lbl_cell('计算年龄'), 2, 2)
    bot_grid.addWidget(self._ji_suan, 2, 3)
    bot_grid.addWidget(lbl_cell('填表时间', 80), 3, 0)
    bot_grid.addWidget(self._tian_biao_shi, 3, 1)
    bot_grid.addWidget(lbl_cell('填表人'), 3, 2)
    bot_grid.addWidget(self._tian_biao_ren, 3, 3)
    return bot_grid
```

- [ ] **Step 7: 重写 _build_layout_a() 为纯组合（≤ 25 行）**

```python
def _build_layout_a(self) -> QScrollArea:
    """严格表格式布局：全格线，双栏，标签宽度固定不换行。"""
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    scroll.setFrameShape(QFrame.Shape.NoFrame)

    container = QWidget()
    container.setObjectName('editorFormA')
    outer = QHBoxLayout(container)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)

    def lbl_cell(text: str, min_w: int = _LW2) -> QLabel:
        w = QLabel(text)
        w.setObjectName('tableLbl')
        w.setAlignment(Qt.AlignmentFlag.AlignCenter)
        w.setContentsMargins(2, 2, 2, 2)
        w.setMinimumWidth(min_w)
        return w

    def sec_cell(text: str) -> QLabel:
        w = QLabel(text)
        w.setObjectName('tableSecLbl')
        w.setContentsMargins(6, 2, 6, 2)
        return w

    outer.addWidget(self._build_la_left(lbl_cell, sec_cell), 1)
    outer.addWidget(self._build_la_right(lbl_cell, sec_cell), 1)

    scroll.setWidget(container)
    return scroll
```

- [ ] **Step 8: 验证**

```
uv run pytest -q --ignore=tests/test_verify_handler.py
```
Expected: 6 failed（预存）, 100 passed

- [ ] **Step 9: 提交**

```
git add app/ui/tabs/editor_tab.py
git commit -m "refactor: 分解 editor_tab._build_layout_a 为多个 section 辅助方法"
```

---

## Task 12：分解 editor_tab._build_layout_b + _build_toolbar

**Files:**
- Modify: `app/ui/tabs/editor_tab.py`

- [ ] **Step 1: 提取 _build_lb_basic_section() — 基本信息+照片**

```python
def _build_lb_basic_section(self, row) -> QWidget:
    """layout_b 基本信息区（含照片右浮）。row 为局部辅助函数。"""
    outer = QHBoxLayout()
    outer.setSpacing(16)
    outer.setContentsMargins(0, 0, 0, 0)
    basic_col = QVBoxLayout()
    basic_col.setSpacing(0)
    basic_col.setContentsMargins(0, 0, 0, 0)
    for lbl_text, w in [
        ('姓名',    self._xing_ming),
        ('性别',    self._xing_bie),
        ('出生年月', self._chu_sheng),
        ('民族',    self._min_zu),
        ('籍贯',    self._ji_guan),
        ('出生地',  self._chu_di),
        ('入党时间', self._ru_dang),
        ('参工时间', self._can_jia),
        ('到龄时间', self._dao_ling),
        ('健康状况', self._jian_kang),
        ('专技职务', self._zhuan_ye),
        ('熟悉专业', self._shu_xi),
    ]:
        basic_col.addWidget(row(lbl_text, w))
    photo_col = QVBoxLayout()
    photo_col.setContentsMargins(0, 0, 0, 0)
    photo_col.addWidget(self._photo, 0, Qt.AlignmentFlag.AlignTop)
    photo_col.addStretch()
    outer.addLayout(basic_col, 1)
    outer.addLayout(photo_col, 0)
    container = QWidget()
    container.setLayout(outer)
    return container
```

- [ ] **Step 2: 提取 _build_lb_edu_section() — 学历学位**

```python
def _build_lb_edu_section(self, sec, row) -> list:
    """返回一批 widget 用于 addWidget；sec/row 为局部辅助函数。"""
    items = [sec('学历学位')]
    for lbl_text, w in [
        ('全日制学历', self._qrz_xueli),
        ('全日制院校', self._qrz_xueli_yuan),
        ('全日制学位', self._qrz_xuewei),
        ('全日制院校', self._qrz_xuewei_yuan),
        ('在职学历',  self._zzj_xueli),
        ('在职院校',  self._zzj_xueli_yuan),
        ('在职学位',  self._zzj_xuewei),
        ('在职院校',  self._zzj_xuewei_yuan),
    ]:
        items.append(row(lbl_text, w))
    return items
```

- [ ] **Step 3: 重写 _build_layout_b() 为组合（≤ 50 行）**

```python
def _build_layout_b(self) -> QScrollArea:
    """轻量分隔式布局：简历风格单列，各节下划线分隔，照片右浮。"""
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    scroll.setFrameShape(QFrame.Shape.NoFrame)

    container = QWidget()
    container.setObjectName('editorFormB')
    col = QVBoxLayout(container)
    col.setContentsMargins(24, 8, 24, 24)
    col.setSpacing(0)

    def _sec(text):
        lbl = QLabel(text)
        lbl.setObjectName('bSecTitle')
        return lbl

    def _row(label_text, widget):
        frame = QFrame()
        frame.setObjectName('bFieldRow')
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lbl = QLabel(label_text)
        lbl.setObjectName('bFieldLabel')
        lbl.setFixedWidth(84)
        lay.addWidget(lbl)
        lay.addWidget(widget, 1)
        return frame

    col.addWidget(_sec('基本信息'))
    col.addWidget(self._build_lb_basic_section(_row))

    for w in self._build_lb_edu_section(_sec, _row):
        col.addWidget(w)

    col.addWidget(_sec('职务'))
    for lbl_text, w in [
        ('现任职务', self._xian_ren),
        ('拟任职务', self._ni_ren),
        ('拟免职务', self._ni_mian),
    ]:
        col.addWidget(_row(lbl_text, w))

    col.addWidget(_sec('简历'))
    col.addWidget(self._jian_li, 1)
    col.addWidget(_sec('奖惩情况'))
    col.addWidget(self._jiang_cheng)
    col.addWidget(_sec('年度考核结果'))
    col.addWidget(self._nian_du)
    col.addWidget(_sec('任免理由'))
    col.addWidget(self._ren_mian)
    col.addWidget(_sec('家庭主要成员'))
    col.addWidget(self._family, 1)
    col.addWidget(_sec('其他信息'))
    for lbl_text, w in [
        ('呈报单位',  self._cheng_bao),
        ('改革前年龄', self._gai_ge_nll),
        ('身份证号',  self._shen_fen),
        ('计算年龄',  self._ji_suan),
        ('填表时间',  self._tian_biao_shi),
        ('填表人',   self._tian_biao_ren),
    ]:
        col.addWidget(_row(lbl_text, w))

    scroll.setWidget(container)
    return scroll
```

- [ ] **Step 4: 提取 _build_toolbar_file_area() — 文件操作按钮区**

```python
def _build_toolbar_file_area(self, btn) -> list:
    """返回 [open_btn, sep, save_btn, saveas_btn, sep, export_btn, print_btn, sep, close_btn]。
    btn 为局部辅助函数。"""
    self._open_btn   = btn('打开', '打开 lrmx 文件（可多选）')
    self._save_btn   = btn('保存', '保存当前文件')
    self._save_btn.setObjectName('primary')
    self._saveas_btn = btn('另存为…', '另存为新文件')
    self._export_btn = btn('导出 PDF', '导出为 PDF 文件')
    self._export_btn.setObjectName('secondary')
    self._print_btn  = btn('打印', '打印预览并打印')
    self._close_btn  = btn('关闭', '关闭当前标签页')

    self._open_btn.clicked.connect(self._on_open_btn)
    self._save_btn.clicked.connect(self._on_save_btn)
    self._saveas_btn.clicked.connect(self._on_saveas_btn)
    self._export_btn.clicked.connect(self._on_export_pdf)
    self._print_btn.clicked.connect(self._on_print_btn)
    self._close_btn.clicked.connect(lambda: self._close_tab(self._tabs.currentIndex()))

    for b in [self._save_btn, self._saveas_btn, self._export_btn,
              self._print_btn, self._close_btn]:
        b.setEnabled(False)

    def sep():
        f = QFrame()
        f.setFrameShape(QFrame.Shape.VLine)
        f.setFrameShadow(QFrame.Shadow.Sunken)
        f.setFixedHeight(18)
        f.setStyleSheet('color: #D0CEC8;')
        return f

    return [self._open_btn, sep(),
            self._save_btn, self._saveas_btn, sep(),
            self._export_btn, self._print_btn, sep(),
            self._close_btn]
```

- [ ] **Step 5: 提取 _build_toolbar_layout_toggle() — 布局切换按钮区**

```python
def _build_toolbar_layout_toggle(self) -> list:
    """返回 [layout_b_btn, layout_a_btn]。"""
    self._layout_b_btn = QPushButton('轻量')
    self._layout_b_btn.setObjectName('layoutToggleL')
    self._layout_b_btn.setFixedHeight(24)
    self._layout_b_btn.setCheckable(True)
    self._layout_b_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    self._layout_b_btn.setToolTip('轻量分隔式布局')
    self._layout_b_btn.clicked.connect(lambda: self._on_layout_toggle('b'))

    self._layout_a_btn = QPushButton('表格')
    self._layout_a_btn.setObjectName('layoutToggleR')
    self._layout_a_btn.setFixedHeight(24)
    self._layout_a_btn.setCheckable(True)
    self._layout_a_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    self._layout_a_btn.setToolTip('严格表格式布局')
    self._layout_a_btn.clicked.connect(lambda: self._on_layout_toggle('a'))

    current_mode = self._layout_mode()
    self._layout_b_btn.setChecked(current_mode == 'b')
    self._layout_a_btn.setChecked(current_mode == 'a')

    return [self._layout_b_btn, self._layout_a_btn]
```

- [ ] **Step 6: 重写 _build_toolbar() 为组合（≤ 30 行）**

```python
def _build_toolbar(self) -> QWidget:
    bar = QWidget()
    bar.setObjectName('editorToolbar')
    bar.setFixedHeight(36)
    lay = QHBoxLayout(bar)
    lay.setContentsMargins(10, 4, 10, 4)
    lay.setSpacing(6)

    self._path_lbl = QLabel('未打开文件')
    self._path_lbl.setStyleSheet('color: #888; font-size: 11px;')
    lay.addWidget(self._path_lbl, 1)

    def _btn(text: str, tooltip: str = '') -> QPushButton:
        b = QPushButton(text)
        b.setFixedHeight(26)
        if tooltip:
            b.setToolTip(tooltip)
        return b

    for w in self._build_toolbar_file_area(_btn):
        lay.addWidget(w)

    lay.addSpacing(10)
    for w in self._build_toolbar_layout_toggle():
        lay.addWidget(w)

    return bar
```

- [ ] **Step 7: 验证**

```
uv run pytest -q --ignore=tests/test_verify_handler.py
```
Expected: 6 failed（预存）, 100 passed

- [ ] **Step 8: 提交**

```
git add app/ui/tabs/editor_tab.py
git commit -m "refactor: 分解 editor_tab._build_layout_b 和 _build_toolbar 为 section 辅助方法"
```

---

## Task 13：分解 docx_exporter._build_context

**Files:**
- Modify: `app/core/docx_exporter.py`

`_build_context` 当前 77 行，将字段准备逻辑按类型分组。

- [ ] **Step 1: 提取 _ctx_time_fields() — 时间字段格式化**

```python
def _ctx_time_fields(self, raw: dict) -> dict:
    """格式化出生、到龄、六位/八位时间字段。"""
    birth_ym = _INVIS.sub('', raw.get('ChuShengNianYue', ''))
    ctx: dict = {}
    ctx['ChuShengNianYue'] = _format_birth(raw.get('ChuShengNianYue', ''))
    ctx['DaoLingNianYue']  = _format_retire_age(raw.get('DaoLingNianYue', ''), birth_ym)
    for key in _TIME6_FIELDS:
        ctx[key] = _format_time6(raw.get(key, ''))
    for key in _TIME8_FIELDS:
        ctx[key] = _format_time8(raw.get(key, ''))
    return ctx
```

- [ ] **Step 2: 提取 _ctx_education_fields() — 学历学位溢出处理**

```python
def _ctx_education_fields(self, raw: dict) -> dict:
    """处理学历/学位字段溢出（超 12 字时的拆分/标记逻辑）。"""
    ctx: dict = {}
    for xueli_key, xuewei_key in [
        (_XUELI_KEY, _XUEWEI_KEY),
        (_ZAIZHI_XUELI_KEY, _ZAIZHI_XUEWEI_KEY),
    ]:
        xueli  = _INVIS.sub('', raw.get(xueli_key,  ''))
        xuewei = _INVIS.sub('', raw.get(xuewei_key, ''))
        if len(xueli) > 12 and not xuewei:
            ctx[xueli_key]  = xueli[:12]
            ctx[xuewei_key] = xueli[12:]
        else:
            ctx[xueli_key]  = xueli
            ctx[xuewei_key] = xuewei
    return ctx
```

- [ ] **Step 3: 提取 _ctx_plain_fields() — 普通字段（escape + 不可见字符清理）**

```python
def _ctx_plain_fields(self, raw: dict, skip_keys: set) -> dict:
    """对未单独处理的字段做 escape + 不可见字符清理。"""
    ctx: dict = {}
    for key, value in raw.items():
        if key in skip_keys:
            continue
        ctx[key] = _html.escape(_INVIS.sub('', value), quote=False)
    return ctx
```

- [ ] **Step 4: 重写 _build_context() 为组合（≤ 35 行）**

```python
def _build_context(self, lrmx: LrmxFile, tpl) -> dict:
    raw = lrmx.as_dict()

    # 各组字段的跳过集合
    SPECIAL_KEYS = {'JianLi', _XUELI_KEY, _XUEWEI_KEY,
                    _ZAIZHI_XUELI_KEY, _ZAIZHI_XUEWEI_KEY,
                    'ZhaoPian', 'ChuShengNianYue', 'DaoLingNianYue',
                    *_TIME6_FIELDS, *_TIME8_FIELDS}

    ctx: dict = {}
    ctx.update(self._ctx_plain_fields(raw, SPECIAL_KEYS))
    ctx.update(self._ctx_time_fields(raw))
    ctx.update(self._ctx_education_fields(raw))
    ctx['ZhaoPian'] = self._decode_photo(raw.get('ZhaoPian', ''), tpl)

    # JianLi
    jianli_raw = _format_jianli_list(raw.get('JianLi', ''))
    jianli = [_html.escape(l, quote=False) for l in jianli_raw]
    self._jianli_line_count = len(jianli)
    self._jianli_lines = jianli_raw
    ctx['JianLi'] = jianli

    # 家庭成员
    family = self._build_family(lrmx)
    for i in range(MAX_FAMILY_SLOTS):
        ctx[f'm{i}'] = family[i] if i < len(family) else dict(_EMPTY_MEMBER)

    # 收集待收缩的纯文本单元格内容
    self._plain_cell_shrink = [
        t for t in (
            _html.unescape(ctx[k]).strip()
            for k in _PLAIN_SHRINK_KEYS
            if isinstance(ctx.get(k), str)
        )
        if t
    ]

    return ctx
```

- [ ] **Step 5: 验证（含现有 docx_exporter 测试）**

```
uv run pytest -q --ignore=tests/test_verify_handler.py
```
Expected: 6 failed（预存）, 100 passed

- [ ] **Step 6: 提交**

```
git add app/core/docx_exporter.py
git commit -m "refactor: 分解 docx_exporter._build_context 为三个字段分组方法"
```

---

## Task 14：分解 docx_exporter._shrink_jianli_cell + _shrink_plain_cells

**Files:**
- Modify: `app/core/docx_exporter.py`

- [ ] **Step 1: 提取 _find_jianli_cells() — 第一阶段：定位简历单元格**

```python
def _find_jianli_cells(self, doc) -> list:
    """扫描文档，返回含简历内容的单元格信息列表。"""
    from typing import NamedTuple

    class _CellInfo(NamedTuple):
        cell: object
        width_emu: int
        height_pt: float

    jianli_cells = []
    seen: set[int] = set()
    for table in doc.tables:
        for row in table.rows:
            row_h_pt = (row.height / _PT_PER_EMU) if row.height else 0.0
            for cell in row.cells:
                if not any(_JIANLI_RENDERED.search(p.text) for p in cell.paragraphs):
                    continue
                cid = id(cell._tc)
                if cid in seen:
                    continue
                seen.add(cid)
                jianli_cells.append(_CellInfo(
                    cell=cell,
                    width_emu=cell.width or 0,
                    height_pt=row_h_pt,
                ))
    return jianli_cells
```

- [ ] **Step 2: 提取 _calc_jianli_target_font() — 第二阶段：计算目标字号**

```python
def _calc_jianli_target_font(self, cell_w: int, cell_h_pt: float) -> tuple[float, float]:
    """返回 (target_pt, target_spacing_pt)。"""
    max_font_pt = _JIANLI_FONT_TIERS[0][1]
    candidates = [
        round(max_font_pt - 0.5 * i, 1)
        for i in range(int((max_font_pt - _MIN_FONT_PT) / 0.5) + 1)
    ]

    if cell_w and cell_h_pt:
        for font_pt in candidates:
            spacing_pt = font_pt + 1.0
            vis = self._estimate_jianli_visual_lines(cell_w, font_pt)
            if vis * spacing_pt <= cell_h_pt:
                return font_pt, spacing_pt
        return _MIN_FONT_PT, _MIN_FONT_PT + 1.0
    else:
        vis = self._jianli_line_count
        for line_limit, font_pt in _JIANLI_FONT_TIERS:
            if vis <= line_limit:
                return font_pt, font_pt + 1.0
        last_pt = _JIANLI_FONT_TIERS[-1][1]
        return last_pt, last_pt + 1.0
```

- [ ] **Step 3: 重写 _shrink_jianli_cell() 为三阶段组合（≤ 25 行）**

```python
def _shrink_jianli_cell(self, doc) -> bool:
    from docx.shared import Pt
    from docx.enum.text import WD_LINE_SPACING

    jianli_cells = self._find_jianli_cells(doc)
    if not jianli_cells:
        return False

    cell_w   = jianli_cells[0].width_emu
    cell_h_pt = jianli_cells[0].height_pt
    target_pt, target_spacing_pt = self._calc_jianli_target_font(cell_w, cell_h_pt)

    max_font_pt = _JIANLI_FONT_TIERS[0][1]
    if target_pt >= max_font_pt:
        return False

    changed = False
    for info in jianli_cells:
        for para in info.cell.paragraphs:
            if _shrink_para_by_1pt(para, target_pt=target_pt):
                changed = True
                para.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
                para.paragraph_format.line_spacing = Pt(target_spacing_pt)
    return changed
```

- [ ] **Step 4: 提取 _calc_plain_cell_target_font() — plain cell 字号计算**

```python
def _calc_plain_cell_target_font(
    self, text: str, cell_w_pt: float, cell_h_pt: float
) -> tuple[float | None, float | None]:
    """返回 (target_pt, target_sp_pt)；无需收缩时返回 (None, None)。"""
    max_font_pt = _JIANLI_FONT_TIERS[0][1]
    candidates = [
        round(max_font_pt - 0.5 * i, 1)
        for i in range(int((max_font_pt - _MIN_FONT_PT) / 0.5) + 1)
    ]
    avail_pt = max(cell_w_pt - 2 * _CELL_MARGIN_PT, 1.0)
    for font_pt in candidates:
        sp_pt = font_pt + 1.0
        vis = max(1, math.ceil(_text_width_pt(text, font_pt) / avail_pt))
        if vis * sp_pt <= cell_h_pt:
            if font_pt >= max_font_pt:
                return None, None
            return font_pt, sp_pt
    return None, None
```

- [ ] **Step 5: 重写 _shrink_plain_cells() 为三阶段组合（≤ 35 行）**

```python
def _shrink_plain_cells(self, doc) -> bool:
    if not self._plain_cell_shrink:
        return False

    from docx.shared import Pt
    from docx.enum.text import WD_LINE_SPACING

    target_set = set(self._plain_cell_shrink)
    changed = False

    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    if not para.runs:
                        continue
                    text = para.text.strip()
                    if not text or text not in target_set:
                        continue

                    cell_w_pt = (cell.width or 0) / _PT_PER_EMU
                    cell_h_emu = self._get_cell_height_emu(cell)
                    cell_h_pt = cell_h_emu / _PT_PER_EMU if cell_h_emu else 0.0

                    if not cell_w_pt or not cell_h_pt:
                        continue

                    target_pt, target_sp_pt = self._calc_plain_cell_target_font(
                        text, cell_w_pt, cell_h_pt
                    )
                    if target_pt is None:
                        continue

                    for run in para.runs:
                        run.font.size = Pt(target_pt)
                    para.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
                    para.paragraph_format.line_spacing = Pt(target_sp_pt)
                    changed = True

    return changed
```

- [ ] **Step 6: 验证**

```
uv run pytest -q --ignore=tests/test_verify_handler.py
```
Expected: 6 failed（预存）, 100 passed

- [ ] **Step 7: 验证方法行数不超过 60 行**

```
uv run python -c "
import ast, pathlib
src = pathlib.Path('app/core/docx_exporter.py').read_text(encoding='utf-8')
tree = ast.parse(src)
long = [(n.end_lineno - n.lineno, n.name, n.lineno)
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.end_lineno - n.lineno >= 60]
long.sort(reverse=True)
for lines, name, lineno in long:
    print(f'L{lineno} {name}: {lines} lines')
"
```
Expected: 无输出（或仅剩 `probe_cell_size` / `export_parallel` 等工具方法，非重构目标）

- [ ] **Step 8: 提交**

```
git add app/core/docx_exporter.py
git commit -m "refactor: 分解 _shrink_jianli_cell 和 _shrink_plain_cells 为阶段方法"
```

---

## 最终验收

- [ ] **运行完整测试套件**

```
uv run pytest -q --ignore=tests/test_verify_handler.py
```
Expected: 6 failed（预存，与重构前完全相同）, 100 passed

- [ ] **验证文件行数**

```
uv run python -c "
import pathlib
files = [
    'app/ui/tabs/verify_tab.py',
    'app/ui/tabs/editor_tab.py',
    'app/ui/tabs/compat_tab.py',
    'app/ui/tabs/convert_tab.py',
    'app/ui/tabs/family_tab.py',
    'app/core/docx_exporter.py',
    'app/ui/workers.py',
    'app/ui/utils.py',
    'app/ui/widgets/flow_layout.py',
    'app/ui/widgets/field_mapping.py',
    'app/ui/widgets/verify_result.py',
    'app/ui/widgets/update_log.py',
    'app/ui/widgets/loading_overlay.py',
]
for f in files:
    p = pathlib.Path(f)
    if p.exists():
        n = sum(1 for _ in p.open(encoding='utf-8'))
        mark = ' ✓' if n <= 900 else ' ✗ OVER'
        if 'verify_tab' in f:
            mark = ' ✓' if n <= 750 else ' ✗ OVER'
        print(f'{n:4d} {f}{mark}')
"
```

- [ ] **验证方法行数（所有文件）**

```
uv run python -c "
import ast, pathlib
for f in pathlib.Path('app').rglob('*.py'):
    src = f.read_text(encoding='utf-8')
    try:
        tree = ast.parse(src)
    except SyntaxError:
        continue
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef):
            lines = n.end_lineno - n.lineno
            if lines >= 60:
                print(f'{f}:{n.lineno} {n.name}: {lines} lines')
"
```
Expected: 仅剩 `probe_cell_size`、`export_parallel`、`_decode_photo` 等原本已是工具函数的方法（非重构目标），其余均 < 60 行
