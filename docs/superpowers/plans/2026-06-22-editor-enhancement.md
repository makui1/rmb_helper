# 编辑器增强 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 对任免表编辑器进行综合升级：多标签页文档模型、双布局切换、拖放打开、PDF 导出/打印预览、工具栏完善、选中颜色修复、自动折叠导航栏。

**Architecture:** 将 `EditorTab` 拆成 `_DocPane`（单文档 widget，含表单 + 状态）和 `EditorTab`（多 tab 容器），用 `QTabWidget` 承载多个 `_DocPane`。PDF 导出/打印复用现有 `DocxExporter.export_bytes()` + `PdfExporter`，打印预览使用新建的 `PrintPreviewDialog`（`QtPdf.QPdfView`）。

**Tech Stack:** PySide6 6.x（QTabWidget, QtPdf.QPdfView, QPrinter, QPrintDialog）, Python tempfile, 现有 docx_exporter / pdf_exporter。

---

## 文件结构

| 文件 | 变更 |
|---|---|
| `app/ui/style.py` | 修改 selection 颜色，增加 `editorFormA` QSS |
| `app/core/lrmx.py` | 增加 `LrmxFile.create_new()` classmethod |
| `app/core/docx_exporter.py` | 增加 `DocxExporter.export_bytes()` |
| `app/ui/widgets/print_preview.py` | 新建 `PrintPreviewDialog` |
| `app/ui/tabs/editor_tab.py` | 大幅重构：提取 `_DocPane`，加 `QTabWidget`、拖放、工具栏、双布局 |
| `app/ui/tabs/settings_tab.py` | 增加「编辑器布局」单选 |
| `app/ui/main_window.py` | `_switch_tab` 增加自动折叠逻辑 |

---

## Task 1：QSS 选中颜色修复

**Files:**
- Modify: `app/ui/style.py:110`

**背景：** 当前 `selection-background-color` 为 `rgba(216,90,48,0.10)`（极淡橙色），选中文字几乎不可见。改为蓝色高对比度方案。

- [ ] **Step 1: 修改 style.py**

在 `app/ui/style.py` 中，将第 110 行：
```python
    selection-background-color: {ACCENT_LIGHT};
```
替换为：
```python
    selection-background-color: #3B82F6;
    selection-color: #ffffff;
```

同时在文件末尾 `"""` 之前追加（QComboBox 下拉列表选中项）：
```css
QComboBox QAbstractItemView::item:selected {{
    background: #3B82F6;
    color: #ffffff;
}}
```

- [ ] **Step 2: 手动验证**

`uv run python main.py` → 打开编辑器 → 在姓名框中输入文字并用鼠标选中 → 确认选中文字白底蓝色清晰可见，不再被橙色遮挡。

- [ ] **Step 3: Commit**

```bash
git add app/ui/style.py
git commit -m "fix: 编辑器文本选中颜色改为蓝色高对比度方案"
```

---

## Task 2：LrmxFile.create_new() + DocxExporter.export_bytes()

**Files:**
- Modify: `app/core/lrmx.py`
- Modify: `app/core/docx_exporter.py`

### 2a. LrmxFile.create_new()

新建一个没有磁盘文件支撑的空 `LrmxFile`，供"新文件另存为"场景使用。

- [ ] **Step 1: 在 lrmx.py 末尾追加 classmethod**

```python
    @classmethod
    def create_new(cls) -> 'LrmxFile':
        """创建一个无磁盘文件的空 LrmxFile，用于新建文档场景。"""
        root = ET.Element('Person')
        ET.SubElement(root, 'Version').text = '2.0'
        inst = cls.__new__(cls)
        inst.path = None          # type: ignore[assignment]
        inst._tree = ET.ElementTree(root)
        inst._root = root
        return inst
```

- [ ] **Step 2: 验证 create_new**

```bash
uv run python -c "
from app.core.lrmx import LrmxFile
lf = LrmxFile.create_new()
lf.set('XingMing', '张三')
import tempfile, pathlib
with tempfile.NamedTemporaryFile(suffix='.lrmx', delete=False) as f:
    tmp = f.name
lf.save(tmp)
lf2 = LrmxFile(tmp)
assert lf2.get('XingMing') == '张三', 'create_new + save failed'
print('create_new OK')
"
```

### 2b. DocxExporter.export_bytes()

- [ ] **Step 3: 在 docx_exporter.py 的 `export()` 方法后追加**

```python
    def export_bytes(self, lrmx: 'LrmxFile') -> bytes:
        """导出为 bytes（内部经由临时文件，复用 export() 的后处理逻辑）。"""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'out.docx'
            self.export(lrmx, out)
            return out.read_bytes()
```

- [ ] **Step 4: 验证 export_bytes**

```bash
uv run python -c "
from pathlib import Path
from app.core.docx_exporter import DocxExporter, get_template_path
from app.core.lrmx import LrmxFile
import glob, sys
files = glob.glob('**/*.lrmx', recursive=True)
if not files:
    print('no lrmx files found, skip')
    sys.exit(0)
lf = LrmxFile(files[0])
tpl = get_template_path()
exp = DocxExporter(tpl)
data = exp.export_bytes(lf)
assert len(data) > 1000, 'export_bytes returned empty'
print(f'export_bytes OK, size={len(data)}')
"
```

- [ ] **Step 5: Commit**

```bash
git add app/core/lrmx.py app/core/docx_exporter.py
git commit -m "feat: LrmxFile.create_new() + DocxExporter.export_bytes()"
```

---

## Task 3：PrintPreviewDialog

**Files:**
- Create: `app/ui/widgets/print_preview.py`

打印预览对话框：显示 PDF → 用户确认 → 弹系统打印对话框 → 打印后删除临时文件。

- [ ] **Step 1: 创建 print_preview.py**

```python
"""打印预览对话框：用 QtPdf.QPdfView 显示临时 PDF，用户确认后打印。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPageLayout, QPageSize
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtPrintSupport import QPrinter, QPrintDialog
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
)


class PrintPreviewDialog(QDialog):
    """显示 pdf_path 的预览，用户点「打印…」后弹系统打印对话框。
    关闭（无论是否打印）后删除 pdf_path。
    """

    def __init__(self, pdf_path: Path, parent=None):
        super().__init__(parent)
        self._pdf_path = pdf_path
        self.setWindowTitle('打印预览')
        self.resize(800, 1000)
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 8)
        lay.setSpacing(0)

        # PDF 文档
        self._doc = QPdfDocument(self)
        self._doc.load(str(self._pdf_path))

        # PDF 视图
        self._view = QPdfView(self)
        self._view.setDocument(self._doc)
        self._view.setPageMode(QPdfView.PageMode.MultiPage)
        self._view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        lay.addWidget(self._view, 1)

        # 底部按钮行
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(12, 6, 12, 0)
        btn_row.setSpacing(8)
        hint = QLabel('确认无误后点击「打印…」选择打印机')
        hint.setStyleSheet('color: #888; font-size: 11px;')
        btn_row.addWidget(hint, 1)

        cancel_btn = QPushButton('取消')
        cancel_btn.setFixedHeight(28)
        cancel_btn.clicked.connect(self.reject)

        print_btn = QPushButton('打印…')
        print_btn.setObjectName('primary')
        print_btn.setFixedHeight(28)
        print_btn.clicked.connect(self._do_print)

        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(print_btn)
        lay.addLayout(btn_row)

    def _do_print(self):
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dlg = QPrintDialog(printer, self)
        if dlg.exec() != QPrintDialog.DialogCode.Accepted:
            return

        from PySide6.QtGui import QPainter
        painter = QPainter(printer)
        page_count = self._doc.pageCount()
        for i in range(page_count):
            if i > 0:
                printer.newPage()
            # 将 PDF 页渲染到打印机分辨率的矩形
            rect = painter.viewport()
            img = self._doc.render(i, rect.size())
            painter.drawImage(rect, img)
        painter.end()
        self.accept()

    def closeEvent(self, ev):
        self._doc.close()
        try:
            self._pdf_path.unlink(missing_ok=True)
        except OSError:
            pass
        super().closeEvent(ev)
```

