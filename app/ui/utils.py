from PySide6.QtWidgets import QMessageBox


def show_error(parent, msg: str) -> None:
    """在所有 UI 层错误提示中统一使用此函数，代替散落的 QMessageBox.critical。"""
    QMessageBox.critical(parent, '错误', msg)


def show_warning(parent, msg: str) -> None:
    """在所有 UI 层警告提示中统一使用此函数，代替散落的 QMessageBox.warning。"""
    QMessageBox.warning(parent, '警告', msg)
