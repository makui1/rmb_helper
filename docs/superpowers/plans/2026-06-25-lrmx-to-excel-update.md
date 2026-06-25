# LRMX → Excel 批量更新 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 LRMX→Excel 批量更新功能，新建独立 update_tab 承载双向更新，将 verify_tab 回归纯核验。

**Architecture:** 新建 `converters.py` 核心模块提供统一转换器接口（内置预设 + 用户自定义代码）。扩展 `ExcelHandler` 新增 `export_to_excel()` 方法。新建 `update_tab.py` 统一承载 Excel→LRMX 和 LRMX→Excel 两个方向。SettingsTab 扩展转换器管理区域。verify_tab 删除更新代码回归纯核验。

**Tech Stack:** Python 3.12, PySide6, openpyxl, BaseWorker/ExcelHandler/LrmxFile/MatchMode

**Spec:** `docs/superpowers/specs/2026-06-25-lrmx-to-excel-update-design.md`

## Global Constraints

- 所有 Python 命令用 `uv run python`，测试用 `uv run pytest -q --ignore=tests/test_verify_handler.py`
- Git commit 信息使用中文
- UI 改动无需测试，核心逻辑改动需测试
- 转换器列在 Excel→LRMX 方向隐藏，仅在 LRMX→Excel 方向显示

---

### Task 1: 创建 converters.py 核心模块

**Files:**
- Create: `app/core/converters.py`
- Create: `tests/test_converters.py`

**Interfaces:**
- Consumes: 无外部依赖（仅 stdlib re/datetime/json, PySide6.QtCore.QSettings）
- Produces:
  - `BUILTIN_CONVERTERS: list[dict]` — `[{'name': str, 'code': str, 'builtin': True}, ...]`
  - `load_custom_converters(settings: QSettings) -> list[dict]`
  - `save_custom_converters(settings: QSettings, converters: list[dict]) -> None`
  - `get_all_converters(settings: QSettings) -> list[dict]`
  - `execute_converter(code: str, value: str) -> str`

- [ ] **Step 1: 写 converters.py**

