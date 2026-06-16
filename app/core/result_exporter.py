"""Export verification results to Excel or self-contained HTML."""
from __future__ import annotations

import html as _html
from datetime import datetime
from pathlib import Path

import openpyxl
from openpyxl.styles import Font, PatternFill

from app.core.verify_handler import PersonResult, char_diff_html

# ── shared constants ──────────────────────────────────────────────────────────

_STATUS_LABELS: dict[str, str] = {
    'ok':        '一致',
    'diff':      '有差异',
    'not_found': '名册无此人',
    'error':     '错误',
}

_STATUS_FILL: dict[str, PatternFill] = {
    'ok':        PatternFill('solid', fgColor='E8F5EC'),
    'diff':      PatternFill('solid', fgColor='FDEAEA'),
    'not_found': PatternFill('solid', fgColor='FFF3E0'),
    'error':     PatternFill('solid', fgColor='F5F5F5'),
}

_DEL_FILL = PatternFill('solid', fgColor='FDEAEA')
_INS_FILL = PatternFill('solid', fgColor='E8F5EC')

_BOLD = Font(bold=True)


def _id_val(result: PersonResult) -> str:
    """Return the Excel value for ShenFenZheng, or '' if not mapped."""
    for fr in result.fields:
        if fr.field == 'ShenFenZheng':
            return fr.excel_val
    return ''


# ── Excel export ──────────────────────────────────────────────────────────────

def export_excel(results: list[PersonResult], path: Path) -> None:
    """Write a dual-sheet workbook. Raises on failure."""
    wb = openpyxl.Workbook()

    # ── Sheet1: 人员汇总 ──────────────────────────────────────────────────────
    ws1 = wb.active
    ws1.title = '人员汇总'
    headers1 = ['姓名', '身份证', '核验状态', '差异字段数', '差异字段', '错误信息']
    ws1.append(headers1)
    for cell in ws1[1]:
        cell.font = _BOLD

    for r in results:
        status = r.status if r.status in _STATUS_LABELS else 'error'
        if r.fields:
            diff_n: int | str = sum(1 for f in r.fields if not f.match)
            diff_names = ', '.join(f.field for f in r.fields if not f.match)
        else:
            diff_n = ''
            diff_names = ''
        ws1.append([
            r.name,
            _id_val(r),
            _STATUS_LABELS[status],
            diff_n,
            diff_names,
            r.error_msg,
        ])
        ws1.cell(ws1.max_row, 3).fill = _STATUS_FILL[status]

    # ── Sheet2: 字段明细 ──────────────────────────────────────────────────────
    ws2 = wb.create_sheet('字段明细')
    headers2 = ['姓名', '身份证', '字段', '名册值', '任免表值', '是否一致']
    ws2.append(headers2)
    for cell in ws2[1]:
        cell.font = _BOLD

    for r in results:
        id_ = _id_val(r)
        status = r.status if r.status in _STATUS_LABELS else 'error'
        if status in ('ok', 'diff') and r.fields:
            for fr in r.fields:
                ws2.append([
                    r.name, id_, fr.field,
                    fr.excel_val, fr.lrmx_val,
                    '✓' if fr.match else '✗',
                ])
                if not fr.match:
                    ws2.cell(ws2.max_row, 4).fill = _DEL_FILL
                    ws2.cell(ws2.max_row, 5).fill = _INS_FILL
        else:
            note = r.error_msg if status == 'error' else _STATUS_LABELS[status]
            ws2.append([r.name, id_, '—', note, '', ''])

    wb.save(path)
