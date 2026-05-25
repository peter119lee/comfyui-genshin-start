"""ComfyUI custom node: 立刻下载并启动原神.

Exposes NODE_CLASS_MAPPINGS / NODE_DISPLAY_NAME_MAPPINGS so ComfyUI can
auto-discover the node when this folder is dropped into custom_nodes/.
"""

from .genshin_node import GenshinImpactLauncher

NODE_CLASS_MAPPINGS = {
    "GenshinImpactLauncher": GenshinImpactLauncher,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "GenshinImpactLauncher": "立刻下载并启动原神",
}

WEB_DIRECTORY = None

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
