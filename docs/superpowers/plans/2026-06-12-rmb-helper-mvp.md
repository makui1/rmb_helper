# rmb_helper MVP 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个 PySide6 桌面应用，支持批量将 .lrmx 文件转换为 docx/pdf，以及通过 Excel 批量更新 lrmx 字段。

**Architecture:** core/ 层为纯 Python 业务逻辑（不依赖 PySide6），ui/ 层调用 core/ 并通过 QThread + Signal 实现非阻塞操作。QSS 全局样式表实现 Claude Code Desktop 亮色风格。

**Tech Stack:** Python 3.14, PySide6 6.11.0, docxtpl, openpyxl, python-docx, pytest

---

## 文件结构

```
rmb_helper/
├── main.py                          # 入口
├── app/
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── lrmx.py                  # LrmxFile：XML 读写
│   │   ├── docx_exporter.py         # DocxExporter：模板填充
│   │   ├── pdf_exporter.py          # PdfExporter：引擎检测 + 转换
│   │   └── excel_handler.py         # ExcelHandler：匹配 + 字段更新
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── style.py                 # QSS 样式表常量
│   │   ├── main_window.py           # MainWindow + QTabWidget
│   │   └── tabs/
│   │       ├── __init__.py
│   │       ├── convert_tab.py       # Tab1：转换导出
│   │       ├── update_tab.py        # Tab2：批量更新
│   │       └── settings_tab.py      # Tab3：设置
│   └── utils/
│       ├── __init__.py
│       └── naming.py                # 文件命名规则引擎
└── tests/
    ├── conftest.py                   # 共享 fixture
    ├── test_lrmx.py
    ├── test_naming.py
    ├── test_docx_exporter.py
    ├── test_pdf_exporter.py
    └── test_excel_handler.py
```

---

## Task 1: 项目依赖与目录骨架

**Files:**
- Modify: `pyproject.toml`
- Create: `app/__init__.py`, `app/core/__init__.py`, `app/ui/__init__.py`, `app/ui/tabs/__init__.py`, `app/utils/__init__.py`, `tests/conftest.py`

- [ ] **Step 1: 更新 pyproject.toml，添加新依赖和 dev 依赖**

将 `pyproject.toml` 改为：

```toml
[project]
name = "rmb_helper"
version = "0.1.0"
description = "任免审批表小工具"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "docxtpl>=0.16.0",
    "openpyxl>=3.1.0",
    "pillow>=11.3.0",
    "pyside6==6.11.0",
    "python-docx>=1.2.0",
]

[dependency-groups]
dev = [
    "pytest>=8.0.0",
    "pytest-qt>=4.4.0",
]

[[index]]
url = "https://pypi.tuna.tsinghua.edu.cn/simple"
default = true
```

注意：移除了 `pyinstaller`（打包是后期工作），`requires-python` 放宽到 `>=3.12` 以兼容 pytest-qt。

- [ ] **Step 2: 安装依赖**

```bash
uv sync
```

预期输出：Resolved ... packages，无报错。

- [ ] **Step 3: 创建目录骨架**

```bash
mkdir -p app/core app/ui/tabs app/utils tests
touch app/__init__.py app/core/__init__.py app/ui/__init__.py
touch app/ui/tabs/__init__.py app/utils/__init__.py
touch tests/conftest.py
```

- [ ] **Step 4: 创建 tests/conftest.py**

```python
from pathlib import Path
import pytest

SAMPLES_DIR = Path(__file__).parent / 'samples'

@pytest.fixture
def sample_lrmx(tmp_path):
    content = '''<?xml version="1.0" encoding="UTF-8"?>
<Person>
    <XingMing>张三</XingMing>
    <XingBie>男</XingBie>
    <ChuShengNianYue>199001</ChuShengNianYue>
    <MinZu>汉族</MinZu>
    <ShenFenZheng>110101199001011234</ShenFenZheng>
    <RuDangShiJian>201506</RuDangShiJian>
    <CanJiaGongZuoShiJian>201207</CanJiaGongZuoShiJian>
    <JianKangZhuangKuang>健康</JianKangZhuangKuang>
    <XianRenZhiWu>科员</XianRenZhiWu>
    <NiRenZhiWu/>
    <NiMianZhiWu/>
    <ZhengZhiMianMao>中共党员</ZhengZhiMianMao>
    <QuanRiZhiJiaoYu_XueLi>本科</QuanRiZhiJiaoYu_XueLi>
    <TianBiaoRen>李四</TianBiaoRen>
</Person>'''
    p = tmp_path / 'zhangsan.lrmx'
    p.write_text(content, encoding='utf-8')
    return p
```

- [ ] **Step 5: 验证目录结构**

```bash
find app tests -name "*.py" | sort
```

预期：列出所有 `__init__.py` 和 `conftest.py`。

- [ ] **Step 6: 提交**

```bash
git add pyproject.toml app/ tests/
git commit -m "chore: project skeleton and dependencies"
```

---

## Task 2: LrmxFile（core/lrmx.py）

**Files:**
- Create: `app/core/lrmx.py`
- Create: `tests/test_lrmx.py`

- [ ] **Step 1: 写失败测试**

新建 `tests/test_lrmx.py`：

```python
from app.core.lrmx import LrmxFile

def test_get_existing_field(sample_lrmx):
    lf = LrmxFile(sample_lrmx)
    assert lf.get('XingMing') == '张三'

def test_get_missing_field_returns_empty(sample_lrmx):
    lf = LrmxFile(sample_lrmx)
    assert lf.get('NotExist') == ''

def test_get_empty_element_returns_empty(sample_lrmx):
    lf = LrmxFile(sample_lrmx)
    assert lf.get('NiRenZhiWu') == ''

def test_set_existing_field(sample_lrmx):
    lf = LrmxFile(sample_lrmx)
    lf.set('XianRenZhiWu', '副科长')
    assert lf.get('XianRenZhiWu') == '副科长'

def test_set_new_field(sample_lrmx):
    lf = LrmxFile(sample_lrmx)
    lf.set('NewField', '新值')
    assert lf.get('NewField') == '新值'

def test_save_and_reload(sample_lrmx, tmp_path):
    lf = LrmxFile(sample_lrmx)
    lf.set('XianRenZhiWu', '副科长')
    out = tmp_path / 'out.lrmx'
    lf.save(out)
    lf2 = LrmxFile(out)
    assert lf2.get('XianRenZhiWu') == '副科长'

def test_as_dict_contains_fields(sample_lrmx):
    lf = LrmxFile(sample_lrmx)
    d = lf.as_dict()
    assert d['XingMing'] == '张三'
    assert d['ShenFenZheng'] == '110101199001011234'

def test_save_overwrites_in_place(sample_lrmx):
    lf = LrmxFile(sample_lrmx)
    lf.set('XingMing', '李雷')
    lf.save()
    lf2 = LrmxFile(sample_lrmx)
    assert lf2.get('XingMing') == '李雷'
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
uv run pytest tests/test_lrmx.py -v
```

