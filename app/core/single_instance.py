"""单实例支持：通过本地 socket 把第二个实例要打开的文件转交给已运行的实例。

- 第二个进程启动时先尝试连接已存在的本地服务；连上则发送文件路径后退出。
- 第一个（主）进程监听本地服务，收到路径后激活窗口并加载文件。
服务名按用户区分，避免多用户会话相互干扰。
"""
from __future__ import annotations

import getpass

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


def _server_name() -> str:
    try:
        user = getpass.getuser()
    except Exception:
        user = 'default'
    return f'rmb_helper_single_instance_{user}'


class SingleInstance(QObject):
    """管理单实例本地服务。message_received(str) 在收到第二实例消息时发出。"""

    message_received = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._name = _server_name()
        self._server: QLocalServer | None = None

    def try_hand_off(self, payload: str) -> bool:
        """若已有实例在运行，则把 payload 发送过去并返回 True；否则返回 False。"""
        sock = QLocalSocket()
        sock.connectToServer(self._name)
        if not sock.waitForConnected(300):
            return False
        sock.write((payload or '').encode('utf-8'))
        sock.flush()
        sock.waitForBytesWritten(300)
        sock.disconnectFromServer()
        return True

    def start_listening(self) -> None:
        """作为主实例开始监听。先清理可能残留的同名服务。"""
        QLocalServer.removeServer(self._name)
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._on_new_connection)
        self._server.listen(self._name)

    def _on_new_connection(self) -> None:
        sock = self._server.nextPendingConnection()
        if sock is None:
            return
        try:
            if sock.waitForReadyRead(1000):
                data = bytes(sock.readAll()).decode('utf-8', 'ignore')
                self.message_received.emit(data)
        finally:
            sock.disconnectFromServer()
