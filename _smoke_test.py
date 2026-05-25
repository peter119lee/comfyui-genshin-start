"""Smoke test for the Genshin launcher node.

Run from this folder's parent so that ``comfyui_genshin_start`` imports as
a package, e.g.::

    cd /path/to/parent
    python comfyui_genshin_start/_smoke_test.py

Stubs out webbrowser.open and subprocess.Popen so we don't actually launch
anything on the test machine.
"""

from __future__ import annotations

import os
import subprocess
import sys
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)


def _stub_webbrowser(url: str) -> bool:
    print(f"  [stub] webbrowser.open({url!r})")
    return True


def _stub_popen(*args, **kwargs):
    print(f"  [stub] subprocess.Popen(args={args}, kwargs={list(kwargs)})")

    class _FakeProc:
        pid = 0

    return _FakeProc()


def _stub_run(*args, **kwargs):
    """Stand in for subprocess.run used by silent_install_hoyoplay()."""
    argv = args[0] if args else kwargs.get("args", [])
    print(f"  [stub] subprocess.run(argv[0:3]={argv[:3]})")

    class _FakeResult:
        returncode = 0
        stdout = "0\n"
        stderr = ""

    return _FakeResult()


def main() -> None:
    webbrowser.open = _stub_webbrowser
    subprocess.Popen = _stub_popen
    subprocess.run = _stub_run

    import comfyui_genshin_start as pkg
    from comfyui_genshin_start import launcher as L

    print("NODE_CLASS_MAPPINGS:", list(pkg.NODE_CLASS_MAPPINGS.keys()))
    print("Display:", pkg.NODE_DISPLAY_NAME_MAPPINGS)

    cls = pkg.NODE_CLASS_MAPPINGS["GenshinImpactLauncher"]
    inputs = cls.INPUT_TYPES()
    print("mode enum:", inputs["required"]["mode"][0])
    print("region enum:", inputs["required"]["region"][0])
    print("RETURN_TYPES:", cls.RETURN_TYPES, "RETURN_NAMES:", cls.RETURN_NAMES)
    print("CATEGORY:", cls.CATEGORY)
    print()

    node = cls()

    print("--- dry_run ---")
    print(node.execute(trigger=True, mode="auto", region="global", passthrough="img", dry_run=True))

    print("--- trigger off ---")
    print(node.execute(trigger=False, mode="auto", region="global", passthrough="img"))

    print("--- open_page global ---")
    print(node.execute(trigger=True, mode="open_page", region="global"))

    print("--- cloud cn ---")
    print(node.execute(trigger=True, mode="cloud", region="cn"))

    print("--- cloud global (no global cloud product) ---")
    print(node.execute(trigger=True, mode="cloud", region="global"))

    L.find_game_exe = lambda: None
    L._hoyoplay_protocol_registered = lambda: False

    print("--- launch_only with no install ---")
    print(node.execute(trigger=True, mode="launch_only", region="global"))

    print("--- auto on win32 with HoYoPlay protocol already registered ---")
    L._hoyoplay_protocol_registered = lambda: True
    print(node.execute(trigger=True, mode="auto", region="global"))

    print("--- auto on win32 clean machine: download + silent install + hint ---")
    L._hoyoplay_protocol_registered = lambda: False
    # stub download_installer so we don't hit the network in CI
    from pathlib import Path as _Path
    def _stub_dl(region, run_after):
        print(f"  [stub] download_installer(region={region}, run_after={run_after})")
        return L.LaunchResult(True, "downloaded", r"C:\fake\HoYoPlay_install.exe")
    _orig_dl = L.download_installer
    L.download_installer = _stub_dl
    try:
        print(node.execute(trigger=True, mode="auto", region="global"))
    finally:
        L.download_installer = _orig_dl

    orig_platform = sys.platform
    try:
        sys.platform = "linux"
        print("--- auto on simulated linux (no install, global) ---")
        print(node.execute(trigger=True, mode="auto", region="global"))
        print("--- auto on simulated linux (no install, cn -> cloud) ---")
        print(node.execute(trigger=True, mode="auto", region="cn"))
        print("--- download_only on simulated linux ---")
        print(node.execute(trigger=True, mode="download_only", region="global"))
    finally:
        sys.platform = orig_platform


if __name__ == "__main__":
    main()
