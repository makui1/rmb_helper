"""转换器系统：内置预设 + 用户可编写自定义 Python 代码片段。

统一接口: def convert(value: str) -> str
"""
from __future__ import annotations

import builtins
import json
import re
from datetime import datetime
from PySide6.QtCore import QSettings


# ═══════════════════════════════════════════════════════════════════════
# 内置转换器函数
# ═══════════════════════════════════════════════════════════════════════

def _convert_date_yyyyMM_to_dot(value: str) -> str:
    """202506 → 2025.06"""
    v = value.strip()
    if len(v) != 6 or not v.isdigit():
        return value
    try:
        return datetime.strptime(v, '%Y%m').strftime('%Y.%m')
    except ValueError:
        return value


def _convert_date_yyyyMMdd_to_dot(value: str) -> str:
    """20250625 → 2025.06.25"""
    v = value.strip()
    if len(v) != 8 or not v.isdigit():
        return value
    try:
        return datetime.strptime(v, '%Y%m%d').strftime('%Y.%m.%d')
    except ValueError:
        return value


def _convert_date_dot_to_yyyyMM(value: str) -> str:
    """2025.06 → 202506"""
    v = value.strip()
    try:
        return datetime.strptime(v, '%Y.%m').strftime('%Y%m')
    except ValueError:
        return value


def _convert_date_dot_to_yyyyMMdd(value: str) -> str:
    """2025.06.25 → 20250625"""
    v = value.strip()
    try:
        return datetime.strptime(v, '%Y.%m.%d').strftime('%Y%m%d')
    except ValueError:
        return value


def _convert_strip_spaces(value: str) -> str:
    """去除所有空白字符"""
    return re.sub(r'\s+', '', value)


def _convert_gender_m_to_1(value: str) -> str:
    """男→1, 女→2"""
    return {'男': '1', '女': '2'}.get(value.strip(), value)


def _convert_gender_1_to_m(value: str) -> str:
    """1→男, 2→女"""
    return {'1': '男', '2': '女'}.get(value.strip(), value)


# ── 内置转换器元数据：(名称, 源码, 函数对象) ──────────────────────────

_BUILTIN_META: list[tuple[str, str, callable]] = [
    ('日期: yyyyMM → yyyy.MM',
     'def convert(value: str) -> str:\n'
     '    """202506 → 2025.06"""\n'
     '    from datetime import datetime\n'
     '    v = value.strip()\n'
     '    if len(v) != 6 or not v.isdigit():\n'
     '        return value\n'
     '    try:\n'
     '        return datetime.strptime(v, "%Y%m").strftime("%Y.%m")\n'
     '    except ValueError:\n'
     '        return value\n',
     _convert_date_yyyyMM_to_dot),
    ('日期: yyyyMMdd → yyyy.MM.dd',
     'def convert(value: str) -> str:\n'
     '    """20250625 → 2025.06.25"""\n'
     '    from datetime import datetime\n'
     '    v = value.strip()\n'
     '    if len(v) != 8 or not v.isdigit():\n'
     '        return value\n'
     '    try:\n'
     '        return datetime.strptime(v, "%Y%m%d").strftime("%Y.%m.%d")\n'
     '    except ValueError:\n'
     '        return value\n',
     _convert_date_yyyyMMdd_to_dot),
    ('日期: yyyy.MM → yyyyMM',
     'def convert(value: str) -> str:\n'
     '    """2025.06 → 202506"""\n'
     '    from datetime import datetime\n'
     '    v = value.strip()\n'
     '    try:\n'
     '        return datetime.strptime(v, "%Y.%m").strftime("%Y%m")\n'
     '    except ValueError:\n'
     '        return value\n',
     _convert_date_dot_to_yyyyMM),
    ('日期: yyyy.MM.dd → yyyyMMdd',
     'def convert(value: str) -> str:\n'
     '    """2025.06.25 → 20250625"""\n'
     '    from datetime import datetime\n'
     '    v = value.strip()\n'
     '    try:\n'
     '        return datetime.strptime(v, "%Y.%m.%d").strftime("%Y%m%d")\n'
     '    except ValueError:\n'
     '        return value\n',
     _convert_date_dot_to_yyyyMMdd),
    ('正则: 去除空格',
     'def convert(value: str) -> str:\n'
     '    """去除所有空白字符"""\n'
     '    import re\n'
     '    return re.sub(r"\\s+", "", value)\n',
     _convert_strip_spaces),
    ('字典: 性别(男→1)',
     'def convert(value: str) -> str:\n'
     '    """男→1, 女→2"""\n'
     '    return {"男": "1", "女": "2"}.get(value.strip(), value)\n',
     _convert_gender_m_to_1),
    ('字典: 性别(1→男)',
     'def convert(value: str) -> str:\n'
     '    """1→男, 2→女"""\n'
     '    return {"1": "男", "2": "女"}.get(value.strip(), value)\n',
     _convert_gender_1_to_m),
]

