"""Medición de recursos compartida por los benchmarks (RAM pico, hardware)."""
import os
import platform
import threading
from pathlib import Path


def _mb(kb: int) -> float:
    return round(kb / 1024, 1)


class PeakRSS(threading.Thread):
    """Muestrea cada 20 ms la RSS del proceso más la de sus hijos vivos (tesseract es un binario aparte).
    ru_maxrss de RUSAGE_CHILDREN no sirve: incluye la memoria heredada por fork() antes del exec."""

    def __init__(self, proc):
        super().__init__(daemon=True)
        self.proc, self.peak, self.peak_children, self._done = proc, 0, 0, threading.Event()

    def run(self):
        import psutil
        while not self._done.wait(0.02):
            try:
                children = sum(c.memory_info().rss for c in self.proc.children(recursive=True))
            except psutil.Error:
                children = 0
            self.peak_children = max(self.peak_children, children)
            self.peak = max(self.peak, self.proc.memory_info().rss + children)

    def stop(self) -> None:
        self._done.set()
        self.join()


def hardware() -> dict:
    mem = dict(l.split(":", 1) for l in Path("/proc/meminfo").read_text().splitlines()[:3])
    return {"arquitectura": platform.machine(), "cpus": os.cpu_count(), "so": platform.platform(),
            "ram_total_mb": _mb(int(mem["MemTotal"].split()[0])),
            "ram_disponible_mb": _mb(int(mem["MemAvailable"].split()[0])),
            "host": os.environ.get("HOST_INFO", "no indicado"), "python": platform.python_version()}
