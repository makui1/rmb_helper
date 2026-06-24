from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QScrollArea, QFrame, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QIcon

from app.core.compare_rules import CompareRule
from app.ui.widgets.flow_layout import _FlowLayout, _MatchTag

_ASSETS = Path(__file__).parent.parent / 'assets'


# 临时定义，Task 10 完成后改为从 app.ui.widgets.update_log 导入
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


class _NoScrollCombo(QComboBox):
    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class _FieldRow(QWidget):
    clicked_field = Signal(str)
    remove_mapping = Signal(str)

    def __init__(self, tag: str, display: str, parent=None):
        super().__init__(parent)
        self._field = tag
        self._rules: list[CompareRule] = []
        self.setObjectName('fieldRow')
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(6)

        name_lbl = QLabel(display)
        name_lbl.setObjectName('fieldRowName')
        name_lbl.setFixedWidth(180)
        layout.addWidget(name_lbl)

        self._map_lbl = QLabel('未匹配')
        self._map_lbl.setObjectName('fieldRowUnmapped')
        self._map_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._map_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(self._map_lbl, 1)

        self._rule_combo = _NoScrollCombo()
        self._rule_combo.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._rule_combo.setFixedWidth(110)
        self._rule_combo.addItem('（默认）')
        self._rule_combo.hide()
        layout.addWidget(self._rule_combo)

        self._remove_btn = _HoverIconButton(
            QIcon(str(_ASSETS / 'remove.svg')),
            QIcon(str(_ASSETS / 'remove-hover.svg')),
        )
        self._remove_btn.setObjectName('fileItemRemove')
        self._remove_btn.setFixedSize(20, 20)
        self._remove_btn.hide()
        self._remove_btn.clicked.connect(lambda: self.remove_mapping.emit(self._field))
        layout.addWidget(self._remove_btn)

    def set_mapped(self, excel_col: str | None):
        if excel_col:
            self._map_lbl.setText(excel_col)
            self._map_lbl.setObjectName('fieldRowMapped')
            self._rule_combo.show()
            self._remove_btn.show()
        else:
            self._map_lbl.setText('未匹配')
            self._map_lbl.setObjectName('fieldRowUnmapped')
            self._rule_combo.setCurrentIndex(0)
            self._rule_combo.hide()
            self._remove_btn.hide()
        self._map_lbl.style().unpolish(self._map_lbl)
        self._map_lbl.style().polish(self._map_lbl)

    def set_available_rules(self, rules: list[CompareRule]) -> None:
        current_name = self._rule_combo.currentText()
        self._rule_combo.clear()
        self._rule_combo.addItem('（默认）')
        for rule in rules:
            self._rule_combo.addItem(rule.name)
        self._rules = rules
        idx = self._rule_combo.findText(current_name)
        self._rule_combo.setCurrentIndex(idx if idx >= 0 else 0)

    def selected_rule(self) -> CompareRule | None:
        idx = self._rule_combo.currentIndex()
        if idx <= 0 or idx - 1 >= len(self._rules):
            return None
        return self._rules[idx - 1]

    def set_pending(self, pending: bool):
        self.setProperty('pending', pending)
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked_field.emit(self._field)
        super().mousePressEvent(event)


