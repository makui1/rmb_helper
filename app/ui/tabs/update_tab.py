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
