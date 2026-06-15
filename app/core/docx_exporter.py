import base64
import re
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Optional

from docxtpl import DocxTemplate, InlineImage
from docx.shared import Emu, Mm

from .lrmx import LrmxFile

# ── Constants ─────────────────────────────────────────────────────────────────

MAX_FAMILY_SLOTS = 10   # how many m0..m9 slots to expose; should exceed any template

_EMPTY_MEMBER: dict[str, str] = {
    'ChengWei': '', 'XingMing': '', 'Age': '',
    'ChuShengRiQi': '', 'ZhengZhiMianMao': '', 'GongZuoDanWeiJiZhiWu': '',
}

# ── Field classification ──────────────────────────────────────────────────────

_TIME6_FIELDS = frozenset({
    'RuDangShiJian', 'CanJiaGongZuoShiJian', 'TianBiaoShiJian',
})
_TIME8_FIELDS = frozenset({'JiSuanNianLingShiJian'})

# Matches all whitespace variants + invisible Unicode chars
_INVIS = re.compile(r'[\s​‌‍﻿ 　]+')

# JianLi line: optional 6-digit or yyyy.MM date, then --, optional end date, then rest
_JIANLI_LINE = re.compile(r'^(\d{6}|\d{4}\.\d{2})--(\d{6}|\d{4}\.\d{2})?(.*)')


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
    """Normalize each JianLi line to the 18-char prefix format and return as list."""
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


def _split_jianli_entry(entry: str) -> dict[str, str]:
    """Split a normalized 18-char-prefix entry into time and exp parts."""
    # Entry format: 'yyyy.MM--yyyy.MM  content' or 'yyyy.MM--         content'
    # Prefix is exactly 18 chars: 7(start) + 2(--) + 7(end or spaces) + 2(spaces)
    if len(entry) >= 18:
        time_part = entry[:16].rstrip()   # 'yyyy.MM--yyyy.MM' or 'yyyy.MM--'
        exp_part = entry[18:]
    else:
        time_part = entry
        exp_part = ''
    return {'time': time_part, 'exp': exp_part}


# ── Exporter ──────────────────────────────────────────────────────────────────

class DocxExporter:
    def __init__(self, template_path: Path) -> None:
        self.template_path = Path(template_path)
        self._photo_width_cache: Optional[int] = None   # EMUs

    def export(self, lrmx: LrmxFile, output_path: Path) -> None:
        tpl = DocxTemplate(self.template_path)
        context = self._build_context(lrmx, tpl)
        tpl.render(context)
        tpl.save(output_path)

    def _build_context(self, lrmx: LrmxFile, tpl: DocxTemplate) -> dict:
        raw = lrmx.as_dict()
        birth_ym = _INVIS.sub('', raw.get('ChuShengNianYue', ''))

        ctx: dict = {}
        for key, value in raw.items():
            if key == 'JianLi':
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

        # JianLi: both plain list (for {%p for e in JianLi %} usage)
        # and table form (for 2-column {%tr for e in JianLiTable %} usage)
        jianli_lines = _format_jianli_list(raw.get('JianLi', ''))
        ctx['JianLi'] = jianli_lines
        ctx['JianLiTable'] = [_split_jianli_entry(e) for e in jianli_lines]

        # JiaTingChengYuan: fixed indexed slots m0..m(MAX_FAMILY_SLOTS-1)
        family = self._build_family(lrmx)
        for i in range(MAX_FAMILY_SLOTS):
            ctx[f'm{i}'] = family[i] if i < len(family) else dict(_EMPTY_MEMBER)

        return ctx

    # ── Photo ────────────────────────────────────────────────────────────────

    def _get_photo_width_emu(self) -> Optional[int]:
        if self._photo_width_cache is not None:
            return self._photo_width_cache if self._photo_width_cache > 0 else None
        try:
            from docx import Document as DocxDoc
            doc = DocxDoc(self.template_path)
            for table in doc.tables:
                for row in table.rows:
                    for cell in row.cells:
                        if 'ZhaoPian' in cell._tc.xml:
                            w = cell.width
                            if w and w > 0:
                                self._photo_width_cache = int(w)
                                return self._photo_width_cache
        except Exception:
            pass
        self._photo_width_cache = -1
        return None

    def _decode_photo(self, b64: str, tpl: DocxTemplate) -> 'InlineImage | str':
        b64 = _INVIS.sub('', b64)
        if not b64:
            return ''
        try:
            img_bytes = base64.b64decode(b64)
            cell_w = self._get_photo_width_emu()
            if cell_w:
                return InlineImage(tpl, BytesIO(img_bytes), width=Emu(cell_w))
            return InlineImage(tpl, BytesIO(img_bytes), width=Mm(26))
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
            members.append(member)
        return members
