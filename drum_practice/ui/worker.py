"""Run slow calls (network requests) off the UI thread."""

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


class _Signals(QObject):
    done = Signal(object)
    failed = Signal(object)


class _Job(QRunnable):
    def __init__(self, fn):
        super().__init__()
        self.fn = fn
        self.signals = _Signals()

    def run(self) -> None:
        try:
            result = self.fn()
        except Exception as error:  # handed to the UI thread to report
            self.signals.failed.emit(error)
        else:
            self.signals.done.emit(result)


def run_in_background(fn, on_done, on_failed) -> _Job:
    """Call `fn()` on a worker thread; `on_done(result)` or `on_failed(error)`
    then run on the UI thread. Keep the returned job alive until it reports."""
    job = _Job(fn)
    job.signals.done.connect(on_done)
    job.signals.failed.connect(on_failed)
    QThreadPool.globalInstance().start(job)
    return job
