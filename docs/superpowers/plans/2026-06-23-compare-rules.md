# 自定义比较规则 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在批量核验功能中支持用户自定义字段比较规则，允许将格式不同但语义相同的值（如 `1986.11` 和 `198611`）判定为一致。

**Architecture:** 新建 `app/core/compare_rules.py` 作为规则数据模型与比较逻辑的单一来源；`VerifyHandler.__init__` 增加可选的 `compare_rules` 参数；Settings Tab 增加 `_CompareRuleDialog` 和规则管理 UI 区块；Verify Tab 的每个 `_FieldRow` 增加规则下拉框，`_MappingWidget` 增加 `set_available_rules()` 和 `get_rule_mapping()` 方法。

**Tech Stack:** Python `datetime.strptime`、`re.findall`、`dataclasses`、`json`；PySide6（QDialog, QListWidget, QComboBox, QRadioButton, QButtonGroup）；QSettings JSON 持久化。

---

## 文件清单

| 操作 | 路径 | 职责 |
|------|------|------|
| 新建 | `app/core/compare_rules.py` | CompareRule 数据类、比较逻辑、JSON 序列化、格式校验 |
| 新建 | `tests/test_compare_rules.py` | 核心逻辑的单元测试 |
| 修改 | `app/core/verify_handler.py` | 添加 `compare_rules` 参数；在比较循环中应用规则 |
| 修改 | `app/ui/tabs/settings_tab.py` | 添加 `_CompareRuleDialog` 类和「比较规则」UI 区块 |
| 修改 | `app/ui/tabs/verify_tab.py` | `_FieldRow` 规则下拉框；`_MappingWidget` 新方法；`_run()` 传参 |

---

## Task 1: `app/core/compare_rules.py` — 数据模型与核心逻辑

**Files:**
- Create: `app/core/compare_rules.py`
- Create: `tests/test_compare_rules.py`

- [ ] **Step 1: 编写失败的测试**

