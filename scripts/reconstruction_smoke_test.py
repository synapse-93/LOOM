"""Manual diagnostic and smoke test script for Meshroom / AliceVision integration."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from loom.reconstruction.meshroom import MeshroomAdapter
from loom.reconstruction.models import ReconstructionJobConfig
from loom.utils.logging import setup_logging


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify Meshroom host availability and run integration smoke test."
    )
    parser.add_argument(
        "--meshroom-path",
        type=Path,
        default=None,
        help="Explicit path to meshroom_batch executable.",
    )
    parser.add_argument(
        "--frames-dir",
        type=Path,
        default=None,
        help="Directory containing test frames (.png/.jpg) to reconstruct.",
    )
    parser.add_argument(
        "--workspace-dir",
        type=Path,
        default=Path("outputs/smoke_test_recon"),
        help="Working directory for reconstruction output.",
    )
    args = parser.parse_args(argv)
    setup_logging(level="INFO")

    print("\n" + "=" * 65)
    print("LOOM: Meshroom / AliceVision Environment Diagnostic")
    print("=" * 65)

    adapter = MeshroomAdapter(binary_path=args.meshroom_path)
    bin_path = adapter.resolve_binary(args.meshroom_path)

    if bin_path is None:
        print("[STATUS] MESHROOM NOT AVAILABLE ON HOST")
        print("\nDiagnostic Details:")
        print("  * 'meshroom_batch' was not detected in system PATH.")
        print("  * No valid binary was found at configured location.")
        print("\nInstallation Instructions:")
        print("  1. Download Meshroom from: https://alicevision.org/#meshroom")
        print("  2. Extract the archive (e.g. to C:\\Tools\\Meshroom-2023.3.0\\).")
        print("  3. Add the extracted folder containing 'meshroom_batch.exe' to PATH,")
        print("     OR set environment variable 'MESHROOM_PATH',")
        print("     OR pass '--meshroom-path <path_to_meshroom_batch>' to the CLI.")
        print("=" * 65 + "\n")
        return 0

    print(f"[STATUS] MESHROOM AVAILABLE: {bin_path}")
    print("=" * 65)

    if args.frames_dir is None:
        print("\n[INFO] No '--frames-dir' provided. Skipping live reconstruction test.")
        print("To run a live reconstruction, supply a folder of 20-60 keyframes:")
        print("  python scripts/reconstruction_smoke_test.py --frames-dir outputs/runs/<run_id>/frames/selected")
        print("=" * 65 + "\n")
        return 0

    frames = sorted(
        [
            p
            for p in args.frames_dir.iterdir()
            if p.suffix.lower() in {".png", ".jpg", ".jpeg"}
        ]
    )
    if not frames:
        print(f"[ERROR] No valid image frames found in {args.frames_dir}")
        return 1

    print(f"\nFound {len(frames)} frames. Starting test reconstruction...")
    cfg = ReconstructionJobConfig(
        workspace_dir=args.workspace_dir,
        binary_path=bin_path,
        timeout_seconds=1800,
    )

    try:
        result = adapter.reconstruct(frames, cfg)
        print("\n" + "=" * 65)
        print("LOOM: Live Reconstruction Smoke Test Result")
        print("=" * 65)
        print(f"Success:             {result.success}")
        print(f"Backend:             {result.backend}")
        print(f"Mesh Output:         {result.mesh_path}")
        print(f"Point Cloud:         {result.point_cloud_path}")
        print(f"Registered Cameras:  {result.registered_cameras_count} / {result.input_frames_count}")
        print(f"Registration Ratio:  {result.registration_ratio}")
        print(f"Execution Time:      {result.execution_time_seconds:.2f}s")
        if result.error_message:
            print(f"Error Message:       {result.error_message}")
        print("=" * 65 + "\n")
        return 0 if result.success else 1
    except Exception as exc:
        print(f"\n[ERROR] Reconstruction failed: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