```python
# app/core/converters.py
"""转换器系统：内置预设 + 用户可编写自定义 Python 代码片段。

统一接口: def convert(value: str) -> str
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from PySide6.QtCore import QSettings


# ═══════════════════════════════════════════════════════════════════════
# 内置转换器函数
# ═══════════════════════════════════════════════════════════════════════

def _convert_date_yyyyMM_to_dot(value: str) -> str:
    """202506 → 2025.06"""
    v = value.strip()
    if len(v) != 6 or not v.isdigit():
        return value
    try:
        return datetime.strptime(v, '%Y%m').strftime('%Y.%m')
    except ValueError:
        return value


def _convert_date_yyyyMMdd_to_dot(value: str) -> str:
    """20250625 → 2025.06.25"""
    v = value.strip()
    if len(v) != 8 or not v.isdigit():
        return value
    try:
        return datetime.strptime(v, '%Y%m%d').strftime('%Y.%m.%d')
    except ValueError:
        return value


def _convert_date_dot_to_yyyyMM(value: str) -> str:
    """2025.06 → 202506"""
    v = value.strip()
    try:
        return datetime.strptime(v, '%Y.%m').strftime('%Y%m')
    except ValueError:
        return value


def _convert_date_dot_to_yyyyMMdd(value: str) -> str:
    """2025.06.25 → 20250625"""
    v = value.strip()
    try:
        return datetime.strptime(v, '%Y.%m.%d').strftime('%Y%m%d')
    except ValueError:
        return value


def _convert_strip_spaces(value: str) -> str:
    """去除所有空白字符"""
    return re.sub(r'\s+', '', value)


def _convert_gender_m_to_1(value: str) -> str:
    """男→1, 女→2"""
    return {'男': '1', '女': '2'}.get(value.strip(), value)


def _convert_gender_1_to_m(value: str) -> str:
    """1→男, 2→女"""
    return {'1': '男', '2': '女'}.get(value.strip(), value)


# ── 内置转换器元数据：(名称, 源码, 函数对象) ──────────────────────────

_BUILTIN_META: list[tuple[str, str, callable]] = [
    ('日期: yyyyMM → yyyy.MM',
     'def convert(value: str) -> str:\n'
     '    """202506 → 2025.06"""\n'
     '    from datetime import datetime\n'
     '    v = value.strip()\n'
     '    if len(v) != 6 or not v.isdigit():\n'
     '        return value\n'
     '    try:\n'
     '        return datetime.strptime(v, "%Y%m").strftime("%Y.%m")\n'
     '    except ValueError:\n'
     '        return value\n',
     _convert_date_yyyyMM_to_dot),
    ('日期: yyyyMMdd → yyyy.MM.dd',
     'def convert(value: str) -> str:\n'
     '    """20250625 → 2025.06.25"""\n'
     '    from datetime import datetime\n'
     '    v = value.strip()\n'
     '    if len(v) != 8 or not v.isdigit():\n'
     '        return value\n'
     '    try:\n'
     '        return datetime.strptime(v, "%Y%m%d").strftime("%Y.%m.%d")\n'
     '    except ValueError:\n'
     '        return value\n',
     _convert_date_yyyyMMdd_to_dot),
    ('日期: yyyy.MM → yyyyMM',
     'def convert(value: str) -> str:\n'
     '    """2025.06 → 202506"""\n'
     '    from datetime import datetime\n'
     '    v = value.strip()\n'
     '    try:\n'
     '        return datetime.strptime(v, "%Y.%m").strftime("%Y%m")\n'
     '    except ValueError:\n'
     '        return value\n',
     _convert_date_dot_to_yyyyMM),
    ('日期: yyyy.MM.dd → yyyyMMdd',
     'def convert(value: str) -> str:\n'
     '    """2025.06.25 → 20250625"""\n'
     '    from datetime import datetime\n'
     '    v = value.strip()\n'
     '    try:\n'
     '        return datetime.strptime(v, "%Y.%m.%d").strftime("%Y%m%d")\n'
     '    except ValueError:\n'
     '        return value\n',
     _convert_date_dot_to_yyyyMMdd),
    ('正则: 去除空格',
     'def convert(value: str) -> str:\n'
     '    """去除所有空白字符"""\n'
     '    import re\n'
     '    return re.sub(r"\\s+", "", value)\n',
     _convert_strip_spaces),
    ('字典: 性别(男→1)',
     'def convert(value: str) -> str:\n'
     '    """男→1, 女→2"""\n'
     '    return {"男": "1", "女": "2"}.get(value.strip(), value)\n',
     _convert_gender_m_to_1),
    ('字典: 性别(1→男)',
     'def convert(value: str) -> str:\n'
     '    """1→男, 2→女"""\n'
     '    return {"1": "男", "2": "女"}.get(value.strip(), value)\n',
     _convert_gender_1_to_m),
]

BUILTIN_CONVERTERS: list[dict] = [
    {'name': name, 'code': code, 'builtin': True}
    for name, code, _fn in _BUILTIN_META
]

# 内置名称 → 函数对象（快速执行）
_BUILTIN_FN: dict[str, callable] = {
    name: fn for name, _code, fn in _BUILTIN_META
}

# 内置源码 → 名称（执行时判断是否匹配内置）
_BUILTIN_CODE_TO_NAME: dict[str, str] = {
    code.strip(): name for name, code, _fn in _BUILTIN_META
}


# ═══════════════════════════════════════════════════════════════════════
# 用户自定义转换器存储
# ═══════════════════════════════════════════════════════════════════════

def load_custom_converters(settings: QSettings) -> list[dict]:
    raw = settings.value('converters_custom', '')
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return [
            {'name': d.get('name', ''), 'code': d.get('code', ''), 'builtin': False}
            for d in data
        ]
    except (json.JSONDecodeError, TypeError, AttributeError):
        return []


def save_custom_converters(settings: QSettings, converters: list[dict]) -> None:
    data = [
        {'name': c['name'], 'code': c['code']}
        for c in converters
        if not c.get('builtin', False)
    ]
    settings.setValue('converters_custom', json.dumps(data, ensure_ascii=False))


def get_all_converters(settings: QSettings) -> list[dict]:
    return BUILTIN_CONVERTERS + load_custom_converters(settings)


# ═══════════════════════════════════════════════════════════════════════
# 转换器执行
# ═══════════════════════════════════════════════════════════════════════

# 用户代码 exec 安全白名单
_EXEC_GLOBALS = {
    '__builtins__': {
        'str': str, 'int': int, 'float': float, 'bool': bool,
        'len': len, 'dict': dict, 'list': list, 'tuple': tuple, 'set': set,
        'True': True, 'False': False, 'None': None,
        'abs': abs, 'min': min, 'max': max, 'sum': sum,
        'enumerate': enumerate, 'zip': zip, 'range': range,
        'isinstance': isinstance, 'type': type,
        'print': print,
        're': re,
        'json': json,
    },
    'datetime': __import__('datetime'),
    're': re,
    'json': json,
}


def execute_converter(code: str, value: str) -> str:
    """执行转换器代码。内置按函数表查；用户代码用 exec 沙箱执行。失败返回原值。"""
    if not code or not code.strip():
        return value

    # 内置转换器直接查表执行
    stripped = code.strip()
    if stripped in _BUILTIN_CODE_TO_NAME:
        fn = _BUILTIN_FN.get(_BUILTIN_CODE_TO_NAME[stripped])
        if fn:
            try:
                return fn(value)
            except Exception:
                return value

    # 用户代码 exec
    try:
        local_ns: dict[str, object] = {}
        exec(code, _EXEC_GLOBALS, local_ns)
        convert_fn = local_ns.get('convert')
        if not callable(convert_fn):
            return value
        result = convert_fn(value)
        return str(result) if result is not None else ''
    except Exception:
        return value
```

