from pathlib import Path
from docx import Document
from app.core.lrmx import LrmxFile
from app.core.docx_exporter import DocxExporter


def make_template(path: Path) -> Path:
    """创建一个含 Jinja2 占位符的最小 docx 模板。"""
    doc = Document()
    doc.add_paragraph('姓名：{{XingMing}}')
    doc.add_paragraph('性别：{{XingBie}}')
    doc.add_paragraph('身份证：{{ShenFenZheng}}')
    doc.save(path)
    return path


def test_export_fills_placeholders(sample_lrmx, tmp_path):
    tpl_path = make_template(tmp_path / 'template.docx')
    exporter = DocxExporter(tpl_path)
    out = tmp_path / 'out.docx'
    lf = LrmxFile(sample_lrmx)
    exporter.export(lf, out)
    assert out.exists()
    doc = Document(out)
    full_text = '\n'.join(p.text for p in doc.paragraphs)
    assert '张三' in full_text
    assert '男' in full_text
    assert '110101199001011234' in full_text
    assert '{{' not in full_text


def test_export_raises_if_template_missing(sample_lrmx, tmp_path):
    import pytest
    exporter = DocxExporter(tmp_path / 'nonexistent.docx')
    with pytest.raises(Exception):
        exporter.export(LrmxFile(sample_lrmx), tmp_path / 'out.docx')
