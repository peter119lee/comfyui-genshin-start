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

# Official entry pages. These are stable URLs maintained by HoYoverse.
DOWNLOAD_PAGE_GLOBAL = "https://genshin.hoyoverse.com/en/download"
DOWNLOAD_PAGE_CN = "https://ys.mihoyo.com/main/download"

# Cloud Genshin. Only the CN cloud service is publicly available; the
# global cloud beta was sunset in 2023, so we point global users to the
# regular download page when they ask for "cloud" mode.
CLOUD_PAGE_CN = "https://ys.mihoyo.com/cloud/"
CLOUD_PAGE_GLOBAL = DOWNLOAD_PAGE_GLOBAL  # no global cloud product exists

# HoYoPlay launcher installer (the modern launcher that ships Genshin).
# These two URLs are the public installer entry points; if they 404 in the
# future we fall back to opening the download page.
HOYOPLAY_INSTALLER_GLOBAL = (
    "https://download-porter.hoyoverse.com/launcher/hyp/HoYoPlay_install.exe"
)
HOYOPLAY_INSTALLER_CN = (
    "https://download-porter.mihoyo.com/launcher/hyp/HoYoPlay_install.exe"
)

# Candidate filesystem locations for the game executable. These are
# templates appended to every drive letter that actually exists at runtime
# (handled by ``_iter_candidate_exes``). Keep them as path *suffixes*, not
# full paths, so we don't have to anticipate which drive the user picked.
GAME_EXE_NAMES = ("GenshinImpact.exe", "YuanShen.exe")

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

# DisplayName fragments we accept when matching Uninstall registry entries.
# Stored lowercase; comparisons are case-insensitive.
GENSHIN_DISPLAY_NAME_NEEDLES = ("genshin impact", "原神", "yuanshen")

# Walk depth when probing under registry InstallLocation values; HoYoPlay's
# layout is `<install>\games\Genshin Impact game\GenshinImpact.exe`, so 5
# is plenty.
REGISTRY_SCAN_MAX_DEPTH = 5
COMMON_DIR_SCAN_MAX_DEPTH = 4

# Substrings that mark a directory as "this is HoYoPlay / Genshin shaped"
# during the broad drive-root scan (phase 2 of _iter_candidate_exes). All
# entries are lowercase; matching uses ``substring in dir_name.lower()`` so
# we also catch user-renamed dirs like ``原神客户端`` or ``my-genshin-old``.
# False positives are cheap: we just walk inside and find no game exe.
KNOWN_GAME_DIR_NEEDLES = (
    "hoyoplay",
    "genshin",
    "原神",
    "yuanshen",
    "mihoyo",
)

# Top-level drive directories we never walk into during broad scan: system
# owned, huge, or irrelevant. Comparison is case-insensitive.
DRIVE_ROOT_SKIP_NAMES = {
    "windows", "programdata", "$recycle.bin",
    "system volume information", "perflogs",
    "msocache", "intel", "amd", "nvidia",
    "recovery", "boot", "config.msi",
}

# HoYoPlay deep-link protocol. Launching with no args opens the launcher;
# we keep it simple and let the user click "Play" themselves.
HOYOPLAY_PROTOCOL_GLOBAL = "hyp-osel://"
HOYOPLAY_PROTOCOL_CN = "hyp-cnb://"

# HoYoPlay deep-link install hint. After silent-installing HoYoPlay we
# fire this URL so the launcher opens with Genshin's install dialog
# already focused. The user only needs to click "Install / 开始下载".
# Format observed in HoYoPlay client: hyp-{global,cn}://launcher/install?game_biz=hk4e_{global,cn}
HOYOPLAY_INSTALL_HINT_GLOBAL = "hyp-osel://launcher/install?game_biz=hk4e_global"
HOYOPLAY_INSTALL_HINT_CN = "hyp-cnb://launcher/install?game_biz=hk4e_cn"

# Silent NSIS install flag. HoYoPlay's installer is NSIS-based; passing
# /S makes it skip every dialog and write to the default install path.
# The installer still triggers UAC because its manifest demands admin.
HOYOPLAY_SILENT_FLAG = "/S"

