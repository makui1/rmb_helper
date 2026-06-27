import json
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListWidget, QListWidgetItem,
    QInputDialog, QMessageBox, QScrollArea, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
    QDialog, QLineEdit, QRadioButton, QButtonGroup,
    QPlainTextEdit, QApplication,
)
from PySide6.QtCore import QSettings, Qt, QSize
from PySide6.QtGui import QIcon
from app.utils.naming import PRESETS
from app.core.verify_handler import LRMX_FIELDS, DEFAULT_FIELD_ALIASES
from app.core import file_assoc
from app.core.compare_rules import CompareRule, rules_to_json, rules_from_json, validate_date_format, validate_regex_pattern
from app.core.converters import get_all_converters, save_custom_converters, execute_converter
from app.ui.utils import show_error, show_warning

_ASSETS = Path(__file__).parent.parent / 'assets'


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
        hint_lbl = QLabel('等价格式列表（双击编辑，点 ＋ 新增）')
        hint_lbl.setStyleSheet('color: #555; font-size: 12px;')
        dv.addWidget(hint_lbl)

        fmt_row = QHBoxLayout()
        self._fmt_list = QListWidget()
        self._fmt_list.setFixedHeight(120)
        self._fmt_list.setEditTriggers(QListWidget.EditTrigger.DoubleClicked)
        fmt_row.addWidget(self._fmt_list, 1)

        fmt_btns = QVBoxLayout()
        add_fmt_btn = QPushButton()
        add_fmt_btn.setIcon(QIcon(str(_ASSETS / 'add-btn.svg')))
        add_fmt_btn.setIconSize(QSize(16, 16))
        add_fmt_btn.setToolTip('新增格式')
        add_fmt_btn.setFixedSize(28, 28)
        add_fmt_btn.clicked.connect(self._add_format)
        del_fmt_btn = QPushButton()
        del_fmt_btn.setIcon(QIcon(str(_ASSETS / 'delete-btn.svg')))
        del_fmt_btn.setIconSize(QSize(16, 16))
        del_fmt_btn.setToolTip('删除格式')
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


