"""Video metadata extraction using OpenCV VideoCapture."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
import cv2

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VideoMetadata:
    """Metadata describing physical and stream properties of a video."""

    file_path: Path
    duration_seconds: float
    frame_count: int
    fps: float
    width: int
    height: int
    codec: str
    file_size_bytes: int


def _decode_fourcc(fourcc_int: int) -> str:
    """Decode integer FourCC code to 4-character string."""
    if fourcc_int <= 0:
        return "unknown"
    chars = []
    for i in range(4):
        c = chr((fourcc_int >> (8 * i)) & 0xFF)
        if c.isprintable() and not c.isspace():
            chars.append(c)
        else:
            chars.append("?")
    codec = "".join(chars)
    return codec if codec != "????" else "unknown"


def extract_video_metadata(video_path: Path) -> VideoMetadata:
    """Extract metadata from video container without loading frames into memory.

    Args:
        video_path: Path to video file.

    Returns:
        VideoMetadata descriptor.

    Raises:
        FileNotFoundError: If video file does not exist.
        ValueError: If video file is empty, unreadable, or contains invalid stream properties.
    """
    resolved_path = Path(video_path).resolve()
    if not resolved_path.is_file():
        raise FileNotFoundError(f"Video file not found: {resolved_path}")

    file_size = resolved_path.stat().st_size
    if file_size == 0:
        raise ValueError(f"Video file is empty (0 bytes): {resolved_path}")

    cap = cv2.VideoCapture(str(resolved_path))
    try:
        if not cap.isOpened():
            raise ValueError(
                f"Unable to open video '{resolved_path.name}'. "
                "The file exists but OpenCV could not initialize a readable video stream."
            )

        frame_count_raw = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        fps_raw = cap.get(cv2.CAP_PROP_FPS)
        width_raw = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
        height_raw = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
        fourcc_raw = int(cap.get(cv2.CAP_PROP_FOURCC))

        width = int(width_raw) if width_raw > 0 else 0
        height = int(height_raw) if height_raw > 0 else 0
        fps = float(fps_raw) if fps_raw > 0 else 0.0
        frame_count = int(frame_count_raw) if frame_count_raw > 0 else 0

        # Validate basic stream properties
        if width <= 0 or height <= 0:
            raise ValueError(
                f"Video '{resolved_path.name}' has invalid resolution ({width}x{height})."
            )

        if fps <= 0.0:
            raise ValueError(
                f"Video '{resolved_path.name}' reports invalid or zero framerate (FPS={fps})."
            )

        # Handle stream frame count if property was unavailable or 0
        if frame_count <= 0:
            # Check if at least first frame can be read
            ret, _ = cap.read()
            if not ret:
                raise ValueError(
                    f"Video '{resolved_path.name}' contains zero readable frames."
                )
            frame_count = 1
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

        duration = frame_count / fps if fps > 0 else 0.0
        codec = _decode_fourcc(fourcc_raw)

        logger.debug(
            "Extracted metadata for %s: %dx%d, %.2f fps, %d frames (%.2fs), codec: %s",
            resolved_path.name,
            width,
            height,
            fps,
            frame_count,
            duration,
            codec,
        )

        return VideoMetadata(
            file_path=resolved_path,
            duration_seconds=round(duration, 3),
            frame_count=frame_count,
            fps=round(fps, 3),
            width=width,
            height=height,
            codec=codec,
            file_size_bytes=file_size,
        )
    finally:
        cap.release()
