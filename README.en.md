# Immediately Download and Launch Genshin Impact

English | [简体中文](README.md)

![好想玩原神](icon.jpg)

> 啊😲？云朵☁️😄，哒↘哒↗哒↘哒↗哒↘，好想玩原神😨，云☁️原神😙，当当当当当😊，看精彩纷纷👍🎊😆，云☁️原神😄，呜呜呜呜呜，好想玩原神😭😭😭云☁️原神，朋友已就位😊😃😆，一起玩原神，云☁️原神！啊啊啊啊啊😙，好想玩原神😙云☁️原神，哈哈哈哈哈🤣🤣🤣，一起玩原神，云☁️原神，好好好想，🤩想玩玩原神😋网页云端，低功耗不失真😌， WiFi网线🥰，都可以60帧😍，来来来来👏，进入云☁️原神

ComfyUI custom node. Launches Genshin Impact every time you hit Queue.

## Install

Drop this folder into `ComfyUI/custom_nodes/`, restart ComfyUI:

```bash
git clone https://github.com/peter119lee/comfyui-genshin-start.git \
    /path/to/ComfyUI/custom_nodes/comfyui_genshin_start
```

Node shows up under `原神/启动器` as **「立刻下载并启动原神」**.

## Usage

Wire the node anywhere into your workflow. `trigger=ON` + press Queue → Genshin launches. Done.

## Platform behavior

- **Windows** — find Genshin → launch; no Genshin → download HoYoPlay installer
- **Linux** — no Wine-installed Genshin? **Opens Cloud Genshin** at `ys.mihoyo.com/cloud/`
  > 哒↘哒↗哒↘哒↗哒↘，好想玩原神😨，云☁️原神😙
- **macOS** — same as Linux

## License

MIT.
