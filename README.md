# 立刻下载并启动原神

[English](README.en.md) | 简体中文

![好想玩原神](icon.jpg)

> 啊😲？云朵☁️😄，哒↘哒↗哒↘哒↗哒↘，好想玩原神😨，云☁️原神😙，当当当当当😊，看精彩纷纷👍🎊😆，云☁️原神😄，呜呜呜呜呜，好想玩原神😭😭😭云☁️原神，朋友已就位😊😃😆，一起玩原神，云☁️原神！啊啊啊啊啊😙，好想玩原神😙云☁️原神，哈哈哈哈哈🤣🤣🤣，一起玩原神，云☁️原神，好好好想，🤩想玩玩原神😋网页云端，低功耗不失真😌， WiFi网线🥰，都可以60帧😍，来来来来👏，进入云☁️原神
>
> #啊😲？云朵☁️😄，哒↘哒↗哒↘哒↗哒↘，好想玩原神😨，云☁️原神😙，当当当当当😊，看精彩纷纷👍🎊😆，云☁️原神😄，呜呜呜呜呜，好想玩原神😭😭😭云☁️原神，朋友已就位😊😃😆，一起玩原神，云☁️原神！啊啊啊啊啊😙，好想玩原神😙云☁️原神，哈哈哈哈哈🤣🤣🤣，一起玩原神，云☁️原神，好好好想，🤩想玩玩原神😋网页云端，低功耗不失真😌， WiFi网线🥰，都可以60帧😍，来来来来👏，进入云☁️原神

ComfyUI 自定义节点。每次按 Queue 顺便启动原神。**没装也帮你自动装。**

## 安装

```bash
git clone https://github.com/peter119lee/comfyui-genshin-start.git \
    /path/to/ComfyUI/custom_nodes/comfyui_genshin_start
```

重启 ComfyUI，节点出现在 `原神/启动器` 分类下。

## 用法

接到工作流任意位置。`trigger=ON` + 按 Queue → 启动原神。完事。

## auto 模式干嘛

```
找到原神 → 直接启动
没找到、HoYoPlay 已装 → 跳到 HoYoPlay 的 Genshin 安装对话框
完全没装 → 下载 HoYoPlay 安装器 → 静默安装（一次 UAC 同意）→ 自动跳安装对话框
```

第三步**真·自动安装**：用 PowerShell `Start-Process -Verb RunAs -Wait` 配 NSIS `/S`（silent），系统跳一次 UAC 你点同意，剩下全自动。HoYoPlay 装完节点马上 fire `hyp-osel://launcher/install?game_biz=hk4e_global` 让 HoYoPlay 直接打开 Genshin 安装窗。你只剩点「开始下载」一下、然后等 70 GB 下载完。

> 真·零互动安装做不到——HoYoPlay 没公开的 CLI 让人 headless 下载游戏本体。从「点 Queue」到「Genshin 在你硬盘上」之间最少要点 2 下：UAC 同意 + HoYoPlay 里的「开始下载」。

## 平台行为

- **Windows** — 见上面的 auto 流程
- **Linux** — 没本地 Wine 装的原神？**直接打开云原神** `ys.mihoyo.com/cloud/`
  > 哒↘哒↗哒↘哒↗哒↘，好想玩原神😨，云☁️原神😙
- **macOS** — 同 Linux

## License

MIT。