- [ ] **Step 2: 写测试**

```python
# tests/test_converters.py
import pytest
from app.core.converters import (
    execute_converter, BUILTIN_CONVERTERS,
    get_all_converters, load_custom_converters, save_custom_converters,
)


class TestBuiltinConverters:
    def test_date_yyyyMM_to_dot(self):
        code = BUILTIN_CONVERTERS[0]['code']
        assert execute_converter(code, '202506') == '2025.06'
        assert execute_converter(code, 'abc') == 'abc'

    def test_date_yyyyMMdd_to_dot(self):
        code = BUILTIN_CONVERTERS[1]['code']
        assert execute_converter(code, '20250625') == '2025.06.25'

    def test_date_dot_to_yyyyMM(self):
        code = BUILTIN_CONVERTERS[2]['code']
        assert execute_converter(code, '2025.06') == '202506'

    def test_date_dot_to_yyyyMMdd(self):
        code = BUILTIN_CONVERTERS[3]['code']
        assert execute_converter(code, '2025.06.25') == '20250625'

    def test_strip_spaces(self):
        code = BUILTIN_CONVERTERS[4]['code']
        assert execute_converter(code, '张 三') == '张三'

    def test_gender_m_to_1(self):
        code = BUILTIN_CONVERTERS[5]['code']
        assert execute_converter(code, '男') == '1'
        assert execute_converter(code, '女') == '2'
        assert execute_converter(code, '未知') == '未知'

    def test_gender_1_to_m(self):
        code = BUILTIN_CONVERTERS[6]['code']
        assert execute_converter(code, '1') == '男'
        assert execute_converter(code, '2') == '女'


class TestUserConverters:
    def test_execute_valid_custom_code(self):
        code = 'def convert(value: str) -> str:\n    return value.upper()\n'
        assert execute_converter(code, 'hello') == 'HELLO'

    def test_execute_code_with_regex(self):
        code = (
            'def convert(value: str) -> str:\n'
            '    import re\n'
            '    return re.sub(r"(\\d{4})(\\d{2})(\\d{2})", r"\\1.\\2.\\3", value)\n'
        )
        assert execute_converter(code, '20250625') == '2025.06.25'

    def test_execute_invalid_code_returns_original(self):
        code = 'def convert(value: str) -> str:\n    raise ValueError("oops")\n'
        assert execute_converter(code, 'hello') == 'hello'

    def test_execute_empty_code_returns_original(self):
        assert execute_converter('', 'hello') == 'hello'

    def test_execute_none_result_returns_empty(self):
        code = 'def convert(value: str) -> str:\n    return None\n'
        assert execute_converter(code, 'hello') == ''


class TestPersistence:
    def test_load_empty(self):
        from PySide6.QtCore import QSettings
        settings = QSettings('test_rmb', 'test_rmb')
        settings.setValue('converters_custom', '')
        result = load_custom_converters(settings)
        assert result == []

    def test_roundtrip(self):
        from PySide6.QtCore import QSettings
        settings = QSettings('test_rmb', 'test_rmb')
        converters = [{'name': 'test', 'code': 'def convert(v): return v', 'builtin': False}]
        save_custom_converters(settings, converters)
        loaded = load_custom_converters(settings)
        assert len(loaded) == 1
        assert loaded[0]['name'] == 'test'

    def test_get_all_includes_builtins(self):
        from PySide6.QtCore import QSettings
        settings = QSettings('test_rmb', 'test_rmb')
        settings.setValue('converters_custom', '')
        all_conv = get_all_converters(settings)
        assert len(all_conv) == len(BUILTIN_CONVERTERS)
        assert all(c['builtin'] for c in all_conv)
```

