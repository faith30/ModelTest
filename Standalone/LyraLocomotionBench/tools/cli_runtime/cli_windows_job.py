"""Windows-only process-tree ownership for one benchmark invocation.

Use ``with WindowsJob() as job: process = job.popen(...)``. The process starts
suspended, is assigned using Popen._handle, and is resumed only after assignment.
This closes the ordinary Popen -> AssignProcessToJobObject child-spawn race.
No breakaway flag is enabled. Closing the job kills remaining descendants.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import subprocess
import time


if os.name != "nt":
    raise ImportError("windows_job requires Windows")

CREATE_SUSPENDED = 0x00000004
CREATE_BREAKAWAY_FROM_JOB = 0x01000000
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION = 1
TH32CS_SNAPTHREAD = 0x00000004
THREAD_SUSPEND_RESUME = 0x0002
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


class JobError(RuntimeError):
    pass


class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class IO_COUNTERS(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
    )]


class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class JOBOBJECT_BASIC_ACCOUNTING_INFORMATION_DATA(ctypes.Structure):
    _fields_ = [
        ("TotalUserTime", ctypes.c_longlong),
        ("TotalKernelTime", ctypes.c_longlong),
        ("ThisPeriodTotalUserTime", ctypes.c_longlong),
        ("ThisPeriodTotalKernelTime", ctypes.c_longlong),
        ("TotalPageFaultCount", wintypes.DWORD),
        ("TotalProcesses", wintypes.DWORD),
        ("ActiveProcesses", wintypes.DWORD),
        ("TotalTerminatedProcesses", wintypes.DWORD),
    ]


class THREADENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
        ("th32ThreadID", wintypes.DWORD), ("th32OwnerProcessID", wintypes.DWORD),
        ("tpBasePri", wintypes.LONG), ("tpDeltaPri", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
    ]


kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
kernel32.CreateJobObjectW.restype = wintypes.HANDLE
kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
kernel32.SetInformationJobObject.restype = wintypes.BOOL
kernel32.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p]
kernel32.QueryInformationJobObject.restype = wintypes.BOOL
kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
kernel32.TerminateJobObject.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
kernel32.Thread32First.argtypes = [wintypes.HANDLE, ctypes.POINTER(THREADENTRY32)]
kernel32.Thread32First.restype = wintypes.BOOL
kernel32.Thread32Next.argtypes = [wintypes.HANDLE, ctypes.POINTER(THREADENTRY32)]
kernel32.Thread32Next.restype = wintypes.BOOL
kernel32.OpenThread.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenThread.restype = wintypes.HANDLE
kernel32.ResumeThread.argtypes = [wintypes.HANDLE]
kernel32.ResumeThread.restype = wintypes.DWORD


def _error(operation: str, code: int | None = None) -> JobError:
    code = ctypes.get_last_error() if code is None else code
    return JobError(f"{operation} failed: {ctypes.WinError(code)}")


def _resume_initial_thread(pid: int) -> None:
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
    if snapshot == INVALID_HANDLE_VALUE:
        raise _error("CreateToolhelp32Snapshot")
    threads = []
    try:
        entry = THREADENTRY32()
        entry.dwSize = ctypes.sizeof(entry)
        present = kernel32.Thread32First(snapshot, ctypes.byref(entry))
        while present:
            if entry.th32OwnerProcessID == pid:
                threads.append(entry.th32ThreadID)
            entry.dwSize = ctypes.sizeof(entry)
            present = kernel32.Thread32Next(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    if len(threads) != 1:
        raise JobError(f"Expected one initial suspended thread for PID {pid}; found {len(threads)}")
    thread = kernel32.OpenThread(THREAD_SUSPEND_RESUME, False, threads[0])
    if not thread:
        raise _error("OpenThread")
    try:
        previous_count = kernel32.ResumeThread(thread)
        if previous_count == 0xFFFFFFFF:
            raise _error("ResumeThread")
        if previous_count != 1:
            raise JobError(f"Unexpected initial thread suspend count: {previous_count}")
    finally:
        kernel32.CloseHandle(thread)


class WindowsJob:
    def __init__(self) -> None:
        # NULL security attributes create a non-inheritable, unnamed job handle.
        self._handle = kernel32.CreateJobObjectW(None, None)
        if not self._handle:
            raise _error("CreateJobObjectW")
        limits = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel32.SetInformationJobObject(
            self._handle, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(limits), ctypes.sizeof(limits),
        ):
            error = _error("SetInformationJobObject")
            kernel32.CloseHandle(self._handle)
            self._handle = None
            raise error

    def _require_open(self) -> None:
        if self._handle is None:
            raise JobError("The job is already closed")

    def attach(self, process: subprocess.Popen) -> None:
        """Assign an existing process; prefer popen() to prevent pre-attach children."""
        self._require_open()
        if process.poll() is not None:
            raise JobError("Cannot assign a process that has already exited")
        if not kernel32.AssignProcessToJobObject(self._handle, wintypes.HANDLE(int(process._handle))):
            raise _error("AssignProcessToJobObject (unmanaged execution is not allowed)")

    def popen(self, *args, **kwargs) -> subprocess.Popen:
        self._require_open()
        flags = kwargs.get("creationflags", 0)
        if flags & CREATE_BREAKAWAY_FROM_JOB:
            raise JobError("CREATE_BREAKAWAY_FROM_JOB is forbidden for benchmark processes")
        kwargs["creationflags"] = flags | CREATE_SUSPENDED | subprocess.CREATE_NO_WINDOW
        process = subprocess.Popen(*args, **kwargs)
        try:
            self.attach(process)
            _resume_initial_thread(process.pid)
        except BaseException:
            # The process has not executed application code unless resume itself failed.
            # Never leave an unassigned suspended process behind or run it unmanaged.
            process.kill()
            process.wait(timeout=15)
            raise
        return process

    @property
    def active_processes(self) -> int:
        self._require_open()
        accounting = JOBOBJECT_BASIC_ACCOUNTING_INFORMATION_DATA()
        if not kernel32.QueryInformationJobObject(
            self._handle, JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION,
            ctypes.byref(accounting), ctypes.sizeof(accounting), None,
        ):
            raise _error("QueryInformationJobObject")
        return accounting.ActiveProcesses

    @property
    def limit_flags(self) -> int:
        self._require_open()
        limits = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        if not kernel32.QueryInformationJobObject(
            self._handle, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(limits), ctypes.sizeof(limits), None,
        ):
            raise _error("QueryInformationJobObject limits")
        return limits.BasicLimitInformation.LimitFlags

    def terminate(self, exit_code: int = 1, timeout: float = 15.0) -> None:
        """Terminate all assigned processes and wait for the job to become empty."""
        self._require_open()
        if not kernel32.TerminateJobObject(self._handle, exit_code):
            raise _error("TerminateJobObject")
        deadline = time.monotonic() + timeout
        while self.active_processes:
            if time.monotonic() >= deadline:
                raise JobError("Job processes did not finish terminating before the cleanup deadline")
            time.sleep(0.02)

    def close(self) -> None:
        if self._handle is None:
            return
        try:
            self.terminate()
        finally:
            handle, self._handle = self._handle, None
            if not kernel32.CloseHandle(handle):
                raise _error("CloseHandle job")

    def __enter__(self) -> WindowsJob:
        self._require_open()
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        self.close()
        return False
