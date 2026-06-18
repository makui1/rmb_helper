# 文件面板 Delegate 优化 Implementation Design

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 用 `QStyledItemDelegate` 替换 `_FileRow` QWidget，消除批量加载时为每行创建实体 Widget 的开销，使大文件夹拖入速度明显提升。

**Background:** 当前 `LrmxFilePanel` 为每个文件调用 `setItemWidget()` 挂载一个 `_FileRow`（含 QHBoxLayout + QLabel + QPushButton），200 个文件 = 600+ Qt 对象创建 + 600+ 布局计算。Delegate 方案让列表只存字符串数据，绘制由 `paint()` 完成，加载时无额外对象创建。

---

## Section 1：数据与结构

**删除：**
- `_FileRow` 类（整体移除）

**新增：**
- `_RowDelegate(QStyledItemDelegate)` — 负责绘制每一行

**保留不变：**
- `_FileList(QListWidget)` — 空列表提示、drag & drop，新增 mouse tracking
- `LrmxFilePanel` 公共接口：`add_file()`、`files()`、`count()`、`files_changed` signal

**`add_file()` 变化：**
```python
def add_file(self, path: str, _emit: bool = True):
    if path in self._path_set:
        return
    self._path_set.add(path)
    item = QListWidgetItem(Path(path).name)       # 文本存 name
    item.setData(Qt.ItemDataRole.UserRole, path)  # UserRole 存完整路径
    item.setSizeHint(QSize(0, 34))
    self._list.addItem(item)
    if _emit:
        self.files_changed.emit(self.files())
```

不再调用 `setItemWidget()`。

---

## Section 2：_RowDelegate 绘制

### 行布局（行高 34px）

```
[10px] [icon 16×16] [8px] [文件名 expanding] [× 区域 30px] [8px]
```

### paint() 实现要点

```python
class _RowDelegate(QStyledItemDelegate):
    _ICON: QIcon          # 初始化时从 rmb.svg 加载，全局复用
    _SEP_NORMAL = QColor('#E8E6E0')
    _SEP_HOVER  = QColor('#1A1A1A')
    _DEL_ZONE_W = 30      # × 按钮区域宽度（px）

    remove_requested = Signal(str)  # 携带完整路径

    def __init__(self, hovered_getter, parent=None): ...

    def paint(self, painter, option, index):
        path = index.data(Qt.ItemDataRole.UserRole)
        name = index.data(Qt.ItemDataRole.DisplayRole)
        is_hovered = (index == self._hovered_index)

        # 1. 图标（左侧固定位置）
        icon_rect = QRect(option.rect.x() + 10, option.rect.y() + 9, 16, 16)
        self._ICON.paint(painter, icon_rect)

        # 2. 文件名（居中可伸缩，ElideRight 截断）
        del_zone_w = self._DEL_ZONE_W if is_hovered else 0
        text_rect = option.rect.adjusted(36, 0, -(del_zone_w + 8), 0)
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.TextSingleLine,
                         painter.fontMetrics().elidedText(name, Qt.ElideRight, text_rect.width()))

        # 3. 分隔线（底部）
        sep_color = self._SEP_HOVER if is_hovered else self._SEP_NORMAL
        painter.setPen(QPen(sep_color, 1))
        y = option.rect.bottom()
        painter.drawLine(option.rect.x() + 10, y, option.rect.right() - 10, y)

        # 4. × 按钮（仅 hovered 行显示）
        if is_hovered:
            del_rect = QRect(option.rect.right() - self._DEL_ZONE_W,
                             option.rect.y(), self._DEL_ZONE_W, option.rect.height())
            painter.setPen(QColor('#888'))
            painter.drawText(del_rect, Qt.AlignCenter, '×')
```

### editorEvent() — 删除点击

```python
def editorEvent(self, event, model, option, index):
    if (event.type() == QEvent.Type.MouseButtonRelease
            and event.button() == Qt.LeftButton):
        del_x = option.rect.right() - self._DEL_ZONE_W
        if event.position().x() >= del_x:
            path = index.data(Qt.ItemDataRole.UserRole)
            self.remove_requested.emit(path)
            return True
    return False
```

---

## Section 3：Hover 追踪

`_FileList` 开启鼠标追踪，重写 `mouseMoveEvent` 和 `leaveEvent`：

```python
class _FileList(QListWidget):
    def __init__(self, delegate: _RowDelegate, parent=None):
        super().__init__(parent)
        self._delegate = delegate
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)

    def mouseMoveEvent(self, event):
        index = self.indexAt(event.pos())
        if index != self._delegate._hovered_index:
            self._delegate._hovered_index = index
            self.viewport().update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._delegate._hovered_index = QModelIndex()
        self.viewport().update()
        super().leaveEvent(event)
```

---

## Section 4：删除事件串联

`LrmxFilePanel._build_ui()` 中：

```python
self._delegate = _RowDelegate()
self._delegate.remove_requested.connect(self._on_path_removed)
self._list.setItemDelegate(self._delegate)
```

```python
def _on_path_removed(self, path: str):
    self._path_set.discard(path)
    for i in range(self._list.count()):
        if self._list.item(i).data(Qt.ItemDataRole.UserRole) == path:
            self._list.takeItem(i)
            break
    self.files_changed.emit(self.files())
```

工具栏「删除选中」逻辑不变，仍使用 `selectedItems()`，只需在 `_remove_selected` 中同步 `_path_set`。

---

## Files Changed

| 文件 | 改动类型 |
|------|---------|
| `app/ui/widgets/file_panel.py` | 删除 `_FileRow`；新增 `_RowDelegate`；修改 `_FileList`（mouse tracking）；修改 `add_file`（去掉 setItemWidget）；修改 `LrmxFilePanel._build_ui`、`_on_row_removed` → `_on_path_removed`、`_remove_selected` |

不涉及其他文件。

---

## 注意事项

- `_RowDelegate._hovered_index` 初始化为 `QModelIndex()`（无效 index，代表无悬停）
- `paint()` 不调用 `super().paint()` — 完全自绘，跳过默认选中高亮背景（当前设计无选中高亮，与现有行为一致）
- `remove_requested` signal 定义在 `_RowDelegate`，不能用 `QStyledItemDelegate` 直接继承 Signal（需继承自 `QObject`，`QStyledItemDelegate` 已是 `QObject` 子类，可直接用）
- 现有 `_FileList.empty_clicked` signal 和空列表 hint 绘制逻辑保留不变
