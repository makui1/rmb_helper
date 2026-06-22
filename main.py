import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication
from app.ui.main_window import MainWindow
from app.core.single_instance import SingleInstance


def _parse_open_path(argv: list[str]) -> str | None:
    """从命令行参数中取出被双击的 .lrmx 文件路径。"""
    for arg in argv[1:]:
        if arg.lower().endswith('.lrmx') and Path(arg).is_file():
            return arg
    return None


def main():
    app = QApplication(sys.argv)
    app.setApplicationName('rmb_helper')
    open_path = _parse_open_path(sys.argv)

    # 单实例：若已有窗口在运行，把文件交给它并退出
    single = SingleInstance()
    if single.try_hand_off(open_path or ''):
        return

    window = MainWindow(open_path=open_path)
    single.start_listening()
    single.message_received.connect(window.activate_and_open)
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    main()