预期：`ImportError: cannot import name 'LrmxFile'`

- [ ] **Step 3: 实现 app/core/lrmx.py**

```python
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional


class LrmxFile:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._tree = ET.parse(self.path)
        self._root = self._tree.getroot()

    def get(self, field: str) -> str:
        elem = self._root.find(field)
        if elem is None:
            return ''
        return elem.text or ''

    def set(self, field: str, value: str) -> None:
        elem = self._root.find(field)
        if elem is not None:
            elem.text = value
        else:
            new_elem = ET.SubElement(self._root, field)
            new_elem.text = value

    def save(self, path: Optional[Path] = None) -> None:
        target = Path(path) if path else self.path
        ET.indent(self._tree, space='    ')
        self._tree.write(
            str(target),
            encoding='UTF-8',
            xml_declaration=True,
        )

    def as_dict(self) -> dict[str, str]:
        return {elem.tag: (elem.text or '') for elem in self._root}
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
uv run pytest tests/test_lrmx.py -v
```

预期：8 passed。

- [ ] **Step 5: 提交**

```bash
git add app/core/lrmx.py tests/test_lrmx.py
git commit -m "feat: LrmxFile XML read/write core"
```

---

## Task 3: 文件命名规则引擎（utils/naming.py）

**Files:**
- Create: `app/utils/naming.py`
- Create: `tests/test_naming.py`

- [ ] **Step 1: 写失败测试**

新建 `tests/test_naming.py`：

```python
from app.utils.naming import apply_rule, PRESETS

def test_basic_substitution():
    fields = {'XingMing': '张三', 'ShenFenZheng': '110101199001011234'}
    assert apply_rule('{XingMing}{ShenFenZheng}', fields) == '张三110101199001011234'

def test_missing_field_kept_as_placeholder():
    fields = {'XingMing': '张三'}
    assert apply_rule('{XingMing}_{ShenFenZheng}', fields) == '张三_{ShenFenZheng}'

def test_illegal_chars_replaced():
    fields = {'XingMing': '张/三', 'ShenFenZheng': '123'}
    result = apply_rule('{XingMing}{ShenFenZheng}', fields)
    assert '/' not in result
    assert result == '张_三123'

def test_empty_template_returns_unnamed():
    assert apply_rule('', {}) == '未命名'

def test_presets_is_list_of_tuples():
    assert isinstance(PRESETS, list)
    assert all(isinstance(p, tuple) and len(p) == 2 for p in PRESETS)

def test_presets_first_item_is_default():
    template, label = PRESETS[0]
    assert '{XingMing}' in template
    assert '{ShenFenZheng}' in template
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
uv run pytest tests/test_naming.py -v
```

预期：`ImportError`

- [ ] **Step 3: 实现 app/utils/naming.py**

```python
import re

FIELD_PATTERN = re.compile(r'\{(\w+)\}')
ILLEGAL_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

PRESETS: list[tuple[str, str]] = [
    ('{XingMing}{ShenFenZheng}', '姓名+身份证号'),
    ('{XingMing}_{XianRenZhiWu}', '姓名+现任职务'),
    ('{XingMing}_{ChuShengNianYue}', '姓名+出生年月'),
]


def apply_rule(template: str, fields: dict[str, str]) -> str:
    def replace(m: re.Match) -> str:
        key = m.group(1)
        return fields.get(key, f'{{{key}}}')

    result = FIELD_PATTERN.sub(replace, template)
    result = ILLEGAL_CHARS.sub('_', result)
    return result or '未命名'
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
uv run pytest tests/test_naming.py -v
```

预期：6 passed。

- [ ] **Step 5: 提交**

```bash
git add app/utils/naming.py tests/test_naming.py
git commit -m "feat: file naming rule engine with preset templates"
```

---

## Task 4: DocxExporter（core/docx_exporter.py）

**Files:**
- Create: `app/core/docx_exporter.py`
- Create: `tests/test_docx_exporter.py`

- [ ] **Step 1: 写失败测试**

新建 `tests/test_docx_exporter.py`：

```python
from pathlib import Path
from docx import Document
from app.core.lrmx import LrmxFile
from app.core.docx_exporter import DocxExporter


def make_template(path: Path) -> Path:
    """创建一个含 Jinja2 占位符的最小 docx 模板。"""
    doc = Document()
    doc.add_paragraph('姓名：{{XingMing}}')
    doc.add_paragraph('性别：{{XingBie}}')
    doc.add_paragraph('身份证：{{ShenFenZheng}}')
    doc.save(path)
    return path


def test_export_fills_placeholders(sample_lrmx, tmp_path):
    tpl_path = make_template(tmp_path / 'template.docx')
    exporter = DocxExporter(tpl_path)
    out = tmp_path / 'out.docx'
    lf = LrmxFile(sample_lrmx)
    exporter.export(lf, out)
    assert out.exists()
    doc = Document(out)
    full_text = '\n'.join(p.text for p in doc.paragraphs)
    assert '张三' in full_text
    assert '男' in full_text
    assert '110101199001011234' in full_text
    assert '{{' not in full_text


def test_export_raises_if_template_missing(sample_lrmx, tmp_path):
    import pytest
    exporter = DocxExporter(tmp_path / 'nonexistent.docx')
    with pytest.raises(Exception):
        exporter.export(LrmxFile(sample_lrmx), tmp_path / 'out.docx')
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
uv run pytest tests/test_docx_exporter.py -v
```

预期：`ImportError`

- [ ] **Step 3: 实现 app/core/docx_exporter.py**

```python
from pathlib import Path
from docxtpl import DocxTemplate
from .lrmx import LrmxFile


class DocxExporter:
    def __init__(self, template_path: Path) -> None:
        self.template_path = Path(template_path)

    def export(self, lrmx: LrmxFile, output_path: Path) -> None:
        tpl = DocxTemplate(self.template_path)
        context = lrmx.as_dict()
        tpl.render(context)
        tpl.save(output_path)
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
uv run pytest tests/test_docx_exporter.py -v
```

预期：2 passed。

- [ ] **Step 5: 提交**

```bash
git add app/core/docx_exporter.py tests/test_docx_exporter.py
git commit -m "feat: DocxExporter fills docxtpl template from LrmxFile"
```

---

## Task 5: PdfExporter（core/pdf_exporter.py）

**Files:**
- Create: `app/core/pdf_exporter.py`
- Create: `tests/test_pdf_exporter.py`

- [ ] **Step 1: 写失败测试**

新建 `tests/test_pdf_exporter.py`：

