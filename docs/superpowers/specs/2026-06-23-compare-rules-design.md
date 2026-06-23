# 自定义比较规则 Implementation Design

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在批量核验功能中支持用户自定义字段比较规则，允许将格式不同但语义相同的值（如 `1986.11` 和 `198611`）判定为一致。

**Architecture:** 新建 `app/core/compare_rules.py` 作为规则的数据模型与比较逻辑的单一来源；`VerifyHandler` 增加可选的 `compare_rules` 参数；Settings Tab 增加规则管理 UI；Verify Tab 的每个字段行增加规则选择下拉框。

**Tech Stack:** PySide6 (QDialog, QListWidget, QComboBox, QRadioButton)、Python `datetime.strptime`、`re.findall`、QSettings JSON 持久化

---

## 涉及文件

| 操作 | 路径 |
|------|------|
| 新建 | `app/core/compare_rules.py` |
| 修改 | `app/core/verify_handler.py` |
| 修改 | `app/ui/tabs/settings_tab.py` |
| 修改 | `app/ui/tabs/verify_tab.py` |
| 新建 | `tests/test_compare_rules.py` |

---

## 第一节：数据模型与核心逻辑（`app/core/compare_rules.py`）

### 数据类

```python
from dataclasses import dataclass, field

@dataclass
class CompareRule:
    name: str
    type: str           # 'date' | 'regex'
    formats: list[str]  # date 专用：互相等价的格式字符串列表，如 ['yyyy.MM', 'yyyyMM']
    pattern: str = ''   # regex 专用：正则表达式字符串
```

### 日期格式转换

将用户输入的 `yyyy.MM.dd` 风格转为 Python `strptime` 格式：

| 用户格式 | Python 格式 |
|----------|-------------|
| `yyyy`   | `%Y`        |
| `MM`     | `%m`        |
| `dd`     | `%d`        |

转换函数：`to_py_format(fmt: str) -> str`，按上表做简单字符串替换（顺序：`yyyy→%Y`，`MM→%m`，`dd→%d`）。

### 比较逻辑

**日期比较：**
```python
def _compare_date(rule: CompareRule, a: str, b: str) -> bool:
    py_fmts = [to_py_format(f) for f in rule.formats]
    pa = _try_parse(a.strip(), py_fmts)
    pb = _try_parse(b.strip(), py_fmts)
    return pa is not None and pb is not None and pa == pb

def _try_parse(s: str, py_fmts: list[str]) -> datetime | None:
    for fmt in py_fmts:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None
```

- 两个值分别逐一尝试规则中的所有格式
- 只要两边都能被解析（不必是同一个格式），且解析结果相等，则返回 True

**正则比较：**
```python
def _compare_regex(rule: CompareRule, a: str, b: str) -> bool:
    try:
        ma = ''.join(re.findall(rule.pattern, a))
        mb = ''.join(re.findall(rule.pattern, b))
        return ma == mb
    except re.error:
        return False
```

- 对两个值分别提取所有匹配项并拼接，比较拼接结果是否相同
- 正则异常时返回 False（不崩溃）

**统一入口：**
```python
def apply_rule(rule: CompareRule, a: str, b: str) -> bool:
    if rule.type == 'date':
        return _compare_date(rule, a, b)
    if rule.type == 'regex':
        return _compare_regex(rule, a, b)
    return False
```

### JSON 持久化

```python
def rules_to_json(rules: list[CompareRule]) -> str: ...
def rules_from_json(s: str) -> list[CompareRule]: ...
```

QSettings key：`'compare_rules'`。格式：
```json
[
  {"name": "月份格式", "type": "date", "formats": ["yyyy.MM", "yyyyMM", "yyyy年MM月"], "pattern": ""},
  {"name": "数字提取", "type": "regex", "formats": [], "pattern": "[0-9]+"}
]
```

### 格式校验工具

```python
def validate_date_format(fmt: str) -> bool:
    """检查格式字符串是否合法（转换后能被 strptime 使用）。"""

def validate_regex_pattern(pattern: str) -> bool:
    """检查正则是否能通过 re.compile()。"""
```

---

## 第二节：VerifyHandler 改动（`app/core/verify_handler.py`）

### `__init__` 新增参数

```python
def __init__(
    self,
    ...existing...,
    compare_rules: dict[str, 'CompareRule'] | None = None,  # key: lrmx_field
) -> None:
    ...
    self.compare_rules: dict[str, CompareRule] = compare_rules or {}
```

### `verify()` 比较逻辑变更

原来（第 247 行）：
```python
match = _strip(excel_raw) == _strip(lrmx_raw)
```

改为：
```python
match = _strip(excel_raw) == _strip(lrmx_raw)
if not match:
    rule = self.compare_rules.get(lrmx_field)
    if rule:
        match = apply_rule(rule, excel_raw, lrmx_raw)
```

逻辑：严格相等优先，不等时再用规则兜底。两者满足其一即判定一致。

---

## 第三节：设置界面（`app/ui/tabs/settings_tab.py`）

### 新增 UI 区块

在「编辑器布局」区块下方添加「比较规则」区块：

```
── 比较规则 ────────────────────────────────────
[日期] 月份格式
[正则] 数字提取
                              [新增] [编辑] [删除]
```

- `QListWidget` 显示规则列表，每行格式：`[类型] 名称`
- 选中某行后「编辑」「删除」才可用
- 「删除」弹二次确认

