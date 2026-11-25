"""Own a Windows SSH process and its ProxyJump/ProxyCommand descendants."""
from __future__ import annotations

import ctypes
from ctypes import wintypes


CREATE_SUSPENDED = 0x00000004


class _RestartThreadEntry(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("usage", wintypes.DWORD), ("thread_id", wintypes.DWORD),
                ("owner_id", wintypes.DWORD), ("base_priority", wintypes.LONG),
                ("delta_priority", wintypes.LONG), ("flags", wintypes.DWORD)]


class WindowsRestartJob:
    def __init__(self):
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.close_handle = self._api("CloseHandle", wintypes.BOOL, wintypes.HANDLE)
        self.terminate_job = self._api("TerminateJobObject", wintypes.BOOL, wintypes.HANDLE, wintypes.UINT)
        create = self._api("CreateJobObjectW", wintypes.HANDLE, ctypes.c_void_p, wintypes.LPCWSTR)
        self.handle = create(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())

    def _api(self, name, result, *arguments):
        call = getattr(self.kernel, name)
        call.restype = result
        call.argtypes = arguments
        return call

    def attach_and_resume(self, pid):
        open_process = self._api("OpenProcess", wintypes.HANDLE, wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        assign = self._api("AssignProcessToJobObject", wintypes.BOOL, wintypes.HANDLE, wintypes.HANDLE)
        process = open_process(0x0101, False, pid)  # PROCESS_SET_QUOTA | PROCESS_TERMINATE
        if not process:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            if not assign(self.handle, process):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            self.close_handle(process)
        self._resume_primary_thread(pid)

    def _resume_primary_thread(self, pid):
        snapshot_threads = self._api("CreateToolhelp32Snapshot", wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD)
        snapshot = snapshot_threads(0x00000004, 0)  # TH32CS_SNAPTHREAD
        if snapshot == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            thread_pointer = ctypes.POINTER(_RestartThreadEntry)
            first = self._api("Thread32First", wintypes.BOOL, wintypes.HANDLE, thread_pointer)
            next_thread = self._api("Thread32Next", wintypes.BOOL, wintypes.HANDLE, thread_pointer)
            entry = _RestartThreadEntry(size=ctypes.sizeof(_RestartThreadEntry))
            found = first(snapshot, ctypes.byref(entry))
            while found:
                if entry.owner_id == pid:
                    self._resume_thread(entry.thread_id)
                    return
                entry.size = ctypes.sizeof(_RestartThreadEntry)
                found = next_thread(snapshot, ctypes.byref(entry))
        finally:
            self.close_handle(snapshot)
        raise OSError("Primärer SSH-Thread nicht gefunden.")

    def _resume_thread(self, thread_id):
        open_thread = self._api("OpenThread", wintypes.HANDLE, wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        resume = self._api("ResumeThread", wintypes.DWORD, wintypes.HANDLE)
        thread = open_thread(0x0002, False, thread_id)  # THREAD_SUSPEND_RESUME
        if not thread:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            if resume(thread) != 1:
                raise OSError("SSH-Thread konnte nicht fortgesetzt werden.")
        finally:
            self.close_handle(thread)

    def terminate(self):
        self.terminate_job(self.handle, 1)

    def close(self):
        try:
            self.terminate()
        finally:
            self.close_handle(self.handle)
