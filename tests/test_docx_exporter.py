from datetime import date
from pathlib import Path
import pytest
from docx import Document
from app.core.lrmx import LrmxFile
from app.core.docx_exporter import (
    DocxExporter,
    _format_time6, _format_time8, _format_with_age,
    _format_jianli, _calc_age,
)


# ── Unit tests for helper functions ──────────────────────────────────────────

def test_format_time6_converts_yyyymm():
    assert _format_time6('199001') == '1990.01'
    assert _format_time6('202312') == '2023.12'


def test_format_time6_passthrough_non_date():
    assert _format_time6('   ') == ''
    assert _format_time6('') == ''


def test_format_time8_converts_yyyymmdd():
    assert _format_time8('20260506') == '2026.05.06'


def test_calc_age_returns_integer():
    # A person born in 199001 should have a positive age
    age = _calc_age('199001')
    assert age > 30


def test_format_with_age_includes_age():
    result = _format_with_age('199001')
    assert '1990.01' in result
    assert '岁' in result
    assert '\n' in result


def test_format_jianli_normalizes_lines():
    text = '199001--199601  某大学学习\n199601--  某单位工作'
    result = _format_jianli(text)
    lines = result.split('\n')
    assert lines[0] == '1990.01--1996.01  某大学学习'
    # Last line: no end date → 7 spaces padding
    assert lines[1] == '1996.01--         某单位工作'
    # Both lines have 18-char prefix
    assert lines[0].index('某大学学习') == 18
    assert lines[1].index('某单位工作') == 18


def test_format_jianli_already_formatted():
    text = '1990.01--1996.01  某大学学习\n1996.01--         某单位工作'
    result = _format_jianli(text)
    lines = result.split('\n')
    assert lines[0] == '1990.01--1996.01  某大学学习'
    assert lines[1] == '1996.01--         某单位工作'


def test_format_jianli_passthrough_non_matching():
    text = '这是普通文字\n1990.01--1996.01  某经历'
    result = _format_jianli(text)
    lines = result.split('\n')
    assert lines[0] == '这是普通文字'
    assert lines[1] == '1990.01--1996.01  某经历'


# ── Integration tests ─────────────────────────────────────────────────────────

def make_template(path: Path) -> Path:
    doc = Document()
    doc.add_paragraph('姓名：{{XingMing}}')
    doc.add_paragraph('出生年月：{{ChuShengNianYue}}')
    doc.add_paragraph('入党时间：{{RuDangShiJian}}')
    doc.add_paragraph('简历：{{JianLi}}')
    doc.add_paragraph('照片：{{ZhaoPian}}')
    doc.save(path)
    return path


def test_export_fills_basic_fields(sample_lrmx, tmp_path):
    tpl_path = make_template(tmp_path / 'template.docx')
    exporter = DocxExporter(tpl_path)
    out = tmp_path / 'out.docx'
    lf = LrmxFile(sample_lrmx)
    exporter.export(lf, out)
    assert out.exists()
    doc = Document(out)
    full_text = '\n'.join(p.text for p in doc.paragraphs)
    assert '张三' in full_text
    assert '{{' not in full_text


def test_export_formats_time_field(sample_lrmx, tmp_path):
    tpl_path = make_template(tmp_path / 'template.docx')
    exporter = DocxExporter(tpl_path)
    out = tmp_path / 'out.docx'
    lf = LrmxFile(sample_lrmx)
    exporter.export(lf, out)
    doc = Document(out)
    full_text = '\n'.join(p.text for p in doc.paragraphs)
    # RuDangShiJian '201506' → '2015.06'
    assert '2015.06' in full_text


def test_export_formats_age_field(sample_lrmx, tmp_path):
    tpl_path = make_template(tmp_path / 'template.docx')
    exporter = DocxExporter(tpl_path)
    out = tmp_path / 'out.docx'
    lf = LrmxFile(sample_lrmx)
    exporter.export(lf, out)
    doc = Document(out)
    full_text = '\n'.join(p.text for p in doc.paragraphs)
    # ChuShengNianYue '199001' → '1990.01\n（XX岁）'
    assert '1990.01' in full_text
    assert '岁' in full_text


def test_export_photo_empty_string_when_no_photo(sample_lrmx, tmp_path):
    tpl_path = make_template(tmp_path / 'template.docx')
    exporter = DocxExporter(tpl_path)
    out = tmp_path / 'out.docx'
    lf = LrmxFile(sample_lrmx)
    # sample_lrmx has empty ZhaoPian - should not raise
    exporter.export(lf, out)
    assert out.exists()


def test_export_raises_if_template_missing(sample_lrmx, tmp_path):
    exporter = DocxExporter(tmp_path / 'nonexistent.docx')
    with pytest.raises(Exception):
        exporter.export(LrmxFile(sample_lrmx), tmp_path / 'out.docx')


def test_build_context_strips_invisible(sample_lrmx, tmp_path):
    tpl_path = make_template(tmp_path / 'template.docx')
    from docxtpl import DocxTemplate
    tpl = DocxTemplate(tpl_path)
    exporter = DocxExporter(tpl_path)
    lf = LrmxFile(sample_lrmx)
    ctx = exporter._build_context(lf, tpl)
    # XingMing '张三' has no invisible chars, should be '张三'
    assert ctx['XingMing'] == '张三'


def test_build_context_has_jiating_list(sample_lrmx, tmp_path):
    tpl_path = make_template(tmp_path / 'template.docx')
    from docxtpl import DocxTemplate
    tpl = DocxTemplate(tpl_path)
    exporter = DocxExporter(tpl_path)
    lf = LrmxFile(sample_lrmx)
    ctx = exporter._build_context(lf, tpl)
    assert isinstance(ctx['JiaTingChengYuan'], list)
    assert len(ctx['JiaTingChengYuan']) == 1
    member = ctx['JiaTingChengYuan'][0]
    assert member['ChengWei'] == '妻子'
    assert member['ChuShengRiQi'] == '1992.05'  # formatted


def test_build_context_jianli_formatted(sample_lrmx, tmp_path):
    tpl_path = make_template(tmp_path / 'template.docx')
    from docxtpl import DocxTemplate
    tpl = DocxTemplate(tpl_path)
    exporter = DocxExporter(tpl_path)
    lf = LrmxFile(sample_lrmx)
    ctx = exporter._build_context(lf, tpl)
    jianli = ctx['JianLi']
    lines = [l for l in jianli.split('\n') if l.strip()]
    # First line: has end date
    assert lines[0] == '2012.07--2016.06  某大学某专业学习'
    # Second line: no end date, 7-space padding
    assert lines[1] == '2016.07--         某单位科员'