```python
# tests/test_compare_rules.py
import pytest
from app.core.compare_rules import (
    CompareRule,
    apply_rule,
    rules_to_json,
    rules_from_json,
    validate_date_format,
    validate_regex_pattern,
    to_py_format,
)


# ── to_py_format ──────────────────────────────────────────────────────────────

def test_to_py_format_year_month():
    assert to_py_format('yyyy.MM') == '%Y.%m'

def test_to_py_format_year_month_no_sep():
    assert to_py_format('yyyyMM') == '%Y%m'

def test_to_py_format_full_date():
    assert to_py_format('yyyy年MM月dd日') == '%Y年%m月%d日'

def test_to_py_format_no_tokens():
    assert to_py_format('invalid') == 'invalid'


# ── validate_date_format ──────────────────────────────────────────────────────

def test_validate_date_format_valid_dot():
    assert validate_date_format('yyyy.MM') is True

def test_validate_date_format_valid_no_sep():
    assert validate_date_format('yyyyMM') is True

def test_validate_date_format_valid_chinese():
    assert validate_date_format('yyyy年MM月') is True

def test_validate_date_format_year_only():
    assert validate_date_format('yyyy') is True

def test_validate_date_format_invalid():
    assert validate_date_format('invalid_fmt') is False

def test_validate_date_format_empty():
    assert validate_date_format('') is False


# ── validate_regex_pattern ────────────────────────────────────────────────────

def test_validate_regex_valid():
    assert validate_regex_pattern('[0-9]+') is True

def test_validate_regex_invalid():
    assert validate_regex_pattern('[unclosed') is False

def test_validate_regex_empty():
    assert validate_regex_pattern('') is False

def test_validate_regex_whitespace_only():
    assert validate_regex_pattern('   ') is False


# ── apply_rule (date) ─────────────────────────────────────────────────────────

@pytest.fixture
def date_rule():
    return CompareRule(name='月份格式', type='date', formats=['yyyy.MM', 'yyyyMM'])

def test_apply_date_rule_match(date_rule):
    assert apply_rule(date_rule, '1986.11', '198611') is True

def test_apply_date_rule_no_match(date_rule):
    assert apply_rule(date_rule, '1986.11', '198612') is False

def test_apply_date_rule_unparseable(date_rule):
    assert apply_rule(date_rule, '不是日期', '198611') is False

def test_apply_date_rule_both_unparseable(date_rule):
    assert apply_rule(date_rule, '不是日期', '也不是') is False

def test_apply_date_rule_same_format_match(date_rule):
    assert apply_rule(date_rule, '198611', '198611') is True

def test_apply_date_rule_strips_whitespace(date_rule):
    assert apply_rule(date_rule, '  1986.11  ', '198611') is True


# ── apply_rule (regex) ────────────────────────────────────────────────────────

@pytest.fixture
def regex_rule():
    return CompareRule(name='数字提取', type='regex', pattern=r'[0-9]+')

def test_apply_regex_rule_match(regex_rule):
    assert apply_rule(regex_rule, '第9个人', '共9个人') is True

def test_apply_regex_rule_no_match(regex_rule):
    assert apply_rule(regex_rule, '第9个人', '共8个人') is False

def test_apply_regex_rule_both_empty(regex_rule):
    # Both have no digits → both → '' == '' → True
    assert apply_rule(regex_rule, '无数字', '也无数字') is True

def test_apply_regex_rule_bad_pattern():
    bad_rule = CompareRule(name='bad', type='regex', pattern='[unclosed')
    assert apply_rule(bad_rule, 'abc', 'abc') is False

def test_apply_regex_rule_multiple_matches(regex_rule):
    assert apply_rule(regex_rule, '123 456', '123456') is True


# ── unknown rule type ─────────────────────────────────────────────────────────

def test_apply_unknown_type_returns_false():
    rule = CompareRule(name='x', type='unknown', formats=[])
    assert apply_rule(rule, 'a', 'a') is False


# ── JSON 往返 ─────────────────────────────────────────────────────────────────

def test_json_roundtrip_date():
    rules = [CompareRule(name='月份格式', type='date', formats=['yyyy.MM', 'yyyyMM'], pattern='')]
    loaded = rules_from_json(rules_to_json(rules))
    assert len(loaded) == 1
    assert loaded[0].name == '月份格式'
    assert loaded[0].type == 'date'
    assert loaded[0].formats == ['yyyy.MM', 'yyyyMM']
    assert loaded[0].pattern == ''

def test_json_roundtrip_regex():
    rules = [CompareRule(name='数字', type='regex', formats=[], pattern=r'[0-9]+')]
    loaded = rules_from_json(rules_to_json(rules))
    assert loaded[0].pattern == r'[0-9]+'

def test_json_roundtrip_empty():
    assert rules_from_json(rules_to_json([])) == []

def test_json_from_empty_string():
    assert rules_from_json('') == []

def test_json_from_invalid():
    assert rules_from_json('not json') == []
```

- [ ] **Step 2: 运行测试确认失败**

```
uv run pytest tests/test_compare_rules.py -v
```

预期：`ImportError: No module named 'app.core.compare_rules'`

- [ ] **Step 3: 实现 `app/core/compare_rules.py`**

