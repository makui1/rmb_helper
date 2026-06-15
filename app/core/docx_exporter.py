import base64
import re
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Optional

from docxtpl import DocxTemplate, InlineImage
from docx.shared import Emu, Mm, Pt
from docx.enum.text import WD_LINE_SPACING

from .lrmx import LrmxFile

# ── Constants ─────────────────────────────────────────────────────────────────

MAX_FAMILY_SLOTS = 10   # how many m0..m9 slots to expose; should exceed any template

_PT_PER_EMU = 12700      # 1 pt = 12700 EMU
_CELL_MARGIN_PT = 5.4    # Word default cell left/right inner margin ≈ 1.9 mm each side
_MIN_FONT_PT = 8.0       # never shrink below 8 pt

_EMPTY_MEMBER: dict[str, str] = {
    'ChengWei': '', 'XingMing': '', 'Age': '',
    'ChuShengRiQi': '', 'ZhengZhiMianMao': '', 'GongZuoDanWeiJiZhiWu': '',
}

# ── Field classification ──────────────────────────────────────────────────────

_TIME6_FIELDS = frozenset({
    'RuDangShiJian', 'CanJiaGongZuoShiJian', 'TianBiaoShiJian',
})
_TIME8_FIELDS = frozenset({'JiSuanNianLingShiJian'})

_XUELI_KEY  = 'QuanRiZhiJiaoYu_XueLi_BiYeYuanXiaoXi'
_XUEWEI_KEY = 'QuanRiZhiJiaoYu_XueWei_BiYeYuanXiaoXi'

# Matches all whitespace variants + invisible Unicode chars
_INVIS = re.compile(r'[\s​‌‍﻿ 　]+')

# JianLi source line: leading start date, any dash/range separator, optional end
# date, then the experience. The separator may be '--', a full-width em/en dash,
# a tilde, '至', etc. Only this LEADING separator is normalized; dashes inside the
# experience text are left untouched.
_JIANLI_LINE = re.compile(
    r'^\s*(\d{4}\.\d{2}|\d{6})\s*(?:[—–－〜～~-]+|至)\s*(\d{4}\.\d{2}|\d{6})?\s*(.*)$'
)
# Pattern that appears in rendered JianLi paragraphs (e.g. "1990.01--1996.06\t...")
_JIANLI_RENDERED = re.compile(r'\d{4}\.\d{2}--')


# ── Pure helper functions ─────────────────────────────────────────────────────

def _to_ym(s: str) -> str:
    s = s.strip() if s else ''
    if re.fullmatch(r'\d{6}', s):
        return f'{s[:4]}.{s[4:]}'
    return s


def _format_time6(value: str) -> str:
    v = _INVIS.sub('', value)
    if re.fullmatch(r'\d{6}', v):
        return f'{v[:4]}.{v[4:]}'
    return v


def _format_time8(value: str) -> str:
    v = _INVIS.sub('', value)
    if re.fullmatch(r'\d{8}', v):
        return f'{v[:4]}.{v[4:6]}.{v[6:]}'
    return v


def _calc_age(ym6: str) -> int:
    """Age in completed years from yyyyMM to today."""
    if not re.fullmatch(r'\d{6}', ym6):
        return 0
    year, month = int(ym6[:4]), int(ym6[4:])
    today = date.today()
    age = today.year - year
    if today.month < month:
        age -= 1
    return age


def _format_birth(value: str) -> str:
    """ChuShengNianYue → 'yyyy.MM\n（X岁）'."""
    v = _INVIS.sub('', value)
    formatted = _format_time6(v)
    if re.fullmatch(r'\d{6}', v):
        return f'{formatted}\n（{_calc_age(v)}岁）'
    return formatted


def _format_retire_age(value: str, birth_ym6: str) -> str:
    """DaoLingNianYue → 'yyyy.MM\n（X岁）' where X is the retirement age."""
    v = _INVIS.sub('', value)
    b = _INVIS.sub('', birth_ym6)
    formatted = _format_time6(v)
    if re.fullmatch(r'\d{6}', v) and re.fullmatch(r'\d{6}', b):
        d_year, d_month = int(v[:4]), int(v[4:])
        b_year, b_month = int(b[:4]), int(b[4:])
        retire_age = d_year - b_year
        if d_month < b_month:
            retire_age -= 1
        return f'{formatted}\n（{retire_age}岁）'
    return formatted


