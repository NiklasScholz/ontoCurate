"""Applies our patches to ontoGPT"""

import importlib.util
import shutil
from pathlib import Path

_PATCHES_DIR = Path(__file__).parent

# Maps patch filename
_PATCHES: dict[str, tuple[str, str]] = {
    "spires_engine.py": ("ontogpt", "engines/spires_engine.py"),
    "llm_client.py": ("ontogpt", "clients/llm_client.py"),
}


def apply_patches(verbose: bool = True) -> None:
    """Copy every patch file over the corresponding installed module file."""
    for patch_filename, (top_level_pkg, rel_path) in _PATCHES.items():
        patch_src = _PATCHES_DIR / patch_filename

        if not patch_src.exists():
            print(f"[apply_patches] WARNING: patch file not found: {patch_src}")
            continue

        try:
            spec = importlib.util.find_spec(top_level_pkg)
        except ModuleNotFoundError:
            print(
                f"[apply_patches] WARNING: package not installed, skipping: {top_level_pkg}"
            )
            continue

        if spec is None or not spec.submodule_search_locations:
            print(f"[apply_patches] WARNING: cannot locate package: {top_level_pkg}")
            continue

        pkg_root = Path(next(iter(spec.submodule_search_locations)))
        target = pkg_root / rel_path

        if not target.exists():
            print(f"[apply_patches] WARNING: target file not found: {target}")
            continue

        shutil.copy2(patch_src, target)
        if verbose:
            print(f"[apply_patches] Patched {target}")
