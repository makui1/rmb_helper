import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QStackedWidget, QFrame, QSplitter,
    QApplication,
)
from PySide6.QtCore import Qt, QPoint, QSize, QEvent
from PySide6.QtGui import QIcon, QCursor
from app.ui.widgets.file_panel import LrmxFilePanel

from app.ui.style import QSS
from app.ui.tabs.settings_tab import SettingsTab

_ASSETS = Path(__file__).parent / 'assets'

if sys.platform == 'win32':
    import ctypes
    import ctypes.wintypes as _wt

    class _MSG(ctypes.Structure):
        _fields_ = [
            ('hWnd',    _wt.HWND),
            ('message', _wt.UINT),
            ('wParam',  _wt.WPARAM),
            ('lParam',  _wt.LPARAM),
            ('time',    _wt.DWORD),
            ('pt',      _wt.POINT),
        ]

    _WM_NCHITTEST  = 0x0084
    _WM_SYSCOMMAND = 0x0112
    _SC_MINIMIZE   = 0xF020
    _SC_MAXIMIZE   = 0xF030
    _SC_RESTORE    = 0xF120

    _HTCLIENT      = 1
    _HTCAPTION     = 2
    _HTMAXBUTTON   = 9
    _HTLEFT        = 10
    _HTRIGHT       = 11
    _HTTOP         = 12
    _HTTOPLEFT     = 13
    _HTTOPRIGHT    = 14
    _HTBOTTOM      = 15
    _HTBOTTOMLEFT  = 16
    _HTBOTTOMRIGHT = 17


