import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication
from app.ui.main_window import MainWindow


def _parse_open_path(argv: list[str]) -> str | None:
    """从命令行参数中取出被双击的 .lrmx 文件路径。"""
    for arg in argv[1:]:
        if arg.lower().endswith('.lrmx') and Path(arg).is_file():
            return arg
    return None


def main():
    app = QApplication(sys.argv)
    app.setApplicationName('rmb_helper')
    window = MainWindow(open_path=_parse_open_path(sys.argv))
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    main()