- [ ] **Step 2: 手动验证（有 PDF 文件时）**

```bash
uv run python -c "
import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
from app.ui.widgets.print_preview import PrintPreviewDialog
app = QApplication(sys.argv)
# 替换为本机任意 PDF 路径
pdf = Path(r'C:/Windows/System32/oobe/FirstLogonAnim.pdf')
if not pdf.exists():
    print('no test pdf, skip visual check')
    sys.exit(0)
dlg = PrintPreviewDialog(pdf)
dlg.exec()
"
```

- [ ] **Step 3: Commit**

```bash
git add app/ui/widgets/print_preview.py
git commit -m "feat: PrintPreviewDialog（QtPdf 预览 + 系统打印对话框）"
```

---

## Task 4：EditorTab 多标签页重构

**Files:**
- Modify: `app/ui/tabs/editor_tab.py` （完整重写）

这是本次最大的任务。将现有单文档 `EditorTab` 重构为：
- `_DocPane(QWidget)`：封装单文档表单 + 状态
- `EditorTab(QWidget)`：QTabWidget 容器 + 文件树 + 工具栏

### 重构说明

现有 `EditorTab` 中：
- 所有 `self._xxx` 表单 widget → 移入 `_DocPane`
- `_load_file`, `_close_file`, `_collect`, `_save`, `_save_as`, `_mark_dirty`, `_connect_dirty` → 移入 `_DocPane`，方法名去下划线前缀
- `_build_form()` → 成为 `_DocPane._build_layout_b()`（当前轻量式布局）
- 工具栏按钮信号 → 改为调用 `self._active_pane().save()` 等

- [ ] **Step 1: 完整替换 editor_tab.py**

将 `app/ui/tabs/editor_tab.py` 替换为以下内容：

