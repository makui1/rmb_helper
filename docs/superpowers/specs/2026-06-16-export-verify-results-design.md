# 核验结果导出 Design Spec

**Goal:** 在批量核验结果区新增导出功能，支持 Excel（双 Sheet）和 HTML（还原 UI 风格）两种格式，由用户自由勾选，导出范围为当前筛选后可见的结果。

**Architecture:** 新增纯逻辑模块 `app/core/result_exporter.py`（无 Qt 依赖），`verify_tab.py` 添加导出 UI 行并调用导出函数。

**Tech Stack:** openpyxl（已有依赖）、Python 标准库 `html` / `pathlib` / `datetime`

---

## 文件变更

| 文件 | 操作 |
|------|------|
| `app/core/result_exporter.py` | 新建：`export_excel`、`export_html` 两个函数 |
| `app/ui/tabs/verify_tab.py` | 修改：添加导出行 UI，连接导出逻辑 |

---

## result_exporter.py 接口

```python
from pathlib import Path
from app.core.verify_handler import PersonResult

def export_excel(results: list[PersonResult], path: Path) -> None:
    """写双 Sheet Excel。Sheet1=人员汇总，Sheet2=字段明细。"""

def export_html(results: list[PersonResult], path: Path, config_summary: str = '') -> None:
    """写自包含 HTML 文件，内联 CSS，无外部依赖。"""
```

两个函数均为同步调用，失败时抛出异常由调用方处理。

---

## Excel 结构

### Sheet1 — 人员汇总（每人一行）

| 列 | 内容 |
|----|------|
| 姓名 | `result.name` |
| 身份证 | 从 fields 中取 ShenFenZheng 的 excel_val（若已映射），否则留空 |
| 核验状态 | 一致 / 有差异 / 名册无此人 / 错误 |
| 差异字段数 | `sum(1 for f in result.fields if not f.match)`，无字段时为空 |
| 差异字段 | 不一致字段的 `field` 名逗号拼接，无字段时为空 |
| 错误信息 | `result.error_msg`，仅 error 状态有值 |

状态单元格背景色：一致=浅绿，有差异=浅红，名册无此人=浅橙，错误=浅灰。

### Sheet2 — 字段明细（每字段一行）

| 列 | 内容 |
|----|------|
| 姓名 | `result.name` |
| 身份证 | 同 Sheet1 |
| 字段 | `fr.field` |
| 名册值 | `fr.excel_val` |
| 任免表值 | `fr.lrmx_val` |
| 是否一致 | ✓ / ✗ |

- 仅 status 为 `ok` 或 `diff` 的人员写入 Sheet2
- `not_found` / `error` 写一行：字段列填"—"，名册值列填状态说明

不一致行的"名册值"和"任免表值"单元格背景色：浅红 / 浅绿。

---

## HTML 结构

单个自包含 `.html` 文件，UTF-8 编码，所有样式内联或写在 `<style>` 块。

```
<html>
  <head>
    <meta charset="utf-8">
    <style> /* 全部内联，无外链 */ </style>
  </head>
  <body>
    <!-- 顶部摘要 -->
    <div class="header">
      <div class="meta">导出时间 · 配置摘要</div>
      <div class="counts">
        <span class="badge ok">N 一致</span>
        <span class="badge diff">N 有差异</span>
        <span class="badge not_found">N 名册无此人</span>
        <span class="badge error">N 错误</span>
      </div>
    </div>

    <!-- 每人一个 details 块 -->
    <details [open if status=='diff']>
      <summary>
        <span class="arrow">▶</span>
        <span class="name">姓名</span>
        <span class="badge {status}">状态标签</span>
      </summary>
      <!-- 字段对比表（仅 ok/diff） -->
      <table>
        <tr><th>字段</th><th>名册值</th><th>任免表值</th></tr>
        <tr>
          <td>字段名</td>
          <td class="[del|same]">名册值（差异字符用 <span class="del"> 红色 </span>）</td>
          <td class="[ins|same]">任免表值（差异字符用 <span class="ins"> 绿色 </span>）</td>
        </tr>
      </table>
      <!-- not_found / error：一段说明文字 -->
    </details>
  </body>
</html>
```

字符级 diff 复用 `verify_handler.char_diff_html` 已有函数生成 HTML 片段。

---

## UI 导出行

位置：`_summary_cards_widget` 下方，独立 `QWidget`（`self._export_row`），核验开始时随结果区一并显示，返回配置时隐藏。

```
[ ✓ Excel ]  [ ✓ HTML ]     [  导出当前结果  ↓  ]    （成功后：已保存到 xxx）
```

- `QCheckBox('Excel')`，默认勾选
- `QCheckBox('HTML')`，默认勾选
- `QPushButton('导出当前结果')`：至少一个勾选时启用，否则禁用
- `QLabel('')`：成功后显示"✓ 已保存到 {目录}"，3 秒后自动清空（`QTimer.singleShot(3000, clear)`）

### 文件命名规则

```
核验结果_{YYYYMMDD}_{筛选状态}.xlsx
核验结果_{YYYYMMDD}_{筛选状态}.html
```

筛选状态：`全部` / `一致` / `有差异` / `名册无此人` / `错误`（取 `_active_filter` 对应中文，无筛选时为"全部"）。

### 导出流程

1. 点击"导出当前结果"
2. `QFileDialog.getExistingDirectory` 选择输出目录
3. 用户取消 → 什么都不做
4. 收集当前可见行：`[r._result for r in self._result_rows if r.isVisible()]`
5. 按勾选格式分别调用 `export_excel` / `export_html`
6. 任一失败 → `QMessageBox.warning` 显示错误，继续尝试另一格式
7. 全部成功 → 导出行显示成功提示

---

## 错误处理

| 场景 | 处理 |
|------|------|
| 无可见结果（全被筛掉） | 按钮禁用（`len(visible) == 0` 时禁用） |
| 磁盘写入失败 | `QMessageBox.warning` 显示异常信息 |
| 未勾选任何格式 | 按钮禁用 |

---

## 不在范围内

- 导出进度条（结果数量有限，同步写入足够快）
- 自定义列选择
- 打印功能
