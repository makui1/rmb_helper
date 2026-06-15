from pathlib import Path
import pytest
from docx import Document
from app.core.lrmx import LrmxFile
from app.core.docx_exporter import (
    DocxExporter,
    _format_time6, _format_time8,
    _format_birth, _format_retire,
    _format_jianli_list, _calc_age,
)


# ── Unit tests for helper functions ──────────────────────────────────────────

def test_format_time6_converts_yyyymm():
    assert _format_time6('199001') == '1990.01'
    assert _format_time6('202312') == '2023.12'


def test_format_time6_passthrough_empty():
    assert _format_time6('   ') == ''
    assert _format_time6('') == ''


def test_format_time8_converts_yyyymmdd():
    assert _format_time8('20260506') == '2026.05.06'


def test_calc_age_returns_positive():
    assert _calc_age('199001') > 30


def test_format_birth_includes_age():
    result = _format_birth('199001')
    assert '1990.01' in result
    assert '岁' in result
    assert '\n' in result


def test_format_retire_future():
    result = _format_retire('209901')
    assert '2099.01' in result
    assert '后退休' in result


def test_format_retire_past():
    result = _format_retire('200001')
    assert '已到龄' in result


def test_format_jianli_list_normalizes_6digit():
    text = '199001--199601  某大学学习\n199601--  某单位工作'
    result = _format_jianli_list(text)
    assert result[0] == '1990.01--1996.01  某大学学习'
    assert result[1] == '1996.01--         某单位工作'


def test_format_jianli_list_already_formatted():
    text = '1990.01--1996.01  某大学学习\n1996.01--         某单位工作'
    result = _format_jianli_list(text)
    assert result[0] == '1990.01--1996.01  某大学学习'
    assert result[1] == '1996.01--         某单位工作'


def test_format_jianli_list_passthrough_non_matching():
    text = '这是普通文字\n1990.01--1996.01  某经历'
    result = _format_jianli_list(text)
    assert '这是普通文字' in result
    assert '1990.01--1996.01  某经历' in result


def test_format_jianli_list_returns_list():
    result = _format_jianli_list('201207--201606  经历一\n201607--  经历二')
    assert isinstance(result, list)
    assert len(result) == 2


def test_format_jianli_list_empty():
    assert _format_jianli_list('') == []


# ── Integration tests ─────────────────────────────────────────────────────────

def make_template(path: Path) -> Path:
    doc = Document()
    doc.add_paragraph('姓名：{{XingMing}}')
    doc.add_paragraph('出生年月：{{ChuShengNianYue}}')
    doc.add_paragraph('入党时间：{{RuDangShiJian}}')
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


def test_build_context_jiating_has_age(sample_lrmx, tmp_path):
    tpl_path = make_template(tmp_path / 'template.docx')
    from docxtpl import DocxTemplate
    tpl = DocxTemplate(tpl_path)
    exporter = DocxExporter(tpl_path)
    ctx = exporter._build_context(LrmxFile(sample_lrmx), tpl)
    assert isinstance(ctx['JiaTingChengYuan'], list)
    member = ctx['JiaTingChengYuan'][0]
    assert member['ChengWei'] == '妻子'
    assert 'Age' in member
    assert '岁' in member['Age']
    assert member['ChuShengRiQi'] == '1992.05'


def test_build_context_jianli_is_list(sample_lrmx, tmp_path):
    tpl_path = make_template(tmp_path / 'template.docx')
    from docxtpl import DocxTemplate
    tpl = DocxTemplate(tpl_path)
    exporter = DocxExporter(tpl_path)
    ctx = exporter._build_context(LrmxFile(sample_lrmx), tpl)
    assert isinstance(ctx['JianLi'], list)
    assert ctx['JianLi'][0] == '2012.07--2016.06  某大学某专业学习'
    assert ctx['JianLi'][1] == '2016.07--         某单位科员'


def test_build_context_retire_field(sample_lrmx, tmp_path):
    tpl_path = make_template(tmp_path / 'template.docx')
    from docxtpl import DocxTemplate
    tpl = DocxTemplate(tpl_path)
    exporter = DocxExporter(tpl_path)
    ctx = exporter._build_context(LrmxFile(sample_lrmx), tpl)
    # DaoLingNianYue 205501 → far future
    assert '2055.01' in ctx['DaoLingNianYue']
    assert '后退休' in ctx['DaoLingNianYue']