```python
from __future__ import annotations
import json
import re
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class CompareRule:
    name: str
    type: str           # 'date' | 'regex'
    formats: list[str] = field(default_factory=list)
    pattern: str = ''


def to_py_format(fmt: str) -> str:
    result = fmt
    result = result.replace('yyyy', '%Y')
    result = result.replace('MM', '%m')
    result = result.replace('dd', '%d')
    return result


def validate_date_format(fmt: str) -> bool:
    if not fmt or not any(token in fmt for token in ('yyyy', 'MM', 'dd')):
        return False
    py_fmt = to_py_format(fmt)
    try:
        sample = datetime(2000, 1, 15)
        formatted = sample.strftime(py_fmt)
        datetime.strptime(formatted, py_fmt)
        return True
    except (ValueError, TypeError):
        return False


def validate_regex_pattern(pattern: str) -> bool:
    if not pattern or not pattern.strip():
        return False
    try:
        re.compile(pattern)
        return True
    except re.error:
        return False


def _try_parse(s: str, py_fmts: list[str]) -> datetime | None:
    for fmt in py_fmts:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _compare_date(rule: CompareRule, a: str, b: str) -> bool:
    py_fmts = [to_py_format(f) for f in rule.formats]
    pa = _try_parse(a.strip(), py_fmts)
    pb = _try_parse(b.strip(), py_fmts)
    return pa is not None and pb is not None and pa == pb


def _compare_regex(rule: CompareRule, a: str, b: str) -> bool:
    try:
        ma = ''.join(re.findall(rule.pattern, a))
        mb = ''.join(re.findall(rule.pattern, b))
        return ma == mb
    except re.error:
        return False


def apply_rule(rule: CompareRule, a: str, b: str) -> bool:
    if rule.type == 'date':
        return _compare_date(rule, a, b)
    if rule.type == 'regex':
        return _compare_regex(rule, a, b)
    return False


def rules_to_json(rules: list[CompareRule]) -> str:
    return json.dumps(
        [
            {
                'name': r.name,
                'type': r.type,
                'formats': r.formats,
                'pattern': r.pattern,
            }
            for r in rules
        ],
        ensure_ascii=False,
    )


def rules_from_json(s: str) -> list[CompareRule]:
    if not s:
        return []
    try:
        data = json.loads(s)
        return [
            CompareRule(
                name=d.get('name', ''),
                type=d.get('type', 'date'),
                formats=d.get('formats', []),
                pattern=d.get('pattern', ''),
            )
            for d in data
        ]
    except (json.JSONDecodeError, TypeError, AttributeError):
        return []
```

- [ ] **Step 4: 运行测试确认通过**

```
uv run pytest tests/test_compare_rules.py -v
```

预期：所有测试通过。

- [ ] **Step 5: 提交**

```
git add app/core/compare_rules.py tests/test_compare_rules.py
git commit -m "feat: 新增 compare_rules 模块，支持日期与正则比较规则"
```

---

## Task 2: `app/core/verify_handler.py` — 接入比较规则

**Files:**
- Modify: `app/core/verify_handler.py`

**背景：** `VerifyHandler.__init__` 目前签名如下（第 148-164 行）：
```python
def __init__(
    self,
    excel_path: Path,
    lrmx_files: list,
    match_mode: str,
    header_row: int,
    field_mapping: dict[str, str],
    match_excel_col_for_id: Optional[str],
    match_excel_col_for_name: Optional[str],
) -> None:
```

比较逻辑在第 247 行：`match = _strip(excel_raw) == _strip(lrmx_raw)`

- [ ] **Step 1: 修改 `VerifyHandler.__init__`**

在第 147 行的 `from app.core.lrmx import LrmxFile` 之后，在文件顶部导入区添加：

```python
from app.core.compare_rules import CompareRule, apply_rule
```

将 `__init__` 签名改为（在 `match_excel_col_for_name` 之后新增一个参数）：

```python
def __init__(
    self,
    excel_path: Path,
    lrmx_files: list,
    match_mode: str,
    header_row: int,
    field_mapping: dict[str, str],
    match_excel_col_for_id: Optional[str],
    match_excel_col_for_name: Optional[str],
    compare_rules: dict[str, CompareRule] | None = None,
) -> None:
    self.excel_path = Path(excel_path)
    self.lrmx_files = [Path(f) for f in lrmx_files]
    self.match_mode = match_mode
    self.header_row = header_row
    self.field_mapping = field_mapping
    self._id_col = match_excel_col_for_id
    self._name_col = match_excel_col_for_name
    self.compare_rules: dict[str, CompareRule] = compare_rules or {}
```

- [ ] **Step 2: 修改 `verify()` 中的比较逻辑**

将第 247 行（`match = _strip(excel_raw) == _strip(lrmx_raw)`）改为：