```python
from unittest.mock import patch, MagicMock
from app.core.pdf_exporter import PdfExporter, PdfEngine, detect_engine


def test_detect_engine_finds_libreoffice():
    with patch('shutil.which', side_effect=lambda x: '/usr/bin/soffice' if x == 'soffice' else None):
        assert detect_engine() == PdfEngine.LIBREOFFICE


def test_detect_engine_finds_wps():
    with patch('shutil.which', side_effect=lambda x: '/usr/bin/wps' if x == 'wps' else None):
        assert detect_engine() == PdfEngine.WPS


def test_detect_engine_none_when_nothing_installed():
    with patch('shutil.which', return_value=None):
        with patch.dict('sys.modules', {'win32com': None, 'win32com.client': None}):
            engine = detect_engine()
            assert engine in (PdfEngine.NONE, PdfEngine.WORD_COM)


def test_available_true_when_engine_found():
    with patch('app.core.pdf_exporter.detect_engine', return_value=PdfEngine.LIBREOFFICE):
        exporter = PdfExporter()
        assert exporter.available() is True


def test_available_false_when_no_engine():
    with patch('app.core.pdf_exporter.detect_engine', return_value=PdfEngine.NONE):
        exporter = PdfExporter()
        assert exporter.available() is False


def test_export_raises_when_no_engine(tmp_path):
    import pytest
    with patch('app.core.pdf_exporter.detect_engine', return_value=PdfEngine.NONE):
        exporter = PdfExporter()
        with pytest.raises(RuntimeError, match='No PDF rendering engine'):
            exporter.export(tmp_path / 'in.docx', tmp_path)
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
uv run pytest tests/test_pdf_exporter.py -v
```

预期：`ImportError`

- [ ] **Step 3: 实现 app/core/pdf_exporter.py**

```python
import shutil
import subprocess
from enum import Enum, auto
from pathlib import Path


class PdfEngine(Enum):
    LIBREOFFICE = auto()
    WPS = auto()
    WORD_COM = auto()
    NONE = auto()


def detect_engine() -> PdfEngine:
    if shutil.which('libreoffice') or shutil.which('soffice'):
        return PdfEngine.LIBREOFFICE
    if shutil.which('wps'):
        return PdfEngine.WPS
    try:
        import win32com.client  # noqa: F401
        return PdfEngine.WORD_COM
    except (ImportError, ModuleNotFoundError):
        pass
    return PdfEngine.NONE


class PdfExporter:
    def __init__(self) -> None:
        self.engine = detect_engine()

    def available(self) -> bool:
        return self.engine != PdfEngine.NONE

    def export(self, docx_path: Path, output_dir: Path) -> Path:
        docx_path = Path(docx_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        if self.engine == PdfEngine.LIBREOFFICE:
            return self._via_libreoffice(docx_path, output_dir)
        if self.engine == PdfEngine.WPS:
            return self._via_wps(docx_path, output_dir)
        if self.engine == PdfEngine.WORD_COM:
            return self._via_word_com(docx_path, output_dir)
        raise RuntimeError('No PDF rendering engine available. Install LibreOffice or WPS.')

    def _via_libreoffice(self, docx_path: Path, output_dir: Path) -> Path:
        cmd = shutil.which('libreoffice') or shutil.which('soffice')
        subprocess.run(
            [cmd, '--headless', '--convert-to', 'pdf', '--outdir', str(output_dir), str(docx_path)],
            check=True, capture_output=True,
        )
        return output_dir / (docx_path.stem + '.pdf')

    def _via_wps(self, docx_path: Path, output_dir: Path) -> Path:
        subprocess.run(
            ['wps', '--headless', '--convert-to', 'pdf', '--outdir', str(output_dir), str(docx_path)],
            check=True, capture_output=True,
        )
        return output_dir / (docx_path.stem + '.pdf')

    def _via_word_com(self, docx_path: Path, output_dir: Path) -> Path:
        import win32com.client
        word = win32com.client.Dispatch('Word.Application')
        word.Visible = False
        try:
            doc = word.Documents.Open(str(docx_path.resolve()))
            pdf_path = output_dir / (docx_path.stem + '.pdf')
            doc.SaveAs(str(pdf_path.resolve()), FileFormat=17)
            doc.Close()
        finally:
            word.Quit()
        return pdf_path
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
uv run pytest tests/test_pdf_exporter.py -v
```

预期：6 passed。

- [ ] **Step 5: 提交**

```bash
git add app/core/pdf_exporter.py tests/test_pdf_exporter.py
git commit -m "feat: PdfExporter with LibreOffice/WPS/Word engine detection"
```

---

## Task 6: ExcelHandler（core/excel_handler.py）

**Files:**
- Create: `app/core/excel_handler.py`
- Create: `tests/test_excel_handler.py`

- [ ] **Step 1: 写失败测试**

新建 `tests/test_excel_handler.py`：

```python
from pathlib import Path
import openpyxl
import pytest
from app.core.lrmx import LrmxFile
from app.core.excel_handler import ExcelHandler, MatchMode


def make_excel(path: Path, rows: list[dict]) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    headers = list(rows[0].keys())
    ws.append(headers)
    for row in rows:
        ws.append([row[h] for h in headers])
    wb.save(path)
    return path


def test_update_by_id_card(sample_lrmx, tmp_path):
    excel = make_excel(tmp_path / 'data.xlsx', [
        {'ShenFenZheng': '110101199001011234', 'XianRenZhiWu': '副科长'},
    ])
    lrmx_dir = sample_lrmx.parent
    handler = ExcelHandler(excel, lrmx_dir, MatchMode.ID_CARD)
    logs = handler.update(['XianRenZhiWu'])
    assert any('张三' in log for log in logs)
    updated = LrmxFile(sample_lrmx)
    assert updated.get('XianRenZhiWu') == '副科长'


def test_backup_created_before_update(sample_lrmx, tmp_path):
    excel = make_excel(tmp_path / 'data.xlsx', [
        {'ShenFenZheng': '110101199001011234', 'XianRenZhiWu': '副科长'},
    ])
    handler = ExcelHandler(excel, sample_lrmx.parent, MatchMode.ID_CARD)
    handler.update(['XianRenZhiWu'])
    assert sample_lrmx.with_suffix('.lrmx.bak').exists()


def test_unmatched_row_logged(sample_lrmx, tmp_path):
    excel = make_excel(tmp_path / 'data.xlsx', [
        {'ShenFenZheng': '000000000000000000', 'XianRenZhiWu': '局长'},
    ])
    handler = ExcelHandler(excel, sample_lrmx.parent, MatchMode.ID_CARD)
    logs = handler.update(['XianRenZhiWu'])
    assert any('未匹配' in log for log in logs)


def test_update_by_name(sample_lrmx, tmp_path):
    excel = make_excel(tmp_path / 'data.xlsx', [
        {'XingMing': '张三', 'JianKangZhuangKuang': '良好'},
    ])
    handler = ExcelHandler(excel, sample_lrmx.parent, MatchMode.NAME)
    handler.update(['JianKangZhuangKuang'])
    updated = LrmxFile(sample_lrmx)
    assert updated.get('JianKangZhuangKuang') == '良好'


def test_progress_callback_called(sample_lrmx, tmp_path):
    excel = make_excel(tmp_path / 'data.xlsx', [
        {'ShenFenZheng': '110101199001011234', 'XianRenZhiWu': '科长'},
    ])
    handler = ExcelHandler(excel, sample_lrmx.parent, MatchMode.ID_CARD)
    calls = []
    handler.update(['XianRenZhiWu'], progress_cb=calls.append)
    assert len(calls) >= 1
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
uv run pytest tests/test_excel_handler.py -v
```

