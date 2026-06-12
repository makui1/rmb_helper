import shutil
import subprocess
from enum import Enum, auto
from pathlib import Path


class PdfEngine(Enum):
    LIBREOFFICE = auto()
    WPS = auto()
    WORD_COM = auto()
    NONE = auto()


def detect_engine() -> PdfEngine:
    if shutil.which('libreoffice') or shutil.which('soffice'):
        return PdfEngine.LIBREOFFICE
    if shutil.which('wps'):
        return PdfEngine.WPS
    try:
        import win32com.client  # noqa: F401
        return PdfEngine.WORD_COM
    except (ImportError, ModuleNotFoundError):
        pass
    return PdfEngine.NONE


class PdfExporter:
    def __init__(self) -> None:
        self.engine = detect_engine()

    def available(self) -> bool:
        return self.engine != PdfEngine.NONE

    def export(self, docx_path: Path, output_dir: Path) -> Path:
        docx_path = Path(docx_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        if self.engine == PdfEngine.LIBREOFFICE:
            return self._via_libreoffice(docx_path, output_dir)
        if self.engine == PdfEngine.WPS:
            return self._via_wps(docx_path, output_dir)
        if self.engine == PdfEngine.WORD_COM:
            return self._via_word_com(docx_path, output_dir)
        raise RuntimeError('No PDF rendering engine available. Install LibreOffice or WPS.')

    def _via_libreoffice(self, docx_path: Path, output_dir: Path) -> Path:
        cmd = shutil.which('libreoffice') or shutil.which('soffice')
        subprocess.run(
            [cmd, '--headless', '--convert-to', 'pdf', '--outdir', str(output_dir), str(docx_path)],
            check=True, capture_output=True,
        )
        return output_dir / (docx_path.stem + '.pdf')

    def _via_wps(self, docx_path: Path, output_dir: Path) -> Path:
        subprocess.run(
            ['wps', '--headless', '--convert-to', 'pdf', '--outdir', str(output_dir), str(docx_path)],
            check=True, capture_output=True,
        )
        return output_dir / (docx_path.stem + '.pdf')

    def _via_word_com(self, docx_path: Path, output_dir: Path) -> Path:
        import win32com.client
        word = win32com.client.Dispatch('Word.Application')
        word.Visible = False
        try:
            doc = word.Documents.Open(str(docx_path.resolve()))
            pdf_path = output_dir / (docx_path.stem + '.pdf')
            doc.SaveAs(str(pdf_path.resolve()), FileFormat=17)
            doc.Close()
        finally:
            word.Quit()
        return pdf_path
