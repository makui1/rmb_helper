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
    empty: list[str] = []

    def replace(m: re.Match) -> str:
        key = m.group(1)
        if key not in fields:
            return f'{{{key}}}'
        val = clean_field(fields[key])
        # 字段值内的非法字符直接删除（不替换成 _），避免尾部多余下划线
        val = ILLEGAL_CHARS.sub('', val)
        if not val:
            empty.append(key)
        return val

    result = FIELD_PATTERN.sub(replace, template)
    if empty:
        raise ValueError(f'字段值为空：{", ".join(empty)}')
    # 模板分隔符（如 _ ）保留；只有模板本身含非法字符时才替换
    result = ILLEGAL_CHARS.sub('_', result)
    if not result:
        raise ValueError('命名结果为空')
    return result
