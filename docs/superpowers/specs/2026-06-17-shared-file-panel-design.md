# 共享 LrmxFilePanel 设计文档

**目标：** 将三个功能 Tab（ConvertTab / CompatTab / VerifyTab）中各自独立的 lrmx 文件列表抽取为 MainWindow 级别的全局共享面板，同时实现无边框窗口的自由拖拽调整大小，以及用系统原生最大化替换当前的伪最大化逻辑。

**架构：** 全局文件面板固定嵌入在侧边栏与内容 QStackedWidget 之间，通过构造器注入的方式将引用传递给各 Tab；Tab 通过类属性声明自己是否需要文件面板，MainWindow 在切换 Tab 时自动显示或隐藏。

---

## 一、全局文件面板布局

### 1.1 当前布局

```
[TitleBar]
[sidebar_container (172px fixed)] | [QStackedWidget]
```

每个 Tab 内部都有一个垂直 `QSplitter`：上半部为 `LrmxFilePanel`，下半部为控件+日志。

### 1.2 目标布局

```
[TitleBar]
[sidebar_container (172px fixed)] | [QSplitter(水平)]
                                        ├─ LrmxFilePanel（min 180px，可拖动）
                                        └─ QStackedWidget（stretch=1）
```

- `QSplitter` 方向：`Qt.Orientation.Horizontal`
- `LrmxFilePanel` 最小宽度设为 180px，不可折叠（`setChildrenCollapsible(False)`）
- 初始分配宽度建议：`splitter.setSizes([220, remaining])`（在 `_build_ui` 末尾调用，`remaining` 由总宽减去侧边栏和文件面板估算）

### 1.3 MainWindow._build_ui 变更要点

```python
# 1. 实例化文件面板
self._file_panel = LrmxFilePanel()
self._file_panel.setMinimumWidth(180)

# 2. 用 QSplitter 包裹文件面板与 stack
from PySide6.QtWidgets import QSplitter
content_splitter = QSplitter(Qt.Orientation.Horizontal)
content_splitter.setChildrenCollapsible(False)
content_splitter.setHandleWidth(4)
content_splitter.addWidget(self._file_panel)
content_splitter.addWidget(self._stack)
content_splitter.setSizes([220, 700])

# 3. body_layout 中用 content_splitter 替换原来的 self._stack
body_layout.addWidget(sidebar_container)
body_layout.addWidget(content_splitter, 1)
```

---

## 二、Tab 协议

### 2.1 类属性 `USES_FILE_PANEL`

每个 Tab 声明一个类属性：

```python
class ConvertTab(QWidget):
    USES_FILE_PANEL: bool = True

class CompatTab(QWidget):
    USES_FILE_PANEL: bool = True

class VerifyTab(QWidget):
    USES_FILE_PANEL: bool = True

class SettingsTab(QWidget):
    USES_FILE_PANEL: bool = False  # 或省略，默认 False
```

不使用文件面板的 Tab 可以省略该属性，`getattr(widget, 'USES_FILE_PANEL', False)` 保证向后兼容。

### 2.2 构造器注入

MainWindow 在 `_build_ui` 中将 `self._file_panel` 传入各 Tab：

```python
self._stack.addWidget(ConvertTab(self._file_panel))   # index 0
self._stack.addWidget(CompatTab(self._file_panel))    # index 1
self._stack.addWidget(VerifyTab(self._file_panel))    # index 2
self._stack.addWidget(SettingsTab())                  # index 3（无文件面板）
```

各 Tab 的 `__init__` 签名变为：

```python
def __init__(self, file_panel: LrmxFilePanel, parent=None):
    super().__init__(parent)
    self._file_panel = file_panel
    ...
```

Tab 内部**不再**实例化 `LrmxFilePanel()`，也不再需要包裹文件面板的垂直 `QSplitter`；控件+日志区直接填满 Tab 全高。

### 2.3 VerifyTab 的信号连接

VerifyTab 当前在内部实例化后立即连接 `file_panel.files_changed`，注入后改为在 `__init__` 中连接：

