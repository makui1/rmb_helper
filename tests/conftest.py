from pathlib import Path
import pytest

SAMPLES_DIR = Path(__file__).parent / 'samples'

@pytest.fixture
def sample_lrmx(tmp_path):
    content = '''<?xml version="1.0" encoding="UTF-8"?>
<Person>
    <XingMing>张三</XingMing>
    <XingBie>男</XingBie>
    <ChuShengNianYue>199001</ChuShengNianYue>
    <MinZu>汉族</MinZu>
    <ShenFenZheng>110101199001011234</ShenFenZheng>
    <RuDangShiJian>201506</RuDangShiJian>
    <CanJiaGongZuoShiJian>201207</CanJiaGongZuoShiJian>
    <JianKangZhuangKuang>健康</JianKangZhuangKuang>
    <XianRenZhiWu>科员</XianRenZhiWu>
    <NiRenZhiWu/>
    <NiMianZhiWu/>
    <ZhengZhiMianMao>中共党员</ZhengZhiMianMao>
    <QuanRiZhiJiaoYu_XueLi>本科</QuanRiZhiJiaoYu_XueLi>
    <TianBiaoRen>李四</TianBiaoRen>
</Person>'''
    p = tmp_path / 'zhangsan.lrmx'
    p.write_text(content, encoding='utf-8')
    return p
