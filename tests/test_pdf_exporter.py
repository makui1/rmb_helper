from unittest.mock import patch, MagicMock
from app.core.pdf_exporter import PdfExporter, PdfEngine, detect_engine, _spire_pdf_worker


def test_detect_engine_finds_libreoffice():
    with patch('shutil.which', side_effect=lambda x: '/usr/bin/soffice' if x == 'soffice' else None):
        assert detect_engine() == PdfEngine.LIBREOFFICE


def test_detect_engine_finds_wps():
    with patch('shutil.which', side_effect=lambda x: '/usr/bin/wps' if x == 'wps' else None):
        assert detect_engine() == PdfEngine.WPS_CLI


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


def test_spire_pdf_worker_is_callable():
    """_spire_pdf_worker 是模块级可调用对象（可 pickle）。"""
    import pickle
    assert callable(_spire_pdf_worker)
    pickle.dumps(_spire_pdf_worker)   # 若不能 pickle 则 ProcessPoolExecutor 会崩


def test_export_parallel_calls_on_progress_per_job(tmp_path):
    """export_parallel 为每个 job 调用一次 on_progress。"""
    from unittest.mock import patch, MagicMock
    from concurrent.futures import Future

    def make_future(result_val):
        f = Future()
        f.set_result(result_val)
        return f

    jobs = [
        (tmp_path / 'a.docx', tmp_path),
        (tmp_path / 'b.docx', tmp_path),
    ]
    future_a = make_future(str(tmp_path / 'a.pdf'))
    future_b = make_future(str(tmp_path / 'b.pdf'))

    calls: list[tuple] = []

    mock_executor = MagicMock()
    mock_executor.submit.side_effect = [future_a, future_b]

    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_executor)
    mock_ctx.__exit__ = MagicMock(return_value=False)

    with patch('app.core.pdf_exporter.ProcessPoolExecutor', return_value=mock_ctx):
        with patch('app.core.pdf_exporter.as_completed', return_value=[future_a, future_b]):
            PdfExporter().export_parallel(jobs, on_progress=lambda s, p, e: calls.append((s, p, e)))

    assert len(calls) == 2
    stems = {c[0] for c in calls}
    assert 'a' in stems and 'b' in stems


def test_export_parallel_handles_worker_exception(tmp_path):
    """worker 抛异常时，on_progress 收到 (stem, None, error_msg)。"""
    from unittest.mock import patch, MagicMock
    from concurrent.futures import Future

    def make_failed_future(exc):
        f = Future()
        f.set_exception(exc)
        return f

    jobs = [(tmp_path / 'bad.docx', tmp_path)]
    bad_future = make_failed_future(RuntimeError('Spire failed'))

    calls: list[tuple] = []

    mock_executor = MagicMock()
    mock_executor.submit.return_value = bad_future

    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_executor)
    mock_ctx.__exit__ = MagicMock(return_value=False)

    with patch('app.core.pdf_exporter.ProcessPoolExecutor', return_value=mock_ctx):
        with patch('app.core.pdf_exporter.as_completed', return_value=[bad_future]):
            PdfExporter().export_parallel(jobs, on_progress=lambda s, p, e: calls.append((s, p, e)))

    assert calls == [('bad', None, 'Spire failed')]
