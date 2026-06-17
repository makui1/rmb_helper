# 共享文件面板 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将三个功能 Tab 中各自独立的 lrmx 文件列表抽取为 MainWindow 级别的全局共享面板，并实现无边框窗口自由拖拽调整大小及原生最大化。

**Architecture:** Tab 通过构造器注入接收共享的 `LrmxFilePanel` 引用；MainWindow 将其嵌入水平 `QSplitter`（文件面板左 / `QStackedWidget` 右）；切换 Tab 时根据 `USES_FILE_PANEL` 类属性显隐面板；`busy_changed` 信号在操作期间锁定文件面板；无边框边缘调整由 `QWindow.startSystemResize()` 委托操作系统。

**Tech Stack:** PySide6 6.x（`QSplitter`, `QStackedWidget`, `QWindow.startSystemResize`, `changeEvent`）

---

## 受影响文件一览

| 文件 | 操作 |
|---|---|
| `app/ui/tabs/convert_tab.py` | 修改：注入 file_panel、加 busy_changed、移除内部 LrmxFilePanel + 垂直 QSplitter |
| `app/ui/tabs/compat_tab.py` | 修改：同上 |
| `app/ui/tabs/verify_tab.py` | 修改：注入 file_panel、移动 files_changed 连接、加 busy_changed、移除垂直 QSplitter |
| `app/ui/main_window.py` | 修改：布局改为水平 QSplitter、注入 file_panel、连接 busy_changed、_switch_tab 显隐、边缘调整大小、原生最大化、最小宽度 1100 |

---

## Task 1: ConvertTab — 构造注入 + busy_changed

**Files:**
- Modify: `app/ui/tabs/convert_tab.py`

此任务为纯 UI 重构，无核心逻辑改动，手动启动应用验证即可。

- [ ] **Step 1: 在类顶部添加类属性和信号**

在 `class ConvertTab(QWidget):` 定义体的最开头（`def __init__` 之前）添加：

```python
class ConvertTab(QWidget):
    USES_FILE_PANEL: bool = True
    busy_changed = Signal(bool)
```

- [ ] **Step 2: 修改 `__init__` 签名，改为注入 file_panel**

将当前的：

```python
def __init__(self, parent=None):
    super().__init__(parent)
    self._settings = QSettings('rmb_helper', 'rmb_helper')
    self._worker = None
    self._build_ui()
    self.setAcceptDrops(True)
```

替换为：

```python
def __init__(self, file_panel: 'LrmxFilePanel', parent=None):
    super().__init__(parent)
    self._settings = QSettings('rmb_helper', 'rmb_helper')
    self._worker = None
    self._file_panel = file_panel
    self._build_ui()
    self.setAcceptDrops(True)
```

- [ ] **Step 3: 移除 `_build_ui` 中的垂直 QSplitter 和 LrmxFilePanel 实例化**

当前 `_build_ui` 中（约第 105–119 行）：

```python
        # ── 分割器：上方文件面板 / 下方控件+日志 ──────────────────────────────
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        layout.addWidget(splitter, 1)

        self._file_panel = LrmxFilePanel()
        splitter.addWidget(self._file_panel)

        bottom = QWidget()
        bot_layout = QVBoxLayout(bottom)
        bot_layout.setContentsMargins(0, 0, 0, 0)
        bot_layout.setSpacing(12)
        splitter.addWidget(bottom)

        splitter.setSizes([140, 400])
        splitter.setHandleWidth(4)
```

替换为：

```python
        bot_layout = QVBoxLayout()
        bot_layout.setContentsMargins(0, 0, 0, 0)
        bot_layout.setSpacing(12)
        layout.addLayout(bot_layout, 1)
```

- [ ] **Step 4: 清理不再使用的 import**

`convert_tab.py` 顶部 imports 中移除 `QSplitter`（因为垂直 QSplitter 已删除）和 `LrmxFilePanel` 的直接实例化不再需要，但类型注解还需要它，所以保留 `from app.ui.widgets.file_panel import LrmxFilePanel`。只需移除 `QSplitter` from the `QWidget` import list：

```python
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QCheckBox, QLineEdit, QComboBox, QTextEdit,
    QFileDialog, QSizePolicy,
)
```