def _format_jianli_list(text: str) -> list[str]:
    """Normalize each JianLi line to 'yyyy.MM--[yyyy.MM]<TAB>experience'.

    Accepts mixed source separators ('--', '—', '–', '~', '至', ...) and
    canonicalizes the leading one to '--'. A tab separates the time part from the
    experience; docxtpl renders it as a real Word tab. Column alignment is left to
    the template: set a hanging indent on the JianLi paragraph so the first line's
    experience snaps to the tab stop and wrapped lines align under it.
    """
    if not text or not text.strip():
        return []
    out = []
    for line in text.split('\n'):
        if not line.strip():
            continue
        m = _JIANLI_LINE.match(line)
        if not m:
            out.append('\t' + line.strip())
            continue
        start = _to_ym(m.group(1))
        end = _to_ym(m.group(2)) if m.group(2) else ''
        content = m.group(3).strip()
        out.append(f'{start}--{end}\t{content}')
    return out


_W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'


def _tr_height_emu(tr) -> int:
    """Read <w:trHeight w:val> from a raw <w:tr> element; val is in twips → EMU."""
    tr_pr = tr.find(f'{{{_W}}}trPr')
    if tr_pr is None:
        return 0
    tr_h = tr_pr.find(f'{{{_W}}}trHeight')
    if tr_h is None:
        return 0
    val = tr_h.get(f'{{{_W}}}val')
    return int(val) * 635 if val else 0   # 1 twip = 635 EMU


def _grid_col_of(tr, target_tc) -> int:
    """Return the grid-column index of target_tc inside tr."""
    col = 0
    for tc in tr.findall(f'{{{_W}}}tc'):
        if tc is target_tc:
            return col
        tc_pr = tc.find(f'{{{_W}}}tcPr')
        span = 1
        if tc_pr is not None:
            gs = tc_pr.find(f'{{{_W}}}gridSpan')
            if gs is not None:
                span = int(gs.get(f'{{{_W}}}val', 1))
        col += span
    return col


def _tc_at_grid_col(tr, target_col: int):
    """Return the <w:tc> element at grid-column target_col in tr, or None."""
    col = 0
    for tc in tr.findall(f'{{{_W}}}tc'):
        tc_pr = tc.find(f'{{{_W}}}tcPr')
        span = 1
        if tc_pr is not None:
            gs = tc_pr.find(f'{{{_W}}}gridSpan')
            if gs is not None:
                span = int(gs.get(f'{{{_W}}}val', 1))
        if col <= target_col < col + span:
            return tc
        col += span
    return None


def _shrink_para_by_1pt(para, fallback_pt: float = 10.5) -> bool:
    """Reduce every run's font size in para by 1 pt (min _MIN_FONT_PT). Returns True if changed."""
    if not para.runs:
        return False
    font_pt = _para_font_size_pt(para) or fallback_pt
    new_pt = 13.5
    if new_pt == font_pt:
        return False
    for run in para.runs:
        run.font.size = Pt(new_pt)
    return True


def _char_width_pt(ch: str, font_pt: float) -> float:
    """CJK / full-width chars count as full font_pt wide; ASCII as ~60%."""
    return font_pt if ord(ch) > 0x2E7F else font_pt * 0.6


def _text_width_pt(text: str, font_pt: float) -> float:
    return sum(_char_width_pt(c, font_pt) for c in text)


def _para_font_size_pt(para) -> Optional[float]:
    """Return font size in pt, walking run → style chain → base styles."""
    for run in para.runs:
        if run.font.size:
            return run.font.size / _PT_PER_EMU
    style = para.style
    while style is not None:
        try:
            if style.font.size:
                return style.font.size / _PT_PER_EMU
        except Exception:
            pass
        style = getattr(style, 'base_style', None)
    return None


# ── Exporter ──────────────────────────────────────────────────────────────────

