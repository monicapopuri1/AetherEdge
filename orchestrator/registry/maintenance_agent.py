"""
maintenance_agent.py — Sample registry script.

Checks disk and CPU usage, prints a JSON result to stdout.
The Workload Runner executes this script and captures stdout.
"""
import json
import shutil

import psutil


def run() -> str:
    disk = shutil.disk_usage("/")
    result = {
        "cpu_percent": psutil.cpu_percent(interval=1),
        "disk_total_gb": round(disk.total / 1024**3, 2),
        "disk_used_gb": round(disk.used / 1024**3, 2),
        "disk_free_gb": round(disk.free / 1024**3, 2),
        "disk_used_percent": round(disk.used / disk.total * 100, 1),
    }
    return json.dumps(result)


if __name__ == "__main__":
    print(run())
