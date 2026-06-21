import re

FIELD_PATTERN = re.compile(r'\{(\w+)\}')
ILLEGAL_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
# 不可见字符：零宽字符、BOM、软连字符、不间断空格等
_INVISIBLE_RE = re.compile(r'[​-‏‪-‮⁠﻿\xad\xa0]+')

PRESETS: list[tuple[str, str]] = [
    ('{XingMing}{ShenFenZheng}', '姓名+身份证号'),
    ('{XingMing}_{XianRenZhiWu}', '姓名+现任职务'),
    ('{XingMing}_{ChuShengNianYue}', '姓名+出生年月'),
]


def clean_field(value: str) -> str:
    """去除字段值中的不可见字符和首尾空白。"""
    value = _INVISIBLE_RE.sub('', value)
    return value.strip()


def apply_rule(template: str, fields: dict[str, str]) -> str:
    def replace(m: re.Match) -> str:
        key = m.group(1)
        raw = fields.get(key, f'{{{key}}}')
        return clean_field(raw)

    result = FIELD_PATTERN.sub(replace, template)
    result = ILLEGAL_CHARS.sub('_', result)
    return result or '未命名'