class _MappingWidget(QWidget):
    mapping_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._selected_col: str | None = None
        self._mapping: dict[str, str] = {}
        self._reverse: dict[str, str] = {}
        self._tags: dict[str, _MatchTag] = {}
        self._field_rows: dict[str, _FieldRow] = {}
        self._build_ui()

    def _build_ui(self):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Left panel — Excel header tags (flow layout, equal width) ──────
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 10, 0)
        lv.setSpacing(4)

        left_title = QLabel('Excel 表头  （点击选中）')
        left_title.setObjectName('sectionTitle')
        lv.addWidget(left_title)

        # Tags container uses flow layout; placed inside a vertical-only scroll area
        self._tags_container = QWidget()
        self._flow_layout = _FlowLayout(self._tags_container, h_spacing=6, v_spacing=6)
        self._flow_layout.setContentsMargins(2, 4, 2, 4)

        tags_scroll = QScrollArea()
        tags_scroll.setObjectName('tagsScroll')
        tags_scroll.setWidgetResizable(True)
        tags_scroll.setWidget(self._tags_container)
        tags_scroll.setFrameShape(QFrame.Shape.NoFrame)
        tags_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        tags_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        lv.addWidget(tags_scroll, 1)

        outer.addWidget(left, 1)  # equal stretch

        # ── Separator ──────────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        outer.addWidget(sep)

        # ── Right panel — lrmx field rows ──────────────────────────────────
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(10, 0, 0, 0)
        rv.setSpacing(4)

        right_title = QLabel('任免表字段  （点击接收匹配）')
        right_title.setObjectName('sectionTitle')
        rv.addWidget(right_title)

        self._fields_scroll = QScrollArea()
        self._fields_scroll.setWidgetResizable(True)
        self._fields_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._fields_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._fields_container = QWidget()
        self._fields_vbox = QVBoxLayout(self._fields_container)
        self._fields_vbox.setContentsMargins(0, 0, 0, 0)
        self._fields_vbox.setSpacing(2)
        self._fields_vbox.addStretch()
        self._fields_scroll.setWidget(self._fields_container)
        rv.addWidget(self._fields_scroll, 1)

        outer.addWidget(right, 1)  # equal stretch

    def load_excel_cols(self, cols: list[str]):
        while self._flow_layout.count():
            item = self._flow_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._tags.clear()
        self._mapping.clear()
        self._reverse.clear()
        self._selected_col = None

        for col in cols:
            if not col or not col.strip():
                continue
            tag = _MatchTag(col)
            tag.clicked_tag.connect(self._on_tag_clicked)
            self._tags[col] = tag
            self._flow_layout.addWidget(tag)
            # 必须显式 show()：新建的 tag 在事件循环处理 show 事件前 isVisible()
            # 为 False，而 _FlowLayout._arrange 会跳过不可见项，导致所有 tag 停在
            # 默认 (0,0,640,480) 几何、堆叠成「一个标签占满整栏」，须点击才恢复。
            tag.show()

        self._tags_container.updateGeometry()

        for fr in self._field_rows.values():
            fr.set_mapped(None)
            fr.set_pending(False)

        self.mapping_changed.emit()

    def load_lrmx_fields(self, fields: list[tuple[str, str]]):
        while self._fields_vbox.count():
            item = self._fields_vbox.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._field_rows.clear()
        self._mapping.clear()
        self._reverse.clear()
        self._selected_col = None

        for tag, display in fields:
            row = _FieldRow(tag, display)
            row.clicked_field.connect(self._on_field_clicked)
            row.remove_mapping.connect(self._remove_mapping)
            self._field_rows[tag] = row
            self._fields_vbox.addWidget(row)
        self._fields_vbox.addStretch()

        self.mapping_changed.emit()

    def apply_presets(self, presets: dict[str, list[str]]):
        """Auto-map excel cols to lrmx fields using alias presets.
        Only maps where both sides are currently unmapped."""
        col_set = set(self._tags.keys())
        for lrmx_tag, aliases in presets.items():
            if lrmx_tag in self._reverse:
                continue
            if lrmx_tag not in self._field_rows:
                continue
            for alias in aliases:
                alias = alias.strip()
                if alias in col_set and alias not in self._mapping:
                    self._mapping[alias] = lrmx_tag
                    self._reverse[lrmx_tag] = alias
                    self._tags[alias].hide()
                    self._field_rows[lrmx_tag].set_mapped(alias)
                    break
        self.mapping_changed.emit()

    def _on_tag_clicked(self, col: str):
        if col in self._mapping:
            return
        if self._selected_col == col:
            # Deselect
            self._tags[col].set_selected(False)
            self._selected_col = None
            self._clear_pending()
        else:
            if self._selected_col and self._selected_col in self._tags:
                self._tags[self._selected_col].set_selected(False)
            self._selected_col = col
            self._tags[col].set_selected(True)
            self._update_pending()

    def _on_field_clicked(self, lrmx_field: str):
        if not self._selected_col:
            return
        if lrmx_field in self._reverse:
            return
        col = self._selected_col
        self._mapping[col] = lrmx_field
        self._reverse[lrmx_field] = col
        self._tags[col].hide()
        self._field_rows[lrmx_field].set_mapped(col)
        self._selected_col = None
        self._tags[col].set_selected(False)
        self._clear_pending()
        self.mapping_changed.emit()

    def _remove_mapping(self, lrmx_field: str):
        if lrmx_field not in self._reverse:
            return
        col = self._reverse.pop(lrmx_field)
        self._mapping.pop(col, None)
        if col in self._tags:
            self._tags[col].show()
            self._tags[col].set_selected(False)
        self._field_rows[lrmx_field].set_mapped(None)
        self.mapping_changed.emit()

    def _update_pending(self):
        for field, row in self._field_rows.items():
            if field not in self._reverse:
                row.set_pending(True)

    def _clear_pending(self):
        for row in self._field_rows.values():
            row.set_pending(False)

    def get_mapping(self) -> dict[str, str]:
        return dict(self._mapping)

    def set_available_rules(self, rules: list[CompareRule]) -> None:
        for row in self._field_rows.values():
            row.set_available_rules(rules)

    def get_rule_mapping(self) -> dict[str, CompareRule]:
        result: dict[str, CompareRule] = {}
        for lrmx_field, row in self._field_rows.items():
            if lrmx_field in self._reverse:
                rule = row.selected_rule()
                if rule is not None:
                    result[lrmx_field] = rule
        return result

    def clear_all(self):
        for lrmx_field in list(self._reverse.keys()):
            self._remove_mapping(lrmx_field)
        self._selected_col = None
