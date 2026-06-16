# 批量核验与批量更新合并 Design Spec

**Goal:** 将"批量更新"功能并入"批量核验" Tab，共用字段映射配置，通过两个并排操作按钮区分核验与更新，同时修复现有更新逻辑无法正确读取 Excel 列的根本问题。

**Architecture:** 删除 `update_tab.py`，在 `verify_tab.py` 中增加更新操作、字段选择对话框和更新结果视图；重构 `excel_handler.py` 的 `update()` 方法使其接受字段映射参数；`main_window.py` 移除 UpdateTab 入口。

**Tech Stack:** PySide6、openpyxl（已有依赖）

---

## 文件变更

| 文件 | 操作 |
|------|------|
| `app/core/excel_handler.py` | 修改：重构 `ExcelHandler.update()` 签名与实现 |
| `app/ui/tabs/verify_tab.py` | 修改：增加更新操作入口、`_UpdateFieldDialog`、更新结果视图、更新 Worker |
| `app/ui/tabs/update_tab.py` | 删除 |
| `app/ui/main_window.py` | 修改：移除 UpdateTab，更新左侧导航 |

---

## 导航变更

左侧导航从四项变为三项：

```
批量转换
版本兼容
批量核验      ← 副标题改为"对照干部名册，核验或更新任免表字段"
```

`UpdateTab` 对应的导航条目删除，`main_window.py` 中不再 import `UpdateTab`。

---

## excel_handler.py — ExcelHandler.update() 重构

### 现有问题

当前 `update()` 假设 Excel 列名与 lrmx 字段名相同（`row.get('XingMing')`），导致实际 Excel 文件无法匹配。

### 新签名

```python
def update(
    self,
    field_mapping: dict[str, str],            # excel_col → lrmx_field
    fields_to_write: list[str],                # 实际要写入的 lrmx 字段名（field_mapping 值的子集）
    header_row: int = 1,
    match_excel_col_for_id: str | None = None,  # 身份证列的 Excel 表头名
    match_excel_col_for_name: str | None = None, # 姓名列的 Excel 表头名
    progress_cb: Optional[Callable[[str], None]] = None,
) -> list[str]:
```

### 新实现要点

- 使用 `header_row` 参数定位表头行（对齐 VerifyHandler 的实现）
- 用 `match_excel_col_for_id` / `match_excel_col_for_name` 构建 Excel 行的匹配 key（与 VerifyHandler._excel_key 一致）
- 对每个 .lrmx 文件，用 lrmx 字段值构建 key，在 Excel 索引中查找对应行
- 仅写入 `fields_to_write` 中列出的字段，通过 `field_mapping` 找到对应 Excel 列后读值
- 写入前备份：`lf.path.rename(lf.path.with_suffix('.lrmx.bak'))`
- progress_cb 消息格式：
  - 成功：`✓ {name}  已更新 {n} 个字段`
  - 未匹配：`△ {name}  未在名册中找到匹配记录`
  - 失败：`✗ {name}  {error}`

---

## verify_tab.py — 新增内容

### 操作按钮区

在设置面板底部，现有"开始核验"按钮左侧增加"开始更新"按钮：

```
[ ⚠ 开始更新 ]                    [ 开始核验 ]
```

- **开始核验**：保持现有 `objectName='primary'`（橙色）位置不变，靠右
- **开始更新**：普通 `QPushButton`（灰底，继承 QSS），带 `⚠` 图标，靠左
- 两个按钮共用前置校验：文件已添加 + Excel 已选 + 至少一个字段已映射，否则禁用

### _UpdateFieldDialog（私有类）

`verify_tab.py` 内新增私有类，继承 `QDialog`，样式完全依赖全局 QSS，不添加任何内联 styleSheet。

```python
class _UpdateFieldDialog(QDialog):
    """字段选择对话框，点击"开始更新"后弹出。"""
```

**布局：**
```
┌─────────────────────────────────────────┐
│  选择要写入的字段                          │
│                                         │
│  以下字段已完成映射，勾选后将从名册写入 .lrmx │
│                                         │
│  ☑ 姓名    ☑ 性别    ☑ 出生年月           │
│  ☑ 民族    ☑ 籍贯    ☐ 入党时间           │
│  ...                                    │
│                          [全选]  [全不选]  │
│                                         │
│  ⚠ 更新将直接修改 .lrmx 文件，建议先核验    │
│     确认数据正确后再执行更新。              │
│                                         │
│              [ 取消 ]  [ 确认更新 ]       │
└─────────────────────────────────────────┘
```

- 列表只显示当前已完成映射的 lrmx 字段，未映射字段不出现
- 默认全选
- "全选"/"全不选"为普通 QPushButton（继承 QSS）
- "确认更新"为 `objectName='primary'` 橙色主按钮
- 对话框最小宽度 400px，使用 `QVBoxLayout` + `QGridLayout`（两列 checkbox）

**返回值：** `exec()` 返回 `QDialog.Accepted` 且 `selected_fields()` 返回已勾选字段名列表。

### _UpdateWorker（私有类）

```python
class _UpdateWorker(QThread):
    log = Signal(str)    # 单条进度消息
    finished = Signal()
```

构造参数与 `ExcelHandler.update()` 新签名对应，调用 `handler.update()`。

### 更新结果视图

点击"确认更新"执行后，隐藏设置面板，显示更新结果区（与核验结果区互斥，同一位置）。

**布局：**
```
← 返回    已更新 N 个 · 未匹配 M 个 · 失败 K 个

[ 全部 ]  [ 成功 ]  [ 错误 ]

────────────────────────────────────────
  ✓  丁国义  已更新 5 个字段
  ✓  丁晓峰  已更新 5 个字段
  △  丁晓雪  未在名册中找到匹配记录
  ✗  某某    写入失败: ...
```

实现细节：
- 使用 `QScrollArea` + 动态添加 `_UpdateLogRow` widget（每行一条日志）
- 汇总栏（`← 返回 · 已更新 N 个...`）复用现有 `_summary_bar` 区域的位置
- 过滤按钮（全部/成功/错误）复用现有 logFilter 样式（`objectName='logFilterBtn'`）
- 加载遮罩（`_LoadingOverlay`）在更新执行期间显示"更新中，请稍候…"
- 无导出按钮（更新结果不需要导出）

### _back_to_setup() 扩展

返回配置时，更新结果视图也需要隐藏，并清空日志行。

---

## 结果区切换逻辑

`VerifyTab` 维护一个 `_mode: str`（`'verify'` 或 `'update'`），决定结果区显示哪套 widget：

- `_mode == 'verify'`：显示现有核验结果区（summary cards、result rows、export row）
- `_mode == 'update'`：显示新增更新结果区（summary bar、log rows）

两套 widget 始终存在于布局中，通过 `show()`/`hide()` 切换。

---

## 错误处理

| 场景 | 处理 |
|------|------|
| 字段选择对话框全部取消勾选 | "确认更新"禁用 |
| .lrmx 写入失败（权限/磁盘） | 记录 `✗` 日志行，继续处理下一个文件 |
| Excel 读取失败 | `_LoadingOverlay` 隐藏，`QMessageBox.critical` 显示错误 |
| 未匹配到任何记录 | 汇总栏显示"未匹配 N 个"，不视为错误 |

---

## 不在范围内

- 更新结果的导出（日志已在界面可见，足够）
- 更新操作的撤销（备份 .lrmx.bak 已提供手动恢复手段）
- 核验后自动触发更新的流水线式操作
