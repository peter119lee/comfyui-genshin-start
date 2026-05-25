# Immediately Download and Launch Genshin Impact

English | [简体中文](README.md)

![好想玩原神](icon.jpg)

> 啊😲？云朵☁️😄，哒↘哒↗哒↘哒↗哒↘，好想玩原神😨，云☁️原神😙，当当当当当😊，看精彩纷纷👍🎊😆，云☁️原神😄，呜呜呜呜呜，好想玩原神😭😭😭云☁️原神，朋友已就位😊😃😆，一起玩原神，云☁️原神！啊啊啊啊啊😙，好想玩原神😙云☁️原神，哈哈哈哈哈🤣🤣🤣，一起玩原神，云☁️原神，好好好想，🤩想玩玩原神😋网页云端，低功耗不失真😌， WiFi网线🥰，都可以60帧😍，来来来来👏，进入云☁️原神

ComfyUI custom node. Launches Genshin Impact every time you hit Queue. **Auto-installs it if missing.**

## Install

```bash
git clone https://github.com/peter119lee/comfyui-genshin-start.git \
    /path/to/ComfyUI/custom_nodes/comfyui_genshin_start
```

Restart ComfyUI. Node shows up under `原神/启动器`.

## Usage

Wire it anywhere into your workflow. `trigger=ON` + press Queue → Genshin launches. Done.

## What `auto` mode does

```
Genshin found      → launch it
HoYoPlay installed → fire install-hint deep link, opens Genshin install dialog
Nothing installed  → download HoYoPlay installer → silent /S install
                     (one UAC click) → fire install-hint deep link
```

The third path is the real auto-install: PowerShell `Start-Process -Verb RunAs -Wait` with NSIS `/S` flag. One UAC prompt, everything else is silent. After HoYoPlay installs, the node fires `hyp-osel://launcher/install?game_biz=hk4e_global` so HoYoPlay opens with the Genshin install dialog already focused. You only click "Install" once and wait for the 70 GB download.

> True zero-interaction install is not possible: HoYoPlay has no public CLI for headless game downloads. From "press Queue" to "Genshin on disk" takes a minimum of 2 clicks: UAC consent + "Install" button inside HoYoPlay.

## Platform behavior

- **Windows** — see the auto flow above
- **Linux** — no Wine-installed Genshin? **Opens Cloud Genshin** at `ys.mihoyo.com/cloud/`
  > 哒↘哒↗哒↘哒↗哒↘，好想玩原神😨，云☁️原神😙
- **macOS** — same as Linux

## License

MIT.
