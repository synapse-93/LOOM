"""Memory-safe semantic foreground masking and visual audit for undistorted COLMAP views."""

from __future__ import annotations

import gc
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

import cv2
import numpy as np

from loom.utils.paths import ensure_directory

logger = logging.getLogger(__name__)

SUPPORTED_IMAGE_EXTENSIONS: frozenset[str] = frozenset({".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"})
CONTOUR_COLOR_BGR: tuple[int, int, int] = (129, 185, 16)  # #10B981 emerald green
EXCLUDED_BORDER_BGR: tuple[int, int, int] = (48, 48, 239)  # crisp red


@dataclass(frozen=True)
class ExcludedViewInfo:
    """Metadata describing a frame rejected by the view-hygiene gate."""

    filename: str
    coverage_ratio: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "filename": self.filename,
            "coverage_ratio": round(float(self.coverage_ratio), 5),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class MaskingResult:
    """Summary of semantic foreground masking, view hygiene, and visual contact sheet."""

    masks_dir: Path
    mask_paths: list[Path]
    coverage_ratios: dict[str, float]
    model_name: str = "isnet-general-use"
    valid_views: list[str] = field(default_factory=list)
    excluded_views: list[dict[str, Any]] = field(default_factory=list)
    median_coverage: float = 0.0
    contact_sheet_path: Optional[Path] = None
    warning_frames: list[str] = field(default_factory=list)
    total_frames: int = 0

    def to_manifest_dict(self) -> dict[str, Any]:
        return {
            "model_name": self.model_name,
            "total_frames": self.total_frames,
            "valid_views": list(self.valid_views),
            "excluded_views": list(self.excluded_views),
            "median_coverage": round(float(self.median_coverage), 5),
            "contact_sheet_path": str(self.contact_sheet_path) if self.contact_sheet_path else None,
        }


def postprocess_alpha_mask(
    alpha: np.ndarray,
    *,
    alpha_threshold: int = 128,
    morph_kernel_size: int = 3,
    min_area_ratio: float = 0.01,
) -> np.ndarray:
    """Clean a raw alpha matte into a single-object binary foreground mask (0 / 255).

    Steps:
        1. Threshold alpha values >= ``alpha_threshold`` to binary ``{0, 255}``.
        2. Apply light morphological open then close (``morph_kernel_size``) to remove speckles.
        3. Retain the primary connected component closest to the image center while
           discarding disconnected islands smaller than ``min_area_ratio`` of image area.
    """
    arr = np.asarray(alpha)
    if arr.ndim == 3:
        arr = arr[:, :, -1]
    if arr.ndim != 2 or arr.size == 0:
        raise ValueError(f"Expected 2D non-empty alpha matte, got shape {arr.shape}")

    if np.issubdtype(arr.dtype, np.floating):
        max_val = float(np.nanmax(arr))
        scale = 255.0 if max_val <= 1.0 + 1e-6 else 1.0
        alpha_u8 = np.clip(np.nan_to_num(arr, nan=0.0) * scale, 0.0, 255.0).astype(np.uint8)
    else:
        alpha_u8 = np.clip(arr, 0, 255).astype(np.uint8)

    binary = np.where(alpha_u8 >= int(alpha_threshold), np.uint8(255), np.uint8(0))

    if morph_kernel_size >= 3:
        kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (morph_kernel_size, morph_kernel_size)
        )
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(binary, connectivity=8)
    if num_labels <= 1:
        return np.zeros_like(binary, dtype=np.uint8)

    height, width = binary.shape
    min_area_px = max(1, int(round(min_area_ratio * height * width)))
    center = np.array([width / 2.0, height / 2.0], dtype=np.float64)

    qualifying: list[tuple[float, int, int]] = []
    for label_id in range(1, num_labels):
        area = int(stats[label_id, cv2.CC_STAT_AREA])
        dist = float(np.linalg.norm(centroids[label_id] - center))
        if area >= min_area_px:
            qualifying.append((dist, -area, label_id))

    if not qualifying:
        return np.zeros_like(binary, dtype=np.uint8)

    qualifying.sort()
    selected_label = qualifying[0][2]
    return np.where(labels == selected_label, np.uint8(255), np.uint8(0))