- [ ] **Step 3: 运行测试**

Run: `uv run pytest tests/test_converters.py -v`
Expected: 所有测试 PASS

- [ ] **Step 4: Commit**

```bash
git add app/core/converters.py tests/test_converters.py
git commit -m "feat: 创建 converters.py 转换器系统核心模块"
```

---

### Task 2: ExcelHandler 新增 export_to_excel() 方法

**Files:**
- Modify: `app/core/excel_handler.py`
- Create: `tests/test_excel_handler_export.py`

**Interfaces:**
- Consumes: `converters.execute_converter`, `LrmxFile`, `MatchMode`, `openpyxl`
- Produces: `ExcelHandler.export_to_excel(field_mapping, fields_to_write, converters, header_row, match_excel_col_for_id, match_excel_col_for_name, progress_cb) -> list[str]`

- [ ] **Step 1: 在 update() 方法后新增 export_to_excel()**

在 `excel_handler.py` 第 132 行 `return logs` 之后插入：

```python
    def export_to_excel(
        self,
        field_mapping: dict[str, str],
        fields_to_write: list[str],
        converters: dict[str, str] | None = None,
        header_row: int = 1,
        match_excel_col_for_id: str | None = None,
        match_excel_col_for_name: str | None = None,
        progress_cb: Optional[Callable[[str], None]] = None,
    ) -> list[str]:
        """
        从 LRMX 文件读取数据，更新匹配的 Excel 行。

        field_mapping:           lrmx字段名 → excel列名 (与 update() 方向相反)
        fields_to_write:         实际要写入 Excel 的 lrmx 字段名
        converters:              lrmx字段名 → 转换器代码（仅需转换的字段）
        header_row:              Excel 表头行号（1-based）
        match_excel_col_for_id:  用于匹配身份证的 Excel 列名
        match_excel_col_for_name:用于匹配姓名的 Excel 列名
        """
        from app.core.converters import execute_converter

        converters = converters or {}

        if self.match_mode == MatchMode.ID_CARD and not match_excel_col_for_id:
            raise ValueError('ID_CARD 匹配模式需要提供 match_excel_col_for_id')
        if self.match_mode == MatchMode.NAME and not match_excel_col_for_name:
            raise ValueError('NAME 匹配模式需要提供 match_excel_col_for_name')
        if self.match_mode == MatchMode.NAME_AND_ID and not (
            match_excel_col_for_id and match_excel_col_for_name
        ):
            raise ValueError(
                'NAME_AND_ID 匹配模式需要同时提供 match_excel_col_for_id '
                '和 match_excel_col_for_name'
            )

        wb = openpyxl.load_workbook(self.excel_path)
        ws = wb.active

        headers = [
            cell.value
            for cell in next(ws.iter_rows(min_row=header_row, max_row=header_row))
        ]

        excel_index: dict[str, tuple[int, dict]] = {}
        for row_idx, row_values in enumerate(
            ws.iter_rows(min_row=header_row + 1, values_only=True), start=header_row + 1
        ):
            row = dict(zip(headers, row_values))
            key = self._excel_key(row, match_excel_col_for_id, match_excel_col_for_name)
            if key:
                excel_index[key] = (row_idx, row)

        lrmx_index = self._load_index()
        logs: list[str] = []

        # 收集需要新增的列（Excel 表头中不存在的字段）
        existing_cols = set(headers)
        new_columns: list[str] = []
        for lrmx_field in fields_to_write:
            excel_col = field_mapping.get(lrmx_field, lrmx_field)
            if excel_col not in existing_cols:
                new_columns.append(excel_col)
                existing_cols.add(excel_col)

        # 构建 headers 查找索引
        header_index: dict[str, int] = {}
        for i, h in enumerate(headers):
            if h is not None:
                header_index[str(h)] = i + 1

        updated_count = 0

        for lrmx_key, lf in lrmx_index.items():
            name = lf.get('XingMing') or lrmx_key
            if lrmx_key not in excel_index:
                msg = f'△ {name}  未在名册中找到匹配记录'
                logs.append(msg)
                if progress_cb:
                    progress_cb(msg)
                continue

            row_idx, excel_row = excel_index[lrmx_key]
            updated = 0
            try:
                for lrmx_field in fields_to_write:
                    excel_col = field_mapping.get(lrmx_field, lrmx_field)
                    val = lf.get(lrmx_field)

                    # 应用转换器
                    converter_code = converters.get(lrmx_field, '')
                    if converter_code and val:
                        val = execute_converter(converter_code, val)

                    # 写入 Excel 单元格
                    col_idx = header_index.get(excel_col)
                    if col_idx is not None and val:
                        ws.cell(row=row_idx, column=col_idx, value=val)
                        updated += 1

                if updated > 0:
                    updated_count += 1
                msg = f'✓ {name}  已更新 {updated} 个字段'
                logs.append(msg)
                if progress_cb:
                    progress_cb(msg)
            except Exception as e:
                msg = f'✗ {name}  {e}'
                logs.append(msg)
                if progress_cb:
                    progress_cb(msg)

        # 追加新列到末尾
        last_col = ws.max_column
        for i, col_name in enumerate(new_columns):
            col_idx = last_col + 1 + i
            ws.cell(row=header_row, column=col_idx, value=col_name)
            header_index[col_name] = col_idx

        # 备份并保存
        import shutil
        backup = self.excel_path.with_suffix('.xlsx.bak')
        shutil.copy2(self.excel_path, backup)
        try:
            wb.save(self.excel_path)
        except Exception:
            shutil.copy2(backup, self.excel_path)
            raise

        summary = (
            f'共处理 {len(lrmx_index)} 个文件，更新 {updated_count} 行'
        )
        if new_columns:
            summary += f'，新增 {len(new_columns)} 列'
        logs.insert(0, summary)
        return logs
```

