from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QComboBox, QTextEdit,
    QFileDialog, QFrame, QProgressBar, QCheckBox,
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QIcon, QDragEnterEvent, QDropEvent

from app.core.excel_exporter import ExcelExporter, fmt_birth, normalize_birth
from app.core.lrmx import LrmxFile
from app.utils.naming import PRESETS, apply_rule
from app.ui.widgets.file_panel import LrmxFilePanel
from app.ui.workers import BaseWorker

_ASSETS = Path(__file__).parent.parent / 'assets'

_DEFAULT_RULE  = '{XingMing}{ChuShengNianYue}'
_DEFAULT_LABEL = '默认（姓名+出生年月）'


class _FamilyWorker(BaseWorker):
    finished = Signal(int, int, int, int)  # ok, skip, error, total
    # log 和 progress 已由 BaseWorker 声明

    def __init__(self, files, output_dir, naming_rule, on_exists, exporter, fix_birth=False):
        super().__init__()
        self.files       = files
        self.output_dir  = Path(output_dir)
        self.naming_rule = naming_rule
        self.on_exists   = on_exists
        self.exporter    = exporter
        self.fix_birth   = fix_birth

    def run(self):
        total = len(self.files)
        ok = skip = error = 0

        existing_map = self.exporter.scan_output_dir(self.output_dir)

        for i, f in enumerate(self.files):
            try:
                lf      = LrmxFile(Path(f))
                d       = lf.as_dict()
                members = lf.family_members()

                naming_d = dict(d)
                raw_birth = naming_d.get('ChuShengNianYue', '')
                naming_d['ChuShengNianYue'] = fmt_birth(raw_birth)

                stem        = apply_rule(self.naming_rule, naming_d)
                output_path = self.output_dir / f'{stem}.xlsx'

                status, label = self.exporter.export(
                    d, members, output_path, existing_map, self.on_exists, self.fix_birth
                )

                if status == 'created':
                    ok += 1
                    self.log.emit(f'✓ {label}（新建）')
                elif status == 'updated':
                    if self.fix_birth and 'ChuShengNianYue' in self.naming_rule:
                        naming_d = dict(d)
                        naming_d['ChuShengNianYue'] = fmt_birth(naming_d.get('ChuShengNianYue', ''))
                        new_stem = apply_rule(self.naming_rule, naming_d)
                        new_path = self.output_dir / f'{new_stem}.xlsx'
                        if new_path != output_path:
                            try:
                                output_path.rename(new_path)
                                label = new_stem
                                self.log.emit(f'✓ {label}（更新并重命名）')
                            except Exception as e:
                                self.log.emit(f'⚠ {label}（更新成功，重命名失败：{e}）')
                        else:
                            self.log.emit(f'✓ {label}（更新）')
                    else:
                        self.log.emit(f'✓ {label}（更新）')
                    ok += 1
                elif status == 'skip':
                    skip += 1
                    self.log.emit(f'△ {label}（已跳过）')
            except Exception as e:
                error += 1
                self.log.emit(f'✗ {Path(f).stem}：{e}')
            self.progress.emit(i + 1)

        self.finished.emit(ok, skip, error, total)


