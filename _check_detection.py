"""Quick verification that find_game_exe() locates an installed Genshin."""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from comfyui_genshin_start import launcher as L

print("find_game_exe ->", L.find_game_exe())
print("via registry  ->", L._registry_uninstall_path())
print("via fs scan   ->", next(iter(L._iter_candidate_exes()), None))
print("dry-run auto  ->", L.perform(mode="auto", region="global", dry_run=True))