- [ ] **Step 2: 写测试**

```python
# tests/test_excel_handler_export.py
import tempfile
from pathlib import Path
import pytest
import openpyxl
from app.core.excel_handler import ExcelHandler, MatchMode


def _make_excel(path: Path, headers: list, rows: list[list]) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    for i, h in enumerate(headers, 1):
        ws.cell(row=1, column=i, value=h)
    for r, row in enumerate(rows, 2):
        for c, val in enumerate(row, 1):
            ws.cell(row=r, column=c, value=val)
    wb.save(path)
    return path


def _make_lrmx(path: Path, fields: dict[str, str]) -> Path:
    import xml.etree.ElementTree as ET
    root = ET.Element('Person')
    for k, v in fields.items():
        elem = ET.SubElement(root, k)
        elem.text = v
    tree = ET.ElementTree(root)
    ET.indent(tree, space='    ')
    tree.write(str(path), encoding='UTF-8', xml_declaration=True)
    return path


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


class TestExportToExcel:
    def test_basic_export(self, temp_dir):
        excel = _make_excel(temp_dir / 'test.xlsx',
            ['身份证号', '姓名', '出生年月'],
            [['110101199001011234', '张三', '']])
        lrmx = _make_lrmx(temp_dir / 'test.lrmx',
            {'XingMing': '张三', 'ShenFenZheng': '110101199001011234', 'ChuShengNianYue': '199001'})

        handler = ExcelHandler(excel, [lrmx], MatchMode.ID_CARD)
        handler.export_to_excel(
            field_mapping={'ChuShengNianYue': '出生年月'},
            fields_to_write=['ChuShengNianYue'],
            header_row=1,
            match_excel_col_for_id='身份证号',
        )

        wb = openpyxl.load_workbook(excel)
        ws = wb.active
        assert ws.cell(row=2, column=3).value == '199001'

    def test_unmatched_skipped(self, temp_dir):
        excel = _make_excel(temp_dir / 'test.xlsx',
            ['身份证号', '姓名'], [['110101199001011234', '张三']])
        lrmx = _make_lrmx(temp_dir / 'test.lrmx',
            {'XingMing': '李四', 'ShenFenZheng': '999999999999999999'})

        handler = ExcelHandler(excel, [lrmx], MatchMode.ID_CARD)
        logs = handler.export_to_excel(
            field_mapping={}, fields_to_write=[],
            header_row=1, match_excel_col_for_id='身份证号',
        )
        assert any('未在名册中找到匹配记录' in m for m in logs)

    def test_new_columns_appended(self, temp_dir):
        excel = _make_excel(temp_dir / 'test.xlsx',
            ['身份证号', '姓名'], [['110101199001011234', '张三']])
        lrmx = _make_lrmx(temp_dir / 'test.lrmx',
            {'XingMing': '张三', 'ShenFenZheng': '110101199001011234', 'XueLi': '本科'})

        handler = ExcelHandler(excel, [lrmx], MatchMode.ID_CARD)
        handler.export_to_excel(
            field_mapping={'XueLi': '最高学历'},
            fields_to_write=['XueLi'],
            header_row=1,
            match_excel_col_for_id='身份证号',
        )

        wb = openpyxl.load_workbook(excel)
        ws = wb.active
        assert ws.cell(row=1, column=3).value == '最高学历'
        assert ws.cell(row=2, column=3).value == '本科'

    def test_with_converter(self, temp_dir):
        excel = _make_excel(temp_dir / 'test.xlsx',
            ['身份证号', '姓名', '出生年月'],
            [['110101199001011234', '张三', '']])
        lrmx = _make_lrmx(temp_dir / 'test.lrmx',
            {'XingMing': '张三', 'ShenFenZheng': '110101199001011234', 'ChuShengNianYue': '199001'})

        from app.core.converters import BUILTIN_CONVERTERS
        date_code = BUILTIN_CONVERTERS[0]['code']

        handler = ExcelHandler(excel, [lrmx], MatchMode.ID_CARD)
        handler.export_to_excel(
            field_mapping={'ChuShengNianYue': '出生年月'},
            fields_to_write=['ChuShengNianYue'],
            converters={'ChuShengNianYue': date_code},
            header_row=1,
            match_excel_col_for_id='身份证号',
        )

        wb = openpyxl.load_workbook(excel)
        ws = wb.active
        assert ws.cell(row=2, column=3).value == '1990.01'

    def test_backup_created(self, temp_dir):
        excel = _make_excel(temp_dir / 'test.xlsx',
            ['身份证号', '姓名'], [['110101199001011234', '张三']])
        lrmx = _make_lrmx(temp_dir / 'test.lrmx',
            {'XingMing': '张三', 'ShenFenZheng': '110101199001011234', 'XueLi': '本科'})

        handler = ExcelHandler(excel, [lrmx], MatchMode.ID_CARD)
        handler.export_to_excel(
            field_mapping={'XueLi': '学历'}, fields_to_write=['XueLi'],
            header_row=1, match_excel_col_for_id='身份证号',
        )
        assert (temp_dir / 'test.xlsx.bak').exists()
```

