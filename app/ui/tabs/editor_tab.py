"""任免审批表编辑器 Tab。

布局参照 任免审批表 纸质表单，左栏为基本信息 + 简历，右栏为奖惩 / 年核 / 任免 / 家庭成员 + 底部。
照片置于左栏顶部右侧与右栏之间。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QLineEdit, QComboBox, QTextEdit,
    QScrollArea, QFileDialog, QMessageBox, QSizePolicy,
    QFrame,
)

from app.core.dmgrp_loader import get_loader
from app.core.lrmx import LrmxFile
from app.ui.widgets.lrmx_tree import LrmxTreePanel
from app.ui.widgets.photo_widget import PhotoWidget
from app.ui.widgets.family_table import FamilyTable

USES_FILE_PANEL = False

# ── label 固定宽度 ──────────────────────────────────────────────
_LW1 = 56   # 短标签
_LW2 = 72   # 长标签
_LW3 = 90   # 更长
_ROW_H = 28


def _lbl(text: str, width: int = _LW1) -> QLabel:
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
    """枚举字段下拉框。选项仅作建议，默认可编辑，用户可输入任意值。"""
    w = QComboBox()
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


def _sep() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFrameShadow(QFrame.Shadow.Sunken)
    line.setStyleSheet('color: #ddd;')
    return line


class EditorTab(QWidget):
    USES_FILE_PANEL = False

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lrmx: LrmxFile | None = None
        self._current_path: str | None = None
        self._dirty = False
        self._loading = False  # suppress dirty marking during load
        self._build_ui()

    # ── UI construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── 左侧文件树 ─────────────────────────────────────────────────────
        self._tree = LrmxTreePanel()
        self._tree.setFixedWidth(220)
        self._tree.file_selected.connect(self._on_file_selected)
        root.addWidget(self._tree)

        # 分隔线
        vline = QFrame()
        vline.setFrameShape(QFrame.Shape.VLine)
        vline.setFrameShadow(QFrame.Shadow.Sunken)
        vline.setStyleSheet('color: #ddd;')
        root.addWidget(vline)

        # ── 右侧编辑区（工具栏 + 表单）──────────────────────────────────────
        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(0)

        right_lay.addWidget(self._build_toolbar())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        form_widget = self._build_form()
        scroll.setWidget(form_widget)
        right_lay.addWidget(scroll, 1)

        root.addWidget(right, 1)

    def _build_toolbar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName('editorToolbar')
        bar.setFixedHeight(36)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(10, 4, 10, 4)
        lay.setSpacing(8)

        self._path_lbl = QLabel('未打开文件')
        self._path_lbl.setStyleSheet('color: #888; font-size: 11px;')
        lay.addWidget(self._path_lbl, 1)

        self._close_btn = QPushButton('关闭')
        self._close_btn.setFixedHeight(26)
        self._close_btn.setEnabled(False)
        self._close_btn.setToolTip('关闭当前文件')
        self._close_btn.clicked.connect(self._close_file)

        self._save_btn = QPushButton('保存')
        self._save_btn.setFixedHeight(26)
        self._save_btn.setEnabled(False)
        self._save_btn.clicked.connect(self._save)

        self._saveas_btn = QPushButton('另存为…')
        self._saveas_btn.setFixedHeight(26)
        self._saveas_btn.setEnabled(False)
        self._saveas_btn.clicked.connect(self._save_as)

        lay.addWidget(self._close_btn)
        lay.addWidget(self._save_btn)
        lay.addWidget(self._saveas_btn)
        return bar

    def _build_form(self) -> QWidget:
        """构建双栏表单主体。"""
        loader = get_loader()

        container = QWidget()
        container.setObjectName('editorForm')
        outer = QHBoxLayout(container)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(12)

        # ── 左栏 ─────────────────────────────────────────────────────────
        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(6)

        # 基本信息 grid。前三行每行 4 列（2 个字段对），右侧 cols 4-5 放照片（跨 3 行）。
        info_grid = QGridLayout()
        info_grid.setHorizontalSpacing(6)
        info_grid.setVerticalSpacing(4)
        info_grid.setColumnStretch(1, 1)
        info_grid.setColumnStretch(3, 1)
        info_grid.setColumnStretch(5, 1)
        info_grid.setColumnMinimumWidth(0, _LW2)
        info_grid.setColumnMinimumWidth(2, _LW2)
        info_grid.setColumnMinimumWidth(4, _LW2)

        # row 0: 姓名 / 性别
        self._xing_ming  = _line()
        self._xing_bie   = _combo(loader.options('GB22611'))
        info_grid.addWidget(_lbl('姓名', _LW2), 0, 0)
        info_grid.addWidget(self._xing_ming, 0, 1)
        info_grid.addWidget(_lbl('性别', _LW2), 0, 2)
        info_grid.addWidget(self._xing_bie, 0, 3)

        # row 1: 出生年月 / 民族
        self._chu_sheng  = _line('YYYYMM')
        self._min_zu     = _combo(loader.options('GB3304'))
        info_grid.addWidget(_lbl('出生年月', _LW2), 1, 0)
        info_grid.addWidget(self._chu_sheng, 1, 1)
        info_grid.addWidget(_lbl('民族', _LW2), 1, 2)
        info_grid.addWidget(self._min_zu, 1, 3)

        # row 2: 籍贯 / 出生地
        self._ji_guan   = _line()
        self._chu_di    = _line()
        info_grid.addWidget(_lbl('籍贯', _LW2), 2, 0)
        info_grid.addWidget(self._ji_guan, 2, 1)
        info_grid.addWidget(_lbl('出生地', _LW2), 2, 2)
        info_grid.addWidget(self._chu_di, 2, 3)

        # 照片：跨前三行，置于右侧 cols 4-5
        self._photo = PhotoWidget()
        info_grid.addWidget(
            self._photo, 0, 4, 3, 2,
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter,
        )

        # row 3: 入党 / 参工 / 到龄
        self._ru_dang   = _line('YYYYMM')
        self._can_jia   = _line('YYYYMM')
        self._dao_ling  = _line(readonly=True)
        info_grid.addWidget(_lbl('入党时间', _LW2), 3, 0)
        info_grid.addWidget(self._ru_dang, 3, 1)
        info_grid.addWidget(_lbl('参工时间', _LW2), 3, 2)
        info_grid.addWidget(self._can_jia, 3, 3)
        info_grid.addWidget(_lbl('到龄时间', _LW2), 3, 4)
        info_grid.addWidget(self._dao_ling, 3, 5)

        # row 4: 健康 / 专技 / 熟悉
        self._jian_kang  = _combo(loader.options('GB22613'))
        self._zhuan_ye   = _combo(loader.options('GB8561'))
        self._shu_xi     = _line()
        info_grid.addWidget(_lbl('健康状况', _LW2), 4, 0)
        info_grid.addWidget(self._jian_kang, 4, 1)
        info_grid.addWidget(_lbl('专技职务', _LW2), 4, 2)
        info_grid.addWidget(self._zhuan_ye, 4, 3)
        info_grid.addWidget(_lbl('熟悉专业', _LW2), 4, 4)
        info_grid.addWidget(self._shu_xi, 4, 5)

        # row 5: 政治面貌（自由文本，全宽）
        self._zheng_zhi = _line()
        info_grid.addWidget(_lbl('政治面貌', _LW2), 5, 0)
        info_grid.addWidget(self._zheng_zhi, 5, 1, 1, 5)

        left_lay.addLayout(info_grid)

        # 学历学位 section
        left_lay.addWidget(_section_label('学历学位'))
        edu_grid = QGridLayout()
        edu_grid.setHorizontalSpacing(6)
        edu_grid.setVerticalSpacing(4)
        edu_grid.setColumnMinimumWidth(0, 52)
        edu_grid.setColumnMinimumWidth(1, 48)
        edu_grid.setColumnStretch(2, 1)
        edu_grid.setColumnMinimumWidth(3, 60)
        edu_grid.setColumnStretch(4, 2)

        xu_li_opts  = loader.options('ZB64')
        xue_wei_opts = loader.options('GB6864')

        self._qrz_xueli  = _combo(xu_li_opts)
        self._qrz_xuewei = _combo(xue_wei_opts)
        self._zzj_xueli  = _combo(xu_li_opts)
        self._zzj_xuewei = _combo(xue_wei_opts)
        self._qrz_xueli_yuan  = _line()
        self._qrz_xuewei_yuan = _line()
        self._zzj_xueli_yuan  = _line()
        self._zzj_xuewei_yuan = _line()

        for row, (type_lbl, kind_lbl, combo_w, yuan_w) in enumerate([
            ('全日制', '学历', self._qrz_xueli,  self._qrz_xueli_yuan),
            ('全日制', '学位', self._qrz_xuewei, self._qrz_xuewei_yuan),
            ('在职',   '学历', self._zzj_xueli,  self._zzj_xueli_yuan),
            ('在职',   '学位', self._zzj_xuewei, self._zzj_xuewei_yuan),
        ]):
            edu_grid.addWidget(QLabel(type_lbl), row, 0)
            edu_grid.addWidget(QLabel(kind_lbl), row, 1)
            edu_grid.addWidget(combo_w, row, 2)
            edu_grid.addWidget(QLabel('毕业院校系及专业'), row, 3)
            edu_grid.addWidget(yuan_w, row, 4)

        left_lay.addLayout(edu_grid)

        # 职务 section
        left_lay.addWidget(_section_label('职务'))
        pos_grid = QGridLayout()
        pos_grid.setHorizontalSpacing(6)
        pos_grid.setVerticalSpacing(4)
        pos_grid.setColumnMinimumWidth(0, _LW2)
        pos_grid.setColumnStretch(1, 1)

        self._xian_ren  = _line()
        self._ni_ren    = _line()
        self._ni_mian   = _line()
        pos_grid.addWidget(_lbl('现任职务', _LW2), 0, 0)
        pos_grid.addWidget(self._xian_ren, 0, 1)
        pos_grid.addWidget(_lbl('拟任职务', _LW2), 1, 0)
        pos_grid.addWidget(self._ni_ren, 1, 1)
        pos_grid.addWidget(_lbl('拟免职务', _LW2), 2, 0)
        pos_grid.addWidget(self._ni_mian, 2, 1)

        left_lay.addLayout(pos_grid)

        # 简历（等宽字体，使空白字符与有效字符宽度一致，保证缩进对齐）
        # 字体通过 QSS#resumeEdit 设置——QSS 的 font-family 优先级高于 setFont()
        left_lay.addWidget(_section_label('简历'))
        self._jian_li = QTextEdit()
        self._jian_li.setObjectName('resumeEdit')
        self._jian_li.setMinimumHeight(200)
        self._jian_li.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._jian_li.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        left_lay.addWidget(self._jian_li, 1)

        left.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        outer.addWidget(left, 1)

        # ── 右栏 ─────────────────────────────────────────────────────────
        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(6)

        right_lay.addWidget(_section_label('奖惩情况'))
        self._jiang_cheng = QTextEdit()
        self._jiang_cheng.setFixedHeight(80)
        right_lay.addWidget(self._jiang_cheng)

        right_lay.addWidget(_section_label('年度考核结果'))
        self._nian_du = QTextEdit()
        self._nian_du.setFixedHeight(80)
        right_lay.addWidget(self._nian_du)

        right_lay.addWidget(_section_label('任免理由'))
        self._ren_mian = QTextEdit()
        self._ren_mian.setFixedHeight(100)
        right_lay.addWidget(self._ren_mian)

        right_lay.addWidget(_section_label('家庭主要成员'))
        self._family = FamilyTable()
        self._family.setMinimumHeight(180)
        self._family.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        right_lay.addWidget(self._family, 1)

        right_lay.addWidget(_section_label('底部信息'))
        bot_grid = QGridLayout()
        bot_grid.setHorizontalSpacing(6)
        bot_grid.setVerticalSpacing(4)
        bot_grid.setColumnStretch(1, 1)
        bot_grid.setColumnStretch(3, 1)

        self._cheng_bao = _line()
        bot_grid.addWidget(_lbl('呈报单位', _LW2), 0, 0)
        bot_grid.addWidget(self._cheng_bao, 0, 1, 1, 3)

        self._gai_ge_nll = _combo(loader.options('NLLB'))
        bot_grid.addWidget(_lbl('改革前年龄', _LW2), 1, 0)
        bot_grid.addWidget(self._gai_ge_nll, 1, 1, 1, 3)

        self._shen_fen   = _line()
        self._ji_suan    = _line('YYYYMMDD')
        bot_grid.addWidget(_lbl('身份证号', _LW2), 2, 0)
        bot_grid.addWidget(self._shen_fen, 2, 1)
        bot_grid.addWidget(_lbl('计算年龄', _LW2), 2, 2)
        bot_grid.addWidget(self._ji_suan, 2, 3)

        self._tian_biao_shi = _line()
        self._tian_biao_ren = _line()
        bot_grid.addWidget(_lbl('填表时间', _LW2), 3, 0)
        bot_grid.addWidget(self._tian_biao_shi, 3, 1)
        bot_grid.addWidget(_lbl('填表人', _LW2), 3, 2)
        bot_grid.addWidget(self._tian_biao_ren, 3, 3)

        right_lay.addLayout(bot_grid)
        right.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        outer.addWidget(right, 1)

        self._connect_dirty()
        return container

    def _connect_dirty(self):
        """连接所有控件的变化信号到 _mark_dirty。"""
        for w in [self._xing_ming, self._chu_sheng, self._ji_guan, self._chu_di,
                  self._ru_dang, self._can_jia, self._shu_xi, self._zheng_zhi,
                  self._xian_ren, self._ni_ren, self._ni_mian,
                  self._qrz_xueli_yuan, self._qrz_xuewei_yuan,
                  self._zzj_xueli_yuan, self._zzj_xuewei_yuan,
                  self._cheng_bao, self._shen_fen, self._ji_suan,
                  self._tian_biao_shi, self._tian_biao_ren]:
            w.textChanged.connect(self._mark_dirty)

        for w in [self._xing_bie, self._min_zu, self._jian_kang, self._zhuan_ye,
                  self._qrz_xueli, self._qrz_xuewei, self._zzj_xueli, self._zzj_xuewei,
                  self._gai_ge_nll]:
            w.currentTextChanged.connect(self._mark_dirty)

        for w in [self._jian_li, self._jiang_cheng, self._nian_du, self._ren_mian]:
            w.textChanged.connect(self._mark_dirty)

        self._photo.changed.connect(self._mark_dirty)
        self._family.table_modified.connect(self._mark_dirty)

    # ── file operations ──────────────────────────────────────────────────────

    def open_path(self, path: str) -> None:
        """外部调用（如双击关联文件）：加入文件树并加载。"""
        self._tree.add_path(path)
        self._on_file_selected(path)

    def _on_file_selected(self, path: str) -> None:
        if self._dirty:
            ret = QMessageBox.question(
                self, '未保存修改',
                f'当前文件有未保存的修改，切换前是否保存？',
                QMessageBox.StandardButton.Save |
                QMessageBox.StandardButton.Discard |
                QMessageBox.StandardButton.Cancel,
            )
            if ret == QMessageBox.StandardButton.Cancel:
                return
            if ret == QMessageBox.StandardButton.Save:
                self._save()

        try:
            self._load_file(path)
        except Exception as e:
            QMessageBox.critical(self, '打开失败', str(e))

    def _load_file(self, path: str) -> None:
        self._loading = True
        try:
            lrmx = LrmxFile(path)
            self._lrmx = lrmx
            self._current_path = path
            d = lrmx.as_dict()

            self._xing_ming.setText(d.get('XingMing', ''))
            self._set_combo(self._xing_bie, d.get('XingBie', ''))
            self._chu_sheng.setText(d.get('ChuShengNianYue', ''))
            self._set_combo(self._min_zu, d.get('MinZu', ''))
            self._ji_guan.setText(d.get('JiGuan', ''))
            self._chu_di.setText(d.get('ChuShengDi', ''))
            self._ru_dang.setText(d.get('RuDangShiJian', ''))
            self._can_jia.setText(d.get('CanJiaGongZuoShiJian', ''))
            self._dao_ling.setText(d.get('DaoLingNianYue', ''))
            self._set_combo(self._jian_kang, d.get('JianKangZhuangKuang', ''))
            self._set_combo(self._zhuan_ye, d.get('ZhuanYeJiShuZhiWu', ''))
            self._shu_xi.setText(d.get('ShuXiZhuanYeYouHeZhuanChang', ''))
            self._zheng_zhi.setText(d.get('ZhengZhiMianMao', ''))

            self._set_combo(self._qrz_xueli,  d.get('QuanRiZhiJiaoYu_XueLi', ''))
            self._set_combo(self._qrz_xuewei, d.get('QuanRiZhiJiaoYu_XueWei', ''))
            self._qrz_xueli_yuan.setText(d.get('QuanRiZhiJiaoYu_XueLi_BiYeYuanXiaoXi', '').strip())
            self._qrz_xuewei_yuan.setText(d.get('QuanRiZhiJiaoYu_XueWei_BiYeYuanXiaoXi', '').strip())
            self._set_combo(self._zzj_xueli,  d.get('ZaiZhiJiaoYu_XueLi', ''))
            self._set_combo(self._zzj_xuewei, d.get('ZaiZhiJiaoYu_XueWei', ''))
            self._zzj_xueli_yuan.setText(d.get('ZaiZhiJiaoYu_XueLi_BiYeYuanXiaoXi', '').strip())
            self._zzj_xuewei_yuan.setText(d.get('ZaiZhiJiaoYu_XueWei_BiYeYuanXiaoXi', '').strip())

            self._xian_ren.setText(d.get('XianRenZhiWu', '').strip())
            self._ni_ren.setText(d.get('NiRenZhiWu', '').strip())
            self._ni_mian.setText(d.get('NiMianZhiWu', '').strip())
            self._jian_li.setPlainText(d.get('JianLi', ''))

            self._jiang_cheng.setPlainText(d.get('JiangChengQingKuang', '').strip())
            self._nian_du.setPlainText(d.get('NianDuKaoHeJieGuo', ''))
            self._ren_mian.setPlainText(d.get('RenMianLiYou', '').strip())

            self._family.load(lrmx.family_members())

            self._cheng_bao.setText(d.get('ChengBaoDanWei', ''))
            self._set_combo(self._gai_ge_nll, d.get('GaiGeQianRenZhiNianLingJieXian', ''))
            self._shen_fen.setText(d.get('ShenFenZheng', ''))
            self._ji_suan.setText(d.get('JiSuanNianLingShiJian', ''))
            self._tian_biao_shi.setText(d.get('TianBiaoShiJian', ''))
            self._tian_biao_ren.setText(d.get('TianBiaoRen', ''))

            self._photo.set_b64(d.get('ZhaoPian', ''))

            self._dirty = False
            self._current_path = path
            self._path_lbl.setText(path)
            self._close_btn.setEnabled(True)
            self._save_btn.setEnabled(True)
            self._saveas_btn.setEnabled(True)
            self._tree.set_modified(path, False)
        finally:
            self._loading = False

    def _close_file(self) -> None:
        """关闭当前文件，清空所有字段显示。"""
        if self._dirty:
            ret = QMessageBox.question(
                self, '未保存修改',
                '当前文件有未保存的修改，关闭前是否保存？',
                QMessageBox.StandardButton.Save |
                QMessageBox.StandardButton.Discard |
                QMessageBox.StandardButton.Cancel,
            )
            if ret == QMessageBox.StandardButton.Cancel:
                return
            if ret == QMessageBox.StandardButton.Save:
                self._save()

        self._loading = True
        try:
            for w in [self._xing_ming, self._chu_sheng, self._ji_guan, self._chu_di,
                      self._ru_dang, self._can_jia, self._dao_ling, self._shu_xi,
                      self._zheng_zhi, self._xian_ren, self._ni_ren, self._ni_mian,
                      self._qrz_xueli_yuan, self._qrz_xuewei_yuan,
                      self._zzj_xueli_yuan, self._zzj_xuewei_yuan,
                      self._cheng_bao, self._shen_fen, self._ji_suan,
                      self._tian_biao_shi, self._tian_biao_ren]:
                w.clear()
            for w in [self._xing_bie, self._min_zu, self._jian_kang, self._zhuan_ye,
                      self._qrz_xueli, self._qrz_xuewei, self._zzj_xueli,
                      self._zzj_xuewei, self._gai_ge_nll]:
                w.setCurrentIndex(0)
            for w in [self._jian_li, self._jiang_cheng, self._nian_du, self._ren_mian]:
                w.clear()
            self._family.load([])
            self._photo.set_b64('')
        finally:
            self._loading = False

        prev_path = self._current_path
        self._lrmx = None
        self._current_path = None
        self._dirty = False
        if prev_path:
            self._tree.set_modified(prev_path, False)
        self._path_lbl.setText('未打开文件')
        self._close_btn.setEnabled(False)
        self._save_btn.setEnabled(False)
        self._saveas_btn.setEnabled(False)

    def _mark_dirty(self, *_args):
        if self._loading or self._lrmx is None:
            return
        if not self._dirty:
            self._dirty = True
            if self._current_path:
                self._tree.set_modified(self._current_path, True)

    def _collect(self) -> None:
        """将所有控件的值写回 _lrmx 对象（但不保存到磁盘）。"""
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
        lrmx.set('ZhengZhiMianMao', self._zheng_zhi.text())

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

    def _save(self) -> None:
        if self._lrmx is None or self._current_path is None:
            return
        self._collect()
        try:
            self._lrmx.save()
            self._dirty = False
            self._tree.set_modified(self._current_path, False)
        except Exception as e:
            QMessageBox.critical(self, '保存失败', str(e))

    def _save_as(self) -> None:
        if self._lrmx is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, '另存为', self._current_path or '', '任免审批表 (*.lrmx)')
        if not path:
            return
        self._collect()
        try:
            self._lrmx.save(path)
            self._current_path = path
            self._lrmx.path = Path(path)
            self._dirty = False
            self._path_lbl.setText(path)
            self._tree.set_modified(path, False)
            self._tree.add_path(path)
        except Exception as e:
            QMessageBox.critical(self, '保存失败', str(e))

    # ── helpers ──────────────────────────────────────────────────────────────

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
