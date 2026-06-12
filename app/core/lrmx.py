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