### `_CompareRuleDialog(QDialog)`

新增内部类，用于新增/编辑规则：

```
规则名称：[_________________]

类型：  ● 日期格式    ○ 正则表达式

── 日期格式（互相等价的格式，每行一个）──
┌───────────────────────────┐  [+]
│ yyyy.MM                   │  [-]
│ yyyyMM                    │
│ yyyy年MM月                │
└───────────────────────────┘
支持字段：yyyy 年 / MM 月 / dd 日

── 正则表达式 ────────────────────────
模式：[_________________]
说明：取所有匹配内容拼接后对比

[取消]                      [保存]
```

- 类型切换时显示/隐藏对应输入区
- 格式列表：`QListWidget` + 内联 `QLineEdit` 编辑（双击编辑）或点 `[+]` 追加空行后立即进入编辑状态
- 保存时校验：名称非空；日期格式至少一个且全部合法；正则能通过 `re.compile`
- 校验失败时在弹窗内显示红字提示，不关闭弹窗

### 加载与保存

- `_load()`：读取 `QSettings('compare_rules', '')` 并用 `rules_from_json` 反序列化，填充列表
- `_save()`（现有按钮）：额外写入 `compare_rules` key

---

## 第四节：核验界面改动（`app/ui/tabs/verify_tab.py`）

### `_FieldRow` 布局

原布局：
```
[任免表字段名 (180px)] [Excel列名 | "未匹配" (stretch)] [× (20px, 隐藏)]
```

新布局：
```
[任免表字段名 (180px)] [Excel列名 | "未匹配" (stretch)] [规则下拉框 (110px)] [× (20px)]
```

- 规则下拉框：`QComboBox`，设 `StrongFocus`，覆写 `wheelEvent` 防误触（同 `_ScrollSafeCombo`）
- **未匹配时**：下拉框隐藏
- **已匹配时**：下拉框显示，第一项为 `"（默认）"`，后续为规则名称列表
- `set_available_rules(rules: list[CompareRule])` 方法：清空并重新填充下拉框选项，保持当前选中名称不变（若仍存在）
- `selected_rule() -> CompareRule | None`：返回当前选中的规则对象，或 None（默认）

### `_MappingWidget` 新增方法

```python
def set_available_rules(self, rules: list[CompareRule]) -> None:
    """更新所有字段行的规则下拉框选项。"""
    for row in self._field_rows.values():
        row.set_available_rules(rules)

def get_rule_mapping(self) -> dict[str, CompareRule | None]:
    """返回 {lrmx_field: rule_or_None}，已匹配且选了规则的字段才有值。"""
    result = {}
    for field, row in self._field_rows.items():
        if field in self._reverse:  # 该字段已匹配
            result[field] = row.selected_rule()
    return result
```

### `VerifyTab._run()` 改动

```python
def _run(self):
    import json
    from app.core.compare_rules import rules_from_json
    raw = self._settings.value('compare_rules', '')
    rules = rules_from_json(raw) if raw else []
    self._mapping_widget.set_available_rules(rules)      # 确保选项最新
    rule_mapping = self._mapping_widget.get_rule_mapping()

    handler = VerifyHandler(
        ...existing args...,
        compare_rules=rule_mapping,
    )
    ...
```

### 规则下拉框重置时机

- 调用 `_mapping_widget.clear_all()` 时，各字段行的下拉框重置为「（默认）」
- 调用 `_remove_mapping(lrmx_field)` 时，对应字段行的下拉框隐藏并重置

---

## 约束与边界条件

| 情况 | 行为 |
|------|------|
| 规则列表为空 | 下拉框只有「（默认）」，功能退化为原有严格比较 |
| 日期格式字符串无法解析某值 | 该值视为解析失败，规则不介入，维持原严格比较结果 |
| 正则表达式编译失败 | `apply_rule` 返回 False，维持原严格比较结果 |
| 两个值都解析为同一 datetime | 判定一致，即使字符串表面不同 |
| 正则提取结果均为空字符串 | `'' == ''` → True，两个值都没有匹配到内容则判定一致 |

最后一条边界：**正则提取结果均为空字符串时判定一致**可能产生误报（两个完全不同的值若都没有匹配项则误判相等）。规避方式：在设置弹窗中的说明文字提醒用户确保正则至少能匹配到有意义内容。核心逻辑不做特殊处理（YAGNI）。

---

## 测试要点（`tests/test_compare_rules.py`）

```python
# 日期规则
assert apply_rule(date_rule, '1986.11', '198611') is True
assert apply_rule(date_rule, '1986.11', '198612') is False
assert apply_rule(date_rule, '不是日期', '198611') is False

# 正则规则
assert apply_rule(regex_rule, '第9个人', '共9个人') is True
assert apply_rule(regex_rule, '第9个人', '共8个人') is False
assert apply_rule(regex_rule, '无数字', '也无数字') is True  # 均为空字符串

# JSON 往返
rules = [CompareRule('月份格式', 'date', ['yyyy.MM', 'yyyyMM'], '')]
assert rules_from_json(rules_to_json(rules))[0].formats == ['yyyy.MM', 'yyyyMM']

# 格式校验
assert validate_date_format('yyyy.MM') is True
assert validate_date_format('invalid_fmt') is False
assert validate_regex_pattern('[0-9]+') is True
assert validate_regex_pattern('[unclosed') is False
```
