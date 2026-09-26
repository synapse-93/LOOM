"""Synthetic video generator for deterministic testing of LOOM Phase 1."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
import cv2
import numpy as np


def create_synthetic_test_video(
    output_path: Path,
    num_frames: int = 60,
    fps: int = 30,
    width: int = 640,
    height: int = 480,
    include_blur: bool = True,
    include_dark: bool = True,
    include_bright: bool = True,
    include_redundant: bool = True,
) -> Path:
    """Generate a small, deterministic video with controlled quality variations.

    Frame distribution (for num_frames=60):
        - Frames 0..19: Normal sharp frames with moving geometric patterns
        - Frames 20..29: Blurry frames (Gaussian blur with large kernel)
        - Frames 30..39: Underexposed/dark frames
        - Frames 40..49: Overexposed/bright frames
        - Frames 50..59: Static/near-identical frames (redundant)

    Args:
        output_path: Destination path for .mp4 video.
        num_frames: Total number of frames to generate.
        fps: Video framerate.
        width: Video width.
        height: Video height.
        include_blur: Whether to include blurry frames.
        include_dark: Whether to include dark frames.
        include_bright: Whether to include bright frames.
        include_redundant: Whether to include redundant frames.

    Returns:
        Resolved Path to generated video.
    """
    out_file = Path(output_path).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)

    # Use standard mp4v FourCC codec for Windows compatibility
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(out_file), fourcc, float(fps), (width, height), isColor=True)

    if not writer.isOpened():
        raise RuntimeError(f"OpenCV VideoWriter failed to open for '{out_file}'")

    try:
        static_frame: np.ndarray | None = None

        for idx in range(num_frames):
            # Base sharp frame: neutral gray background with sharp high-contrast grid and geometric shapes
            frame = np.full((height, width, 3), 120, dtype=np.uint8)

            # Draw static grid
            for x in range(0, width, 40):
                cv2.line(frame, (x, 0), (x, height), (70, 70, 70), 1)
            for y in range(0, height, 40):
                cv2.line(frame, (0, y), (width, y), (70, 70, 70), 1)

            # Moving sharp rectangle and circle simulating orbital panning
            offset = int((idx / num_frames) * (width - 150))
            cv2.rectangle(frame, (50 + offset, 100), (150 + offset, 250), (220, 220, 220), -1)
            cv2.circle(frame, (100 + offset, 175), 35, (0, 0, 255), -1)

            # High-frequency text for sharpness
            cv2.putText(
                frame,
                f"LOOM_FRAME_{idx:04d}",
                (40, height - 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (255, 255, 255),
                2,
            )

            # Inject controlled variations based on frame index
            if include_blur and 20 <= idx < 30:
                # Apply heavy Gaussian blur simulating rapid camera motion
                frame = cv2.GaussianBlur(frame, (35, 35), 0)

            elif include_dark and 30 <= idx < 40:
                # Underexposed frame (brightness < 20)
                frame = (frame * 0.08).astype(np.uint8)

            elif include_bright and 40 <= idx < 50:
                # Overexposed frame (brightness > 240)
                frame = np.clip(frame.astype(np.int16) + 220, 0, 255).astype(np.uint8)

            elif include_redundant and 50 <= idx < 60:
                # Static identical frame
                if static_frame is None:
                    static_frame = frame.copy()
                frame = static_frame.copy()

            writer.write(frame)

    finally:
        writer.release()

    return out_file


def main(argv: list[str] | None = None) -> int:
    """CLI handler for synthetic test video generation."""
    parser = argparse.ArgumentParser(
        description="Generate synthetic test video for LOOM Phase 1 testing."
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("data/raw/synthetic_test.mp4"),
        help="Path for generated video file.",
    )
    parser.add_argument(
        "--frames",
        "-n",
        type=int,
        default=60,
        help="Number of frames (default: 60).",
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=30,
        help="Framerate in FPS (default: 30).",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=640,
        help="Frame width (default: 640).",
    )
    parser.add_argument(
        "--height",
        type=int,
        default=480,
        help="Frame height (default: 480).",
    )

    args = parser.parse_args(argv)

    out = create_synthetic_test_video(
        output_path=args.output,
        num_frames=args.frames,
        fps=args.fps,
        width=args.width,
        height=args.height,
    )
    print(f"Generated synthetic test video ({args.frames} frames @ {args.fps} fps): {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
