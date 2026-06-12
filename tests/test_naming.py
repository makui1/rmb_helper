from app.utils.naming import apply_rule, PRESETS

def test_basic_substitution():
    fields = {'XingMing': '张三', 'ShenFenZheng': '110101199001011234'}
    assert apply_rule('{XingMing}{ShenFenZheng}', fields) == '张三110101199001011234'

def test_missing_field_kept_as_placeholder():
    fields = {'XingMing': '张三'}
    assert apply_rule('{XingMing}_{ShenFenZheng}', fields) == '张三_{ShenFenZheng}'

def test_illegal_chars_replaced():
    fields = {'XingMing': '张/三', 'ShenFenZheng': '123'}
    result = apply_rule('{XingMing}{ShenFenZheng}', fields)
    assert '/' not in result
    assert result == '张_三123'

def test_empty_template_returns_unnamed():
    assert apply_rule('', {}) == '未命名'

def test_presets_is_list_of_tuples():
    assert isinstance(PRESETS, list)
    assert all(isinstance(p, tuple) and len(p) == 2 for p in PRESETS)

def test_presets_first_item_is_default():
    template, label = PRESETS[0]
    assert '{XingMing}' in template
    assert '{ShenFenZheng}' in template