预期：`ImportError`

- [ ] **Step 3: 实现 app/core/excel_handler.py**

```python
from pathlib import Path
from typing import Callable, Optional
import openpyxl
from .lrmx import LrmxFile


class MatchMode:
    ID_CARD = 'ShenFenZheng'
    NAME = 'XingMing'
    NAME_AND_ID = 'both'


class ExcelHandler:
    def __init__(self, excel_path: Path, lrmx_dir: Path, match_mode: str) -> None:
        self.excel_path = Path(excel_path)
        self.lrmx_dir = Path(lrmx_dir)
        self.match_mode = match_mode

    def _make_key(self, lf: LrmxFile) -> str:
        if self.match_mode == MatchMode.ID_CARD:
            return lf.get('ShenFenZheng').strip()
        if self.match_mode == MatchMode.NAME:
            return lf.get('XingMing').strip()
        return lf.get('XingMing').strip() + lf.get('ShenFenZheng').strip()

    def _row_key(self, row: dict) -> str:
        if self.match_mode == MatchMode.ID_CARD:
            return str(row.get('ShenFenZheng') or '').strip()
        if self.match_mode == MatchMode.NAME:
            return str(row.get('XingMing') or '').strip()
        return str(row.get('XingMing') or '').strip() + str(row.get('ShenFenZheng') or '').strip()

    def _load_index(self) -> dict[str, LrmxFile]:
        index: dict[str, LrmxFile] = {}
        for f in self.lrmx_dir.glob('*.lrmx'):
            try:
                lf = LrmxFile(f)
                key = self._make_key(lf)
                if key:
                    index[key] = lf
            except Exception:
                pass
        return index

    def update(
        self,
        fields_to_update: list[str],
        progress_cb: Optional[Callable[[str], None]] = None,
    ) -> list[str]:
        wb = openpyxl.load_workbook(self.excel_path)
        ws = wb.active
        headers = [cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))]
        index = self._load_index()
        logs: list[str] = []

        for row_values in ws.iter_rows(min_row=2, values_only=True):
            row = dict(zip(headers, row_values))
            key = self._row_key(row)
            if not key or key not in index:
                msg = f'⚠ 未匹配: {key or "(空)"}'
                logs.append(msg)
                if progress_cb:
                    progress_cb(msg)
                continue

            lf = index[key]
            backup = lf.path.with_suffix('.lrmx.bak')
            lf.path.rename(backup)
            for field in fields_to_update:
                val = row.get(field)
                if val is not None:
                    lf.set(field, str(val))
            lf.save(lf.path)
            msg = f'✓ 已更新: {lf.get("XingMing")}'
            logs.append(msg)
            if progress_cb:
                progress_cb(msg)

        return logs
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
uv run pytest tests/test_excel_handler.py -v
```

预期：5 passed。

- [ ] **Step 5: 运行全部测试，确认无回归**

```bash
uv run pytest tests/ -v
```

预期：所有测试通过。

- [ ] **Step 6: 提交**

```bash
git add app/core/excel_handler.py tests/test_excel_handler.py
git commit -m "feat: ExcelHandler matches lrmx by ID/name and updates fields"
```

---

## Task 7: QSS 样式表（ui/style.py）

**Files:**
- Create: `app/ui/style.py`

此任务无自动化测试（样式需目视验证），直接实现。

- [ ] **Step 1: 创建 app/ui/style.py**

```python
ACCENT = '#D85A30'
ACCENT_LIGHT = 'rgba(216, 90, 48, 0.10)'
ACCENT_HOVER = '#C04E28'

QSS = f"""
QMainWindow, QDialog {{
    background-color: #FFFFFF;
}}

QWidget {{
    background-color: #FFFFFF;
    color: #1A1A1A;
    font-family: "Microsoft YaHei UI", "PingFang SC", "Noto Sans CJK SC", sans-serif;
    font-size: 13px;
}}

/* 左侧导航栏 */
QListWidget#sidebar {{
    background-color: #F5F4F1;
    border: none;
    border-right: 0.5px solid #E0DDD6;
    outline: none;
    padding: 8px 0;
}}
QListWidget#sidebar::item {{
    padding: 8px 16px;
    color: #555550;
    border-radius: 0;
}}
QListWidget#sidebar::item:selected {{
    background-color: {ACCENT_LIGHT};
    color: {ACCENT};
}}
QListWidget#sidebar::item:hover:!selected {{
    background-color: #EEEDE8;
    color: #1A1A1A;
}}

/* 输入框 */
QLineEdit, QPlainTextEdit {{
    border: 0.5px solid #D0CEC8;
    border-radius: 6px;
    padding: 4px 8px;
    background-color: #FFFFFF;
    color: #1A1A1A;
    selection-background-color: {ACCENT_LIGHT};
}}
QLineEdit:focus, QPlainTextEdit:focus {{
    border-color: {ACCENT};
}}
QLineEdit:read-only {{
    background-color: #F5F4F1;
    color: #888880;
}}

/* 按钮 */
QPushButton {{
    border: 0.5px solid #C8C6C0;
    border-radius: 6px;
    padding: 5px 14px;
    background-color: #F5F4F1;
    color: #333330;
}}
QPushButton:hover {{
    background-color: #EEEDEA;
    border-color: #B0AEA8;
}}
QPushButton:pressed {{
    background-color: #E5E4E0;
}}
QPushButton#primary {{
    background-color: {ACCENT};
    color: #FFFFFF;
    border: none;
    font-weight: 500;
}}
QPushButton#primary:hover {{
    background-color: {ACCENT_HOVER};
}}
QPushButton#primary:pressed {{
    background-color: #A84020;
}}
QPushButton#primary:disabled {{
    background-color: #D0A898;
    color: rgba(255,255,255,0.6);
}}

/* 下拉框 */
QComboBox {{
    border: 0.5px solid #D0CEC8;
    border-radius: 6px;
    padding: 4px 8px;
    background-color: #FFFFFF;
}}
QComboBox:focus {{
    border-color: {ACCENT};
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}

/* 复选框 */
QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    border: 1.5px solid #C0BEB8;
    border-radius: 3px;
}}
QCheckBox::indicator:checked {{
    background-color: {ACCENT};
    border-color: {ACCENT};
    image: none;
}}

/* 单选框 */
QRadioButton::indicator {{
    width: 14px;
    height: 14px;
    border: 1.5px solid #C0BEB8;
    border-radius: 7px;
}}
QRadioButton::indicator:checked {{
    background-color: {ACCENT};
    border-color: {ACCENT};
}}

/* 列表视图（文件列表） */
QListWidget#fileList {{
    border: 0.5px solid #D0CEC8;
    border-radius: 6px;
    background-color: #FAFAF8;
    outline: none;
}}
QListWidget#fileList::item {{
    padding: 5px 8px;
    border-radius: 4px;
    color: #333330;
}}
QListWidget#fileList::item:selected {{
    background-color: {ACCENT_LIGHT};
    color: {ACCENT};
}}

/* 日志区域 */
QPlainTextEdit#logView {{
    background-color: #F5F4F1;
    border: 0.5px solid #D0CEC8;
    border-radius: 6px;
    font-family: "Cascadia Code", "Consolas", "Courier New", monospace;
    font-size: 12px;
    color: #444440;
    padding: 6px;
}}

/* 分割线 */
QFrame[frameShape="4"],
QFrame[frameShape="5"] {{
    color: #E0DDD6;
}}

/* 标签 */
QLabel {{
    background: transparent;
    color: #555550;
}}
QLabel#sectionTitle {{
    font-size: 14px;
    font-weight: 500;
    color: #1A1A1A;
}}

/* 滚动条 */
QScrollBar:vertical {{
    border: none;
    background: transparent;
    width: 6px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: #C0BEB8;
    border-radius: 3px;
    min-height: 20px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
"""
```

