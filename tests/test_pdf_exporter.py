from unittest.mock import patch, MagicMock
from app.core.pdf_exporter import PdfExporter, PdfEngine, detect_engine


def test_detect_engine_finds_libreoffice():
    with patch('shutil.which', side_effect=lambda x: '/usr/bin/soffice' if x == 'soffice' else None):
        assert detect_engine() == PdfEngine.LIBREOFFICE


def test_detect_engine_finds_wps():
    with patch('shutil.which', side_effect=lambda x: '/usr/bin/wps' if x == 'wps' else None):
        assert detect_engine() == PdfEngine.WPS


def test_detect_engine_none_when_nothing_installed():
    import sys
    with patch('shutil.which', return_value=None):
        # 移除 win32com（如果存在）
        modules_backup = {k: sys.modules.pop(k) for k in list(sys.modules.keys()) if 'win32com' in k}
        try:
            engine = detect_engine()
            assert engine in (PdfEngine.NONE, PdfEngine.WORD_COM)
        finally:
            sys.modules.update(modules_backup)


def test_available_true_when_engine_found():
    with patch('app.core.pdf_exporter.detect_engine', return_value=PdfEngine.LIBREOFFICE):
        exporter = PdfExporter()
        assert exporter.available() is True


def test_available_false_when_no_engine():
    with patch('app.core.pdf_exporter.detect_engine', return_value=PdfEngine.NONE):
        exporter = PdfExporter()
        assert exporter.available() is False


def test_export_raises_when_no_engine(tmp_path):
    import pytest
    with patch('app.core.pdf_exporter.detect_engine', return_value=PdfEngine.NONE):
        exporter = PdfExporter()
        with pytest.raises(RuntimeError, match='No PDF rendering engine'):
            exporter.export(tmp_path / 'in.docx', tmp_path)