```python
def __init__(self, file_panel: LrmxFilePanel, parent=None):
    super().__init__(parent)
    self._file_panel = file_panel
    self._file_panel.files_changed.connect(self._on_files_changed)
    ...
```

### 2.4 拖放（drag & drop）

各 Tab 的 `dropEvent` 继续调用 `self._file_panel.add_file()` / `self._file_panel._scan_and_add()`，逻辑不变。

---

## 三、Tab 切换时显示/隐藏文件面板

```python
def _switch_tab(self, index: int):
    self._stack.setCurrentIndex(index)
    for i, btn in enumerate(self._nav_btns):
        btn.setChecked(i == index)
    widget = self._stack.widget(index)
    self._file_panel.setVisible(getattr(widget, 'USES_FILE_PANEL', False))
```

文件面板隐藏时，`QSplitter` 自动将剩余空间让给 `QStackedWidget`，无需额外处理。

---

## 四、操作期间锁定文件面板

### 4.1 信号定义

每个使用文件面板的 Tab 声明：

```python
from PySide6.QtCore import Signal

class ConvertTab(QWidget):
    busy_changed = Signal(bool)
```

### 4.2 信号连接（MainWindow 侧）

```python
for tab in (convert_tab, compat_tab, verify_tab):
    tab.busy_changed.connect(lambda busy: self._file_panel.setEnabled(not busy))
```

### 4.3 Tab 内部发射时机

以 ConvertTab 为例：

```python
def _run(self):
    ...
    self.busy_changed.emit(True)   # 开始前锁定
    self._worker.finished.connect(self._on_finished)
    self._worker.start()

def _on_finished(self, done, total, elapsed):
    self._run_btn.setEnabled(True)
    self.busy_changed.emit(False)  # 完成后解锁
    ...
```

VerifyTab 中核验和更新两个操作都需要发射，错误路径（`except` 块）也要保证发射 `False`。

---

## 五、最小窗口宽度调整

```python
# 当前
self.setMinimumSize(900, 700)

# 变更后
self.setMinimumSize(1100, 700)
```

---

## 六、无边框窗口自由调整大小

### 6.1 方案

使用 `QWindow.startSystemResize(Qt.Edges)` 将调整逻辑委托给操作系统。该 API 自 Qt 5.15 起在 Windows / macOS / Linux 上均可用，无需平台特定代码。

### 6.2 边缘检测

在 `MainWindow` 上重写三个事件方法，检测区域为距窗口边缘 8px 的边框带：

```python
_RESIZE_MARGIN = 8

def _edge_at(self, pos: QPoint) -> Qt.Edges:
    x, y, w, h = pos.x(), pos.y(), self.width(), self.height()
    m = self._RESIZE_MARGIN
    left   = x < m
    right  = x > w - m
    top    = y < m
    bottom = y > h - m
    edges = Qt.Edges()
    if left:   edges |= Qt.Edge.LeftEdge
    if right:  edges |= Qt.Edge.RightEdge
    if top:    edges |= Qt.Edge.TopEdge
    if bottom: edges |= Qt.Edge.BottomEdge
    return edges
```

### 6.3 鼠标事件

```python
_CURSOR_MAP = {
    Qt.Edge.LeftEdge:                              Qt.CursorShape.SizeHorCursor,
    Qt.Edge.RightEdge:                             Qt.CursorShape.SizeHorCursor,
    Qt.Edge.TopEdge:                               Qt.CursorShape.SizeVerCursor,
    Qt.Edge.BottomEdge:                            Qt.CursorShape.SizeVerCursor,
    Qt.Edge.LeftEdge  | Qt.Edge.TopEdge:           Qt.CursorShape.SizeFDiagCursor,
    Qt.Edge.RightEdge | Qt.Edge.BottomEdge:        Qt.CursorShape.SizeFDiagCursor,
    Qt.Edge.RightEdge | Qt.Edge.TopEdge:           Qt.CursorShape.SizeBDiagCursor,
    Qt.Edge.LeftEdge  | Qt.Edge.BottomEdge:        Qt.CursorShape.SizeBDiagCursor,
}

def mousePressEvent(self, event):
    if event.button() == Qt.MouseButton.LeftButton:
        edges = self._edge_at(event.position().toPoint())
        if edges:
            self.windowHandle().startSystemResize(edges)
            return
    super().mousePressEvent(event)

def mouseMoveEvent(self, event):
    edges = self._edge_at(event.position().toPoint())
    cursor = self._CURSOR_MAP.get(edges, Qt.CursorShape.ArrowCursor)
    self.setCursor(cursor)
    super().mouseMoveEvent(event)
```

