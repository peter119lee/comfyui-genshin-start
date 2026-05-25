"""Diagnose why find_game_exe() returns None on this machine.

Dumps everything our discovery layer looks at, so we can see whether the
miss is a registry key naming issue, an unscanned drive, or a deeper
nested install path than our walker handles.
"""

from __future__ import annotations

import os
import string
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from comfyui_genshin_start import launcher as L  # noqa: E402


def section(title: str) -> None:
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def dump_registry() -> None:
    section("Registry probe (legacy hardcoded keys)")
    if sys.platform != "win32":
        print("  not Windows; skipping")
        return
    import winreg

    keys = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\miHoYo\Genshin Impact"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Cognosphere\Genshin Impact"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Genshin Impact"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Genshin Impact"),
    ]
    hive_names = {
        winreg.HKEY_LOCAL_MACHINE: "HKLM",
        winreg.HKEY_CURRENT_USER: "HKCU",
        winreg.HKEY_CLASSES_ROOT: "HKCR",
    }

    for hive, sub in keys:
        label = f"{hive_names.get(hive, hive)}\\{sub}"
        try:
            with winreg.OpenKey(hive, sub) as key:
                values: dict[str, object] = {}
                i = 0
                while True:
                    try:
                        name, val, _ = winreg.EnumValue(key, i)
                    except OSError:
                        break
                    values[name] = val
                    i += 1
                print(f"[+] {label}")
                for k, v in values.items():
                    print(f"      {k!r}: {v!r}")
        except FileNotFoundError:
            print(f"[-] {label}  (missing)")
        except OSError as exc:
            print(f"[?] {label}  ({exc})")


def dump_uninstall_search() -> None:
    """Walk every Uninstall subkey to find anything Genshin-shaped."""
    section("Uninstall registry search (DisplayName matches)")
    if sys.platform != "win32":
        return
    import winreg

    roots = [
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER,
         r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    needles = ("genshin", "原神", "yuanshen", "hoyoplay", "mihoyo", "cognosphere")

    for hive, root in roots:
        try:
            with winreg.OpenKey(hive, root) as key:
                i = 0
                while True:
                    try:
                        sub = winreg.EnumKey(key, i)
                    except OSError:
                        break
                    i += 1
                    try:
                        with winreg.OpenKey(key, sub) as child:
                            try:
                                display, _ = winreg.QueryValueEx(child, "DisplayName")
                            except FileNotFoundError:
                                continue
                            d_lower = str(display).lower()
                            if not any(n in d_lower for n in needles):
                                continue
                            try:
                                loc, _ = winreg.QueryValueEx(child, "InstallLocation")
                            except FileNotFoundError:
                                loc = "<no InstallLocation>"
                            try:
                                exe, _ = winreg.QueryValueEx(child, "DisplayIcon")
                            except FileNotFoundError:
                                exe = "<no DisplayIcon>"
                            print(f"  {root}\\{sub}")
                            print(f"    DisplayName     : {display}")
                            print(f"    InstallLocation : {loc}")
                            print(f"    DisplayIcon     : {exe}")
                    except OSError:
                        continue
        except FileNotFoundError:
            continue


def dump_hoyoplay_protocol() -> None:
    section("HoYoPlay URI handler")
    if sys.platform != "win32":
        return
    import winreg

    for proto in ("hyp-osel", "hyp-cnb", "hyp"):
        try:
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, proto) as key:
                try:
                    cmd_key = winreg.OpenKey(key, r"shell\open\command")
                    try:
                        val, _ = winreg.QueryValueEx(cmd_key, "")
                    except FileNotFoundError:
                        val = "<no default value>"
                    finally:
                        cmd_key.Close()
                    print(f"[+] {proto}://  ->  {val}")
                except OSError:
                    print(f"[+] {proto}://  (registered, no shell\\open\\command)")
        except FileNotFoundError:
            print(f"[-] {proto}://  (not registered)")


def dump_filesystem_scan() -> None:
    section("Filesystem scan (drives x suffixes)")
    print(f"COMMON_PATH_SUFFIXES = {L.COMMON_PATH_SUFFIXES}")
    print(f"GAME_EXE_NAMES = {L.GAME_EXE_NAMES}")
    print()

    drives: list[str] = []
    for letter in string.ascii_uppercase:
        root = f"{letter}:\\"
        if os.path.exists(root):
            drives.append(root)
    print(f"drives present: {drives}")
    print()

    for drive in drives:
        for suffix in L.COMMON_PATH_SUFFIXES:
            full = Path(drive) / suffix
            if not full.is_dir():
                continue
            print(f"[+] {full}")
            try:
                for child in sorted(full.iterdir()):
                    marker = "/" if child.is_dir() else " "
                    print(f"      {marker} {child.name}")
            except OSError as exc:
                print(f"      (cannot list: {exc})")


def dump_deep_search() -> None:
    section("Deep search (Program Files + drive root, depth 6)")
    if sys.platform != "win32":
        return
    drives = []
    for letter in string.ascii_uppercase:
        root = f"{letter}:\\"
        if os.path.exists(root):
            drives.append(root)

    print("Scanning... may take 10-30 seconds.")
    found: list[Path] = []
    roots: list[Path] = []
    for drive in drives:
        for prefix in ("", "Program Files", "Program Files (x86)", "Games", "Game"):
            r = Path(drive) / prefix if prefix else Path(drive)
            if r.is_dir():
                roots.append(r)

    targets = set(L.GAME_EXE_NAMES)
    skip_names = {
        "windows", "Windows", "WINDOWS",
        "$Recycle.Bin", "System Volume Information",
        "ProgramData",
        "node_modules", ".git", "__pycache__",
    }

    for root in roots:
        stack: list[tuple[Path, int]] = [(root, 0)]
        while stack:
            current, depth = stack.pop()
            if depth > 6:
                continue
            try:
                entries = list(current.iterdir())
            except (PermissionError, OSError):
                continue
            for entry in entries:
                try:
                    if entry.is_file() and entry.name in targets:
                        print(f"[!!] {entry}")
                        found.append(entry)
                    elif entry.is_dir() and entry.name not in skip_names:
                        stack.append((entry, depth + 1))
                except (PermissionError, OSError):
                    continue
    if not found:
        print("[--] no GenshinImpact.exe / YuanShen.exe found under scanned roots")


def main() -> None:
    print(f"sys.platform = {sys.platform}")
    print(f"sys.version  = {sys.version.split()[0]}")
    print(f"current find_game_exe() result: {L.find_game_exe()}")

    dump_registry()
    dump_uninstall_search()
    dump_hoyoplay_protocol()
    dump_filesystem_scan()
    dump_deep_search()


if __name__ == "__main__":
    main()
