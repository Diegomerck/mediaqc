"""Read-only Windows process-tree working-set/private-byte sampling via Win32."""

import ctypes
from ctypes import wintypes as w


class Entry(ctypes.Structure):
    _fields_ = [
        ("size", w.DWORD),
        ("usage", w.DWORD),
        ("pid", w.DWORD),
        ("heap", ctypes.c_size_t),
        ("module", w.DWORD),
        ("threads", w.DWORD),
        ("parent", w.DWORD),
        ("priority", w.LONG),
        ("flags", w.DWORD),
        ("exe", w.WCHAR * 260),
    ]


class Counters(ctypes.Structure):
    _fields_ = [("size", w.DWORD), ("faults", w.DWORD)] + [
        (name, ctypes.c_size_t)
        for name in (
            "peak_ws",
            "ws",
            "peak_paged",
            "paged",
            "peak_nonpaged",
            "nonpaged",
            "pagefile",
            "peak_pagefile",
            "private",
        )
    ]


def sample(root: int) -> tuple[int, int, set[int]]:
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [w.DWORD, w.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = w.HANDLE
    kernel.Process32FirstW.argtypes = [w.HANDLE, ctypes.POINTER(Entry)]
    kernel.Process32NextW.argtypes = [w.HANDLE, ctypes.POINTER(Entry)]
    kernel.CloseHandle.argtypes = [w.HANDLE]
    kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    kernel.OpenProcess.restype = w.HANDLE
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes = [w.HANDLE, ctypes.POINTER(Counters), w.DWORD]
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    parents = {}
    entry = Entry()
    entry.size = ctypes.sizeof(entry)
    try:
        more = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        while more:
            parents[int(entry.pid)] = int(entry.parent)
            more = kernel.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel.CloseHandle(snapshot)
    owned = {root}
    while True:
        expanded = owned | {pid for pid, parent in parents.items() if parent in owned}
        if expanded == owned:
            break
        owned = expanded
    working = private = 0
    for pid in owned:
        handle = kernel.OpenProcess(0x410, False, pid)
        if not handle:
            continue  # A child may exit between enumeration and opening it.
        try:
            counters = Counters()
            counters.size = ctypes.sizeof(counters)
            if psapi.GetProcessMemoryInfo(
                handle, ctypes.byref(counters), counters.size
            ):
                working += counters.ws
                private += counters.private
        finally:
            kernel.CloseHandle(handle)
    return working, private, owned & parents.keys()