```python
"""任免审批表编辑器 Tab — 多标签页版本。

每个打开的 .lrmx 文件在 QTabWidget 中占一个 _DocPane。
工具栏按钮操作当前激活的 _DocPane。
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QSettings
from PySide6.QtGui import QFont, QFontMetricsF, QTextBlockFormat, QTextCursor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QLineEdit, QComboBox, QTextEdit,
    QScrollArea, QFileDialog, QMessageBox, QSizePolicy,
    QFrame, QTabWidget,
)

from app.core.dmgrp_loader import get_loader
from app.core.lrmx import LrmxFile
from app.ui.widgets.lrmx_tree import LrmxTreePanel
from app.ui.widgets.photo_widget import PhotoWidget
from app.ui.widgets.family_table import FamilyTable

USES_FILE_PANEL = False

_LW2 = 72
_ROW_H = 28


def _lbl(text: str, width: int = _LW2) -> QLabel:
    lbl = QLabel(text)
    lbl.setFixedWidth(width)
    lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    lbl.setStyleSheet('color: #555; font-size: 12px;')
    return lbl


def _line(placeholder: str = '', readonly: bool = False) -> QLineEdit:
    w = QLineEdit()
    w.setPlaceholderText(placeholder)
    w.setReadOnly(readonly)
    w.setFixedHeight(_ROW_H)
    if readonly:
        w.setStyleSheet('background: #f5f5f0; color: #888;')
    return w


def _combo(options: list[str], editable: bool = True) -> QComboBox:
    w = QComboBox()
    w.setEditable(editable)
    if editable:
        w.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
    w.addItem('')
    for o in options:
        w.addItem(o)
    w.setFixedHeight(_ROW_H)
    return w


def _section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        'font-size: 12px; font-weight: bold; color: #444;'
        'border-bottom: 1px solid #ddd; padding-bottom: 2px; margin-top: 4px;'
    )
    return lbl


class _ResumeEdit(QTextEdit):
    """简历编辑框：自动换行 + 18 字符悬挂缩进。"""
    _INDENT_CHARS = 18

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('resumeEdit')
        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self._apply_indent()

    def _indent_px(self) -> float:
        f = QFont()
        f.setFamilies(['NSimSun', 'SimSun', 'Consolas'])
        f.setPixelSize(13)
        return self._INDENT_CHARS * QFontMetricsF(f).horizontalAdvance('0')

    def _apply_indent(self):
        indent = self._indent_px()
        fmt = QTextBlockFormat()
        fmt.setLeftMargin(indent)
        fmt.setTextIndent(-indent)
        cur = QTextCursor(self.document())
        cur.select(QTextCursor.SelectionType.Document)
        was = self.blockSignals(True)
        cur.mergeBlockFormat(fmt)
        self.blockSignals(was)

    def setPlainText(self, text: str) -> None:
        super().setPlainText(text)
        self._apply_indent()

    def clear(self) -> None:
        super().clear()
        self._apply_indent()


class _DocPane(QWidget):
    """单文档窗格：表单 widget + 文件状态。"""

    dirty_changed = Signal(bool)   # 文件脏状态变化
    path_changed  = Signal(str)    # 文件路径变化（另存为后）

    def __init__(self, layout_mode: str = 'b', parent=None):
        super().__init__(parent)
        self._lrmx: LrmxFile | None = None
        self._current_path: str | None = None
        self._dirty = False
        self._loading = False
        self._layout_mode = layout_mode
        self._build_widgets()
        self._install_layout(layout_mode)
        self._connect_dirty()

    # ── widget 实例化（与布局无关）───────────────────────────────────────────

    def _build_widgets(self):
        loader = get_loader()
        self._xing_ming      = _line()
        self._xing_bie       = _combo(loader.options('GB22611'))
        self._chu_sheng      = _line('YYYYMM')
        self._min_zu         = _combo(loader.options('GB3304'))
        self._ji_guan        = _line()
        self._chu_di         = _line()
        self._photo          = PhotoWidget()
        self._ru_dang        = _line('YYYYMM')
        self._can_jia        = _line('YYYYMM')
        self._dao_ling       = _line(readonly=True)
        self._jian_kang      = _combo(loader.options('GB22613'))
        self._zhuan_ye       = _combo(loader.options('GB8561'))
        self._shu_xi         = _line()

        xu_li_opts   = loader.options('ZB64')
        xue_wei_opts = loader.options('GB6864')
        self._qrz_xueli       = _combo(xu_li_opts)
        self._qrz_xuewei      = _combo(xue_wei_opts)
        self._qrz_xueli_yuan  = _line()
        self._qrz_xuewei_yuan = _line()
        self._zzj_xueli       = _combo(xu_li_opts)
        self._zzj_xuewei      = _combo(xue_wei_opts)
        self._zzj_xueli_yuan  = _line()
        self._zzj_xuewei_yuan = _line()

        self._xian_ren  = _line()
        self._ni_ren    = _line()
        self._ni_mian   = _line()
        self._jian_li   = _ResumeEdit()
        self._jian_li.setMinimumHeight(200)
        self._jian_li.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._jiang_cheng = QTextEdit()
        self._jiang_cheng.setFixedHeight(80)
        self._nian_du     = QTextEdit()
        self._nian_du.setFixedHeight(80)
        self._ren_mian    = QTextEdit()
        self._ren_mian.setFixedHeight(100)

        self._family = FamilyTable()
        self._family.setMinimumHeight(180)
        self._family.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._cheng_bao     = _line()
        self._gai_ge_nll    = _combo(loader.options('NLLB'))
        self._shen_fen      = _line()
        self._ji_suan       = _line('YYYYMMDD')
        self._tian_biao_shi = _line()
        self._tian_biao_ren = _line()

    # ── 布局（两种，可运行时切换）────────────────────────────────────────────

    def _install_layout(self, mode: str):
        """拆除旧布局并安装新布局。"""
        # 拆除旧布局（若有）
        old = self.layout()
        if old is not None:
            # 把顶层 widget 从旧布局里取出，不删除 widget 本身
            while old.count():
                item = old.takeAt(0)
                w = item.widget()
                if w:
                    w.setParent(None)  # type: ignore[arg-type]
            import shiboken6
            if shiboken6.isValid(old):
                old.deleteLater()

        if mode == 'a':
            self._build_layout_a()
        else:
            self._build_layout_b()
        self._layout_mode = mode

    def _build_layout_b(self):
        """轻量分隔式布局（现有双栏滚动表单）。"""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        container.setObjectName('editorForm')
        outer = QHBoxLayout(container)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(12)

        # ── 左栏 ─────────────────────────────────────────────────────────
        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(6)

        info_grid = QGridLayout()
        info_grid.setHorizontalSpacing(6)
        info_grid.setVerticalSpacing(4)
        info_grid.setColumnStretch(1, 1)
        info_grid.setColumnStretch(3, 1)
        info_grid.setColumnStretch(5, 1)
        info_grid.setColumnMinimumWidth(0, _LW2)
        info_grid.setColumnMinimumWidth(2, _LW2)
        info_grid.setColumnMinimumWidth(4, _LW2)

        info_grid.addWidget(_lbl('姓名'), 0, 0)
        info_grid.addWidget(self._xing_ming, 0, 1)
        info_grid.addWidget(_lbl('性别'), 0, 2)
        info_grid.addWidget(self._xing_bie, 0, 3)
        info_grid.addWidget(_lbl('出生年月'), 1, 0)
        info_grid.addWidget(self._chu_sheng, 1, 1)
        info_grid.addWidget(_lbl('民族'), 1, 2)
        info_grid.addWidget(self._min_zu, 1, 3)
        info_grid.addWidget(_lbl('籍贯'), 2, 0)
        info_grid.addWidget(self._ji_guan, 2, 1)
        info_grid.addWidget(_lbl('出生地'), 2, 2)
        info_grid.addWidget(self._chu_di, 2, 3)
        info_grid.addWidget(
            self._photo, 0, 4, 3, 2,
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter,
        )
        info_grid.addWidget(_lbl('入党时间'), 3, 0)
        info_grid.addWidget(self._ru_dang, 3, 1)
        info_grid.addWidget(_lbl('参工时间'), 3, 2)
        info_grid.addWidget(self._can_jia, 3, 3)
        info_grid.addWidget(_lbl('到龄时间'), 3, 4)
        info_grid.addWidget(self._dao_ling, 3, 5)
        info_grid.addWidget(_lbl('健康状况'), 4, 0)
        info_grid.addWidget(self._jian_kang, 4, 1)
        info_grid.addWidget(_lbl('专技职务'), 4, 2)
        info_grid.addWidget(self._zhuan_ye, 4, 3)
        info_grid.addWidget(_lbl('熟悉专业'), 4, 4)
        info_grid.addWidget(self._shu_xi, 4, 5)
        left_lay.addLayout(info_grid)

        left_lay.addWidget(_section_label('学历学位'))
        edu_grid = QGridLayout()
        edu_grid.setHorizontalSpacing(6)
        edu_grid.setVerticalSpacing(4)
        edu_grid.setColumnMinimumWidth(0, 52)
        edu_grid.setColumnMinimumWidth(1, 48)
        edu_grid.setColumnStretch(2, 1)
        edu_grid.setColumnMinimumWidth(3, 60)
        edu_grid.setColumnStretch(4, 2)
        for row, (type_lbl, kind_lbl, combo_w, yuan_w) in enumerate([
            ('全日制', '学历', self._qrz_xueli,  self._qrz_xueli_yuan),
            ('全日制', '学位', self._qrz_xuewei, self._qrz_xuewei_yuan),
            ('在职',   '学历', self._zzj_xueli,  self._zzj_xueli_yuan),
            ('在职',   '学位', self._zzj_xuewei, self._zzj_xuewei_yuan),
        ]):
            edu_grid.addWidget(QLabel(type_lbl), row, 0)
            edu_grid.addWidget(QLabel(kind_lbl), row, 1)
            edu_grid.addWidget(combo_w, row, 2)
            edu_grid.addWidget(QLabel('毕业院校系及专业'), row, 3)
            edu_grid.addWidget(yuan_w, row, 4)
        left_lay.addLayout(edu_grid)

        left_lay.addWidget(_section_label('职务'))
        pos_grid = QGridLayout()
        pos_grid.setHorizontalSpacing(6)
        pos_grid.setVerticalSpacing(4)
        pos_grid.setColumnMinimumWidth(0, _LW2)
        pos_grid.setColumnStretch(1, 1)
        pos_grid.addWidget(_lbl('现任职务'), 0, 0)
        pos_grid.addWidget(self._xian_ren, 0, 1)
        pos_grid.addWidget(_lbl('拟任职务'), 1, 0)
        pos_grid.addWidget(self._ni_ren, 1, 1)
        pos_grid.addWidget(_lbl('拟免职务'), 2, 0)
        pos_grid.addWidget(self._ni_mian, 2, 1)
        left_lay.addLayout(pos_grid)

        left_lay.addWidget(_section_label('简历'))
        left_lay.addWidget(self._jian_li, 1)

        left.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        outer.addWidget(left, 1)

        # ── 右栏 ─────────────────────────────────────────────────────────
        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(6)
        right_lay.addWidget(_section_label('奖惩情况'))
        right_lay.addWidget(self._jiang_cheng)
        right_lay.addWidget(_section_label('年度考核结果'))
        right_lay.addWidget(self._nian_du)
        right_lay.addWidget(_section_label('任免理由'))
        right_lay.addWidget(self._ren_mian)
        right_lay.addWidget(_section_label('家庭主要成员'))
        right_lay.addWidget(self._family, 1)
        right_lay.addWidget(_section_label('底部信息'))

        bot_grid = QGridLayout()
        bot_grid.setHorizontalSpacing(6)
        bot_grid.setVerticalSpacing(4)
        bot_grid.setColumnStretch(1, 1)
        bot_grid.setColumnStretch(3, 1)
        bot_grid.addWidget(_lbl('呈报单位'), 0, 0)
        bot_grid.addWidget(self._cheng_bao, 0, 1, 1, 3)
        bot_grid.addWidget(_lbl('改革前年龄'), 1, 0)
        bot_grid.addWidget(self._gai_ge_nll, 1, 1, 1, 3)
        bot_grid.addWidget(_lbl('身份证号'), 2, 0)
        bot_grid.addWidget(self._shen_fen, 2, 1)
        bot_grid.addWidget(_lbl('计算年龄'), 2, 2)
        bot_grid.addWidget(self._ji_suan, 2, 3)
        bot_grid.addWidget(_lbl('填表时间'), 3, 0)
        bot_grid.addWidget(self._tian_biao_shi, 3, 1)
        bot_grid.addWidget(_lbl('填表人'), 3, 2)
        bot_grid.addWidget(self._tian_biao_ren, 3, 3)
        right_lay.addLayout(bot_grid)

        right.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        outer.addWidget(right, 1)

        scroll.setWidget(container)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

    def _build_layout_a(self):
        """严格表格式布局：全格线，密度最高。"""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        container.setObjectName('editorFormA')
        grid = QGridLayout(container)
        grid.setSpacing(0)
        grid.setContentsMargins(0, 0, 0, 0)

        def lbl_cell(text: str) -> QLabel:
            w = QLabel(text)
            w.setObjectName('tableLbl')
            w.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            w.setContentsMargins(4, 2, 6, 2)
            return w

        def sec_cell(text: str) -> QLabel:
            w = QLabel(text)
            w.setObjectName('tableSecLbl')
            w.setContentsMargins(6, 2, 6, 2)
            return w

        row = 0

        # 基本信息
        grid.addWidget(sec_cell('基本信息'), row, 0, 1, 8); row += 1
        grid.addWidget(lbl_cell('姓名'), row, 0)
        grid.addWidget(self._xing_ming, row, 1)
        grid.addWidget(lbl_cell('性别'), row, 2)
        grid.addWidget(self._xing_bie, row, 3)
        grid.addWidget(self._photo, row, 4, 3, 4,
                       Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        row += 1
        grid.addWidget(lbl_cell('出生年月'), row, 0)
        grid.addWidget(self._chu_sheng, row, 1)
        grid.addWidget(lbl_cell('民族'), row, 2)
        grid.addWidget(self._min_zu, row, 3); row += 1
        grid.addWidget(lbl_cell('籍贯'), row, 0)
        grid.addWidget(self._ji_guan, row, 1)
        grid.addWidget(lbl_cell('出生地'), row, 2)
        grid.addWidget(self._chu_di, row, 3); row += 1
        grid.addWidget(lbl_cell('入党时间'), row, 0)
        grid.addWidget(self._ru_dang, row, 1)
        grid.addWidget(lbl_cell('参工时间'), row, 2)
        grid.addWidget(self._can_jia, row, 3)
        grid.addWidget(lbl_cell('到龄时间'), row, 4)
        grid.addWidget(self._dao_ling, row, 5, 1, 3); row += 1
        grid.addWidget(lbl_cell('健康状况'), row, 0)
        grid.addWidget(self._jian_kang, row, 1)
        grid.addWidget(lbl_cell('专技职务'), row, 2)
        grid.addWidget(self._zhuan_ye, row, 3)
        grid.addWidget(lbl_cell('熟悉专业'), row, 4)
        grid.addWidget(self._shu_xi, row, 5, 1, 3); row += 1

        # 学历学位
        grid.addWidget(sec_cell('学历学位'), row, 0, 1, 8); row += 1
        for type_lbl, kind_lbl, combo_w, yuan_w in [
            ('全日制', '学历', self._qrz_xueli,  self._qrz_xueli_yuan),
            ('全日制', '学位', self._qrz_xuewei, self._qrz_xuewei_yuan),
            ('在职',   '学历', self._zzj_xueli,  self._zzj_xueli_yuan),
            ('在职',   '学位', self._zzj_xuewei, self._zzj_xuewei_yuan),
        ]:
            grid.addWidget(lbl_cell(type_lbl), row, 0)
            grid.addWidget(lbl_cell(kind_lbl), row, 1)
            grid.addWidget(combo_w, row, 2)
            grid.addWidget(lbl_cell('毕业院校系及专业'), row, 3)
            grid.addWidget(yuan_w, row, 4, 1, 4); row += 1

        # 职务
        grid.addWidget(sec_cell('职务'), row, 0, 1, 8); row += 1
        for lbl_text, w in [('现任职务', self._xian_ren),
                             ('拟任职务', self._ni_ren),
                             ('拟免职务', self._ni_mian)]:
            grid.addWidget(lbl_cell(lbl_text), row, 0)
            grid.addWidget(w, row, 1, 1, 7); row += 1

        # 简历
        grid.addWidget(sec_cell('简历'), row, 0, 1, 8); row += 1
        grid.addWidget(self._jian_li, row, 0, 1, 8); row += 1

        # 右栏内容（在此布局中顺序排列于左栏之下）
        grid.addWidget(sec_cell('奖惩情况'), row, 0, 1, 8); row += 1
        grid.addWidget(self._jiang_cheng, row, 0, 1, 8); row += 1
        grid.addWidget(sec_cell('年度考核结果'), row, 0, 1, 8); row += 1
        grid.addWidget(self._nian_du, row, 0, 1, 8); row += 1
        grid.addWidget(sec_cell('任免理由'), row, 0, 1, 8); row += 1
        grid.addWidget(self._ren_mian, row, 0, 1, 8); row += 1
        grid.addWidget(sec_cell('家庭主要成员'), row, 0, 1, 8); row += 1
        grid.addWidget(self._family, row, 0, 1, 8); row += 1

        # 底部
        grid.addWidget(sec_cell('底部信息'), row, 0, 1, 8); row += 1
        grid.addWidget(lbl_cell('呈报单位'), row, 0)
        grid.addWidget(self._cheng_bao, row, 1, 1, 7); row += 1
        grid.addWidget(lbl_cell('改革前年龄'), row, 0)
        grid.addWidget(self._gai_ge_nll, row, 1, 1, 7); row += 1
        grid.addWidget(lbl_cell('身份证号'), row, 0)
        grid.addWidget(self._shen_fen, row, 1)
        grid.addWidget(lbl_cell('计算年龄'), row, 2)
        grid.addWidget(self._ji_suan, row, 3, 1, 5); row += 1
        grid.addWidget(lbl_cell('填表时间'), row, 0)
        grid.addWidget(self._tian_biao_shi, row, 1)
        grid.addWidget(lbl_cell('填表人'), row, 2)
        grid.addWidget(self._tian_biao_ren, row, 3, 1, 5); row += 1

        for col in range(8):
            grid.setColumnStretch(col, 1)

        scroll.setWidget(container)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

    def rebuild_layout(self, mode: str) -> None:
        """切换布局模式（保留字段值）。"""
        if mode == self._layout_mode:
            return
        snap = self._snapshot()
        self._install_layout(mode)
        self._connect_dirty()
        self._restore_snapshot(snap)

    # ── 字段快照（用于布局切换时保留值）────────────────────────────────────

    def _snapshot(self) -> dict:
        return {
            'XingMing': self._xing_ming.text(),
            'XingBie': self._xing_bie.currentText(),
            'ChuShengNianYue': self._chu_sheng.text(),
            'MinZu': self._min_zu.currentText(),
            'JiGuan': self._ji_guan.text(),
            'ChuShengDi': self._chu_di.text(),
            'RuDangShiJian': self._ru_dang.text(),
            'CanJiaGongZuoShiJian': self._can_jia.text(),
            'DaoLingNianYue': self._dao_ling.text(),
            'JianKangZhuangKuang': self._jian_kang.currentText(),
            'ZhuanYeJiShuZhiWu': self._zhuan_ye.currentText(),
            'ShuXiZhuanYeYouHeZhuanChang': self._shu_xi.text(),
            'QuanRiZhiJiaoYu_XueLi': self._qrz_xueli.currentText(),
            'QuanRiZhiJiaoYu_XueWei': self._qrz_xuewei.currentText(),
            'QuanRiZhiJiaoYu_XueLi_BiYeYuanXiaoXi': self._qrz_xueli_yuan.text(),
            'QuanRiZhiJiaoYu_XueWei_BiYeYuanXiaoXi': self._qrz_xuewei_yuan.text(),
            'ZaiZhiJiaoYu_XueLi': self._zzj_xueli.currentText(),
            'ZaiZhiJiaoYu_XueWei': self._zzj_xuewei.currentText(),
            'ZaiZhiJiaoYu_XueLi_BiYeYuanXiaoXi': self._zzj_xueli_yuan.text(),
            'ZaiZhiJiaoYu_XueWei_BiYeYuanXiaoXi': self._zzj_xuewei_yuan.text(),
            'XianRenZhiWu': self._xian_ren.text(),
            'NiRenZhiWu': self._ni_ren.text(),
            'NiMianZhiWu': self._ni_mian.text(),
            'JianLi': self._jian_li.toPlainText(),
            'JiangChengQingKuang': self._jiang_cheng.toPlainText(),
            'NianDuKaoHeJieGuo': self._nian_du.toPlainText(),
            'RenMianLiYou': self._ren_mian.toPlainText(),
            'ChengBaoDanWei': self._cheng_bao.text(),
            'GaiGeQianRenZhiNianLingJieXian': self._gai_ge_nll.currentText(),
            'ShenFenZheng': self._shen_fen.text(),
            'JiSuanNianLingShiJian': self._ji_suan.text(),
            'TianBiaoShiJian': self._tian_biao_shi.text(),
            'TianBiaoRen': self._tian_biao_ren.text(),
            'ZhaoPian': self._photo.b64(),
            '_family': self._family.dump(),
        }

    def _restore_snapshot(self, snap: dict) -> None:
        self._loading = True
        try:
            self._xing_ming.setText(snap.get('XingMing', ''))
            self._set_combo(self._xing_bie, snap.get('XingBie', ''))
            self._chu_sheng.setText(snap.get('ChuShengNianYue', ''))
            self._set_combo(self._min_zu, snap.get('MinZu', ''))
            self._ji_guan.setText(snap.get('JiGuan', ''))
            self._chu_di.setText(snap.get('ChuShengDi', ''))
            self._ru_dang.setText(snap.get('RuDangShiJian', ''))
            self._can_jia.setText(snap.get('CanJiaGongZuoShiJian', ''))
            self._dao_ling.setText(snap.get('DaoLingNianYue', ''))
            self._set_combo(self._jian_kang, snap.get('JianKangZhuangKuang', ''))
            self._set_combo(self._zhuan_ye, snap.get('ZhuanYeJiShuZhiWu', ''))
            self._shu_xi.setText(snap.get('ShuXiZhuanYeYouHeZhuanChang', ''))
            self._set_combo(self._qrz_xueli, snap.get('QuanRiZhiJiaoYu_XueLi', ''))
            self._set_combo(self._qrz_xuewei, snap.get('QuanRiZhiJiaoYu_XueWei', ''))
            self._qrz_xueli_yuan.setText(snap.get('QuanRiZhiJiaoYu_XueLi_BiYeYuanXiaoXi', ''))
            self._qrz_xuewei_yuan.setText(snap.get('QuanRiZhiJiaoYu_XueWei_BiYeYuanXiaoXi', ''))
            self._set_combo(self._zzj_xueli, snap.get('ZaiZhiJiaoYu_XueLi', ''))
            self._set_combo(self._zzj_xuewei, snap.get('ZaiZhiJiaoYu_XueWei', ''))
            self._zzj_xueli_yuan.setText(snap.get('ZaiZhiJiaoYu_XueLi_BiYeYuanXiaoXi', ''))
            self._zzj_xuewei_yuan.setText(snap.get('ZaiZhiJiaoYu_XueWei_BiYeYuanXiaoXi', ''))
            self._xian_ren.setText(snap.get('XianRenZhiWu', ''))
            self._ni_ren.setText(snap.get('NiRenZhiWu', ''))
            self._ni_mian.setText(snap.get('NiMianZhiWu', ''))
            self._jian_li.setPlainText(snap.get('JianLi', ''))
            self._jiang_cheng.setPlainText(snap.get('JiangChengQingKuang', ''))
            self._nian_du.setPlainText(snap.get('NianDuKaoHeJieGuo', ''))
            self._ren_mian.setPlainText(snap.get('RenMianLiYou', ''))
            self._cheng_bao.setText(snap.get('ChengBaoDanWei', ''))
            self._set_combo(self._gai_ge_nll, snap.get('GaiGeQianRenZhiNianLingJieXian', ''))
            self._shen_fen.setText(snap.get('ShenFenZheng', ''))
            self._ji_suan.setText(snap.get('JiSuanNianLingShiJian', ''))
            self._tian_biao_shi.setText(snap.get('TianBiaoShiJian', ''))
            self._tian_biao_ren.setText(snap.get('TianBiaoRen', ''))
            self._photo.set_b64(snap.get('ZhaoPian', ''))
            self._family.load(snap.get('_family', []))
        finally:
            self._loading = False

    # ── 文件操作 ─────────────────────────────────────────────────────────────

    def load(self, path: str) -> None:
        self._loading = True
        try:
            lrmx = LrmxFile(path)
            self._lrmx = lrmx
            self._current_path = path
            d = lrmx.as_dict()
            snap = {
                'XingMing': d.get('XingMing', ''),
                'XingBie': d.get('XingBie', ''),
                'ChuShengNianYue': d.get('ChuShengNianYue', ''),
                'MinZu': d.get('MinZu', ''),
                'JiGuan': d.get('JiGuan', ''),
                'ChuShengDi': d.get('ChuShengDi', ''),
                'RuDangShiJian': d.get('RuDangShiJian', ''),
                'CanJiaGongZuoShiJian': d.get('CanJiaGongZuoShiJian', ''),
                'DaoLingNianYue': d.get('DaoLingNianYue', ''),
                'JianKangZhuangKuang': d.get('JianKangZhuangKuang', ''),
                'ZhuanYeJiShuZhiWu': d.get('ZhuanYeJiShuZhiWu', ''),
                'ShuXiZhuanYeYouHeZhuanChang': d.get('ShuXiZhuanYeYouHeZhuanChang', ''),
                'QuanRiZhiJiaoYu_XueLi': d.get('QuanRiZhiJiaoYu_XueLi', ''),
                'QuanRiZhiJiaoYu_XueWei': d.get('QuanRiZhiJiaoYu_XueWei', ''),
                'QuanRiZhiJiaoYu_XueLi_BiYeYuanXiaoXi': d.get('QuanRiZhiJiaoYu_XueLi_BiYeYuanXiaoXi', '').strip(),
                'QuanRiZhiJiaoYu_XueWei_BiYeYuanXiaoXi': d.get('QuanRiZhiJiaoYu_XueWei_BiYeYuanXiaoXi', '').strip(),
                'ZaiZhiJiaoYu_XueLi': d.get('ZaiZhiJiaoYu_XueLi', ''),
                'ZaiZhiJiaoYu_XueWei': d.get('ZaiZhiJiaoYu_XueWei', ''),
                'ZaiZhiJiaoYu_XueLi_BiYeYuanXiaoXi': d.get('ZaiZhiJiaoYu_XueLi_BiYeYuanXiaoXi', '').strip(),
                'ZaiZhiJiaoYu_XueWei_BiYeYuanXiaoXi': d.get('ZaiZhiJiaoYu_XueWei_BiYeYuanXiaoXi', '').strip(),
                'XianRenZhiWu': d.get('XianRenZhiWu', '').strip(),
                'NiRenZhiWu': d.get('NiRenZhiWu', '').strip(),
                'NiMianZhiWu': d.get('NiMianZhiWu', '').strip(),
                'JianLi': d.get('JianLi', ''),
                'JiangChengQingKuang': d.get('JiangChengQingKuang', '').strip(),
                'NianDuKaoHeJieGuo': d.get('NianDuKaoHeJieGuo', ''),
                'RenMianLiYou': d.get('RenMianLiYou', '').strip(),
                'ChengBaoDanWei': d.get('ChengBaoDanWei', ''),
                'GaiGeQianRenZhiNianLingJieXian': d.get('GaiGeQianRenZhiNianLingJieXian', ''),
                'ShenFenZheng': d.get('ShenFenZheng', ''),
                'JiSuanNianLingShiJian': d.get('JiSuanNianLingShiJian', ''),
                'TianBiaoShiJian': d.get('TianBiaoShiJian', ''),
                'TianBiaoRen': d.get('TianBiaoRen', ''),
                'ZhaoPian': d.get('ZhaoPian', ''),
                '_family': lrmx.family_members(),
            }
            self._restore_snapshot(snap)
            self._dirty = False
        finally:
            self._loading = False
        self.path_changed.emit(path)
        self.dirty_changed.emit(False)

    def close_file(self) -> None:
        self._restore_snapshot({})
        self._lrmx = None
        self._current_path = None
        self._dirty = False
        self.path_changed.emit('')
        self.dirty_changed.emit(False)

    def collect(self) -> None:
        if self._lrmx is None:
            return
        lrmx = self._lrmx
        lrmx.set('XingMing', self._xing_ming.text())
        lrmx.set('XingBie', self._xing_bie.currentText())
        lrmx.set('ChuShengNianYue', self._chu_sheng.text())
        lrmx.set('MinZu', self._min_zu.currentText())
        lrmx.set('JiGuan', self._ji_guan.text())
        lrmx.set('ChuShengDi', self._chu_di.text())
        lrmx.set('RuDangShiJian', self._ru_dang.text())
        lrmx.set('CanJiaGongZuoShiJian', self._can_jia.text())
        lrmx.set('JianKangZhuangKuang', self._jian_kang.currentText())
        lrmx.set('ZhuanYeJiShuZhiWu', self._zhuan_ye.currentText())
        lrmx.set('ShuXiZhuanYeYouHeZhuanChang', self._shu_xi.text())
        lrmx.set('QuanRiZhiJiaoYu_XueLi', self._qrz_xueli.currentText())
        lrmx.set('QuanRiZhiJiaoYu_XueWei', self._qrz_xuewei.currentText())
        lrmx.set('QuanRiZhiJiaoYu_XueLi_BiYeYuanXiaoXi', self._qrz_xueli_yuan.text())
        lrmx.set('QuanRiZhiJiaoYu_XueWei_BiYeYuanXiaoXi', self._qrz_xuewei_yuan.text())
        lrmx.set('ZaiZhiJiaoYu_XueLi', self._zzj_xueli.currentText())
        lrmx.set('ZaiZhiJiaoYu_XueWei', self._zzj_xuewei.currentText())
        lrmx.set('ZaiZhiJiaoYu_XueLi_BiYeYuanXiaoXi', self._zzj_xueli_yuan.text())
        lrmx.set('ZaiZhiJiaoYu_XueWei_BiYeYuanXiaoXi', self._zzj_xuewei_yuan.text())
        lrmx.set('XianRenZhiWu', self._xian_ren.text())
        lrmx.set('NiRenZhiWu', self._ni_ren.text())
        lrmx.set('NiMianZhiWu', self._ni_mian.text())
        lrmx.set('JianLi', self._jian_li.toPlainText())
        lrmx.set('JiangChengQingKuang', self._jiang_cheng.toPlainText())
        lrmx.set('NianDuKaoHeJieGuo', self._nian_du.toPlainText())
        lrmx.set('RenMianLiYou', self._ren_mian.toPlainText())
        lrmx.set_family_members(self._family.dump())
        lrmx.set('ChengBaoDanWei', self._cheng_bao.text())
        lrmx.set('GaiGeQianRenZhiNianLingJieXian', self._gai_ge_nll.currentText())
        lrmx.set('ShenFenZheng', self._shen_fen.text())
        lrmx.set('JiSuanNianLingShiJian', self._ji_suan.text())
        lrmx.set('TianBiaoShiJian', self._tian_biao_shi.text())
        lrmx.set('TianBiaoRen', self._tian_biao_ren.text())
        lrmx.set('ZhaoPian', self._photo.b64())

    def save(self) -> bool:
        """保存。若无路径则执行 save_as。成功返回 True。"""
        if self._lrmx is None:
            return self.save_as()
        if self._current_path is None:
            return self.save_as()
        self.collect()
        try:
            self._lrmx.save()
            self._dirty = False
            self.dirty_changed.emit(False)
            return True
        except Exception as e:
            QMessageBox.critical(self, '保存失败', str(e))
            return False

    def save_as(self) -> bool:
        """另存为。若 _lrmx 为 None 则先 create_new。成功返回 True。"""
        if self._lrmx is None:
            self._lrmx = LrmxFile.create_new()
        path, _ = QFileDialog.getSaveFileName(
            self, '另存为', self._current_path or '', '任免审批表 (*.lrmx)')
        if not path:
            return False
        self.collect()
        try:
            self._lrmx.save(path)
            self._current_path = path
            self._lrmx.path = Path(path)  # type: ignore[assignment]
            self._dirty = False
            self.dirty_changed.emit(False)
            self.path_changed.emit(path)
            return True
        except Exception as e:
            QMessageBox.critical(self, '保存失败', str(e))
            return False

    def is_dirty(self) -> bool:
        return self._dirty

    def current_path(self) -> str | None:
        return self._current_path

    def lrmx(self) -> LrmxFile | None:
        return self._lrmx

    # ── 脏状态 ───────────────────────────────────────────────────────────────

    def _mark_dirty(self, *_args):
        if self._loading:
            return
        if not self._dirty:
            self._dirty = True
            self.dirty_changed.emit(True)

    def _connect_dirty(self):
        for w in [self._xing_ming, self._chu_sheng, self._ji_guan, self._chu_di,
                  self._ru_dang, self._can_jia, self._shu_xi,
                  self._xian_ren, self._ni_ren, self._ni_mian,
                  self._qrz_xueli_yuan, self._qrz_xuewei_yuan,
                  self._zzj_xueli_yuan, self._zzj_xuewei_yuan,
                  self._cheng_bao, self._shen_fen, self._ji_suan,
                  self._tian_biao_shi, self._tian_biao_ren]:
            try: w.textChanged.disconnect(self._mark_dirty)
            except RuntimeError: pass
            w.textChanged.connect(self._mark_dirty)
        for w in [self._xing_bie, self._min_zu, self._jian_kang, self._zhuan_ye,
                  self._qrz_xueli, self._qrz_xuewei, self._zzj_xueli,
                  self._zzj_xuewei, self._gai_ge_nll]:
            try: w.currentTextChanged.disconnect(self._mark_dirty)
            except RuntimeError: pass
            w.currentTextChanged.connect(self._mark_dirty)
        for w in [self._jian_li, self._jiang_cheng, self._nian_du, self._ren_mian]:
            try: w.textChanged.disconnect(self._mark_dirty)
            except RuntimeError: pass
            w.textChanged.connect(self._mark_dirty)
        try: self._photo.changed.disconnect(self._mark_dirty)
        except RuntimeError: pass
        self._photo.changed.connect(self._mark_dirty)
        try: self._family.table_modified.disconnect(self._mark_dirty)
        except RuntimeError: pass
        self._family.table_modified.connect(self._mark_dirty)

    @staticmethod
    def _set_combo(combo: QComboBox, value: str) -> None:
        value = value.strip()
        idx = combo.findText(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        elif combo.isEditable():
            combo.setCurrentText(value)
        else:
            combo.setCurrentIndex(0)


class EditorTab(QWidget):
    USES_FILE_PANEL = False

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._build_ui()

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._tree = LrmxTreePanel()
        self._tree.setFixedWidth(220)
        self._tree.file_selected.connect(self._open_path)
        root.addWidget(self._tree)

        vline = QFrame()
        vline.setFrameShape(QFrame.Shape.VLine)
        vline.setFrameShadow(QFrame.Shadow.Sunken)
        vline.setStyleSheet('color: #ddd;')
        root.addWidget(vline)

        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(0)
        right_lay.addWidget(self._build_toolbar())

        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(True)
        self._tabs.tabCloseRequested.connect(self._close_tab)
        self._tabs.currentChanged.connect(self._refresh_toolbar)
        right_lay.addWidget(self._tabs, 1)
        root.addWidget(right, 1)

    def _build_toolbar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName('editorToolbar')
        bar.setFixedHeight(36)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(10, 4, 10, 4)
        lay.setSpacing(8)

        self._path_lbl = QLabel('未打开文件')
        self._path_lbl.setStyleSheet('color: #888; font-size: 11px;')
        lay.addWidget(self._path_lbl, 1)

        def _btn(text: str, tooltip: str = '') -> QPushButton:
            b = QPushButton(text)
            b.setFixedHeight(26)
            if tooltip:
                b.setToolTip(tooltip)
            return b

        self._open_btn   = _btn('打开', '打开 lrmx 文件（可多选）')
        self._close_btn  = _btn('关闭', '关闭当前标签页')
        self._save_btn   = _btn('保存', '保存当前文件')
        self._save_btn.setObjectName('primary')
        self._saveas_btn = _btn('另存为…')
        self._export_btn = _btn('导出 PDF')
        self._print_btn  = _btn('打印')

        self._open_btn.clicked.connect(self._on_open_btn)
        self._close_btn.clicked.connect(lambda: self._close_tab(self._tabs.currentIndex()))
        self._save_btn.clicked.connect(self._on_save_btn)
        self._saveas_btn.clicked.connect(self._on_saveas_btn)
        self._export_btn.clicked.connect(self._on_export_pdf)
        self._print_btn.clicked.connect(self._on_print_btn)

        lay.addWidget(self._open_btn)
        for b in [self._close_btn, self._save_btn, self._saveas_btn,
                  self._export_btn, self._print_btn]:
            b.setEnabled(False)
            lay.addWidget(b)
        return bar

    # ── active pane ──────────────────────────────────────────────────────────

    def _active_pane(self) -> _DocPane | None:
        w = self._tabs.currentWidget()
        return w if isinstance(w, _DocPane) else None

    def _layout_mode(self) -> str:
        return QSettings('rmb_helper', 'rmb_helper').value('editor/layout_mode', 'b')

    # ── public API ───────────────────────────────────────────────────────────

    def open_path(self, path: str) -> None:
        """外部调用（双击文件关联 / SingleInstance）。"""
        self._open_path(path)

    def set_layout_mode(self, mode: str) -> None:
        """由 MainWindow 在设置变更后调用，重建已有标签页布局。"""
        for i in range(self._tabs.count()):
            pane = self._tabs.widget(i)
            if isinstance(pane, _DocPane):
                pane.rebuild_layout(mode)

    # ── open / close tabs ────────────────────────────────────────────────────

    def _open_path(self, path: str) -> None:
        # 去重：已打开则激活
        for i in range(self._tabs.count()):
            pane = self._tabs.widget(i)
            if isinstance(pane, _DocPane) and pane.current_path() == path:
                self._tabs.setCurrentIndex(i)
                return
        pane = _DocPane(layout_mode=self._layout_mode())
        pane.dirty_changed.connect(lambda dirty, p=pane: self._on_pane_dirty(p, dirty))
        pane.path_changed.connect(lambda new_path, p=pane: self._on_pane_path(p, new_path))
        try:
            pane.load(path)
        except Exception as e:
            QMessageBox.critical(self, '打开失败', str(e))
            return
        idx = self._tabs.addTab(pane, Path(path).name)
        self._tabs.setCurrentIndex(idx)
        self._tree.add_path(path)
        self._refresh_toolbar()

    def _close_tab(self, index: int) -> None:
        if index < 0:
            return
        pane = self._tabs.widget(index)
        if isinstance(pane, _DocPane) and pane.is_dirty():
            ret = QMessageBox.question(
                self, '未保存修改', '当前文件有未保存的修改，关闭前是否保存？',
                QMessageBox.StandardButton.Save |
                QMessageBox.StandardButton.Discard |
                QMessageBox.StandardButton.Cancel,
            )
            if ret == QMessageBox.StandardButton.Cancel:
                return
            if ret == QMessageBox.StandardButton.Save:
                if isinstance(pane, _DocPane):
                    pane.save()
        self._tabs.removeTab(index)
        self._refresh_toolbar()

    # ── pane signal handlers ─────────────────────────────────────────────────

    def _on_pane_dirty(self, pane: _DocPane, dirty: bool) -> None:
        idx = self._tabs.indexOf(pane)
        if idx < 0:
            return
        path = pane.current_path()
        name = Path(path).name if path else '新文件'
        self._tabs.setTabText(idx, f'{name} *' if dirty else name)
        if pane is self._active_pane() and path:
            self._tree.set_modified(path, dirty)

    def _on_pane_path(self, pane: _DocPane, new_path: str) -> None:
        idx = self._tabs.indexOf(pane)
        if idx < 0:
            return
        if new_path:
            self._tabs.setTabText(idx, Path(new_path).name)
            self._tree.add_path(new_path)
        if pane is self._active_pane():
            self._path_lbl.setText(new_path or '未打开文件')

    def _refresh_toolbar(self) -> None:
        pane = self._active_pane()
        has = pane is not None
        for b in [self._close_btn, self._save_btn, self._saveas_btn,
                  self._export_btn, self._print_btn]:
            b.setEnabled(has)
        self._path_lbl.setText(
            (pane.current_path() or '新文件') if pane else '未打开文件'
        )

    # ── toolbar actions ──────────────────────────────────────────────────────

    def _on_open_btn(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, '打开文件', '', '任免审批表 (*.lrmx)')
        for path in paths:
            self._open_path(path)

    def _on_save_btn(self) -> None:
        pane = self._active_pane()
        if pane:
            pane.save()

    def _on_saveas_btn(self) -> None:
        pane = self._active_pane()
        if pane:
            pane.save_as()

    def _on_export_pdf(self) -> None:
        pane = self._active_pane()
        if pane is None:
            return
        lrmx = pane.lrmx()
        if lrmx is None:
            QMessageBox.information(self, '提示', '请先保存文件再导出 PDF。')
            return
        # 先 collect 确保最新值写入
        pane.collect()
        try:
            from app.core.docx_exporter import DocxExporter, get_template_path
            from app.core.pdf_exporter import PdfExporter, detect_engine, PdfEngine
            engine = detect_engine()
            if engine == PdfEngine.NONE:
                QMessageBox.warning(self, '无法导出',
                    '未检测到可用的 PDF 转换工具（WPS / Word / LibreOffice）。')
                return
            xing_ming = lrmx.get('XingMing') or '未命名'
            default_name = f'{xing_ming}_任免审批表.pdf'
            dest, _ = QFileDialog.getSaveFileName(
                self, '导出 PDF', default_name, 'PDF 文件 (*.pdf)')
            if not dest:
                return
            tpl = get_template_path()
            docx_bytes = DocxExporter(tpl).export_bytes(lrmx)
            with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as f:
                f.write(docx_bytes)
                tmp_docx = Path(f.name)
            try:
                pdf_exporter = PdfExporter()
                tmp_pdf = pdf_exporter.export(tmp_docx, tmp_docx.parent)
                shutil.copy(tmp_pdf, dest)
                tmp_pdf.unlink(missing_ok=True)
            finally:
                tmp_docx.unlink(missing_ok=True)
            QMessageBox.information(self, '导出成功', f'已保存至：\n{dest}')
        except Exception as e:
            QMessageBox.critical(self, '导出失败', str(e))

    def _on_print_btn(self) -> None:
        pane = self._active_pane()
        if pane is None:
            return
        lrmx = pane.lrmx()
        if lrmx is None:
            QMessageBox.information(self, '提示', '请先保存文件再打印。')
            return
        pane.collect()
        try:
            from app.core.docx_exporter import DocxExporter, get_template_path
            from app.core.pdf_exporter import PdfExporter, detect_engine, PdfEngine
            from app.ui.widgets.print_preview import PrintPreviewDialog
            engine = detect_engine()
            if engine == PdfEngine.NONE:
                QMessageBox.warning(self, '无法打印',
                    '未检测到可用的 PDF 转换工具（WPS / Word / LibreOffice）。')
                return
            tpl = get_template_path()
            docx_bytes = DocxExporter(tpl).export_bytes(lrmx)
            tmp_dir = Path(tempfile.gettempdir())
            tmp_docx = tmp_dir / f'.rmb_print_{id(self)}.docx'
            tmp_docx.write_bytes(docx_bytes)
            try:
                pdf_exporter = PdfExporter()
                tmp_pdf = pdf_exporter.export(tmp_docx, tmp_dir)
            finally:
                tmp_docx.unlink(missing_ok=True)
            # PrintPreviewDialog 负责在关闭后删除 tmp_pdf
            dlg = PrintPreviewDialog(tmp_pdf, self)
            dlg.exec()
        except Exception as e:
            QMessageBox.critical(self, '打印失败', str(e))

    # ── drag & drop ──────────────────────────────────────────────────────────

    def dragEnterEvent(self, ev) -> None:
        if ev.mimeData().hasUrls():
            if any(u.toLocalFile().lower().endswith('.lrmx')
                   for u in ev.mimeData().urls()):
                ev.acceptProposedAction()

    def dropEvent(self, ev) -> None:
        for url in ev.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith('.lrmx') and Path(path).is_file():
                self._open_path(path)
```

