from __future__ import annotations
import json
import re
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class CompareRule:
    name: str
    type: str           # 'date' | 'regex'
    formats: list[str] = field(default_factory=list)
    pattern: str = ''


def to_py_format(fmt: str) -> str:
    result = fmt
    result = result.replace('yyyy', '%Y')
    result = result.replace('MM', '%m')
    result = result.replace('dd', '%d')
    return result


def validate_date_format(fmt: str) -> bool:
    if not fmt or not any(token in fmt for token in ('yyyy', 'MM', 'dd')):
        return False
    py_fmt = to_py_format(fmt)
    try:
        sample = datetime(2000, 1, 15)
        formatted = sample.strftime(py_fmt)
        datetime.strptime(formatted, py_fmt)
        return True
    except (ValueError, TypeError):
        return False


def validate_regex_pattern(pattern: str) -> bool:
    if not pattern or not pattern.strip():
        return False
    try:
        re.compile(pattern)
        return True
    except re.error:
        return False


def _try_parse(s: str, py_fmts: list[str]) -> datetime | None:
    for fmt in py_fmts:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _compare_date(rule: CompareRule, a: str, b: str) -> bool:
    py_fmts = [to_py_format(f) for f in rule.formats]
    pa = _try_parse(a.strip(), py_fmts)
    pb = _try_parse(b.strip(), py_fmts)
    return pa is not None and pb is not None and pa == pb


def _compare_regex(rule: CompareRule, a: str, b: str) -> bool:
    try:
        ma = ''.join(re.findall(rule.pattern, a))
        mb = ''.join(re.findall(rule.pattern, b))
        return ma == mb
    except re.error:
        return False


def apply_rule(rule: CompareRule, a: str, b: str) -> bool:
    if rule.type == 'date':
        return _compare_date(rule, a, b)
    if rule.type == 'regex':
        return _compare_regex(rule, a, b)
    return False


def rules_to_json(rules: list[CompareRule]) -> str:
    return json.dumps(
        [
            {
                'name': r.name,
                'type': r.type,
                'formats': r.formats,
                'pattern': r.pattern,
            }
            for r in rules
        ],
        ensure_ascii=False,
    )


def rules_from_json(s: str) -> list[CompareRule]:
    if not s:
        return []
    try:
        data = json.loads(s)
        return [
            CompareRule(
                name=d.get('name', ''),
                type=d.get('type', 'date'),
                formats=d.get('formats', []),
                pattern=d.get('pattern', ''),
            )
            for d in data
        ]
    except (json.JSONDecodeError, TypeError, AttributeError):
        return []
