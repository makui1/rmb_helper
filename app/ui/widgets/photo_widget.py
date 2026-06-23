import base64

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QDialog, QFileDialog, QPushButton, QSlider,
)
from PySide6.QtCore import (
    Qt, Signal, QRect, QPoint, QPointF, QBuffer, QByteArray, QIODevice,
)
from PySide6.QtGui import QPixmap, QPainter, QPen, QColor

_PHOTO_W = 134
_PHOTO_H = 28*6  # 4:5 预览尺寸


class _ClickLabel(QLabel):
    """可点击的照片框。"""
    clicked = Signal()

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(ev)


class _CropCanvas(QWidget):
    """固定居中的 4:5 裁剪框，图片可在框后缩放/平移。"""

    zoom_changed = Signal(float)

    def __init__(self, pixmap: QPixmap, parent=None):
        super().__init__(parent)
        self._orig = pixmap
        self._zoom = 1.0
        self._offset = QPointF(0, 0)   # 图片左上角在画布中的坐标
        self._frame = QRect()
        self._dragging = False
        self._last = QPoint()
        self.setMinimumSize(440, 560)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    # ── 布局/换算 ────────────────────────────────────────────────────────────

    def resizeEvent(self, ev):
        self._frame = self._frame_rect()
        self._recenter()
        super().resizeEvent(ev)

    def _frame_rect(self) -> QRect:
        m = 30
        aw = max(self.width() - 2 * m, 10)
        ah = max(self.height() - 2 * m, 10)
        fw = aw
        fh = int(fw * 5 / 4)
        if fh > ah:
            fh = ah
            fw = int(fh * 4 / 5)
        return QRect((self.width() - fw) // 2, (self.height() - fh) // 2, fw, fh)

    def _base_scale(self) -> float:
        if self._orig.width() == 0 or self._orig.height() == 0:
            return 1.0
        # 让图片至少铺满裁剪框
        return max(self._frame.width() / self._orig.width(),
                   self._frame.height() / self._orig.height())

    def _scale(self) -> float:
        return self._base_scale() * self._zoom

    def _recenter(self):
        s = self._scale()
        iw = self._orig.width() * s
        ih = self._orig.height() * s
        fc = self._frame.center()
        self._offset = QPointF(fc.x() - iw / 2, fc.y() - ih / 2)
        self._clamp()

    def _clamp(self):
        """保证图片始终覆盖裁剪框（不留空白）。"""
        s = self._scale()
        iw = self._orig.width() * s
        ih = self._orig.height() * s
        fr = self._frame
        x, y = self._offset.x(), self._offset.y()
        x = min(x, fr.left())
        y = min(y, fr.top())
        if x + iw < fr.right():
            x = fr.right() - iw
        if y + ih < fr.bottom():
            y = fr.bottom() - ih
        self._offset = QPointF(x, y)

    # ── 缩放 ─────────────────────────────────────────────────────────────────

    def zoom(self) -> float:
        return self._zoom

    def set_zoom(self, z: float):
        z = max(1.0, min(z, 6.0))
        if abs(z - self._zoom) < 1e-4:
            return
        fc = self._frame.center()
        s0 = self._scale()
        # 裁剪框中心对应的原图坐标，缩放后保持不变
        px = (fc.x() - self._offset.x()) / s0
        py = (fc.y() - self._offset.y()) / s0
        self._zoom = z
        s1 = self._scale()
        self._offset = QPointF(fc.x() - px * s1, fc.y() - py * s1)
        self._clamp()
        self.update()
        self.zoom_changed.emit(self._zoom)

    def wheelEvent(self, ev):
        self.set_zoom(self._zoom * (1.0015 ** ev.angleDelta().y()))

    # ── 拖动平移 ─────────────────────────────────────────────────────────────

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._last = ev.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, ev):
        if self._dragging:
            p = ev.position().toPoint()
            d = p - self._last
            self._last = p
            self._offset = QPointF(self._offset.x() + d.x(), self._offset.y() + d.y())
            self._clamp()
            self.update()

    def mouseReleaseEvent(self, _ev):
        self._dragging = False
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    # ── 绘制 ─────────────────────────────────────────────────────────────────

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor('#2B2B2B'))
        s = self._scale()
        target = QRect(int(self._offset.x()), int(self._offset.y()),
                       int(self._orig.width() * s), int(self._orig.height() * s))
        p.drawPixmap(target, self._orig)

        fr = self._frame
        p.setOpacity(0.55)
        p.fillRect(QRect(0, 0, self.width(), fr.top()), QColor(0, 0, 0))
        p.fillRect(QRect(0, fr.bottom() + 1, self.width(),
                         self.height() - fr.bottom() - 1), QColor(0, 0, 0))
        p.fillRect(QRect(0, fr.top(), fr.left(), fr.height()), QColor(0, 0, 0))
        p.fillRect(QRect(fr.right() + 1, fr.top(),
                         self.width() - fr.right() - 1, fr.height()), QColor(0, 0, 0))
        p.setOpacity(1.0)
        p.setPen(QPen(QColor('#D85A30'), 2))
        p.drawRect(fr)
        p.end()

    def crop_in_orig(self) -> QRect:
        s = self._scale()
        fr = self._frame
        rect = QRect(
            round((fr.left() - self._offset.x()) / s),
            round((fr.top() - self._offset.y()) / s),
            round(fr.width() / s),
            round(fr.height() / s),
        )
        return rect.intersected(self._orig.rect())


