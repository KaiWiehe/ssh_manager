"""Opt-in Windows ConPTY/real SSH test. Never uses the user's SSH files.

Install requirements-terminal-test.txt, build, then run this script. A temporary
ssh.exe shim adds only -F <isolated config> to the real client's arguments. This
tests actual native/Git SSH and terminal handles without changing known_hosts.
It does NOT replace manual Windows Terminal/Herdr host UI acceptance.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
import socket
import subprocess
import sys
import threading
import time

import paramiko
import pyte
from winpty import PtyProcess

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ssh_manager_app.cli_search import safe_text
from ssh_manager_app.core import _find_git_bash


class SSHServer(paramiko.ServerInterface):
    def __init__(self):
        self.ready = threading.Event()
        self.sizes = []
        self.received = []

    def check_auth_password(self, username, password):
        return paramiko.AUTH_SUCCESSFUL if (username, password) == ("qatest", "local-test-only") else paramiko.AUTH_FAILED

    def get_allowed_auths(self, username):
        return "password"

    def check_channel_request(self, kind, chanid):
        return paramiko.OPEN_SUCCEEDED if kind == "session" else paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def check_channel_pty_request(self, channel, term, width, height, *args):
        self.sizes.append((width, height))
        return True

    def check_channel_window_change_request(self, channel, width, height, *args):
        self.sizes.append((width, height))
        return True

    def check_channel_shell_request(self, channel):
        self.ready.set()
        return True


class LocalSSH:
    def __init__(self):
        self.key = paramiko.RSAKey.generate(2048)
        self.socket = socket.socket()
        self.socket.bind(("127.0.0.1", 0))
        self.socket.listen(8)
        self.socket.settimeout(0.5)
        self.port = self.socket.getsockname()[1]
        self.stopped = threading.Event()
        self.servers = []
        self.transports = []
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()

    def serve(self):
        while not self.stopped.is_set():
            try:
                client, _ = self.socket.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            threading.Thread(target=self.handle, args=(client,), daemon=True).start()

    def handle(self, client):
        server = SSHServer()
        self.servers.append(server)
        transport = paramiko.Transport(client)
        self.transports.append(transport)
        try:
            transport.add_server_key(self.key)
            transport.start_server(server=server)
            channel = transport.accept(20)
            if channel is None or not server.ready.wait(20):
                return
            channel.send(b"\r\nSSHM_QA_REMOTE_READY\r\nqa> ")
            pending = b""
            while transport.is_active():
                data = channel.recv(1024)
                server.received.append(data.hex())
                if not data:
                    break
                if b"\x03" in data:
                    channel.send(b"\r\nSSHM_QA_REMOTE_INTERRUPT\r\nqa> ")
                    pending = b""
                    continue
                channel.send(data)
                pending += data.replace(b"\r", b"\n")
                if b"exit\n" in pending:
                    channel.send(b"\r\nSSHM_QA_REMOTE_EXIT\r\n")
                    channel.send_exit_status(7)
                    channel.close()
                    return
        except (OSError, EOFError, paramiko.SSHException):
            return
        finally:
            transport.close()

    def close(self):
        self.stopped.set()
        self.socket.close()
        for transport in self.transports:
            transport.close()
        self.thread.join(timeout=2)


class Terminal:
    def __init__(self, command, env):
        self.process = PtyProcess.spawn(command, env=env, cwd=str(ROOT), dimensions=(35, 125))
        self.raw = ""
        self.screen = pyte.Screen(125, 35)
        self.stream = pyte.Stream(self.screen)
        threading.Thread(target=self.read, daemon=True).start()

    def read(self):
        try:
            while True:
                data = self.process.read(8192)
                self.raw += data
                self.stream.feed(data)
        except (EOFError, OSError):
            return

    def wait(self, text, timeout=25, start=0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if text.casefold() in safe_text(self.raw[start:], multiline=True).casefold():
                return
            time.sleep(0.05)
        raise AssertionError(f"Terminal did not show {text!r}:\n{safe_text(self.raw[-7000:], multiline=True)}")

    def write(self, value):
        self.process.write(value)

    def close(self):
        self.process.close(force=True)


def compile_shim(folder):
    source = folder / "ssh.cs"
    source.write_text('''using System;
using System.Diagnostics;
class Ssh {
    static int Main(string[] args) {
        Console.CancelKeyPress += delegate(object sender, ConsoleCancelEventArgs e) { e.Cancel = true; };
        var start = new ProcessStartInfo(Environment.GetEnvironmentVariable("SSHM_QA_SSH"));
        start.UseShellExecute = false;
        start.Arguments = "-F \\"" + Environment.GetEnvironmentVariable("SSHM_QA_CONFIG") + "\\" " + String.Join(" ", args);
        var child = Process.Start(start);
        child.WaitForExit();
        return child.ExitCode;
    }
}''', encoding="utf-8")
    compiler = Path(os.environ["WINDIR"]) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
    subprocess.run([str(compiler), "/nologo", f"/out:{folder / 'ssh.exe'}", str(source)], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, default=ROOT / "dist/sshm.exe")
    parser.add_argument("--output", type=Path, default=ROOT / ".tmp/terminal-qa")
    parser.add_argument("--shell", choices=["powershell", "git-bash"])
    parser.add_argument("--skip-interrupt", action="store_true")
    parser.add_argument("--direct-ssh", action="store_true", help="Compare the same terminal against bare SSH without the CLI")
    args = parser.parse_args()
    if args.direct_ssh and args.shell != "git-bash":
        parser.error("--direct-ssh requires --shell git-bash")
    folder = args.output.resolve()
    folder.mkdir(parents=True, exist_ok=True)
    compile_shim(folder)
    bash = Path(_find_git_bash())
    clients = {"powershell": Path(os.environ["WINDIR"]) / "System32/OpenSSH/ssh.exe",
               "git-bash": bash.parent.parent / "usr/bin/ssh.exe"}
    server = LocalSSH()
    results = []
    try:
        for shell, client in clients.items():
            if args.shell and shell != args.shell:
                continue
            first_server = len(server.servers)
            home = folder / shell
            data = home / "AppData/SSH-Manager"
            data.mkdir(parents=True, exist_ok=True)
            (home / ".ssh").mkdir(exist_ok=True)
            (home / ".ssh/config").write_text("", encoding="utf-8")
            config = home / "test_config"
            known = home / "known_hosts"
            config.write_text(f'Host *\n  UserKnownHostsFile "{known.as_posix()}"\n  StrictHostKeyChecking ask\n  PreferredAuthentications password\n  PubkeyAuthentication no\n', encoding="utf-8")
            if shell == "git-bash":
                # Git SSH honors HOME, so exercise it directly without the shim.
                (home / ".ssh/config").write_text(config.read_text(encoding="utf-8"), encoding="utf-8")
            known.unlink(missing_ok=True)
            (data / "app_sessions.json").write_text(json.dumps({"sessions": [{"id": "local-qa", "name": "__sshm_local_qa__", "hostname": "127.0.0.1", "port": server.port, "username": "qatest", "folder": "QA/Local", "source": "app"}]}), encoding="utf-8")
            (data / "notes.json").write_text(json.dumps({"notes": {"__app__local-qa": "Lokaler Test – vollständige Notiz\nZweite Zeile"}}), encoding="utf-8")
            (data / "ui_state.json").write_text(json.dumps({"favorite_sessions": {"__app__local-qa": True}}), encoding="utf-8")
            env = dict(os.environ)
            # Windows environment variable names are case-insensitive. Do not
            # supply a second differently cased Path entry to CreateProcess.
            for key in list(env):
                if key.casefold() == "path":
                    env.pop(key)
            env.update(APPDATA=str(home / "AppData"), USERPROFILE=str(home), HOME=str(home),
                       SSHM_QA_SSH=str(client), SSHM_QA_CONFIG=str(config),
                       PATH=str(client.parent if shell == "git-bash" else folder) + os.pathsep + os.environ.get("PATH", ""))
            exe = args.exe.resolve()
            if shell == "powershell":
                escaped = str(exe).replace("'", "''")
                command = ["powershell.exe", "-NoLogo", "-NoProfile", "-NoExit", "-Command",
                           f"& '{escaped}' __sshm_local_qa__; Write-Host ('SSHM_QA_RETURN:' + $LASTEXITCODE)"]
            else:
                invocation = (f"{shlex.quote(client.as_posix())} -p {server.port} qatest@127.0.0.1" if args.direct_ssh else
                              f"{shlex.quote(exe.as_posix())} __sshm_local_qa__")
                script = f"{invocation}; result=$?; printf '\\nSSHM_QA_RETURN:%s\\n' \"$result\"; exec bash --noprofile --norc -i"
                command = [str(bash), "--noprofile", "--norc", "-c", script]
            terminal = Terminal(command, env)
            try:
                if not args.direct_ssh:
                    terminal.wait("Verbindungen")
                    terminal.wait("__sshm_local_qa__")
                    # Two real ancestors and one matching leaf; focus remains search.
                    terminal.write("\x1b[B\x1b[B")
                    time.sleep(0.3)
                    (home / "picker.txt").write_text("\n".join(terminal.screen.display), encoding="utf-8")
                    terminal.write("\r")
                terminal.wait("Are you sure you want to continue connecting")
                terminal.write("yes\r")
                terminal.wait("password:")
                terminal.write("local-test-only\r")
                terminal.wait("SSHM_QA_REMOTE_READY")
                terminal.process.setwinsize(28, 90)
                time.sleep(0.3)
                if not args.skip_interrupt:
                    start = len(terminal.raw)
                    terminal.write("\x03")
                    terminal.wait("SSHM_QA_REMOTE_INTERRUPT", start=start)
                terminal.write("exit\r")
                terminal.wait("SSHM_QA_RETURN:7")
                start = len(terminal.raw)
                terminal.write(("Write-Host ('SSHM_QA_' + 'SHELL_USABLE')\r" if shell == "powershell" else
                                "printf '%s%s\\n' SSHM_QA_ SHELL_USABLE\r"))
                terminal.wait("SSHM_QA_SHELL_USABLE", start=start)
                if not args.direct_ssh:
                    recent = json.loads((data / "ui_state.json").read_text())["recent_sessions"]
                    assert recent == ["__app__local-qa"]
                assert any((90, 28) in s.sizes for s in server.servers[first_server:])
                checks = ["host-key", "password", "remote-pty", "resize", "exit-code-7", "shell-return"]
                if not args.direct_ssh:
                    checks.extend(["picker", "recent"])
                if not args.skip_interrupt:
                    checks.append("ctrl-c")
                results.append({"shell": shell, "client": str(client), "exe": str(exe),
                                "host": "Windows ConPTY (not a WT/Herdr UI test)", "passed": True,
                                "mode": "bare-ssh-baseline" if args.direct_ssh else "cli",
                                "skipped": ["ctrl-c"] if args.skip_interrupt else [], "checks": checks})
                print(shell + ": passed", flush=True)
            finally:
                (home / "terminal.txt").write_text(safe_text(terminal.raw, multiline=True), encoding="utf-8")
                (home / "server.json").write_text(json.dumps([{"sizes": s.sizes, "received": s.received} for s in server.servers]), encoding="utf-8")
                terminal.close()
    finally:
        server.close()
        (folder / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
