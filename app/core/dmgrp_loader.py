import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def _xml_path() -> Path:
    if hasattr(sys, '_MEIPASS'):
        return Path(sys._MEIPASS) / 'resources' / 'DmGrp.xml'
    return Path(__file__).parent.parent / 'resources' / 'DmGrp.xml'


class DmgrpLoader:
    def __init__(self) -> None:
        self._data: dict[str, list[str]] = {}
        p = _xml_path()
        if p.exists():
            self._load(p)

    def _load(self, path: Path) -> None:
        root = ET.parse(path).getroot()
        for grp in root.findall('dmgrp'):
            gid = grp.get('id', '')
            opts = [c.get('dmcpt', '').strip() for c in grp.findall('dmcod')]
            self._data[gid] = [o for o in opts if o]

    def options(self, grp_id: str) -> list[str]:
        return list(self._data.get(grp_id, []))


_loader: DmgrpLoader | None = None


def get_loader() -> DmgrpLoader:
    global _loader
    if _loader is None:
        _loader = DmgrpLoader()
    return _loader
