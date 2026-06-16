from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListWidget, QListWidgetItem, QLineEdit,
    QRadioButton, QButtonGroup, QTextEdit, QFileDialog,
    QSizePolicy, QMenu, QDialog, QProgressBar, QFrame,
)
from PySide6.QtCore import Qt, QThread, Signal, QSize, QEvent, QTimer
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QIcon, QPainter, QColor, QPen

from app.core.excel_handler import ExcelHandler, MatchMode

_ASSETS = Path(__file__).parent.parent / 'assets'

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


# ── background workers ────────────────────────────────────────────────────────

class _FolderScanWorker(QThread):
    done = Signal(list)

    def __init__(self, folder: str, parent=None):
        super().__init__(parent)
        self._folder = folder

    def run(self):
        paths = sorted(str(p) for p in Path(self._folder).rglob('*.lrmx'))
        self.done.emit(paths)


class _Worker(QThread):
    log = Signal(str)
    finished = Signal()

    def __init__(self, excel_path, lrmx_files, match_mode, fields):
        super().__init__()
        self.excel_path = excel_path
        self.lrmx_files = lrmx_files
        self.match_mode = match_mode
        self.fields = fields

    def run(self):
        try:
            handler = ExcelHandler(self.excel_path, self.lrmx_files, self.match_mode)
            handler.update(self.fields, progress_cb=self.log.emit)
        except Exception as e:
            self.log.emit(f'✗ 错误: {e}')
        self.finished.emit()


# ── shared list widgets ───────────────────────────────────────────────────────

class _LoadingDialog(QDialog):
    def __init__(self, parent, message: str = '正在扫描，请稍候…'):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setModal(True)
        self.setObjectName('loadingDialog')
        self.setFixedSize(260, 90)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 20, 28, 20)
        layout.setSpacing(12)

        lbl = QLabel(message)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setObjectName('loadingLabel')
        layout.addWidget(lbl)

        bar = QProgressBar()
        bar.setRange(0, 0)
        bar.setFixedHeight(4)
        bar.setTextVisible(False)
        bar.setObjectName('loadingBar')
        layout.addWidget(bar)

    def showEvent(self, event):
        super().showEvent(event)
        if self.parent():
            pg = self.parent().frameGeometry()
            self.move(
                pg.center().x() - self.width() // 2,
                pg.center().y() - self.height() // 2,
            )


class _FileList(QListWidget):
    empty_clicked = Signal()
    _HINT = '拖放 .lrmx 文件至此，或点击「添加」'

    def __init__(self, parent=None):
        super().__init__(parent)
        self.viewport().installEventFilter(self)

    def eventFilter(self, obj, event):
        if (obj is self.viewport()
                and event.type() == QEvent.Type.MouseButtonPress
                and event.button() == Qt.MouseButton.LeftButton
                and self.count() == 0):
            self.empty_clicked.emit()
        return super().eventFilter(obj, event)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.count() == 0:
            painter = QPainter(self.viewport())
            painter.setPen(QColor('#BBBBBB'))
            font = self.font()
            font.setPointSize(11)
            painter.setFont(font)
            painter.drawText(
                self.viewport().rect(),
                Qt.AlignmentFlag.AlignCenter,
                self._HINT,
            )
            painter.end()


class _FileRow(QWidget):
    removed = Signal(QListWidgetItem)
    _SEP_NORMAL = QColor('#E8E6E0')
    _SEP_HOVER  = QColor('#1A1A1A')

    def __init__(self, path: str, item: QListWidgetItem, parent=None):
        super().__init__(parent)
        self._item = item
        self._hovered = False
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 8, 6)
        layout.setSpacing(8)

        icon = QLabel('📄')
        icon.setFixedWidth(18)
        layout.addWidget(icon)

        name = QLabel(Path(path).name)
        name.setObjectName('fileItemName')
        name.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(name, 1)

        btn = QPushButton('×')
        btn.setObjectName('fileItemRemove')
        btn.setFixedSize(20, 20)
        btn.clicked.connect(lambda: self.removed.emit(self._item))
        layout.addWidget(btn)

    def event(self, e: QEvent) -> bool:
        if e.type() == QEvent.Type.HoverEnter:
            self._hovered = True
            self.update()
        elif e.type() == QEvent.Type.HoverLeave:
            self._hovered = False
            self.update()
        return super().event(e)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        color = self._SEP_HOVER if self._hovered else self._SEP_NORMAL
        painter.setPen(QPen(color, 1))
        y = self.height() - 1
        painter.drawLine(10, y, self.width() - 10, y)
        painter.end()