- [ ] **Step 5: 在 `_run` 中发射 `busy_changed(True)`**

在 `_run` 方法中，`self._worker.start()` 之前添加一行：

当前末尾为：
```python
        self._worker.log.connect(self._append_log)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()
```

改为：
```python
        self._worker.log.connect(self._append_log)
        self._worker.finished.connect(self._on_finished)
        self.busy_changed.emit(True)
        self._worker.start()
```

- [ ] **Step 6: 在 `_on_finished` 中发射 `busy_changed(False)`**

当前：
```python
    def _on_finished(self, done: int, total: int, elapsed: float):
        self._run_btn.setEnabled(True)
        self._append_log(f'完成 {done}/{total}，耗时 {elapsed:.1f}s')
```

改为：
```python
    def _on_finished(self, done: int, total: int, elapsed: float):
        self._run_btn.setEnabled(True)
        self.busy_changed.emit(False)
        self._append_log(f'完成 {done}/{total}，耗时 {elapsed:.1f}s')
```

- [ ] **Step 7: Commit**

```
git add app/ui/tabs/convert_tab.py
git commit -m "refactor: ConvertTab 接受注入的 file_panel，添加 busy_changed 信号"
```

---

## Task 2: CompatTab — 构造注入 + busy_changed

**Files:**
- Modify: `app/ui/tabs/compat_tab.py`

- [ ] **Step 1: 在类顶部添加类属性和信号**

在 `class CompatTab(QWidget):` 定义体最开头添加：

```python
class CompatTab(QWidget):
    USES_FILE_PANEL: bool = True
    busy_changed = Signal(bool)
```

- [ ] **Step 2: 修改 `__init__` 签名**

将当前的：

```python
    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._log_entries: list[tuple[str, str]] = []
        self._active_filter = 'all'
        self._build_ui()
        self.setAcceptDrops(True)
```

替换为：

```python
    def __init__(self, file_panel: 'LrmxFilePanel', parent=None):
        super().__init__(parent)
        self._worker = None
        self._log_entries: list[tuple[str, str]] = []
        self._active_filter = 'all'
        self._file_panel = file_panel
        self._build_ui()
        self.setAcceptDrops(True)
```

- [ ] **Step 3: 移除 `_build_ui` 中的垂直 QSplitter 和 LrmxFilePanel 实例化**

当前（约第 88–102 行）：

```python
        # ── 分割器：上方文件面板 / 下方控件+日志 ──────────────────────────────
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        layout.addWidget(splitter, 1)

        self._file_panel = LrmxFilePanel()
        splitter.addWidget(self._file_panel)

        bottom = QWidget()
        bot_layout = QVBoxLayout(bottom)
        bot_layout.setContentsMargins(0, 0, 0, 0)
        bot_layout.setSpacing(12)
        splitter.addWidget(bottom)

        splitter.setSizes([140, 400])
        splitter.setHandleWidth(4)
```

替换为：

```python
        bot_layout = QVBoxLayout()
        bot_layout.setContentsMargins(0, 0, 0, 0)
        bot_layout.setSpacing(12)
        layout.addLayout(bot_layout, 1)
```

- [ ] **Step 4: 清理不再使用的 import**

从 `QWidget` import list 中移除 `QSplitter`。保留 `from app.ui.widgets.file_panel import LrmxFilePanel`（用于类型注解）。

修改后 imports 第一段为：

```python
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListWidget, QListWidgetItem,
    QCheckBox, QLineEdit, QComboBox, QTextEdit,
    QFileDialog, QFrame,
)
```

- [ ] **Step 5: 在 `_run` 中发射 `busy_changed(True)`**

在 `_run` 末尾的 `self._worker.start()` 之前插入：

```python
        self._worker.log.connect(self._append_log)
        self._worker.finished.connect(self._on_finished)
        self.busy_changed.emit(True)
        self._worker.start()
```

- [ ] **Step 6: 在 `_on_finished` 中发射 `busy_changed(False)`**

当前：
```python
    def _on_finished(self, processed: int, total: int):
        self._run_btn.setEnabled(True)
        self._append_log(f'── 完成：共 {total} 个文件，处理 {processed} 个 ──')
```

