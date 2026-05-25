"""ComfyUI node definition for ``GenshinImpactLauncher``."""

from __future__ import annotations

from typing import Any

from .launcher import perform


class _AnyType(str):
    """Sentinel that compares equal to every other type string.

    ComfyUI uses string equality on socket types to validate links. By
    overriding ``__ne__`` we let this socket accept any upstream output.
    """

    def __ne__(self, other: object) -> bool:  # noqa: D401
        return False


ANY = _AnyType("*")


class GenshinImpactLauncher:
    """Detects, launches, or downloads Genshin Impact when executed.

    Wire ``trigger`` to a constant or a boolean upstream so you control when
    this fires. ``passthrough`` lets the node sit inline in any workflow
    without breaking the graph.
    """

    CATEGORY = "原神/启动器"
    FUNCTION = "execute"
    OUTPUT_NODE = True
    RETURN_TYPES = (ANY, "STRING")
    RETURN_NAMES = ("passthrough", "status")

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {
                "trigger": (
                    "BOOLEAN",
                    {
                        "default": True,
                        "label_on": "启动",
                        "label_off": "略过",
                    },
                ),
                "mode": (
                    ["auto", "launch_only", "download_only", "open_page", "cloud"],
                    {"default": "auto"},
                ),
                "region": (
                    ["global", "cn"],
                    {"default": "global"},
                ),
            },
            "optional": {
                "passthrough": (ANY,),
                "dry_run": (
                    "BOOLEAN",
                    {
                        "default": False,
                        "label_on": "dry-run",
                        "label_off": "execute",
                    },
                ),
            },
        }

    @classmethod
    def IS_CHANGED(cls, *_args: Any, **_kwargs: Any) -> float:
        # Force re-execution each prompt run; otherwise ComfyUI caches the
        # node and the user's "启动" button never fires twice in a row.
        import time

        return time.time()

    def execute(
        self,
        trigger: bool,
        mode: str,
        region: str,
        passthrough: Any = None,
        dry_run: bool = False,
    ) -> tuple[Any, str]:
        if not trigger:
            return passthrough, "[OK] skipped: trigger is off"

        result = perform(mode=mode, region=region, dry_run=dry_run)
        return passthrough, result.to_status()
