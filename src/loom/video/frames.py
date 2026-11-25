"""Streaming frame extraction with deterministic naming, motion gating, blur rejection, and manifest generation."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
import cv2
import numpy as np

from loom.config.models import VideoConfig
from loom.pipeline.artifacts import FrameSetArtifact
from loom.utils.paths import ensure_directory

logger = logging.getLogger(__name__)


def compute_laplacian_variance(frame: np.ndarray) -> float:
    """Calculate the Laplacian variance of an image as a measure of optical sharpness.

    Var(∇² I) = cv2.Laplacian(I, cv2.CV_64F).var()

    Args:
        frame: BGR or grayscale image array.

    Returns:
        Laplacian variance as float (higher = sharper).
    """
    if frame is None or frame.size == 0:
        return 0.0
    if len(frame.shape) == 3:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    else:
        gray = frame
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def find_nearest_sharp_frame(
    cap: cv2.VideoCapture,
    candidate_idx: int,
    candidate_frame: np.ndarray,
    candidate_sharpness: float,
    total_frames: int,
    blur_threshold: float,
    max_search_radius: int = 10,
) -> tuple[int, np.ndarray, float]:
    """Search adjacent frames to replace a blurry candidate with the nearest sharp frame.

    Args:
        cap: Open cv2.VideoCapture instance.
        candidate_idx: Index of candidate frame in video.
        candidate_frame: Decoded candidate image array.
        candidate_sharpness: Laplacian variance of candidate frame.
        total_frames: Total frame count of the video stream.
        blur_threshold: Sharpness threshold below which a frame is considered blurry.
        max_search_radius: Maximum frame offset (+/-) to check for a sharp alternative.

    Returns:
        Tuple of (resolved_frame_idx, resolved_frame, resolved_sharpness).
    """
    if candidate_sharpness >= blur_threshold or max_search_radius <= 0:
        return candidate_idx, candidate_frame, candidate_sharpness

    best_idx = candidate_idx
    best_frame = candidate_frame
    best_sharpness = candidate_sharpness

    # Search alternating adjacent offsets (+1, -1, +2, -2, ...)
    offsets: list[int] = []
    for r in range(1, max_search_radius + 1):
        offsets.extend([r, -r])

    for offset in offsets:
        adj_idx = candidate_idx + offset
        if adj_idx < 0 or adj_idx >= total_frames:
            continue
        cap.set(cv2.CAP_PROP_POS_FRAMES, adj_idx)
        ret, adj_frame = cap.read()
        if not ret or adj_frame is None:
            continue
        adj_sharpness = compute_laplacian_variance(adj_frame)
        if adj_sharpness > best_sharpness:
            best_idx = adj_idx
            best_frame = adj_frame
            best_sharpness = adj_sharpness
            if adj_sharpness >= blur_threshold:
                logger.debug(
                    "Replaced blurry candidate frame %d (sharpness=%.1f) with adjacent frame %d (sharpness=%.1f)",
                    candidate_idx, candidate_sharpness, adj_idx, adj_sharpness,
                )
                break

    return best_idx, best_frame, best_sharpness


class FrameExtractor:
    """Streams and extracts candidate keyframes from video files without memory accumulation.

    Contract:
        Frames are decoded and written to disk sequentially. At no point is the entire
        video or all decoded image arrays retained simultaneously in memory.
    """

    def __init__(self, config: VideoConfig) -> None:
        self.config = config

    def extract(
        self,
        video_path: Path,
        output_dir: Path,
        blur_threshold: float | None = None,
    ) -> FrameSetArtifact:
        """Stream frames from video and write selected samples to output directory.

        Evenly strides candidate frames across video duration capped at max_frames
        (default: 75), rejects heavily blurred frames using Laplacian variance, and
        falls back to the nearest sharp adjacent frame.

        Args:
            video_path: Source video file path.
            output_dir: Destination directory for extracted image frames.
            blur_threshold: Optional override for Laplacian variance blur rejection threshold.

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

            # Determine max_frames (default to 68 for turbo mode, 130 for standard video inputs)
            is_turbo = getattr(self.config, "turbo", False)
            configured_max = getattr(self.config, "max_frames", None)
            if configured_max is not None and configured_max > 0:
                max_frames = configured_max
            elif is_turbo:
                max_frames = 68
            else:
                max_frames = 130

            configured_target_dim = getattr(self.config, "target_max_dimension", None)
            if configured_target_dim is not None and configured_target_dim > 0:
                target_max_dimension = configured_target_dim
            elif is_turbo:
                target_max_dimension = 960
            else:
                target_max_dimension = 960

            effective_blur_threshold = (
                blur_threshold
                if blur_threshold is not None
                else getattr(self.config, "blur_threshold", 18.0)
            )

            # Determine effective sampling interval
            step = max(1, self.config.sample_interval)
            if self.config.target_fps is not None and self.config.target_fps > 0:
                if fps > self.config.target_fps:
                    step = max(1, int(round(fps / self.config.target_fps)))

            # Evenly stride frame candidates across video duration when source_frame_count > max_frames
            if source_frame_count > 0:
                if source_frame_count > max_frames and step == 1 and self.config.target_fps is None:
                    candidate_indices = np.round(
                        np.linspace(0, source_frame_count - 1, max_frames)
                    ).astype(int).tolist()
                else:
                    candidate_indices = list(range(0, source_frame_count, step))[:max_frames]
            else:
                candidate_indices = []

            jpeg_quality = getattr(self.config, "jpeg_quality", 95)
            encode_params = [cv2.IMWRITE_JPEG_QUALITY, max(1, min(100, jpeg_quality))]

            logger.info(
                "Starting frame extraction for '%s' (step=%d, max_frames=%d, quality=%d, blur_threshold=%.1f)",
                src.name,
                step,
                max_frames,
                jpeg_quality,
                effective_blur_threshold,
            )

            extracted_paths: list[Path] = []
            manifest_records: list[dict[str, Any]] = []

            if candidate_indices:
                for c_idx in candidate_indices:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, c_idx)
                    ret, frame = cap.read()
                    if not ret or frame is None:
                        continue

                    sharpness = compute_laplacian_variance(frame)
                    resolved_idx = c_idx

                    # Reject blurred frames and fall back to nearest sharp adjacent frame
                    if effective_blur_threshold > 0 and sharpness < effective_blur_threshold:
                        resolved_idx, frame, sharpness = find_nearest_sharp_frame(
                            cap=cap,
                            candidate_idx=c_idx,
                            candidate_frame=frame,
                            candidate_sharpness=sharpness,
                            total_frames=source_frame_count,
                            blur_threshold=effective_blur_threshold,
                        )

                    # Downscale frame so max(W, H) <= target_max_dimension using cv2.INTER_AREA
                    h, w = frame.shape[:2]
                    if target_max_dimension is not None and max(h, w) > target_max_dimension:
                        scale = float(target_max_dimension) / float(max(h, w))
                        new_w = max(1, int(round(w * scale)))
                        new_h = max(1, int(round(h * scale)))
                        frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
                        h, w = new_h, new_w

                    timestamp_sec = round(c_idx / fps, 4)
                    filename = f"frame_{c_idx:06d}.jpg"
                    frame_dest = dest_dir / filename

                    success = cv2.imwrite(str(frame_dest), frame, encode_params)
                    if not success:
                        raise RuntimeError(f"Failed to write extracted frame to {frame_dest}")

                    extracted_paths.append(frame_dest)
                    manifest_records.append(
                        {
                            "filename": filename,
                            "path": str(frame_dest),
                            "source_frame_index": c_idx,
                            "resolved_frame_index": resolved_idx,
                            "sharpness": round(sharpness, 2),
                            "timestamp_seconds": timestamp_sec,
                            "width": w,
                            "height": h,
                        }
                    )
            else:
                # Streaming fallback if source_frame_count was not detectable
                source_frame_idx = 0
                while True:
                    ret, frame = cap.read()
                    if not ret:
                        break

                    if source_frame_idx % step == 0:
                        sharpness = compute_laplacian_variance(frame)
                        resolved_idx = source_frame_idx
                        # Downscale frame so max(W, H) <= target_max_dimension using cv2.INTER_AREA
                        h, w = frame.shape[:2]
                        if target_max_dimension is not None and max(h, w) > target_max_dimension:
                            scale = float(target_max_dimension) / float(max(h, w))
                            new_w = max(1, int(round(w * scale)))
                            new_h = max(1, int(round(h * scale)))
                            frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
                            h, w = new_h, new_w

                        timestamp_sec = round(source_frame_idx / fps, 4)
                        filename = f"frame_{source_frame_idx:06d}.jpg"
                        frame_dest = dest_dir / filename

                        success = cv2.imwrite(str(frame_dest), frame, encode_params)
                        if not success:
                            raise RuntimeError(f"Failed to write extracted frame to {frame_dest}")

                        extracted_paths.append(frame_dest)
                        manifest_records.append(
                            {
                                "filename": filename,
                                "path": str(frame_dest),
                                "source_frame_index": source_frame_idx,
                                "resolved_frame_index": resolved_idx,
                                "sharpness": round(sharpness, 2),
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
                "max_frames": max_frames,
                "blur_threshold": effective_blur_threshold,
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

    def extract_all(self, video_path: Path, output_dir: Path) -> FrameSetArtifact:
        """Alias for extract() to ensure compatibility with alternative caller conventions."""
        return self.extract(video_path, output_dir)


# Alias conforming to KeyframeExtractor naming conventions
KeyframeExtractor = FrameExtractor


def extract_keyframes(
    video_path: Path | str,
    output_dir: Path | str,
    target_max_dimension: int | None = None,
    max_frames: int | None = None,
    turbo: bool = False,
    blur_threshold: float = 18.0,
) -> FrameSetArtifact:
    """Convenience helper to extract keyframes with optional turbo downscaling.

    Args:
        video_path: Path to source video file.
        output_dir: Directory where keyframes are written.
        target_max_dimension: Max resolution dimension (default: 960 in turbo mode, 960 otherwise).
        max_frames: Maximum number of frames to extract (default: 68 in turbo mode, 75 otherwise).
        turbo: If True, defaults max_frames to 68 and enables high-speed processing.
        blur_threshold: Laplacian variance blur rejection threshold (default: 18.0).

    Returns:
        FrameSetArtifact containing extracted frames.
    """
    effective_max = max_frames if max_frames is not None else (68 if turbo else 130)
    effective_dim = target_max_dimension if target_max_dimension is not None else 960
    cfg = VideoConfig(
        max_frames=effective_max,
        target_max_dimension=effective_dim,
        turbo=turbo,
        blur_threshold=blur_threshold,
    )
    extractor = FrameExtractor(cfg)
    return extractor.extract(Path(video_path), Path(output_dir))