改为：
```python
    def _on_finished(self, processed: int, total: int):
        self._run_btn.setEnabled(True)
        self.busy_changed.emit(False)
        self._append_log(f'── 完成：共 {total} 个文件，处理 {processed} 个 ──')
```

- [ ] **Step 7: Commit**

```
git add app/ui/tabs/compat_tab.py
git commit -m "refactor: CompatTab 接受注入的 file_panel，添加 busy_changed 信号"
```

---

## Task 3: VerifyTab — 构造注入 + busy_changed

**Files:**
- Modify: `app/ui/tabs/verify_tab.py`

VerifyTab 有两个后台 Worker（核验 + 更新），两者都需要发射 `busy_changed`。错误路径 `_on_update_critical` 也需要发射 `False`。

- [ ] **Step 1: 在类顶部添加类属性和信号**

在 `class VerifyTab(QWidget):` 定义体最开头添加：

```python
class VerifyTab(QWidget):
    USES_FILE_PANEL: bool = True
    busy_changed = Signal(bool)
```

- [ ] **Step 2: 修改 `__init__` 签名，移动 `files_changed` 连接**

将当前的：

```python
    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._update_worker = None
        self._settings = QSettings('rmb_helper', 'rmb_helper')
        self._counts = {'ok': 0, 'diff': 0, 'not_found': 0, 'error': 0}
        self._active_filter: str | None = None
        self._result_rows: list[_ResultRow] = []
        self._update_counts = {'ok': 0, 'not_found': 0, 'error': 0}
        self._update_log_rows: list[_UpdateLogRow] = []
        self._update_active_filter: str | None = None
        self._build_ui()
        self.setAcceptDrops(True)
```

替换为：

```python
    def __init__(self, file_panel: 'LrmxFilePanel', parent=None):
        super().__init__(parent)
        self._worker = None
        self._update_worker = None
        self._settings = QSettings('rmb_helper', 'rmb_helper')
        self._counts = {'ok': 0, 'diff': 0, 'not_found': 0, 'error': 0}
        self._active_filter: str | None = None
        self._result_rows: list[_ResultRow] = []
        self._update_counts = {'ok': 0, 'not_found': 0, 'error': 0}
        self._update_log_rows: list[_UpdateLogRow] = []
        self._update_active_filter: str | None = None
        self._file_panel = file_panel
        self._build_ui()
        self._file_panel.files_changed.connect(self._on_files_changed)
        self.setAcceptDrops(True)
```

- [ ] **Step 3: 移除 `_build_ui` 中的垂直 QSplitter、LrmxFilePanel 实例化和 files_changed 连接**

找到 `_build_ui` 中（约第 777–793 行）的这段：

```python
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
```

替换为：

```python
        bottom_pane = QWidget()
        bot_layout = QVBoxLayout(bottom_pane)
        bot_layout.setContentsMargins(0, 0, 0, 0)
        bot_layout.setSpacing(12)
        sp.addWidget(bottom_pane, 1)
```

- [ ] **Step 4: 清理不再使用的 import**

从 `PySide6.QtWidgets` import list 中移除 `QSplitter`。保留 `LrmxFilePanel` import（用于类型注解）：

```python
from app.ui.widgets.file_panel import LrmxFilePanel
```

应保留（在文件顶部已有此行，检查确认即可）。

- [ ] **Step 5: 在 `_run` 中发射 `busy_changed(True)`**

`_run` 方法末尾（约第 1184–1187 行），在 `self._worker.start()` 前插入：

```python
        self._worker = _VerifyWorker(handler)
        self._worker.result_ready.connect(self._on_result)
        self._worker.finished.connect(self._on_finished)
        self.busy_changed.emit(True)
        self._worker.start()
```

- [ ] **Step 6: 在 `_on_finished` 中发射 `busy_changed(False)`**

当前：
```python
    def _on_finished(self):
        QTimer.singleShot(400, self._loading_overlay.hide)
        self._update_export_btn()
```

改为：
```python
    def _on_finished(self):
        self.busy_changed.emit(False)
        QTimer.singleShot(400, self._loading_overlay.hide)
        self._update_export_btn()
```

