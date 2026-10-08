"""Bounded TCP connect scanning, with no application payload or SSH login."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import errno
import queue
import socket
import subprocess
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

from .ssh_utils import ssh_argv
from .ui_components import fit_window_to_parent, install_context_help


def scan_addresses(session, user):
    host = session.hostname
    if session.is_ssh_config_session:
        result = subprocess.run(ssh_argv(session, user, ["-G"]), capture_output=True, text=True, timeout=8,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode:
            raise ValueError("SSH-Alias konnte nicht aufgelöst werden.")
        fields = dict(line.split(None, 1) for line in result.stdout.splitlines() if len(line.split(None, 1)) == 2)
        host = fields.get("hostname", host)
    # The scan intentionally follows the direct PC-to-IP path, never SSH proxies.
    unique = {}
    for family, kind, protocol, _, address in socket.getaddrinfo(host, 0, type=socket.SOCK_STREAM):
        unique[(family, address)] = (family, kind, protocol, address)
    if not unique:
        raise ValueError("Keine Zieladresse aufgelöst.")
    return list(unique.values())


def probe_port(address, port, timeout):
    family, kind, protocol, endpoint = address
    target = (endpoint[0], port, *endpoint[2:])
    try:
        with socket.socket(family, kind, protocol) as connection:
            connection.settimeout(timeout)
            code = connection.connect_ex(target)
    except (TimeoutError, socket.timeout):
        return "timeout"
    except OSError:
        return "error"
    if code == 0:
        return "open"
    if code in (errno.ECONNREFUSED, 10061):
        return "refused"
    if code in (errno.ETIMEDOUT, errno.EWOULDBLOCK, errno.EAGAIN, 10060, 10035):
        return "timeout"
    return "error"


def scan_address(address, cancel, report, *, ports=range(1, 65536), rate=50, timeout=1, workers=64):
    """Bound pending work and starts/sec globally; wait at most one probe on cancel."""
    if not 1 <= rate <= 100 or not 0 < timeout <= 5 or not 1 <= workers <= 64:
        raise ValueError("Ungültige Scan-Grenzen.")
    counts = dict(open=0, refused=0, timeout=0, error=0)
    pending, iterator = {}, iter(ports)
    total, done, exhausted = len(ports), 0, False
    next_start, last_report = time.monotonic(), 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        while pending or not exhausted:
            if cancel.is_set():
                for future in pending:
                    future.cancel()
                break
            now = time.monotonic()
            if not exhausted and len(pending) < workers and now >= next_start:
                try:
                    port = next(iterator)
                except StopIteration:
                    exhausted = True
                else:
                    pending[pool.submit(probe_port, address, port, timeout)] = port
                    # No catch-up burst after a slow poll or response.
                    next_start = now + 1 / rate
            completed, _ = wait(pending, timeout=0, return_when=FIRST_COMPLETED) if pending else (set(), set())
            for future in completed:
                port = pending.pop(future)
                status = future.result()
                counts[status] += 1
                done += 1
                if status == "open":
                    report("open", port)
            if done and now - last_report >= .2:
                report("progress", (done, total, dict(counts)))
                last_report = now
            if not completed:
                cancel.wait(min(.01, max(.001, next_start - time.monotonic())))
        # Let bounded in-flight probes finish, retaining any verified open ports.
        for future, port in pending.items():
            if future.cancelled():
                continue
            status = future.result()
            counts[status] += 1
            done += 1
            if status == "open":
                report("open", port)
    report("progress", (done, total, dict(counts)))
    return done, total, counts


class FullPortScanDialog(tk.Toplevel):
    def __init__(self, parent, sessions, user=""):
        super().__init__(parent)
        install_context_help(self, "diagnosis")
        self.title("Alle TCP-Ports prüfen – dauert sehr lange")
        self.transient(parent)
        self.sessions, self.user = list(sessions), user
        self.cancel_event = threading.Event()
        self.events = queue.SimpleQueue()
        self.running, self.timer = False, None
        frame = ttk.Frame(self, padding=14)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(6, weight=1)
        info = ttk.Label(frame, text=f"{len(sessions)} Ziel(e): alle TCP-Ports 1–65535 je aufgelöster IP, direkt von diesem Rechner.\nDauert sehr lange: mehrere zehn Minuten oder länger. Ziele/IPs werden nacheinander geprüft.\nKeine Anmeldung, keine Nutzdaten, keine UDP-Prüfung. Verbindungen können Logs, Sicherheitsalarme oder Sperren auslösen; empfindliche Dienste können beeinträchtigt werden.\nSSH-Proxys werden nicht benutzt. Nur scannen, wenn das im Zielnetz vorgesehen ist.", wraplength=880, justify="left")
        info.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        settings = ttk.Frame(frame)
        settings.grid(row=1, column=0, sticky="ew")
        ttk.Label(settings, text="Max. Verbindungsstarts pro Sekunde:").pack(side="left")
        self.rate = tk.StringVar(value="50")
        self.rate_entry = ttk.Spinbox(settings, from_=1, to=100, textvariable=self.rate, width=5)
        self.rate_entry.pack(side="left", padx=8)
        ttk.Label(settings, text="Timeout je Port (Sekunden):").pack(side="left")
        self.timeout = tk.StringVar(value="1")
        self.timeout_entry = ttk.Spinbox(settings, from_=.5, to=5, increment=.5, textvariable=self.timeout, width=5)
        self.timeout_entry.pack(side="left", padx=8)
        rate_hint = ttk.Label(frame, text="Höchstens 64 Verbindungen gleichzeitig. 50 Starts/s bedeuten mindestens ca. 22 Minuten je IP; Timeouts können die Dauer verlängern.", wraplength=860)
        rate_hint.grid(row=2, column=0, sticky="ew", pady=8)
        self.status = tk.StringVar(value="Bereit. Ein Scan startet erst mit „Vollscan starten“.")
        status_label = ttk.Label(frame, textvariable=self.status, wraplength=860)
        status_label.grid(row=3, column=0, sticky="ew", pady=4)
        frame.bind("<Configure>", lambda event: [label.configure(wraplength=max(180, event.width - 28)) for label in (info, rate_hint, status_label)])
        self.progress = ttk.Progressbar(frame, maximum=65535)
        self.progress.grid(row=4, column=0, sticky="ew", pady=8)
        ttk.Label(frame, text="Erreichbare TCP-Ports · kein Beleg für einen bestimmten Dienst oder eine erfolgreiche Anmeldung").grid(row=5, column=0, sticky="w")
        self.output = ttk.Treeview(frame, columns=("host", "ip", "port"), show="headings")
        for name, label, width in (("host", "Host", 250), ("ip", "Geprüfte IP", 280), ("port", "TCP-Port", 140)):
            self.output.heading(name, text=label)
            self.output.column(name, width=width)
        self.output.grid(row=6, column=0, sticky="nsew")
        bar = ttk.Scrollbar(frame, command=self.output.yview)
        bar.grid(row=6, column=1, sticky="ns")
        self.output.configure(yscrollcommand=bar.set)
        self.details = tk.Text(frame, height=3, wrap="word", state="disabled")
        self.details.grid(row=7, column=0, sticky="ew", pady=8)
        self.show_details("Keine Ergebnisse. Timeout = keine Antwort; nicht sicher geschlossen. Abgelehnt = TCP-Verbindung ausdrücklich zurückgewiesen.")
        actions = ttk.Frame(frame)
        actions.grid(row=8, column=0, sticky="e")
        self.start_button = ttk.Button(actions, text="Vollscan starten", command=self.start)
        self.start_button.pack(side="left", padx=8)
        self.stop_button = ttk.Button(actions, text="Abbrechen", command=self.stop, state="disabled")
        self.stop_button.pack(side="left")
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Destroy>", self._destroyed, add="+")
        fit_window_to_parent(self, parent.master or parent, 980, 760)

    def start(self):
        if self.running:
            return
        try:
            rate, timeout = int(self.rate.get()), float(self.timeout.get())
            if not 1 <= rate <= 100 or not .5 <= timeout <= 5:
                raise ValueError()
        except ValueError:
            messagebox.showwarning("Scan-Grenzen", "1–100 Starts/s und 0,5–5 Sekunden Timeout wählen.", parent=self)
            return
        self.events = queue.SimpleQueue()
        self.cancel_event.clear()
        self.output.delete(*self.output.get_children())
        self.progress.configure(value=0)
        self.running = True
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.rate_entry.configure(state="disabled")
        self.timeout_entry.configure(state="disabled")
        self.status.set("Vollscan läuft … Zieladressen werden aufgelöst.")
        self.show_details("Noch kein Ziel vollständig geprüft.")
        events, cancel = self.events, self.cancel_event
        sessions, user = list(self.sessions), self.user

        def work():
            incomplete = False
            summaries = []
            try:
                for session in sessions:
                    if cancel.is_set():
                        break
                    try:
                        addresses = scan_addresses(session, session.username or user)
                    except (OSError, ValueError, subprocess.TimeoutExpired):
                        incomplete = True
                        summaries.append(f"{session.display_name}: Auflösung fehlgeschlagen, nicht gescannt")
                        events.put(("summary", "\n".join(summaries)))
                        continue
                    for address in addresses:
                        if cancel.is_set():
                            break
                        host, ip = session.display_name, address[3][0]
                        events.put(("target", (host, ip)))

                        def report(kind, value):
                            events.put((kind, (host, ip, value)))

                        done, total, counts = scan_address(address, cancel, report, rate=rate, timeout=timeout)
                        summaries.append(f"{host} ({ip}): {done}/{total} geprüft; {counts['open']} offen, {counts['refused']} abgelehnt, {counts['timeout']} ohne Antwort, {counts['error']} Fehler")
                        events.put(("summary", "\n".join(summaries)))
                events.put(("finished", "Abgebrochen – Teilergebnis" if cancel.is_set() else "Scan beendet – unvollständig (Zielauflösung fehlgeschlagen)" if incomplete else "Vollscan abgeschlossen"))
            except Exception:
                events.put(("finished", "Scan fehlgeschlagen – Teilergebnis, kein vollständiger Nachweis"))

        try:
            threading.Thread(target=work, daemon=True).start()
        except (OSError, RuntimeError):
            events.put(("finished", "Scan konnte nicht gestartet werden"))
        self.timer = self.after(100, self.poll)

    def show_details(self, text):
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", text)
        self.details.configure(state="disabled")

    def poll(self):
        self.timer = None
        for _ in range(500):
            try:
                kind, value = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "open":
                host, ip, port = value
                self.output.insert("", "end", values=(host, ip, port))
            elif kind == "target":
                self.progress.configure(value=0)
                self.status.set(f"{value[0]} ({value[1]}): Scan startet …")
            elif kind == "progress":
                host, ip, (done, total, counts) = value
                self.progress.configure(maximum=total, value=done)
                self.status.set(f"{host} ({ip}): {done}/{total} · {counts['open']} offen · {counts['timeout']} ohne Antwort · {counts['error']} Fehler")
            elif kind == "summary":
                self.show_details(value)
            elif kind == "finished":
                self.running = False
                self.status.set(value + ". Ergebnisse gelten für diesen Rechner und den Prüfzeitpunkt.")
                self.start_button.configure(state="normal")
                self.stop_button.configure(state="disabled")
                self.rate_entry.configure(state="normal")
                self.timeout_entry.configure(state="normal")
        if self.running:
            self.timer = self.after(100, self.poll)

    def stop(self):
        self.cancel_event.set()
        self.stop_button.configure(state="disabled")
        self.status.set("Abbruch läuft … bereits gestartete Prüfungen enden nach ihrem Timeout.")

    def _destroyed(self, event):
        if event.widget is self:
            self.cancel_event.set()
            if self.timer is not None:
                self.after_cancel(self.timer)
                self.timer = None

    def close(self):
        self.cancel_event.set()
        self.destroy()
