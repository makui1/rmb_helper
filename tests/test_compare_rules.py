# tests/test_compare_rules.py
import pytest
from app.core.compare_rules import (
    CompareRule,
    apply_rule,
    rules_to_json,
    rules_from_json,
    validate_date_format,
    validate_regex_pattern,
    to_py_format,
)


# ── to_py_format ──────────────────────────────────────────────────────────────

def test_to_py_format_year_month():
    assert to_py_format('yyyy.MM') == '%Y.%m'

def test_to_py_format_year_month_no_sep():
    assert to_py_format('yyyyMM') == '%Y%m'

def test_to_py_format_full_date():
    assert to_py_format('yyyy年MM月dd日') == '%Y年%m月%d日'

def test_to_py_format_no_tokens():
    assert to_py_format('invalid') == 'invalid'


# ── validate_date_format ──────────────────────────────────────────────────────

def test_validate_date_format_valid_dot():
    assert validate_date_format('yyyy.MM') is True

def test_validate_date_format_valid_no_sep():
    assert validate_date_format('yyyyMM') is True

def test_validate_date_format_valid_chinese():
    assert validate_date_format('yyyy年MM月') is True

def test_validate_date_format_year_only():
    assert validate_date_format('yyyy') is True

def test_validate_date_format_invalid():
    assert validate_date_format('invalid_fmt') is False

def test_validate_date_format_empty():
    assert validate_date_format('') is False


# ── validate_regex_pattern ────────────────────────────────────────────────────

def test_validate_regex_valid():
    assert validate_regex_pattern('[0-9]+') is True

def test_validate_regex_invalid():
    assert validate_regex_pattern('[unclosed') is False

def test_validate_regex_empty():
    assert validate_regex_pattern('') is False

def test_validate_regex_whitespace_only():
    assert validate_regex_pattern('   ') is False


# ── apply_rule (date) ─────────────────────────────────────────────────────────

@pytest.fixture
def date_rule():
    return CompareRule(name='月份格式', type='date', formats=['yyyy.MM', 'yyyyMM'])

def test_apply_date_rule_match(date_rule):
    assert apply_rule(date_rule, '1986.11', '198611') is True

def test_apply_date_rule_no_match(date_rule):
    assert apply_rule(date_rule, '1986.11', '198612') is False

def test_apply_date_rule_unparseable(date_rule):
    assert apply_rule(date_rule, '不是日期', '198611') is False

def test_apply_date_rule_both_unparseable(date_rule):
    assert apply_rule(date_rule, '不是日期', '也不是') is False

def test_apply_date_rule_same_format_match(date_rule):
    assert apply_rule(date_rule, '198611', '198611') is True

def test_apply_date_rule_strips_whitespace(date_rule):
    assert apply_rule(date_rule, '  1986.11  ', '198611') is True


# ── apply_rule (regex) ────────────────────────────────────────────────────────

@pytest.fixture
def regex_rule():
    return CompareRule(name='数字提取', type='regex', pattern=r'[0-9]+')

def test_apply_regex_rule_match(regex_rule):
    assert apply_rule(regex_rule, '第9个人', '共9个人') is True

def test_apply_regex_rule_no_match(regex_rule):
    assert apply_rule(regex_rule, '第9个人', '共8个人') is False

def test_apply_regex_rule_both_empty(regex_rule):
    assert apply_rule(regex_rule, '无数字', '也无数字') is True

def test_apply_regex_rule_bad_pattern():
    bad_rule = CompareRule(name='bad', type='regex', pattern='[unclosed')
    assert apply_rule(bad_rule, 'abc', 'abc') is False

def test_apply_regex_rule_multiple_matches(regex_rule):
    assert apply_rule(regex_rule, '123 456', '123456') is True


# ── unknown rule type ─────────────────────────────────────────────────────────

def test_apply_unknown_type_returns_false():
    rule = CompareRule(name='x', type='unknown', formats=[])
    assert apply_rule(rule, 'a', 'a') is False


# ── JSON 往返 ─────────────────────────────────────────────────────────────────

def test_json_roundtrip_date():
    rules = [CompareRule(name='月份格式', type='date', formats=['yyyy.MM', 'yyyyMM'], pattern='')]
    loaded = rules_from_json(rules_to_json(rules))
    assert len(loaded) == 1
    assert loaded[0].name == '月份格式'
    assert loaded[0].type == 'date'
    assert loaded[0].formats == ['yyyy.MM', 'yyyyMM']
    assert loaded[0].pattern == ''

def test_json_roundtrip_regex():
    rules = [CompareRule(name='数字', type='regex', formats=[], pattern=r'[0-9]+')]
    loaded = rules_from_json(rules_to_json(rules))
    assert loaded[0].pattern == r'[0-9]+'

def test_json_roundtrip_empty():
    assert rules_from_json(rules_to_json([])) == []

def test_json_from_empty_string():
    assert rules_from_json('') == []

def test_json_from_invalid():
    assert rules_from_json('not json') == []