- [ ] **Step 2: 提交**

```bash
git add app/ui/style.py
git commit -m "feat: QSS light theme inspired by Claude Code Desktop"
```

---

## Task 8: MainWindow + SettingsTab

**Files:**
- Create: `app/ui/main_window.py`
- Create: `app/ui/tabs/settings_tab.py`
- Modify: `main.py`

- [ ] **Step 1: 实现 app/ui/tabs/settings_tab.py**

```python
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QListWidget, QListWidgetItem,
    QInputDialog, QFileDialog, QMessageBox,
)
from PySide6.QtCore import QSettings
from app.utils.naming import PRESETS


class SettingsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._settings = QSettings('rmb_helper', 'rmb_helper')
        self._build_ui()
        self._load()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # 模板路径
        tpl_label = QLabel('docx 模板路径')
        tpl_label.setObjectName('sectionTitle')
        layout.addWidget(tpl_label)

        tpl_row = QHBoxLayout()
        self._tpl_edit = QLineEdit()
        self._tpl_edit.setPlaceholderText('请选择 .docx 模板文件…')
        self._tpl_edit.setReadOnly(True)
        tpl_btn = QPushButton('浏览')
        tpl_btn.clicked.connect(self._browse_template)
        tpl_row.addWidget(self._tpl_edit)
        tpl_row.addWidget(tpl_btn)
        layout.addLayout(tpl_row)

        # 命名规则预设
        rule_label = QLabel('命名规则预设')
        rule_label.setObjectName('sectionTitle')
        layout.addWidget(rule_label)

        self._rule_list = QListWidget()
        self._rule_list.setObjectName('fileList')
        self._rule_list.setMaximumHeight(160)
        layout.addWidget(self._rule_list)

        rule_btns = QHBoxLayout()
        add_btn = QPushButton('新增')
        add_btn.clicked.connect(self._add_rule)
        edit_btn = QPushButton('编辑')
        edit_btn.clicked.connect(self._edit_rule)
        del_btn = QPushButton('删除')
        del_btn.clicked.connect(self._delete_rule)
        rule_btns.addWidget(add_btn)
        rule_btns.addWidget(edit_btn)
        rule_btns.addWidget(del_btn)
        rule_btns.addStretch()
        layout.addLayout(rule_btns)

        save_btn = QPushButton('保存设置')
        save_btn.setObjectName('primary')
        save_btn.clicked.connect(self._save)
        layout.addWidget(save_btn)
        layout.addStretch()

    def _browse_template(self):
        path, _ = QFileDialog.getOpenFileName(
            self, '选择模板文件', '', 'Word 文档 (*.docx)'
        )
        if path:
            self._tpl_edit.setText(path)

    def _add_rule(self):
        text, ok = QInputDialog.getText(
            self, '新增命名规则',
            '输入规则模板（可用字段：{XingMing} {ShenFenZheng} {XianRenZhiWu} 等）：'
        )
        if ok and text.strip():
            self._rule_list.addItem(text.strip())

    def _edit_rule(self):
        item = self._rule_list.currentItem()
        if not item:
            return
        text, ok = QInputDialog.getText(self, '编辑命名规则', '规则模板：', text=item.text())
        if ok and text.strip():
            item.setText(text.strip())

    def _delete_rule(self):
        row = self._rule_list.currentRow()
        if row >= 0:
            self._rule_list.takeItem(row)

    def _load(self):
        self._tpl_edit.setText(self._settings.value('template_path', ''))
        rules = self._settings.value('naming_rules', [p[0] for p in PRESETS])
        if isinstance(rules, str):
            rules = [rules]
        self._rule_list.clear()
        for r in rules:
            self._rule_list.addItem(r)

    def _save(self):
        self._settings.setValue('template_path', self._tpl_edit.text())
        rules = [self._rule_list.item(i).text() for i in range(self._rule_list.count())]
        self._settings.setValue('naming_rules', rules)
        QMessageBox.information(self, '保存成功', '设置已保存。')

    def template_path(self) -> str:
        return self._tpl_edit.text()

    def naming_rules(self) -> list[str]:
        return [self._rule_list.item(i).text() for i in range(self._rule_list.count())]
```

- [ ] **Step 2: 实现 app/ui/main_window.py**