class CropDialog(QDialog):
    def __init__(self, pixmap: QPixmap, parent=None):
        super().__init__(parent)
        self.setWindowTitle('调整照片（4:5）')
        self.setMinimumSize(520, 680)
        self._pixmap = pixmap
        self._result: QPixmap | None = None

        lay = QVBoxLayout(self)
        self._canvas = _CropCanvas(pixmap)
        lay.addWidget(self._canvas, 1)

        # ── 缩放控制 ───────────────────────────────────────────────────────
        zoom_row = QHBoxLayout()
        zoom_row.addWidget(QLabel('缩放'))
        minus = QPushButton('－')
        minus.setFixedWidth(32)
        minus.clicked.connect(lambda: self._canvas.set_zoom(self._canvas.zoom() - 0.2))
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(100, 600)   # 1.0x – 6.0x
        self._slider.setValue(100)
        self._slider.valueChanged.connect(lambda v: self._canvas.set_zoom(v / 100))
        plus = QPushButton('＋')
        plus.setFixedWidth(32)
        plus.clicked.connect(lambda: self._canvas.set_zoom(self._canvas.zoom() + 0.2))
        self._canvas.zoom_changed.connect(
            lambda z: self._slider.setValue(int(round(z * 100))))
        zoom_row.addWidget(minus)
        zoom_row.addWidget(self._slider, 1)
        zoom_row.addWidget(plus)
        lay.addLayout(zoom_row)

        hint = QLabel('滚轮或拖动滑块缩放，拖动照片平移；橙色框内为最终 4:5 区域')
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet('color: #888; font-size: 11px;')
        lay.addWidget(hint)

        btns = QHBoxLayout()
        btns.addStretch()
        cancel = QPushButton('取消')
        cancel.clicked.connect(self.reject)
        ok = QPushButton('确认')
        ok.setObjectName('primary')
        ok.clicked.connect(self._confirm)
        btns.addWidget(cancel)
        btns.addWidget(ok)
        lay.addLayout(btns)

    def _confirm(self):
        rect = self._canvas.crop_in_orig()
        if rect.isValid() and rect.width() > 0 and rect.height() > 0:
            self._result = self._pixmap.copy(rect)
        self.accept()

    def cropped(self) -> QPixmap | None:
        return self._result


class PhotoWidget(QWidget):
    """照片预览，点击照片框即可更换。changed 信号发出新的 base64 字符串。"""

    changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._b64 = ''
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._label = _ClickLabel()
        self._label.setFixedSize(_PHOTO_W, _PHOTO_H)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet('border: 1px solid #ccc; background: #f0efe9; color: #999;')
        self._label.setText('点击\n上传照片')
        self._label.setCursor(Qt.CursorShape.PointingHandCursor)
        self._label.setToolTip('点击更换照片')
        self._label.clicked.connect(self._pick)
        lay.addWidget(self._label, 0, Qt.AlignmentFlag.AlignHCenter)

    # ── public API ───────────────────────────────────────────────────────────

    def set_b64(self, b64: str) -> None:
        self._b64 = b64
        if b64:
            self._show(b64)
        else:
            self._label.setPixmap(QPixmap())
            self._label.setText('点击\n上传照片')

    def b64(self) -> str:
        return self._b64

    # ── internals ──────────────────────────────────────────────────────────────

    def _show(self, b64: str) -> None:
        try:
            pm = QPixmap()
            pm.loadFromData(base64.b64decode(b64))
            if not pm.isNull():
                self._label.setPixmap(pm.scaled(
                    _PHOTO_W, _PHOTO_H,
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

        dlg = CropDialog(pm, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        result = dlg.cropped()
        if result is None or result.isNull():
            return

        ba = self._encode(result, 85)
        if len(ba) > 5 * 1024 * 1024:   # 超过 5MB 再压一档
            ba = self._encode(result, 55)

        b64 = base64.b64encode(bytes(ba)).decode()
        self._b64 = b64
        self._show(b64)
        self.changed.emit(b64)

    @staticmethod
    def _encode(pm: QPixmap, quality: int) -> QByteArray:
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        pm.toImage().save(buf, 'JPEG', quality)
        buf.close()
        return ba
