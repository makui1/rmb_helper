from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QStackedWidget, QFrame,
)
from PySide6.QtCore import Qt, QPoint, QSize
from PySide6.QtGui import QIcon

from app.ui.style import QSS
from app.ui.tabs.settings_tab import SettingsTab

_ASSETS = Path(__file__).parent / 'assets'


class _TitleBar(QWidget):
    """Frameless title bar: drag to move, double-click to maximize/restore."""

    def __init__(self, window: QMainWindow):
        super().__init__(window)
        self._win = window
        self._drag_pos: QPoint | None = None
        self.setFixedHeight(30)
        self.setObjectName('titleBar')

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(0)

        # ── 左侧区域：应用图标 + 分隔线 + 折叠按钮
        app_icon = QLabel()
        app_icon.setPixmap(QIcon(str(_ASSETS / 'icon.ico')).pixmap(QSize(18, 18)))
        app_icon.setFixedSize(26, 30)
        app_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        app_icon.setStyleSheet('background: transparent;')
        layout.addWidget(app_icon)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setObjectName('titleBarSep')
        sep.setFixedSize(1, 16)
        layout.addSpacing(6)
        layout.addWidget(sep, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addSpacing(6)

        self._toggle_btn = QPushButton()
        self._toggle_btn.setIcon(QIcon(str(_ASSETS / 'collapse.svg')))
        self._toggle_btn.setIconSize(QSize(20, 20))
        self._toggle_btn.setObjectName('winBtn')
        self._toggle_btn.setFixedSize(32, 26)
        self._toggle_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._toggle_btn.clicked.connect(lambda: window.toggle_sidebar())
        layout.addWidget(self._toggle_btn)

        # ── 中央：软件名居中
        layout.addStretch(1)
        title_label = QLabel('任免表工具箱')
        title_label.setObjectName('titleBarAppName')
        layout.addWidget(title_label)
        layout.addStretch(1)

        # ── 右侧：最小化 + 关闭
        for icon_file, slot, obj in [
            ('minimize.svg', window.showMinimized, 'winBtn'),
            ('close.svg',    window.close,         'winBtnClose'),
        ]:
            btn = QPushButton()
            btn.setIcon(QIcon(str(_ASSETS / icon_file)))
            btn.setIconSize(QSize(16, 16))
            btn.setObjectName(obj)
            btn.setFixedSize(32, 26)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.clicked.connect(slot)
            layout.addWidget(btn)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = (
                event.globalPosition().toPoint() - self._win.frameGeometry().topLeft()
            )
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() == Qt.MouseButton.LeftButton:
            self._win.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def set_collapsed(self, collapsed: bool):
        icon_file = 'unfold.svg' if collapsed else 'collapse.svg'
        self._toggle_btn.setIcon(QIcon(str(_ASSETS / icon_file)))

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._win.isMaximized():
                self._win.showNormal()
            else:
                self._win.showMaximized()
        super().mouseDoubleClickEvent(event)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('干部任免审批表管理工具')
        self.setMinimumSize(860, 580)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setWindowIcon(QIcon(str(_ASSETS / 'icon.ico')))
        self.setStyleSheet(QSS)
        self._sidebar_container: QWidget | None = None
        self._title_bar: _TitleBar | None = None
        self._build_ui()

    def _build_ui(self):
        root_widget = QWidget()
        self.setCentralWidget(root_widget)
        root = QVBoxLayout(root_widget)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── 自定义标题栏 ──────────────────────────────────────────────────
        self._title_bar = _TitleBar(self)
        root.addWidget(self._title_bar)

        # ── 主体（侧边栏 + 内容区） ───────────────────────────────────────
        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # 侧边栏外层容器：提供四周 margin，背景透明，使卡片浮在窗口上
        sidebar_container = QWidget()
        sidebar_container.setObjectName('sidebarContainer')
        sidebar_container.setFixedWidth(172)  # 8 margin + 156 card + 8 margin
        sc_layout = QVBoxLayout(sidebar_container)
        sc_layout.setContentsMargins(8, 8, 8, 8)
        sc_layout.setSpacing(0)

        # 侧边栏卡片（圆角矩形）
        sidebar = QWidget()
        sidebar.setObjectName('sidebar')
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(0, 8, 0, 8)
        sb_layout.setSpacing(0)

        self._nav_btns: list[QPushButton] = []
        for label, icon in [
            ('批量转换', 'convert.svg'),
            ('批量更新', 'update.svg'),
            ('版本兼容', 'compat.svg'),
        ]:
            btn = self._make_nav_btn(label, icon=icon)
            sb_layout.addWidget(btn)
            self._nav_btns.append(btn)

        sb_layout.addStretch()

        settings_btn = self._make_nav_btn('设置', icon='setting.svg')
        sb_layout.addWidget(settings_btn)
        self._nav_btns.append(settings_btn)

        sc_layout.addWidget(sidebar)
        self._sidebar_container = sidebar_container

        # 内容区
        from app.ui.tabs.convert_tab import ConvertTab
        from app.ui.tabs.update_tab import UpdateTab
        from app.ui.tabs.compat_tab import CompatTab

        self._stack = QStackedWidget()
        self._stack.addWidget(ConvertTab())
        self._stack.addWidget(UpdateTab())
        self._stack.addWidget(CompatTab())
        self._stack.addWidget(SettingsTab())

        body_layout.addWidget(sidebar_container)
        body_layout.addWidget(self._stack)
        root.addWidget(body)

        self._switch_tab(0)

    def toggle_sidebar(self):
        if self._sidebar_container:
            visible = self._sidebar_container.isVisible()
            self._sidebar_container.setVisible(not visible)
            if self._title_bar:
                self._title_bar.set_collapsed(visible)

    def _make_nav_btn(self, label: str, icon: str | None = None) -> QPushButton:
        idx = len(self._nav_btns) if hasattr(self, '_nav_btns') else 0
        btn = QPushButton(label)
        btn.setObjectName('navBtn')
        btn.setCheckable(True)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        if icon:
            btn.setIcon(QIcon(str(_ASSETS / icon)))
            btn.setIconSize(QSize(16, 16))
        btn.clicked.connect(lambda _, i=idx: self._switch_tab(i))
        return btn

    def _switch_tab(self, index: int):
        self._stack.setCurrentIndex(index)
        for i, btn in enumerate(self._nav_btns):
            btn.setChecked(i == index)