```python
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout,
    QListWidget, QListWidgetItem, QStackedWidget,
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon

from app.ui.style import QSS
from app.ui.tabs.settings_tab import SettingsTab


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('干部任免审批表管理工具')
        self.setMinimumSize(860, 580)
        self.setStyleSheet(QSS)
        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 左侧导航
        self._sidebar = QListWidget()
        self._sidebar.setObjectName('sidebar')
        self._sidebar.setFixedWidth(160)
        self._sidebar.setSpacing(2)

        nav_items = [
            ('转换导出', ''),
            ('批量更新', ''),
            ('设置', ''),
        ]
        for label, icon_path in nav_items:
            item = QListWidgetItem(label)
            item.setSizeHint(QSize(160, 36))
            self._sidebar.addItem(item)
        self._sidebar.setCurrentRow(0)
        self._sidebar.currentRowChanged.connect(self._switch_tab)

        # 右侧内容区（延迟导入避免循环）
        from app.ui.tabs.convert_tab import ConvertTab
        from app.ui.tabs.update_tab import UpdateTab

        self._stack = QStackedWidget()
        self._convert_tab = ConvertTab()
        self._update_tab = UpdateTab()
        self._settings_tab = SettingsTab()

        self._stack.addWidget(self._convert_tab)
        self._stack.addWidget(self._update_tab)
        self._stack.addWidget(self._settings_tab)

        root.addWidget(self._sidebar)
        root.addWidget(self._stack)

    def _switch_tab(self, index: int):
        self._stack.setCurrentIndex(index)
```

- [ ] **Step 3: 更新 main.py**

```python
import sys
from PySide6.QtWidgets import QApplication
from app.ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName('rmb_helper')
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
```

- [ ] **Step 4: 目视验证窗口可启动**

```bash
uv run python main.py
```

预期：弹出窗口，左侧三个导航项，右侧目前显示空白（ConvertTab/UpdateTab 尚未实现会报错）。

> 注意：此时 ConvertTab 和 UpdateTab 还未创建，MainWindow 导入会失败。先创建两个空占位文件继续：

```bash
# 临时占位，Task 9/10 会替换
cat > app/ui/tabs/convert_tab.py << 'EOF'
from PySide6.QtWidgets import QWidget
class ConvertTab(QWidget):
    pass
EOF
cat > app/ui/tabs/update_tab.py << 'EOF'
from PySide6.QtWidgets import QWidget
class UpdateTab(QWidget):
    pass
EOF
```

再运行 `uv run python main.py`，确认窗口正常弹出，样式正确。

- [ ] **Step 5: 提交**

```bash
git add app/ui/ main.py
git commit -m "feat: MainWindow with sidebar navigation and SettingsTab"
```

---

## Task 9: ConvertTab（转换导出）

**Files:**
- Modify: `app/ui/tabs/convert_tab.py`（替换占位）

- [ ] **Step 1: 实现 app/ui/tabs/convert_tab.py**

```python
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListWidget, QListWidgetItem,
    QCheckBox, QLineEdit, QComboBox, QPlainTextEdit,
    QFileDialog, QFrame,
)
from PySide6.QtCore import Qt, QSettings, QThread, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent

from app.core.lrmx import LrmxFile
from app.core.docx_exporter import DocxExporter
from app.core.pdf_exporter import PdfExporter
from app.utils.naming import apply_rule, PRESETS


class _Worker(QThread):
    log = Signal(str)
    finished = Signal()

    def __init__(self, files, output_dir, naming_rule, do_docx, do_pdf, template_path):
        super().__init__()
        self.files = files
        self.output_dir = Path(output_dir)
        self.naming_rule = naming_rule
        self.do_docx = do_docx
        self.do_pdf = do_pdf
        self.template_path = template_path

    def run(self):
        pdf_exporter = PdfExporter()
        if self.do_pdf and not pdf_exporter.available():
            self.log.emit('⚠ 未检测到 PDF 渲染引擎（LibreOffice / WPS），将跳过 PDF 输出')

        for lrmx_path in self.files:
            try:
                lf = LrmxFile(Path(lrmx_path))
                stem = apply_rule(self.naming_rule, lf.as_dict()) or Path(lrmx_path).stem

                if self.do_docx:
                    if not self.template_path:
                        self.log.emit('✗ 未配置模板路径，请在「设置」中指定 .docx 模板')
                        continue
                    out_docx = self.output_dir / (stem + '.docx')
                    DocxExporter(self.template_path).export(lf, out_docx)
                    self.log.emit(f'✓ {stem} → docx')

                if self.do_pdf and pdf_exporter.available():
                    if not self.template_path:
                        self.log.emit('✗ 未配置模板路径，跳过 PDF')
                        continue
                    tmp_docx = self.output_dir / (stem + '_tmp.docx')
                    DocxExporter(self.template_path).export(lf, tmp_docx)
                    pdf_exporter.export(tmp_docx, self.output_dir)
                    tmp_docx.unlink(missing_ok=True)
                    self.log.emit(f'✓ {stem} → pdf')

            except Exception as e:
                self.log.emit(f'✗ {Path(lrmx_path).name}: {e}')

        self.finished.emit()


class ConvertTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._settings = QSettings('rmb_helper', 'rmb_helper')
        self._worker = None
        self._build_ui()
        self.setAcceptDrops(True)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        title = QLabel('转换导出')
        title.setObjectName('sectionTitle')
        layout.addWidget(title)

        sub = QLabel('将 .lrmx 文件批量转换为 docx / pdf')
        sub.setStyleSheet('color: #888880; font-size: 12px;')
        layout.addWidget(sub)

        # 文件列表
        self._file_list = QListWidget()
        self._file_list.setObjectName('fileList')
        self._file_list.setMinimumHeight(100)
        self._file_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        layout.addWidget(self._file_list)

        file_btns = QHBoxLayout()
        add_btn = QPushButton('选择文件…')
        add_btn.clicked.connect(self._pick_files)
        clear_btn = QPushButton('清空')
        clear_btn.clicked.connect(self._file_list.clear)
        del_btn = QPushButton('删除选中')
        del_btn.clicked.connect(self._delete_selected)
        file_btns.addWidget(add_btn)
        file_btns.addWidget(del_btn)
        file_btns.addWidget(clear_btn)
        file_btns.addStretch()
        layout.addLayout(file_btns)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep)

        # 输出格式
        fmt_row = QHBoxLayout()
        fmt_label = QLabel('输出格式')
        fmt_label.setFixedWidth(64)
        self._chk_docx = QCheckBox('docx')
        self._chk_docx.setChecked(True)
        self._chk_pdf = QCheckBox('pdf')
        self._chk_pdf.setChecked(True)
        fmt_row.addWidget(fmt_label)
        fmt_row.addWidget(self._chk_docx)
        fmt_row.addSpacing(16)
        fmt_row.addWidget(self._chk_pdf)
        fmt_row.addStretch()
        layout.addLayout(fmt_row)

        # 输出目录
        dir_row = QHBoxLayout()
        dir_label = QLabel('输出目录')
        dir_label.setFixedWidth(64)
        self._dir_edit = QLineEdit()
        self._dir_edit.setPlaceholderText('选择输出目录…')
        self._dir_edit.setReadOnly(True)
        dir_btn = QPushButton('浏览')
        dir_btn.clicked.connect(self._pick_dir)
        dir_row.addWidget(dir_label)
        dir_row.addWidget(self._dir_edit)
        dir_row.addWidget(dir_btn)
        layout.addLayout(dir_row)

        # 命名规则
        rule_row = QHBoxLayout()
        rule_label = QLabel('命名规则')
        rule_label.setFixedWidth(64)
        self._rule_combo = QComboBox()
        self._refresh_rules()
        self._custom_edit = QLineEdit()
        self._custom_edit.setPlaceholderText('自定义：{XingMing}_{ShenFenZheng}')
        self._custom_edit.setVisible(False)
        custom_btn = QPushButton('自定义')
        custom_btn.setCheckable(True)
        custom_btn.toggled.connect(self._toggle_custom)
        rule_row.addWidget(rule_label)
        rule_row.addWidget(self._rule_combo)
        rule_row.addWidget(self._custom_edit)
        rule_row.addWidget(custom_btn)
        layout.addLayout(rule_row)

        # 执行按钮
        run_row = QHBoxLayout()
        run_row.addStretch()
        self._run_btn = QPushButton('开始转换')
        self._run_btn.setObjectName('primary')
        self._run_btn.setFixedWidth(100)
        self._run_btn.clicked.connect(self._run)
        run_row.addWidget(self._run_btn)
        layout.addLayout(run_row)

        # 日志
        self._log = QPlainTextEdit()
        self._log.setObjectName('logView')
        self._log.setReadOnly(True)
        self._log.setMinimumHeight(100)
        layout.addWidget(self._log)

    def _refresh_rules(self):
        rules = self._settings.value('naming_rules', [p[0] for p in PRESETS])
        if isinstance(rules, str):
            rules = [rules]
        self._rule_combo.clear()
        for r in rules:
            self._rule_combo.addItem(r)

    def _toggle_custom(self, checked):
        self._rule_combo.setVisible(not checked)
        self._custom_edit.setVisible(checked)

    def _pick_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, '选择 lrmx 文件', '', '任免审批表 (*.lrmx)'
        )
        for p in paths:
            if not self._file_list.findItems(p, Qt.MatchFlag.MatchExactly):
                self._file_list.addItem(p)

    def _delete_selected(self):
        for item in self._file_list.selectedItems():
            self._file_list.takeItem(self._file_list.row(item))

    def _pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, '选择输出目录')
        if d:
            self._dir_edit.setText(d)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.endswith('.lrmx') and not self._file_list.findItems(path, Qt.MatchFlag.MatchExactly):
                self._file_list.addItem(path)

    def _run(self):
        files = [self._file_list.item(i).text() for i in range(self._file_list.count())]
        if not files:
            self._log.appendPlainText('⚠ 请先添加 .lrmx 文件')
            return
        output_dir = self._dir_edit.text()
        if not output_dir:
            self._log.appendPlainText('⚠ 请选择输出目录')
            return

        naming_rule = (
            self._custom_edit.text().strip()
            if self._custom_edit.isVisible()
            else self._rule_combo.currentText()
        ) or PRESETS[0][0]

        template_path = self._settings.value('template_path', '')
        self._run_btn.setEnabled(False)
        self._log.clear()

        self._worker = _Worker(
            files=files,
            output_dir=output_dir,
            naming_rule=naming_rule,
            do_docx=self._chk_docx.isChecked(),
            do_pdf=self._chk_pdf.isChecked(),
            template_path=template_path,
        )
        self._worker.log.connect(self._log.appendPlainText)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _on_finished(self):
        self._run_btn.setEnabled(True)
        self._log.appendPlainText('── 完成 ──')
```

