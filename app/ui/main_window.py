from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout,
    QListWidget, QListWidgetItem, QStackedWidget,
)
from PySide6.QtCore import Qt, QSize

from app.ui.style import QSS
from app.ui.tabs.settings_tab import SettingsTab


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('干部任免审批表管理工具')
        self.setMinimumSize(860, 580)
        self.setStyleSheet(QSS)
        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 左侧导航
        self._sidebar = QListWidget()
        self._sidebar.setObjectName('sidebar')
        self._sidebar.setFixedWidth(160)
        self._sidebar.setSpacing(2)

        nav_items = [
            ('转换导出', ''),
            ('批量更新', ''),
            ('设置', ''),
        ]
        for label, icon_path in nav_items:
            item = QListWidgetItem(label)
            item.setSizeHint(QSize(160, 36))
            self._sidebar.addItem(item)
        self._sidebar.setCurrentRow(0)
        self._sidebar.currentRowChanged.connect(self._switch_tab)

        # 右侧内容区（延迟导入避免循环）
        from app.ui.tabs.convert_tab import ConvertTab
        from app.ui.tabs.update_tab import UpdateTab

        self._stack = QStackedWidget()
        self._convert_tab = ConvertTab()
        self._update_tab = UpdateTab()
        self._settings_tab = SettingsTab()

        self._stack.addWidget(self._convert_tab)
        self._stack.addWidget(self._update_tab)
        self._stack.addWidget(self._settings_tab)

        root.addWidget(self._sidebar)
        root.addWidget(self._stack)

    def _switch_tab(self, index: int):
        self._stack.setCurrentIndex(index)
