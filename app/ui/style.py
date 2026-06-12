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
