"""Actually launch Genshin via the node and observe the result.

Run with ComfyUI's bundled Python and ``COMFYUI_DIR`` pointing at your
ComfyUI install:

    set COMFYUI_DIR=C:\\path\\to\\ComfyUI
    python comfyui_genshin_start/_test_real_launch.py

Steps:
  1. Load the node through ComfyUI's load_custom_node (real bootstrap).
  2. Call execute(trigger=True, mode='auto', region='global', dry_run=False)
     - i.e. exactly what pressing Queue in the UI would do.
  3. Snapshot child processes before / after to see whether GenshinImpact.exe
     (or its launcher) actually started.
  4. Try alternate Popen flags / os.startfile if the first attempt fails,
     and report which path actually works.
"""

from __future__ import annotations

import asyncio
import inspect
import os
import subprocess
import sys
import time
from pathlib import Path

COMFYUI_DIR = os.environ.get("COMFYUI_DIR", r"C:\ComfyUI")


def list_genshin_pids() -> list[tuple[int, str, str]]:
    """Return (pid, image_name, cmdline) for any Genshin/HoYoPlay process."""
    out = subprocess.run(
        ["wmic", "process", "get", "ProcessId,Name,CommandLine", "/format:csv"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    rows: list[tuple[int, str, str]] = []
    for line in out.stdout.splitlines():
        if not line.strip() or line.startswith("Node"):
            continue
        parts = line.split(",")
        if len(parts) < 4:
            continue
        cmdline, name, pid_str = parts[1], parts[2], parts[3]
        if not pid_str.strip().isdigit():
            continue
        joined = (name + " " + cmdline).lower()
        if any(k in joined for k in ("genshin", "yuanshen", "hoyoplay", "mhyprot")):
            rows.append((int(pid_str), name, cmdline))
    return rows


def announce_processes(label: str) -> list[tuple[int, str, str]]:
    rows = list_genshin_pids()
    print(f"  [{label}] {len(rows)} genshin/hoyoplay process(es):")
    for pid, name, cmd in rows:
        print(f"    pid={pid} name={name} cmd={cmd[:120]}")
    return rows


def kill_pids(pids: set[int]) -> None:
    for pid in pids:
        try:
            subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                           capture_output=True, text=True, timeout=10)
        except subprocess.SubprocessError:
            pass


def boot_node():
    sys.path.insert(0, COMFYUI_DIR)
    os.chdir(COMFYUI_DIR)
    import nodes  # type: ignore[import-not-found]

    target = os.path.join(COMFYUI_DIR, "custom_nodes", "comfyui_genshin_start")
    fn = nodes.load_custom_node
    if inspect.iscoroutinefunction(fn):
        ok = asyncio.run(fn(target))
    else:
        ok = fn(target)
    print(f"  load_custom_node -> {ok!r}")
    cls = nodes.NODE_CLASS_MAPPINGS["GenshinImpactLauncher"]
    return cls()


def main() -> int:
    if not os.path.isdir(COMFYUI_DIR):
        print(f"[FAIL] ComfyUI not found at {COMFYUI_DIR}")
        print("Set COMFYUI_DIR env var to your ComfyUI install path.")
        return 1

    print("[1/4] checking detection:")
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from comfyui_genshin_start import launcher as L
    exe = L.find_game_exe()
    print(f"  exe = {exe}")
    if exe is None:
        print("  detection failed; bailing")
        return 1

    print("[2/4] booting node via ComfyUI's load_custom_node:")
    node = boot_node()

    print("[3/4] baseline process snapshot:")
    before = {pid for pid, *_ in announce_processes("before")}

    print("[4/4] calling execute(trigger=True, mode='auto', region='global', dry_run=False):")
    t0 = time.time()
    result = node.execute(
        trigger=True, mode="auto", region="global", passthrough=None, dry_run=False,
    )
    dt = time.time() - t0
    print(f"  returned in {dt*1000:.0f} ms: {result}")

    time.sleep(4)
    after_rows = announce_processes("after")
    after = {pid for pid, *_ in after_rows}
    new_pids = after - before
    print(f"  new pids: {sorted(new_pids)}")

    if new_pids:
        print("[OK] launch produced child process(es). Killing them so the test")
        print("     does not leave Genshin running on your machine.")
        time.sleep(2)
        kill_pids(new_pids)
        return 0

    print()
    print("[FAIL] no Genshin/HoYoPlay process appeared. Diagnosing...")

    print("[a] Re-running launch_exe directly with extra error capture:")
    try:
        proc = subprocess.Popen(
            [str(exe)],
            cwd=str(Path(exe).parent),
            creationflags=0x00000008 | 0x00000200,
            close_fds=True,
        )
        print(f"    Popen returned, pid={proc.pid}")
        time.sleep(2)
        print(f"    poll() = {proc.poll()}")
    except OSError as exc:
        print(f"    Popen raised OSError: {exc!r}")
        if hasattr(exc, "winerror"):
            print(f"    winerror = {exc.winerror}")

    print("[b] Trying os.startfile() (uses ShellExecute, respects UAC manifest):")
    try:
        os.startfile(str(exe))  # type: ignore[attr-defined]
        print("    os.startfile() returned")
        time.sleep(4)
        rows2 = announce_processes("after-startfile")
        new2 = {pid for pid, *_ in rows2} - before
        if new2:
            print(f"    [OK] os.startfile spawned: {sorted(new2)}")
            kill_pids(new2)
            return 2
    except OSError as exc:
        print(f"    os.startfile raised: {exc!r}")

    return 4


if __name__ == "__main__":
    sys.exit(main())
