import shutil
import time
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QCheckBox, QLineEdit, QComboBox, QTextEdit,
    QFileDialog, QSizePolicy, QProgressBar,
)
from PySide6.QtCore import Qt, QSettings, Signal, QSize
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QIcon

from app.core.lrmx import LrmxFile
from app.core.docx_exporter import DocxExporter, get_template_path
from app.core.pdf_exporter import PdfExporter
from app.utils.naming import apply_rule, clean_field, PRESETS
from app.ui.widgets.file_panel import LrmxFilePanel
from app.ui.workers import BaseWorker

_ASSETS = Path(__file__).parent.parent / 'assets'


class _FormatWorker(BaseWorker):
    """后台格式化 LRMX 文件（空标签自闭合 + 姓名空格 + 身份证 x→X）。"""

    def __init__(self, files: list[str]):
        super().__init__()
        self.files = files

    def run(self):
        total = len(self.files)
        for i, path in enumerate(self.files):
            try:
                LrmxFile(Path(path)).normalize()
                self.log.emit(f'<span style="color:#1E7A3A;">✓</span> {Path(path).name}')
            except Exception as e:
                self.log.emit(
                    f'<span style="color:#B02020;">✗</span> {Path(path).name}：{e}'
                )
            self.progress.emit(int((i + 1) / total * 100))


class _Worker(BaseWorker):
    finished = Signal(int, int, float)  # done, total, elapsed_seconds

    def __init__(self, files, output_dir, sub_dir, naming_rule, do_docx, do_pdf,
                 sibling_dir=False, collect_lrmx=False):
        super().__init__()
        self.files = files
        self.output_dir = Path(output_dir) if output_dir else None
        self.sub_dir = sub_dir if sub_dir else False
        self.naming_rule = naming_rule
        self.do_docx = do_docx
        self.do_pdf = do_pdf
        self.sibling_dir = sibling_dir
        self.collect_lrmx = collect_lrmx

    def run(self):
        start = time.monotonic()
        total = len(self.files)
        total_steps = total * (2 if self.do_pdf else 1)

        # ── 模板准备（各一次） ────────────────────────────────────────
        try:
            template_bytes = get_template_path().read_bytes()
        except FileNotFoundError as e:
            self.log.emit(f'✗ {e}')
            self.finished.emit(0, total, 0.0)
            return

        cell_size = DocxExporter.probe_cell_size(template_bytes)

        pdf_exporter = PdfExporter()
        pdf_available = False
        if self.do_pdf:
            pdf_available = pdf_exporter.available()
            if not pdf_available:
                self.log.emit('△ 未检测到可用 PDF 渲染引擎，PDF 输出已跳过')

        # ── 预处理：解析所有 lrmx，计算输出路径 ──────────────────────────
        succeeded: list[bool] = [False] * total
        docx_job_args: list[tuple[str, str]] = []
        docx_job_meta: list[tuple[int, str, Path]] = []  # (idx, stem, pdf_out_dir)
        tmp_dirs: set[Path] = set()

        for idx, lrmx_path in enumerate(self.files):
            num = f'({idx + 1}/{total})'
            try:
                lf = LrmxFile(Path(lrmx_path))
                stem = apply_rule(self.naming_rule, lf.as_dict()) or Path(lrmx_path).stem
                base_dir = Path(lrmx_path).parent if self.sibling_dir else self.output_dir

                # 根据 sub_dir 决定 docx / pdf 各自的落地目录
                docx_out_dir = (base_dir / 'docx') if self.sub_dir else base_dir
                pdf_out_dir  = (base_dir / 'pdf')  if self.sub_dir else base_dir

                if self.do_docx:
                    docx_out_dir.mkdir(parents=True, exist_ok=True)
                    docx_path = docx_out_dir / (stem + '.docx')
                    docx_job_args.append((lrmx_path, str(docx_path)))
                    docx_job_meta.append((idx, stem, pdf_out_dir))
                elif pdf_available:
                    # 仅导出 PDF：docx 写到临时目录，PDF 写到 pdf_out_dir
                    tmp_dir = base_dir / '.tmp_docx'
                    tmp_dirs.add(tmp_dir)
                    tmp_dir.mkdir(parents=True, exist_ok=True)
                    tmp_docx = tmp_dir / (stem + '.docx')
                    docx_job_args.append((lrmx_path, str(tmp_docx)))
                    docx_job_meta.append((idx, stem, pdf_out_dir))
                else:
                    succeeded[idx] = True

            except Exception as e:
                self.log.emit(f'✗ {Path(lrmx_path).name}: {e} {num}')

        # ── 阶段一：并行 DOCX ────────────────────────────────────────────
        pdf_jobs: list[tuple[Path, Path]] = []

        if docx_job_args:
            docx_total = len(docx_job_args)
            docx_done_count = [0]
            output_to_meta: dict[str, tuple[int, str, Path]] = {
                job[1]: meta
                for job, meta in zip(docx_job_args, docx_job_meta)
            }

            def _on_docx(stem: str, output_path: 'str | None', err: str) -> None:
                docx_done_count[0] += 1
                self.progress.emit(docx_done_count[0])
                n = f'({docx_done_count[0]}/{docx_total})'
                if err:
                    self.log.emit(f'✗ {stem}: {err} {n}')
                else:
                    idx, _, pdf_out_dir = output_to_meta[output_path]
                    succeeded[idx] = True
                    if self.do_docx:
                        self.log.emit(f'✓ {stem} → docx 完成 {n}')
                    if pdf_available:
                        pdf_jobs.append((Path(output_path), pdf_out_dir))

            DocxExporter.export_parallel(
                docx_job_args, template_bytes, cell_size, on_progress=_on_docx
            )

        # ── 阶段二：并行 PDF ─────────────────────────────────────────────
        if pdf_jobs:
            pdf_total = len(pdf_jobs)
            pdf_done_count = [0]

            def _on_pdf(stem: str, pdf_path: 'str | None', err: str) -> None:
                pdf_done_count[0] += 1
                self.progress.emit(len(docx_job_args) + pdf_done_count[0])
                n = f'({pdf_done_count[0]}/{pdf_total})'
                if err:
                    self.log.emit(f'✗ {stem}: {err} {n}')
                else:
                    self.log.emit(f'✓ {stem} → pdf 完成 {n}')

            pdf_exporter.export_parallel(pdf_jobs, on_progress=_on_pdf)

        # ── 收尾 ────────────────────────────────────────────────────
        for tmp_dir in tmp_dirs:
            shutil.rmtree(tmp_dir, ignore_errors=True)

        # ── 归集任免表 ───────────────────────────────────────────────
        if self.collect_lrmx and self.output_dir:
            collect_dir = self.output_dir / '任免审批表'
            collect_dir.mkdir(parents=True, exist_ok=True)
            for lrmx_path in self.files:
                try:
                    lf   = LrmxFile(Path(lrmx_path))
                    d    = lf.as_dict()
                    name = clean_field(d.get('XingMing', ''))
                    sfz  = clean_field(d.get('ShenFenZheng', ''))
                    empty = [f for f, v in [('XingMing', name), ('ShenFenZheng', sfz)] if not v]
                    if empty:
                        raise ValueError(f'字段值为空：{", ".join(empty)}')
                    dest_name = f'{name}{sfz}.lrmx'
                    shutil.copy2(lrmx_path, collect_dir / dest_name)
                    self.log.emit(f'✓ 归集：{dest_name}')
                except Exception as e:
                    self.log.emit(f'✗ 归集失败 {Path(lrmx_path).name}：{e}')

        done = sum(succeeded)
        self.finished.emit(done, total, time.monotonic() - start)