def build_mask_contact_sheet(
    images_dir: Path | str,
    masks_dir: Path | str,
    ordered_filenames: Sequence[str],
    coverage_ratios: dict[str, float],
    excluded_map: dict[str, dict[str, Any]],
    output_path: Path | str,
    *,
    grid_rows: int = 4,
    grid_cols: int = 4,
    tile_width: int = 320,
    tile_height: int = 240,
) -> Path:
    """Render a 4x4 visual mask audit contact sheet with green contours and red excluded flags.

    Selects up to ``grid_rows * grid_cols`` (16) tiles, prioritizing up to 4 excluded views
    (if present) plus evenly spaced valid views across the orbit.
    """
    src_dir = Path(images_dir).resolve()
    m_dir = Path(masks_dir).resolve()
    out_file = Path(output_path).resolve()
    ensure_directory(out_file.parent)

    max_tiles = grid_rows * grid_cols
    excluded_names = [fn for fn in ordered_filenames if fn in excluded_map]
    valid_names = [fn for fn in ordered_filenames if fn not in excluded_map]

    # Prioritize up to 4 excluded views so failure modes are immediately inspectable
    chosen_excluded = excluded_names[:4]
    remaining_slots = max(0, max_tiles - len(chosen_excluded))

    if len(valid_names) <= remaining_slots:
        chosen_valid = list(valid_names)
    elif remaining_slots > 0:
        indices = np.linspace(0, len(valid_names) - 1, remaining_slots, dtype=int)
        chosen_valid = [valid_names[int(i)] for i in indices]
    else:
        chosen_valid = []

    selected_set = set(chosen_excluded) | set(chosen_valid)
    selected = [fn for fn in ordered_filenames if fn in selected_set][:max_tiles]

    canvas = np.full((grid_rows * tile_height, grid_cols * tile_width, 3), 18, dtype=np.uint8)

    for tile_idx, fname in enumerate(selected):
        r = tile_idx // grid_cols
        c = tile_idx % grid_cols
        y0, y1 = r * tile_height, (r + 1) * tile_height
        x0, x1 = c * tile_width, (c + 1) * tile_width

        img_bgr = cv2.imread(str(src_dir / fname), cv2.IMREAD_COLOR)
        mask_path = m_dir / f"{Path(fname).stem}.png"
        mask_gray = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE) if mask_path.is_file() else None

        if img_bgr is None:
            tile = np.full((tile_height, tile_width, 3), 30, dtype=np.uint8)
        else:
            tile = cv2.resize(img_bgr, (tile_width, tile_height), interpolation=cv2.INTER_AREA)

        cov = float(coverage_ratios.get(fname, 0.0))
        is_excluded = fname in excluded_map

        if mask_gray is not None and mask_gray.size > 0:
            mask_resized = cv2.resize(mask_gray, (tile_width, tile_height), interpolation=cv2.INTER_NEAREST)
            mask_bin = (mask_resized > 127).astype(np.uint8) * 255
            if not is_excluded:
                # Subtle green tint inside mask + crisp #10B981 contour
                fg = mask_bin > 0
                tint = np.zeros_like(tile)
                tint[:, :] = CONTOUR_COLOR_BGR
                tile[fg] = cv2.addWeighted(tile[fg], 0.85, tint[fg], 0.15, 0)
                contours, _ = cv2.findContours(mask_bin, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                cv2.drawContours(tile, contours, -1, CONTOUR_COLOR_BGR, 2)

        # Dark header strip for readable top-left telemetry
        cv2.rectangle(tile, (0, 0), (tile_width, 28), (16, 18, 22), -1)
        header_text = f"{fname} ({cov * 100.0:.1f}%)"
        cv2.putText(
            tile,
            header_text,
            (8, 19),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.46,
            (236, 238, 242),
            1,
            cv2.LINE_AA,
        )

        if is_excluded:
            cv2.rectangle(tile, (2, 2), (tile_width - 3, tile_height - 3), EXCLUDED_BORDER_BGR, 4)
            badge = f"EXCLUDED ({cov * 100.0:.1f}%)"
            cv2.rectangle(tile, (8, tile_height - 32), (210, tile_height - 8), (24, 24, 160), -1)
            cv2.putText(
                tile,
                badge,
                (14, tile_height - 15),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.50,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )

        canvas[y0:y1, x0:x1] = tile

    cv2.imwrite(str(out_file), canvas, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
    logger.info("[MASK] Saved %dx%d visual audit contact sheet -> %s", grid_rows, grid_cols, out_file)
    return out_file


class ForegroundMasker:
    """Generates clean binary foreground masks on undistorted COLMAP images via rembg."""

    def __init__(
        self,
        model_name: str = "isnet-general-use",
        alpha_threshold: int = 128,
        morph_kernel_size: int = 3,
        min_area_ratio: float = 0.01,
        low_coverage_warn: float = 0.02,
        high_coverage_warn: float = 0.95,
        min_valid_views: int = 20,
        min_valid_ratio_small: float = 0.60,
        session: Optional[Any] = None,
        remove_fn: Optional[Callable[..., Any]] = None,
    ) -> None:
        self.model_name = model_name
        self.alpha_threshold = alpha_threshold
        self.morph_kernel_size = morph_kernel_size
        self.min_area_ratio = min_area_ratio
        self.low_coverage_warn = low_coverage_warn
        self.high_coverage_warn = high_coverage_warn
        self.min_valid_views = min_valid_views
        self.min_valid_ratio_small = min_valid_ratio_small
        self._session = session
        self._remove_fn = remove_fn

    def close(self) -> None:
        """Release ONNX session memory and collect garbage before downstream GPU stages."""
        self._session = None
        gc.collect()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    def _ensure_session(self) -> tuple[Any, Callable[..., Any]]:
        if self._remove_fn is not None:
            return self._session, self._remove_fn

        import onnxruntime as ort
        import rembg

        if self._session is None:
            logger.info("[MASK] Initializing rembg session (%s, CPU bounded memory)...", self.model_name)
            sess_opts = ort.SessionOptions()
            sess_opts.enable_cpu_mem_arena = False
            sess_opts.enable_mem_pattern = False
            sess_opts.intra_op_num_threads = 4
            sess_opts.inter_op_num_threads = 1
            self._session = rembg.new_session(
                self.model_name,
                sess_opts=sess_opts,
                providers=["CPUExecutionProvider"],
            )
        return self._session, rembg.remove

    def mask_image(self, image_bgr: np.ndarray) -> np.ndarray:
        """Infer and post-process a binary uint8 (0/255) foreground mask for a BGR image."""
        session, remove_fn = self._ensure_session()
        image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        raw_alpha = remove_fn(image_rgb, session=session, only_mask=True)
        alpha_arr = np.asarray(raw_alpha)
        if alpha_arr.ndim == 3:
            alpha_arr = alpha_arr[:, :, -1]
        return postprocess_alpha_mask(
            alpha_arr,
            alpha_threshold=self.alpha_threshold,
            morph_kernel_size=self.morph_kernel_size,
            min_area_ratio=self.min_area_ratio,
        )

    def mask_directory(
        self,
        images_dir: Path | str,
        output_dir: Path | str,
        image_names: Optional[Sequence[str]] = None,
        *,
        debug_dir: Optional[Path | str] = None,
    ) -> MaskingResult:
        """Run semantic masking across all undistorted COLMAP images in ``images_dir``.

        Classifies every view as valid (``0.02 <= coverage <= 0.95``) or excluded
        (``empty_or_tiny`` / ``over_segmented``), enforces the minimum valid-views circuit
        breaker, writes a 4x4 visual contact sheet to ``debug_dir/masks_grid.jpg``, and
        releases the ONNX session via ``close()``.
        """
        src_dir = Path(images_dir).resolve()
        if not src_dir.is_dir():
            raise FileNotFoundError(f"Undistorted images directory not found: {src_dir}")

        masks_dir = ensure_directory(Path(output_dir).resolve())

        if image_names is not None:
            frame_paths = [src_dir / name for name in image_names if (src_dir / name).is_file()]
        else:
            frame_paths = sorted(
                p for p in src_dir.iterdir()
                if p.is_file() and p.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS
            )

        if not frame_paths:
            raise ValueError(f"No supported images found in {src_dir}")

        mask_paths: list[Path] = []
        coverage_ratios: dict[str, float] = {}
        valid_views: list[str] = []
        excluded_views: list[dict[str, Any]] = []
        excluded_map: dict[str, dict[str, Any]] = {}
        warning_frames: list[str] = []
        ordered_names: list[str] = []
        total = len(frame_paths)
        skipped_existing = 0

        needs_inference = any(
            not ((masks_dir / f"{p.stem}.png").is_file() and (masks_dir / f"{p.stem}.png").stat().st_size > 0)
            for p in frame_paths
        )
        if needs_inference:
            self._ensure_session()

        logger.info("[MASK] Segmenting %d undistorted frames with %s...", total, self.model_name)

        try:
            for idx, frame_path in enumerate(frame_paths, start=1):
                mask_out = masks_dir / f"{frame_path.stem}.png"
                mask: Optional[np.ndarray] = None
                resumed = False

                if mask_out.is_file() and mask_out.stat().st_size > 0:
                    existing_mask = cv2.imread(str(mask_out), cv2.IMREAD_GRAYSCALE)
                    if existing_mask is not None and existing_mask.size > 0:
                        mask = existing_mask
                        resumed = True
                        skipped_existing += 1

                if mask is None:
                    img_bgr = cv2.imread(str(frame_path), cv2.IMREAD_COLOR)
                    if img_bgr is None:
                        logger.warning("[MASK] Skipping unreadable image: %s", frame_path.name)
                        continue
                    mask = self.mask_image(img_bgr)
                    cv2.imwrite(str(mask_out), mask)

                mask_paths.append(mask_out)
                ordered_names.append(frame_path.name)

                coverage = float(np.mean(mask > 127))
                coverage_ratios[frame_path.name] = coverage

                if coverage < self.low_coverage_warn:
                    info = ExcludedViewInfo(frame_path.name, coverage, "empty_or_tiny").to_dict()
                    excluded_views.append(info)
                    excluded_map[frame_path.name] = info
                    warning_frames.append(frame_path.name)
                    logger.warning(
                        "[MASK] Frame %d/%d (%s) EXCLUDED (empty_or_tiny: %.1f%% < %.0f%%)",
                        idx,
                        total,
                        frame_path.name,
                        coverage * 100.0,
                        self.low_coverage_warn * 100.0,
                    )
                elif coverage > self.high_coverage_warn:
                    info = ExcludedViewInfo(frame_path.name, coverage, "over_segmented").to_dict()
                    excluded_views.append(info)
                    excluded_map[frame_path.name] = info
                    warning_frames.append(frame_path.name)
                    logger.warning(
                        "[MASK] Frame %d/%d (%s) EXCLUDED (over_segmented: %.1f%% > %.0f%%)",
                        idx,
                        total,
                        frame_path.name,
                        coverage * 100.0,
                        self.high_coverage_warn * 100.0,
                    )
                else:
                    valid_views.append(frame_path.name)
                    if not resumed and (idx == 1 or idx == total or idx % 10 == 0):
                        logger.info(
                            "[MASK] Frame %d/%d (%s) valid foreground coverage: %.1f%%",
                            idx,
                            total,
                            frame_path.name,
                            coverage * 100.0,
                        )

                if not resumed and idx % 10 == 0:
                    gc.collect()
        finally:
            self.close()

        # Generate 4x4 visual contact sheet BEFORE circuit-breaker abort so failures are inspectable
        resolved_debug_dir = (
            Path(debug_dir).resolve()
            if debug_dir is not None
            else (masks_dir.parent / "debug_masks").resolve()
        )
        contact_sheet_path = build_mask_contact_sheet(
            images_dir=src_dir,
            masks_dir=masks_dir,
            ordered_filenames=ordered_names,
            coverage_ratios=coverage_ratios,
            excluded_map=excluded_map,
            output_path=resolved_debug_dir / "masks_grid.jpg",
        )

        # Enforce minimum valid-view circuit breaker
        total_processed = len(ordered_names)
        if total_processed >= self.min_valid_views:
            if len(valid_views) < self.min_valid_views:
                raise RuntimeError(
                    f"Foreground masking circuit breaker triggered: only {len(valid_views)}/{total_processed} "
                    f"valid views remain (minimum required: {self.min_valid_views}). "
                    f"Inspect contact sheet: {contact_sheet_path}"
                )
        else:
            min_required = int(np.ceil(total_processed * self.min_valid_ratio_small))
            if len(valid_views) < min_required:
                raise RuntimeError(
                    f"Foreground masking circuit breaker triggered: only {len(valid_views)}/{total_processed} "
                    f"valid views remain (< {self.min_valid_ratio_small * 100:.0f}% threshold). "
                    f"Inspect contact sheet: {contact_sheet_path}"
                )

        median_cov = float(np.median(list(coverage_ratios.values()))) if coverage_ratios else 0.0
        logger.info(
            "[MASK] Completed %d masks in %s: %d/%d valid views, %d excluded, median_coverage=%.1f%% (%d resumed)",
            total_processed,
            masks_dir,
            len(valid_views),
            total_processed,
            len(excluded_views),
            median_cov * 100.0,
            skipped_existing,
        )
        return MaskingResult(
            masks_dir=masks_dir,
            mask_paths=mask_paths,
            coverage_ratios=coverage_ratios,
            model_name=self.model_name,
            valid_views=valid_views,
            excluded_views=excluded_views,
            median_coverage=median_cov,
            contact_sheet_path=contact_sheet_path,
            warning_frames=warning_frames,
            total_frames=total_processed,
        )
