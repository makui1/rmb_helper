import json
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListWidget, QListWidgetItem,
    QInputDialog, QMessageBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
    QDialog, QLineEdit, QRadioButton, QButtonGroup,
)
from PySide6.QtCore import QSettings, Qt, QSize
from PySide6.QtGui import QIcon
from app.utils.naming import PRESETS
from app.core.verify_handler import LRMX_FIELDS, DEFAULT_FIELD_ALIASES
from app.core import file_assoc
from app.core.compare_rules import CompareRule, rules_to_json, rules_from_json, validate_date_format, validate_regex_pattern

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

        # 核验字段自动匹配
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep)

        alias_label = QLabel('核验字段自动匹配')
        alias_label.setObjectName('sectionTitle')
        layout.addWidget(alias_label)

        alias_sub = QLabel('加载 Excel 文件后，自动将匹配的表头映射到对应任免表字段。多个关键词用逗号分隔。')
        alias_sub.setStyleSheet('color: #888880; font-size: 12px;')
        alias_sub.setWordWrap(True)
        layout.addWidget(alias_sub)

        self._alias_table = QTableWidget(len(LRMX_FIELDS), 3)
        self._alias_table.setHorizontalHeaderLabels(['字段名', '任免表字段', 'Excel 匹配关键词（逗号分隔）'])
        self._alias_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._alias_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._alias_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._alias_table.verticalHeader().setVisible(False)
        self._alias_table.setMinimumHeight(240)
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
        layout.addWidget(self._alias_table)

        save_btn = QPushButton('保存设置')
        save_btn.setObjectName('primary')
        save_btn.clicked.connect(self._save)
        layout.addWidget(save_btn)

        # 文件关联（仅 Windows）
        if file_assoc.supported():
            assoc_sep = QFrame()
            assoc_sep.setFrameShape(QFrame.Shape.HLine)
            layout.addWidget(assoc_sep)

            assoc_label = QLabel('文件关联')
            assoc_label.setObjectName('sectionTitle')
            layout.addWidget(assoc_label)

            assoc_sub = QLabel('关联后，在资源管理器中双击 .lrmx 文件即可用本工具打开。仅影响当前用户，无需管理员权限。')
            assoc_sub.setStyleSheet('color: #888880; font-size: 12px;')
            assoc_sub.setWordWrap(True)
            layout.addWidget(assoc_sub)

            assoc_row = QHBoxLayout()
            self._assoc_btn = QPushButton()
            self._assoc_btn.clicked.connect(self._toggle_assoc)
            assoc_row.addWidget(self._assoc_btn)
            assoc_row.addStretch()
            layout.addLayout(assoc_row)
            self._refresh_assoc_btn()

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
        layout.addLayout(rule_btn_row)

        layout.addStretch()

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
            QMessageBox.critical(self, '操作失败', f'修改文件关联失败：\n{e}')
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