class ConvertTab(QWidget):
    USES_FILE_PANEL: bool = True
    busy_changed = Signal(bool)

    def __init__(self, file_panel: LrmxFilePanel, parent=None):
        super().__init__(parent)
        self._settings = QSettings('rmb_helper', 'rmb_helper')
        self._worker = None
        self._file_panel = file_panel
        self._build_ui()
        self.setAcceptDrops(True)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 15, 24, 15)
        layout.setSpacing(12)

        title = QLabel('批量转换')
        title.setObjectName('sectionTitle')
        layout.addWidget(title)

        sub = QLabel('lrmx → docx / pdf 批量转换')
        sub.setStyleSheet('color: #888880; font-size: 12px;')
        layout.addWidget(sub)

        bot_layout = QVBoxLayout()
        bot_layout.setContentsMargins(0, 0, 0, 0)
        bot_layout.setSpacing(12)
        layout.addLayout(bot_layout, 1)

        # ── 输出选项 ───────────────────────────────────────────────────────────
        fmt_row = QHBoxLayout()
        fmt_label = QLabel('输出选项')
        fmt_label.setFixedWidth(64)
        self._chk_docx = QCheckBox('docx')
        self._chk_docx.setChecked(False)
        self._chk_pdf = QCheckBox('pdf')
        self._chk_pdf.setChecked(True)
        self._chk_sibling = QCheckBox('输出到任免表同级目录')
        self._chk_sibling.setChecked(False)
        self._chk_sibling.toggled.connect(self._on_sibling_toggled)
        self._chk_own_dir = QCheckBox('为输出文件类型创建目录')
        self._chk_own_dir.setChecked(True)
        self._chk_collect = QCheckBox('归集任免表')
        self._chk_collect.setChecked(False)
        self._chk_collect.setToolTip('将文件列表中的 lrmx 文件复制到输出目录下的【任免审批表】子文件夹，命名为{姓名}{身份证号}.lrmx')
        fmt_row.addWidget(fmt_label)
        fmt_row.addWidget(self._chk_docx)
        fmt_row.addSpacing(16)
        fmt_row.addWidget(self._chk_pdf)
        fmt_row.addSpacing(16)
        fmt_row.addWidget(self._chk_sibling)
        fmt_row.addSpacing(16)
        fmt_row.addWidget(self._chk_own_dir)
        fmt_row.addSpacing(16)
        fmt_row.addWidget(self._chk_collect)
        fmt_row.addStretch()
        bot_layout.addLayout(fmt_row)

        # ── 输出目录 ───────────────────────────────────────────────────────────
        dir_row = QHBoxLayout()
        dir_label = QLabel('输出目录')
        dir_label.setFixedWidth(64)
        self._dir_edit = QLineEdit()
        self._dir_edit.setPlaceholderText('选择输出目录…')
        self._dir_edit.setReadOnly(True)
        self._dir_edit.addAction(
            QIcon(str(_ASSETS / 'folder.svg')), QLineEdit.ActionPosition.LeadingPosition
        )
        self._dir_btn = QPushButton('浏览')
        self._dir_btn.setIcon(QIcon(str(_ASSETS / 'folder.svg')))
        self._dir_btn.setIconSize(QSize(15, 15))
        self._dir_btn.clicked.connect(self._pick_dir)
        dir_row.addWidget(dir_label)
        dir_row.addWidget(self._dir_edit)
        dir_row.addWidget(self._dir_btn)
        bot_layout.addLayout(dir_row)

        # ── 命名规则 + 开始按钮 ────────────────────────────────────────────────
        rule_row = QHBoxLayout()
        rule_label = QLabel('命名规则')
        rule_label.setFixedWidth(64)
        self._rule_combo = QComboBox()
        self._rule_combo.setEditable(False)
        self._refresh_rules()
        self._custom_edit = QLineEdit()
        self._custom_edit.setPlaceholderText('自定义：{XingMing}_{ShenFenZheng}')
        self._custom_edit.setVisible(False)
        custom_btn = QPushButton('自定义')
        custom_btn.setCheckable(True)
        custom_btn.toggled.connect(self._toggle_custom)
        self._run_btn = QPushButton('开始转换')
        self._run_btn.setIcon(QIcon(str(_ASSETS / 'start.svg')))
        self._run_btn.setIconSize(QSize(16, 16))
        self._run_btn.setObjectName('primary')
        self._run_btn.clicked.connect(self._run)
        self._format_btn = QPushButton('格式化')
        self._format_btn.setToolTip('将文件列表中所有 lrmx 的空标签转为自闭合格式')
        self._format_btn.clicked.connect(self._on_format)
        rule_row.addWidget(rule_label)
        rule_row.addWidget(self._rule_combo)
        rule_row.addWidget(self._custom_edit)
        rule_row.addWidget(custom_btn)
        rule_row.addStretch()
        rule_row.addWidget(self._format_btn)
        rule_row.addSpacing(6)
        rule_row.addWidget(self._run_btn)
        bot_layout.addLayout(rule_row)

        self._progress = QProgressBar()
        self._progress.setObjectName('loadingBar')
        self._progress.setFixedHeight(4)
        self._progress.setTextVisible(False)
        self._progress.setVisible(False)
        bot_layout.addWidget(self._progress)

        # ── 日志 ───────────────────────────────────────────────────────────────
        log_header = QHBoxLayout()
        log_header.setContentsMargins(0, 0, 0, 0)
        log_header.setSpacing(4)
        log_header.addStretch()
        self._log_filter_btns: list[QPushButton] = []
        for label, key in [('全部', 'all'), ('成功', 'ok'), ('错误', 'error')]:
            btn = QPushButton(label)
            btn.setFixedHeight(22)
            btn.setCheckable(True)
            btn.setProperty('logFilter', key)
            btn.setObjectName('logFilterBtn')
            btn.clicked.connect(lambda _, k=key: self._set_log_filter(k))
            log_header.addWidget(btn)
            self._log_filter_btns.append(btn)
        self._log_filter_btns[0].setChecked(True)
        self._active_filter = 'all'
        bot_layout.addLayout(log_header)

        self._log = QTextEdit()
        self._log.setObjectName('logView')
        self._log.setReadOnly(True)
        self._log.setMinimumHeight(80)
        bot_layout.addWidget(self._log, 1)
        self._log_entries: list[tuple[str, str]] = []

    # ── helpers ───────────────────────────────────────────────────────────────

    def _pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, '选择输出目录')
        if d:
            self._dir_edit.setText(d)

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

    def _on_sibling_toggled(self, checked: bool):
        self._dir_edit.setEnabled(not checked)
        self._dir_btn.setEnabled(not checked)

    def _on_format(self):
        """对文件列表中所有 lrmx 执行 XML 格式化（后台线程）。"""
        files = self._file_panel.files()
        if not files:
            self._log.clear()
            self._log.append('⚠ 文件列表为空，请先添加 lrmx 文件。')
            return

        self._format_btn.setEnabled(False)
        self._run_btn.setEnabled(False)
        self._log.clear()
        self._log_entries.clear()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setVisible(True)

        self._format_worker = _FormatWorker(files=list(files))
        self._format_worker.log.connect(self._append_log)
        self._format_worker.progress.connect(self._progress.setValue)
        self._format_worker.finished.connect(self._on_format_finished)
        self.busy_changed.emit(True)
        self._format_worker.start()

    def _on_format_finished(self):
        self._progress.setVisible(False)
        self._format_btn.setEnabled(True)
        self._run_btn.setEnabled(True)
        self.busy_changed.emit(False)
        self._log.append('')
        ok = sum(1 for e in self._log_entries if '✓' in e)
        err = len(self._log_entries) - ok
        self._log.append(f'格式化完成：{ok} 成功，{err} 失败')

    # ── drag & drop (tab-level, delegates to panel) ───────────────────────────

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith('.lrmx'):
                self._file_panel.add_file(path)

    # ── log helpers ───────────────────────────────────────────────────────────

    def _append_log(self, message: str):
        if message.startswith('✓'):
            color, kind = '#2e7d32', 'ok'
        elif message.startswith('✗'):
            color, kind = '#c62828', 'error'
        elif message.startswith('△') or message.startswith('⚠'):
            color, kind = '#e65100', 'warn'
        else:
            color, kind = '#888880', 'info'
        self._log_entries.append((f'<span style="color:{color}">{message}</span>', kind))
        if self._active_filter == 'all' or (
            self._active_filter == 'ok' and kind == 'ok'
        ) or (
            self._active_filter == 'error' and kind in ('error', 'warn')
        ):
            self._log.append(self._log_entries[-1][0])

    def _set_log_filter(self, key: str):
        self._active_filter = key
        for btn in self._log_filter_btns:
            btn.setChecked(btn.property('logFilter') == key)
        self._render_log()

    def _render_log(self):
        self._log.clear()
        for html, kind in self._log_entries:
            if self._active_filter == 'all':
                self._log.append(html)
            elif self._active_filter == 'ok' and kind == 'ok':
                self._log.append(html)
            elif self._active_filter == 'error' and kind in ('error', 'warn'):
                self._log.append(html)

    # ── run ───────────────────────────────────────────────────────────────────

    def _run(self):
        files = self._file_panel.files()
        if not files:
            self._append_log('⚠ 请先添加 .lrmx 文件')
            return
        sibling = self._chk_sibling.isChecked()
        output_dir = self._dir_edit.text()
        if not sibling and not output_dir:
            self._append_log('⚠ 请选择输出目录，或勾选「输出到任免表同级目录」')
            return

        naming_rule = (
            self._custom_edit.text().strip()
            if self._custom_edit.isVisible()
            else self._rule_combo.currentText()
        ) or PRESETS[0][0]

        self._run_btn.setEnabled(False)
        self._log.clear()
        self._log_entries.clear()

        self._worker = _Worker(
            files=files,
            output_dir=output_dir,
            sub_dir=self._chk_own_dir.isChecked(),
            naming_rule=naming_rule,
            do_docx=self._chk_docx.isChecked(),
            do_pdf=self._chk_pdf.isChecked(),
            sibling_dir=sibling,
            collect_lrmx=self._chk_collect.isChecked(),
        )
        total_steps = len(files) * (2 if self._chk_pdf.isChecked() else 1)
        self._progress.setRange(0, total_steps)
        self._progress.setValue(0)
        self._progress.setVisible(True)

        self._worker.log.connect(self._append_log)
        self._worker.progress.connect(self._progress.setValue)
        self._worker.finished.connect(self._on_finished)
        self.busy_changed.emit(True)
        self._worker.start()

    def _on_finished(self, done: int, total: int, elapsed: float):
        self._progress.setVisible(False)
        self._run_btn.setEnabled(True)
        self.busy_changed.emit(False)
        self._append_log(f'完成 {done}/{total}，耗时 {elapsed:.1f}s')
