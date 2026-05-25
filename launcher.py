"""Genshin Impact discovery + launch + download helpers.

All operations are best-effort and read-only against the user's machine
(registry queries, filesystem checks). The only side effects are:
    1. starting an already-installed game executable, or
    2. downloading the official HoYoPlay installer to %TEMP% and opening it,
    3. opening the official download page in the default browser.

No silent installs, no privilege escalation, no third-party mirrors.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

# --- Constants ------------------------------------------------------------

DOWNLOAD_PAGE_GLOBAL = "https://genshin.hoyoverse.com/en/download"
DOWNLOAD_PAGE_CN = "https://ys.mihoyo.com/main/download"

# Cloud Genshin: only the CN cloud service is publicly available; the
# global cloud beta was sunset in 2023, so we point global users to the
# regular download page when they ask for "cloud" mode.
CLOUD_PAGE_CN = "https://ys.mihoyo.com/cloud/"
CLOUD_PAGE_GLOBAL = DOWNLOAD_PAGE_GLOBAL

# HoYoPlay launcher installer (the modern launcher that ships Genshin).
HOYOPLAY_INSTALLER_GLOBAL = (
    "https://download-porter.hoyoverse.com/launcher/hyp/HoYoPlay_install.exe"
)
HOYOPLAY_INSTALLER_CN = (
    "https://download-porter.mihoyo.com/launcher/hyp/HoYoPlay_install.exe"
)

GAME_EXE_NAMES = ("GenshinImpact.exe", "YuanShen.exe")

# Path *suffixes* (not full paths). At runtime each suffix is combined
# with every drive letter that exists, so we don't have to hard-code C:/D:/E:.
COMMON_PATH_SUFFIXES = (
    r"HoYoPlay\games",
    r"Program Files\HoYoPlay\games",
    r"Program Files (x86)\HoYoPlay\games",
    r"Genshin Impact",
    r"Program Files\Genshin Impact",
    r"Program Files (x86)\Genshin Impact",
    r"Games\Genshin Impact",
    r"Games\HoYoPlay\games",
)

# Lowercase, case-insensitive substring match against Uninstall DisplayName.
GENSHIN_DISPLAY_NAME_NEEDLES = ("genshin impact", "原神", "yuanshen")

REGISTRY_SCAN_MAX_DEPTH = 5
COMMON_DIR_SCAN_MAX_DEPTH = 4

HOYOPLAY_PROTOCOL_GLOBAL = "hyp-osel://"
HOYOPLAY_PROTOCOL_CN = "hyp-cnb://"

LINUX_WINE_BASES = (
    "~/.wine/drive_c",
    "~/.wine-genshin/drive_c",
    "~/Games",
    "~/.var/app/com.usebottles.bottles/data/bottles/bottles",
    "~/.local/share/lutris/runners/wine",
)
LINUX_SCAN_MAX_DEPTH = 5


# --- Data types -----------------------------------------------------------


@dataclass(frozen=True)
class LaunchResult:
    ok: bool
    action: str
    detail: str

    def to_status(self) -> str:
        prefix = "[OK]" if self.ok else "[FAIL]"
        return f"{prefix} {self.action}: {self.detail}"


# --- Discovery ------------------------------------------------------------


def _shallow_find(
    base: Path,
    target_names: Iterable[str],
    max_depth: int,
) -> Iterable[Path]:
    """Iterative DFS: yield files under ``base`` whose name is in targets."""
    targets = set(target_names)
    if not base.is_dir():
        return
    stack: list[tuple[Path, int]] = [(base, 0)]
    while stack:
        current, depth = stack.pop()
        try:
            entries = list(current.iterdir())
        except (PermissionError, OSError):
            continue
        for entry in entries:
            try:
                if entry.is_file() and entry.name in targets:
                    yield entry
                elif entry.is_dir() and depth < max_depth:
                    if entry.name in {"windows", "ProgramData", "users"}:
                        continue
                    stack.append((entry, depth + 1))
            except (PermissionError, OSError):
                continue


def _linux_wine_candidates() -> Iterable[Path]:
    for raw in LINUX_WINE_BASES:
        base = Path(os.path.expanduser(raw))
        yield from _shallow_find(base, GAME_EXE_NAMES, LINUX_SCAN_MAX_DEPTH)


def _iter_candidate_exes() -> Iterable[Path]:
    """Cross-drive scan with bounded depth on Windows."""
    if sys.platform != "win32":
        return
    import string

    drive_roots: list[Path] = []
    for letter in string.ascii_uppercase:
        root = Path(f"{letter}:\\")
        if root.exists():
            drive_roots.append(root)

    seen: set[Path] = set()
    for drive in drive_roots:
        for suffix in COMMON_PATH_SUFFIXES:
            base = drive / suffix
            if not base.is_dir():
                continue
            for hit in _shallow_find(base, GAME_EXE_NAMES, COMMON_DIR_SCAN_MAX_DEPTH):
                if hit not in seen:
                    seen.add(hit)
                    yield hit


def _registry_uninstall_path() -> Optional[Path]:
    """Walk Windows Uninstall hive matching by DisplayName."""
    if sys.platform != "win32":
        return None
    try:
        import winreg
    except ImportError:
        return None

    uninstall_roots = (
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER,
         r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    )

    candidate_bases: list[Path] = []

    for hive, root_path in uninstall_roots:
        try:
            root_key = winreg.OpenKey(hive, root_path)
        except OSError:
            continue
        try:
            i = 0
            while True:
                try:
                    sub_name = winreg.EnumKey(root_key, i)
                except OSError:
                    break
                i += 1
                try:
                    sub_key = winreg.OpenKey(root_key, sub_name)
                except OSError:
                    continue
                try:
                    try:
                        display, _ = winreg.QueryValueEx(sub_key, "DisplayName")
                    except FileNotFoundError:
                        continue
                    d_lower = str(display).lower()
                    if not any(n in d_lower for n in GENSHIN_DISPLAY_NAME_NEEDLES):
                        continue
                    bases = _harvest_install_bases(sub_key)
                    candidate_bases.extend(bases)
                finally:
                    sub_key.Close()
        finally:
            root_key.Close()

    seen: set[Path] = set()
    for base in candidate_bases:
        if base in seen:
            continue
        seen.add(base)
        if not base.is_dir():
            continue
        for hit in _shallow_find(base, GAME_EXE_NAMES, REGISTRY_SCAN_MAX_DEPTH):
            return hit
    return None


def _harvest_install_bases(sub_key) -> list[Path]:
    """Pull plausible base directories out of an Uninstall registry entry."""
    import winreg

    bases: list[Path] = []

    def _add_dir_value(value_name: str) -> None:
        try:
            raw, _ = winreg.QueryValueEx(sub_key, value_name)
        except FileNotFoundError:
            return
        if not raw:
            return
        candidate = Path(str(raw))
        if candidate.is_dir():
            bases.append(candidate)

    def _add_file_parent_value(value_name: str) -> None:
        try:
            raw, _ = winreg.QueryValueEx(sub_key, value_name)
        except FileNotFoundError:
            return
        if not raw:
            return
        text = str(raw).strip().strip('"')
        if "," in text:
            text = text.split(",", 1)[0]
        path = Path(text)
        parent = path.parent if path.suffix else path
        if parent.is_dir():
            bases.append(parent)

    _add_dir_value("InstallLocation")
    _add_dir_value("InstallPath")
    _add_file_parent_value("DisplayIcon")
    _add_file_parent_value("UninstallString")
    return bases


def _hoyoplay_protocol_registered() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg
    except ImportError:
        return False
    for proto in ("hyp-osel", "hyp-cnb", "hyp"):
        try:
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, proto):
                return True
        except OSError:
            continue
    return False


def find_game_exe() -> Optional[Path]:
    if sys.platform == "win32":
        registry_hit = _registry_uninstall_path()
        if registry_hit is not None:
            return registry_hit
        for candidate in _iter_candidate_exes():
            return candidate
        return None

    if sys.platform.startswith("linux"):
        for candidate in _linux_wine_candidates():
            return candidate
        return None

    return None


# --- Actions --------------------------------------------------------------


def launch_exe(exe_path: Path) -> LaunchResult:
    """Spawn the game executable detached from ComfyUI.

    On Windows GenshinImpact.exe has ``requireAdministrator`` in its manifest
    (mhyprot2 anti-cheat needs kernel driver loading), so plain
    subprocess.Popen raises ``WinError 740 (elevation required)``. We use
    os.startfile which goes through ShellExecute, respects the manifest,
    and triggers the UAC prompt the same way a Start Menu / Explorer
    double-click would.
    """
    if sys.platform == "win32":
        try:
            os.startfile(str(exe_path))  # noqa: S606
        except OSError as exc:
            return LaunchResult(False, "launched_exe", f"{exe_path}: {exc}")
        return LaunchResult(True, "launched_exe", str(exe_path))

    if sys.platform.startswith("linux"):
        return launch_wine(exe_path)

    return LaunchResult(False, "launched_exe", f"unsupported OS: {sys.platform}")


def launch_wine(exe_path: Path) -> LaunchResult:
    """Run a Genshin .exe via the system wine binary.

    Note: HoYoverse's mhyprot2 anti-cheat is a Windows kernel driver and
    will refuse to load under Wine, so the launcher may open but actually
    entering the game world is unlikely to succeed.
    """
    wine_bin = shutil.which("wine") or shutil.which("wine64")
    if wine_bin is None:
        return LaunchResult(
            False,
            "launched_wine",
            "wine not found in PATH; install wine or use mode=open_page/cloud",
        )
    try:
        subprocess.Popen(  # noqa: S603
            [wine_bin, str(exe_path)],
            cwd=str(exe_path.parent),
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
    except OSError as exc:
        return LaunchResult(False, "launched_wine", f"{wine_bin} {exe_path}: {exc}")
    return LaunchResult(
        True,
        "launched_wine",
        f"{wine_bin} {exe_path} (anti-cheat may block actual gameplay)",
    )


def launch_protocol(region: str) -> LaunchResult:
    proto = HOYOPLAY_PROTOCOL_CN if region == "cn" else HOYOPLAY_PROTOCOL_GLOBAL
    try:
        opened = webbrowser.open(proto)
    except OSError as exc:
        return LaunchResult(False, "launched_protocol", f"{proto}: {exc}")
    if not opened:
        return LaunchResult(False, "launched_protocol", f"OS refused {proto}")
    return LaunchResult(True, "launched_protocol", proto)


def open_download_page(region: str) -> LaunchResult:
    url = DOWNLOAD_PAGE_CN if region == "cn" else DOWNLOAD_PAGE_GLOBAL
    try:
        opened = webbrowser.open(url)
    except OSError as exc:
        return LaunchResult(False, "opened_page", f"{url}: {exc}")
    if not opened:
        return LaunchResult(False, "opened_page", f"OS refused {url}")
    return LaunchResult(True, "opened_page", url)


def open_cloud(region: str) -> LaunchResult:
    """Open Cloud Genshin (CN only; global users get the download page)."""
    if region == "cn":
        url = CLOUD_PAGE_CN
        action = "opened_cloud"
    else:
        url = CLOUD_PAGE_GLOBAL
        action = "opened_page"
    try:
        opened = webbrowser.open(url)
    except OSError as exc:
        return LaunchResult(False, action, f"{url}: {exc}")
    if not opened:
        return LaunchResult(False, action, f"OS refused {url}")
    if region != "cn":
        return LaunchResult(
            True,
            action,
            f"{url} (no global cloud product; opened download page)",
        )
    return LaunchResult(True, action, url)


def download_installer(region: str, run_after: bool) -> LaunchResult:
    url = HOYOPLAY_INSTALLER_CN if region == "cn" else HOYOPLAY_INSTALLER_GLOBAL
    target_dir = Path(tempfile.gettempdir()) / "comfyui_genshin_start"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"HoYoPlay_install_{int(time.time())}.exe"

    try:
        req = urllib.request.Request(  # noqa: S310
            url,
            headers={"User-Agent": "comfyui-genshin-start/1.0"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
            if resp.status != 200:
                return LaunchResult(
                    False, "downloaded", f"HTTP {resp.status} from {url}",
                )
            with target.open("wb") as fh:
                shutil.copyfileobj(resp, fh)
    except (OSError, ValueError) as exc:
        page = open_download_page(region)
        return LaunchResult(
            page.ok,
            "downloaded",
            f"installer fetch failed ({exc}); opened download page instead",
        )

    if not run_after:
        return LaunchResult(True, "downloaded", str(target))

    if sys.platform != "win32":
        return LaunchResult(
            True,
            "downloaded",
            f"saved to {target}; cannot auto-run on {sys.platform}",
        )

    try:
        os.startfile(str(target))  # noqa: S606
    except OSError as exc:
        return LaunchResult(
            False,
            "downloaded",
            f"saved to {target} but failed to launch: {exc}",
        )
    return LaunchResult(True, "downloaded", f"running {target}")


# --- High-level orchestration --------------------------------------------


def perform(mode: str, region: str, dry_run: bool) -> LaunchResult:
    if dry_run:
        exe = find_game_exe()
        installed = f"installed at {exe}" if exe else "not installed"
        return LaunchResult(
            True, "skipped", f"dry-run on {sys.platform}; game {installed}",
        )

    if mode == "open_page":
        return open_download_page(region)

    if mode == "cloud":
        return open_cloud(region)

    if mode == "download_only":
        if sys.platform != "win32":
            page = open_download_page(region)
            return LaunchResult(
                page.ok,
                "downloaded",
                f"installer is Windows-only on {sys.platform}; opened page",
            )
        return download_installer(region, run_after=True)

    if mode == "launch_only":
        exe = find_game_exe()
        if exe is not None:
            return launch_exe(exe)
        if sys.platform == "win32" and _hoyoplay_protocol_registered():
            return launch_protocol(region)
        return LaunchResult(False, "launched_exe", "Genshin Impact not found")

    # mode == "auto"
    exe = find_game_exe()
    if exe is not None:
        return launch_exe(exe)

    if sys.platform == "win32":
        if _hoyoplay_protocol_registered():
            return launch_protocol(region)
        return download_installer(region, run_after=True)

    if region == "cn":
        return open_cloud(region)
    return open_download_page(region)
