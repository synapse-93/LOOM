"""Streaming frame extraction with deterministic naming and manifest generation."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
import cv2

from loom.config.models import VideoConfig
from loom.pipeline.artifacts import FrameSetArtifact
from loom.utils.paths import ensure_directory

logger = logging.getLogger(__name__)


class FrameExtractor:
    """Streams and extracts candidate keyframes from video files without memory accumulation.

    Contract:
        Frames are decoded and written to disk sequentially. At no point is the entire
        video or all decoded image arrays retained simultaneously in memory.
    """

    def __init__(self, config: VideoConfig) -> None:
        self.config = config

    def extract(self, video_path: Path, output_dir: Path) -> FrameSetArtifact:
        """Stream frames from video and write selected samples to output directory.

        Args:
            video_path: Source video file path.
            output_dir: Destination directory for extracted image frames.

        Returns:
            FrameSetArtifact containing list of extracted frame paths and metadata.

        Raises:
            FileNotFoundError: If video file does not exist.
            ValueError: If video cannot be decoded or produces 0 frames.
            RuntimeError: If frame writing fails.
        """
        src = Path(video_path).resolve()
        if not src.is_file():
            raise FileNotFoundError(f"Source video not found for extraction: {src}")

        dest_dir = ensure_directory(output_dir)

        cap = cv2.VideoCapture(str(src))
        try:
            if not cap.isOpened():
                raise ValueError(
                    f"Unable to open video '{src.name}'. "
                    "The file exists but OpenCV could not initialize a readable video stream."
                )

            fps = cap.get(cv2.CAP_PROP_FPS)
            fps = float(fps) if fps > 0 else 30.0
            source_frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

            # Determine effective sampling interval
            step = max(1, self.config.sample_interval)
            if self.config.target_fps is not None and self.config.target_fps > 0:
                if fps > self.config.target_fps:
                    step = max(1, int(round(fps / self.config.target_fps)))

            max_frames = self.config.max_frames
            jpeg_quality = getattr(self.config, "jpeg_quality", 95)
            encode_params = [cv2.IMWRITE_JPEG_QUALITY, max(1, min(100, jpeg_quality))]

            logger.info(
                "Starting frame extraction for '%s' (step=%d, max_frames=%d, quality=%d)",
                src.name,
                step,
                max_frames,
                jpeg_quality,
            )

            extracted_paths: list[Path] = []
            manifest_records: list[dict[str, Any]] = []
            source_frame_idx = 0

            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                if source_frame_idx % step == 0:
                    timestamp_sec = round(source_frame_idx / fps, 4)
                    filename = f"frame_{source_frame_idx:06d}.jpg"
                    frame_dest = dest_dir / filename

                    success = cv2.imwrite(str(frame_dest), frame, encode_params)
                    if not success:
                        raise RuntimeError(f"Failed to write extracted frame to {frame_dest}")

                    h, w = frame.shape[:2]
                    extracted_paths.append(frame_dest)
                    manifest_records.append(
                        {
                            "filename": filename,
                            "path": str(frame_dest),
                            "source_frame_index": source_frame_idx,
                            "timestamp_seconds": timestamp_sec,
                            "width": w,
                            "height": h,
                        }
                    )

                    if len(extracted_paths) >= max_frames:
                        logger.info("Reached maximum requested frames (%d)", max_frames)
                        break

                source_frame_idx += 1

            if not extracted_paths:
                raise ValueError(
                    f"Frame extraction produced 0 usable frames from video '{src.name}'."
                )

            # Generate machine-readable JSON manifest
            manifest_path = dest_dir / "manifest.json"
            manifest_data = {
                "source_video": str(src),
                "fps": round(fps, 3),
                "source_frame_count": source_frame_count,
                "sample_interval": step,
                "total_extracted": len(extracted_paths),
                "jpeg_quality": jpeg_quality,
                "frames": manifest_records,
            }
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest_data, f, indent=2)

            logger.info(
                "Extracted %d frames from '%s' into %s",
                len(extracted_paths),
                src.name,
                dest_dir,
            )

            return FrameSetArtifact(
                stage_name="frame_extraction",
                frames_dir=dest_dir,
                frame_paths=extracted_paths,
                total_extracted=len(extracted_paths),
                metadata={
                    "manifest_path": str(manifest_path),
                    "fps": fps,
                    "sample_step": step,
                    "source_frame_count": source_frame_count,
                },
            )
        finally:
            cap.release()
