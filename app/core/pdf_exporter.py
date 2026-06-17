import shutil
import subprocess
import sys
from collections import defaultdict
from enum import Enum, auto
from pathlib import Path


class PdfEngine(Enum):
    ASPOSE      = auto()   # Aspose.Words Java exe（最优先）
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


def _find_aspose_exe() -> Path | None:
    candidates = [
        # 开发环境：项目根目录 / docx2pdf/target/
        Path(__file__).parent.parent.parent / 'docx2pdf' / 'target' / 'docx2pdf.exe',
        # 打包后：与主程序同级目录
        Path(sys.executable).parent / 'docx2pdf.exe',
    ]
    return next((p for p in candidates if p.exists()), None)


_WPS_PROG_IDS = ('WPS.Application', 'KSO.Application')


def detect_engine() -> PdfEngine:
    if _find_aspose_exe():
        return PdfEngine.ASPOSE
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


class PdfExporter:
    def __init__(self) -> None:
        self.engine = detect_engine()
        self._aspose_exe: Path | None = (
            _find_aspose_exe() if self.engine == PdfEngine.ASPOSE else None
        )

    def available(self) -> bool:
        return self.engine != PdfEngine.NONE

    def export(self, docx_path: Path, output_dir: Path) -> Path:
        """单文件转换。Aspose 引擎建议用 export_batch() 以避免重复启动 JVM。"""
        docx_path  = Path(docx_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        if self.engine == PdfEngine.ASPOSE:
            results = self._via_aspose_batch([docx_path], output_dir)
            _, pdf, err = results[0]
            if pdf is None:
                raise RuntimeError(err)
            return pdf
        if self.engine == PdfEngine.LIBREOFFICE:
            return self._via_libreoffice(docx_path, output_dir)
        if self.engine == PdfEngine.WPS_COM:
            return self._via_com(docx_path, output_dir, _WPS_PROG_IDS)
        if self.engine == PdfEngine.WORD_COM:
            return self._via_com(docx_path, output_dir, ('Word.Application',))
        if self.engine == PdfEngine.WPS_CLI:
            return self._via_wps_cli(docx_path, output_dir)
        raise RuntimeError('未检测到可用的 PDF 渲染引擎，请构建 docx2pdf.exe 或安装 WPS / LibreOffice。')

    def export_batch(
        self, docx_paths: list[Path], output_dir: Path
    ) -> list[tuple[Path, Path | None, str]]:
        """批量转换。返回 [(输入路径, 输出PDF路径|None, 错误信息)] 列表。
        Aspose 引擎只启动一次 JVM；其他引擎逐个调用。
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        if self.engine == PdfEngine.ASPOSE:
            return self._via_aspose_batch(docx_paths, output_dir)

        results = []
        for p in docx_paths:
            try:
                pdf = self.export(p, output_dir)
                results.append((p, pdf, ''))
            except Exception as e:
                results.append((p, None, str(e)))
        return results

    # ── Aspose (Java exe) ─────────────────────────────────────────────────────

    def _via_aspose_batch(
        self, docx_paths: list[Path], output_dir: Path
    ) -> list[tuple[Path, Path | None, str]]:
        proc = subprocess.run(
            [str(self._aspose_exe), str(output_dir)] + [str(p) for p in docx_paths],
            capture_output=True, text=True, encoding='utf-8',
        )
        # 解析 OK / ERR 行（按 stem 匹配回原始输入）
        ok_stems:  set[str]        = set()
        err_stems: dict[str, str]  = {}
        for line in proc.stdout.splitlines():
            if line.startswith('OK '):
                ok_stems.add(Path(line[3:].strip()).stem.lower())
            elif line.startswith('ERR '):
                rest = line[4:]
                sep = rest.find(': ')
                if sep != -1:
                    err_stems[Path(rest[:sep]).stem.lower()] = rest[sep + 2:]

        results = []
        for p in docx_paths:
            key = p.stem.lower()
            if key in ok_stems:
                results.append((p, output_dir / (p.stem + '.pdf'), ''))
            else:
                results.append((p, None, err_stems.get(key, '转换失败（未知原因）')))
        return results

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