- [ ] **Step 2: 目视验证 ConvertTab**

```bash
uv run python main.py
```

验证：
- 点击「选择文件」可以选 .lrmx 文件
- 拖放 .lrmx 文件到窗口有效
- 勾选 docx/pdf 有效
- 「开始转换」点击后按钮变灰、日志区输出内容
- 无报错

- [ ] **Step 3: 提交**

```bash
git add app/ui/tabs/convert_tab.py
git commit -m "feat: ConvertTab with drag-drop, QThread worker, realtime log"
```

---

## Task 10: UpdateTab（批量更新）

**Files:**
- Modify: `app/ui/tabs/update_tab.py`（替换占位）

- [ ] **Step 1: 实现 app/ui/tabs/update_tab.py**

```python
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QRadioButton, QButtonGroup,
    QListWidget, QPlainTextEdit, QFileDialog, QFrame,
)
from PySide6.QtCore import QThread, Signal
import openpyxl

from app.core.excel_handler import ExcelHandler, MatchMode

FIELD_LABELS: dict[str, str] = {
    'XingMing': '姓名', 'XingBie': '性别', 'ChuShengNianYue': '出生年月',
    'MinZu': '民族', 'JiGuan': '籍贯', 'RuDangShiJian': '入党时间',
    'CanJiaGongZuoShiJian': '参加工作时间', 'JianKangZhuangKuang': '健康状况',
    'ZhengZhiMianMao': '政治面貌', 'ShenFenZheng': '身份证号',
    'QuanRiZhiJiaoYu_XueLi': '全日制学历', 'QuanRiZhiJiaoYu_XueWei': '全日制学位',
    'ZaiZhiJiaoYu_XueLi': '在职学历', 'ZaiZhiJiaoYu_XueWei': '在职学位',
    'ZhuanYeJiShuZhiWu': '专业技术职务', 'XianRenZhiWu': '现任职务',
    'NiRenZhiWu': '拟任职务', 'NiMianZhiWu': '拟免职务',
    'RenMianLiYou': '任免理由', 'TianBiaoRen': '填表人',
}


class _Worker(QThread):
    log = Signal(str)
    finished = Signal()

    def __init__(self, excel_path, lrmx_dir, match_mode, fields):
        super().__init__()
        self.excel_path = excel_path
        self.lrmx_dir = lrmx_dir
        self.match_mode = match_mode
        self.fields = fields

    def run(self):
        try:
            handler = ExcelHandler(self.excel_path, self.lrmx_dir, self.match_mode)
            handler.update(self.fields, progress_cb=self.log.emit)
        except Exception as e:
            self.log.emit(f'✗ 错误: {e}')
        self.finished.emit()


class UpdateTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        title = QLabel('批量更新')
        title.setObjectName('sectionTitle')
        layout.addWidget(title)

        sub = QLabel('从 Excel 汇总表读取数据，批量更新对应 .lrmx 文件的字段')
        sub.setStyleSheet('color: #888880; font-size: 12px;')
        layout.addWidget(sub)

        # lrmx 目录
        dir_row = QHBoxLayout()
        dir_label = QLabel('lrmx 目录')
        dir_label.setFixedWidth(72)
        self._dir_edit = QLineEdit()
        self._dir_edit.setReadOnly(True)
        self._dir_edit.setPlaceholderText('包含 .lrmx 文件的目录…')
        dir_btn = QPushButton('浏览')
        dir_btn.clicked.connect(self._pick_dir)
        dir_row.addWidget(dir_label)
        dir_row.addWidget(self._dir_edit)
        dir_row.addWidget(dir_btn)
        layout.addLayout(dir_row)

        # Excel 文件
        xl_row = QHBoxLayout()
        xl_label = QLabel('Excel 文件')
        xl_label.setFixedWidth(72)
        self._xl_edit = QLineEdit()
        self._xl_edit.setReadOnly(True)
        self._xl_edit.setPlaceholderText('选择 .xlsx 文件…')
        xl_btn = QPushButton('浏览')
        xl_btn.clicked.connect(self._pick_excel)
        xl_row.addWidget(xl_label)
        xl_row.addWidget(self._xl_edit)
        xl_row.addWidget(xl_btn)
        layout.addLayout(xl_row)

        # 匹配依据
        match_row = QHBoxLayout()
        match_label = QLabel('匹配依据')
        match_label.setFixedWidth(72)
        self._match_group = QButtonGroup(self)
        self._rb_id = QRadioButton('身份证号（推荐）')
        self._rb_id.setChecked(True)
        self._rb_name = QRadioButton('姓名')
        self._rb_both = QRadioButton('姓名+身份证号')
        self._match_group.addButton(self._rb_id)
        self._match_group.addButton(self._rb_name)
        self._match_group.addButton(self._rb_both)
        match_row.addWidget(match_label)
        match_row.addWidget(self._rb_id)
        match_row.addSpacing(12)
        match_row.addWidget(self._rb_name)
        match_row.addSpacing(12)
        match_row.addWidget(self._rb_both)
        match_row.addStretch()
        layout.addLayout(match_row)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep)

        # 更新字段多选
        field_label = QLabel('选择要更新的字段')
        field_label.setObjectName('sectionTitle')
        layout.addWidget(field_label)

        self._field_list = QListWidget()
        self._field_list.setObjectName('fileList')
        self._field_list.setMaximumHeight(150)
        from PySide6.QtCore import Qt
        for key, label in FIELD_LABELS.items():
            from PySide6.QtWidgets import QListWidgetItem
            item = QListWidgetItem(f'{label}（{key}）')
            item.setData(Qt.ItemDataRole.UserRole, key)
            item.setCheckState(Qt.CheckState.Unchecked)
            self._field_list.addItem(item)
        layout.addWidget(self._field_list)

        # 执行
        run_row = QHBoxLayout()
        run_row.addStretch()
        self._run_btn = QPushButton('开始更新')
        self._run_btn.setObjectName('primary')
        self._run_btn.setFixedWidth(100)
        self._run_btn.clicked.connect(self._run)
        run_row.addWidget(self._run_btn)
        layout.addLayout(run_row)

        # 日志
        self._log = QPlainTextEdit()
        self._log.setObjectName('logView')
        self._log.setReadOnly(True)
        self._log.setMinimumHeight(100)
        layout.addWidget(self._log)

    def _pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, '选择 lrmx 文件目录')
        if d:
            self._dir_edit.setText(d)

    def _pick_excel(self):
        path, _ = QFileDialog.getOpenFileName(
            self, '选择 Excel 文件', '', 'Excel 文件 (*.xlsx *.xls)'
        )
        if path:
            self._xl_edit.setText(path)

    def _run(self):
        from PySide6.QtCore import Qt
        lrmx_dir = self._dir_edit.text()
        excel_path = self._xl_edit.text()
        if not lrmx_dir or not excel_path:
            self._log.appendPlainText('⚠ 请选择 lrmx 目录和 Excel 文件')
            return

        fields = []
        for i in range(self._field_list.count()):
            item = self._field_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                fields.append(item.data(Qt.ItemDataRole.UserRole))
        if not fields:
            self._log.appendPlainText('⚠ 请至少勾选一个要更新的字段')
            return

        if self._rb_id.isChecked():
            match_mode = MatchMode.ID_CARD
        elif self._rb_name.isChecked():
            match_mode = MatchMode.NAME
        else:
            match_mode = MatchMode.NAME_AND_ID

        self._run_btn.setEnabled(False)
        self._log.clear()
        self._worker = _Worker(excel_path, lrmx_dir, match_mode, fields)
        self._worker.log.connect(self._log.appendPlainText)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _on_finished(self):
        self._run_btn.setEnabled(True)
        self._log.appendPlainText('── 完成 ──')
```

