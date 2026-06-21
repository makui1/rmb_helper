import shutil
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from enum import Enum, auto
from pathlib import Path
from typing import Callable


class PdfEngine(Enum):
    SPIRE       = auto()   # Spire.Doc Free (pip install spire-doc-free)
    LIBREOFFICE = auto()
    WPS_COM     = auto()   # WPS Office via Windows COM
    WORD_COM    = auto()   # Microsoft Word via Windows COM
    WPS_CLI     = auto()   # WPS via CLI (Linux / macOS)
    NONE        = auto()


def _winreg_has(prog_id: str) -> bool:
    if sys.platform != 'win32':
        return False
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, prog_id)
        winreg.CloseKey(key)
        return True
    except (FileNotFoundError, OSError):
        return False


def _spire_available() -> bool:
    try:
        import spire.doc  # noqa: F401
        return True
    except ImportError:
        return False


_WPS_PROG_IDS = ('WPS.Application', 'KSO.Application')


def detect_engine() -> PdfEngine:
    if _spire_available():
        return PdfEngine.SPIRE
    if shutil.which('libreoffice') or shutil.which('soffice'):
        return PdfEngine.LIBREOFFICE
    if sys.platform == 'win32':
        if any(_winreg_has(p) for p in _WPS_PROG_IDS):
            return PdfEngine.WPS_COM
        if _winreg_has('Word.Application'):
            return PdfEngine.WORD_COM
    if shutil.which('wps'):
        return PdfEngine.WPS_CLI
    return PdfEngine.NONE


def _spire_pdf_worker(args: tuple[str, str]) -> str:
    """在子进程中运行，独立加载 Spire，将 docx 转为 pdf。
    args = (docx_path_str, output_dir_str)
    返回生成的 pdf_path_str。
    必须是模块级函数，否则无法被 multiprocessing pickle。
    IO_SharingViolation 是 Spire 并发写文件冲突，最多重试 3 次。
    """
    import time
    docx_path_str, output_dir_str = args
    from spire.doc import Document, FileFormat
    from pathlib import Path as _Path
    pdf_path = _Path(output_dir_str) / (_Path(docx_path_str).stem + '.pdf')
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            doc = Document()
            doc.LoadFromFile(docx_path_str)
            doc.SaveToFile(str(pdf_path), FileFormat.PDF)
            doc.Close()
            return str(pdf_path)
        except Exception as e:
            last_err = e
            if attempt < 2:
                time.sleep(0.5 * (attempt + 1))
    raise last_err  # type: ignore[misc]


class PdfExporter:
    def __init__(self) -> None:
        self.engine = detect_engine()

    def available(self) -> bool:
        return self.engine != PdfEngine.NONE

    def export(self, docx_path: Path, output_dir: Path) -> Path:
        docx_path  = Path(docx_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        if self.engine == PdfEngine.SPIRE:
            return self._via_spire(docx_path, output_dir)
        if self.engine == PdfEngine.LIBREOFFICE:
            return self._via_libreoffice(docx_path, output_dir)
        if self.engine == PdfEngine.WPS_COM:
            return self._via_com(docx_path, output_dir, _WPS_PROG_IDS)
        if self.engine == PdfEngine.WORD_COM:
            return self._via_com(docx_path, output_dir, ('Word.Application',))
        if self.engine == PdfEngine.WPS_CLI:
            return self._via_wps_cli(docx_path, output_dir)
        raise RuntimeError('未检测到可用的 PDF 渲染引擎，请运行 pip install spire-doc-free 或安装 WPS / LibreOffice。')

    def export_batch(
        self,
        docx_paths: list[Path],
        output_dir: Path,
        on_progress=None,
    ) -> list[tuple[Path, Path | None, str]]:
        """批量转换。返回 [(输入路径, 输出PDF路径|None, 错误信息)] 列表。
        on_progress(inp, pdf, err) 在每个文件完成时实时回调（可选）。
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        results = []
        for p in docx_paths:
            try:
                pdf = self.export(p, output_dir)
                results.append((p, pdf, ''))
                if on_progress:
                    on_progress(p, pdf, '')
            except Exception as e:
                results.append((p, None, str(e)))
                if on_progress:
                    on_progress(p, None, str(e))
        return results

    # ── Spire.Doc Free (Python) ───────────────────────────────────────────────

    def _via_spire(self, docx_path: Path, output_dir: Path) -> Path:
        from spire.doc import Document, FileFormat
        pdf_path = output_dir / (docx_path.stem + '.pdf')
        doc = Document()
        doc.LoadFromFile(str(docx_path))
        doc.SaveToFile(str(pdf_path), FileFormat.PDF)
        doc.Close()
        return pdf_path

    # ── LibreOffice ───────────────────────────────────────────────────────────

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

    def export_parallel(
        self,
        jobs: 'list[tuple[Path, Path]]',
        on_progress: 'Callable[[str, str | None, str], None] | None' = None,
    ) -> None:
        """并行转换 docx → pdf。
        jobs: [(docx_path, output_dir), ...]
        on_progress(stem, pdf_path_str_or_None, error_str) 每个文件完成时回调。
        进程数 = min(cpu_count, len(jobs))，as_completed 随完成随回报。
        """
        if not jobs:
            return
        import os
        # Spire.Doc 在高并发时会触发 IO_SharingViolation，上限设为 4
        n = min(4, os.cpu_count() or 1, len(jobs))
        str_jobs = [(str(d), str(o)) for d, o in jobs]
        with ProcessPoolExecutor(max_workers=n) as executor:
            future_to_stem = {
                executor.submit(_spire_pdf_worker, job): Path(job[0]).stem
                for job in str_jobs
            }
            for future in as_completed(future_to_stem):
                stem = future_to_stem[future]
                try:
                    pdf_path = future.result()
                    if on_progress:
                        on_progress(stem, pdf_path, '')
                except Exception as e:
                    if on_progress:
                        on_progress(stem, None, str(e))

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
