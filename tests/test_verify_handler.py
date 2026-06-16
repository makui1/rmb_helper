import openpyxl
import pytest
from pathlib import Path
from app.core.verify_handler import (
    read_excel_headers,
    get_lrmx_fields,
    _strip,
    char_diff_html,
    VerifyHandler,
    PersonResult,
    FieldResult,
)
from app.core.excel_handler import MatchMode


def make_excel(path: Path, rows: list[dict], header_row: int = 1) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    for _ in range(header_row - 1):
        ws.append([])
    headers = list(rows[0].keys())
    ws.append(headers)
    for row in rows:
        ws.append([row[h] for h in headers])
    wb.save(path)
    return path


# ── _strip ────────────────────────────────────────────────────────────────────

def test_strip_removes_whitespace():
    assert _strip('张 三') == '张三'

def test_strip_removes_newline():
    assert _strip('张\n三') == '张三'


# ── read_excel_headers ────────────────────────────────────────────────────────

def test_read_excel_headers_default_row1(tmp_path):
    make_excel(tmp_path / 'x.xlsx', [{'姓名': '张三', '性别': '男'}])
    headers = read_excel_headers(tmp_path / 'x.xlsx', header_row=1)
    assert headers == ['姓名', '性别']

def test_read_excel_headers_custom_row(tmp_path):
    make_excel(tmp_path / 'x.xlsx', [{'身份证': 'abc', '民族': '汉族'}], header_row=3)
    headers = read_excel_headers(tmp_path / 'x.xlsx', header_row=3)
    assert headers == ['身份证', '民族']


# ── get_lrmx_fields ───────────────────────────────────────────────────────────

def test_get_lrmx_fields_excludes_version(sample_lrmx):
    from app.core.lrmx import LrmxFile
    lf = LrmxFile(sample_lrmx)
    lf.set('version', '2')
    lf.save()
    fields = get_lrmx_fields(sample_lrmx)
    assert 'version' not in fields

def test_get_lrmx_fields_returns_all_direct_children(sample_lrmx):
    fields = get_lrmx_fields(sample_lrmx)
    assert 'XingMing' in fields
    assert 'ShenFenZheng' in fields

def test_get_lrmx_fields_excludes_nested_containers(sample_lrmx):
    fields = get_lrmx_fields(sample_lrmx)
    assert 'ChengWei' not in fields


# ── char_diff_html ────────────────────────────────────────────────────────────

def test_char_diff_html_equal():
    a_html, b_html = char_diff_html('张三', '张三')
    assert '<span' not in a_html
    assert '张三' in a_html

def test_char_diff_html_replace():
    a_html, b_html = char_diff_html('男', '女')
    assert 'del' in a_html
    assert 'ins' in b_html

def test_char_diff_html_partial():
    a_html, b_html = char_diff_html('硕士研究生', '硕士生')
    assert '硕士' in a_html
    assert '研究' in a_html


# ── VerifyHandler ─────────────────────────────────────────────────────────────

def test_verify_match_by_id(sample_lrmx, tmp_path):
    excel = make_excel(tmp_path / 'd.xlsx', [
        {'身份证': '110101199001011234', '性别': '男'},
    ])
    handler = VerifyHandler(
        excel_path=excel,
        lrmx_files=[sample_lrmx],
        match_mode=MatchMode.ID_CARD,
        header_row=1,
        field_mapping={'身份证': 'ShenFenZheng', '性别': 'XingBie'},
        match_excel_col_for_id='身份证',
        match_excel_col_for_name=None,
    )
    results = handler.verify()
    assert len(results) == 1
    r = results[0]
    assert r.status == 'ok'
    assert all(f.match for f in r.fields)

def test_verify_detects_diff(sample_lrmx, tmp_path):
    excel = make_excel(tmp_path / 'd.xlsx', [
        {'身份证': '110101199001011234', '性别': '女'},
    ])
    handler = VerifyHandler(
        excel_path=excel,
        lrmx_files=[sample_lrmx],
        match_mode=MatchMode.ID_CARD,
        header_row=1,
        field_mapping={'身份证': 'ShenFenZheng', '性别': 'XingBie'},
        match_excel_col_for_id='身份证',
        match_excel_col_for_name=None,
    )
    results = handler.verify()
    r = results[0]
    assert r.status == 'diff'
    diff_fields = [f for f in r.fields if not f.match]
    assert len(diff_fields) == 1
    assert diff_fields[0].field == 'XingBie'

def test_verify_not_found(sample_lrmx, tmp_path):
    excel = make_excel(tmp_path / 'd.xlsx', [
        {'身份证': '000000000000000000', '性别': '男'},
    ])
    handler = VerifyHandler(
        excel_path=excel,
        lrmx_files=[sample_lrmx],
        match_mode=MatchMode.ID_CARD,
        header_row=1,
        field_mapping={'身份证': 'ShenFenZheng', '性别': 'XingBie'},
        match_excel_col_for_id='身份证',
        match_excel_col_for_name=None,
    )
    results = handler.verify()
    assert results[0].status == 'not_found'

def test_verify_strips_invisible(sample_lrmx, tmp_path):
    # Excel value has a zero-width space after 男, lrmx has plain 男 → should match
    excel = make_excel(tmp_path / 'd.xlsx', [
        {'身份证': '110101199001011234', '性别': '男​'},
    ])
    handler = VerifyHandler(
        excel_path=excel,
        lrmx_files=[sample_lrmx],
        match_mode=MatchMode.ID_CARD,
        header_row=1,
        field_mapping={'身份证': 'ShenFenZheng', '性别': 'XingBie'},
        match_excel_col_for_id='身份证',
        match_excel_col_for_name=None,
    )
    results = handler.verify()
    assert results[0].status == 'ok'

def test_verify_progress_callback(sample_lrmx, tmp_path):
    excel = make_excel(tmp_path / 'd.xlsx', [
        {'身份证': '110101199001011234', '性别': '男'},
    ])
    handler = VerifyHandler(
        excel_path=excel,
        lrmx_files=[sample_lrmx],
        match_mode=MatchMode.ID_CARD,
        header_row=1,
        field_mapping={'身份证': 'ShenFenZheng', '性别': 'XingBie'},
        match_excel_col_for_id='身份证',
        match_excel_col_for_name=None,
    )
    calls = []
    handler.verify(progress_cb=calls.append)
    assert len(calls) == 1
    assert isinstance(calls[0], PersonResult)
