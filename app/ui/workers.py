from PySide6.QtCore import QThread, Signal


class BaseWorker(QThread):
    """所有后台 Worker 的基类。提供统一的 log / progress / error 信号，
    消除各 Tab 重复声明的样板代码。

    子类选择两种模式之一：
    a) 简单任务：实现 work()，run() 自动包裹 try/except → emits error
    b) 复杂循环任务（per-file try/except）：直接 override run()，
       仅复用信号声明，无需调用 super().run()
    """
    log      = Signal(str)
    progress = Signal(int)   # 0–100
    error    = Signal(str)   # 统一错误信号；UI 层连接到 show_error

    def run(self):
        try:
            self.work()
        except Exception as e:
            self.error.emit(str(e))

    def work(self):
        raise NotImplementedError
