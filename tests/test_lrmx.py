from app.core.lrmx import LrmxFile

def test_get_existing_field(sample_lrmx):
    lf = LrmxFile(sample_lrmx)
    assert lf.get('XingMing') == '张三'

def test_get_missing_field_returns_empty(sample_lrmx):
    lf = LrmxFile(sample_lrmx)
    assert lf.get('NotExist') == ''

def test_get_empty_element_returns_empty(sample_lrmx):
    lf = LrmxFile(sample_lrmx)
    assert lf.get('NiRenZhiWu') == ''

def test_set_existing_field(sample_lrmx):
    lf = LrmxFile(sample_lrmx)
    lf.set('XianRenZhiWu', '副科长')
    assert lf.get('XianRenZhiWu') == '副科长'

def test_set_new_field(sample_lrmx):
    lf = LrmxFile(sample_lrmx)
    lf.set('NewField', '新值')
    assert lf.get('NewField') == '新值'

def test_save_and_reload(sample_lrmx, tmp_path):
    lf = LrmxFile(sample_lrmx)
    lf.set('XianRenZhiWu', '副科长')
    out = tmp_path / 'out.lrmx'
    lf.save(out)
    lf2 = LrmxFile(out)
    assert lf2.get('XianRenZhiWu') == '副科长'

def test_as_dict_contains_fields(sample_lrmx):
    lf = LrmxFile(sample_lrmx)
    d = lf.as_dict()
    assert d['XingMing'] == '张三'
    assert d['ShenFenZheng'] == '110101199001011234'

def test_save_overwrites_in_place(sample_lrmx):
    lf = LrmxFile(sample_lrmx)
    lf.set('XingMing', '李雷')
    lf.save()
    lf2 = LrmxFile(sample_lrmx)
    assert lf2.get('XingMing') == '李雷'


def test_family_members_returns_list(sample_lrmx):
    lf = LrmxFile(sample_lrmx)
    members = lf.family_members()
    assert len(members) == 1
    assert members[0]['ChengWei'] == '妻子'
    assert members[0]['XingMing'] == '李梅'
    assert members[0]['ChuShengRiQi'] == '199205'


def test_family_members_empty_when_no_jiating(tmp_path):
    content = '''<?xml version="1.0" encoding="UTF-8"?>
<Person>
    <XingMing>测试</XingMing>
</Person>'''
    p = tmp_path / 'test.lrmx'
    p.write_text(content, encoding='utf-8')
    lf = LrmxFile(p)
    assert lf.family_members() == []