class FamilyTab(QWidget):
    USES_FILE_PANEL: bool = True
    busy_changed = Signal(bool)

    def __init__(self, file_panel: LrmxFilePanel, parent=None):
        super().__init__(parent)
        self._worker    = None
        self._exporter  = None
        self._log_entries: list[tuple[str, str]] = []
        self._active_filter = 'all'
        self._file_panel = file_panel
        self._build_ui()
        self.setAcceptDrops(True)

    def _get_exporter(self) -> ExcelExporter | None:
        if self._exporter is None:
            try:
                self._exporter = ExcelExporter()
            except Exception as e:
                self._append_log(f'✗ 模板加载失败：{e}')
                return None
        return self._exporter

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 15, 24, 15)
        layout.setSpacing(12)

        title = QLabel('家庭关系表')
        title.setObjectName('sectionTitle')
        layout.addWidget(title)

        sub = QLabel('根据任免表生成或更新干部家庭社会关系 Excel')
        sub.setStyleSheet('color: #888880; font-size: 12px;')
        layout.addWidget(sub)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep)

        # ── 文件命名 ──────────────────────────────────────────────────────────
        rule_row = QHBoxLayout()
        lbl = QLabel('文件命名')
        lbl.setFixedWidth(60)
        self._rule_combo = QComboBox()
        self._rule_combo.addItem(_DEFAULT_LABEL, _DEFAULT_RULE)
        for template, label in PRESETS:
            self._rule_combo.addItem(label, template)
        rule_row.addWidget(lbl)
        rule_row.addWidget(self._rule_combo, 1)
        layout.addLayout(rule_row)

        # ── 输出目录 ──────────────────────────────────────────────────────────
        dir_row = QHBoxLayout()
        dir_lbl = QLabel('输出目录')
        dir_lbl.setFixedWidth(60)
        dir_icon = QIcon(str(_ASSETS / 'folder.svg'))
        self._dir_edit = QLineEdit()
        self._dir_edit.setReadOnly(True)
        self._dir_edit.setPlaceholderText('选择输出目录…')
        self._dir_edit.addAction(dir_icon, QLineEdit.ActionPosition.LeadingPosition)
        self._dir_btn = QPushButton('浏览')
        self._dir_btn.setIcon(dir_icon)
        self._dir_btn.setIconSize(QSize(15, 15))
        self._dir_btn.clicked.connect(self._pick_dir)
        dir_row.addWidget(dir_lbl)
        dir_row.addWidget(self._dir_edit, 1)
        dir_row.addWidget(self._dir_btn)
        layout.addLayout(dir_row)

        # ── 已存在时 ──────────────────────────────────────────────────────────
        exists_row = QHBoxLayout()
        exists_lbl = QLabel('已存在时')
        exists_lbl.setFixedWidth(60)
        self._exists_combo = QComboBox()
        self._exists_combo.addItem('跳过', 'skip')
        self._exists_combo.addItem('更新基础信息', 'update')
        exists_row.addWidget(exists_lbl)
        exists_row.addWidget(self._exists_combo, 1)
        layout.addLayout(exists_row)

        self._chk_fix_birth = QCheckBox('修正已有关系表出生年月为标准格式 (yyyy.MM)')
        self._chk_fix_birth.setChecked(False)
        layout.addWidget(self._chk_fix_birth)

        # ── 开始按钮 ──────────────────────────────────────────────────────────
        run_row = QHBoxLayout()
        run_row.addStretch()
        self._run_btn = QPushButton('开始生成')
        self._run_btn.setObjectName('primary')
        self._run_btn.setIcon(QIcon(str(_ASSETS / 'start.svg')))
        self._run_btn.setIconSize(QSize(16, 16))
        self._run_btn.clicked.connect(self._run)
        run_row.addWidget(self._run_btn)
        layout.addLayout(run_row)

        self._progress = QProgressBar()
        self._progress.setObjectName('loadingBar')
        self._progress.setFixedHeight(4)
        self._progress.setTextVisible(False)
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        # ── 日志 ──────────────────────────────────────────────────────────────
        log_header = QHBoxLayout()
        log_header.setContentsMargins(0, 0, 0, 0)
        log_header.setSpacing(4)
        log_header.addStretch()
        self._log_filter_btns: list[QPushButton] = []
        for label, key in [('全部', 'all'), ('成功', 'ok'), ('跳过', 'skip'), ('错误', 'error')]:
            btn = QPushButton(label)
            btn.setFixedHeight(22)
            btn.setCheckable(True)
            btn.setProperty('logFilter', key)
            btn.setObjectName('logFilterBtn')
            btn.clicked.connect(lambda _, k=key: self._set_log_filter(k))
            log_header.addWidget(btn)
            self._log_filter_btns.append(btn)
        self._log_filter_btns[0].setChecked(True)
        layout.addLayout(log_header)

        self._log = QTextEdit()
        self._log.setObjectName('logView')
        self._log.setReadOnly(True)
        self._log.setMinimumHeight(80)
        layout.addWidget(self._log, 1)

    def _pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, '选择输出目录')
        if d:
            self._dir_edit.setText(d)

    # ── drag & drop ───────────────────────────────────────────────────────────

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
        elif message.startswith('△'):
            color, kind = '#e65100', 'skip'
        else:
            color, kind = '#888880', 'info'
        html = f'<span style="color:{color}">{message}</span>'
        self._log_entries.append((html, kind))
        if self._matches_filter(kind):
            self._log.append(html)

    def _matches_filter(self, kind: str) -> bool:
        f = self._active_filter
        if f == 'all':   return True
        if f == 'ok':    return kind == 'ok'
        if f == 'skip':  return kind == 'skip'
        if f == 'error': return kind == 'error'
        return True

    def _set_log_filter(self, key: str):
        self._active_filter = key
        for btn in self._log_filter_btns:
            btn.setChecked(btn.property('logFilter') == key)
        self._log.clear()
        for html, kind in self._log_entries:
            if self._matches_filter(kind):
                self._log.append(html)

    # ── run ───────────────────────────────────────────────────────────────────

    def _run(self):
        files = self._file_panel.files()
        if not files:
            self._append_log('△ 请先添加 lrmx 文件')
            return

        output_dir = self._dir_edit.text().strip()
        if not output_dir:
            self._append_log('△ 请选择输出目录')
            return

        exporter = self._get_exporter()
        if exporter is None:
            return

        self._run_btn.setEnabled(False)
        self._log.clear()
        self._log_entries.clear()

        self._worker = _FamilyWorker(
            files       = files,
            output_dir  = output_dir,
            naming_rule = self._rule_combo.currentData(),
            on_exists   = self._exists_combo.currentData(),
            exporter    = exporter,
            fix_birth   = self._chk_fix_birth.isChecked(),
        )
        self._progress.setRange(0, len(files))
        self._progress.setValue(0)
        self._progress.setVisible(True)

        self._worker.log.connect(self._append_log)
        self._worker.progress.connect(self._progress.setValue)
        self._worker.finished.connect(self._on_finished)
        self.busy_changed.emit(True)
        self._worker.start()

    def _on_finished(self, ok: int, skip: int, error: int, total: int):
        self._progress.setVisible(False)
        self._run_btn.setEnabled(True)
        self.busy_changed.emit(False)
        self._append_log(
            f'── 完成：共 {total} 个文件，生成/更新 {ok} 个，'
            f'跳过 {skip} 个，失败 {error} 个 ──'
        )
