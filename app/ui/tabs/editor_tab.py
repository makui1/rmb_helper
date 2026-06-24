"""任免审批表编辑器 Tab — 多标签页版本。

每个打开的 .lrmx 文件在 QTabWidget 中占一个 _DocPane。
工具栏按钮操作当前激活的 _DocPane。
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QSettings
from PySide6.QtGui import QFont, QFontMetricsF, QTextBlockFormat, QTextCursor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QLineEdit, QComboBox, QTextEdit,
    QScrollArea, QFileDialog, QMessageBox, QSizePolicy,
    QFrame, QTabWidget,
)
from app.ui.utils import show_error, show_warning


class _ScrollSafeCombo(QComboBox):
    """滚轮事件仅在控件已获得键盘焦点时生效，防止滚动页面时误改选项。"""
    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()

from app.core.dmgrp_loader import get_loader
from app.core.lrmx import LrmxFile
from app.ui.widgets.lrmx_tree import LrmxTreePanel
from app.ui.widgets.photo_widget import PhotoWidget
from app.ui.widgets.family_table import FamilyTable

USES_FILE_PANEL = False

_LW2 = 72
_ROW_H = 28


def _lbl(text: str, width: int = _LW2) -> QLabel:
    lbl = QLabel(text)
    lbl.setFixedWidth(width)
    lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    lbl.setStyleSheet('color: #555; font-size: 12px;')
    return lbl


def _line(placeholder: str = '', readonly: bool = False) -> QLineEdit:
    w = QLineEdit()
    w.setPlaceholderText(placeholder)
    w.setReadOnly(readonly)
    w.setFixedHeight(_ROW_H)
    if readonly:
        w.setStyleSheet('background: #f5f5f0; color: #888;')
    return w


def _combo(options: list[str], editable: bool = True) -> QComboBox:
    w = _ScrollSafeCombo()
    w.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    w.setEditable(editable)
    if editable:
        w.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
    w.addItem('')
    for o in options:
        w.addItem(o)
    w.setFixedHeight(_ROW_H)
    return w


def _section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        'font-size: 12px; font-weight: bold; color: #444;'
        'border-bottom: 1px solid #ddd; padding-bottom: 2px; margin-top: 4px;'
    )
    return lbl


class _ResumeEdit(QTextEdit):
    """简历编辑框：自动换行 + 18 字符悬挂缩进。"""
    _INDENT_CHARS = 18

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('resumeEdit')
        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self._apply_indent()

    def _indent_px(self) -> float:
        f = QFont()
        f.setFamilies(['NSimSun', 'SimSun', 'Consolas'])
        f.setPixelSize(13)
        return self._INDENT_CHARS * QFontMetricsF(f).horizontalAdvance('0')

    def _apply_indent(self):
        indent = self._indent_px()
        fmt = QTextBlockFormat()
        fmt.setLeftMargin(indent)
        fmt.setTextIndent(-indent)
        cur = QTextCursor(self.document())
        cur.select(QTextCursor.SelectionType.Document)
        was = self.blockSignals(True)
        cur.mergeBlockFormat(fmt)
        self.blockSignals(was)

    def setPlainText(self, text: str) -> None:
        super().setPlainText(text)
        self._apply_indent()

    def clear(self) -> None:
        super().clear()
        self._apply_indent()


class _DocPane(QWidget):
    """单文档窗格：表单 widget + 文件状态。"""

    dirty_changed = Signal(bool)   # 文件脏状态变化
    path_changed  = Signal(str)    # 文件路径变化（另存为后）

    def __init__(self, layout_mode: str = 'b', parent=None):
        super().__init__(parent)
        self._lrmx: LrmxFile | None = None
        self._current_path: str | None = None
        self._dirty = False
        self._loading = False
        self._layout_mode = layout_mode
        self._dirty_connected = False
        self._build_widgets()
        self._install_layout(layout_mode)
        self._connect_dirty()

    # ── widget 实例化（与布局无关）───────────────────────────────────────────

    def _build_widgets(self):
        loader = get_loader()
        self._xing_ming      = _line()
        self._xing_bie       = _combo(loader.options('GB22611'))
        self._chu_sheng      = _line('YYYYMM')
        self._min_zu         = _combo(loader.options('GB3304'))
        self._ji_guan        = _line()
        self._chu_di         = _line()
        self._photo          = PhotoWidget()
        self._ru_dang        = _line('YYYYMM')
        self._can_jia        = _line('YYYYMM')
        self._dao_ling       = _line(readonly=True)
        self._jian_kang      = _combo(loader.options('GB22613'))
        self._zhuan_ye       = _combo(loader.options('GB8561'))
        self._shu_xi         = _line()

        xu_li_opts   = loader.options('ZB64')
        xue_wei_opts = loader.options('GB6864')
        self._qrz_xueli       = _combo(xu_li_opts)
        self._qrz_xuewei      = _combo(xue_wei_opts)
        self._qrz_xueli_yuan  = _line()
        self._qrz_xuewei_yuan = _line()
        self._zzj_xueli       = _combo(xu_li_opts)
        self._zzj_xuewei      = _combo(xue_wei_opts)
        self._zzj_xueli_yuan  = _line()
        self._zzj_xuewei_yuan = _line()

        self._xian_ren  = _line()
        self._ni_ren    = _line()
        self._ni_mian   = _line()
        self._jian_li   = _ResumeEdit()
        self._jian_li.setMinimumHeight(200)
        self._jian_li.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._jiang_cheng = QTextEdit()
        self._jiang_cheng.setFixedHeight(80)
        self._nian_du     = QTextEdit()
        self._nian_du.setFixedHeight(80)
        self._ren_mian    = QTextEdit()
        self._ren_mian.setFixedHeight(100)

        self._family = FamilyTable()
        self._family.setMinimumHeight(180)
        self._family.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._cheng_bao     = _line()
        self._gai_ge_nll    = _combo(loader.options('NLLB'))
        self._shen_fen      = _line()
        self._ji_suan       = _line('YYYYMMDD')
        self._tian_biao_shi = _line()
        self._tian_biao_ren = _line()

    # ── 布局（两种，可运行时切换）────────────────────────────────────────────

    def _install_layout(self, mode: str):
        """保留根布局永久不变，只替换内部的滚动子组件，避免白屏。"""
        root = self.layout()
        if root is None:
            root = QVBoxLayout(self)
            root.setContentsMargins(0, 0, 0, 0)
            root.setSpacing(0)
        while root.count():
            item = root.takeAt(0)
            w = item.widget()
            if w:
                w.hide()
                w.setParent(None)  # type: ignore[arg-type]
                w.deleteLater()
        scroll = self._build_layout_a() if mode == 'a' else self._build_layout_b()
        root.addWidget(scroll)
        self._layout_mode = mode

    def _build_layout_b(self) -> QScrollArea:
        """轻量分隔式布局：简历风格单列，各节下划线分隔，照片右浮。"""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        container.setObjectName('editorFormB')
        col = QVBoxLayout(container)
        col.setContentsMargins(24, 8, 24, 24)
        col.setSpacing(0)

        def _sec(text: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setObjectName('bSecTitle')
            return lbl

        def _row(label_text: str, widget: QWidget) -> QFrame:
            frame = QFrame()
            frame.setObjectName('bFieldRow')
            lay = QHBoxLayout(frame)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(8)
            lbl = QLabel(label_text)
            lbl.setObjectName('bFieldLabel')
            lbl.setFixedWidth(84)
            lay.addWidget(lbl)
            lay.addWidget(widget, 1)
            return frame

        # ── 基本信息（照片右浮）
        col.addWidget(_sec('基本信息'))
        basic_outer = QHBoxLayout()
        basic_outer.setSpacing(16)
        basic_outer.setContentsMargins(0, 0, 0, 0)
        basic_col = QVBoxLayout()
        basic_col.setSpacing(0)
        basic_col.setContentsMargins(0, 0, 0, 0)
        for lbl_text, w in [
            ('姓名',    self._xing_ming),
            ('性别',    self._xing_bie),
            ('出生年月', self._chu_sheng),
            ('民族',    self._min_zu),
            ('籍贯',    self._ji_guan),
            ('出生地',  self._chu_di),
            ('入党时间', self._ru_dang),
            ('参工时间', self._can_jia),
            ('到龄时间', self._dao_ling),
            ('健康状况', self._jian_kang),
            ('专技职务', self._zhuan_ye),
            ('熟悉专业', self._shu_xi),
        ]:
            basic_col.addWidget(_row(lbl_text, w))
        photo_right = QVBoxLayout()
        photo_right.setContentsMargins(0, 0, 0, 0)
        photo_right.addWidget(self._photo, 0, Qt.AlignmentFlag.AlignTop)
        photo_right.addStretch()
        basic_outer.addLayout(basic_col, 1)
        basic_outer.addLayout(photo_right, 0)
        col.addLayout(basic_outer)

        # ── 学历学位
        col.addWidget(_sec('学历学位'))
        for lbl_text, w in [
            ('全日制学历', self._qrz_xueli),
            ('全日制院校', self._qrz_xueli_yuan),
            ('全日制学位', self._qrz_xuewei),
            ('全日制院校', self._qrz_xuewei_yuan),
            ('在职学历',  self._zzj_xueli),
            ('在职院校',  self._zzj_xueli_yuan),
            ('在职学位',  self._zzj_xuewei),
            ('在职院校',  self._zzj_xuewei_yuan),
        ]:
            col.addWidget(_row(lbl_text, w))

        # ── 职务
        col.addWidget(_sec('职务'))
        for lbl_text, w in [
            ('现任职务', self._xian_ren),
            ('拟任职务', self._ni_ren),
            ('拟免职务', self._ni_mian),
        ]:
            col.addWidget(_row(lbl_text, w))

        # ── 简历
        col.addWidget(_sec('简历'))
        col.addWidget(self._jian_li, 1)

        # ── 奖惩
        col.addWidget(_sec('奖惩情况'))
        col.addWidget(self._jiang_cheng)

        # ── 年度考核
        col.addWidget(_sec('年度考核结果'))
        col.addWidget(self._nian_du)

        # ── 任免理由
        col.addWidget(_sec('任免理由'))
        col.addWidget(self._ren_mian)

        # ── 家庭主要成员
        col.addWidget(_sec('家庭主要成员'))
        col.addWidget(self._family, 1)

        # ── 其他信息
        col.addWidget(_sec('其他信息'))
        for lbl_text, w in [
            ('呈报单位',  self._cheng_bao),
            ('改革前年龄', self._gai_ge_nll),
            ('身份证号',  self._shen_fen),
            ('计算年龄',  self._ji_suan),
            ('填表时间',  self._tian_biao_shi),
            ('填表人',   self._tian_biao_ren),
        ]:
            col.addWidget(_row(lbl_text, w))

        scroll.setWidget(container)
        return scroll

    def _build_la_info_grid(self, lbl_cell) -> QHBoxLayout:
        """基本信息网格 + 照片（水平布局）。"""
        info_outer = QHBoxLayout()
        info_outer.setSpacing(0)
        info_outer.setContentsMargins(0, 0, 0, 0)
        info_grid = QGridLayout()
        info_grid.setSpacing(0)
        info_grid.setContentsMargins(0, 0, 0, 0)
        info_grid.setColumnStretch(1, 1)
        info_grid.setColumnStretch(3, 1)
        for (r, c, lbl_text, w) in [
            (0, 0, '姓名',    self._xing_ming),
            (0, 2, '性别',    self._xing_bie),
            (1, 0, '出生年月', self._chu_sheng),
            (1, 2, '民族',    self._min_zu),
            (2, 0, '籍贯',    self._ji_guan),
            (2, 2, '出生地',  self._chu_di),
            (3, 0, '入党时间', self._ru_dang),
            (3, 2, '参工时间', self._can_jia),
            (4, 0, '到龄时间', self._dao_ling),
            (4, 2, '健康状况', self._jian_kang),
            (5, 0, '专技职务', self._zhuan_ye),
            (5, 2, '熟悉专业', self._shu_xi),
        ]:
            info_grid.addWidget(lbl_cell(lbl_text), r, c)
            info_grid.addWidget(w, r, c + 1)
        info_outer.addLayout(info_grid, 1)
        info_outer.addWidget(self._photo, 0, Qt.AlignmentFlag.AlignCenter)
        return info_outer

    def _build_la_edu_grid(self, lbl_cell) -> QGridLayout:
        """学历学位网格。"""
        edu_grid = QGridLayout()
        edu_grid.setSpacing(0)
        edu_grid.setContentsMargins(0, 0, 0, 0)
        edu_grid.setColumnMinimumWidth(0, 44)
        edu_grid.setColumnMinimumWidth(1, 40)
        edu_grid.setColumnStretch(2, 1)
        edu_grid.setColumnMinimumWidth(3, 92)
        edu_grid.setColumnStretch(4, 2)
        for row, (type_lbl, kind_lbl, combo_w, yuan_w) in enumerate([
            ('全日制', '学历', self._qrz_xueli,  self._qrz_xueli_yuan),
            ('全日制', '学位', self._qrz_xuewei, self._qrz_xuewei_yuan),
            ('在职',   '学历', self._zzj_xueli,  self._zzj_xueli_yuan),
            ('在职',   '学位', self._zzj_xuewei, self._zzj_xuewei_yuan),
        ]):
            tl = lbl_cell(type_lbl, 44)
            kl = lbl_cell(kind_lbl, 40)
            yl = lbl_cell('毕业院校系及专业', 92)
            edu_grid.addWidget(tl, row, 0)
            edu_grid.addWidget(kl, row, 1)
            edu_grid.addWidget(combo_w, row, 2)
            edu_grid.addWidget(yl, row, 3)
            edu_grid.addWidget(yuan_w, row, 4)
        return edu_grid

    def _build_la_pos_grid(self, lbl_cell) -> QGridLayout:
        """职务网格。"""
        pos_grid = QGridLayout()
        pos_grid.setSpacing(0)
        pos_grid.setContentsMargins(0, 0, 0, 0)
        pos_grid.setColumnMinimumWidth(0, _LW2)
        pos_grid.setColumnStretch(1, 1)
        for r, (lbl_text, w) in enumerate([
            ('现任职务', self._xian_ren),
            ('拟任职务', self._ni_ren),
            ('拟免职务', self._ni_mian),
        ]):
            pos_grid.addWidget(lbl_cell(lbl_text), r, 0)
            pos_grid.addWidget(w, r, 1)
        return pos_grid

    def _build_la_bot_grid(self, lbl_cell) -> QGridLayout:
        """底部信息网格。"""
        bot_grid = QGridLayout()
        bot_grid.setSpacing(0)
        bot_grid.setContentsMargins(0, 0, 0, 0)
        bot_grid.setColumnMinimumWidth(0, 80)
        bot_grid.setColumnMinimumWidth(2, _LW2)
        bot_grid.setColumnStretch(1, 1)
        bot_grid.setColumnStretch(3, 1)
        bot_grid.addWidget(lbl_cell('呈报单位', 80), 0, 0)
        bot_grid.addWidget(self._cheng_bao, 0, 1, 1, 3)
        bot_grid.addWidget(lbl_cell('改革前年龄', 80), 1, 0)
        bot_grid.addWidget(self._gai_ge_nll, 1, 1, 1, 3)
        bot_grid.addWidget(lbl_cell('身份证号', 80), 2, 0)
        bot_grid.addWidget(self._shen_fen, 2, 1)
        bot_grid.addWidget(lbl_cell('计算年龄'), 2, 2)
        bot_grid.addWidget(self._ji_suan, 2, 3)
        bot_grid.addWidget(lbl_cell('填表时间', 80), 3, 0)
        bot_grid.addWidget(self._tian_biao_shi, 3, 1)
        bot_grid.addWidget(lbl_cell('填表人'), 3, 2)
        bot_grid.addWidget(self._tian_biao_ren, 3, 3)
        return bot_grid

    def _build_la_left(self, lbl_cell, sec_cell) -> QWidget:
        """左栏容器：基本信息 + 学历学位 + 职务 + 简历。"""
        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(0)

        left_lay.addWidget(sec_cell('基本信息'))
        left_lay.addLayout(self._build_la_info_grid(lbl_cell))

        left_lay.addWidget(sec_cell('学历学位'))
        left_lay.addLayout(self._build_la_edu_grid(lbl_cell))

        left_lay.addWidget(sec_cell('职务'))
        left_lay.addLayout(self._build_la_pos_grid(lbl_cell))

        left_lay.addWidget(sec_cell('简历'))
        left_lay.addWidget(self._jian_li, 1)

        left.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        return left

    def _build_la_right(self, lbl_cell, sec_cell) -> QWidget:
        """右栏容器：奖惩 + 考核 + 任免理由 + 家庭成员 + 底部信息。"""
        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(0)

        right_lay.addWidget(sec_cell('奖惩情况'))
        right_lay.addWidget(self._jiang_cheng)
        right_lay.addWidget(sec_cell('年度考核结果'))
        right_lay.addWidget(self._nian_du)
        right_lay.addWidget(sec_cell('任免理由'))
        right_lay.addWidget(self._ren_mian)
        right_lay.addWidget(sec_cell('家庭主要成员'))
        right_lay.addWidget(self._family, 1)
        right_lay.addWidget(sec_cell('底部信息'))
        right_lay.addLayout(self._build_la_bot_grid(lbl_cell))

        right.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        return right

    def _build_layout_a(self) -> QScrollArea:
        """严格表格式布局：全格线，双栏，标签宽度固定不换行。"""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        container.setObjectName('editorFormA')
        outer = QHBoxLayout(container)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        def lbl_cell(text: str, min_w: int = _LW2) -> QLabel:
            w = QLabel(text)
            w.setObjectName('tableLbl')
            w.setAlignment(Qt.AlignmentFlag.AlignCenter)
            w.setContentsMargins(2, 2, 2, 2)
            w.setMinimumWidth(min_w)
            return w

        def sec_cell(text: str) -> QLabel:
            w = QLabel(text)
            w.setObjectName('tableSecLbl')
            w.setContentsMargins(6, 2, 6, 2)
            return w

        outer.addWidget(self._build_la_left(lbl_cell, sec_cell), 1)
        outer.addWidget(self._build_la_right(lbl_cell, sec_cell), 1)

        scroll.setWidget(container)
        return scroll

    def rebuild_layout(self, mode: str) -> None:
        """切换布局模式（保留字段值）。"""
        if mode == self._layout_mode:
            return
        snap = self._snapshot()
        self._install_layout(mode)
        self._connect_dirty()
        self._restore_snapshot(snap)

    # ── 字段快照（用于布局切换时保留值）────────────────────────────────────

    def _snapshot(self) -> dict:
        return {
            'XingMing': self._xing_ming.text(),
            'XingBie': self._xing_bie.currentText(),
            'ChuShengNianYue': self._chu_sheng.text(),
            'MinZu': self._min_zu.currentText(),
            'JiGuan': self._ji_guan.text(),
            'ChuShengDi': self._chu_di.text(),
            'RuDangShiJian': self._ru_dang.text(),
            'CanJiaGongZuoShiJian': self._can_jia.text(),
            'DaoLingNianYue': self._dao_ling.text(),
            'JianKangZhuangKuang': self._jian_kang.currentText(),
            'ZhuanYeJiShuZhiWu': self._zhuan_ye.currentText(),
            'ShuXiZhuanYeYouHeZhuanChang': self._shu_xi.text(),
            'QuanRiZhiJiaoYu_XueLi': self._qrz_xueli.currentText(),
            'QuanRiZhiJiaoYu_XueWei': self._qrz_xuewei.currentText(),
            'QuanRiZhiJiaoYu_XueLi_BiYeYuanXiaoXi': self._qrz_xueli_yuan.text(),
            'QuanRiZhiJiaoYu_XueWei_BiYeYuanXiaoXi': self._qrz_xuewei_yuan.text(),
            'ZaiZhiJiaoYu_XueLi': self._zzj_xueli.currentText(),
            'ZaiZhiJiaoYu_XueWei': self._zzj_xuewei.currentText(),
            'ZaiZhiJiaoYu_XueLi_BiYeYuanXiaoXi': self._zzj_xueli_yuan.text(),
            'ZaiZhiJiaoYu_XueWei_BiYeYuanXiaoXi': self._zzj_xuewei_yuan.text(),
            'XianRenZhiWu': self._xian_ren.text(),
            'NiRenZhiWu': self._ni_ren.text(),
            'NiMianZhiWu': self._ni_mian.text(),
            'JianLi': self._jian_li.toPlainText(),
            'JiangChengQingKuang': self._jiang_cheng.toPlainText(),
            'NianDuKaoHeJieGuo': self._nian_du.toPlainText(),
            'RenMianLiYou': self._ren_mian.toPlainText(),
            'ChengBaoDanWei': self._cheng_bao.text(),
            'GaiGeQianRenZhiNianLingJieXian': self._gai_ge_nll.currentText(),
            'ShenFenZheng': self._shen_fen.text(),
            'JiSuanNianLingShiJian': self._ji_suan.text(),
            'TianBiaoShiJian': self._tian_biao_shi.text(),
            'TianBiaoRen': self._tian_biao_ren.text(),
            'ZhaoPian': self._photo.b64(),
            '_family': self._family.dump(),
        }

    def _restore_snapshot(self, snap: dict) -> None:
        self._loading = True
        try:
            self._xing_ming.setText(snap.get('XingMing', ''))
            self._set_combo(self._xing_bie, snap.get('XingBie', ''))
            self._chu_sheng.setText(snap.get('ChuShengNianYue', ''))
            self._set_combo(self._min_zu, snap.get('MinZu', ''))
            self._ji_guan.setText(snap.get('JiGuan', ''))
            self._chu_di.setText(snap.get('ChuShengDi', ''))
            self._ru_dang.setText(snap.get('RuDangShiJian', ''))
            self._can_jia.setText(snap.get('CanJiaGongZuoShiJian', ''))
            self._dao_ling.setText(snap.get('DaoLingNianYue', ''))
            self._set_combo(self._jian_kang, snap.get('JianKangZhuangKuang', ''))
            self._set_combo(self._zhuan_ye, snap.get('ZhuanYeJiShuZhiWu', ''))
            self._shu_xi.setText(snap.get('ShuXiZhuanYeYouHeZhuanChang', ''))
            self._set_combo(self._qrz_xueli, snap.get('QuanRiZhiJiaoYu_XueLi', ''))
            self._set_combo(self._qrz_xuewei, snap.get('QuanRiZhiJiaoYu_XueWei', ''))
            self._qrz_xueli_yuan.setText(snap.get('QuanRiZhiJiaoYu_XueLi_BiYeYuanXiaoXi', ''))
            self._qrz_xuewei_yuan.setText(snap.get('QuanRiZhiJiaoYu_XueWei_BiYeYuanXiaoXi', ''))
            self._set_combo(self._zzj_xueli, snap.get('ZaiZhiJiaoYu_XueLi', ''))
            self._set_combo(self._zzj_xuewei, snap.get('ZaiZhiJiaoYu_XueWei', ''))
            self._zzj_xueli_yuan.setText(snap.get('ZaiZhiJiaoYu_XueLi_BiYeYuanXiaoXi', ''))
            self._zzj_xuewei_yuan.setText(snap.get('ZaiZhiJiaoYu_XueWei_BiYeYuanXiaoXi', ''))
            self._xian_ren.setText(snap.get('XianRenZhiWu', ''))
            self._ni_ren.setText(snap.get('NiRenZhiWu', ''))
            self._ni_mian.setText(snap.get('NiMianZhiWu', ''))
            self._jian_li.setPlainText(snap.get('JianLi', ''))
            self._jiang_cheng.setPlainText(snap.get('JiangChengQingKuang', ''))
            self._nian_du.setPlainText(snap.get('NianDuKaoHeJieGuo', ''))
            self._ren_mian.setPlainText(snap.get('RenMianLiYou', ''))
            self._cheng_bao.setText(snap.get('ChengBaoDanWei', ''))
            self._set_combo(self._gai_ge_nll, snap.get('GaiGeQianRenZhiNianLingJieXian', ''))
            self._shen_fen.setText(snap.get('ShenFenZheng', ''))
            self._ji_suan.setText(snap.get('JiSuanNianLingShiJian', ''))
            self._tian_biao_shi.setText(snap.get('TianBiaoShiJian', ''))
            self._tian_biao_ren.setText(snap.get('TianBiaoRen', ''))
            self._photo.set_b64(snap.get('ZhaoPian', ''))
            self._family.load(snap.get('_family', []))
        finally:
            self._loading = False

    # ── 文件操作 ─────────────────────────────────────────────────────────────

    def load(self, path: str) -> None:
        self._loading = True
        try:
            lrmx = LrmxFile(path)
            self._lrmx = lrmx
            self._current_path = path
            d = lrmx.as_dict()
            snap = {
                'XingMing': d.get('XingMing', ''),
                'XingBie': d.get('XingBie', ''),
                'ChuShengNianYue': d.get('ChuShengNianYue', ''),
                'MinZu': d.get('MinZu', ''),
                'JiGuan': d.get('JiGuan', ''),
                'ChuShengDi': d.get('ChuShengDi', ''),
                'RuDangShiJian': d.get('RuDangShiJian', ''),
                'CanJiaGongZuoShiJian': d.get('CanJiaGongZuoShiJian', ''),
                'DaoLingNianYue': d.get('DaoLingNianYue', ''),
                'JianKangZhuangKuang': d.get('JianKangZhuangKuang', ''),
                'ZhuanYeJiShuZhiWu': d.get('ZhuanYeJiShuZhiWu', ''),
                'ShuXiZhuanYeYouHeZhuanChang': d.get('ShuXiZhuanYeYouHeZhuanChang', ''),
                'QuanRiZhiJiaoYu_XueLi': d.get('QuanRiZhiJiaoYu_XueLi', ''),
                'QuanRiZhiJiaoYu_XueWei': d.get('QuanRiZhiJiaoYu_XueWei', ''),
                'QuanRiZhiJiaoYu_XueLi_BiYeYuanXiaoXi': d.get('QuanRiZhiJiaoYu_XueLi_BiYeYuanXiaoXi', '').strip(),
                'QuanRiZhiJiaoYu_XueWei_BiYeYuanXiaoXi': d.get('QuanRiZhiJiaoYu_XueWei_BiYeYuanXiaoXi', '').strip(),
                'ZaiZhiJiaoYu_XueLi': d.get('ZaiZhiJiaoYu_XueLi', ''),
                'ZaiZhiJiaoYu_XueWei': d.get('ZaiZhiJiaoYu_XueWei', ''),
                'ZaiZhiJiaoYu_XueLi_BiYeYuanXiaoXi': d.get('ZaiZhiJiaoYu_XueLi_BiYeYuanXiaoXi', '').strip(),
                'ZaiZhiJiaoYu_XueWei_BiYeYuanXiaoXi': d.get('ZaiZhiJiaoYu_XueWei_BiYeYuanXiaoXi', '').strip(),
                'XianRenZhiWu': d.get('XianRenZhiWu', '').strip(),
                'NiRenZhiWu': d.get('NiRenZhiWu', '').strip(),
                'NiMianZhiWu': d.get('NiMianZhiWu', '').strip(),
                'JianLi': d.get('JianLi', ''),
                'JiangChengQingKuang': d.get('JiangChengQingKuang', '').strip(),
                'NianDuKaoHeJieGuo': d.get('NianDuKaoHeJieGuo', ''),
                'RenMianLiYou': d.get('RenMianLiYou', '').strip(),
                'ChengBaoDanWei': d.get('ChengBaoDanWei', ''),
                'GaiGeQianRenZhiNianLingJieXian': d.get('GaiGeQianRenZhiNianLingJieXian', ''),
                'ShenFenZheng': d.get('ShenFenZheng', ''),
                'JiSuanNianLingShiJian': d.get('JiSuanNianLingShiJian', ''),
                'TianBiaoShiJian': d.get('TianBiaoShiJian', ''),
                'TianBiaoRen': d.get('TianBiaoRen', ''),
                'ZhaoPian': d.get('ZhaoPian', ''),
                '_family': lrmx.family_members(),
            }
            self._restore_snapshot(snap)
            self._dirty = False
        finally:
            self._loading = False
        self.path_changed.emit(path)
        self.dirty_changed.emit(False)

    def close_file(self) -> None:
        self._restore_snapshot({})
        self._lrmx = None
        self._current_path = None
        self._dirty = False
        self.path_changed.emit('')
        self.dirty_changed.emit(False)

    def collect(self) -> None:
        if self._lrmx is None:
            return
        lrmx = self._lrmx
        lrmx.set('XingMing', self._xing_ming.text())
        lrmx.set('XingBie', self._xing_bie.currentText())
        lrmx.set('ChuShengNianYue', self._chu_sheng.text())
        lrmx.set('MinZu', self._min_zu.currentText())
        lrmx.set('JiGuan', self._ji_guan.text())
        lrmx.set('ChuShengDi', self._chu_di.text())
        lrmx.set('RuDangShiJian', self._ru_dang.text())
        lrmx.set('CanJiaGongZuoShiJian', self._can_jia.text())
        lrmx.set('JianKangZhuangKuang', self._jian_kang.currentText())
        lrmx.set('ZhuanYeJiShuZhiWu', self._zhuan_ye.currentText())
        lrmx.set('ShuXiZhuanYeYouHeZhuanChang', self._shu_xi.text())
        lrmx.set('QuanRiZhiJiaoYu_XueLi', self._qrz_xueli.currentText())
        lrmx.set('QuanRiZhiJiaoYu_XueWei', self._qrz_xuewei.currentText())
        lrmx.set('QuanRiZhiJiaoYu_XueLi_BiYeYuanXiaoXi', self._qrz_xueli_yuan.text())
        lrmx.set('QuanRiZhiJiaoYu_XueWei_BiYeYuanXiaoXi', self._qrz_xuewei_yuan.text())
        lrmx.set('ZaiZhiJiaoYu_XueLi', self._zzj_xueli.currentText())
        lrmx.set('ZaiZhiJiaoYu_XueWei', self._zzj_xuewei.currentText())
        lrmx.set('ZaiZhiJiaoYu_XueLi_BiYeYuanXiaoXi', self._zzj_xueli_yuan.text())
        lrmx.set('ZaiZhiJiaoYu_XueWei_BiYeYuanXiaoXi', self._zzj_xuewei_yuan.text())
        lrmx.set('XianRenZhiWu', self._xian_ren.text())
        lrmx.set('NiRenZhiWu', self._ni_ren.text())
        lrmx.set('NiMianZhiWu', self._ni_mian.text())
        lrmx.set('JianLi', self._jian_li.toPlainText())
        lrmx.set('JiangChengQingKuang', self._jiang_cheng.toPlainText())
        lrmx.set('NianDuKaoHeJieGuo', self._nian_du.toPlainText())
        lrmx.set('RenMianLiYou', self._ren_mian.toPlainText())
        lrmx.set_family_members(self._family.dump())
        lrmx.set('ChengBaoDanWei', self._cheng_bao.text())
        lrmx.set('GaiGeQianRenZhiNianLingJieXian', self._gai_ge_nll.currentText())
        lrmx.set('ShenFenZheng', self._shen_fen.text())
        lrmx.set('JiSuanNianLingShiJian', self._ji_suan.text())
        lrmx.set('TianBiaoShiJian', self._tian_biao_shi.text())
        lrmx.set('TianBiaoRen', self._tian_biao_ren.text())
        lrmx.set('ZhaoPian', self._photo.b64())

    def save(self) -> bool:
        """保存。若无路径则执行 save_as。成功返回 True。"""
        if self._lrmx is None:
            return self.save_as()
        if self._current_path is None:
            return self.save_as()
        self.collect()
        try:
            self._lrmx.save()
            self._dirty = False
            self.dirty_changed.emit(False)
            return True
        except Exception as e:
            show_error(self, str(e))
            return False

    def save_as(self) -> bool:
        """另存为。若 _lrmx 为 None 则先 create_new。成功返回 True。"""
        if self._lrmx is None:
            self._lrmx = LrmxFile.create_new()
        path, _ = QFileDialog.getSaveFileName(
            self, '另存为', self._current_path or '', '任免审批表 (*.lrmx)')
        if not path:
            return False
        self.collect()
        try:
            self._lrmx.save(path)
            self._current_path = path
            self._lrmx.path = Path(path)  # type: ignore[assignment]
            self._dirty = False
            self.dirty_changed.emit(False)
            self.path_changed.emit(path)
            return True
        except Exception as e:
            show_error(self, str(e))
            return False

    def is_dirty(self) -> bool:
        return self._dirty

    def current_path(self) -> str | None:
        return self._current_path

    def lrmx(self) -> LrmxFile | None:
        return self._lrmx

    # ── 脏状态 ───────────────────────────────────────────────────────────────

    def _mark_dirty(self, *_args):
        if self._loading:
            return
        if not self._dirty:
            self._dirty = True
            self.dirty_changed.emit(True)

    def _connect_dirty(self):
        if self._dirty_connected:
            for w in [self._xing_ming, self._chu_sheng, self._ji_guan, self._chu_di,
                      self._ru_dang, self._can_jia, self._shu_xi,
                      self._xian_ren, self._ni_ren, self._ni_mian,
                      self._qrz_xueli_yuan, self._qrz_xuewei_yuan,
                      self._zzj_xueli_yuan, self._zzj_xuewei_yuan,
                      self._cheng_bao, self._shen_fen, self._ji_suan,
                      self._tian_biao_shi, self._tian_biao_ren]:
                try: w.textChanged.disconnect(self._mark_dirty)
                except RuntimeError: pass
            for w in [self._xing_bie, self._min_zu, self._jian_kang, self._zhuan_ye,
                      self._qrz_xueli, self._qrz_xuewei, self._zzj_xueli,
                      self._zzj_xuewei, self._gai_ge_nll]:
                try: w.currentTextChanged.disconnect(self._mark_dirty)
                except RuntimeError: pass
            for w in [self._jian_li, self._jiang_cheng, self._nian_du, self._ren_mian]:
                try: w.textChanged.disconnect(self._mark_dirty)
                except RuntimeError: pass
            try: self._photo.changed.disconnect(self._mark_dirty)
            except RuntimeError: pass
            try: self._family.table_modified.disconnect(self._mark_dirty)
            except RuntimeError: pass

        for w in [self._xing_ming, self._chu_sheng, self._ji_guan, self._chu_di,
                  self._ru_dang, self._can_jia, self._shu_xi,
                  self._xian_ren, self._ni_ren, self._ni_mian,
                  self._qrz_xueli_yuan, self._qrz_xuewei_yuan,
                  self._zzj_xueli_yuan, self._zzj_xuewei_yuan,
                  self._cheng_bao, self._shen_fen, self._ji_suan,
                  self._tian_biao_shi, self._tian_biao_ren]:
            w.textChanged.connect(self._mark_dirty)
        for w in [self._xing_bie, self._min_zu, self._jian_kang, self._zhuan_ye,
                  self._qrz_xueli, self._qrz_xuewei, self._zzj_xueli,
                  self._zzj_xuewei, self._gai_ge_nll]:
            w.currentTextChanged.connect(self._mark_dirty)
        for w in [self._jian_li, self._jiang_cheng, self._nian_du, self._ren_mian]:
            w.textChanged.connect(self._mark_dirty)
        self._photo.changed.connect(self._mark_dirty)
        self._family.table_modified.connect(self._mark_dirty)
        self._dirty_connected = True

    @staticmethod
    def _set_combo(combo: QComboBox, value: str) -> None:
        value = value.strip()
        idx = combo.findText(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        elif combo.isEditable():
            combo.setCurrentText(value)
        else:
            combo.setCurrentIndex(0)


class EditorTab(QWidget):
    USES_FILE_PANEL = False

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._build_ui()

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._tree = LrmxTreePanel()
        self._tree.setFixedWidth(220)
        self._tree.file_selected.connect(self._open_path)
        root.addWidget(self._tree)

        vline = QFrame()
        vline.setFrameShape(QFrame.Shape.VLine)
        vline.setFrameShadow(QFrame.Shadow.Sunken)
        vline.setStyleSheet('color: #ddd;')
        root.addWidget(vline)

        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(0)
        right_lay.addWidget(self._build_toolbar())

        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(True)
        self._tabs.tabCloseRequested.connect(self._close_tab)
        self._tabs.currentChanged.connect(self._refresh_toolbar)
        right_lay.addWidget(self._tabs, 1)
        root.addWidget(right, 1)

        shortcuts = [
            ('Ctrl+O',       self._on_open_btn),
            ('Ctrl+S',       self._on_save_btn),
            ('Ctrl+Shift+S', self._on_saveas_btn),
            ('Ctrl+W',       lambda: self._close_tab(self._tabs.currentIndex())),
            ('Ctrl+P',       self._on_print_btn),
            ('Ctrl+Shift+P', self._on_export_pdf),
        ]
        for key, slot in shortcuts:
            sc = QShortcut(QKeySequence(key), self)
            sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(slot)

    def _build_toolbar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName('editorToolbar')
        bar.setFixedHeight(36)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(10, 4, 10, 4)
        lay.setSpacing(6)

        self._path_lbl = QLabel('未打开文件')
        self._path_lbl.setStyleSheet('color: #888; font-size: 11px;')
        lay.addWidget(self._path_lbl, 1)

        def _btn(text: str, tooltip: str = '') -> QPushButton:
            b = QPushButton(text)
            b.setFixedHeight(26)
            if tooltip:
                b.setToolTip(tooltip)
            return b

        def _sep() -> QFrame:
            f = QFrame()
            f.setFrameShape(QFrame.Shape.VLine)
            f.setFrameShadow(QFrame.Shadow.Sunken)
            f.setFixedHeight(18)
            f.setStyleSheet('color: #D0CEC8;')
            return f

        self._open_btn   = _btn('打开', '打开 lrmx 文件（可多选）')

        self._save_btn   = _btn('保存', '保存当前文件')
        self._save_btn.setObjectName('primary')
        self._saveas_btn = _btn('另存为…', '另存为新文件')

        self._export_btn = _btn('导出 PDF', '导出为 PDF 文件')
        self._export_btn.setObjectName('secondary')
        self._print_btn  = _btn('打印', '打印预览并打印')

        self._close_btn  = _btn('关闭', '关闭当前标签页')

        self._open_btn.clicked.connect(self._on_open_btn)
        self._save_btn.clicked.connect(self._on_save_btn)
        self._saveas_btn.clicked.connect(self._on_saveas_btn)
        self._export_btn.clicked.connect(self._on_export_pdf)
        self._print_btn.clicked.connect(self._on_print_btn)
        self._close_btn.clicked.connect(lambda: self._close_tab(self._tabs.currentIndex()))

        lay.addWidget(self._open_btn)
        lay.addWidget(_sep())
        lay.addWidget(self._save_btn)
        lay.addWidget(self._saveas_btn)
        lay.addWidget(_sep())
        lay.addWidget(self._export_btn)
        lay.addWidget(self._print_btn)
        lay.addWidget(_sep())
        lay.addWidget(self._close_btn)

        for b in [self._save_btn, self._saveas_btn, self._export_btn,
                  self._print_btn, self._close_btn]:
            b.setEnabled(False)

        # 布局切换分段控件
        lay.addSpacing(10)
        self._layout_b_btn = QPushButton('轻量')
        self._layout_b_btn.setObjectName('layoutToggleL')
        self._layout_b_btn.setFixedHeight(24)
        self._layout_b_btn.setCheckable(True)
        self._layout_b_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._layout_b_btn.setToolTip('轻量分隔式布局')
        self._layout_b_btn.clicked.connect(lambda: self._on_layout_toggle('b'))

        self._layout_a_btn = QPushButton('表格')
        self._layout_a_btn.setObjectName('layoutToggleR')
        self._layout_a_btn.setFixedHeight(24)
        self._layout_a_btn.setCheckable(True)
        self._layout_a_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._layout_a_btn.setToolTip('严格表格式布局')
        self._layout_a_btn.clicked.connect(lambda: self._on_layout_toggle('a'))

        current_mode = self._layout_mode()
        self._layout_b_btn.setChecked(current_mode == 'b')
        self._layout_a_btn.setChecked(current_mode == 'a')

        lay.addWidget(self._layout_b_btn)
        lay.addWidget(self._layout_a_btn)

        return bar

    # ── active pane ──────────────────────────────────────────────────────────

    def _active_pane(self) -> _DocPane | None:
        w = self._tabs.currentWidget()
        return w if isinstance(w, _DocPane) else None

    def _layout_mode(self) -> str:
        return QSettings('rmb_helper', 'rmb_helper').value('editor/layout_mode', 'b')

    # ── public API ───────────────────────────────────────────────────────────

    def open_path(self, path: str) -> None:
        """外部调用（双击文件关联 / SingleInstance）。"""
        self._open_path(path)

    def set_layout_mode(self, mode: str) -> None:
        """切换布局模式，重建已有标签页，并同步工具栏切换按钮状态。"""
        if hasattr(self, '_layout_b_btn'):
            for btn, m in [(self._layout_b_btn, 'b'), (self._layout_a_btn, 'a')]:
                btn.blockSignals(True)
                btn.setChecked(m == mode)
                btn.blockSignals(False)
        for i in range(self._tabs.count()):
            pane = self._tabs.widget(i)
            if isinstance(pane, _DocPane):
                pane.rebuild_layout(mode)

    def _on_layout_toggle(self, mode: str) -> None:
        """布局切换按钮点击处理：保证单选语义，存 QSettings，重建已开标签页。"""
        for btn, m in [(self._layout_b_btn, 'b'), (self._layout_a_btn, 'a')]:
            btn.blockSignals(True)
            btn.setChecked(m == mode)
            btn.blockSignals(False)
        QSettings('rmb_helper', 'rmb_helper').setValue('editor/layout_mode', mode)
        for i in range(self._tabs.count()):
            pane = self._tabs.widget(i)
            if isinstance(pane, _DocPane):
                pane.rebuild_layout(mode)

    # ── open / close tabs ────────────────────────────────────────────────────

    def _open_path(self, path: str) -> None:
        for i in range(self._tabs.count()):
            pane = self._tabs.widget(i)
            if isinstance(pane, _DocPane) and pane.current_path() == path:
                self._tabs.setCurrentIndex(i)
                return
        pane = _DocPane(layout_mode=self._layout_mode())
        pane.dirty_changed.connect(lambda dirty, p=pane: self._on_pane_dirty(p, dirty))
        pane.path_changed.connect(lambda new_path, p=pane: self._on_pane_path(p, new_path))
        try:
            pane.load(path)
        except Exception as e:
            show_error(self, str(e))
            return
        idx = self._tabs.addTab(pane, Path(path).name)
        self._tabs.setCurrentIndex(idx)
        self._tree.add_path(path)
        self._refresh_toolbar()

    def _close_tab(self, index: int) -> None:
        if index < 0:
            return
        pane = self._tabs.widget(index)
        if isinstance(pane, _DocPane) and pane.is_dirty():
            ret = QMessageBox.question(
                self, '未保存修改', '当前文件有未保存的修改，关闭前是否保存？',
                QMessageBox.StandardButton.Save |
                QMessageBox.StandardButton.Discard |
                QMessageBox.StandardButton.Cancel,
            )
            if ret == QMessageBox.StandardButton.Cancel:
                return
            if ret == QMessageBox.StandardButton.Save:
                if isinstance(pane, _DocPane):
                    pane.save()
        self._tabs.removeTab(index)
        self._refresh_toolbar()

    # ── pane signal handlers ─────────────────────────────────────────────────

    def _on_pane_dirty(self, pane: _DocPane, dirty: bool) -> None:
        idx = self._tabs.indexOf(pane)
        if idx < 0:
            return
        path = pane.current_path()
        name = Path(path).name if path else '新文件'
        self._tabs.setTabText(idx, f'{name} *' if dirty else name)
        if pane is self._active_pane() and path:
            self._tree.set_modified(path, dirty)

    def _on_pane_path(self, pane: _DocPane, new_path: str) -> None:
        idx = self._tabs.indexOf(pane)
        if idx < 0:
            return
        if new_path:
            self._tabs.setTabText(idx, Path(new_path).name)
            self._tree.add_path(new_path)
        if pane is self._active_pane():
            self._path_lbl.setText(new_path or '未打开文件')

    def _refresh_toolbar(self) -> None:
        pane = self._active_pane()
        has = pane is not None
        for b in [self._close_btn, self._save_btn, self._saveas_btn,
                  self._export_btn, self._print_btn]:
            b.setEnabled(has)
        self._path_lbl.setText(
            (pane.current_path() or '新文件') if pane else '未打开文件'
        )

    # ── toolbar actions ──────────────────────────────────────────────────────

    def _on_open_btn(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, '打开文件', '', '任免审批表 (*.lrmx)')
        for path in paths:
            self._open_path(path)

    def _on_save_btn(self) -> None:
        pane = self._active_pane()
        if pane:
            pane.save()

    def _on_saveas_btn(self) -> None:
        pane = self._active_pane()
        if pane:
            pane.save_as()

    def _on_export_pdf(self) -> None:
        pane = self._active_pane()
        if pane is None:
            return
        lrmx = pane.lrmx()
        if lrmx is None:
            QMessageBox.information(self, '提示', '请先保存文件再导出 PDF。')
            return
        pane.collect()
        try:
            from app.core.docx_exporter import DocxExporter, get_template_path
            from app.core.pdf_exporter import PdfExporter, detect_engine, PdfEngine
            engine = detect_engine()
            if engine == PdfEngine.NONE:
                show_warning(self, '未检测到可用的 PDF 转换工具（WPS / Word / LibreOffice）。')
                return
            cp = pane.current_path()
            if cp:
                default_name = Path(cp).stem + '.pdf'
            else:
                default_name = (lrmx.get('XingMing') or '未命名') + '_任免审批表.pdf'
            dest, _ = QFileDialog.getSaveFileName(
                self, '导出 PDF', default_name, 'PDF 文件 (*.pdf)')
            if not dest:
                return
            tpl = get_template_path()
            docx_bytes = DocxExporter(tpl).export_bytes(lrmx)
            with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as f:
                f.write(docx_bytes)
                tmp_docx = Path(f.name)
            try:
                pdf_exporter = PdfExporter()
                tmp_pdf = pdf_exporter.export(tmp_docx, tmp_docx.parent)
                shutil.copy(tmp_pdf, dest)
                tmp_pdf.unlink(missing_ok=True)
            finally:
                tmp_docx.unlink(missing_ok=True)
            QMessageBox.information(self, '导出成功', f'已保存至：\n{dest}')
        except Exception as e:
            show_error(self, str(e))

    def _on_print_btn(self) -> None:
        pane = self._active_pane()
        if pane is None:
            return
        lrmx = pane.lrmx()
        if lrmx is None:
            QMessageBox.information(self, '提示', '请先保存文件再打印。')
            return
        pane.collect()
        try:
            from app.core.docx_exporter import DocxExporter, get_template_path
            from app.core.pdf_exporter import PdfExporter, detect_engine, PdfEngine
            from app.ui.widgets.print_preview import PrintPreviewDialog
            engine = detect_engine()
            if engine == PdfEngine.NONE:
                show_warning(self, '未检测到可用的 PDF 转换工具（WPS / Word / LibreOffice）。')
                return
            tpl = get_template_path()
            docx_bytes = DocxExporter(tpl).export_bytes(lrmx)
            tmp_dir = Path(tempfile.gettempdir())
            tmp_docx = tmp_dir / f'.rmb_print_{id(self)}.docx'
            tmp_docx.write_bytes(docx_bytes)
            try:
                pdf_exporter = PdfExporter()
                tmp_pdf = pdf_exporter.export(tmp_docx, tmp_dir)
            finally:
                tmp_docx.unlink(missing_ok=True)
            # PrintPreviewDialog 负责在关闭后删除 tmp_pdf
            dlg = PrintPreviewDialog(tmp_pdf, self)
            dlg.exec()
        except Exception as e:
            show_error(self, str(e))

    # ── drag & drop ──────────────────────────────────────────────────────────

    def dragEnterEvent(self, ev) -> None:
        if ev.mimeData().hasUrls():
            if any(u.toLocalFile().lower().endswith('.lrmx')
                   for u in ev.mimeData().urls()):
                ev.acceptProposedAction()

    def dropEvent(self, ev) -> None:
        for url in ev.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith('.lrmx') and Path(path).is_file():
                self._open_path(path)