- [ ] **Step 3: 运行测试**

Run: `uv run pytest tests/test_excel_handler_export.py -v`
Expected: 所有测试 PASS

- [ ] **Step 4: 运行全部测试确保无回归**

Run: `uv run pytest -q --ignore=tests/test_verify_handler.py`
Expected: 100 passing

- [ ] **Step 5: Commit**

```bash
git add app/core/excel_handler.py tests/test_excel_handler_export.py
git commit -m "feat: ExcelHandler 新增 export_to_excel() 方法，支持 LRMX→Excel"
```

---

### Task 3: field_mapping widget 增加转换器列

**Files:**
- Modify: `app/ui/widgets/field_mapping.py`

**Interfaces:**
- Changes: `_FieldRow.__init__` 新增 `converters` 参数和 `_converter_combo`
- New methods: `_FieldRow.selected_converter_code()`, `_FieldRow.set_converter_visible()`, `_MappingWidget.set_converters_visible()`, `_MappingWidget.get_converter_mapping()`

- [ ] **Step 1: 修改 _FieldRow 构造函数**

```python
# __init__ 签名增加 converters 参数
def __init__(self, tag: str, display: str, converters: list[dict] = None, parent=None):
    super().__init__(parent)
    # ... 现有 name_lbl, _map_lbl, _rule_combo ...

    # 新增：转换器下拉框 (在 _rule_combo 之后，_remove_btn 之前)
    self._converter_combo = _NoScrollCombo()
    self._converter_combo.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    self._converter_combo.setFixedWidth(160)
    self._converter_combo.addItem('无转换', None)
    if converters:
        for c in converters:
            self._converter_combo.addItem(c['name'], c['code'])
    self._converter_combo.hide()
    layout.addWidget(self._converter_combo)

    # ... 现有 _remove_btn ...
```

- [ ] **Step 2: 修改 set_mapped 同步显示/隐藏转换器**

```python
def set_mapped(self, excel_col: str | None):
    if excel_col:
        # ... 现有 ...
        self._converter_combo.show()
        # ...
    else:
        # ... 现有 ...
        self._converter_combo.setCurrentIndex(0)
        self._converter_combo.hide()
        # ...
```

- [ ] **Step 3: 新增方法**

```python
def selected_converter_code(self) -> str | None:
    return self._converter_combo.currentData()

def set_converter_visible(self, visible: bool):
    """由外部控制转换器列的可见性（方向切换时调用）"""
    if visible and self._map_lbl.objectName() == 'fieldRowMapped':
        self._converter_combo.show()
    else:
        self._converter_combo.hide()
```

- [ ] **Step 4: 修改 _MappingWidget.load_lrmx_fields 传递 converters**

