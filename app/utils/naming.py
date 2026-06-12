import re

FIELD_PATTERN = re.compile(r'\{(\w+)\}')
ILLEGAL_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

PRESETS: list[tuple[str, str]] = [
    ('{XingMing}{ShenFenZheng}', '姓名+身份证号'),
    ('{XingMing}_{XianRenZhiWu}', '姓名+现任职务'),
    ('{XingMing}_{ChuShengNianYue}', '姓名+出生年月'),
]


def apply_rule(template: str, fields: dict[str, str]) -> str:
    def replace(m: re.Match) -> str:
        key = m.group(1)
        return fields.get(key, f'{{{key}}}')

    result = FIELD_PATTERN.sub(replace, template)
    result = ILLEGAL_CHARS.sub('_', result)
    return result or '未命名'