class _TitleBar(QWidget):
    """Frameless title bar: drag to move, double-click to maximize/restore."""

    def __init__(self, window: QMainWindow):
        super().__init__(window)
        self._win = window
        self._drag_pos: QPoint | None = None
        self._drag_from_maximized: bool = False
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
        title_label = QLabel('任 免 表 工 具 箱')
        title_label.setObjectName('titleBarAppName')
        layout.addWidget(title_label)
        layout.addStretch(1)

        # ── 右侧：最小化 + 最大化/还原 + 关闭
        min_btn = QPushButton()
        min_btn.setIcon(QIcon(str(_ASSETS / 'minimize.svg')))
        min_btn.setIconSize(QSize(16, 16))
        min_btn.setObjectName('winBtn')
        min_btn.setFixedSize(32, 26)
        min_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        min_btn.clicked.connect(window.showMinimized)
        layout.addWidget(min_btn)

        self._max_btn = QPushButton()
        self._max_btn.setIcon(QIcon(str(_ASSETS / 'maximize.svg')))
        self._max_btn.setIconSize(QSize(16, 16))
        self._max_btn.setObjectName('winBtn')
        self._max_btn.setFixedSize(32, 26)
        self._max_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._max_btn.clicked.connect(window.toggle_maximize)
        layout.addWidget(self._max_btn)

        close_btn = QPushButton()
        close_btn.setIcon(QIcon(str(_ASSETS / 'close.svg')))
        close_btn.setIconSize(QSize(16, 16))
        close_btn.setObjectName('winBtnClose')
        close_btn.setFixedSize(32, 26)
        close_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        close_btn.clicked.connect(window.close)
        layout.addWidget(close_btn)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = (
                event.globalPosition().toPoint() - self._win.frameGeometry().topLeft()
            )
            self._drag_from_maximized = self._win.isMaximized()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos is None or event.buttons() != Qt.MouseButton.LeftButton:
            super().mouseMoveEvent(event)
            return
        global_pos = event.globalPosition().toPoint()
        if self._drag_from_maximized:
            ratio = self._drag_pos.x() / max(self._win.width(), 1)
            self._win.showNormal()
            self._drag_pos = QPoint(
                int(ratio * self._win.width()),
                self._drag_pos.y(),
            )
            self._drag_from_maximized = False
        self._win.move(global_pos - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        self._drag_from_maximized = False
        super().mouseReleaseEvent(event)

    def set_collapsed(self, collapsed: bool):
        icon_file = 'unfold.svg' if collapsed else 'collapse.svg'
        self._toggle_btn.setIcon(QIcon(str(_ASSETS / icon_file)))

    def set_maximized(self, is_max: bool):
        icon_file = 'unmaximize.svg' if is_max else 'maximize.svg'
        self._max_btn.setIcon(QIcon(str(_ASSETS / icon_file)))

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._win.toggle_maximize()
        super().mouseDoubleClickEvent(event)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('干部任免审批表管理工具')
        self.resize(1250, 700)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setWindowIcon(QIcon(str(_ASSETS / 'icon.ico')))
        self.setStyleSheet(QSS)
        self._sidebar_container: QWidget | None = None
        self._title_bar: _TitleBar | None = None
        self._file_panel: LrmxFilePanel | None = None
        self._resize_cursor_set: bool = False
        self._build_ui()
        if sys.platform != 'win32':
            QApplication.instance().installEventFilter(self)

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
        sidebar_container.setFixedWidth(190)  # 8 margin + 156 card + 8 margin
        sc_layout = QVBoxLayout(sidebar_container)
        sc_layout.setContentsMargins(8, 15, 8, 15)
        sc_layout.setSpacing(0)

        # 侧边栏卡片（圆角矩形）
        sidebar = QWidget()
        sidebar.setObjectName('sidebar')
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(0, 15, 0, 15)
        sb_layout.setSpacing(0)

        self._nav_btns: list[QPushButton] = []
        for label, icon in [
            ('批量格式转换', 'convert.svg'),
            ('批量版本兼容', 'compat.svg'),
            ('批量核验/更新', 'verify.svg'),
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
        from app.ui.tabs.compat_tab import CompatTab
        from app.ui.tabs.verify_tab import VerifyTab

        self._file_panel = LrmxFilePanel()
        self._file_panel.setMinimumWidth(180)
        self._file_panel.setContentsMargins(8,15,0,15)

        convert_tab = ConvertTab(self._file_panel)
        compat_tab = CompatTab(self._file_panel)
        verify_tab = VerifyTab(self._file_panel)

        self._stack = QStackedWidget()
        self._stack.addWidget(convert_tab)    # index 0 → 批量转换
        self._stack.addWidget(compat_tab)     # index 1 → 版本兼容
        self._stack.addWidget(verify_tab)     # index 2 → 批量核验
        self._stack.addWidget(SettingsTab())  # index 3 → 设置

        for tab in (convert_tab, compat_tab, verify_tab):
            tab.busy_changed.connect(lambda busy: self._file_panel.setEnabled(not busy))

        content_splitter = QSplitter(Qt.Orientation.Horizontal)
        content_splitter.setChildrenCollapsible(False)
        content_splitter.setHandleWidth(4)
        content_splitter.addWidget(self._file_panel)
        content_splitter.addWidget(self._stack)
        content_splitter.setSizes([220, 700])

        body_layout.addWidget(sidebar_container)
        body_layout.addWidget(content_splitter, 1)
        root.addWidget(body)

        self._switch_tab(0)

    def toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def changeEvent(self, event):
        if event.type() == QEvent.Type.WindowStateChange and self._title_bar:
            self._title_bar.set_maximized(self.isMaximized())
        super().changeEvent(event)

    def nativeEvent(self, event_type, message):
        if sys.platform == 'win32':
            import ctypes
            msg = _MSG.from_address(int(message))

            if msg.message == _WM_NCHITTEST:
                sx = ctypes.c_short(msg.lParam & 0xFFFF).value
                sy = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
                local = self.mapFromGlobal(QPoint(sx, sy))
                x, y, w, h, m = local.x(), local.y(), self.width(), self.height(), 8

                if not self.isMaximized():
                    if x < m and y < m:        return True, _HTTOPLEFT
                    if x > w-m and y < m:      return True, _HTTOPRIGHT
                    if x < m and y > h-m:      return True, _HTBOTTOMLEFT
                    if x > w-m and y > h-m:    return True, _HTBOTTOMRIGHT
                    if x < m:                  return True, _HTLEFT
                    if x > w-m:                return True, _HTRIGHT
                    if y < m:                  return True, _HTTOP
                    if y > h-m:                return True, _HTBOTTOM

                if self._title_bar and y <= self._title_bar.height():
                    tb_pos = self._title_bar.mapFromGlobal(QPoint(sx, sy))
                    child = self._title_bar.childAt(tb_pos)
                    # 只有 QPushButton 保留 HTCLIENT 让 Qt 处理点击
                    # Label / Frame / 空白区域全部返回 HTCAPTION 让 Windows 处理拖拽 & Snap
                    if isinstance(child, QPushButton):
                        return True, _HTCLIENT
                    return True, _HTCAPTION

                return True, _HTCLIENT

            elif msg.message == 0x00A3:  # WM_NCLBUTTONDBLCLK
                if msg.wParam == _HTCAPTION:
                    self.toggle_maximize()
                    return True, 0

        return super().nativeEvent(event_type, message)

    _RESIZE_MARGIN = 8

    _CURSOR_MAP = {
        Qt.Edge.LeftEdge:                                Qt.CursorShape.SizeHorCursor,
        Qt.Edge.RightEdge:                               Qt.CursorShape.SizeHorCursor,
        Qt.Edge.TopEdge:                                 Qt.CursorShape.SizeVerCursor,
        Qt.Edge.BottomEdge:                              Qt.CursorShape.SizeVerCursor,
        Qt.Edge.LeftEdge  | Qt.Edge.TopEdge:             Qt.CursorShape.SizeFDiagCursor,
        Qt.Edge.RightEdge | Qt.Edge.BottomEdge:          Qt.CursorShape.SizeFDiagCursor,
        Qt.Edge.RightEdge | Qt.Edge.TopEdge:             Qt.CursorShape.SizeBDiagCursor,
        Qt.Edge.LeftEdge  | Qt.Edge.BottomEdge:          Qt.CursorShape.SizeBDiagCursor,
    }

    def _edge_at(self, pos: QPoint) -> Qt.Edges:
        x, y, w, h = pos.x(), pos.y(), self.width(), self.height()
        m = self._RESIZE_MARGIN
        edges = Qt.Edges()
        if x < m:      edges |= Qt.Edge.LeftEdge
        if x > w - m:  edges |= Qt.Edge.RightEdge
        if y < m:      edges |= Qt.Edge.TopEdge
        if y > h - m:  edges |= Qt.Edge.BottomEdge
        return edges

    def eventFilter(self, watched, event):
        t = event.type()
        if t == QEvent.Type.MouseMove:
            local = self.mapFromGlobal(event.globalPosition().toPoint())
            if not self.isMaximized() and self.rect().contains(local):
                edges = self._edge_at(local)
                if edges:
                    shape = self._CURSOR_MAP.get(edges, Qt.CursorShape.ArrowCursor)
                    if self._resize_cursor_set:
                        QApplication.changeOverrideCursor(QCursor(shape))
                    else:
                        QApplication.setOverrideCursor(QCursor(shape))
                        self._resize_cursor_set = True
                else:
                    self._clear_resize_cursor()
            else:
                self._clear_resize_cursor()
        elif t == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton and not self.isMaximized():
                local = self.mapFromGlobal(event.globalPosition().toPoint())
                if self.rect().contains(local):
                    edges = self._edge_at(local)
                    if edges:
                        wh = self.windowHandle()
                        if wh:
                            wh.startSystemResize(edges)
                        return True
        return False

    def _clear_resize_cursor(self):
        if self._resize_cursor_set:
            QApplication.restoreOverrideCursor()
            self._resize_cursor_set = False

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
        if self._file_panel:
            widget = self._stack.widget(index)
            self._file_panel.setVisible(getattr(widget, 'USES_FILE_PANEL', False))