```python
match = _strip(excel_raw) == _strip(lrmx_raw)
if not match:
    rule = self.compare_rules.get(lrmx_field)
    if rule:
        match = apply_rule(rule, excel_raw, lrmx_raw)
```

注意：这里迭代变量是 `excel_col` 和 `lrmx_field`（第 244 行 `for excel_col, lrmx_field in self.field_mapping.items():`)。

- [ ] **Step 3: 运行现有测试确认无回归**

```
uv run pytest tests/test_verify_handler.py tests/test_compare_rules.py -v
```

预期：全部通过。

- [ ] **Step 4: 提交**

```
git add app/core/verify_handler.py
git commit -m "feat: VerifyHandler 支持 compare_rules 参数，比较不一致时尝试应用规则"
```

---

## Task 3: `app/ui/tabs/settings_tab.py` — 规则管理 UI

**Files:**
- Modify: `app/ui/tabs/settings_tab.py`

**背景：** 该文件当前顶部导入（第 1-13 行）：
```python
import json

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListWidget, QListWidgetItem,
    QInputDialog, QMessageBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
)
from PySide6.QtCore import QSettings, Qt
from app.utils.naming import PRESETS
from app.core.verify_handler import LRMX_FIELDS, DEFAULT_FIELD_ALIASES
from app.core import file_assoc
```

`SettingsTab.__init__`（第 16-20 行）：
```python
def __init__(self, parent=None):
    super().__init__(parent)
    self._settings = QSettings('rmb_helper', 'rmb_helper')
    self._build_ui()
    self._load()
```

- [ ] **Step 1: 扩展导入**

将顶部导入块替换为：

```python
import json

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListWidget, QListWidgetItem,
    QInputDialog, QMessageBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
    QDialog, QLineEdit, QRadioButton, QButtonGroup,
)
from PySide6.QtCore import QSettings, Qt
from app.utils.naming import PRESETS
from app.core.verify_handler import LRMX_FIELDS, DEFAULT_FIELD_ALIASES
from app.core import file_assoc
from app.core.compare_rules import CompareRule, rules_to_json, rules_from_json, validate_date_format, validate_regex_pattern
```

- [ ] **Step 2: 在 `SettingsTab` 类之前添加 `_CompareRuleDialog` 类**

在 `class SettingsTab(QWidget):` 这一行之前插入：

