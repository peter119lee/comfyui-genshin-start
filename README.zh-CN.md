# comfyui-genshin-start

[English](README.md) | [简体中文](README.zh-CN.md)

ComfyUI 自定义节点：**「立刻下载并启动原神」**。

把整个文件夹丢到 `ComfyUI/custom_nodes/` 下，重启 ComfyUI，节点会出现在 `原神/启动器` 分类下，名称是「立刻下载并启动原神」。

## 行为（`mode = auto`）

1. 枚举 Windows 注册表 Uninstall hive（HKLM 64-bit + WOW6432Node + HKCU），用 `DisplayName` 匹配 `Genshin Impact` / `原神` / `YuanShen`，从 `InstallLocation` / `InstallPath` / `DisplayIcon` 提取候选安装目录
2. 枚举所有存在的盘符（A-Z），配上路径后缀 `HoYoPlay\games`、`Program Files\Genshin Impact`、`Games\Genshin Impact` 等扫描
3. 找到 `GenshinImpact.exe` 或 `YuanShen.exe` 就用 `os.startfile()` 启动（走 ShellExecute，会正常触发 UAC，跟开始菜单双击 .exe 一样）
4. 没找到但 HoYoPlay protocol handler 已注册，就用 `hyp-osel://` / `hyp-cnb://` 唤醒启动器
5. 完全没装就把官方 HoYoPlay 安装器抓到 `%TEMP%\comfyui_genshin_start\`，再 `os.startfile()` 跳出安装向导（不静默安装）
6. 安装器网址 404 时，自动退回打开官方下载页

## 安装

```bash
git clone https://github.com/peter119lee/comfyui-genshin-start.git \
    /path/to/ComfyUI/custom_nodes/comfyui_genshin_start
```

重启 ComfyUI。

## 输入

| 字段 | 类型 | 说明 |
|------|------|------|
| `trigger` | BOOLEAN | 总开关 |
| `mode` | enum | `auto` / `launch_only` / `download_only` / `open_page` / `cloud` |
| `region` | enum | `global` / `cn` |
| `passthrough` | ANY (optional) | 任何上游输出，原样传到下游 |
| `dry_run` | BOOLEAN (optional) | 只汇报检测状态，不做任何实际动作 |

## 输出

| 字段 | 类型 | 说明 |
|------|------|------|
| `passthrough` | ANY | 等于输入的 `passthrough` |
| `status` | STRING | 例如 `[OK] launched_exe: G:\HoYoPlay\...\GenshinImpact.exe` |

## 模式说明

- **`auto`** —— 完整链路：检测 → 启动 / 唤醒启动器 / 下载
- **`launch_only`** —— 只在找到游戏时启动，否则 `[FAIL]`
- **`download_only`** —— 强制重新下载 HoYoPlay 安装器
- **`open_page`** —— 只开官方下载页
- **`cloud`** —— 云·原神（仅 CN 区可用；全球版云·原神 2023 年已停服）

## 安全声明

- 只读注册表，不写
- 只从官方 `*.hoyoverse.com` / `*.mihoyo.com` 下载
- 不静默安装，安装器会跳 UI
- 节点本身不要求管理员权限（游戏自己的 UAC manifest 会触发提权）
- 设计上假设你在自己桌面跑 ComfyUI，不是共享/生产服务器

如果你在 headless / Docker 跑 ComfyUI 又开了这个节点，请用 `dry_run` 或 `mode = open_page`，否则 `webbrowser.open` 会因为没有 `DISPLAY` 报错。

## 为什么 `IS_CHANGED` 返回 `time.time()`

ComfyUI 默认会缓存节点输出，不强制每次重新执行的话，第二次按 Queue 不会重新启动原神。我们希望每次都触发，所以用时间戳当「永远变化」的标记。

## Linux / macOS 现实状况

原神**没有 Linux / macOS 原生客户端**，mhyprot2 反作弊是 Windows kernel driver，Wine / Proton / CrossOver / Whisky 都会被挡。

### Linux

- `auto` 先扫这些 Wine prefix：
  - `~/.wine/drive_c`
  - `~/.wine-genshin/drive_c`
  - `~/Games`（Lutris 默认）
  - `~/.var/app/com.usebottles.bottles/data/bottles/bottles`（Bottles flatpak）
  - `~/.local/share/lutris/runners/wine`
- 找到就 `wine GenshinImpact.exe`，但反作弊大概率挡你进入游戏
- 没找到时 `region=cn` 自动开云·原神，`region=global` 开下载页
- `download_only` 改开下载页（`.exe` 在 Wine 下跑不动）
- 真要在 Linux 上玩，只有 `mode=cloud` + `region=cn` 这一条路

### macOS

没有 Wine 扫描（CrossOver / Whisky 路径太杂）。`auto` 永远走 cloud（CN）/ open_page（global）。

### Headless / Docker

别按 trigger。或把 `dry_run` 打开，不会动任何东西。否则 `webbrowser.open()` 会因为没有 `DISPLAY` 报错。

## 诊断

节点检测不到你的安装时跑：

```bash
python comfyui_genshin_start/_diagnose.py
```

它会 dump 注册表探测、Uninstall hive 遍历、HoYoPlay URI handler 状态、文件系统扫描、深度搜索结果。

## License

MIT。见 [LICENSE](LICENSE)。
