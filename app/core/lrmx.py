import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional


class LrmxFile:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._tree = ET.parse(self.path)
        self._root = self._tree.getroot()

    def get(self, field: str) -> str:
        elem = self._root.find(field)
        if elem is None:
            return ''
        return elem.text or ''

    def set(self, field: str, value: str) -> None:
        elem = self._root.find(field)
        if elem is not None:
            elem.text = value
        else:
            new_elem = ET.SubElement(self._root, field)
            new_elem.text = value

    def save(self, path: Optional[Path | str] = None) -> None:
        target = Path(path) if path else self.path
        ET.indent(self._tree, space='    ')
        self._tree.write(
            str(target),
            encoding='UTF-8',
            xml_declaration=True,
        )

    def as_dict(self) -> dict[str, str]:
        return {elem.tag: (elem.text or '') for elem in self._root}

    def family_members(self) -> list[dict[str, str]]:
        """Return JiaTingChengYuan Items as a list of field dicts."""
        container = self._root.find('JiaTingChengYuan')
        if container is None:
            return []
        result = []
        for item in container:
            member = {child.tag: (child.text or '') for child in item}
            result.append(member)
        return result

    def set_family_members(self, members: list[dict[str, str]]) -> None:
        container = self._root.find('JiaTingChengYuan')
        if container is None:
            container = ET.SubElement(self._root, 'JiaTingChengYuan')
        container.clear()
        for m in members:
            item = ET.SubElement(container, 'Item')
            for key, val in m.items():
                child = ET.SubElement(item, key)
                child.text = val

    def normalize(self) -> None:
        """将内容为空的叶子标签转为自闭合单标签（<tag/>），就地保存。

        递归遍历 XML 树，对无子元素且文本为空（或纯空白）的标签，
        将其 text 设为 None，使得序列化时输出 <tag/> 而非 <tag></tag>。
        同时清理姓名字段中多余的空格（如 "张 三" → "张三"）。
        """
        def _norm(elem):
            if len(elem) == 0:
                if elem.text is not None and not elem.text.strip():
                    elem.text = None
                elif elem.tag == 'XingMing' and elem.text:
                    # 删除姓名中的多余空格（如 "张 三" → "张三"）
                    stripped = re.sub(r'\s+', '', elem.text)
                    if stripped != elem.text:
                        elem.text = stripped
            else:
                for child in elem:
                    _norm(child)
        _norm(self._root)
        self.save()

    @classmethod
    def create_new(cls) -> 'LrmxFile':
        """创建无磁盘文件的空 LrmxFile，用于新建文档并另存为。"""
        root = ET.Element('Person')
        ET.SubElement(root, 'Version').text = '2.0'
        inst = cls.__new__(cls)
        inst.path = None          # type: ignore[assignment]
        inst._tree = ET.ElementTree(root)
        inst._root = root
        return inst