- [ ] **Step 2: 检查 pdf_exporter 的 export() 方法签名**

```bash
uv run python -c "
from app.core.pdf_exporter import PdfExporter, detect_engine
import inspect
print(inspect.signature(PdfExporter.export if hasattr(PdfExporter, 'export') else PdfExporter.__init__))
"
```

若 `PdfExporter.export` 签名不是 `(self, docx_path, output_dir) -> Path`，根据实际签名调整 `_on_export_pdf` 和 `_on_print_btn` 中的调用方式。

- [ ] **Step 3: 启动验证基本功能**

```bash
uv run python main.py
```

验证：
1. 切换到「任免表编辑器」tab
2. 点「打开」选择一个 .lrmx 文件 → 出现标签页，表单填满
3. 再点「打开」选同一文件 → 激活已有 tab，不新建
4. 再点「打开」选不同文件 → 新建第二个 tab
5. 从左侧文件树点击 → 新建 tab 或激活已有
6. 拖拽 .lrmx 文件到右侧内容区 → 新建 tab
7. 修改字段 → tab 标题显示 `*`
8. 点「保存」→ `*` 消失

- [ ] **Step 4: Commit**

```bash
git add app/ui/tabs/editor_tab.py
git commit -m "feat: 编辑器多标签页重构（_DocPane + QTabWidget + 工具栏完善 + 拖放）"
```

