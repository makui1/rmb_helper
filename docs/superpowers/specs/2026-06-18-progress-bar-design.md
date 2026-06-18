# 进度条优化 Implementation Design

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在三个批量操作 Tab（批量格式转换、批量版本兼容、批量核验/更新）中各加一条进度条，实时反映当前任务完成比例。

**Background:** 当前三个 Tab 的 Worker 均只通过文字日志汇报进度，用户无法直观感知整体完成情况。批量转换 Tab 有两个并行阶段（DOCX + PDF），需特殊处理。

---

## Section 1：信号与数据流

每个 Tab 的 `_Worker` 新增一个信号：

```python
progress = Signal(int, int)  # (current, total)
```

**ConvertTab `_Worker`**：
- `total = len(self.files) * 2`（两阶段各算一半）
- DOCX 阶段：每完成一个文件，在 `_on_docx` 回调中 emit `progress(docx_done_count[0], total)`
- PDF 阶段：每完成一个文件，在 `_on_pdf` 回调中 emit `progress(len(docx_job_args) + pdf_done_count[0], total)`
- 仅开启 DOCX 不开 PDF 时：`total = len(self.files)`，DOCX 完成即 100%
- 仅开启 PDF 不开 DOCX 时：同上，DOCX（生成临时文件）算第一阶段，PDF 算第二阶段，`total = len(self.files) * 2`

**CompatTab `_Worker`**：
- `total = len(self.files)`
- 每处理完一个文件 emit `progress(i + 1, total)`

**VerifyTab `_Worker`**：
- `total = len(lrmx_files)`（或当前任务文件数）
- 每处理完一个文件 emit `progress(i + 1, total)`（需确认 VerifyTab Worker 的结构）

---

## Section 2：UI

**三个 Tab 均做以下相同改动：**

在"开始"按钮所在行（`rule_row` / 操作行）与日志过滤按钮行之间，插入一个 `QProgressBar`：

```python
self._progress = QProgressBar()
self._progress.setRange(0, 100)
self._progress.setValue(0)
self._progress.setVisible(False)
self._progress.setTextVisible(False)   # 不显示百分比文字，保持简洁
self._progress.setFixedHeight(4)       # 细条样式
bot_layout.addWidget(self._progress)
```

**生命周期：**
- 任务开始（`_run` 方法）：`setRange(0, total)`、`setValue(0)`、`setVisible(True)`
  - 注意：`total` 需从 Worker 的 `progress` 信号首次发射中得知，或在启动前预计算
  - 推荐：Worker 额外发射一个 `started = Signal(int)` 信号传递 `total`，UI 用它做 `setRange`
- 任务运行中：`progress` 信号 → `setValue(current)`
- 任务结束（`finished` 信号）：`setValue(total)`（满格），然后短暂延迟或直接 `setVisible(False)`

**QSS 样式（加入 `app/ui/style.py`）：**

```css
QProgressBar {
    background: #e0e0e0;
    border: none;
    border-radius: 2px;
}
QProgressBar::chunk {
    background: #4a90d9;
    border-radius: 2px;
}
```

---

## Files Changed

| 文件 | 改动类型 |
|------|---------|
| `app/ui/tabs/convert_tab.py` | Worker 加 `progress` + `started` 信号；UI 加进度条 |
| `app/ui/tabs/compat_tab.py` | Worker 加 `progress` + `started` 信号；UI 加进度条 |
| `app/ui/tabs/verify_tab.py` | Worker 加 `progress` + `started` 信号；UI 加进度条 |
| `app/ui/style.py` | 加 `QProgressBar` / `QProgressBar::chunk` 样式 |

不涉及：core 层任何文件、MainWindow、其他 UI 组件。

---

## 注意事项

- `progress` 信号从 Worker 线程 emit，Qt 自动使用 queued connection，UI 在主线程安全更新，无性能影响。
- ConvertTab 当用户只勾选 DOCX 不勾选 PDF 时，`total = len(files)`，进度条直接 0→100%。
- ConvertTab 当用户只勾选 PDF 不勾选 DOCX 时，内部仍有两阶段（生成临时 DOCX + 转 PDF），`total = len(files) * 2`。
- VerifyTab 的 Worker 结构需读取后确认，但信号模式与其他两个 Tab 相同。
