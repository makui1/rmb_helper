# 任免表编辑器增强 设计文档

## 目标

对现有 `EditorTab` 进行一次综合升级，涵盖：多标签页文档模型、双布局切换、拖放打开、导出 PDF、打印预览、工具栏补全、选中颜色修复、编辑器进入时自动折叠导航栏。

## 架构概述

核心变化是将 `EditorTab` 从**单文档**改为**多文档（MDI-lite）**模型：

- 新增 `_DocPane(QWidget)`：封装单个文档的表单 widget + 状态（`_lrmx`, `_current_path`, `_dirty`）
- `EditorTab` 右侧编辑区换为 `QTabWidget`，每个 tab = 一个 `_DocPane` 实例
- 左侧 `LrmxTreePanel` 保持共享，点击文件触发 `_open_path(path)`
- 工具栏按钮始终操作当前激活的 `_DocPane`（`_active_pane()`）

---

## 一、多标签页 + 文件操作

### 1.1 `_DocPane`

```python
class _DocPane(QWidget):
    dirty_changed = Signal(bool)      # 供 tab 标题显示 *
    path_changed  = Signal(str)       # 供工具栏路径标签更新

    def __init__(self, layout_mode: str = 'b', parent=None): ...
    def load(self, path: str) -> None: ...
    def close_file(self) -> None: ...
    def collect(self) -> None: ...          # 将 widget 值写回 _lrmx
    def save(self) -> bool: ...             # 无路径则触发 save_as
    def save_as(self) -> bool: ...
    def is_dirty(self) -> bool: ...
    def current_path(self) -> str | None: ...
    def lrmx(self) -> LrmxFile | None: ...
```

`_DocPane` 内部用与现有 `EditorTab` 相同的字段 widget，只是布局根据 `layout_mode` 选择（见第二节）。

### 1.2 打开文件逻辑（`EditorTab._open_path`）

```
_open_path(path):
  1. 若已有 tab 打开该路径 → 激活该 tab，return
  2. 否则新建 _DocPane，调用 pane.load(path)
  3. 将 tab 加入 QTabWidget，标题 = 文件名
  4. 将 path 加入左侧 LrmxTreePanel（若不在列表中）
```

### 1.3 各入口汇总

| 入口 | 行为 |
|---|---|
| 左侧文件树点击 | `_open_path(path)` |
| 工具栏「打开」按钮 | `QFileDialog.getOpenFileNames`，多选 → 逐个 `_open_path` |
| 拖放 .lrmx 到右侧内容区 | `dropEvent` → `_open_path(path)` |
| 主窗口 `open_lrmx(path)`（双击文件关联） | `_open_path(path)` |

### 1.4 工具栏按钮状态

所有操作按钮（关闭、保存、另存为、导出PDF、打印）在 `_active_pane()` 为 `None` 时禁用。`QTabWidget.currentChanged` 信号触发按钮状态刷新。

### 1.5 无文件时保存

`_DocPane.save()` 内：若 `_current_path is None` → 调用 `save_as()`（弹文件选择对话框）。

### 1.6 关闭 tab 脏检查

`QTabWidget` 的关闭按钮（`setTabsClosable(True)`）连接到槽：若当前 pane `is_dirty()` → 弹确认对话框（保存 / 不保存 / 取消）。

---

## 二、双布局切换

### 2.1 两种布局

| 模式 | 标识 | 特征 |
|---|---|---|
| 轻量分隔式（默认） | `'b'` | 下划线分隔行，label 左对齐，无格线，现代表单感 |
| 严格表格式 | `'a'` | 全格线，紧贴纸质表格，密度最高 |

### 2.2 切换机制

- 设置项 `editor/layout_mode`（`'b'` 或 `'a'`）存入 `QSettings`
- `SettingsTab` 增加「编辑器布局」单选组（轻量 / 表格）
- 切换时 `EditorTab` 重建所有已开 tab 的 `_DocPane`（保留字段值，只换布局容器）
- `_DocPane` 提供 `rebuild_layout(mode)` 方法：收集当前字段值 → 重建布局 widget → 回填值

### 2.3 两套布局的 widget 复用