```python
class _CompareRuleDialog(QDialog):
    def __init__(self, rule: CompareRule | None = None, parent=None):
        super().__init__(parent)
        self._initial_rule = rule
        self._result: CompareRule | None = None
        self.setWindowTitle('编辑比较规则' if rule else '新增比较规则')
        self.setMinimumWidth(420)
        self._build_ui()
        if rule:
            self._load_rule(rule)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel('规则名称'))
        self._name_edit = QLineEdit()
        name_row.addWidget(self._name_edit)
        layout.addLayout(name_row)

        type_row = QHBoxLayout()
        type_row.addWidget(QLabel('类型'))
        self._rb_date = QRadioButton('日期格式')
        self._rb_regex = QRadioButton('正则表达式')
        self._rb_date.setChecked(True)
        self._type_group = QButtonGroup(self)
        self._type_group.addButton(self._rb_date, 0)
        self._type_group.addButton(self._rb_regex, 1)
        type_row.addWidget(self._rb_date)
        type_row.addWidget(self._rb_regex)
        type_row.addStretch()
        layout.addLayout(type_row)

        # ── 日期格式面板 ──────────────────────────────────────────
        self._date_widget = QWidget()
        dv = QVBoxLayout(self._date_widget)
        dv.setContentsMargins(0, 0, 0, 0)
        dv.setSpacing(4)
        hint_lbl = QLabel('等价格式列表（双击编辑，点 + 新增）')
        hint_lbl.setStyleSheet('color: #555; font-size: 12px;')
        dv.addWidget(hint_lbl)

        fmt_row = QHBoxLayout()
        self._fmt_list = QListWidget()
        self._fmt_list.setFixedHeight(120)
        self._fmt_list.setEditTriggers(QListWidget.EditTrigger.DoubleClicked)
        fmt_row.addWidget(self._fmt_list, 1)

        fmt_btns = QVBoxLayout()
        add_fmt_btn = QPushButton('+')
        add_fmt_btn.setFixedSize(28, 28)
        add_fmt_btn.clicked.connect(self._add_format)
        del_fmt_btn = QPushButton('−')
        del_fmt_btn.setFixedSize(28, 28)
        del_fmt_btn.clicked.connect(self._del_format)
        fmt_btns.addWidget(add_fmt_btn)
        fmt_btns.addWidget(del_fmt_btn)
        fmt_btns.addStretch()
        fmt_row.addLayout(fmt_btns)
        dv.addLayout(fmt_row)

        token_hint = QLabel('支持：yyyy 年 / MM 月 / dd 日　例：yyyy.MM　yyyyMM　yyyy年MM月')
        token_hint.setStyleSheet('color: #888; font-size: 11px;')
        token_hint.setWordWrap(True)
        dv.addWidget(token_hint)
        layout.addWidget(self._date_widget)

        # ── 正则面板 ──────────────────────────────────────────────
        self._regex_widget = QWidget()
        rv = QVBoxLayout(self._regex_widget)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(4)
        rv.addWidget(QLabel('正则表达式模式'))
        self._pattern_edit = QLineEdit()
        rv.addWidget(self._pattern_edit)
        regex_hint = QLabel('取所有匹配内容拼接后对比，例：[0-9]+')
        regex_hint.setStyleSheet('color: #888; font-size: 11px;')
        rv.addWidget(regex_hint)
        self._regex_widget.hide()
        layout.addWidget(self._regex_widget)

        # ── 错误提示 ──────────────────────────────────────────────
        self._error_lbl = QLabel('')
        self._error_lbl.setStyleSheet('color: #B02020; font-size: 11px;')
        self._error_lbl.hide()
        layout.addWidget(self._error_lbl)

        # ── 按钮行 ────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton('取消')
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton('保存')
        save_btn.setObjectName('primary')
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

        self._rb_date.toggled.connect(self._on_type_changed)

    def _on_type_changed(self, is_date: bool):
        self._date_widget.setVisible(is_date)
        self._regex_widget.setVisible(not is_date)

    def _add_format(self):
        item = QListWidgetItem('')
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        self._fmt_list.addItem(item)
        self._fmt_list.setCurrentItem(item)
        self._fmt_list.editItem(item)

    def _del_format(self):
        row = self._fmt_list.currentRow()
        if row >= 0:
            self._fmt_list.takeItem(row)

    def _load_rule(self, rule: CompareRule):
        self._name_edit.setText(rule.name)
        if rule.type == 'regex':
            self._rb_regex.setChecked(True)
            self._pattern_edit.setText(rule.pattern)
        else:
            self._rb_date.setChecked(True)
            for fmt in rule.formats:
                item = QListWidgetItem(fmt)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                self._fmt_list.addItem(item)

    def _save(self):
        name = self._name_edit.text().strip()
        if not name:
            self._show_error('规则名称不能为空')
            return

        if self._rb_date.isChecked():
            formats = [
                self._fmt_list.item(i).text().strip()
                for i in range(self._fmt_list.count())
            ]
            formats = [f for f in formats if f]
            if not formats:
                self._show_error('请至少添加一个日期格式')
                return
            invalid = [f for f in formats if not validate_date_format(f)]
            if invalid:
                self._show_error(f'格式无效（需包含 yyyy/MM/dd 之一）：{", ".join(invalid)}')
                return
            self._result = CompareRule(name=name, type='date', formats=formats)
        else:
            pattern = self._pattern_edit.text().strip()
            if not validate_regex_pattern(pattern):
                self._show_error('正则表达式无效或为空')
                return
            self._result = CompareRule(name=name, type='regex', pattern=pattern)

        self._error_lbl.hide()
        self.accept()

    def _show_error(self, msg: str):
        self._error_lbl.setText(msg)
        self._error_lbl.show()

    def result_rule(self) -> CompareRule:
        return self._result

```

