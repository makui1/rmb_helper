import json

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QListWidget, QListWidgetItem,
    QInputDialog, QFileDialog, QMessageBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
)
from PySide6.QtCore import QSettings, Qt
from app.utils.naming import PRESETS
from app.core.verify_handler import LRMX_FIELDS, DEFAULT_FIELD_ALIASES


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

    def _save(self):
        self._settings.setValue('template_path', self._tpl_edit.text())
        rules = [self._rule_list.item(i).text() for i in range(self._rule_list.count())]
        self._settings.setValue('naming_rules', rules)

        aliases: dict[str, str] = {}
        for i, (tag, _) in enumerate(LRMX_FIELDS):
            item = self._alias_table.item(i, 2)
            val = item.text().strip() if item else ''
            if val:
                aliases[tag] = val
        self._settings.setValue('verify_field_aliases', json.dumps(aliases, ensure_ascii=False))

        QMessageBox.information(self, '保存成功', '设置已保存。')

    def template_path(self) -> str:
        return self._tpl_edit.text()

    def naming_rules(self) -> list[str]:
        return [self._rule_list.item(i).text() for i in range(self._rule_list.count())]
