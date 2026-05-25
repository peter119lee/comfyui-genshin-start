"""Test loading the node via ComfyUI's actual custom-node bootstrap.

Run with ComfyUI's bundled Python and point ``COMFYUI_DIR`` at your install::

    set COMFYUI_DIR=C:\\path\\to\\ComfyUI
    python comfyui_genshin_start/_test_in_comfyui.py
"""

from __future__ import annotations

import os
import sys

COMFYUI_DIR = os.environ.get("COMFYUI_DIR", r"C:\ComfyUI")
PACKAGE_NAME = "comfyui_genshin_start"


def main() -> int:
    if not os.path.isdir(COMFYUI_DIR):
        print(f"[FAIL] ComfyUI not found at {COMFYUI_DIR}")
        print("Set COMFYUI_DIR env var to your ComfyUI install path.")
        return 1

    sys.path.insert(0, COMFYUI_DIR)
    os.chdir(COMFYUI_DIR)

    print(f"[*] Python {sys.version.split()[0]} on {sys.platform}")
    print(f"[*] cwd = {os.getcwd()}")

    try:
        import nodes  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] could not import ComfyUI's nodes module: {exc!r}")
        return 2

    load_fn = getattr(nodes, "load_custom_node", None)
    if load_fn is None:
        print("[FAIL] nodes.load_custom_node missing; ComfyUI version too old?")
        return 3

    target = os.path.join(COMFYUI_DIR, "custom_nodes", PACKAGE_NAME)
    print(f"[*] loading {target}")
    import asyncio
    import inspect

    if inspect.iscoroutinefunction(load_fn):
        ok = asyncio.run(load_fn(target))
    else:
        ok = load_fn(target)
    print(f"[*] load_custom_node returned: {ok!r}")

    cls_map = getattr(nodes, "NODE_CLASS_MAPPINGS", {})
    name_map = getattr(nodes, "NODE_DISPLAY_NAME_MAPPINGS", {})

    if "GenshinImpactLauncher" not in cls_map:
        print("[FAIL] GenshinImpactLauncher not registered in NODE_CLASS_MAPPINGS")
        print(f"     keys present: {sorted(cls_map.keys())[:20]}")
        return 4

    cls = cls_map["GenshinImpactLauncher"]
    display = name_map.get("GenshinImpactLauncher")

    print(f"[OK] class registered: {cls}")
    print(f"[OK] display name: {display!r}")
    print(f"[OK] CATEGORY: {cls.CATEGORY}")
    print(f"[OK] RETURN_TYPES: {cls.RETURN_TYPES}")
    print(f"[OK] RETURN_NAMES: {cls.RETURN_NAMES}")

    inputs = cls.INPUT_TYPES()
    print(f"[OK] mode enum: {inputs['required']['mode'][0]}")
    print(f"[OK] region enum: {inputs['required']['region'][0]}")

    node = cls()
    result = node.execute(
        trigger=True,
        mode="auto",
        region="global",
        passthrough="dummy_image",
        dry_run=True,
    )
    print(f"[OK] dry-run execute() -> {result}")

    result2 = node.execute(trigger=False, mode="auto", region="global", passthrough=42)
    print(f"[OK] trigger-off execute() -> {result2}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