---

## Task 5：editorFormA QSS

**Files:**
- Modify: `app/ui/style.py`

为表格式布局（`QWidget#editorFormA`）增加 QSS，使标签和输入框呈现全格线外观。

- [ ] **Step 1: 在 style.py 末尾 `"""` 之前追加**

```css
/* ── 编辑器表格式布局 (editorFormA) ──────────────────────────── */
QWidget#editorFormA QLabel#tableLbl {{
    border: 0.5px solid #CECDCA;
    background: #F5F4F1;
    color: #555;
    font-size: 12px;
    padding: 2px 6px;
    min-height: {_ROW_H}px;
}}
QWidget#editorFormA QLabel#tableSecLbl {{
    border: 0.5px solid #CECDCA;
    background: #EEEDEA;
    color: #444;
    font-size: 11px;
    font-weight: bold;
    padding: 2px 6px;
    min-height: 20px;
}}
QWidget#editorFormA QLineEdit,
QWidget#editorFormA QComboBox {{
    border: 0.5px solid #CECDCA;
    border-radius: 0;
    padding: 2px 4px;
}}
QWidget#editorFormA QTextEdit {{
    border: 0.5px solid #CECDCA;
    border-radius: 0;
}}
```

注意：`{_ROW_H}` 是 Python 格式字符串变量（style.py 使用 `.format()` 渲染），应替换为字面量 `28`：