- [ ] **Step 3: 在 `_build_ui()` 中添加「比较规则」UI 区块**

找到 `_build_ui` 方法中最后一个区块末尾（编辑器布局区块结束后、`layout.addStretch()` 之前），插入：

```python
        # ── 比较规则 ──────────────────────────────────────────────────────────
        sep_cr = QFrame()
        sep_cr.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep_cr)

        cr_title = QLabel('比较规则')
        cr_title.setObjectName('sectionTitle')
        layout.addWidget(cr_title)

        cr_sub = QLabel('核验时可为每个字段指定比较规则，允许格式不同但语义相同的值被判定为一致。')
        cr_sub.setStyleSheet('color: #888880; font-size: 12px;')
        cr_sub.setWordWrap(True)
        layout.addWidget(cr_sub)

        self._compare_rule_list = QListWidget()
        self._compare_rule_list.setMaximumHeight(140)
        self._compare_rule_list.currentRowChanged.connect(self._refresh_rule_btns)
        layout.addWidget(self._compare_rule_list)

        rule_btn_row = QHBoxLayout()
        self._add_cr_btn = QPushButton('新增')
        self._add_cr_btn.clicked.connect(self._add_compare_rule)
        self._edit_cr_btn = QPushButton('编辑')
        self._edit_cr_btn.clicked.connect(self._edit_compare_rule)
        self._edit_cr_btn.setEnabled(False)
        self._del_cr_btn = QPushButton('删除')
        self._del_cr_btn.clicked.connect(self._delete_compare_rule)
        self._del_cr_btn.setEnabled(False)
        rule_btn_row.addWidget(self._add_cr_btn)
        rule_btn_row.addWidget(self._edit_cr_btn)
        rule_btn_row.addWidget(self._del_cr_btn)
        rule_btn_row.addStretch()
        layout.addLayout(rule_btn_row)
```

- [ ] **Step 4: 在 `_load()` 中读取规则**

在 `_load()` 方法体内（读取其他设置之后）追加：

```python
        raw_cr = self._settings.value('compare_rules', '')
        self._compare_rules: list[CompareRule] = rules_from_json(raw_cr)
        self._refresh_compare_rule_list()
```

- [ ] **Step 5: 在 `_save()` 中保存规则**

在 `_save()` 方法体内（保存其他设置之后）追加：

```python
        self._settings.setValue('compare_rules', rules_to_json(self._compare_rules))
```

- [ ] **Step 6: 添加规则管理方法**

在 `SettingsTab` 类内添加以下方法：

```python
    def _refresh_rule_btns(self):
        enabled = self._compare_rule_list.currentRow() >= 0
        self._edit_cr_btn.setEnabled(enabled)
        self._del_cr_btn.setEnabled(enabled)

    def _refresh_compare_rule_list(self):
        self._compare_rule_list.clear()
        for rule in self._compare_rules:
            badge = '日期' if rule.type == 'date' else '正则'
            self._compare_rule_list.addItem(f'[{badge}] {rule.name}')
        self._refresh_rule_btns()

    def _add_compare_rule(self):
        dlg = _CompareRuleDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._compare_rules.append(dlg.result_rule())
            self._refresh_compare_rule_list()
            self._settings.setValue('compare_rules', rules_to_json(self._compare_rules))

    def _edit_compare_rule(self):
        row = self._compare_rule_list.currentRow()
        if row < 0:
            return
        dlg = _CompareRuleDialog(self._compare_rules[row], parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._compare_rules[row] = dlg.result_rule()
            self._refresh_compare_rule_list()
            self._settings.setValue('compare_rules', rules_to_json(self._compare_rules))

    def _delete_compare_rule(self):
        row = self._compare_rule_list.currentRow()
        if row < 0:
            return
        name = self._compare_rules[row].name
        reply = QMessageBox.question(
            self, '确认删除', f'确定删除规则「{name}」吗？',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._compare_rules.pop(row)
            self._refresh_compare_rule_list()
            self._settings.setValue('compare_rules', rules_to_json(self._compare_rules))
```