BUILTIN_CONVERTERS: list[dict] = [
    {'name': name, 'code': code, 'builtin': True}
    for name, code, _fn in _BUILTIN_META
]

# 内置名称 → 函数对象（快速执行）
_BUILTIN_FN: dict[str, callable] = {
    name: fn for name, _code, fn in _BUILTIN_META
}

# 内置源码 → 名称（执行时判断是否匹配内置）
_BUILTIN_CODE_TO_NAME: dict[str, str] = {
    code.strip(): name for name, code, _fn in _BUILTIN_META
}


# ═══════════════════════════════════════════════════════════════════════
# 用户自定义转换器存储
# ═══════════════════════════════════════════════════════════════════════

def load_custom_converters(settings: QSettings) -> list[dict]:
    raw = settings.value('converters_custom', '')
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return [
            {'name': d.get('name', ''), 'code': d.get('code', ''), 'builtin': False}
            for d in data
        ]
    except (json.JSONDecodeError, TypeError, AttributeError):
        return []


def save_custom_converters(settings: QSettings, converters: list[dict]) -> None:
    data = [
        {'name': c['name'], 'code': c['code']}
        for c in converters
        if not c.get('builtin', False)
    ]
    settings.setValue('converters_custom', json.dumps(data, ensure_ascii=False))


def get_all_converters(settings: QSettings) -> list[dict]:
    return BUILTIN_CONVERTERS + load_custom_converters(settings)


# ═══════════════════════════════════════════════════════════════════════
# 转换器执行
# ═══════════════════════════════════════════════════════════════════════

# 用户代码 exec 安全白名单
_EXEC_GLOBALS = {
    '__builtins__': {
        '__import__': __import__,
        '__orig_import__': getattr(builtins, '__orig_import__', __import__),
        'str': str, 'int': int, 'float': float, 'bool': bool,
        'len': len, 'dict': dict, 'list': list, 'tuple': tuple, 'set': set,
        'True': True, 'False': False, 'None': None,
        'abs': abs, 'min': min, 'max': max, 'sum': sum,
        'enumerate': enumerate, 'zip': zip, 'range': range,
        'isinstance': isinstance, 'type': type,
        'print': print,
        're': re,
        'json': json,
    },
    'datetime': __import__('datetime'),
    're': re,
    'json': json,
}


def execute_converter(code: str, value: str) -> str:
    """执行转换器代码。内置按函数表查；用户代码用 exec 沙箱执行。失败返回原值。"""
    if not code or not code.strip():
        return value

    # 内置转换器直接查表执行
    stripped = code.strip()
    if stripped in _BUILTIN_CODE_TO_NAME:
        fn = _BUILTIN_FN.get(_BUILTIN_CODE_TO_NAME[stripped])
        if fn:
            try:
                return fn(value)
            except Exception:
                return value

    # 用户代码 exec
    try:
        local_ns: dict[str, object] = {}
        exec(code, _EXEC_GLOBALS, local_ns)
        convert_fn = local_ns.get('convert')
        if not callable(convert_fn):
            return value
        result = convert_fn(value)
        return str(result) if result is not None else ''
    except Exception:
        return value
