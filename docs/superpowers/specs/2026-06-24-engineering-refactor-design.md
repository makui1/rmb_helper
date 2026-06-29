# 工程重构 Design

## 目标

在不改变任何用户可见行为的前提下，消除代码库中的四类工程债务：重复的 Worker 样板、过大的文件、过长的方法、分散的错误处理。重构完成后，每个文件职责单一，每个方法不超过 60 行，错误处理路径统一。

## 策略

方案 C（横切关注点优先）：先提取全局共享基础设施（BaseWorker + 统一错误处理），再拆分最大的文件（verify_tab.py），再分解长方法（editor_tab.py），最后整理核心层（docx_exporter.py）。每个任务独立提交、独立验证，测试允许随结构同步更新（行为语义不变）。

---

## 第一节：BaseWorker + 统一错误处理

### 问题

五个 Tab 各自定义结构相同的 `_XxxWorker(QThread)`：
- `_CompatWorker` — `compat_tab.py`
- `_ConvertWorker` — `convert_tab.py`
- `_FamilyWorker` — `family_tab.py`
- `_VerifyWorker`、`_UpdateWorker` — `verify_tab.py`
- `file_panel.py` 内的匿名 Worker

每个都重复声明 `log = Signal(str)`、`progress = Signal(int)`、`try/except`。错误提示分散：部分弹 `QMessageBox`，部分发 log 信号，部分静默。

### 设计

**新建 `app/ui/workers.py`**：

```python
class BaseWorker(QThread):
    log      = Signal(str)
    progress = Signal(int)   # 0–100
    error    = Signal(str)   # 统一错误信号

    def run(self):
        try:
            self.work()
        except Exception as e:
            self.error.emit(str(e))

    def work(self):
        raise NotImplementedError
```

各 Tab Worker 改为：
```python
class _CompatWorker(BaseWorker):
    finished = Signal(int, int)

    def __init__(self, files, ...):
        super().__init__()
        ...

    def work(self):
        # 原 run() 内容，去掉 try/except
        ...
```

**新建 `app/ui/utils.py`**：

```python
def show_error(parent, msg: str) -> None:
    QMessageBox.critical(parent, '错误', msg)

def show_warning(parent, msg: str) -> None:
    QMessageBox.warning(parent, '警告', msg)
```

所有 UI 层错误提示改用这两个函数；`BaseWorker.error` 信号在调用方统一连接到 `show_error`。

### 文件变动

| 操作 | 文件 |
|------|------|
| 新建 | `app/ui/workers.py` |
| 新建 | `app/ui/utils.py` |
| 修改 | `app/ui/tabs/compat_tab.py` |
| 修改 | `app/ui/tabs/convert_tab.py` |
| 修改 | `app/ui/tabs/family_tab.py` |
| 修改 | `app/ui/tabs/verify_tab.py` |
| 修改 | `app/ui/widgets/file_panel.py` |

---

## 第二节：verify_tab.py 拆分

### 问题

`verify_tab.py` 当前 1564 行，含 14 个类、87 个函数。14 个类涵盖自定义布局、标签 widget、字段行 widget、映射面板、结果行、更新日志行、diff 面板、弹窗、加载遮罩、Worker、主 Tab，职责完全混杂。

### 设计

按职责拆分为 5 个目标文件：

| 目标文件 | 迁移的类 | 行数估算 |
|----------|----------|----------|
| `app/ui/widgets/flow_layout.py` | `_FlowLayout`、`_MatchTag` | ~150 行 |
| `app/ui/widgets/field_mapping.py` | `_NoScrollCombo`、`_FieldRow`、`_MappingWidget` | ~300 行 |
| `app/ui/widgets/verify_result.py` | `_DiffPanel`、`_ResultRow` | ~200 行 |
| `app/ui/widgets/update_log.py` | `_UpdateLogRow`、`_UpdateFieldDialog`、`_HoverIconButton` | ~180 行 |
| `app/ui/widgets/loading_overlay.py` | `_LoadingOverlay` | ~50 行 |
| `app/ui/tabs/verify_tab.py`（保留） | `_VerifyWorker`、`_UpdateWorker`、`VerifyTab` | ~700 行 |

**迁移原则**：
- 只移动，不重写；类接口和行为保持不变。
- `_VerifyWorker`、`_UpdateWorker` 改继承 `BaseWorker`（第一节），但留在 `verify_tab.py`（与 `VerifyTab` 耦合深，不值得单独抽文件）。
- `verify_tab.py` 顶部通过 `from app.ui.widgets.xxx import ...` 导入，对外接口不变。

---

## 第三节：editor_tab.py 长方法分解

### 问题

| 方法 | 行数 |
|------|------|
| `_build_layout_a` | 159 行 |
| `_build_layout_b` | 118 行 |
| `_build_toolbar` | 85 行 |

三个方法各自将所有 section 的构建逻辑堆在一起，难以定位单个字段的渲染路径。

### 设计

不拆文件，不拆类，只在 `EditorTab` 内做方法分解。父方法变为纯组合，每个 section 提成独立方法：

```python
def _build_layout_a(self) -> QWidget:
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.addWidget(self._build_la_header())
    lay.addWidget(self._build_la_personal())
    lay.addWidget(self._build_la_position())
    lay.addWidget(self._build_la_approvals())
    return w

def _build_la_header(self) -> QWidget: ...     # ≤40 行
def _build_la_personal(self) -> QWidget: ...   # ≤40 行
def _build_la_position(self) -> QWidget: ...   # ≤40 行
def _build_la_approvals(self) -> QWidget: ...  # ≤40 行
```

`_build_layout_b` 和 `_build_toolbar` 同理拆分。

**不动的部分**：`_on_xxx` 事件处理方法、数据加载/保存逻辑——长度合理，行为清晰，不需要改动。

**目标**：所有方法不超过 60 行。

---

## 第四节：docx_exporter.py 内部结构

### 问题

| 方法 | 行数 |
|------|------|
| `_shrink_jianli_cell` | 84 行 |
| `_build_context` | 77 行 |
| `_shrink_plain_cells` | 67 行 |

逻辑分支多、嵌套深，追踪某个字段的渲染路径需要在深层 if 中跳转。

### 设计

不拆文件，不拆类，分三个方向做方法分解：

**① `_build_context` 按字段分组**：
```python
def _build_context(self, lrmx: dict) -> dict:
    ctx = {}
    ctx.update(self._ctx_basic_info(lrmx))
    ctx.update(self._ctx_position_info(lrmx))
    ctx.update(self._ctx_approval_info(lrmx))
    return ctx
```

**② `_shrink_jianli_cell` / `_shrink_plain_cells` 阶段分解**：
将"测量 → 判断是否需要收缩 → 执行收缩"三个阶段各提成独立方法，消除深层嵌套 if。

**③ `_CellSizer` 辅助类（条件触发）**：
仅当 ② 完成后单个方法仍超过 40 行，才将单元格尺寸测量逻辑提取为内部辅助类。

**公开接口不变**：`export()`、`export_bytes()` 签名和行为完全不变，现有测试无需修改。

---

## 验收标准

| 指标 | 目标 |
|------|------|
| 单文件行数 | `verify_tab.py` ≤ 750 行；其余所有文件 ≤ 900 行 |
| 单方法行数 | 所有方法 ≤ 60 行 |
| Worker 重复代码 | 消除；所有 Worker 继承 `BaseWorker` |
| 错误提示 | 所有 UI 层错误通过 `show_error` / `show_warning` |
| 测试 | `uv run pytest` 全绿（允许同步更新测试以匹配新结构，行为语义不变） |
| 用户可见行为 | 零变化 |
