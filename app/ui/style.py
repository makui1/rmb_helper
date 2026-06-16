from pathlib import Path

ACCENT = '#D85A30'
ACCENT_LIGHT = 'rgba(216, 90, 48, 0.10)'
ACCENT_HOVER = '#C04E28'

_ASSETS = (Path(__file__).parent / 'assets').as_posix()

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

/* ── 自定义标题栏 ───────────────────────────────────────────────────── */
QWidget#titleBar {{
    background-color: #F0EFEb;
    border-bottom: 0.5px solid #E0DDD6;
}}
QPushButton#winBtn {{
    border: none;
    background: transparent;
    color: #888880;
    font-size: 16px;
    padding: 0;
    border-radius: 4px;
}}
QPushButton#winBtn:hover {{
    background-color: #E0DDD6;
    color: #1A1A1A;
}}
QPushButton#winBtnClose {{
    border: none;
    background: transparent;
    color: #888880;
    font-size: 16px;
    padding: 0;
    border-radius: 4px;
}}
QPushButton#winBtnClose:hover {{
    background-color: #E05040;
    color: #FFFFFF;
}}
QLabel#titleBarAppName {{
    color: #555550;
    font-size: 13px;
    font-weight: 500;
    background: transparent;
}}
QFrame#titleBarSep {{
    color: #D0CEC8;
    background-color: #D0CEC8;
}}

/* ── 侧边栏外层容器：透明，仅提供 margin ────────────────────────────── */
QWidget#sidebarContainer {{
    background: transparent;
}}

/* ── 侧边栏卡片：圆角矩形，浮于白色窗口背景上 ──────────────────────── */
QWidget#sidebar {{
    background-color: #F5F4F1;
    border-radius: 10px;
    border: 0.5px solid #E0DDD6;
}}

QPushButton#navBtn {{
    border: none;
    border-radius: 6px;
    text-align: left;
    padding: 7px 10px;
    margin: 1px 6px;
    color: #555550;
    background-color: transparent;
    font-size: 13px;
}}
QPushButton#navBtn:checked {{
    background-color: {ACCENT_LIGHT};
    color: {ACCENT};
    font-weight: 500;
}}
QPushButton#navBtn:hover:!checked {{
    background-color: #EEEDE8;
    color: #1A1A1A;
}}

/* ── Tooltip ────────────────────────────────────────────────────────── */
QToolTip {{
    background-color: #FAFAF8;
    color: #333330;
    border: 0.5px solid #D0CEC8;
    padding: 6px 10px;
    font-size: 12px;
    font-family: "Microsoft YaHei UI", "PingFang SC", sans-serif;
}}

/* ── 输入框 ─────────────────────────────────────────────────────────── */
QLineEdit, QTextEdit {{
    border: 0.5px solid #D0CEC8;
    border-radius: 6px;
    padding: 4px 8px;
    background-color: #FFFFFF;
    color: #1A1A1A;
    selection-background-color: {ACCENT_LIGHT};
}}
QLineEdit:focus, QTextEdit:focus {{
    border-color: {ACCENT};
}}
QLineEdit:read-only {{
    background-color: #F5F4F1;
    color: #888880;
}}

/* ── 按钮 ───────────────────────────────────────────────────────────── */
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

/* ── 下拉框 ─────────────────────────────────────────────────────────── */
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

/* ── 复选框：白底 + 橙色钩 ──────────────────────────────────────────── */
QCheckBox::indicator {{
    width: 15px;
    height: 15px;
    border: 1px solid #C0BEB8;
    border-radius: 3px;
    background-color: #FFFFFF;
}}
QCheckBox::indicator:hover {{
    border-color: {ACCENT};
}}
QCheckBox::indicator:checked {{
    background-color: #FFFFFF;
    border-color: {ACCENT};
    image: url({_ASSETS}/checkmark.svg);
}}

/* ── 单选框 ─────────────────────────────────────────────────────────── */
QRadioButton::indicator {{
    width: 8px;
    height: 8px;
    border: 1px solid #C0BEB8;
    border-radius: 4px;
    background-color: #FFFFFF;
}}
QRadioButton::indicator:checked {{
    background-color: {ACCENT};
    border-color: {ACCENT};
}}

/* ── 列表项复选框（字段选择列表） ───────────────────────────────────── */
QListWidget::indicator {{
    width: 15px;
    height: 15px;
    border: 1px solid #C0BEB8;
    border-radius: 3px;
    background-color: #FFFFFF;
}}
QListWidget::indicator:hover {{
    border-color: {ACCENT};
}}
QListWidget::indicator:checked {{
    background-color: #FFFFFF;
    border-color: {ACCENT};
    image: url({_ASSETS}/checkmark.svg);
}}

/* ── 文件列表：无边框，行间距由 _FileRow 的分割线承担 ─────────────────── */
QListWidget#fileList {{
    border: 1px solid #C0BEB8;
    border-radius: 6px;
    background-color: transparent;
    outline: none;
}}
QListWidget#fileList::item {{
    padding: 0;
    border-radius: 0;
}}
QListWidget#fileList::item:selected {{
    background-color: {ACCENT_LIGHT};
    color: {ACCENT};
}}