实际写入：
```css
    min-height: 28px;
```

- [ ] **Step 2: 验证**

`uv run python main.py` → 设置 → 编辑器布局切换为「严格表格式」→ 编辑器 tab 打开文件 → 确认出现格线、标签灰底、输入框直角。

- [ ] **Step 3: Commit**

```bash
git add app/ui/style.py
git commit -m "style: editorFormA 表格式布局 QSS（全格线 + 标签灰底）"
```

---

## Task 6：Settings 布局切换

**Files:**
- Modify: `app/ui/tabs/settings_tab.py`
- Modify: `app/ui/main_window.py`

### 6a. SettingsTab 增加布局选项

- [ ] **Step 1: 在 settings_tab.py 的 imports 区追加**

```python
from PySide6.QtWidgets import QRadioButton, QButtonGroup
```

- [ ] **Step 2: 在 `_build_ui` 方法末尾的 `layout.addStretch()` 之前追加**

```python
        # 编辑器布局
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep2)

        layout_label = QLabel('编辑器布局')
        layout_label.setObjectName('sectionTitle')
        layout.addWidget(layout_label)

        layout_row = QHBoxLayout()
        self._layout_b_btn = QRadioButton('轻量分隔式（默认）')
        self._layout_a_btn = QRadioButton('严格表格式')
        self._layout_group = QButtonGroup(self)
        self._layout_group.addButton(self._layout_b_btn, 0)
        self._layout_group.addButton(self._layout_a_btn, 1)
        layout_row.addWidget(self._layout_b_btn)
        layout_row.addWidget(self._layout_a_btn)
        layout_row.addStretch()
        layout.addLayout(layout_row)
        self._layout_group.idClicked.connect(self._on_layout_changed)
```

