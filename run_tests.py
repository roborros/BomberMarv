#!/usr/bin/env python3
"""Run every BomberMarv test suite and fail if any suite fails."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time


ROOT = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(ROOT, "web_client")


def _resolve_js_runner() -> list[str]:
    bun = shutil.which("bun")
    if bun is None:
        user_profile = os.environ.get("USERPROFILE") or os.environ.get("HOME") or ""
        candidate = os.path.join(user_profile, ".bun", "bin", "bun.exe" if os.name == "nt" else "bun")
        if os.path.exists(candidate):
            bun = candidate
    if bun:
        return [bun]
    npm = shutil.which("npm")
    if npm:
        return [npm]
    raise RuntimeError("Need bun or npm on PATH to run web_client tests")


def _run(name: str, command: list[str], cwd: str, env: dict[str, str]) -> bool:
    print(f"\n==> {name}", flush=True)
    print(" ".join(command), flush=True)
    started = time.perf_counter()
    result = subprocess.run(command, cwd=cwd, env=env)
    elapsed = time.perf_counter() - started
    if result.returncode == 0:
        print(f"OK  {name} ({elapsed:.1f}s)", flush=True)
        return True
    print(f"FAIL  {name} ({elapsed:.1f}s, exit {result.returncode})", flush=True)
    return False


def main() -> int:
    env = os.environ.copy()
    env.setdefault("SDL_VIDEODRIVER", "dummy")
    env.setdefault("SDL_AUDIODRIVER", "dummy")
    env.setdefault("PYTHONUNBUFFERED", "1")

    js = _resolve_js_runner()
    js_test = js + (["run", "test"] if os.path.basename(js[0]).lower().startswith("bun") else ["test"])
    js_typecheck = js + (
        ["x", "tsc", "--noEmit"]
        if os.path.basename(js[0]).lower().startswith("bun")
        else ["exec", "--", "tsc", "--noEmit"]
    )

    suites = [
        ("Python import smoke", [sys.executable, "test_imports.py"], ROOT),
        (
            "Python unit tests",
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"],
            ROOT,
        ),
        ("Web client unit tests", js_test, WEB),
        ("Web client typecheck", js_typecheck, WEB),
    ]

    print("Running all BomberMarv tests", flush=True)
    failed = []
    for name, command, cwd in suites:
        if not _run(name, command, cwd, env):
            failed.append(name)

    print(flush=True)
    if failed:
        print("Failed suites: " + ", ".join(failed), flush=True)
        return 1
    print("All test suites passed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