- [ ] **Step 7: 在 `_run_update` 中发射 `busy_changed(True)`**

`_run_update` 末尾（约第 1253–1256 行），在 `self._update_worker.start()` 前插入：

```python
        self._update_worker.log.connect(self._on_update_log)
        self._update_worker.critical.connect(self._on_update_critical)
        self._update_worker.finished.connect(self._on_update_finished)
        self.busy_changed.emit(True)
        self._update_worker.start()
```

- [ ] **Step 8: 在 `_on_update_finished` 中发射 `busy_changed(False)`**

当前：
```python
    def _on_update_finished(self):
        QTimer.singleShot(400, self._update_loading_overlay.hide)
        ok = self._update_counts['ok']
        ...
```

改为：
```python
    def _on_update_finished(self):
        self.busy_changed.emit(False)
        QTimer.singleShot(400, self._update_loading_overlay.hide)
        ok = self._update_counts['ok']
        ...
```

- [ ] **Step 9: 在 `_on_update_critical` 中发射 `busy_changed(False)`**

当前：
```python
    def _on_update_critical(self, msg: str):
        self._update_loading_overlay.hide()
        QMessageBox.critical(self, 'Excel 读取失败', msg)
        self._back_to_setup()
```

改为：
```python
    def _on_update_critical(self, msg: str):
        self.busy_changed.emit(False)
        self._update_loading_overlay.hide()
        QMessageBox.critical(self, 'Excel 读取失败', msg)
        self._back_to_setup()
```

- [ ] **Step 10: Commit**

```
git add app/ui/tabs/verify_tab.py
git commit -m "refactor: VerifyTab 接受注入的 file_panel，添加 busy_changed 信号"
```

---

## Task 4: MainWindow — 布局重构 + 边缘调整大小 + 原生最大化

**Files:**
- Modify: `app/ui/main_window.py`

这是变更最大的一个任务，分步骤进行以减少出错。

- [ ] **Step 1: 添加 import**

在文件顶部，将：

```python
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QStackedWidget, QFrame,
)
from PySide6.QtCore import Qt, QPoint, QRect, QSize
```

改为：

```python
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QStackedWidget, QFrame, QSplitter,
)
from PySide6.QtCore import Qt, QPoint, QSize, QEvent
from app.ui.widgets.file_panel import LrmxFilePanel
```

（移除 `QRect`，添加 `QSplitter`、`QEvent`、`LrmxFilePanel`）

- [ ] **Step 2: 修改 `MainWindow.__init__`**

将当前的：

```python
    def __init__(self):
        super().__init__()
        self.setWindowTitle('干部任免审批表管理工具')
        self.setMinimumSize(900, 700)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setWindowIcon(QIcon(str(_ASSETS / 'icon.ico')))
        self.setStyleSheet(QSS)
        self._sidebar_container: QWidget | None = None
        self._title_bar: _TitleBar | None = None
        self._pseudo_maximized: bool = False
        self._restore_geometry: QRect | None = None
        self._build_ui()
```

替换为：

```python
    def __init__(self):
        super().__init__()
        self.setWindowTitle('干部任免审批表管理工具')
        self.setMinimumSize(1100, 700)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setWindowIcon(QIcon(str(_ASSETS / 'icon.ico')))
        self.setStyleSheet(QSS)
        self.setMouseTracking(True)
        self._sidebar_container: QWidget | None = None
        self._title_bar: _TitleBar | None = None
        self._file_panel: LrmxFilePanel | None = None
        self._build_ui()
```

- [ ] **Step 3: 修改 `_build_ui` — 实例化 Tab 时注入 file_panel，包裹在水平 QSplitter 中**

找到当前的（约第 202–214 行）：

```python
        # 内容区
        from app.ui.tabs.convert_tab import ConvertTab
        from app.ui.tabs.compat_tab import CompatTab
        from app.ui.tabs.verify_tab import VerifyTab

        self._stack = QStackedWidget()
        self._stack.addWidget(ConvertTab())   # index 0 → 批量转换
        self._stack.addWidget(CompatTab())    # index 1 → 版本兼容
        self._stack.addWidget(VerifyTab())    # index 2 → 批量核验
        self._stack.addWidget(SettingsTab())  # index 3 → 设置

        body_layout.addWidget(sidebar_container)
        body_layout.addWidget(self._stack)
```