- [ ] **Step 3: 在 `_load` 方法末尾追加**

```python
        mode = self._settings.value('editor/layout_mode', 'b')
        if mode == 'a':
            self._layout_a_btn.setChecked(True)
        else:
            self._layout_b_btn.setChecked(True)
```

- [ ] **Step 4: 在 SettingsTab 类末尾追加方法和信号**

在类定义顶部（`__init__` 之前）增加信号：
```python
    layout_mode_changed = Signal(str)
```

在类末尾追加：
```python
    def _on_layout_changed(self, btn_id: int) -> None:
        mode = 'a' if btn_id == 1 else 'b'
        self._settings.setValue('editor/layout_mode', mode)
        self.layout_mode_changed.emit(mode)
```

### 6b. MainWindow 连接信号

- [ ] **Step 5: 在 main_window.py `_switch_tab` 中初始化 SettingsTab 的地方，增加信号连接**

找到：
```python
            else:
                from app.ui.tabs.settings_tab import SettingsTab
                tab = SettingsTab()
```
替换为：
```python
            else:
                from app.ui.tabs.settings_tab import SettingsTab
                tab = SettingsTab()
                tab.layout_mode_changed.connect(self._on_layout_mode_changed)
```

- [ ] **Step 6: 在 MainWindow 中追加方法**

