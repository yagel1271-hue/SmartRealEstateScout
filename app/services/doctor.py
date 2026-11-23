"""Environment check ("doctor"): Python, Git, Ollama, disk, RAM.

Read-only. Works on Windows (primary target) and Linux.
"""
from __future__ import annotations

import ctypes
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

MIN_PYTHON = (3, 12)
MIN_FREE_DISK_GB = 5


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str
    required: bool = True


def _version_of(cmd: str) -> str | None:
    exe = shutil.which(cmd)
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=15)
        return (out.stdout or out.stderr).strip().splitlines()[0]
    except Exception as exc:  # noqa: BLE001
        return f"found but failed to run ({exc})"


def total_ram_gb() -> float | None:
    try:
        if sys.platform == "win32":
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))  # type: ignore[attr-defined]
            return round(stat.ullTotalPhys / 1024**3, 1)
        with open("/proc/meminfo", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    return round(int(line.split()[1]) / 1024**2, 1)
    except Exception:  # noqa: BLE001
        return None
    return None


def run_checks(project_dir: Path) -> list[CheckResult]:
    results: list[CheckResult] = []

    py_ok = sys.version_info[:2] >= MIN_PYTHON
    results.append(CheckResult("Python", py_ok, f"{platform.python_version()} (need {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+)"))

    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    results.append(CheckResult("Virtual env (.venv)", in_venv, "active" if in_venv else "not active - run setup.bat"))

    git = _version_of("git")
    results.append(CheckResult("Git", git is not None, git or "not installed"))

    free_gb = round(shutil.disk_usage(project_dir).free / 1024**3, 1)
    results.append(CheckResult("Free disk", free_gb >= MIN_FREE_DISK_GB, f"{free_gb} GB (need {MIN_FREE_DISK_GB}+)"))

    ram = total_ram_gb()
    results.append(CheckResult("RAM", ram is not None, f"{ram} GB" if ram else "unknown", required=False))

    ollama = _version_of("ollama")
    results.append(CheckResult("Ollama (optional)", ollama is not None, ollama or "not installed", required=False))

    results.append(CheckResult("OS", True, f"{platform.system()} {platform.release()} {platform.machine()}", required=False))
    return results


def format_report(results: list[CheckResult]) -> str:
    lines = []
    for r in results:
        mark = "OK  " if r.ok else ("FAIL" if r.required else "--  ")
        lines.append(f"[{mark}] {r.name:<20} {r.detail}")
    failed = [r for r in results if r.required and not r.ok]
    lines.append("")
    lines.append("ALL REQUIRED CHECKS PASSED" if not failed else f"{len(failed)} REQUIRED CHECK(S) FAILED")
    return "\n".join(lines)