/* 文件行内的标签和 × 按钮 */
QLabel#fileItemName {{
    color: #333330;
    font-size: 13px;
    background: transparent;
}}
QPushButton#fileItemRemove {{
    border: none;
    background: transparent;
    color: #BBBBBB;
    font-size: 16px;
    font-weight: bold;
    padding: 0;
}}
QPushButton#fileItemRemove:hover {{
    color: {ACCENT};
    background: transparent;
}}

/* 拖放提示文字 */
QLabel#dropHint {{
    color: #BBBBBB;
    font-size: 12px;
    padding: 4px 0 8px 0;
    background: transparent;
}}

/* ── 日志筛选按钮 ───────────────────────────────────────────────────── */
QPushButton#logFilterBtn {{
    border: 0.5px solid #D0CEC8;
    border-radius: 4px;
    padding: 1px 10px;
    font-size: 12px;
    background-color: transparent;
    color: #888880;
}}
QPushButton#logFilterBtn:checked {{
    background-color: #F0EEE8;
    color: #333330;
    border-color: #B0AEA8;
}}
QPushButton#logFilterBtn:hover:!checked {{
    background-color: #F5F4F1;
}}

/* ── 日志区域 ────────────────────────────────────────────────────────── */
QTextEdit#logView {{
    background-color: #F5F4F1;
    border: 0.5px solid #D0CEC8;
    border-radius: 6px;
    font-family: "Cascadia Code", "Consolas", "Courier New", monospace;
    font-size: 12px;
    color: #444440;
    padding: 6px;
}}

/* ── Loading 对话框 ──────────────────────────────────────────────────── */
QDialog#loadingDialog {{
    background-color: #FFFFFF;
    border: 0.5px solid #D0CEC8;
    border-radius: 10px;
}}
QLabel#loadingLabel {{
    color: #555550;
    font-size: 13px;
}}
QProgressBar#loadingBar {{
    border: none;
    border-radius: 2px;
    background-color: #E8E6E0;
}}
QProgressBar#loadingBar::chunk {{
    background-color: {ACCENT};
    border-radius: 2px;
}}

/* ── 下拉菜单 ───────────────────────────────────────────────────────── */
QMenu {{
    background-color: #FFFFFF;
    border: 0.5px solid #D0CEC8;
    border-radius: 6px;
    padding: 4px 0;
}}
QMenu::item {{
    padding: 6px 20px;
    color: #333330;
    font-size: 13px;
}}
QMenu::item:selected {{
    background-color: {ACCENT_LIGHT};
    color: {ACCENT};
}}

/* ── 分割线 ─────────────────────────────────────────────────────────── */
QFrame[frameShape="4"],
QFrame[frameShape="5"] {{
    color: #E0DDD6;
}}

/* ── 标签 ───────────────────────────────────────────────────────────── */
QLabel {{
    background: transparent;
    color: #555550;
}}
QLabel#sectionTitle {{
    font-size: 14px;
    font-weight: 500;
    color: #1A1A1A;
}}
QLabel#pdfHint {{
    color: #C07030;
    font-size: 12px;
    background: transparent;
}}

/* ── 滚动条 ─────────────────────────────────────────────────────────── */
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
QScrollBar:horizontal {{
    border: none;
    background: transparent;
    height: 6px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: #C0BEB8;
    border-radius: 3px;
    min-width: 20px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* ── 批量核验标签和元素 ──────────────────────────────────────────────── */
QLabel#matchTag {{
    background: #1a3a5c;
    color: #7bb3e8;
    border: 1px solid #2d5a8e;
    border-radius: 10px;
    padding: 3px 10px;
    font-size: 12px;
}}
QLabel#matchTag:hover {{
    background: #1f4470;
    border-color: #4a80c0;
}}
QLabel#matchTag[selected="true"] {{
    background: #1e4a7a;
    color: #c8e0ff;
    border-color: #4a90d4;
    border-width: 2px;
}}
QWidget#fieldRow {{
    background: #242424;
    border: 1px solid transparent;
    border-radius: 4px;
}}
QWidget#fieldRow:hover {{
    border-color: #2d5a8e;
}}
QWidget#fieldRow[pending="true"] {{
    border-color: #3a5070;
}}
QLabel#fieldRowName {{
    color: #ccc;
    font-size: 11px;
}}
QLabel#fieldRowMapped {{
    color: #5db880;
    font-size: 11px;
    background: #1a3a24;
    border: 1px solid #2d6a4f;
    border-radius: 8px;
    padding: 1px 6px;
}}
QLabel#fieldRowUnmapped {{
    color: #555;
    font-size: 11px;
    font-style: italic;
}}
QWidget#summaryCard {{
    background: #1e1e1e;
    border: 1px solid #2a2a2a;
    border-radius: 5px;
}}
QWidget#resultRowHeader:hover {{
    background: #1e2530;
}}
QLabel#resultArrow {{
    color: #555;
    font-size: 11px;
}}
QLabel#resultName {{
    color: #ccc;
    font-weight: 600;
}}
QTextEdit#diffDetail {{
    background: #111518;
    border: none;
    border-radius: 0;
    font-size: 12px;
}}
QFrame#resultSep {{
    color: #1e1e1e;
    background: #1e1e1e;
    max-height: 1px;
}}
QScrollArea#resultScroll {{
    border: none;
    background: transparent;
}}
"""
