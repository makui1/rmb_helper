import base64
import re
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Optional

from docxtpl import DocxTemplate, InlineImage
from docx.shared import Emu, Mm

from .lrmx import LrmxFile

# ── Field classification ──────────────────────────────────────────────────────

_TIME6_FIELDS = frozenset({
    'RuDangShiJian', 'CanJiaGongZuoShiJian', 'TianBiaoShiJian',
})
_TIME8_FIELDS = frozenset({'JiSuanNianLingShiJian'})

_INVIS = re.compile(r'[\s​‌‍﻿ 　]+')

# 6-digit or yyyy.MM date at start of JianLi line (try 6-digit first)
_JIANLI_LINE = re.compile(r'^(\d{6}|\d{4}(?:\.\d{2})?)--(\d{6}|\d{4}(?:\.\d{2}))?(.*)')


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
    """Age in years from birth yyyyMM to today."""
    v = _INVIS.sub('', ym6)
    if not re.fullmatch(r'\d{6}', v):
        return 0
    year, month = int(v[:4]), int(v[4:])
    today = date.today()
    age = today.year - year
    if today.month < month:
        age -= 1
    return age


def _format_birth(value: str) -> str:
    """ChuShengNianYue: yyyy.MM\n（X岁）"""
    v = _INVIS.sub('', value)
    formatted = _format_time6(v)
    if re.fullmatch(r'\d{6}', v):
        return f'{formatted}\n（{_calc_age(v)}岁）'
    return formatted


def _format_retire(value: str) -> str:
    """DaoLingNianYue: yyyy.MM\n（X年Y月后退休）or（已到龄）"""
    v = _INVIS.sub('', value)
    formatted = _format_time6(v)
    if re.fullmatch(r'\d{6}', v):
        year, month = int(v[:4]), int(v[4:])
        today = date.today()
        total_months = (year * 12 + month) - (today.year * 12 + today.month)
        if total_months <= 0:
            return f'{formatted}\n（已到龄）'
        yrs, mos = divmod(total_months, 12)
        if mos == 0:
            return f'{formatted}\n（{yrs}年后退休）'
        return f'{formatted}\n（{yrs}年{mos}个月后退休）'
    return formatted


def _format_jianli_list(text: str) -> list[str]:
    """Return JianLi as list of normalized entry strings (one per line)."""
    if not text or not text.strip():
        return []
    out = []
    for line in text.split('\n'):
        if not line.strip():
            continue
        m = _JIANLI_LINE.match(line)
        if not m:
            out.append(line)
            continue
        start = _to_ym(m.group(1))                               # 7 chars
        end = _to_ym(m.group(2)) if m.group(2) else '       '   # 7 chars or 7 spaces
        content = m.group(3).strip()
        out.append(f'{start}--{end}  {content}')
    return out


class DocxExporter:
    def __init__(self, template_path: Path) -> None:
        self.template_path = Path(template_path)
        self._photo_cell_width: Optional[int] = None   # EMUs, cached

    def export(self, lrmx: LrmxFile, output_path: Path) -> None:
        tpl = DocxTemplate(self.template_path)
        context = self._build_context(lrmx, tpl)
        tpl.render(context)
        tpl.save(output_path)

    def _build_context(self, lrmx: LrmxFile, tpl: DocxTemplate) -> dict:
        ctx: dict = {}
        for key, value in lrmx.as_dict().items():
            if key == 'JianLi':
                ctx[key] = _format_jianli_list(value)
            elif key == 'ZhaoPian':
                ctx[key] = self._decode_photo(value, tpl)
            elif key == 'ChuShengNianYue':
                ctx[key] = _format_birth(value)
            elif key == 'DaoLingNianYue':
                ctx[key] = _format_retire(value)
            elif key in _TIME6_FIELDS:
                ctx[key] = _format_time6(value)
            elif key in _TIME8_FIELDS:
                ctx[key] = _format_time8(value)
            else:
                ctx[key] = _INVIS.sub('', value)
        ctx['JiaTingChengYuan'] = self._build_family(lrmx)
        return ctx

    def _photo_width_emu(self) -> Optional[int]:
        """Read the width of the ZhaoPian cell from the template (cached)."""
        if self._photo_cell_width is not None:
            return self._photo_cell_width
        try:
            from docx import Document as DocxDoc
            doc = DocxDoc(self.template_path)
            for table in doc.tables:
                for row in table.rows:
                    for cell in row.cells:
                        if 'ZhaoPian' in cell._tc.xml:
                            w = cell.width
                            if w:
                                self._photo_cell_width = int(w)
                                return self._photo_cell_width
        except Exception:
            pass
        self._photo_cell_width = -1   # sentinel: no cell found
        return None

    def _decode_photo(self, b64: str, tpl: DocxTemplate) -> 'InlineImage | str':
        b64 = _INVIS.sub('', b64)
        if not b64:
            return ''
        try:
            img_bytes = base64.b64decode(b64)
            width_emu = self._photo_width_emu()
            if width_emu and width_emu > 0:
                return InlineImage(tpl, BytesIO(img_bytes), width=Emu(width_emu))
            return InlineImage(tpl, BytesIO(img_bytes), width=Mm(26))
        except Exception:
            return ''

    def _build_family(self, lrmx: LrmxFile) -> list[dict]:
        members = []
        for raw in lrmx.family_members():
            member: dict = {}
            for k, v in raw.items():
                if k == 'ChuShengRiQi':
                    v_clean = _INVIS.sub('', v)
                    member['Age'] = f'{_calc_age(v_clean)}岁' if re.fullmatch(r'\d{6}', v_clean) else ''
                    member[k] = _format_time6(v_clean)
                else:
                    member[k] = _INVIS.sub('', v)
            members.append(member)
        return members
