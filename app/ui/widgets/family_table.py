from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QComboBox, QHeaderView,
    QAbstractItemView,
)
from PySide6.QtCore import Qt, Signal

from app.core.dmgrp_loader import get_loader

_COLS = ['ChengWei', 'XingMing', 'ChuShengRiQi', 'ZhengZhiMianMao', 'GongZuoDanWeiJiZhiWu']
_HEADERS = ['称谓', '姓名', '出生日期', '政治面貌', '工作单位及职务']
_MIN_ROWS = 8  # 显示的最少行数


class FamilyTable(QWidget):
    """家庭成员表：称谓下拉 + 其余文本列，支持增删行。"""

    table_modified = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        self._table = QTableWidget(0, len(_COLS))
        self._table.setHorizontalHeaderLabels(_HEADERS)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.verticalHeader().setVisible(False)
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        hh.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self._table.setColumnWidth(0, 70)
        self._table.setColumnWidth(1, 80)
        self._table.setColumnWidth(2, 80)
        self._table.setColumnWidth(3, 90)
        self._table.itemChanged.connect(lambda _: self.table_modified.emit())
        lay.addWidget(self._table, 1)

        btn_row = QHBoxLayout()
        add_btn = QPushButton('+ 添加成员')
        add_btn.setFixedHeight(24)
        add_btn.clicked.connect(self._add_row)
        del_btn = QPushButton('- 删除选中')
        del_btn.setFixedHeight(24)
        del_btn.clicked.connect(self._del_row)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(del_btn)
        btn_row.addStretch()
        lay.addLayout(btn_row)

    def _add_row(self, data: dict | None = None):
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._table.setRowHeight(row, 26)

        combo = QComboBox()
        combo.setFrame(False)
        for opt in get_loader().options('GB4761'):
            combo.addItem(opt)
        if data:
            idx = combo.findText(data.get('ChengWei', ''))
            if idx >= 0:
                combo.setCurrentIndex(idx)
        combo.currentTextChanged.connect(lambda _: self.table_modified.emit())
        self._table.setCellWidget(row, 0, combo)

        for col_i, key in enumerate(_COLS[1:], 1):
            item = QTableWidgetItem(data.get(key, '') if data else '')
            self._table.setItem(row, col_i, item)

    def _del_row(self):
        rows = self._table.selectedItems()
        if rows:
            self._table.removeRow(rows[0].row())
            self.table_modified.emit()

    def load(self, members: list[dict[str, str]]) -> None:
        self._table.blockSignals(True)
        self._table.setRowCount(0)
        for m in members:
            self._add_row(m)
        self._table.blockSignals(False)

    def dump(self) -> list[dict[str, str]]:
        result = []
        for row in range(self._table.rowCount()):
            combo = self._table.cellWidget(row, 0)
            cheng_wei = combo.currentText() if combo else ''
            m: dict[str, str] = {'ChengWei': cheng_wei}
            for col_i, key in enumerate(_COLS[1:], 1):
                item = self._table.item(row, col_i)
                m[key] = item.text() if item else ''
            result.append(m)
        return result