```python
def load_lrmx_fields(self, fields: list[tuple[str, str]], converters: list[dict] = None):
    # ... clear existing ...
    for tag, display in fields:
        row = _FieldRow(tag, display, converters=converters)  # ← 传入 converters
        # ...
```

- [ ] **Step 3: _MappingWidget 新增方法**

```python
def set_converters_visible(self, visible: bool):
    for row in self._field_rows.values():
        row.set_converter_visible(visible)

def get_converter_mapping(self) -> dict[str, str]:
    result: dict[str, str] = {}
    for lrmx_field, row in self._field_rows.items():
        if lrmx_field in self._reverse:
            code = row.selected_converter_code()
            if code:
                result[lrmx_field] = code
    return result
```

- [ ] **Step 4: 运行测试确保无回归**

Run: `uv run pytest -q --ignore=tests/test_verify_handler.py`
Expected: 100 passing

- [ ] **Step 5: Commit**

```bash
git add app/ui/widgets/field_mapping.py
git commit -m "feat: field_mapping 字段行增加转换器下拉框列"
```

---

### Task 4: 新建 update_tab.py — 双向批量更新 tab

**Files:**
- Create: `app/ui/tabs/update_tab.py`

详细代码见上面设计讨论中的完整实现。关键结构：
- `DIRECTION_IMPORT = 0` / `DIRECTION_EXPORT = 1` 方向常量
- `_ImportWorker(BaseWorker)` — Excel→LRMX worker
- `_ExportWorker(BaseWorker)` — LRMX→Excel worker
- `UpdateTab(QWidget)` — 主 tab 类
  - `USES_FILE_PANEL = True`
  - `busy_changed = Signal(bool)`
  - 方向切换按钮 → `_switch_direction()`
  - 文件选择、字段匹配、匹配依据、开始按钮 → 复用 verify_tab 模式
  - 日志区域 + 过滤按钮 + LoadingOverlay
  - `_run()` 方法根据方向启动不同 worker

特别注意：LRMX→Excel 方向需反转映射 `{excel_col: lrmx_field}` → `{lrmx_field: excel_col}` 并传递 converters。

- [ ] **Step 1: 写 update_tab.py 完整代码**

参照上面 Task 4 完整代码（见设计讨论）。

- [ ] **Step 2: 运行测试确保无回归**

Run: `uv run pytest -q --ignore=tests/test_verify_handler.py`
Expected: 100 passing（import 不报错）

- [ ] **Step 3: Commit**

```bash
git add app/ui/tabs/update_tab.py
git commit -m "feat: 新建 update_tab.py 双向批量更新 tab"
```

---

### Task 5: verify_tab.py 清理

**Files:**
- Modify: `app/ui/tabs/verify_tab.py`

**变更清单：**
1. 删除 `_UpdateWorker` 类（第57-80行）
2. 删除 `__init__` 中：`self._update_worker`、`self._update_counts`、`self._update_log_rows`、`self._update_active_filter`
3. 删除 `_build_ui` 中：`self._update_btn`（开始更新按钮）、`_update_filter_row`（第351-368行）、`_update_scroll`（第370-382行）、`_update_loading_overlay`（第384-385行）
4. 删除方法：`_run_update`、`_on_update_log`、`_on_update_critical`、`_on_update_finished`、`_set_update_filter`、`_clear_update_results`
5. 清理 `_back_to_setup` 中的更新相关代码
6. 清理 `eventFilter` 中 `_update_scroll` 判断
7. 清理 `_update_run_btn` 中 `_update_btn.setEnabled` 调用
8. 清理不再使用的 import（`_UpdateFieldDialog`、`_UpdateLogRow` 等，如果不再使用）

- [ ] **Step 1: 删除 _UpdateWorker 类** — 删除 verify_tab.py 第57-80行

- [ ] **Step 2: 删除 __init__ 中更新状态变量** — 删除 `self._update_worker = None`、`self._update_counts`、`self._update_log_rows`、`self._update_active_filter`

- [ ] **Step 3: 删除 _build_ui 中更新按钮** — 删除 `self._update_btn` 创建和 `run_row.addWidget`（第212-217行附近）

- [ ] **Step 4: 删除 _update_filter_row 和 _update_scroll** — 删除第351-385行（整个更新结果区域）

- [ ] **Step 5: 删除 6 个 _update_* 方法** — `_run_update`、`_on_update_log`、`_on_update_critical`、`_on_update_finished`、`_set_update_filter`、`_clear_update_results`