# ── tab widget ────────────────────────────────────────────────────────────────

class UpdateTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._scan_worker = None
        self._log_entries: list[tuple[str, str]] = []
        self._active_filter = 'all'
        self._build_ui()
        self.setAcceptDrops(True)

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

        # ── lrmx 文件列表 ───────────────────────────────────────────────────────
        list_header = QHBoxLayout()
        list_header.setContentsMargins(0, 0, 0, 0)
        list_header.setSpacing(6)
        list_header.addStretch()

        add_btn = QPushButton('+ 添加')
        add_btn.setFixedHeight(26)
        add_menu = QMenu(add_btn)
        add_menu.addAction('选择文件…', self._pick_files)
        add_menu.addAction('选择文件夹…', self._pick_folder)
        add_btn.setMenu(add_menu)

        del_btn = QPushButton('删除选中')
        del_btn.setFixedHeight(26)
        del_btn.clicked.connect(self._remove_selected)

        clear_btn = QPushButton('清空')
        clear_btn.setFixedHeight(26)
        clear_btn.clicked.connect(self._clear_files)

        list_header.addWidget(add_btn)
        list_header.addWidget(del_btn)
        list_header.addWidget(clear_btn)
        layout.addLayout(list_header)

        self._file_list = _FileList()
        self._file_list.setObjectName('fileList')
        self._file_list.setMinimumHeight(100)
        self._file_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self._file_list.empty_clicked.connect(lambda: add_menu.exec(
            add_btn.mapToGlobal(add_btn.rect().bottomLeft())
        ))
        layout.addWidget(self._file_list)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep1)

        # ── Excel 文件 ─────────────────────────────────────────────────────────
        xl_row = QHBoxLayout()
        xl_label = QLabel('Excel 文件')
        xl_label.setFixedWidth(72)
        self._xl_edit = QLineEdit()
        self._xl_edit.setReadOnly(True)
        self._xl_edit.setPlaceholderText('选择 .xlsx 文件…')
        xl_btn = QPushButton('浏览')
        xl_btn.setIcon(QIcon(str(_ASSETS / 'folder.svg')))
        xl_btn.setIconSize(QSize(15, 15))
        xl_btn.clicked.connect(self._pick_excel)
        xl_row.addWidget(xl_label)
        xl_row.addWidget(self._xl_edit)
        xl_row.addWidget(xl_btn)
        layout.addLayout(xl_row)

        # ── 匹配依据 ───────────────────────────────────────────────────────────
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

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep2)

        # ── 更新字段多选 ───────────────────────────────────────────────────────
        field_header = QHBoxLayout()
        field_header.setContentsMargins(0, 0, 0, 0)
        field_header.setSpacing(6)
        field_title = QLabel('选择要更新的字段')
        field_title.setObjectName('sectionTitle')
        field_header.addWidget(field_title)
        field_header.addStretch()
        sel_all_btn = QPushButton('全选')
        sel_all_btn.setFixedHeight(26)
        sel_all_btn.clicked.connect(self._select_all_fields)
        sel_none_btn = QPushButton('全不选')
        sel_none_btn.setFixedHeight(26)
        sel_none_btn.clicked.connect(self._deselect_all_fields)
        field_header.addWidget(sel_all_btn)
        field_header.addWidget(sel_none_btn)
        layout.addLayout(field_header)

        self._field_list = QListWidget()
        self._field_list.setObjectName('fileList')
        self._field_list.setMaximumHeight(150)
        for key, label in FIELD_LABELS.items():
            item = QListWidgetItem(f'{label}（{key}）')
            item.setData(Qt.ItemDataRole.UserRole, key)
            item.setCheckState(Qt.CheckState.Unchecked)
            self._field_list.addItem(item)
        layout.addWidget(self._field_list)

        # ── 开始按钮 ───────────────────────────────────────────────────────────
        run_row = QHBoxLayout()
        run_row.addStretch()
        self._run_btn = QPushButton('开始更新')
        self._run_btn.setIcon(QIcon(str(_ASSETS / 'start.svg')))
        self._run_btn.setIconSize(QSize(16, 16))
        self._run_btn.setObjectName('primary')
        self._run_btn.clicked.connect(self._run)
        run_row.addWidget(self._run_btn)
        layout.addLayout(run_row)

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
        layout.addLayout(log_header)

        self._log = QTextEdit()
        self._log.setObjectName('logView')
        self._log.setReadOnly(True)
        self._log.setMinimumHeight(100)
        layout.addWidget(self._log)

    # ── field helpers ─────────────────────────────────────────────────────────

    def _select_all_fields(self):
        for i in range(self._field_list.count()):
            self._field_list.item(i).setCheckState(Qt.CheckState.Checked)

    def _deselect_all_fields(self):
        for i in range(self._field_list.count()):
            self._field_list.item(i).setCheckState(Qt.CheckState.Unchecked)

    # ── file list helpers ─────────────────────────────────────────────────────

    def _add_file(self, path: str):
        for i in range(self._file_list.count()):
            if self._file_list.item(i).data(Qt.ItemDataRole.UserRole) == path:
                return
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, path)
        item.setSizeHint(QSize(0, 34))
        self._file_list.addItem(item)
        row = _FileRow(path, item)
        row.removed.connect(self._remove_item)
        self._file_list.setItemWidget(item, row)

    def _remove_item(self, item: QListWidgetItem):
        self._file_list.takeItem(self._file_list.row(item))

    def _remove_selected(self):
        for item in self._file_list.selectedItems():
            self._file_list.takeItem(self._file_list.row(item))

    def _clear_files(self):
        self._file_list.clear()

    def _pick_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, '选择 lrmx 文件', '', '任免审批表 (*.lrmx)'
        )
        for p in paths:
            self._add_file(p)

    def _pick_folder(self):
        folder = QFileDialog.getExistingDirectory(self, '选择包含 lrmx 文件的文件夹')
        if not folder:
            return
        dlg = _LoadingDialog(self, '正在扫描文件夹…')
        self._scan_worker = _FolderScanWorker(folder)

        def _on_done(paths):
            batch = list(paths)
            def add_batch():
                chunk, rest = batch[:20], batch[20:]
                for p in chunk:
                    self._add_file(p)
                batch.clear()
                batch.extend(rest)
                if batch:
                    QTimer.singleShot(0, add_batch)
                else:
                    dlg.accept()
            QTimer.singleShot(0, add_batch)

        self._scan_worker.done.connect(_on_done)
        self._scan_worker.start()
        dlg.exec()

    def _files(self) -> list[str]:
        return [
            self._file_list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self._file_list.count())
        ]

    # ── drag & drop ───────────────────────────────────────────────────────────

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith('.lrmx'):
                self._add_file(path)

    # ── Excel picker ──────────────────────────────────────────────────────────

    def _pick_excel(self):
        path, _ = QFileDialog.getOpenFileName(
            self, '选择 Excel 文件', '', 'Excel 文件 (*.xlsx *.xls)'
        )
        if path:
            self._xl_edit.setText(path)

    # ── log helpers ───────────────────────────────────────────────────────────

    def _append_log(self, message: str):
        if message.startswith('✓') or message.startswith('已更新'):
            color, kind = '#2e7d32', 'ok'
        elif message.startswith('✗'):
            color, kind = '#c62828', 'error'
        elif message.startswith('△') or message.startswith('⚠') or message.startswith('未匹配'):
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
        files = self._files()
        if not files:
            self._append_log('⚠ 请先添加 lrmx 文件')
            return

        excel_path = self._xl_edit.text()
        if not excel_path:
            self._append_log('⚠ 请选择 Excel 文件')
            return

        fields = [
            self._field_list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self._field_list.count())
            if self._field_list.item(i).checkState() == Qt.CheckState.Checked
        ]
        if not fields:
            self._append_log('⚠ 请至少勾选一个要更新的字段')
            return

        if self._rb_id.isChecked():
            match_mode = MatchMode.ID_CARD
        elif self._rb_name.isChecked():
            match_mode = MatchMode.NAME
        else:
            match_mode = MatchMode.NAME_AND_ID

        self._run_btn.setEnabled(False)
        self._log.clear()
        self._log_entries.clear()

        self._worker = _Worker(excel_path, files, match_mode, fields)
        self._worker.log.connect(self._append_log)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _on_finished(self):
        self._run_btn.setEnabled(True)
        self._append_log('── 完成 ──')