class _ConverterDialog(QDialog):
    """转换器编辑弹窗（新建/编辑），替代内联编辑器。"""

    def __init__(self, converter: dict | None = None, existing_names: list[str] | None = None,
                 parent=None):
        super().__init__(parent)
        self._initial = converter
        self._existing_names = existing_names or []
        self._result: dict | None = None
        self.setWindowTitle('编辑转换器' if converter else '新增转换器')
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)
        self._build_ui()
        if converter:
            self._load(converter)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel('名称'))
        self._name_edit = QLineEdit()
        name_row.addWidget(self._name_edit)
        layout.addLayout(name_row)

        code_row = QHBoxLayout()
        code_label = QLabel('代码（必须定义 convert(value: str) -> str 函数）')
        code_row.addWidget(code_label, 1)
        ai_btn = QPushButton('📋 复制AI提示词示例')
        ai_btn.setToolTip('将转换器编写提示词复制到剪贴板，可粘贴到 AI 对话中生成代码')
        ai_btn.setStyleSheet('color: #D85A30; font-size: 12px;')
        ai_btn.clicked.connect(self._copy_ai_prompt)
        code_row.addWidget(ai_btn)
        layout.addLayout(code_row)

        self._code_edit = QPlainTextEdit()
        self._code_edit.setPlaceholderText(
            'def convert(value: str) -> str:\n'
            '    # 在此编写转换逻辑\n'
            '    return value'
        )
        self._code_edit.setMinimumHeight(150)
        self._code_edit.setStyleSheet(
            'font-family: "Cascadia Code", "Consolas", monospace; font-size: 13px;'
        )
        layout.addWidget(self._code_edit, 1)

        # 测试行
        test_row = QHBoxLayout()
        test_row.addWidget(QLabel('测试'))
        self._test_input = QLineEdit()
        self._test_input.setPlaceholderText('输入测试值…')
        self._test_input.textChanged.connect(self._on_test)
        test_row.addWidget(self._test_input, 1)
        test_row.addWidget(QLabel('→'))
        self._test_result = QLabel('（结果）')
        self._test_result.setStyleSheet('color: #1E7A3A; font-weight: bold;')
        test_row.addWidget(self._test_result)
        layout.addLayout(test_row)

        # 错误提示
        self._error_lbl = QLabel('')
        self._error_lbl.setStyleSheet('color: #B02020; font-size: 11px;')
        self._error_lbl.hide()
        layout.addWidget(self._error_lbl)

        # 保存/取消
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

    def _copy_ai_prompt(self):
        """将 AI 提示词示例复制到剪贴板。"""
        prompt = (
            '请帮我写一个 Python 转换函数，用于将任免表（LRMX）字段值转换为名册（Excel）中的目标格式。\n'
            '\n'
            '要求：\n'
            '1. 必须定义一个名为 convert 的函数，签名固定为：def convert(value: str) -> str\n'
            '2. 输入 value 是任免表中的原始字段值（字符串类型）\n'
            '3. 返回值是转换后写入 Excel 的值（也必须是字符串）\n'
            '4. 只使用 Python 内置函数，不能导入第三方库\n'
            '5. 如果转换失败或值为空，直接返回原值 value\n'
            '\n'
            '我的转换需求：【在这里用自然语言描述你的转换逻辑，例如：\n'
            '  - "把日期从 yyyyMMdd 格式转为 yyyy.MM.dd 格式"\n'
            '  - "把性别字段的"男"转为"1"，"女"转为"2""\n'
            '  - "去掉身份证号中的空格和特殊字符"\n'
            '  - "把籍贯中的省市简称替换为全称，如"京"→"北京""\n'
            '】\n'
            '\n'
            '以下是系统内置的转换器示例，可供参考：\n'
            '━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
            '# 示例1：日期格式转换 yyyyMM → yyyy.MM\n'
            'def convert(value: str) -> str:\n'
            '    v = value.strip()\n'
            '    if len(v) == 6 and v.isdigit():\n'
            '        return f"{v[:4]}.{v[4:]}"\n'
            '    return value\n'
            '\n'
            '# 示例2：性别映射 男→1 女→0\n'
            'def convert(value: str) -> str:\n'
            '    v = value.strip()\n'
            '    if v in ("男", "男性"):\n'
            '        return "1"\n'
            '    elif v in ("女", "女性"):\n'
            '        return "0"\n'
            '    return value\n'
            '\n'
            '# 示例3：去除所有空格\n'
            'def convert(value: str) -> str:\n'
            '    return value.replace(" ", "").replace("\\u3000", "")\n'
            '━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
            '\n'
            '请根据我的需求写出对应的 convert 函数，只输出代码，不需要额外解释。'
        )
        QApplication.clipboard().setText(prompt)
        QMessageBox.information(
            self, '已复制',
            'AI 提示词已复制到剪贴板。\n\n'
            '打开任意 AI 工具（如 ChatGPT、Claude、通义千问等），\n'
            '粘贴后替换【我的转换需求】部分，即可生成转换器代码。'
        )

    def _load(self, converter: dict):
        self._name_edit.setText(converter.get('name', ''))
        self._code_edit.setPlainText(converter.get('code', ''))

    def _save(self):
        name = self._name_edit.text().strip()
        code = self._code_edit.toPlainText().strip()
        if not name:
            self._show_error('名称不能为空')
            return
        if not code:
            self._show_error('代码不能为空')
            return
        if 'def convert' not in code:
            self._show_error('代码中必须包含 def convert 函数定义')
            return
        # 验证语法
        try:
            compile(code, '<converter>', 'exec')
        except SyntaxError as e:
            self._show_error(f'语法错误: {e}')
            return

        # 检查重名
        if name in self._existing_names:
            self._show_error(f'名称「{name}」已被使用')
            return

        self._error_lbl.hide()
        self._result = {'name': name, 'code': code, 'builtin': False}
        self.accept()

    def _show_error(self, msg: str):
        self._error_lbl.setText(msg)
        self._error_lbl.show()

    def _on_test(self, text: str):
        if not text:
            self._test_result.setText('（结果）')
            self._test_result.setStyleSheet('color: #1E7A3A; font-weight: bold;')
            return
        code = self._code_edit.toPlainText().strip()
        if not code:
            return
        try:
            result = execute_converter(code, text)
            self._test_result.setText(result)
            self._test_result.setStyleSheet('color: #1E7A3A; font-weight: bold;')
        except Exception as e:
            self._test_result.setText(f'错误: {e}')
            self._test_result.setStyleSheet('color: #B02020;')

    def result(self) -> dict | None:
        return self._result


class SettingsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._settings = QSettings('rmb_helper', 'rmb_helper')
        self._build_ui()
        self._load()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        cv = QVBoxLayout(content)
        cv.setContentsMargins(24, 20, 24, 20)
        cv.setSpacing(16)

        # ═══════════════════════════════════════════════════════════════════════
        # QTabWidget — 三个子标签页
        # ═══════════════════════════════════════════════════════════════════════
        tabs = QTabWidget()

        # ── Tab 0: 通用 ─────────────────────────────────────────────────────
        tab_general = QWidget()
        tg = QVBoxLayout(tab_general)
        tg.setContentsMargins(16, 16, 16, 16)
        tg.setSpacing(16)

        rule_label = QLabel('命名规则预设')
        rule_label.setObjectName('sectionTitle')
        tg.addWidget(rule_label)

        rule_sub = QLabel('任免表文件命名模板，可用字段：{XingMing} {ShenFenZheng} {XianRenZhiWu} 等')
        rule_sub.setStyleSheet('color: #888880; font-size: 12px;')
        rule_sub.setWordWrap(True)
        tg.addWidget(rule_sub)

        self._rule_list = QListWidget()
        self._rule_list.setObjectName('fileList')
        self._rule_list.setMaximumHeight(200)
        tg.addWidget(self._rule_list)

        rule_btns = QHBoxLayout()
        self._add_rule_btn = QPushButton()
        self._add_rule_btn.setIcon(QIcon(str(_ASSETS / 'add-btn.svg')))
        self._add_rule_btn.setIconSize(QSize(16, 16))
        self._add_rule_btn.setToolTip('新增规则')
        self._add_rule_btn.setFixedSize(28, 28)
        self._add_rule_btn.clicked.connect(self._add_rule)
        self._edit_rule_btn = QPushButton()
        self._edit_rule_btn.setIcon(QIcon(str(_ASSETS / 'edit.svg')))
        self._edit_rule_btn.setIconSize(QSize(16, 16))
        self._edit_rule_btn.setToolTip('编辑规则')
        self._edit_rule_btn.setFixedSize(28, 28)
        self._edit_rule_btn.clicked.connect(self._edit_rule)
        self._del_rule_btn = QPushButton()
        self._del_rule_btn.setIcon(QIcon(str(_ASSETS / 'delete-btn.svg')))
        self._del_rule_btn.setIconSize(QSize(16, 16))
        self._del_rule_btn.setToolTip('删除规则')
        self._del_rule_btn.setFixedSize(28, 28)
        self._del_rule_btn.clicked.connect(self._delete_rule)
        rule_btns.addWidget(self._add_rule_btn)
        rule_btns.addWidget(self._edit_rule_btn)
        rule_btns.addWidget(self._del_rule_btn)
        rule_btns.addStretch()
        tg.addLayout(rule_btns)

        # 文件关联（仅 Windows）
        if file_assoc.supported():
            tg.addSpacing(12)
            assoc_sep = QFrame()
            assoc_sep.setFrameShape(QFrame.Shape.HLine)
            tg.addWidget(assoc_sep)

            assoc_label = QLabel('文件关联')
            assoc_label.setObjectName('sectionTitle')
            tg.addWidget(assoc_label)

            assoc_sub = QLabel('关联后，在资源管理器中双击 .lrmx 文件即可用本工具打开。仅影响当前用户，无需管理员权限。')
            assoc_sub.setStyleSheet('color: #888880; font-size: 12px;')
            assoc_sub.setWordWrap(True)
            tg.addWidget(assoc_sub)

            assoc_row = QHBoxLayout()
            self._assoc_btn = QPushButton()
            self._assoc_btn.clicked.connect(self._toggle_assoc)
            assoc_row.addWidget(self._assoc_btn)
            assoc_row.addStretch()
            tg.addLayout(assoc_row)
            self._refresh_assoc_btn()

        tg.addStretch()
        tabs.addTab(tab_general, '通用')

        # ── Tab 1: 核验 ─────────────────────────────────────────────────────
        tab_verify = QWidget()
        tv = QVBoxLayout(tab_verify)
        tv.setContentsMargins(16, 16, 16, 16)
        tv.setSpacing(16)

        alias_label = QLabel('核验字段自动匹配')
        alias_label.setObjectName('sectionTitle')
        tv.addWidget(alias_label)

        alias_sub = QLabel('加载 Excel 文件后，自动将匹配的表头映射到对应任免表字段。多个关键词用逗号分隔。')
        alias_sub.setStyleSheet('color: #888880; font-size: 12px;')
        alias_sub.setWordWrap(True)
        tv.addWidget(alias_sub)

        self._alias_table = QTableWidget(len(LRMX_FIELDS), 3)
        self._alias_table.setHorizontalHeaderLabels(['字段名', '任免表字段', 'Excel 匹配关键词（逗号分隔）'])
        self._alias_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._alias_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._alias_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._alias_table.verticalHeader().setVisible(False)
        self._alias_table.setMinimumHeight(300)
        for i, (tag, display) in enumerate(LRMX_FIELDS):
            display_item = QTableWidgetItem(display)
            display_item.setFlags(display_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            tag_item = QTableWidgetItem(tag)
            tag_item.setFlags(tag_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            tag_item.setForeground(Qt.GlobalColor.gray)
            aliases = DEFAULT_FIELD_ALIASES.get(tag, [])
            alias_item = QTableWidgetItem(', '.join(aliases))
            self._alias_table.setItem(i, 0, display_item)
            self._alias_table.setItem(i, 1, tag_item)
            self._alias_table.setItem(i, 2, alias_item)
        tv.addWidget(self._alias_table)

        tv.addSpacing(8)
        cr_sep = QFrame()
        cr_sep.setFrameShape(QFrame.Shape.HLine)
        tv.addWidget(cr_sep)

        cr_title = QLabel('比较规则')
        cr_title.setObjectName('sectionTitle')
        tv.addWidget(cr_title)

        cr_sub = QLabel('核验时可为每个字段指定比较规则，允许格式不同但语义相同的值被判定为一致。')
        cr_sub.setStyleSheet('color: #888880; font-size: 12px;')
        cr_sub.setWordWrap(True)
        tv.addWidget(cr_sub)

        self._compare_rule_list = QListWidget()
        self._compare_rule_list.setMaximumHeight(200)
        self._compare_rule_list.currentRowChanged.connect(self._refresh_rule_btns)
        tv.addWidget(self._compare_rule_list)

        rule_btn_row = QHBoxLayout()
        self._add_cr_btn = QPushButton()
        self._add_cr_btn.setIcon(QIcon(str(_ASSETS / 'add-btn.svg')))
        self._add_cr_btn.setIconSize(QSize(16, 16))
        self._add_cr_btn.setToolTip('新增规则')
        self._add_cr_btn.setFixedSize(28, 28)
        self._add_cr_btn.clicked.connect(self._add_compare_rule)
        self._edit_cr_btn = QPushButton()
        self._edit_cr_btn.setIcon(QIcon(str(_ASSETS / 'edit.svg')))
        self._edit_cr_btn.setIconSize(QSize(16, 16))
        self._edit_cr_btn.setToolTip('编辑规则')
        self._edit_cr_btn.setFixedSize(28, 28)
        self._edit_cr_btn.setEnabled(False)
        self._edit_cr_btn.clicked.connect(self._edit_compare_rule)
        self._del_cr_btn = QPushButton()
        self._del_cr_btn.setIcon(QIcon(str(_ASSETS / 'delete-btn.svg')))
        self._del_cr_btn.setIconSize(QSize(16, 16))
        self._del_cr_btn.setToolTip('删除规则')
        self._del_cr_btn.setFixedSize(28, 28)
        self._del_cr_btn.setEnabled(False)
        self._del_cr_btn.clicked.connect(self._delete_compare_rule)
        rule_btn_row.addWidget(self._add_cr_btn)
        rule_btn_row.addWidget(self._edit_cr_btn)
        rule_btn_row.addWidget(self._del_cr_btn)
        rule_btn_row.addStretch()
        tv.addLayout(rule_btn_row)

        tv.addStretch()
        tabs.addTab(tab_verify, '核验')

        # ── Tab 2: 转换器 ───────────────────────────────────────────────────
        tab_conv = QWidget()
        tc = QVBoxLayout(tab_conv)
        tc.setContentsMargins(16, 16, 16, 16)
        tc.setSpacing(16)

        conv_title = QLabel('转换器管理')
        conv_title.setObjectName('sectionTitle')
        tc.addWidget(conv_title)

        conv_sub = QLabel(
            'LRMX→Excel 更新时可选用转换器对字段值进行格式转换。'
            '内置转换器不可编辑删除。自定义转换器可编写 Python 代码。'
        )
        conv_sub.setStyleSheet('color: #888880; font-size: 12px;')
        conv_sub.setWordWrap(True)
        tc.addWidget(conv_sub)

        self._converter_list = QListWidget()
        self._converter_list.setMaximumHeight(250)
        self._converter_list.currentRowChanged.connect(self._on_converter_selected)
        tc.addWidget(self._converter_list)

        conv_btn_row = QHBoxLayout()
        self._add_conv_btn = QPushButton()
        self._add_conv_btn.setIcon(QIcon(str(_ASSETS / 'add-btn.svg')))
        self._add_conv_btn.setIconSize(QSize(16, 16))
        self._add_conv_btn.setToolTip('新建转换器')
        self._add_conv_btn.setFixedSize(28, 28)
        self._add_conv_btn.clicked.connect(self._add_converter)
        self._edit_conv_btn = QPushButton()
        self._edit_conv_btn.setIcon(QIcon(str(_ASSETS / 'edit.svg')))
        self._edit_conv_btn.setIconSize(QSize(16, 16))
        self._edit_conv_btn.setToolTip('编辑转换器')
        self._edit_conv_btn.setFixedSize(28, 28)
        self._edit_conv_btn.setEnabled(False)
        self._edit_conv_btn.clicked.connect(self._edit_converter)
        self._del_conv_btn = QPushButton()
        self._del_conv_btn.setIcon(QIcon(str(_ASSETS / 'delete-btn.svg')))
        self._del_conv_btn.setIconSize(QSize(16, 16))
        self._del_conv_btn.setToolTip('删除转换器')
        self._del_conv_btn.setFixedSize(28, 28)
        self._del_conv_btn.setEnabled(False)
        self._del_conv_btn.clicked.connect(self._delete_converter)
        conv_btn_row.addWidget(self._add_conv_btn)
        conv_btn_row.addWidget(self._edit_conv_btn)
        conv_btn_row.addWidget(self._del_conv_btn)
        conv_btn_row.addStretch()
        tc.addLayout(conv_btn_row)

        tc.addStretch()
        tabs.addTab(tab_conv, '转换器')

        # ═══════════════════════════════════════════════════════════════════════

        cv.addWidget(tabs)

        # 保存 / 恢复默认（在 QScrollArea 之外，始终可见）
        save_row = QHBoxLayout()
        reset_btn = QPushButton('恢复默认设置')
        reset_btn.setToolTip('清除所有设置并恢复为默认值')
        reset_btn.clicked.connect(self._reset_defaults)
        save_row.addWidget(reset_btn)
        save_row.addStretch()
        save_btn = QPushButton('保存设置')
        save_btn.setObjectName('primary')
        save_btn.clicked.connect(self._save)
        save_row.addWidget(save_btn)
        cv.addLayout(save_row)

        scroll.setWidget(content)
        layout.addWidget(scroll)

    def _refresh_assoc_btn(self):
        registered = file_assoc.is_registered()
        self._assoc_btn.setText('取消关联 .lrmx 文件' if registered else '关联 .lrmx 文件')
        self._assoc_btn.setObjectName('' if registered else 'primary')
        # 切换 objectName 后需 unpolish/polish 才能刷新外观
        self._assoc_btn.style().unpolish(self._assoc_btn)
        self._assoc_btn.style().polish(self._assoc_btn)

    def _toggle_assoc(self):
        try:
            if file_assoc.is_registered():
                file_assoc.unregister()
                QMessageBox.information(self, '已取消关联', '已取消 .lrmx 文件关联。')
            else:
                file_assoc.register()
                QMessageBox.information(
                    self, '关联成功',
                    '已关联 .lrmx 文件。\n现在双击 .lrmx 文件即可用本工具打开。')
        except Exception as e:
            show_error(self, f'修改文件关联失败：\n{e}')
        self._refresh_assoc_btn()

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
        rules = self._settings.value('naming_rules', [p[0] for p in PRESETS])
        if isinstance(rules, str):
            rules = [rules]
        self._rule_list.clear()
        for r in rules:
            self._rule_list.addItem(r)

        raw = self._settings.value('verify_field_aliases', '')
        if raw:
            try:
                stored: dict[str, str] = json.loads(raw)
            except Exception:
                stored = {}
            for i, (tag, _) in enumerate(LRMX_FIELDS):
                if tag in stored:
                    item = self._alias_table.item(i, 2)
                    if item:
                        item.setText(stored[tag])

        raw_cr = self._settings.value('compare_rules', '')
        self._compare_rules: list[CompareRule] = rules_from_json(raw_cr)
        self._refresh_compare_rule_list()

        self._load_converters()

    def _save(self):
        rules = [self._rule_list.item(i).text() for i in range(self._rule_list.count())]
        self._settings.setValue('naming_rules', rules)

        aliases: dict[str, str] = {}
        for i, (tag, _) in enumerate(LRMX_FIELDS):
            item = self._alias_table.item(i, 2)
            val = item.text().strip() if item else ''
            if val:
                aliases[tag] = val
        self._settings.setValue('verify_field_aliases', json.dumps(aliases, ensure_ascii=False))

        self._settings.setValue('compare_rules', rules_to_json(self._compare_rules))

        QMessageBox.information(self, '保存成功', '设置已保存。')

    def _reset_defaults(self):
        reply = QMessageBox.warning(
            self, '恢复默认设置',
            '确定要恢复所有设置为默认值吗？\n\n'
            '此操作将清除：\n'
            '  · 命名规则预设\n'
            '  · 核验字段自动匹配关键词\n'
            '  · 比较规则\n'
            '  · 自定义转换器\n\n'
            '此操作不可撤销。',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._settings.clear()
        self._settings.sync()
        self._load()
        QMessageBox.information(self, '已恢复', '所有设置已恢复为默认值。')

    def naming_rules(self) -> list[str]:
        return [self._rule_list.item(i).text() for i in range(self._rule_list.count())]

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

    # ── 转换器管理 ────────────────────────────────────────────────────────

    def _load_converters(self):
        self._all_converters: list[dict] = get_all_converters(self._settings)
        self._refresh_converter_list()

    def _refresh_converter_list(self):
        self._converter_list.clear()
        for c in self._all_converters:
            prefix = '🔒 ' if c.get('builtin') else '✏ '
            self._converter_list.addItem(f'{prefix}{c["name"]}')
        self._on_converter_selected(self._converter_list.currentRow())

    def _on_converter_selected(self, row: int):
        if row < 0:
            self._edit_conv_btn.setEnabled(False)
            self._del_conv_btn.setEnabled(False)
            return
        is_builtin = self._all_converters[row].get('builtin', False)
        self._edit_conv_btn.setEnabled(not is_builtin)
        self._del_conv_btn.setEnabled(not is_builtin)

    def _add_converter(self):
        existing = [c['name'] for c in self._all_converters]
        dlg = _ConverterDialog(existing_names=existing, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            conv = dlg.result()
            if conv:
                self._all_converters.append(conv)
                self._persist_converters()
                self._refresh_converter_list()

    def _edit_converter(self):
        row = self._converter_list.currentRow()
        if row < 0:
            return
        c = self._all_converters[row]
        if c.get('builtin'):
            return
        existing = [c2['name'] for i, c2 in enumerate(self._all_converters) if i != row]
        dlg = _ConverterDialog(converter=c, existing_names=existing, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            conv = dlg.result()
            if conv:
                self._all_converters[row] = conv
                self._persist_converters()
                self._refresh_converter_list()

    def _delete_converter(self):
        row = self._converter_list.currentRow()
        if row < 0:
            return
        c = self._all_converters[row]
        if c.get('builtin'):
            return
        reply = QMessageBox.question(
            self, '确认删除', f'确定删除转换器「{c["name"]}」吗？',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._all_converters.pop(row)
            self._persist_converters()
            self._refresh_converter_list()

    def _persist_converters(self):
        save_custom_converters(self._settings, self._all_converters)