替换为：

```python
        # 内容区
        from app.ui.tabs.convert_tab import ConvertTab
        from app.ui.tabs.compat_tab import CompatTab
        from app.ui.tabs.verify_tab import VerifyTab

        self._file_panel = LrmxFilePanel()
        self._file_panel.setMinimumWidth(180)

        convert_tab = ConvertTab(self._file_panel)
        compat_tab = CompatTab(self._file_panel)
        verify_tab = VerifyTab(self._file_panel)

        self._stack = QStackedWidget()
        self._stack.addWidget(convert_tab)    # index 0 → 批量转换
        self._stack.addWidget(compat_tab)     # index 1 → 版本兼容
        self._stack.addWidget(verify_tab)     # index 2 → 批量核验
        self._stack.addWidget(SettingsTab())  # index 3 → 设置

        for tab in (convert_tab, compat_tab, verify_tab):
            tab.busy_changed.connect(lambda busy: self._file_panel.setEnabled(not busy))

        content_splitter = QSplitter(Qt.Orientation.Horizontal)
        content_splitter.setChildrenCollapsible(False)
        content_splitter.setHandleWidth(4)
        content_splitter.addWidget(self._file_panel)
        content_splitter.addWidget(self._stack)
        content_splitter.setSizes([220, 700])

        body_layout.addWidget(sidebar_container)
        body_layout.addWidget(content_splitter, 1)
```

- [ ] **Step 4: 修改 `_switch_tab` — 切换时显隐文件面板**

将当前的：

```python
    def _switch_tab(self, index: int):
        self._stack.setCurrentIndex(index)
        for i, btn in enumerate(self._nav_btns):
            btn.setChecked(i == index)
```

替换为：

```python
    def _switch_tab(self, index: int):
        self._stack.setCurrentIndex(index)
        for i, btn in enumerate(self._nav_btns):
            btn.setChecked(i == index)
        if self._file_panel:
            widget = self._stack.widget(index)
            self._file_panel.setVisible(getattr(widget, 'USES_FILE_PANEL', False))
```

- [ ] **Step 5: 替换 `toggle_maximize` — 改为原生最大化**

将当前的整个 `toggle_maximize` 方法（含 `_SIDEBAR_W_NORMAL`、`_SIDEBAR_W_MAX` 常量）：

```python
    def toggle_maximize(self):
        if self._pseudo_maximized:
            if self._restore_geometry:
                self.setGeometry(self._restore_geometry)
            self._pseudo_maximized = False
        else:
            self._restore_geometry = self.geometry()
            self.setGeometry(self.screen().availableGeometry())
            self._pseudo_maximized = True
        if self._title_bar:
            self._title_bar.set_maximized(self._pseudo_maximized)
        if self._sidebar_container:
            w = self._SIDEBAR_W_MAX if self._pseudo_maximized else self._SIDEBAR_W_NORMAL
            self._sidebar_container.setFixedWidth(w)

    _SIDEBAR_W_NORMAL = 172
    _SIDEBAR_W_MAX    = 250
```

替换为：

```python
    def toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()
```

- [ ] **Step 6: 添加 `changeEvent` — 同步最大化图标**

在 `toggle_maximize` 之后添加：

```python
    def changeEvent(self, event):
        if event.type() == QEvent.Type.WindowStateChange and self._title_bar:
            self._title_bar.set_maximized(self.isMaximized())
        super().changeEvent(event)
```

- [ ] **Step 7: 添加边缘检测辅助方法和光标映射**

在 `changeEvent` 之后添加：