`MainWindow` 需设置 `setMouseTracking(True)` 以便在不按下鼠标时也能收到 `mouseMoveEvent` 更新光标。

### 6.4 注意事项

- 标题栏自身已消耗鼠标事件，上边缘检测只有当鼠标在标题栏**外**（即真正的窗口顶部像素）时才生效；标题栏高度 30px，8px 重叠范围极小，实际使用中无冲突。
- 最大化状态下禁用 resize（操作系统层面已自动处理，`startSystemResize` 在最大化时无效果）。

---

## 七、用原生最大化替换伪最大化

### 7.1 当前实现

`MainWindow` 持有 `_pseudo_maximized: bool` 和 `_restore_geometry: QRect | None`，`toggle_maximize()` 通过 `setGeometry(screen().availableGeometry())` 手动铺满屏幕，并同步调整侧边栏宽度。

### 7.2 目标实现

改用系统 API：

```python
def toggle_maximize(self):
    if self.isMaximized():
        self.showNormal()
    else:
        self.showMaximized()
```

移除 `_pseudo_maximized`、`_restore_geometry` 及相关的 `_SIDEBAR_W_MAX` 逻辑（最大化后侧边栏宽度无需手动调整，布局自动伸展）。

### 7.3 图标同步

覆写 `changeEvent` 以响应系统最大化/还原（包括 Win+↑、Snap 等手势）：

```python
def changeEvent(self, event):
    from PySide6.QtCore import QEvent
    if event.type() == QEvent.Type.WindowStateChange and self._title_bar:
        self._title_bar.set_maximized(self.isMaximized())
    super().changeEvent(event)
```

### 7.4 标题栏拖动时的还原

`_TitleBar.mouseMoveEvent` 中当前判断 `self._drag_from_maximized` 并调用 `toggle_maximize()`，修改为：

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

`_drag_from_maximized` 的赋值改为 `self._win.isMaximized()`（替换 `self._win._pseudo_maximized`）。

---

## 受影响的文件清单

| 文件 | 变更类型 | 要点 |
|---|---|---|
| `app/ui/main_window.py` | 重构 | 布局改为水平 QSplitter；实例化文件面板；注入各 Tab；`_switch_tab` 显隐面板；连接 `busy_changed`；`toggle_maximize` 改为系统 API；`changeEvent` 同步图标；`mousePressEvent/mouseMoveEvent` 实现边缘检测；`setMouseTracking(True)`；最小宽度改 1100px |
| `app/ui/tabs/convert_tab.py` | 重构 | 加 `USES_FILE_PANEL = True`、`busy_changed` Signal；`__init__` 接受 `file_panel` 参数；移除内部 `LrmxFilePanel()` 及垂直 QSplitter；`_run`/`_on_finished` 发射 `busy_changed` |
| `app/ui/tabs/compat_tab.py` | 重构 | 同 ConvertTab |
| `app/ui/tabs/verify_tab.py` | 重构 | 同上；连接 `files_changed` 信号改到 `__init__`；核验和更新两个 Worker 都需发射 `busy_changed` |
| `app/ui/tabs/settings_tab.py` | 微改 | 可加 `USES_FILE_PANEL = False`（也可省略） |
| `app/ui/widgets/file_panel.py` | 可能不变 | 接口不变；若需调整样式可修改 |