- [ ] **Step 2: 目视验证 UpdateTab**

```bash
uv run python main.py
```

切换到「批量更新」Tab，验证：
- 目录/文件选择按钮有效
- 匹配依据单选有效
- 字段列表可勾选
- 点击「开始更新」后按钮变灰，日志区有输出

- [ ] **Step 3: 运行全部测试**

```bash
uv run pytest tests/ -v
```

预期：所有测试通过。

- [ ] **Step 4: 提交**

```bash
git add app/ui/tabs/update_tab.py
git commit -m "feat: UpdateTab with field multi-select and QThread worker"
```

---

## Task 11: .gitignore 与收尾

**Files:**
- Create: `.gitignore`

- [ ] **Step 1: 创建 .gitignore**

```
__pycache__/
*.pyc
*.pyo
.venv/
.uv/
*.egg-info/
dist/
build/
.superpowers/
*.bak
```

- [ ] **Step 2: 提交**

```bash
git add .gitignore
git commit -m "chore: add .gitignore"
```

- [ ] **Step 3: 完整端到端手动验证**

1. 在「设置」Tab 中配置模板路径（选择已添加 `{{XingMing}}` 等占位符的 `.docx` 模板）
2. 在「转换导出」Tab 中：
   - 拖入 `安胜华620102198505026231.lrmx`
   - 选择输出目录
   - 勾选 docx，点击「开始转换」
   - 确认输出目录中有 `.docx` 文件，内容正确
3. 在「批量更新」Tab 中：
   - 选择 lrmx 目录和一个测试 Excel
   - 勾选「身份证号」匹配 + 目标字段
   - 点击「开始更新」，查看日志，确认 `.bak` 备份文件已生成

---

## 自检结果

- 设计文档全部功能点（lrmx→docx, lrmx→pdf, Excel批量更新）均有对应 Task ✓
- 无 TBD / TODO / 占位内容 ✓
- 类型/方法名跨 Task 一致：`LrmxFile.get/set/save/as_dict`，`ExcelHandler.update`，`DocxExporter.export`，`PdfExporter.export/available` ✓
- 每个 Task 均含完整代码 ✓
