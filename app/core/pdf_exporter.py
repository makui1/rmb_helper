import shutil
import subprocess
import sys
from enum import Enum, auto
from pathlib import Path


class PdfEngine(Enum):
    LIBREOFFICE = auto()
    WPS_COM     = auto()   # WPS Office via Windows COM
    WORD_COM    = auto()   # Microsoft Word via Windows COM
    WPS_CLI     = auto()   # WPS via CLI (Linux / macOS)
    NONE        = auto()


def _winreg_has(prog_id: str) -> bool:
    """Return True if prog_id is registered in HKEY_CLASSES_ROOT (Windows only)."""
    if sys.platform != 'win32':
        return False
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, prog_id)
        winreg.CloseKey(key)
        return True
    except (FileNotFoundError, OSError):
        return False


# WPS registers under one of these ProgIDs depending on version
_WPS_PROG_IDS = ('WPS.Application', 'KSO.Application')


def detect_engine() -> PdfEngine:
    # LibreOffice — cross-platform CLI
    if shutil.which('libreoffice') or shutil.which('soffice'):
        return PdfEngine.LIBREOFFICE

    if sys.platform == 'win32':
        # WPS Office COM (installed but not necessarily in PATH)
        if any(_winreg_has(p) for p in _WPS_PROG_IDS):
            return PdfEngine.WPS_COM
        # Microsoft Word COM
        if _winreg_has('Word.Application'):
            return PdfEngine.WORD_COM

    # WPS CLI (Linux / macOS)
    if shutil.which('wps'):
        return PdfEngine.WPS_CLI

    return PdfEngine.NONE


class PdfExporter:
    def __init__(self) -> None:
        self.engine = detect_engine()

    def available(self) -> bool:
        return self.engine != PdfEngine.NONE

    def export(self, docx_path: Path, output_dir: Path) -> Path:
        docx_path  = Path(docx_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        if self.engine == PdfEngine.LIBREOFFICE:
            return self._via_libreoffice(docx_path, output_dir)
        if self.engine == PdfEngine.WPS_COM:
            return self._via_com(docx_path, output_dir, _WPS_PROG_IDS)
        if self.engine == PdfEngine.WORD_COM:
            return self._via_com(docx_path, output_dir, ('Word.Application',))
        if self.engine == PdfEngine.WPS_CLI:
            return self._via_wps_cli(docx_path, output_dir)
        raise RuntimeError('未检测到可用的 PDF 渲染引擎，请安装 WPS 或 LibreOffice。')

    # ── engine implementations ────────────────────────────────────────────────

    def _via_libreoffice(self, docx_path: Path, output_dir: Path) -> Path:
        cmd = shutil.which('libreoffice') or shutil.which('soffice')
        subprocess.run(
            [cmd, '--headless', '--convert-to', 'pdf',
             '--outdir', str(output_dir), str(docx_path)],
            check=True, capture_output=True,
        )
        return output_dir / (docx_path.stem + '.pdf')

    def _via_wps_cli(self, docx_path: Path, output_dir: Path) -> Path:
        subprocess.run(
            ['wps', '--headless', '--convert-to', 'pdf',
             '--outdir', str(output_dir), str(docx_path)],
            check=True, capture_output=True,
        )
        return output_dir / (docx_path.stem + '.pdf')

    def _via_com(self, docx_path: Path, output_dir: Path,
                 prog_ids: tuple[str, ...]) -> Path:
        import win32com.client
        app = None
        for prog_id in prog_ids:
            if _winreg_has(prog_id):
                try:
                    app = win32com.client.Dispatch(prog_id)
                    break
                except Exception:
                    continue
        if app is None:
            raise RuntimeError(f'无法启动 COM 应用：{prog_ids}')

        app.Visible = False
        pdf_path = output_dir / (docx_path.stem + '.pdf')
        try:
            doc = app.Documents.Open(str(docx_path.resolve()))
            try:
                doc.SaveAs(str(pdf_path.resolve()), FileFormat=17)  # 17 = wdFormatPDF
            finally:
                doc.Close(False)
        finally:
            try:
                app.Quit()
            except Exception:
                pass
        return pdf_path
