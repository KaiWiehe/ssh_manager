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
