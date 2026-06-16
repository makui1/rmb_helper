from pathlib import Path
import openpyxl
import pytest
from app.core.lrmx import LrmxFile
from app.core.excel_handler import ExcelHandler, MatchMode


def make_excel(path: Path, rows: list[dict]) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    headers = list(rows[0].keys())
    ws.append(headers)
    for row in rows:
        ws.append([row[h] for h in headers])
    wb.save(path)
    return path


def test_update_by_id_card(sample_lrmx, tmp_path):
    """Excel 列名不同于 lrmx 字段名时，通过 field_mapping 正确写入"""
    excel = make_excel(tmp_path / 'data.xlsx', [
        {'证件号': '110101199001011234', '现任职务': '副科长'},
    ])
    handler = ExcelHandler(excel, [sample_lrmx], MatchMode.ID_CARD)
    field_mapping = {'证件号': 'ShenFenZheng', '现任职务': 'XianRenZhiWu'}
    logs = handler.update(
        field_mapping=field_mapping,
        fields_to_write=['XianRenZhiWu'],
        match_excel_col_for_id='证件号',
    )
    assert any('张三' in log for log in logs)
    assert any('✓' in log for log in logs)
    updated = LrmxFile(sample_lrmx)
    assert updated.get('XianRenZhiWu') == '副科长'


def test_backup_created_before_update(sample_lrmx, tmp_path):
    excel = make_excel(tmp_path / 'data.xlsx', [
        {'证件号': '110101199001011234', '现任职务': '副科长'},
    ])
    handler = ExcelHandler(excel, [sample_lrmx], MatchMode.ID_CARD)
    field_mapping = {'证件号': 'ShenFenZheng', '现任职务': 'XianRenZhiWu'}
    handler.update(
        field_mapping=field_mapping,
        fields_to_write=['XianRenZhiWu'],
        match_excel_col_for_id='证件号',
    )
    assert sample_lrmx.with_suffix('.lrmx.bak').exists()


def test_unmatched_lrmx_logged(sample_lrmx, tmp_path):
    """名册中没有对应记录时，日志显示 △ 未匹配"""
    excel = make_excel(tmp_path / 'data.xlsx', [
        {'证件号': '000000000000000000', '现任职务': '局长'},
    ])
    handler = ExcelHandler(excel, [sample_lrmx], MatchMode.ID_CARD)
    field_mapping = {'证件号': 'ShenFenZheng', '现任职务': 'XianRenZhiWu'}
    logs = handler.update(
        field_mapping=field_mapping,
        fields_to_write=['XianRenZhiWu'],
        match_excel_col_for_id='证件号',
    )
    assert any('△' in log for log in logs)
    assert any('未在名册中找到' in log for log in logs)


def test_update_by_name(sample_lrmx, tmp_path):
    excel = make_excel(tmp_path / 'data.xlsx', [
        {'姓名': '张三', '健康状况': '良好'},
    ])
    handler = ExcelHandler(excel, [sample_lrmx], MatchMode.NAME)
    field_mapping = {'姓名': 'XingMing', '健康状况': 'JianKangZhuangKuang'}
    handler.update(
        field_mapping=field_mapping,
        fields_to_write=['JianKangZhuangKuang'],
        match_excel_col_for_name='姓名',
    )
    updated = LrmxFile(sample_lrmx)
    assert updated.get('JianKangZhuangKuang') == '良好'


def test_fields_to_write_subset(sample_lrmx, tmp_path):
    """fields_to_write 只写入子集，其他已映射字段不写入"""
    excel = make_excel(tmp_path / 'data.xlsx', [
        {'证件号': '110101199001011234', '现任职务': '副科长', '姓名': '张三'},
    ])
    handler = ExcelHandler(excel, [sample_lrmx], MatchMode.ID_CARD)
    field_mapping = {
        '证件号': 'ShenFenZheng',
        '现任职务': 'XianRenZhiWu',
        '姓名': 'XingMing',
    }
    handler.update(
        field_mapping=field_mapping,
        fields_to_write=['XianRenZhiWu'],  # 只写入现任职务
        match_excel_col_for_id='证件号',
    )
    updated = LrmxFile(sample_lrmx)
    assert updated.get('XianRenZhiWu') == '副科长'
    assert updated.get('XingMing') == '张三'  # 原值不变（sample 本来就是张三）


