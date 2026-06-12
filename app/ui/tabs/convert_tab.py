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
