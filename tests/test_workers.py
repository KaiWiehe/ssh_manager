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