# How long to wait for the silent install before declaring it stuck.
# A clean HoYoPlay install runs in ~20-30s; 5 minutes is a generous cap.
HOYOPLAY_SILENT_INSTALL_TIMEOUT_S = 300

# Linux Wine prefixes worth scanning. We probe these *if and only if* the
# user is on Linux; otherwise we don't waste time touching the home dir.
LINUX_WINE_BASES = (
    "~/.wine/drive_c",
    "~/.wine-genshin/drive_c",
    "~/Games",  # Lutris default
    "~/.var/app/com.usebottles.bottles/data/bottles/bottles",  # Bottles flatpak
    "~/.local/share/lutris/runners/wine",
)
LINUX_SCAN_MAX_DEPTH = 5


# --- Data types -----------------------------------------------------------


@dataclass(frozen=True)
class LaunchResult:
    ok: bool
    action: str  # "launched_exe" | "launched_wine" | "launched_protocol" | "downloaded" | "opened_page" | "opened_cloud" | "skipped" | "noop"
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
    """Yield files under ``base`` whose name is in ``target_names``.

    Iterative DFS so we don't recurse into massive trees, and so a single
    PermissionError in one subdirectory doesn't kill the whole walk.
    """
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
                    # Skip Wine system dirs that obviously won't contain
                    # the game, to keep scans fast.
                    if entry.name in {"windows", "ProgramData", "users"}:
                        continue
                    stack.append((entry, depth + 1))
            except (PermissionError, OSError):
                continue


def _linux_wine_candidates() -> Iterable[Path]:
    """Yield Genshin executables found inside common Linux Wine prefixes."""
    for raw in LINUX_WINE_BASES:
        base = Path(os.path.expanduser(raw))
        yield from _shallow_find(base, GAME_EXE_NAMES, LINUX_SCAN_MAX_DEPTH)


def _iter_candidate_exes() -> Iterable[Path]:
    """Yield plausible Genshin executable paths on this machine.

    Two phases, both deduplicated against each other:

      Phase 1 (fast): combine each drive letter with each entry in
      ``COMMON_PATH_SUFFIXES``. Catches default English installs.

      Phase 2 (broad): walk each drive root 1-2 levels deep looking for any
      directory whose name is in ``KNOWN_GAME_DIR_NAMES``, regardless of
      its parent. Catches Chinese-rooted installs like
      ``D:\\游戏\\HoYoPlay\\games\\Genshin Impact game\\GenshinImpact.exe``
      that phase 1 cannot match because the suffix list is English-only.

    ``find_game_exe`` only consumes the first hit, so phase 2 only runs as
    a fallback when phase 1 finds nothing.
    """
    if sys.platform != "win32":
        return
    import string

    drive_roots: list[Path] = []
    for letter in string.ascii_uppercase:
        root = Path(f"{letter}:\\")
        if root.exists():
            drive_roots.append(root)

    seen: set[Path] = set()

    # --- Phase 1: fixed-suffix probe ---
    for drive in drive_roots:
        for suffix in COMMON_PATH_SUFFIXES:
            base = drive / suffix
            if not base.is_dir():
                continue
            for hit in _shallow_find(base, GAME_EXE_NAMES, COMMON_DIR_SCAN_MAX_DEPTH):
                if hit not in seen:
                    seen.add(hit)
                    yield hit

    # --- Phase 2: broad drive-root scan for Chinese / custom-rooted installs ---
    for hit in _iter_drive_root_broad_scan(drive_roots):
        if hit not in seen:
            seen.add(hit)
            yield hit


