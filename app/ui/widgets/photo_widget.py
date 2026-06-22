import base64
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QLabel,
    QDialog, QFileDialog, QHBoxLayout,
)
from PySide6.QtCore import Qt, Signal, QRect, QPoint, QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QPixmap, QPainter, QPen, QColor

_PHOTO_W = 120
_PHOTO_H = 150  # 4:5 display size
_HANDLE  = 8
_CORNER_Z = 14  # hit zone radius for corner handles


class _CropCanvas(QWidget):
    """在缩小显示的图片上拖动/调整 4:5 裁剪框。"""

    def __init__(self, pixmap: QPixmap, parent=None):
        super().__init__(parent)
        self._orig = pixmap
        self._scale = 1.0
        self._img_off = QPoint(0, 0)
        self._crop = QRect()
        self._drag_mode = ''          # '' | 'move' | 'tl' | 'tr' | 'bl' | 'br'
        self._drag_anchor = QPoint()
        self._drag_crop0 = QRect()
        self.setMouseTracking(True)
        self.setMinimumSize(420, 520)

    def resizeEvent(self, ev):
        self._fit()
        super().resizeEvent(ev)

    def _fit(self):
        iw, ih = self._orig.width(), self._orig.height()
        sw, sh = self.width() - 24, self.height() - 24
        s = min(sw / max(iw, 1), sh / max(ih, 1))
        self._scale = s
        dw, dh = int(iw * s), int(ih * s)
        self._img_off = QPoint((self.width() - dw) // 2, (self.height() - dh) // 2)
        if not self._crop.isValid():
            cw = dw
            ch = int(cw * 5 / 4)
            if ch > dh:
                ch = dh
                cw = int(ch * 4 / 5)
            cx = self._img_off.x() + (dw - cw) // 2
            cy = self._img_off.y() + (dh - ch) // 2
            self._crop = QRect(cx, cy, cw, ch)

    def _img_rect(self) -> QRect:
        iw, ih = self._orig.width(), self._orig.height()
        return QRect(self._img_off.x(), self._img_off.y(),
                     int(iw * self._scale), int(ih * self._scale))

    def paintEvent(self, _ev):
        p = QPainter(self)
        ir = self._img_rect()
        scaled = self._orig.scaled(ir.width(), ir.height(),
                                   Qt.AspectRatioMode.IgnoreAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)
        p.drawPixmap(ir.topLeft(), scaled)

        p.setOpacity(0.55)
        cr = self._crop
        # four dark rectangles outside the crop
        p.fillRect(ir.left(), ir.top(), ir.width(), cr.top() - ir.top(), QColor(0, 0, 0))
        p.fillRect(ir.left(), cr.bottom() + 1, ir.width(), ir.bottom() - cr.bottom(), QColor(0, 0, 0))
        p.fillRect(ir.left(), cr.top(), cr.left() - ir.left(), cr.height(), QColor(0, 0, 0))
        p.fillRect(cr.right() + 1, cr.top(), ir.right() - cr.right(), cr.height(), QColor(0, 0, 0))
        p.setOpacity(1.0)

        p.setPen(QPen(QColor('#D85A30'), 2))
        p.drawRect(cr)

        h = _HANDLE
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor('#D85A30'))
        for cx, cy in [(cr.left(), cr.top()), (cr.right(), cr.top()),
                       (cr.left(), cr.bottom()), (cr.right(), cr.bottom())]:
            p.drawRect(cx - h // 2, cy - h // 2, h, h)
        p.end()

    def _corner_hit(self, pos: QPoint) -> str:
        z = _CORNER_Z
        r = self._crop
        corners = {'tl': (r.left(), r.top()), 'tr': (r.right(), r.top()),
                   'bl': (r.left(), r.bottom()), 'br': (r.right(), r.bottom())}
        for name, (cx, cy) in corners.items():
            if abs(pos.x() - cx) <= z and abs(pos.y() - cy) <= z:
                return name
        return ''

    def mousePressEvent(self, ev):
        if ev.button() != Qt.MouseButton.LeftButton:
            return
        pos = ev.position().toPoint()
        c = self._corner_hit(pos)
        if c:
            self._drag_mode = c
        elif self._crop.contains(pos):
            self._drag_mode = 'move'
        else:
            return
        self._drag_anchor = pos
        self._drag_crop0 = QRect(self._crop)

    def mouseMoveEvent(self, ev):
        pos = ev.position().toPoint()
        if not self._drag_mode:
            c = self._corner_hit(pos)
            if c in ('tl', 'br'):
                self.setCursor(Qt.CursorShape.SizeFDiagCursor)
            elif c in ('tr', 'bl'):
                self.setCursor(Qt.CursorShape.SizeBDiagCursor)
            elif self._crop.contains(pos):
                self.setCursor(Qt.CursorShape.SizeAllCursor)
            else:
                self.unsetCursor()
            return

        ir = self._img_rect()
        dx = pos.x() - self._drag_anchor.x()
        dy = pos.y() - self._drag_anchor.y()
        r = QRect(self._drag_crop0)

        if self._drag_mode == 'move':
            r = r.translated(dx, dy)
            if r.left() < ir.left():     r.moveLeft(ir.left())
            if r.top() < ir.top():       r.moveTop(ir.top())
            if r.right() > ir.right():   r.moveRight(ir.right())
            if r.bottom() > ir.bottom(): r.moveBottom(ir.bottom())
        else:
            m = self._drag_mode
            if m == 'br':
                nw = max(40, r.width() + dx)
                nh = int(nw * 5 / 4)
                if r.top() + nh > ir.bottom(): nh = ir.bottom() - r.top(); nw = int(nh * 4 / 5)
                r.setRight(r.left() + nw); r.setBottom(r.top() + nh)
            elif m == 'bl':
                nw = max(40, r.width() - dx)
                nh = int(nw * 5 / 4)
                if r.top() + nh > ir.bottom(): nh = ir.bottom() - r.top(); nw = int(nh * 4 / 5)
                r.setLeft(r.right() - nw); r.setBottom(r.top() + nh)
            elif m == 'tr':
                nw = max(40, r.width() + dx)
                nh = int(nw * 5 / 4)
                if r.bottom() - nh < ir.top(): nh = r.bottom() - ir.top(); nw = int(nh * 4 / 5)
                r.setRight(r.left() + nw); r.setTop(r.bottom() - nh)
            elif m == 'tl':
                nw = max(40, r.width() - dx)
                nh = int(nw * 5 / 4)
                if r.bottom() - nh < ir.top(): nh = r.bottom() - ir.top(); nw = int(nh * 4 / 5)
                r.setLeft(r.right() - nw); r.setTop(r.bottom() - nh)
            if r.left() < ir.left():     r.moveLeft(ir.left())
            if r.top() < ir.top():       r.moveTop(ir.top())
            if r.right() > ir.right():   r.setRight(ir.right())
            if r.bottom() > ir.bottom(): r.setBottom(ir.bottom())

        if r.width() >= 20 and r.height() >= 25:
            self._crop = r
        self.update()

    def mouseReleaseEvent(self, _ev):
        self._drag_mode = ''

    def crop_in_orig(self) -> QRect:
        """将裁剪框换算回原图坐标。"""
        r = self._crop
        ox, oy, s = self._img_off.x(), self._img_off.y(), self._scale
        return QRect(int((r.left() - ox) / s), int((r.top() - oy) / s),
                     int(r.width() / s), int(r.height() / s))


class CropDialog(QDialog):
    def __init__(self, pixmap: QPixmap, parent=None):
        super().__init__(parent)
        self.setWindowTitle('裁剪照片（4:5 比例）')
        self.setMinimumSize(500, 640)
        self._pixmap = pixmap
        self._result: QPixmap | None = None

        lay = QVBoxLayout(self)
        self._canvas = _CropCanvas(pixmap)
        lay.addWidget(self._canvas, 1)

        hint = QLabel('拖动裁剪框移动位置；拖动四角调整大小（自动保持 4:5）')
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet('color: #888; font-size: 11px;')
        lay.addWidget(hint)

        btns = QHBoxLayout()
        btns.addStretch()
        cancel = QPushButton('取消')
        cancel.clicked.connect(self.reject)
        ok = QPushButton('确认裁剪')
        ok.setObjectName('primaryBtn')
        ok.clicked.connect(self._confirm)
        btns.addWidget(cancel)
        btns.addWidget(ok)
        lay.addLayout(btns)

    def _confirm(self):
        rect = self._canvas.crop_in_orig()
        self._result = self._pixmap.copy(rect)
        self.accept()

    def cropped(self) -> QPixmap | None:
        return self._result


class PhotoWidget(QWidget):
    """照片预览 + 更换按钮。changed 信号发出新的 base64 字符串。"""

    changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._b64 = ''
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)

        self._label = QLabel()
        self._label.setFixedSize(_PHOTO_W, _PHOTO_H)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet('border: 1px solid #ccc; background: #f0efe9;')
        self._label.setText('暂无\n照片')
        lay.addWidget(self._label, 0, Qt.AlignmentFlag.AlignHCenter)

        btn = QPushButton('更换照片')
        btn.setFixedHeight(24)
        btn.clicked.connect(self._pick)
        lay.addWidget(btn)

    def set_b64(self, b64: str) -> None:
        self._b64 = b64
        if b64:
            self._show(b64)
        else:
            self._label.setPixmap(QPixmap())
            self._label.setText('暂无\n照片')

    def b64(self) -> str:
        return self._b64

    def _show(self, b64: str) -> None:
        try:
            pm = QPixmap()
            pm.loadFromData(base64.b64decode(b64))
            if not pm.isNull():
                self._label.setPixmap(pm.scaled(_PHOTO_W, _PHOTO_H,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation))
                self._label.setText('')
                return
        except Exception:
            pass
        self._label.setPixmap(QPixmap())
        self._label.setText('照片错误')

    def _pick(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, '选择照片', '',
            '图片文件 (*.jpg *.jpeg *.png *.bmp *.webp)')
        if not path:
            return
        pm = QPixmap(path)
        if pm.isNull():
            return
        # Check 4:5 ratio
        w, h = pm.width(), pm.height()
        if abs(w * 5 - h * 4) > max(w, h) * 0.02:
            dlg = CropDialog(pm, self)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            pm = dlg.cropped()
            if pm is None:
                return

        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        pm.toImage().save(buf, 'JPEG', 85)
        buf.close()
        if len(ba) > 5 * 1024 * 1024:
            ba = QByteArray()
            buf = QBuffer(ba)
            buf.open(QIODevice.OpenModeFlag.WriteOnly)
            pm.toImage().save(buf, 'JPEG', 55)
            buf.close()

        b64 = base64.b64encode(bytes(ba)).decode()
        self._b64 = b64
        self._show(b64)
        self.changed.emit(b64)
