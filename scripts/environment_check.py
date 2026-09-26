"""Environment and system tool diagnostic check for LOOM."""

from __future__ import annotations

import shutil
import sys


def check_environment() -> int:
    """Inspect local Python environment and external toolchain availability."""
    print("=" * 60)
    print("LOOM: Environment Diagnostic Check")
    print("=" * 60)

    # Python version check
    v = sys.version_info
    print(f"Python Version: {v.major}.{v.minor}.{v.micro}")
    if v.major == 3 and v.minor == 10:
        print("  -> Status: OK (Python 3.10 is the recommended baseline)")
    else:
        print(f"  -> Warning: Target is Python 3.10.11; active runtime is {v.major}.{v.minor}.{v.micro}")

    # Core dependencies check
    core_packages = [
        "yaml",
        "numpy",
        "cv2",
        "open3d",
        "trimesh",
        "pymeshlab",
        "scipy",
        "tqdm",
        "pytest",
    ]
    print("\nPython Dependencies:")
    missing_packages: list[str] = []
    for pkg in core_packages:
        try:
            __import__(pkg)
            print(f"  [OK]      {pkg}")
        except ImportError:
            print(f"  [MISSING] {pkg}")
            missing_packages.append(pkg)

    # External reconstruction tools check
    external_tools = [
        ("Meshroom CLI", "meshroom_batch"),
        ("AliceVision", "aliceVision_cameraInit"),
        ("COLMAP", "colmap"),
    ]
    print("\nExternal Photogrammetry Tools in PATH:")
    for name, binary in external_tools:
        path = shutil.which(binary)
        if path:
            print(f"  [FOUND]   {name} ({path})")
        else:
            print(f"  [MISSING] {name} ('{binary}' not found in system PATH)")

    print("\n" + "=" * 60)
    print("Diagnostic complete.")
    return 0


if __name__ == "__main__":
    sys.exit(check_environment())