```python
    _RESIZE_MARGIN = 8

    _CURSOR_MAP = {
        Qt.Edge.LeftEdge:                                Qt.CursorShape.SizeHorCursor,
        Qt.Edge.RightEdge:                               Qt.CursorShape.SizeHorCursor,
        Qt.Edge.TopEdge:                                 Qt.CursorShape.SizeVerCursor,
        Qt.Edge.BottomEdge:                              Qt.CursorShape.SizeVerCursor,
        Qt.Edge.LeftEdge  | Qt.Edge.TopEdge:             Qt.CursorShape.SizeFDiagCursor,
        Qt.Edge.RightEdge | Qt.Edge.BottomEdge:          Qt.CursorShape.SizeFDiagCursor,
        Qt.Edge.RightEdge | Qt.Edge.TopEdge:             Qt.CursorShape.SizeBDiagCursor,
        Qt.Edge.LeftEdge  | Qt.Edge.BottomEdge:          Qt.CursorShape.SizeBDiagCursor,
    }

    def _edge_at(self, pos: QPoint) -> Qt.Edges:
        x, y, w, h = pos.x(), pos.y(), self.width(), self.height()
        m = self._RESIZE_MARGIN
        edges = Qt.Edges()
        if x < m:      edges |= Qt.Edge.LeftEdge
        if x > w - m:  edges |= Qt.Edge.RightEdge
        if y < m:      edges |= Qt.Edge.TopEdge
        if y > h - m:  edges |= Qt.Edge.BottomEdge
        return edges
```

- [ ] **Step 8: 添加 `mousePressEvent` 和 `mouseMoveEvent`**

紧接着添加：

```python
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            edges = self._edge_at(event.position().toPoint())
            if edges:
                self.windowHandle().startSystemResize(edges)
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        edges = self._edge_at(event.position().toPoint())
        self.setCursor(self._CURSOR_MAP.get(edges, Qt.CursorShape.ArrowCursor))
        super().mouseMoveEvent(event)
```

- [ ] **Step 9: 修改 `_TitleBar.mousePressEvent` — 使用 `isMaximized()` 替代 `_pseudo_maximized`**

将当前的：

```python
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = (
                event.globalPosition().toPoint() - self._win.frameGeometry().topLeft()
            )
            self._drag_from_maximized = self._win._pseudo_maximized
        super().mousePressEvent(event)
```

替换为：

```python
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = (
                event.globalPosition().toPoint() - self._win.frameGeometry().topLeft()
            )
            self._drag_from_maximized = self._win.isMaximized()
        super().mousePressEvent(event)
```

- [ ] **Step 10: 修改 `_TitleBar.mouseMoveEvent` — 使用 `showNormal()` 替代 `toggle_maximize()`**

将当前的：

```python
        if self._drag_from_maximized:
            # Restore and recompute drag offset so cursor stays at the same
            # horizontal ratio within the restored title bar.
            ratio = self._drag_pos.x() / max(self._win.width(), 1)
            self._win.toggle_maximize()
            self._drag_pos = QPoint(
                int(ratio * self._win.width()),
                self._drag_pos.y(),
            )
            self._drag_from_maximized = False
```

替换为：

```python
        if self._drag_from_maximized:
            ratio = self._drag_pos.x() / max(self._win.width(), 1)
            self._win.showNormal()
            self._drag_pos = QPoint(
                int(ratio * self._win.width()),
                self._drag_pos.y(),
            )
            self._drag_from_maximized = False
```

- [ ] **Step 11: 删除 `toggle_sidebar` 中对 `_pseudo_maximized` 的引用（如有）**

检查 `toggle_sidebar` 方法，确认其中没有引用 `_pseudo_maximized`。当前代码（第 236–241 行）只涉及 `_sidebar_container` 的显隐，无须修改。

- [ ] **Step 12: 手动启动应用验证**

```
uv run python -m app
```

验证清单：
- 启动后窗口宽度≥1100px，文件面板在侧边栏右侧显示
- 拖动文件面板和内容区之间的分割线可调整宽度
- 切换到「设置」Tab，文件面板消失；切到其他 Tab，文件面板恢复
- 拖到文件列表中，三个功能 Tab 共享同一批文件
- 开始转换/兼容/核验时，文件面板变灰无法操作；完成后恢复
- 点击最大化按钮，窗口原生最大化；再次点击还原（图标正确切换）
- 拖动标题栏从最大化状态拖出，窗口按比例还原位置
- 拖动窗口边缘/角落可自由调整大小，光标在边缘变为方向箭头

- [ ] **Step 13: Commit**

```
git add app/ui/main_window.py
git commit -m "refactor: 全局共享 LrmxFilePanel，实现边缘调整大小和原生最大化"
```
