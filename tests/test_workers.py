import threading
from ssh_manager_app.workers import run_worker


class Owner:
    def __init__(self):
        self.callbacks = []
        self.thread = threading.get_ident()
        self.exists = True
    def winfo_exists(self):
        assert threading.get_ident() == self.thread
        return self.exists
    def bind(self, *args, **kwargs):
        return "binding"
    def unbind(self, *args):
        assert threading.get_ident() == self.thread
    def after(self, delay, callback):
        assert threading.get_ident() == self.thread
        self.callbacks.append(callback)


def test_worker_error_is_delivered_on_main_thread():
    owner = Owner()
    received = []
    def fail():
        assert threading.get_ident() != owner.thread
        raise ValueError("broken")
    thread = run_worker(owner, fail, lambda _: None, lambda error: received.append((threading.get_ident(), type(error))))
    thread.join(2)
    owner.callbacks.pop(0)()
    assert received == [(owner.thread, ValueError)]


def test_closed_window_discards_late_worker_results():
    owner = Owner()
    received = []
    thread = run_worker(owner, lambda: 42, received.append)
    thread.join(2)
    owner.exists = False
    owner.callbacks.pop(0)()
    assert received == []


def test_diagnostics_exclude_exception_secrets_and_bound_log_size(tmp_path, monkeypatch):
    import logging
    from ssh_manager_app import errors
    logger = logging.getLogger("ssh_manager.errors")
    previous = list(logger.handlers)
    logger.handlers = []
    monkeypatch.setattr(errors, "_APPDATA_DIR", tmp_path)
    try:
        try:
            raise ValueError("PASSWORD-and-confidential-command")
        except ValueError as error:
            errors.record_failure(error)
        text = (tmp_path / "error.log").read_text()
        assert "ValueError" in text
        assert "PASSWORD" not in text
        assert "confidential-command" not in text
        assert logger.handlers[0].maxBytes == 262144
        assert logger.handlers[0].backupCount == 3
    finally:
        for handler in logger.handlers:
            handler.close()
        logger.handlers = previous


def test_real_tk_stays_responsive_until_worker_result_arrives():
    import time
    import tkinter as tk
    import pytest
    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(str(error))
    root.withdraw()
    release = threading.Event()
    received = []
    ticks = []
    errors = []
    root.report_callback_exception = lambda *args: errors.append(args)
    try:
        thread = run_worker(root, lambda: (release.wait(2), 42)[1], received.append)
        root.after(5, lambda: ticks.append(True))
        deadline = time.monotonic() + 1
        while not ticks and time.monotonic() < deadline:
            root.update()
            time.sleep(.01)
        assert ticks and not received
        release.set()
        thread.join(2)
        deadline = time.monotonic() + 1
        while not received and time.monotonic() < deadline:
            root.update()
            time.sleep(.01)
        assert received == [42]
        assert errors == []
    finally:
        release.set()
        root.destroy()