- [ ] **Step 7: 确认启动无报错（UI 变更不跑 pytest）**

```
uv run python -c "from app.ui.tabs.settings_tab import SettingsTab; print('OK')"
```

预期：打印 `OK`，无报错。

- [ ] **Step 8: 提交**

```
git add app/ui/tabs/settings_tab.py
git commit -m "feat: 设置界面新增「比较规则」管理区块"
```

---

## Task 4: `app/ui/tabs/verify_tab.py` — 字段行规则下拉框

**Files:**
- Modify: `app/ui/tabs/verify_tab.py`

**背景：** `verify_tab.py` 当前顶部导入（第 6-13 行）中**没有** `QComboBox`，需要添加。`_FieldRow` 类在第 389 行，其 `__init__` 在第 393 行，`set_mapped()` 在第 421 行。`_MappingWidget` 在第 444 行，`get_mapping()` 在第 631 行，`_remove_mapping()` 在第 611 行。`_run()` 在第 1139 行，`VerifyHandler` 构造在第 1153 行。

- [ ] **Step 1: 在 `verify_tab.py` 顶部添加 `QComboBox` 导入**

将导入块中的 `QDialog, QGridLayout,` 改为 `QDialog, QGridLayout, QComboBox,`：

```python
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QCheckBox, QMessageBox,
    QRadioButton, QButtonGroup, QFileDialog,
    QSizePolicy, QFrame, QProgressBar,
    QScrollArea, QSpinBox, QLayout,
    QDialog, QGridLayout, QComboBox,
)
```

同时在导入区末尾（第 24 行 `DEFAULT_FIELD_ALIASES,` 下方）添加：

```python
from app.core.compare_rules import CompareRule, rules_from_json
```

- [ ] **Step 2: 在文件顶部（`_UpdateFieldDialog` 类之前）添加 `_NoScrollCombo`**

```python
class _NoScrollCombo(QComboBox):
    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()
```

- [ ] **Step 3: 修改 `_FieldRow.__init__`，添加规则下拉框**

在 `_FieldRow.__init__` 中，在 `self._remove_btn` 定义（第 414 行）之前插入规则下拉框，并初始化 `self._rules`：

`__init__` 方法的完整 body 改为：

```python
    def __init__(self, tag: str, display: str, parent=None):
        super().__init__(parent)
        self._field = tag
        self._rules: list[CompareRule] = []
        self.setObjectName('fieldRow')
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(6)

        name_lbl = QLabel(display)
        name_lbl.setObjectName('fieldRowName')
        name_lbl.setFixedWidth(180)
        layout.addWidget(name_lbl)

        self._map_lbl = QLabel('未匹配')
        self._map_lbl.setObjectName('fieldRowUnmapped')
        self._map_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._map_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(self._map_lbl, 1)

        self._rule_combo = _NoScrollCombo()
        self._rule_combo.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._rule_combo.setFixedWidth(110)
        self._rule_combo.addItem('（默认）')
        self._rule_combo.hide()
        layout.addWidget(self._rule_combo)

        self._remove_btn = QPushButton()
        self._remove_btn.setObjectName('fileItemRemove')
        self._remove_btn.setFixedSize(20, 20)
        self._remove_btn.hide()
        self._remove_btn.clicked.connect(lambda: self.remove_mapping.emit(self._field))
        layout.addWidget(self._remove_btn)
```

- [ ] **Step 4: 修改 `_FieldRow.set_mapped()`，控制规则下拉框的显隐**

将 `set_mapped()` 方法改为：