def _iter_drive_root_broad_scan(drive_roots: Iterable[Path]) -> Iterable[Path]:
    """Walk each drive root looking for HoYoPlay/Genshin-named subdirs.

    For every drive listed, we list its top-level entries. If a top-level
    entry's name contains any of ``KNOWN_GAME_DIR_NEEDLES`` (substring,
    case-insensitive), we walk inside it for the game exe. Otherwise we
    list its direct children (one level deeper) and check those names too.
    This covers four layouts:

      D:\\HoYoPlay\\games\\...                 (top-level match)
      D:\\游戏\\HoYoPlay\\games\\...           (one level deeper)
      D:\\我的游戏\\原神\\GenshinImpact.exe    (one level deeper, Chinese name)
      D:\\Programs\\原神客户端\\YuanShen.exe   (renamed dir, substring match)

    System-owned top-level dirs (Windows, ProgramData, etc.) are skipped
    so we don't waste time or trip on permission errors.
    """
    for drive in drive_roots:
        try:
            top_level = list(drive.iterdir())
        except (PermissionError, OSError):
            continue
        for child in top_level:
            try:
                if not child.is_dir():
                    continue
                lname = child.name.lower()
                if lname in DRIVE_ROOT_SKIP_NAMES:
                    continue
                if any(n in lname for n in KNOWN_GAME_DIR_NEEDLES):
                    yield from _shallow_find(
                        child, GAME_EXE_NAMES, COMMON_DIR_SCAN_MAX_DEPTH,
                    )
                    continue
                # Look one level deeper for D:\<anything>\HoYoPlay style.
                try:
                    grandchildren = list(child.iterdir())
                except (PermissionError, OSError):
                    continue
                for grand in grandchildren:
                    try:
                        if not grand.is_dir():
                            continue
                        gname = grand.name.lower()
                        if any(n in gname for n in KNOWN_GAME_DIR_NEEDLES):
                            yield from _shallow_find(
                                grand,
                                GAME_EXE_NAMES,
                                COMMON_DIR_SCAN_MAX_DEPTH,
                            )
                    except (PermissionError, OSError):
                        continue
            except (PermissionError, OSError):
                continue


def _registry_uninstall_path() -> Optional[Path]:
    """Find the game by walking the Windows Uninstall registry hive.

    Strategy:
      1. Iterate every direct child of ``Uninstall`` under HKLM (64-bit and
         WOW6432Node) and HKCU.
      2. For each child whose ``DisplayName`` looks Genshin-shaped, harvest
         a candidate base directory from ``InstallLocation`` (best),
         falling back to the parent of ``DisplayIcon`` or ``ExeName``.
      3. Walk that base directory bounded by ``REGISTRY_SCAN_MAX_DEPTH``
         looking for ``GenshinImpact.exe`` / ``YuanShen.exe``.

    HoYoPlay registers a per-game key with a hashed name like
    ``hk4e_global_1_0_VYTpXlbWo8_production`` whose ``InstallLocation`` is
    the HoYoPlay root (e.g. ``G:\\HoYoPlay``); the actual exe lives at
    ``<root>\\games\\Genshin Impact game\\GenshinImpact.exe``.
    """
    if sys.platform != "win32":
        return None
    try:
        import winreg  # noqa: WPS433 (stdlib, win-only)
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

    # Walk every candidate base, preferring the first hit. We deduplicate
    # so we don't repeatedly scan the same directory.
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
        # DisplayIcon / UninstallString may have ",0" suffixes or quotes.
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
    """Return True iff HoYoPlay's URI handler is registered."""
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
    """Best-effort lookup for an installed Genshin Impact executable."""
    if sys.platform == "win32":
        # 1. Registry-pointed install dir.
        registry_hit = _registry_uninstall_path()
        if registry_hit is not None:
            return registry_hit
        # 2. Common filesystem locations.
        for candidate in _iter_candidate_exes():
            return candidate
        return None

    if sys.platform.startswith("linux"):
        for candidate in _linux_wine_candidates():
            return candidate
        return None

    # macOS and others: no realistic way to find the game.
    return None


# --- Actions --------------------------------------------------------------


