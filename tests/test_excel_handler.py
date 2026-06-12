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
    excel = make_excel(tmp_path / 'data.xlsx', [
        {'ShenFenZheng': '110101199001011234', 'XianRenZhiWu': '副科长'},
    ])
    lrmx_dir = sample_lrmx.parent
    handler = ExcelHandler(excel, lrmx_dir, MatchMode.ID_CARD)
    logs = handler.update(['XianRenZhiWu'])
    assert any('张三' in log for log in logs)
    updated = LrmxFile(sample_lrmx)
    assert updated.get('XianRenZhiWu') == '副科长'


def test_backup_created_before_update(sample_lrmx, tmp_path):
    excel = make_excel(tmp_path / 'data.xlsx', [
        {'ShenFenZheng': '110101199001011234', 'XianRenZhiWu': '副科长'},
    ])
    handler = ExcelHandler(excel, sample_lrmx.parent, MatchMode.ID_CARD)
    handler.update(['XianRenZhiWu'])
    assert sample_lrmx.with_suffix('.lrmx.bak').exists()


def test_unmatched_row_logged(sample_lrmx, tmp_path):
    excel = make_excel(tmp_path / 'data.xlsx', [
        {'ShenFenZheng': '000000000000000000', 'XianRenZhiWu': '局长'},
    ])
    handler = ExcelHandler(excel, sample_lrmx.parent, MatchMode.ID_CARD)
    logs = handler.update(['XianRenZhiWu'])
    assert any('未匹配' in log for log in logs)


def test_update_by_name(sample_lrmx, tmp_path):
    excel = make_excel(tmp_path / 'data.xlsx', [
        {'XingMing': '张三', 'JianKangZhuangKuang': '良好'},
    ])
    handler = ExcelHandler(excel, sample_lrmx.parent, MatchMode.NAME)
    handler.update(['JianKangZhuangKuang'])
    updated = LrmxFile(sample_lrmx)
    assert updated.get('JianKangZhuangKuang') == '良好'


def test_progress_callback_called(sample_lrmx, tmp_path):
    excel = make_excel(tmp_path / 'data.xlsx', [
        {'ShenFenZheng': '110101199001011234', 'XianRenZhiWu': '科长'},
    ])
    handler = ExcelHandler(excel, sample_lrmx.parent, MatchMode.ID_CARD)
    calls = []
    handler.update(['XianRenZhiWu'], progress_cb=calls.append)
    assert len(calls) >= 1