- [ ] **Step 6: 清理 _back_to_setup** — 删除其中的 `_update_loading_overlay.hide()`、`_update_worker` disconnect、`_update_filter_row.hide()`、`_update_scroll.hide()`、`_clear_update_results()`

- [ ] **Step 7: 清理 eventFilter** — 删除 `elif obj is self._update_scroll: self._update_loading_overlay.resize(...)`

- [ ] **Step 8: 清理 _update_run_btn** — 删除 `self._update_btn.setEnabled(ready)` 和 `self._update_btn.setToolTip(tip)`

- [ ] **Step 9: 清理 import** — 删除不再使用的 `_UpdateFieldDialog`（如果只有 update 用）、`_UpdateLogRow`、`_HoverIconButton` 等（需检查 verify_tab 剩余代码是否仍引用）

- [ ] **Step 7: 运行测试确保无回归**

Run: `uv run pytest -q --ignore=tests/test_verify_handler.py`
Expected: 100 passing

- [ ] **Step 8: Commit**

```bash
git add app/ui/tabs/verify_tab.py
git commit -m "refactor: verify_tab 删除更新面板代码，回归纯核验职责"
```

---

### Task 6: settings_tab.py 新增转换器管理区域

**Files:**
- Modify: `app/ui/tabs/settings_tab.py`

**变更内容：**
在比较规则区域之后、`layout.addStretch()` 之前，新增：
- 转换器列表（QListWidget），显示所有内置 + 自定义，🔒/✏ 前缀区分
- 新建/编辑/删除按钮（内置只读）
- 编辑面板：名称输入 + 代码编辑器 + 测试行
- 保存时用 `compile()` 验证语法

新增方法：`_load_converters`、`_refresh_converter_list`、`_on_converter_selected`、`_add_converter`、`_edit_converter`、`_delete_converter`、`_save_converter`、`_cancel_converter_edit`、`_persist_converters`、`_on_converter_test`

在 `_load()` 末尾调用 `_load_converters()`

新增 import：`from PySide6.QtWidgets import QPlainTextEdit`

- [ ] **Step 1: 实现转换器管理 UI 和方法**

按设计 spec Section 6 实现。

- [ ] **Step 2: 运行测试确保无回归**

Run: `uv run pytest -q --ignore=tests/test_verify_handler.py`
Expected: 100 passing

- [ ] **Step 3: Commit**

```bash
git add app/ui/tabs/settings_tab.py
git commit -m "feat: settings_tab 新增转换器管理区域"
```

---

### Task 7: main_window.py 注册 UpdateTab

**Files:**
- Modify: `app/ui/main_window.py`
- Create: `app/ui/assets/update.svg`（如果没有的话，复制 verify.svg）

**变更：**
1. 导航列表增加 `('批量更新', 'update.svg')` 在编辑器之后
2. 原有"批量核验/更新"改为"批量核验"
3. `_switch_tab` 中 index 5 → UpdateTab
4. 复制/创建 update.svg 图标

- [ ] **Step 1: 增加导航按钮**

```python
    for label, icon in [
        ('批量格式转换', 'convert.svg'),
        ('批量版本兼容', 'compat.svg'),
        ('批量核验', 'verify.svg'),
        ('生成家庭关系表', 'export.svg'),
        ('任免表编辑器', 'edit.svg'),
        ('批量更新', 'update.svg'),
    ]:
```

- [ ] **Step 2: 增加 UpdateTab 分支**

```python
    elif index == 5:
        from app.ui.tabs.update_tab import UpdateTab
        tab = UpdateTab(self._file_panel)
```

- [ ] **Step 3: 复制图标**

```powershell
copy app\ui\assets\verify.svg app\ui\assets\update.svg
```

- [ ] **Step 4: 运行测试确保无回归**

Run: `uv run pytest -q --ignore=tests/test_verify_handler.py`
Expected: 100 passing

- [ ] **Step 5: Commit**

```bash
git add app/ui/main_window.py app/ui/assets/update.svg
git commit -m "feat: main_window 注册 UpdateTab，导航新增批量更新入口"
```

---

### 验收

完成所有 Task 后：

- [ ] `uv run pytest -q --ignore=tests/test_verify_handler.py` → 全部通过
- [ ] `uv run pytest tests/test_converters.py tests/test_excel_handler_export.py -v` → 全部通过
- [ ] 导航栏有 6 个功能按钮 + 设置
- [ ] 方向切换时转换器列正确显示/隐藏
- [ ] 内置转换器在设置页不可编辑删除
- [ ] verify_tab.py 不再包含 `_update_` 方法
