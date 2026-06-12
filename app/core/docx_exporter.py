from pathlib import Path
from docxtpl import DocxTemplate
from .lrmx import LrmxFile


class DocxExporter:
    def __init__(self, template_path: Path) -> None:
        self.template_path = Path(template_path)

    def export(self, lrmx: LrmxFile, output_path: Path) -> None:
        tpl = DocxTemplate(self.template_path)
        context = lrmx.as_dict()
        tpl.render(context)
        tpl.save(output_path)
