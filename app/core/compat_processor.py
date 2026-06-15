"""
Compatibility processor: upgrade old lrmx files to new format by adding
GaiGeQianRenZhiNianLingJieXian and DaoLingNianYue fields.

Reform law (effective 2025-01-01):
  Male (base 60): +1 month delay every 4 months, up to +36 months (→63)
  Female base 55: +1 month delay every 4 months, up to +36 months (→58)
  Female base 50: +1 month delay every 2 months, up to +60 months (→55) [reserved]
"""
from pathlib import Path
from typing import Optional

from app.core.lrmx import LrmxFile

_ALL_LIMIT_OPTIONS = [
    '改革前任职年龄界限为55岁',
    '改革前任职年龄界限为60岁',
    '改革前任职年龄界限为63岁',
    '改革前任职年龄界限为65岁',
    '改革前任职年龄界限为66岁',
]
MALE_LIMIT_OPTIONS = _ALL_LIMIT_OPTIONS
FEMALE_LIMIT_OPTIONS = _ALL_LIMIT_OPTIONS

# Only these base ages have a defined reform calculation
_BASE_AGE_RULES: dict[int, tuple[int, int]] = {
    60: (4, 36),   # (delay_interval_months, max_delay_months)
    55: (4, 36),
    50: (2, 60),
}

_LIMIT_TO_BASE_AGE: dict[str, int] = {
    '改革前任职年龄界限为60岁': 60,
    '改革前任职年龄界限为55岁': 55,
}


def _add_months(year: int, month: int, delta: int) -> tuple[int, int]:
    total = year * 12 + month + delta
    return (total - 1) // 12, (total - 1) % 12 + 1


def calc_daolignianue(birth_ym: str, limit_str: str) -> str:
    """
    Calculate DaoLingNianYue (YYYYMM) from birth year-month (YYYYMM) and limit string.
    Returns '' for limit categories that have no defined reform formula (63/65/66).
    """
    base_age = _LIMIT_TO_BASE_AGE.get(limit_str)
    if base_age is None:
        return ''

    birth_year = int(birth_ym[:4])
    birth_month = int(birth_ym[4:6])

    # Pre-reform retirement date (same month, base_age years later)
    retire_year = birth_year + base_age
    retire_month = birth_month

    # n: months from Jan 2025 to original retirement (1 = Jan 2025, ≤0 = before reform)
    n = (retire_year - 2025) * 12 + retire_month

    interval, max_delay = _BASE_AGE_RULES[base_age]
    delay = min(max_delay, (n - 1) // interval + 1) if n >= 1 else 0

    new_year, new_month = _add_months(retire_year, retire_month, delay)
    return f'{new_year:04d}{new_month:02d}'


def is_new_version(lf: LrmxFile) -> bool:
    """Return True if the file already has both new fields filled in."""
    return bool(lf.get('DaoLingNianYue') and lf.get('GaiGeQianRenZhiNianLingJieXian'))


def process_file(
    path: Path,
    male_limit: str,
    female_limit: str,
    output_path: Optional[Path] = None,
) -> tuple[str, str]:
    """
    Process a single lrmx file.

    Returns (status, message):
      'skip'  – already new version, not modified
      'ok'    – processed successfully
      'error' – failed, message contains reason
    """
    lf = LrmxFile(path)

    if is_new_version(lf):
        return 'skip', f'{path.name}（已是新版本，已跳过）'

    xingbie = lf.get('XingBie')
    birth_ym = lf.get('ChuShengNianYue')

    if not birth_ym:
        return 'error', f'{path.name}：缺少出生年月字段'

    if xingbie == '男':
        limit_str = male_limit
    elif xingbie == '女':
        limit_str = female_limit
    else:
        return 'error', f'{path.name}：无法识别性别（XingBie={repr(xingbie)}）'

    daolignianue = calc_daolignianue(birth_ym, limit_str)

    lf.set('GaiGeQianRenZhiNianLingJieXian', limit_str)
    lf.set('DaoLingNianYue', daolignianue)
    lf.save(output_path or path)

    calc_note = daolignianue[:4] + '.' + daolignianue[4:] if daolignianue else '暂不计算'
    return 'ok', f'{path.stem}：{limit_str}，到龄年月 {calc_note}'
