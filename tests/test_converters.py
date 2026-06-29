import pytest
from app.core.converters import (
    execute_converter, BUILTIN_CONVERTERS,
    get_all_converters, load_custom_converters, save_custom_converters,
)


class TestBuiltinConverters:
    def test_date_yyyyMM_to_dot(self):
        code = BUILTIN_CONVERTERS[0]['code']
        assert execute_converter(code, '202506') == '2025.06'
        assert execute_converter(code, 'abc') == 'abc'

    def test_date_yyyyMMdd_to_dot(self):
        code = BUILTIN_CONVERTERS[1]['code']
        assert execute_converter(code, '20250625') == '2025.06.25'

    def test_date_dot_to_yyyyMM(self):
        code = BUILTIN_CONVERTERS[2]['code']
        assert execute_converter(code, '2025.06') == '202506'

    def test_date_dot_to_yyyyMMdd(self):
        code = BUILTIN_CONVERTERS[3]['code']
        assert execute_converter(code, '2025.06.25') == '20250625'

    def test_strip_spaces(self):
        code = BUILTIN_CONVERTERS[4]['code']
        assert execute_converter(code, '张 三') == '张三'

    def test_gender_m_to_1(self):
        code = BUILTIN_CONVERTERS[5]['code']
        assert execute_converter(code, '男') == '1'
        assert execute_converter(code, '女') == '2'
        assert execute_converter(code, '未知') == '未知'

    def test_gender_1_to_m(self):
        code = BUILTIN_CONVERTERS[6]['code']
        assert execute_converter(code, '1') == '男'
        assert execute_converter(code, '2') == '女'


class TestUserConverters:
    def test_execute_valid_custom_code(self):
        code = 'def convert(value: str) -> str:\n    return value.upper()\n'
        assert execute_converter(code, 'hello') == 'HELLO'

    def test_execute_code_with_regex(self):
        code = (
            'def convert(value: str) -> str:\n'
            '    import re\n'
            '    return re.sub(r"(\\d{4})(\\d{2})(\\d{2})", r"\\1.\\2.\\3", value)\n'
        )
        assert execute_converter(code, '20250625') == '2025.06.25'

    def test_execute_invalid_code_returns_original(self):
        code = 'def convert(value: str) -> str:\n    raise ValueError("oops")\n'
        assert execute_converter(code, 'hello') == 'hello'

    def test_execute_empty_code_returns_original(self):
        assert execute_converter('', 'hello') == 'hello'

    def test_execute_none_result_returns_empty(self):
        code = 'def convert(value: str) -> str:\n    return None\n'
        assert execute_converter(code, 'hello') == ''


class TestPersistence:
    def test_load_empty(self):
        from PySide6.QtCore import QSettings
        settings = QSettings('test_rmb', 'test_rmb')
        settings.setValue('converters_custom', '')
        result = load_custom_converters(settings)
        assert result == []

    def test_roundtrip(self):
        from PySide6.QtCore import QSettings
        settings = QSettings('test_rmb', 'test_rmb')
        converters = [{'name': 'test', 'code': 'def convert(v): return v', 'builtin': False}]
        save_custom_converters(settings, converters)
        loaded = load_custom_converters(settings)
        assert len(loaded) == 1
        assert loaded[0]['name'] == 'test'

    def test_get_all_includes_builtins(self):
        from PySide6.QtCore import QSettings
        settings = QSettings('test_rmb', 'test_rmb')
        settings.setValue('converters_custom', '')
        all_conv = get_all_converters(settings)
        assert len(all_conv) == len(BUILTIN_CONVERTERS)
        assert all(c['builtin'] for c in all_conv)