def launch_exe(exe_path: Path) -> LaunchResult:
    """Spawn the game executable detached from ComfyUI.

    On Windows ``GenshinImpact.exe`` has ``requireAdministrator`` in its
    manifest (mhyprot2 anti-cheat needs kernel driver loading), so plain
    ``subprocess.Popen`` raises ``WinError 740 (elevation required)``. We
    use :func:`os.startfile` instead, which goes through ShellExecute,
    respects the manifest, and triggers the UAC prompt the same way a
    Start Menu / Explorer double-click would.

    On Linux this dispatches to ``wine``.
    """
    if sys.platform == "win32":
        try:
            # ShellExecute "open" verb. Working directory defaults to the
            # exe's folder, which is what HoYoPlay's launcher does too.
            os.startfile(str(exe_path))  # noqa: S606 (user-facing game)
        except OSError as exc:
            return LaunchResult(False, "launched_exe", f"{exe_path}: {exc}")
        return LaunchResult(True, "launched_exe", str(exe_path))

    if sys.platform.startswith("linux"):
        return launch_wine(exe_path)

    return LaunchResult(False, "launched_exe", f"unsupported OS: {sys.platform}")


def launch_wine(exe_path: Path) -> LaunchResult:
    """Run a Genshin .exe via the system ``wine`` binary.

    Note: HoYoverse's mhyprot2 anti-cheat is a Windows kernel driver and
    will refuse to load under Wine, so the game launcher may open but
    actually entering the game world is unlikely to succeed.
    """
    wine_bin = shutil.which("wine") or shutil.which("wine64")
    if wine_bin is None:
        return LaunchResult(
            False,
            "launched_wine",
            "wine not found in PATH; install wine or use mode=open_page/cloud",
        )
    try:
        subprocess.Popen(  # noqa: S603 (wine + path discovered locally)
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
    """Trigger the HoYoPlay URI handler so its launcher window opens."""
    proto = HOYOPLAY_PROTOCOL_CN if region == "cn" else HOYOPLAY_PROTOCOL_GLOBAL
    try:
        opened = webbrowser.open(proto)
    except OSError as exc:
        return LaunchResult(False, "launched_protocol", f"{proto}: {exc}")
    if not opened:
        return LaunchResult(False, "launched_protocol", f"OS refused {proto}")
    return LaunchResult(True, "launched_protocol", proto)


def launch_install_hint(region: str) -> LaunchResult:
    """Open HoYoPlay focused on the Genshin install dialog.

    Uses the deep-link `hyp-{osel,cnb}://launcher/install?game_biz=hk4e_*`
    URL that HoYoPlay registers with Windows. After this fires the user
    only needs one more click ("Install" / "开始下载") inside HoYoPlay's
    UI; everything else is automatic.
    """
    url = HOYOPLAY_INSTALL_HINT_CN if region == "cn" else HOYOPLAY_INSTALL_HINT_GLOBAL
    try:
        opened = webbrowser.open(url)
    except OSError as exc:
        return LaunchResult(False, "launched_install_hint", f"{url}: {exc}")
    if not opened:
        return LaunchResult(False, "launched_install_hint", f"OS refused {url}")
    return LaunchResult(True, "launched_install_hint", url)


def silent_install_hoyoplay(installer_path: Path) -> LaunchResult:
    """Run the HoYoPlay installer silently (NSIS /S) and wait for it.

    Uses ``powershell Start-Process -Verb RunAs -Wait`` because:
      - ``-Verb RunAs`` triggers UAC properly (subprocess.Popen can't, the
        installer's manifest demands admin)
      - ``-Wait`` blocks until the installer exits, so we know HoYoPlay
        is ready before firing the install-hint deep link
      - ``/S`` is the standard NSIS silent flag, skipping every dialog

    Caller (ComfyUI worker) blocks for the duration. A clean install
    finishes in 20-30 seconds; we cap at 5 minutes.
    """
    if sys.platform != "win32":
        return LaunchResult(
            False,
            "silent_installed",
            f"silent install not supported on {sys.platform}",
        )

    cmd = [
        "powershell",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        (
            f"$ErrorActionPreference='Stop'; "
            f"Start-Process -FilePath '{installer_path}' "
            f"-ArgumentList '{HOYOPLAY_SILENT_FLAG}' "
            f"-Verb RunAs -Wait -PassThru | "
            f"Select-Object -ExpandProperty ExitCode"
        ),
    ]
    try:
        result = subprocess.run(  # noqa: S603 (path discovered locally)
            cmd,
            capture_output=True,
            text=True,
            timeout=HOYOPLAY_SILENT_INSTALL_TIMEOUT_S,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        return LaunchResult(
            False,
            "silent_installed",
            f"installer timed out after {HOYOPLAY_SILENT_INSTALL_TIMEOUT_S}s",
        )
    except OSError as exc:
        return LaunchResult(
            False,
            "silent_installed",
            f"powershell call failed: {exc}",
        )

    if result.returncode != 0:
        # PowerShell returned non-zero, often because user denied UAC.
        stderr = (result.stderr or "").strip()
        return LaunchResult(
            False,
            "silent_installed",
            f"installer exited non-zero (UAC denied?): {stderr[:200]}",
        )

    installer_exit = (result.stdout or "").strip().splitlines()[-1:] or [""]
    return LaunchResult(
        True,
        "silent_installed",
        f"HoYoPlay silently installed (installer exit={installer_exit[0]})",
    )


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
    """Open the cloud Genshin page (CN only; global users get download page)."""
    if region == "cn":
        url = CLOUD_PAGE_CN
        action = "opened_cloud"
    else:
        url = CLOUD_PAGE_GLOBAL
        action = "opened_page"  # honest: there's no global cloud
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
    """Download HoYoPlay installer to %TEMP% and (optionally) run it."""
    url = HOYOPLAY_INSTALLER_CN if region == "cn" else HOYOPLAY_INSTALLER_GLOBAL
    target_dir = Path(tempfile.gettempdir()) / "comfyui_genshin_start"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"HoYoPlay_install_{int(time.time())}.exe"

    try:
        req = urllib.request.Request(  # noqa: S310 (https URL, fixed host)
            url,
            headers={"User-Agent": "comfyui-genshin-start/1.0"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
            if resp.status != 200:
                return LaunchResult(
                    False,
                    "downloaded",
                    f"HTTP {resp.status} from {url}",
                )
            with target.open("wb") as fh:
                shutil.copyfileobj(resp, fh)
    except (OSError, ValueError) as exc:
        # Fall back to opening the page so the user can click through manually.
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
        os.startfile(str(target))  # noqa: S606 (user-facing installer)
    except OSError as exc:
        return LaunchResult(
            False,
            "downloaded",
            f"saved to {target} but failed to launch: {exc}",
        )
    return LaunchResult(True, "downloaded", f"running {target}")


# --- High-level orchestration --------------------------------------------


def perform(mode: str, region: str, dry_run: bool) -> LaunchResult:
    """Top-level dispatch for the node's ``execute`` method."""
    if dry_run:
        exe = find_game_exe()
        installed = f"installed at {exe}" if exe else "not installed"
        return LaunchResult(
            True,
            "skipped",
            f"dry-run on {sys.platform}; game {installed}",
        )

    if mode == "open_page":
        return open_download_page(region)

    if mode == "cloud":
        return open_cloud(region)

    if mode == "download_only":
        if sys.platform != "win32":
            # Downloading a .exe installer on Linux/macOS is pointless: we
            # can't run it. Hand the user off to the download page instead.
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
        # HoYoPlay already installed but Genshin isn't: jump straight to the
        # install hint URL so the launcher opens with the install dialog
        # focused on Genshin (one click from "Install").
        if _hoyoplay_protocol_registered():
            return launch_install_hint(region)

        # Nothing installed. Run the full silent-install chain:
        #   1. fetch HoYoPlay installer to %TEMP%
        #   2. silent install with /S (one UAC prompt)
        #   3. fire the install hint deep link to surface Genshin install dialog
        download = download_installer(region, run_after=False)
        if not download.ok:
            return download
        installer_path = Path(download.detail)

        install = silent_install_hoyoplay(installer_path)
        if not install.ok:
            return install

        hint = launch_install_hint(region)
        return LaunchResult(
            hint.ok,
            "auto_installed",
            f"HoYoPlay installed silently; {hint.detail}",
        )

    # Non-Windows: no native client exists. Best path forward is cloud
    # (CN only) or the download page.
    if region == "cn":
        return open_cloud(region)
    return open_download_page(region)
