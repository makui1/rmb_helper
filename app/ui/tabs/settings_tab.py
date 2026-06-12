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