class DocxExporter:
    def __init__(self, template_path: Path) -> None:
        self.template_path = Path(template_path)
        self._photo_cell_cache: Optional[tuple[int, int]] = None  # (width_emu, height_emu)
        self._xueli_shrink_text: Optional[str] = None   # XueLi text that needs post-shrink
        self._jianli_needs_shrink: bool = False          # JianLi > 12 lines

    def export(self, lrmx: LrmxFile, output_path: Path) -> None:
        tpl = DocxTemplate(self.template_path)
        context = self._build_context(lrmx, tpl)
        tpl.render(context)
        out = Path(output_path)
        tpl.save(out)
        # Post-process the saved file with plain python-docx. Doing this after
        # save (rather than via tpl.get_docx()) avoids disturbing docxtpl's
        # render/save pipeline.
        self._post_process(out)

    def _build_context(self, lrmx: LrmxFile, tpl: DocxTemplate) -> dict:
        raw = lrmx.as_dict()
        birth_ym = _INVIS.sub('', raw.get('ChuShengNianYue', ''))

        ctx: dict = {}
        for key, value in raw.items():
            if key in ('JianLi', _XUELI_KEY, _XUEWEI_KEY):
                continue  # handled separately below
            elif key == 'ZhaoPian':
                ctx[key] = self._decode_photo(value, tpl)
            elif key == 'ChuShengNianYue':
                ctx[key] = _format_birth(value)
            elif key == 'DaoLingNianYue':
                ctx[key] = _format_retire_age(value, birth_ym)
            elif key in _TIME6_FIELDS:
                ctx[key] = _format_time6(value)
            elif key in _TIME8_FIELDS:
                ctx[key] = _format_time8(value)
            else:
                ctx[key] = _INVIS.sub('', value)

        # JianLi: list of 'time<TAB>experience' strings for a
        # {%p for line in JianLi %}{{line}}{%p endfor %} loop. Column alignment
        # (hanging indent) is configured in the template, not here.
        jianli = _format_jianli_list(raw.get('JianLi', ''))
        self._jianli_needs_shrink = len(jianli) > 12
        ctx['JianLi'] = jianli

        # QuanRiZhiJiaoYu XueLi/XueWei overflow:
        #   > 12 chars + XueWei empty  → split: XueLi[:10] / XueLi[10:] → XueWei
        #   > 12 chars + XueWei filled → keep as-is, flag for post-process font shrink
        self._xueli_shrink_text = None
        xueli  = _INVIS.sub('', raw.get(_XUELI_KEY,  ''))
        xuewei = _INVIS.sub('', raw.get(_XUEWEI_KEY, ''))
        if len(xueli) > 12 and not xuewei:
            ctx[_XUELI_KEY]  = xueli[:10]
            ctx[_XUEWEI_KEY] = xueli[10:]
        elif len(xueli) > 12:
            ctx[_XUELI_KEY]  = xueli
            ctx[_XUEWEI_KEY] = xuewei
            self._xueli_shrink_text = xueli
        else:
            ctx[_XUELI_KEY]  = xueli
            ctx[_XUEWEI_KEY] = xuewei

        # JiaTingChengYuan: fixed indexed slots m0..m(MAX_FAMILY_SLOTS-1)
        family = self._build_family(lrmx)
        for i in range(MAX_FAMILY_SLOTS):
            ctx[f'm{i}'] = family[i] if i < len(family) else dict(_EMPTY_MEMBER)

        return ctx

    # ── Post-processing ───────────────────────────────────────────────────────

    def _post_process(self, path: Path) -> None:
        from docx import Document as DocxDoc
        doc = DocxDoc(path)
        changed = self._shrink_overflow_cells(doc)
        changed |= self._shrink_xueli_cell(doc)
        changed |= self._shrink_jianli_cell(doc)
        if changed:
            doc.save(path)

    def _shrink_overflow_cells(self, doc) -> bool:
        """In rows with exact height, shrink font by 1 pt when text exceeds cell width."""
        from docx.enum.table import WD_ROW_HEIGHT_RULE

        changed = False
        for table in doc.tables:
            seen: set[int] = set()
            for row in table.rows:
                if row.height_rule != WD_ROW_HEIGHT_RULE.EXACTLY:
                    continue
                for cell in row.cells:
                    cid = id(cell._tc)
                    if cid in seen:
                        continue
                    seen.add(cid)
                    if self._shrink_cell_if_needed(cell):
                        changed = True
        return changed

    @staticmethod
    def _shrink_cell_if_needed(cell) -> bool:
        cell_w = cell.width
        if not cell_w:
            return False
        usable_pt = cell_w / _PT_PER_EMU - 2 * _CELL_MARGIN_PT
        if usable_pt <= 0:
            return False
        changed = False
        for para in cell.paragraphs:
            text = para.text
            if not text.strip():
                continue
            font_pt = _para_font_size_pt(para)
            if not font_pt:
                continue
            if _text_width_pt(text, font_pt) > usable_pt:
                new_pt = max(font_pt - 1.0, _MIN_FONT_PT)
                for run in para.runs:
                    run.font.size = Pt(new_pt)
                changed = True
        return changed

    def _shrink_xueli_cell(self, doc) -> bool:
        """Shrink XueLi paragraph by 1 pt when it was too long and XueWei was filled."""
        if not self._xueli_shrink_text:
            return False
        changed = False
        for table in doc.tables:
            seen: set[int] = set()
            for row in table.rows:
                for cell in row.cells:
                    cid = id(cell._tc)
                    if cid in seen:
                        continue
                    seen.add(cid)
                    for para in cell.paragraphs:
                        if para.text == self._xueli_shrink_text:
                            changed |= _shrink_para_by_1pt(para)
        return changed

    def _shrink_jianli_cell(self, doc) -> bool:
        """Shrink JianLi cell paragraphs to 13.5pt and set line spacing when > 12 lines."""
        if not self._jianli_needs_shrink:
            return False
        changed = False
        processed: set[int] = set()
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    paras = cell.paragraphs
                    if not any(_JIANLI_RENDERED.search(p.text) for p in paras):
                        continue
                    cid = id(cell._tc)
                    if cid in processed:
                        continue
                    processed.add(cid)
                    for para in paras:
                        if _shrink_para_by_1pt(para):
                            changed = True
                            para.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
                            para.paragraph_format.line_spacing = Pt(14.5)
        return changed

    # ── Photo ────────────────────────────────────────────────────────────────

    def _get_photo_cell_size(self) -> Optional[tuple[int, int]]:
        """Return (width_emu, height_emu) of the photo cell, or None."""
        if self._photo_cell_cache is not None:
            return self._photo_cell_cache if self._photo_cell_cache[0] > 0 else None
        try:
            from docx import Document as DocxDoc
            doc = DocxDoc(self.template_path)
            for table in doc.tables:
                trs = table._tbl.findall(f'{{{_W}}}tr')
                for tr_idx, tr in enumerate(trs):
                    for tc in tr.findall(f'{{{_W}}}tc'):
                        if 'ZhaoPian' not in tc.xml:
                            continue
                        tc_pr = tc.find(f'{{{_W}}}tcPr')
                        vm = tc_pr.find(f'{{{_W}}}vMerge') if tc_pr is not None else None
                        if vm is not None and vm.get(f'{{{_W}}}val', '') != 'restart':
                            continue
                        # Cell width from <w:tcW w:w>
                        cell_w = 0
                        if tc_pr is not None:
                            tc_w_el = tc_pr.find(f'{{{_W}}}tcW')
                            if tc_w_el is not None:
                                w_val = tc_w_el.get(f'{{{_W}}}w')
                                w_type = tc_w_el.get(f'{{{_W}}}type', '')
                                if w_val and w_type == 'dxa':
                                    cell_w = int(w_val) * 635  # twips → EMU
                        # Fall back to python-docx row cell width
                        if cell_w == 0:
                            for row in table.rows:
                                for cell in row.cells:
                                    if cell._tc is tc and cell.width:
                                        cell_w = int(cell.width)
                                        break
                        # Accumulate cell height across merged rows
                        grid_col = _grid_col_of(tr, tc)
                        total_h = _tr_height_emu(tr)
                        for next_tr in trs[tr_idx + 1:]:
                            next_tc = _tc_at_grid_col(next_tr, grid_col)
                            if next_tc is None:
                                break
                            next_pr = next_tc.find(f'{{{_W}}}tcPr')
                            next_vm = next_pr.find(f'{{{_W}}}vMerge') if next_pr is not None else None
                            if next_vm is not None and next_vm.get(f'{{{_W}}}val', '') != 'restart':
                                total_h += _tr_height_emu(next_tr)
                            else:
                                break
                        if cell_w > 0 and total_h > 0:
                            self._photo_cell_cache = (cell_w, total_h)
                            return self._photo_cell_cache
        except Exception:
            pass
        self._photo_cell_cache = (-1, -1)
        return None

    def _decode_photo(self, b64: str, tpl: DocxTemplate) -> 'InlineImage | str':
        b64 = _INVIS.sub('', b64)
        if not b64:
            return ''
        try:
            from PIL import Image
            img_bytes = base64.b64decode(b64)
            size = self._get_photo_cell_size()
            if size:
                cell_w_emu, cell_h_emu = size
                # Crop left/right to match cell aspect ratio, then fit by height
                img = Image.open(BytesIO(img_bytes))
                pw, ph = img.size
                target_w = int(ph * cell_w_emu / cell_h_emu)
                if target_w < pw:
                    left = (pw - target_w) // 2
                    img = img.crop((left, 0, left + target_w, ph))
                buf = BytesIO()
                img.save(buf, format='JPEG')
                buf.seek(0)
                return InlineImage(tpl, buf, height=Emu(cell_h_emu))
            return InlineImage(tpl, BytesIO(img_bytes), height=Mm(45))
        except Exception:
            return ''

    # ── Family members ───────────────────────────────────────────────────────

    def _build_family(self, lrmx: LrmxFile) -> list[dict]:
        members = []
        for raw in lrmx.family_members():
            member: dict = {}
            for k, v in raw.items():
                if k == 'ChuShengRiQi':
                    v_clean = _INVIS.sub('', v)
                    member['Age'] = (
                        f'{_calc_age(v_clean)}岁'
                        if re.fullmatch(r'\d{6}', v_clean) else ''
                    )
                    member[k] = _format_time6(v_clean)
                else:
                    member[k] = _INVIS.sub('', v)
            gongzuo = member.get('GongZuoDanWeiJiZhiWu', '')
            if '已去世' in gongzuo or '已故' in gongzuo:
                member['Age'] = ''
            members.append(member)
        return members
