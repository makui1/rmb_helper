from pathlib import Path
from typing import Callable, Optional
import openpyxl
from .lrmx import LrmxFile


class MatchMode:
    ID_CARD = 'ShenFenZheng'
    NAME = 'XingMing'
    NAME_AND_ID = 'both'


class ExcelHandler:
    def __init__(self, excel_path: Path, lrmx_files: list, match_mode: str) -> None:
        self.excel_path = Path(excel_path)
        self.lrmx_files = [Path(f) for f in lrmx_files]
        self.match_mode = match_mode

    def _make_key(self, lf: LrmxFile) -> str:
        if self.match_mode == MatchMode.ID_CARD:
            return lf.get('ShenFenZheng').strip()
        if self.match_mode == MatchMode.NAME:
            return lf.get('XingMing').strip()
        return lf.get('XingMing').strip() + lf.get('ShenFenZheng').strip()

    def _row_key(self, row: dict) -> str:
        if self.match_mode == MatchMode.ID_CARD:
            return str(row.get('ShenFenZheng') or '').strip()
        if self.match_mode == MatchMode.NAME:
            return str(row.get('XingMing') or '').strip()
        return str(row.get('XingMing') or '').strip() + str(row.get('ShenFenZheng') or '').strip()

    def _load_index(self) -> dict[str, LrmxFile]:
        index: dict[str, LrmxFile] = {}
        for f in self.lrmx_files:
            try:
                lf = LrmxFile(f)
                key = self._make_key(lf)
                if key:
                    index[key] = lf
            except Exception:
                pass
        return index

    def update(
        self,
        fields_to_update: list[str],
        progress_cb: Optional[Callable[[str], None]] = None,
    ) -> list[str]:
        wb = openpyxl.load_workbook(self.excel_path)
        ws = wb.active
        headers = [cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))]
        index = self._load_index()
        logs: list[str] = []

        for row_values in ws.iter_rows(min_row=2, values_only=True):
            row = dict(zip(headers, row_values))
            key = self._row_key(row)
            if not key or key not in index:
                msg = f'未匹配: {key or "(空)"}'
                logs.append(msg)
                if progress_cb:
                    progress_cb(msg)
                continue

            lf = index[key]
            backup = lf.path.with_suffix('.lrmx.bak')
            lf.path.rename(backup)
            for field in fields_to_update:
                val = row.get(field)
                if val is not None:
                    lf.set(field, str(val))
            lf.save(lf.path)
            msg = f'已更新: {lf.get("XingMing")}'
            logs.append(msg)
            if progress_cb:
                progress_cb(msg)

        return logs
