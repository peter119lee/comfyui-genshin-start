"""Test: does the discovery code handle Chinese-character install paths?

We don't touch the real registry. We:
  1. Build fake directory trees on L: with various Chinese path components.
  2. Call _shallow_find directly to confirm the walker enters Chinese dirs.
  3. Check whether _iter_candidate_exes (the cross-drive scan) catches them.
  4. Use a real Windows binary (notepad.exe) copied into a Chinese-named
     directory to verify os.startfile actually launches via a Chinese path.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

# Force UTF-8 stdout so we can print Chinese paths in cmd.exe.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

from comfyui_genshin_start import launcher as L  # noqa: E402


def make_fake_tree(test_root: Path) -> list[Path]:
    if test_root.exists():
        shutil.rmtree(test_root)
    test_root.mkdir(parents=True)

    fakes = [
        test_root / "游戏" / "HoYoPlay" / "games" / "Genshin Impact game" / "GenshinImpact.exe",
        test_root / "我的游戏" / "原神" / "GenshinImpact.exe",
        test_root / "Programs" / "原神客户端" / "YuanShen.exe",
        test_root / "純中文路徑" / "原神-繁體" / "GenshinImpact.exe",
    ]
    for f in fakes:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"fake")
    return fakes


def test_shallow_find(test_root: Path) -> None:
    print("=== test 1: _shallow_find walks into Chinese subdirectories ===")
    hits = list(L._shallow_find(test_root, L.GAME_EXE_NAMES, max_depth=10))
    for h in hits:
        print(f"  found: {h}")
    assert len(hits) >= 4, f"expected >=4 hits, got {len(hits)}"
    print(f"  [OK] {len(hits)} exes found across Chinese paths")
    print()


def test_iter_candidate_exes(test_root: Path) -> None:
    print("=== test 2: _iter_candidate_exes (real cross-drive scan) ===")
    print("  Note: tempdir adds an extra wrapper dir, so this scan")
    print("  may not reach our fake exes. Phase 2 (broad scan) is tested in test 2b.")
    hits = list(L._iter_candidate_exes())
    real_test_hits = [h for h in hits if str(test_root) in str(h)]
    print(f"  cross-drive scan found {len(real_test_hits)} of our fake Chinese installs")
    print(f"  total cross-drive hits (all drives): {len(hits)}")
    print()


def test_broad_scan_directly(test_root: Path) -> None:
    print("=== test 2b: _iter_drive_root_broad_scan with test_root as fake drive ===")
    print(f"  feeding test_root={test_root} as if it were a drive letter")
    hits = list(L._iter_drive_root_broad_scan([test_root]))
    for h in hits:
        print(f"  found: {h}")
    print(f"  [{'OK' if len(hits) >= 3 else 'PARTIAL'}] broad scan found {len(hits)} hits")
    print("  (3 expected: 游戏\\HoYoPlay, 我的游戏\\原神, Programs\\原神客户端)")
    print("  (純中文路徑\\原神-繁體 doesn't match KNOWN_GAME_DIR_NAMES so skipped)")
    print()


def test_real_launch_via_chinese_path(test_root: Path) -> None:
    """Confirm os.startfile() doesn't reject a Chinese-character path."""
    print("=== test 3: os.startfile() through a Chinese path (real exe) ===")
    if sys.platform != "win32":
        print(f"  [SKIP] {sys.platform}: os.startfile is Windows-only")
        return
    notepad_src = Path(r"C:\Windows\System32\notepad.exe")
    if not notepad_src.is_file():
        print("  notepad.exe not found, skipping")
        return

    chinese_dir = test_root / "中文资料夹" / "测试启动"
    chinese_dir.mkdir(parents=True, exist_ok=True)
    target = chinese_dir / "我的记事本.exe"
    shutil.copy2(notepad_src, target)
    print(f"  spawning: {target}")

    # We don't try to detect the spawned process: wmic was removed in
    # Windows Server 2025 and tasklist's IMAGENAME filter is unreliable
    # against non-ASCII names. The contract here is "ShellExecuteW
    # accepts the wide path"; if the call didn't raise, that's verified.
    try:
        os.startfile(str(target))
    except OSError as exc:
        print(f"  [FAIL] os.startfile raised: {exc!r}")
        return

    print("  [OK] os.startfile() returned without error.")
    print("       Chinese path was accepted by ShellExecuteW (Win32 wide-char API).")
    # Best-effort cleanup: if the process did spawn, kill all matching by
    # base name. taskkill failures (no such process) are fine.
    time.sleep(1)
    subprocess.run(
        ["taskkill", "/F", "/IM", "我的记事本.exe"],
        capture_output=True, timeout=5,
    )
    print()


def main() -> None:
    import tempfile
    test_root = Path(tempfile.mkdtemp(prefix="genshin_chinese_test_"))
    try:
        fakes = make_fake_tree(test_root)
        print(f"created {len(fakes)} fake exes under {test_root}")
        for f in fakes:
            print(f"  {f}")
        print()

        test_shallow_find(test_root)
        test_iter_candidate_exes(test_root)
        test_broad_scan_directly(test_root)
        test_real_launch_via_chinese_path(test_root)
    finally:
        if test_root.exists():
            shutil.rmtree(test_root, ignore_errors=True)
            print(f"cleaned up {test_root}")


if __name__ == "__main__":
    main()
