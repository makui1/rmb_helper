import re
import openpyxl
from pathlib import Path

_TEMPLATE = Path(__file__).parent.parent / 'resources' / 'family_template.xlsx'

SPECIAL_CHENGWEI = {
    '父亲', '母亲',
    '祖父', '爷爷',
    '祖母', '奶奶',
    '外祖父', '外祖母',
    '孙子', '孙女',
}

_PLACEHOLDER_RE = re.compile(r'\{\{(\w+(?:\.\w+)?)\}\}')
_BIRTH_YM_RE    = re.compile(r'\d{4}\.\d{1,2}')


def fmt_birth(raw: str) -> str:
    """'196811' → '1968.11'  (strip leading zero in month)"""
    raw = (raw or '').strip()
    if re.fullmatch(r'\d{6}', raw):
        return f'{raw[:4]}.{int(raw[4:])}'
    return raw


class ExcelExporter:
    def __init__(self, template_path: Path = _TEMPLATE):
        self._template = template_path
        # {(sheet_title, coordinate): field_name}
        self._field_map: dict[tuple[str, str], str] = {}
        self._name_coord:  tuple[str, str] | None = None
        self._birth_coord: tuple[str, str] | None = None
        self._scan_template()

    def _scan_template(self):
        wb = openpyxl.load_workbook(self._template)
        for ws in wb.worksheets:
            for row in ws.iter_rows():
                for cell in row:
                    if not isinstance(cell.value, str):
                        continue
                    m = _PLACEHOLDER_RE.search(cell.value)
                    if not m:
                        continue
                    field = m.group(1)
                    key   = (ws.title, cell.coordinate)
                    self._field_map[key] = field
                    if '.' not in field:
                        if field == 'XingMing' and self._name_coord is None:
                            self._name_coord = key
                        elif field == 'ChuShengNianYue' and self._birth_coord is None:
                            self._birth_coord = key
        wb.close()

    def scan_output_dir(self, output_dir: Path) -> dict[tuple[str, str], Path]:
        """Return {(name, birth_ym): path} for existing xlsx in output_dir."""
        result: dict[tuple[str, str], Path] = {}
        if not output_dir.is_dir():
            return result
        for p in output_dir.glob('*.xlsx'):
            try:
                wb   = openpyxl.load_workbook(p, read_only=True, data_only=True)
                name = birth = ''
                if self._name_coord:
                    sh, coord = self._name_coord
                    ws = wb[sh] if sh in wb.sheetnames else wb.active
                    v  = ws[coord].value
                    name = str(v).strip() if v else ''
                if self._birth_coord:
                    sh, coord = self._birth_coord
                    ws = wb[sh] if sh in wb.sheetnames else wb.active
                    v  = ws[coord].value
                    raw = str(v) if v else ''
                    hit = _BIRTH_YM_RE.search(raw)
                    birth = hit.group(0) if hit else ''
                wb.close()
                if name and birth:
                    result[(name, birth)] = p
            except Exception:
                pass
        return result

    def export(
        self,
        lrmx_dict:    dict[str, str],
        members:      list[dict[str, str]],
        output_path:  Path,
        existing_map: dict[tuple[str, str], Path],
        on_exists:    str = 'skip',
    ) -> tuple[str, str]:
        """Export to xlsx.

        Returns (status, stem):
          'created' — new file written
          'updated' — existing file basic-info refreshed
          'skip'    — existing file unchanged
        """
        name      = lrmx_dict.get('XingMing', '')
        birth_raw = lrmx_dict.get('ChuShengNianYue', '')
        birth_ym  = fmt_birth(birth_raw)
        stem      = output_path.stem

        existing = existing_map.get((name, birth_ym))

        if existing is not None:
            if on_exists == 'skip':
                return 'skip', stem
            wb          = openpyxl.load_workbook(existing)
            save_path   = existing
            update_only = True
        else:
            wb          = openpyxl.load_workbook(self._template)
            save_path   = output_path
            update_only = False

        n_group = [m for m in members if m.get('ChengWei') in SPECIAL_CHENGWEI]
        m_group = [m for m in members if m.get('ChengWei') not in SPECIAL_CHENGWEI]

        for (sh, coord), field in self._field_map.items():
            is_member = '.' in field
            if update_only and is_member:
                continue  # preserve manually-edited family data

            ws = wb[sh] if sh in wb.sheetnames else wb.active

            if is_member:
                prefix, attr = field.split('.', 1)
                if prefix.startswith('m'):
                    idx    = int(prefix[1:])
                    member = m_group[idx] if idx < len(m_group) else None
                elif prefix.startswith('n'):
                    idx    = int(prefix[1:])
                    member = n_group[idx] if idx < len(n_group) else None
                else:
                    member = None

                if member and attr == 'ChuShengNianYue':
                    value = fmt_birth(member.get('ChuShengRiQi', ''))
                elif member:
                    value = member.get(attr, '')
                else:
                    value = ''
            else:
                if field == 'ChuShengNianYue':
                    value = birth_ym
                else:
                    value = lrmx_dict.get(field, '')

            ws[coord] = value

        save_path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(save_path)
        return ('updated' if update_only else 'created'), stem
