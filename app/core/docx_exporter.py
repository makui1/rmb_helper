import base64
import re
from datetime import date
from io import BytesIO
from pathlib import Path

from docxtpl import DocxTemplate, InlineImage
from docx.shared import Mm

from .lrmx import LrmxFile

# ── Field classification ──────────────────────────────────────────────────────

_TIME6_FIELDS = frozenset({
    'ChuShengNianYue', 'RuDangShiJian', 'CanJiaGongZuoShiJian',
    'DaoLingNianYue', 'TianBiaoShiJian',
})
_AGE_FIELDS = frozenset({'ChuShengNianYue', 'DaoLingNianYue'})
_TIME8_FIELDS = frozenset({'JiSuanNianLingShiJian'})

_INVIS = re.compile(r'[\s​‌‍﻿]+')
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
    v = _INVIS.sub('', ym6)
    if not re.fullmatch(r'\d{6}', v):
        return 0
    year, month = int(v[:4]), int(v[4:])
    today = date.today()
    age = today.year - year
    if today.month < month:
        age -= 1
    return age


def _format_with_age(value: str) -> str:
    v = _INVIS.sub('', value)
    formatted = _format_time6(v)
    if re.fullmatch(r'\d{6}', v):
        return f'{formatted}\n（{_calc_age(v)}岁）'
    return formatted


def _format_jianli(text: str) -> str:
    lines = text.split('\n')
    out = []
    for line in lines:
        m = _JIANLI_LINE.match(line)
        if not m:
            out.append(line)
            continue
        start = _to_ym(m.group(1))
        end = _to_ym(m.group(2)) if m.group(2) else '       '
        content = m.group(3).strip()
        out.append(f'{start}--{end}  {content}')
    return '\n'.join(out)


class DocxExporter:
    def __init__(self, template_path: Path) -> None:
        self.template_path = Path(template_path)

    def export(self, lrmx: LrmxFile, output_path: Path) -> None:
        tpl = DocxTemplate(self.template_path)
        context = self._build_context(lrmx, tpl)
        tpl.render(context)
        tpl.save(output_path)

    def _build_context(self, lrmx: LrmxFile, tpl: DocxTemplate) -> dict:
        ctx: dict = {}
        for key, value in lrmx.as_dict().items():
            if key == 'JianLi':
                ctx[key] = _format_jianli(value)
            elif key == 'ZhaoPian':
                ctx[key] = self._decode_photo(value, tpl)
            elif key in _AGE_FIELDS:
                ctx[key] = _format_with_age(value)
            elif key in _TIME6_FIELDS:
                ctx[key] = _format_time6(value)
            elif key in _TIME8_FIELDS:
                ctx[key] = _format_time8(value)
            else:
                ctx[key] = _INVIS.sub('', value)
        ctx['JiaTingChengYuan'] = self._build_family(lrmx, tpl)
        return ctx

    def _decode_photo(self, b64: str, tpl: DocxTemplate) -> 'InlineImage | str':
        b64 = _INVIS.sub('', b64)
        if not b64:
            return ''
        try:
            img_bytes = base64.b64decode(b64)
            return InlineImage(tpl, BytesIO(img_bytes), width=Mm(26))
        except Exception:
            return ''

    def _build_family(self, lrmx: LrmxFile, tpl: DocxTemplate) -> list[dict]:
        members = []
        for raw in lrmx.family_members():
            member = {}
            for k, v in raw.items():
                if k == 'ChuShengRiQi':
                    member[k] = _format_time6(v)
                else:
                    member[k] = _INVIS.sub('', v)
            members.append(member)
        return members