两种布局共用同一批输入 widget 实例（`self._xing_ming`, `self._xing_bie` 等），只重建布局容器（`QGridLayout` / `QTableWidget`-like layout），不重新实例化 `QLineEdit`/`QComboBox`。

---

## 三、PDF 导出 + 打印

### 3.1 共用渲染链

```
_DocPane.collect()
  → docx_exporter.export_bytes(lrmx)   # 返回 bytes，不写磁盘
  → pdf_exporter.bytes_to_pdf(docx_bytes, tmp_dir)   # 返回 Path
```

`docx_exporter` 需补充 `export_bytes(lrmx: LrmxFile) -> bytes` 方法（已有 `export()` 写文件，新增内存版本）。

### 3.2 导出 PDF（item 5）

```
渲染链 → 得到临时 pdf_path
→ QFileDialog.getSaveFileName（默认文件名 = 姓名 + 日期.pdf）
→ shutil.copy(pdf_path, dest)
→ 删除临时文件
```

### 3.3 打印（item 6）

```
渲染链 → 得到临时 pdf_path（tempfile.gettempdir()，用户权限，无需管理员）
→ 打开 PrintPreviewDialog（自定义 QDialog）
    - 主体：QtPdf.QPdfView 渲染临时 PDF
    - 底部：「打印…」「取消」按钮
→ 用户点「打印…」→ QPrintDialog → 逐页 QPdfDocument.render() → QPainter → QPrinter
→ 完成或取消 → 删除临时文件
```

**权限说明：** `tempfile.gettempdir()` 返回 `%LOCALAPPDATA%\Temp`，属用户私有目录，读写不需要管理员权限。

### 3.4 `PrintPreviewDialog`

新文件 `app/ui/widgets/print_preview.py`：

```python
class PrintPreviewDialog(QDialog):
    def __init__(self, pdf_path: Path, parent=None): ...
    # 内含 QPdfView + 打印/取消按钮
    # closeEvent 确保删除 pdf_path
```

---

## 四、选中颜色修复（item 7）

在 `app/ui/style.py` QSS 末尾追加：

```css
QLineEdit::selection        { background: #3B82F6; color: #fff; }
QTextEdit::selection        { background: #3B82F6; color: #fff; }
QPlainTextEdit::selection   { background: #3B82F6; color: #fff; }
```

蓝色 `#3B82F6` 与软件强调色（橙红）色相差异足够大，选中文字在白底/深底均清晰可读。

---

## 五、自动折叠导航栏（item 9）

在 `MainWindow._switch_tab` 中：

```python
EDITOR_INDEX = 4

def _switch_tab(self, index: int):
    prev = self._current_index
    self._current_index = index

    if index == EDITOR_INDEX and not self._sidebar_collapsed:
        self._auto_collapsed_for_editor = True
        self.toggle_sidebar()          # 折叠
    elif prev == EDITOR_INDEX and getattr(self, '_auto_collapsed_for_editor', False):
        self._auto_collapsed_for_editor = False
        self.toggle_sidebar()          # 还原展开
    ...
```

- 手动折叠侧边栏后切到编辑器，`_auto_collapsed_for_editor` 不会被置为 True，离开时也不会强制展开
- 标题栏折叠按钮图标沿用现有 `collapse.svg` / `unfold.svg`，无需新增资源

---

## 六、文件结构变更

| 文件 | 变更 |
|---|---|
| `app/ui/tabs/editor_tab.py` | 大幅重构：提取 `_DocPane`，加 `QTabWidget`，加拖放，加工具栏按钮 |
| `app/ui/widgets/print_preview.py` | 新建：`PrintPreviewDialog` |
| `app/core/docx_exporter.py` | 补充 `export_bytes()` 方法 |
| `app/ui/style.py` | 追加 `::selection` QSS |
| `app/ui/main_window.py` | `_switch_tab` 加自动折叠逻辑 |
| `app/ui/tabs/settings_tab.py` | 加「编辑器布局」设置项 |

---

## 七、不在本次范围内

- 标签页拖拽排序
- 标签页分屏/浮动
- 打印页边距自定义
- DaoLingNianYue 自动计算（已在 backlog，单独处理）