def test_progress_callback_called(sample_lrmx, tmp_path):
    excel = make_excel(tmp_path / 'data.xlsx', [
        {'证件号': '110101199001011234', '现任职务': '科长'},
    ])
    handler = ExcelHandler(excel, [sample_lrmx], MatchMode.ID_CARD)
    field_mapping = {'证件号': 'ShenFenZheng', '现任职务': 'XianRenZhiWu'}
    calls = []
    handler.update(
        field_mapping=field_mapping,
        fields_to_write=['XianRenZhiWu'],
        match_excel_col_for_id='证件号',
        progress_cb=calls.append,
    )
    assert len(calls) >= 1


def test_header_row_param(sample_lrmx, tmp_path):
    """header_row=2 时跳过第一行"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(['这是说明行，非表头'])
    ws.append(['证件号', '现任职务'])
    ws.append(['110101199001011234', '处长'])
    p = tmp_path / 'data2.xlsx'
    wb.save(p)

    handler = ExcelHandler(p, [sample_lrmx], MatchMode.ID_CARD)
    field_mapping = {'证件号': 'ShenFenZheng', '现任职务': 'XianRenZhiWu'}
    handler.update(
        field_mapping=field_mapping,
        fields_to_write=['XianRenZhiWu'],
        header_row=2,
        match_excel_col_for_id='证件号',
    )
    updated = LrmxFile(sample_lrmx)
    assert updated.get('XianRenZhiWu') == '处长'


def test_backup_restored_on_save_failure(sample_lrmx, tmp_path, monkeypatch):
    """写入失败时备份文件应被还原为原文件"""
    excel = make_excel(tmp_path / 'data.xlsx', [
        {'证件号': '110101199001011234', '现任职务': '副科长'},
    ])
    handler = ExcelHandler(excel, [sample_lrmx], MatchMode.ID_CARD)
    field_mapping = {'证件号': 'ShenFenZheng', '现任职务': 'XianRenZhiWu'}

    def failing_save(path):
        raise OSError('磁盘已满')

    monkeypatch.setattr('app.core.lrmx.LrmxFile.save', failing_save)

    logs = handler.update(
        field_mapping=field_mapping,
        fields_to_write=['XianRenZhiWu'],
        match_excel_col_for_id='证件号',
    )
    assert any('✗' in log for log in logs)
    assert sample_lrmx.exists(), '原文件应被还原'
    assert not sample_lrmx.with_suffix('.lrmx.bak').exists(), '备份文件应消失'


def test_validation_id_col_required(sample_lrmx, tmp_path):
    """ID_CARD 模式未提供 match_excel_col_for_id 应抛出 ValueError"""
    excel = make_excel(tmp_path / 'data.xlsx', [
        {'证件号': '110101199001011234', '现任职务': '副科长'},
    ])
    handler = ExcelHandler(excel, [sample_lrmx], MatchMode.ID_CARD)
    field_mapping = {'证件号': 'ShenFenZheng', '现任职务': 'XianRenZhiWu'}
    with pytest.raises(ValueError, match='match_excel_col_for_id'):
        handler.update(
            field_mapping=field_mapping,
            fields_to_write=['XianRenZhiWu'],
            # match_excel_col_for_id intentionally omitted
        )


def test_validation_name_col_required(sample_lrmx, tmp_path):
    """NAME 模式未提供 match_excel_col_for_name 应抛出 ValueError"""
    excel = make_excel(tmp_path / 'data.xlsx', [
        {'姓名': '张三', '健康状况': '良好'},
    ])
    handler = ExcelHandler(excel, [sample_lrmx], MatchMode.NAME)
    field_mapping = {'姓名': 'XingMing', '健康状况': 'JianKangZhuangKuang'}
    with pytest.raises(ValueError, match='match_excel_col_for_name'):
        handler.update(
            field_mapping=field_mapping,
            fields_to_write=['JianKangZhuangKuang'],
            # match_excel_col_for_name intentionally omitted
        )


def test_validation_name_and_id_cols_required(sample_lrmx, tmp_path):
    """NAME_AND_ID 模式未提供任一列名应抛出 ValueError"""
    excel = make_excel(tmp_path / 'data.xlsx', [
        {'证件号': '110101199001011234', '姓名': '张三', '健康状况': '良好'},
    ])
    handler = ExcelHandler(excel, [sample_lrmx], MatchMode.NAME_AND_ID)
    field_mapping = {'证件号': 'ShenFenZheng', '姓名': 'XingMing', '健康状况': 'JianKangZhuangKuang'}
    with pytest.raises(ValueError):
        handler.update(
            field_mapping=field_mapping,
            fields_to_write=['JianKangZhuangKuang'],
            match_excel_col_for_id='证件号',
            # match_excel_col_for_name intentionally omitted
        )
