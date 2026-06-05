"""Applies project-local patches to installed third-party packages.
"""

import importlib.util
import shutil
from pathlib import Path

_PATCHES_DIR = Path(__file__).parent

# Patched fiel paths 
_PATCHES: dict[str, str] = {
    "spires_engine.py": "ontogpt.engines.spires_engine",
}


def apply_patches(verbose: bool = True) -> None:
    """Copy every patch file over the corresponding installed module file."""
    for patch_filename, module_path in _PATCHES.items():
        patch_src = _PATCHES_DIR / patch_filename

        if not patch_src.exists():
            print(f"[apply_patches] WARNING: patch file not found: {patch_src}")
            continue

        try:
            spec = importlib.util.find_spec(module_path)
        except ModuleNotFoundError:
            print(f"[apply_patches] WARNING: module not installed, skipping: {module_path}")
            continue

        if spec is None or spec.origin is None:
            print(f"[apply_patches] WARNING: cannot locate installed file for: {module_path}")
            continue

        target = Path(spec.origin)
        shutil.copy2(patch_src, target)
        if verbose:
            print(f"[apply_patches] Patched {target}")
