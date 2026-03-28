#!/usr/bin/env python3
"""
AetherEdge Hello Agent — sample workload script.

Runs in an isolated subprocess with a sanitized environment.
No access to the node's private keys, certs, or AETHER_ variables.
"""
import os
import platform
import sys

SEPARATOR = "─" * 52

print(SEPARATOR)
print("  AetherEdge Hello Agent")
print(SEPARATOR)
print(f"  Hostname  : {platform.node()}")
print(f"  OS        : {platform.system()} {platform.release()}")
print(f"  Arch      : {platform.machine()}")
print(f"  Python    : {sys.version.split()[0]}")
print(f"  PID       : {os.getpid()}")
print()

# Prove the environment is isolated — no sensitive vars should be visible
sensitive = [
    k for k in os.environ
    if any(k.startswith(p) for p in ("AETHER", "SSL", "CERT", "KEY", "SECRET", "TOKEN"))
]
if sensitive:
    print(f"  [WARNING] Sensitive env vars leaked: {sensitive}")
else:
    print("  Env isolation  : OK — no sensitive vars visible ✓")

print()
print("  Processing AI Task...")
print("  [1/3] Analyzing input data...")
print("  [2/3] Running inference...")
print("  [3/3] Generating output...")
print()
print("  Result: Task completed successfully.")
print(SEPARATOR)