```python
    def set_mapped(self, excel_col: str | None):
        if excel_col:
            self._map_lbl.setText(excel_col)
            self._map_lbl.setObjectName('fieldRowMapped')
            self._rule_combo.show()
            self._remove_btn.show()
        else:
            self._map_lbl.setText('未匹配')
            self._map_lbl.setObjectName('fieldRowUnmapped')
            self._rule_combo.setCurrentIndex(0)
            self._rule_combo.hide()
            self._remove_btn.hide()
        self._map_lbl.style().unpolish(self._map_lbl)
        self._map_lbl.style().polish(self._map_lbl)
```

- [ ] **Step 5: 在 `_FieldRow` 中添加 `set_available_rules()` 和 `selected_rule()`**

在 `set_pending()` 方法之前插入：

```python
    def set_available_rules(self, rules: list[CompareRule]) -> None:
        current_name = self._rule_combo.currentText()
        self._rule_combo.clear()
        self._rule_combo.addItem('（默认）')
        for rule in rules:
            self._rule_combo.addItem(rule.name)
        self._rules = rules
        idx = self._rule_combo.findText(current_name)
        self._rule_combo.setCurrentIndex(idx if idx >= 0 else 0)

    def selected_rule(self) -> CompareRule | None:
        idx = self._rule_combo.currentIndex()
        if idx <= 0 or idx - 1 >= len(self._rules):
            return None
        return self._rules[idx - 1]
```

- [ ] **Step 6: 在 `_MappingWidget` 中添加 `set_available_rules()` 和 `get_rule_mapping()`**

在 `get_mapping()` 方法之后插入：

```python
    def set_available_rules(self, rules: list[CompareRule]) -> None:
        for row in self._field_rows.values():
            row.set_available_rules(rules)

    def get_rule_mapping(self) -> dict[str, CompareRule]:
        result: dict[str, CompareRule] = {}
        for lrmx_field, row in self._field_rows.items():
            if lrmx_field in self._reverse:
                rule = row.selected_rule()
                if rule is not None:
                    result[lrmx_field] = rule
        return result
```

- [ ] **Step 7: 修改 `_run()` 加载规则并传给 `VerifyHandler`**

将 `_run()` 方法（第 1139 行）中的开头改为：

```python
    def _run(self):
        raw_cr = self._settings.value('compare_rules', '')
        rules = rules_from_json(raw_cr)
        self._mapping_widget.set_available_rules(rules)
        rule_mapping = self._mapping_widget.get_rule_mapping()

        files = self._file_panel.files()
        excel_path = self._xl_edit.text()
        mapping = self._mapping_widget.get_mapping()
        ...
```

并将 `VerifyHandler(...)` 构造（第 1153 行）改为：

```python
        handler = VerifyHandler(
            excel_path=excel_path,
            lrmx_files=files,
            match_mode=match_mode,
            header_row=self._header_spin.value(),
            field_mapping=mapping,
            match_excel_col_for_id=id_col,
            match_excel_col_for_name=name_col,
            compare_rules=rule_mapping,
        )
```

- [ ] **Step 8: 确认导入无报错**

```
uv run python -c "from app.ui.tabs.verify_tab import VerifyTab; print('OK')"
```

预期：打印 `OK`，无报错。

- [ ] **Step 9: 运行所有测试**

```
uv run pytest tests/test_verify_handler.py tests/test_compare_rules.py -v
```

预期：全部通过。

- [ ] **Step 10: 提交**

```
git add app/ui/tabs/verify_tab.py
git commit -m "feat: 核验界面字段行新增规则下拉框，_run() 传入 compare_rules"
```

---

## 自查 checklist（实现者自用）

- [ ] `apply_rule` 严格相等时不被调用（`verify_handler.py` 先判 `_strip` 相等）
- [ ] 规则列表为空时，核验行为与改动前完全一致
- [ ] 关闭/重开应用，规则仍保留（QSettings 持久化）
- [ ] 在字段行未匹配时，规则下拉框隐藏
- [ ] 在字段行取消匹配（点 ×）后，规则下拉框重置为「（默认）」并隐藏
- [ ] `get_rule_mapping()` 只返回已匹配且选了非默认规则的字段