```python
    def _on_layout_mode_changed(self, mode: str) -> None:
        editor = self._tab_widgets.get(4)
        if editor is not None and hasattr(editor, 'set_layout_mode'):
            editor.set_layout_mode(mode)
```

- [ ] **Step 7: 验证**

`uv run python main.py` → 打开一个 lrmx → 设置 → 切换「严格表格式」→ 切回编辑器 → 确认布局变化且字段值保留。

- [ ] **Step 8: Commit**

```bash
git add app/ui/tabs/settings_tab.py app/ui/main_window.py
git commit -m "feat: 设置页增加编辑器布局切换（轻量/表格式），实时应用到已开标签页"
```

---

## Task 7：MainWindow 自动折叠导航栏

**Files:**
- Modify: `app/ui/main_window.py`

- [ ] **Step 1: 在 `MainWindow.__init__` 的实例变量初始化区追加**

找到：
```python
        self._resizable: bool = True
```
在其后追加：
```python
        self._auto_collapsed_for_editor: bool = False
```

- [ ] **Step 2: 在 `_switch_tab` 方法末尾，`setMinimumSize` 调用之后追加自动折叠逻辑**

找到 `_switch_tab` 中的末尾段（在 `self._resizable = True` / `setMinimumSize` 之后），追加：

```python
        # 自动折叠：切入编辑器时折叠，切出时还原（仅针对「因编辑器而折叠」的情况）
        if index == 4 and not self._sidebar_collapsed:
            self._auto_collapsed_for_editor = True
            self.toggle_sidebar()
        elif prev == 4 and self._auto_collapsed_for_editor:
            self._auto_collapsed_for_editor = False
            self.toggle_sidebar()
```

- [ ] **Step 3: 验证**

`uv run python main.py` →
1. 侧边栏展开状态下切换到「任免表编辑器」→ 侧边栏自动折叠
2. 切换到其他 tab → 侧边栏自动展开
3. 手动折叠侧边栏后切换到编辑器 → 不被强制展开也不重复折叠
4. 折叠状态切出编辑器 → 侧边栏保持用户手动折叠的状态

- [ ] **Step 4: Commit**

```bash
git add app/ui/main_window.py
git commit -m "feat: 切换到编辑器 tab 时自动折叠导航栏，切出时自动还原"
```

---

## 自检清单

对照设计文档 `docs/superpowers/specs/2026-06-22-editor-enhancement-design.md`：

| 需求 | 任务 | 覆盖 |
|---|---|---|
| 选中颜色修复 | Task 1 | ✓ |
| docx 导出 bytes | Task 2 | ✓ |
| 打印预览对话框 | Task 3 | ✓ |
| 多标签页 + 拖放 + 打开多选 | Task 4 | ✓ |
| 无文件时保存 → save_as | Task 4（_DocPane.save） | ✓ |
| 导出 PDF 工具栏按钮 | Task 4（_on_export_pdf） | ✓ |
| 打印工具栏按钮 | Task 4（_on_print_btn） | ✓ |
| 严格表格式布局 | Task 4（_build_layout_a）+ Task 5 | ✓ |
| 设置页布局切换 | Task 6 | ✓ |
| 自动折叠导航栏 | Task 7 | ✓ |
