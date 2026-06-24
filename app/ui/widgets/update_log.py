from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QCheckBox, QDialog, QGridLayout, QFrame,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon

_ASSETS = Path(__file__).parent.parent / 'assets'


class _HoverIconButton(QPushButton):
    def __init__(self, icon_normal: QIcon, icon_hover: QIcon, parent=None):
        super().__init__(parent)
        self._icon_normal = icon_normal
        self._icon_hover = icon_hover
        self.setIcon(icon_normal)
        self.setStyleSheet("border:None;")

    def enterEvent(self, event):
        self.setIcon(self._icon_hover)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setIcon(self._icon_normal)
        super().leaveEvent(event)


class _UpdateFieldDialog(QDialog):
    """字段选择对话框，点击「开始更新」后弹出，让用户确认要写入的字段。"""

    def __init__(self, mapped_fields: list[tuple[str, str]], parent=None):
        super().__init__(parent)
        self.setWindowTitle('选择要写入的字段')
        self.setMinimumWidth(400)
        self._checks: dict[str, QCheckBox] = {}
        self._build_ui(mapped_fields)

    def _build_ui(self, mapped_fields: list[tuple[str, str]]):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 16, 20, 16)

        layout.addWidget(QLabel('以下字段已完成映射，勾选后将从名册写入 .lrmx'))

        grid_widget = QWidget()
        grid = QGridLayout(grid_widget)
        grid.setSpacing(8)
        grid.setContentsMargins(0, 0, 0, 0)
        for i, (tag, display) in enumerate(mapped_fields):
            chk = QCheckBox(display)
            chk.setChecked(True)
            chk.toggled.connect(self._refresh_confirm_btn)
            self._checks[tag] = chk
            grid.addWidget(chk, i // 2, i % 2)
        layout.addWidget(grid_widget)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        sel_all = QPushButton('全选')
        sel_all.setFixedHeight(26)
        sel_all.clicked.connect(self._select_all)
        sel_none = QPushButton('全不选')
        sel_none.setFixedHeight(26)
        sel_none.clicked.connect(self._deselect_all)
        btn_row.addWidget(sel_all)
        btn_row.addWidget(sel_none)
        layout.addLayout(btn_row)

        warn = QLabel('⚠ 更新将直接修改 .lrmx 文件，建议先核验确认数据正确后再执行更新。')
        warn.setWordWrap(True)
        warn.setStyleSheet('color: #C07030; font-size: 11px;')
        layout.addWidget(warn)

        action_row = QHBoxLayout()
        action_row.addStretch()
        cancel = QPushButton('取消')
        cancel.setFixedHeight(28)
        cancel.clicked.connect(self.reject)
        self._confirm_btn = QPushButton('确认更新')
        self._confirm_btn.setObjectName('primary')
        self._confirm_btn.setFixedHeight(28)
        self._confirm_btn.clicked.connect(self.accept)
        action_row.addWidget(cancel)
        action_row.addWidget(self._confirm_btn)
        layout.addLayout(action_row)

    def _refresh_confirm_btn(self):
        self._confirm_btn.setEnabled(
            any(c.isChecked() for c in self._checks.values())
        )

    def _select_all(self):
        for chk in self._checks.values():
            chk.setChecked(True)

    def _deselect_all(self):
        for chk in self._checks.values():
            chk.setChecked(False)

    def selected_fields(self) -> list[str]:
        return [tag for tag, chk in self._checks.items() if chk.isChecked()]


class _UpdateLogRow(QWidget):
    """更新结果区的单条日志行：显示图标 + 消息，附带分隔线。"""

    def __init__(self, message: str, kind: str, parent=None):
        super().__init__(parent)
        self._kind = kind  # 'ok' | 'not_found' | 'error'
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        row_w = QWidget()
        rl = QHBoxLayout(row_w)
        rl.setContentsMargins(10, 7, 10, 7)
        lbl = QLabel(message)
        if kind == 'ok':
            lbl.setStyleSheet('color: #1E7A3A;')
        elif kind == 'not_found':
            lbl.setStyleSheet('color: #C07030;')
        else:
            lbl.setStyleSheet('color: #B02020;')
        rl.addWidget(lbl)
        outer.addWidget(row_w)

        sep = QFrame()
        sep.setObjectName('resultSep')
        sep.setFrameShape(QFrame.Shape.HLine)
        outer.addWidget(sep)
