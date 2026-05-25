# comfyui-genshin-start

[English](README.md) | [简体中文](README.zh-CN.md)

ComfyUI custom node: **"Immediately download and launch Genshin Impact"**.

Drop this folder into your `ComfyUI/custom_nodes/`, restart ComfyUI, and the node appears under `原神/启动器` as `立刻下载并启动原神`.

## Behavior (`mode = auto`)

1. Walk Windows Uninstall registry hive (HKLM 64-bit + WOW6432Node + HKCU), match by `DisplayName` against `Genshin Impact` / `原神` / `YuanShen`, harvest install dirs from `InstallLocation` / `InstallPath` / `DisplayIcon`.
2. Enumerate every existing drive letter (A-Z) and probe path suffixes like `HoYoPlay\games`, `Program Files\Genshin Impact`, `Games\Genshin Impact`.
3. If `GenshinImpact.exe` / `YuanShen.exe` is found, launch via `os.startfile()` (uses ShellExecute, triggers UAC the same way a Start Menu double-click does).
4. If not found but the HoYoPlay URI handler is registered, fire `hyp-osel://` / `hyp-cnb://` to wake the launcher.
5. If nothing is installed, download the official HoYoPlay installer to `%TEMP%\comfyui_genshin_start\` and pop the install wizard via `os.startfile()`. No silent install.
6. If the installer URL 404s, fall back to opening the official download page.

## Installation

```bash
git clone https://github.com/peter119lee/comfyui-genshin-start.git \
    /path/to/ComfyUI/custom_nodes/comfyui_genshin_start
```

Restart ComfyUI.

## Inputs

| Field | Type | Description |
|-------|------|-------------|
| `trigger` | BOOLEAN | On/off switch |
| `mode` | enum | `auto` / `launch_only` / `download_only` / `open_page` / `cloud` |
| `region` | enum | `global` / `cn` |
| `passthrough` | ANY (optional) | Upstream output passed unchanged downstream |
| `dry_run` | BOOLEAN (optional) | Report install state only, no side effects |

## Outputs

| Field | Type | Description |
|-------|------|-------------|
| `passthrough` | ANY | Same as input |
| `status` | STRING | E.g. `[OK] launched_exe: G:\HoYoPlay\...\GenshinImpact.exe` |

## Modes

- **`auto`** — full chain: detect → launch / wake launcher / download
- **`launch_only`** — only launch if the game is found, else `[FAIL]`
- **`download_only`** — always re-download HoYoPlay installer
- **`open_page`** — open the official download page
- **`cloud`** — Cloud Genshin (CN only; global cloud was discontinued in 2023)

## Safety

- Read-only registry access
- Only downloads from official `*.hoyoverse.com` / `*.mihoyo.com`
- No silent install — installer pops a UI wizard
- No admin elevation requested by the node itself; the game's own UAC manifest handles elevation
- Designed for desktop ComfyUI use, not shared / production servers

If you run ComfyUI headless or in Docker, set `dry_run = true` or use `mode = open_page`. Otherwise `webbrowser.open` will fail without `DISPLAY`.

## Why `IS_CHANGED` returns `time.time()`

ComfyUI caches node outputs by default. Without forced re-execution a second Queue press would not re-launch Genshin. Timestamp acts as an "always changed" sentinel.

## Linux / macOS reality

Genshin Impact has **no native Linux or macOS client**, and mhyprot2 is a Windows kernel driver, so Wine / Proton / CrossOver / Whisky all hit the anti-cheat wall.

### Linux

- `auto` first probes Wine prefixes:
  - `~/.wine/drive_c`
  - `~/.wine-genshin/drive_c`
  - `~/Games` (Lutris default)
  - `~/.var/app/com.usebottles.bottles/data/bottles/bottles` (Bottles flatpak)
  - `~/.local/share/lutris/runners/wine`
- If found, runs `wine GenshinImpact.exe`. Anti-cheat will probably block actual gameplay.
- If not found and `region=cn`, opens Cloud Genshin (`ys.mihoyo.com/cloud/`).
- If not found and `region=global`, opens the download page.
- `download_only` opens the download page (the `.exe` installer is useless under Wine).
- `mode = cloud` + `region=cn` is the only path that actually plays on Linux.

### macOS

No Wine scan (CrossOver / Whisky paths vary). `auto` always falls through to cloud (CN) or open_page (global).

### Headless / Docker

Don't trigger this node. Use `dry_run` if you must run it; otherwise `webbrowser.open()` errors without `DISPLAY`.

## Diagnostics

If detection misses your install, run:

```bash
python comfyui_genshin_start/_diagnose.py
```

It dumps registry probes, Uninstall hive walk, HoYoPlay URI handler status, filesystem scan, and a deep search for the game exe.

## License

MIT. See [LICENSE](LICENSE).
