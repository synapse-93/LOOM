"""Reconstruction-aware keyframe selection evaluating temporal spread and geometric connectivity."""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence
import cv2
import numpy as np

from loom.capture.guidance import CaptureGuidance
from loom.capture.quality import FrameQualityResult
from loom.config.models import CaptureConfig

logger = logging.getLogger(__name__)


@dataclass
class FrameAnalysis:
    """Internal optical and feature extraction metrics for a candidate frame."""

    index: int
    path: Path
    sharpness: float
    brightness: float
    contrast: float
    texture_score: float
    keypoint_count: int
    grid_coverage: float
    optical_score: float
    is_underexposed: bool
    is_overexposed: bool
    is_low_contrast: bool
    is_low_texture: bool
    is_severe_defect: bool
    keypoints: list[cv2.KeyPoint] = field(default_factory=list)
    descriptors: np.ndarray | None = None
    thumbnail: np.ndarray = field(default_factory=lambda: np.zeros((64, 64), dtype=np.uint8))


@dataclass
class MatchEdge:
    """Geometrically verified pairwise match information between two candidate frames."""

    i: int
    j: int
    raw_matches: int
    f_inliers: int
    h_inliers: int
    h_ratio: float
    is_connected: bool
    is_parallax_bearing: bool


class ReconstructionAwareSelector:
    """Selects candidate keyframes maximizing temporal distribution and geometric connectivity.

    Contrast with default mode:
        Instead of applying a single hard sharpness cutoff that risks dropping large
        temporal spans of video and fragmenting the match graph, this selector:
        1. Divides the candidate timeline into uniform temporal buckets to guarantee full duration span.
        2. Evaluates multi-factor optical quality (sharpness, exposure, contrast, feature distribution).
        3. Computes geometric verification (Fundamental matrix vs Homography) in a bounded local window.
        4. Identifies planar/rotation (homography-dominated) degeneracy lacking parallax.
        5. Prioritizes bridge frames that link disconnected graph components.
        6. Suppresses visually redundant frames.
    """

    def __init__(self, config: CaptureConfig) -> None:
        self.config = config

    def _extract_frame_features(
        self,
        index: int,
        path: Path,
    ) -> FrameAnalysis:
        """Analyze optical properties and extract bounded features."""
        gray = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if gray is None:
            raise ValueError(f"Failed to load image for quality assessment: {path}")

        sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        brightness = float(np.mean(gray))
        contrast = float(np.std(gray))
        texture_score = sharpness

        min_texture_thresh = float(getattr(self.config, "min_texture_score", 10.0))
        is_low_texture = texture_score < min_texture_thresh
        is_underexposed = brightness < getattr(self.config, "min_brightness", 30.0)
        is_overexposed = brightness > getattr(self.config, "max_brightness", 235.0)
        is_low_contrast = contrast < getattr(self.config, "min_contrast", 15.0)

        # Severe defect check: completely dark, blown out, or flat gradient
        is_severe_defect = (
            brightness < 10.0 or brightness > 248.0 or contrast < 5.0
        )

        thumb = cv2.resize(gray, (64, 64), interpolation=cv2.INTER_AREA)

        keypoints: list[cv2.KeyPoint] = []
        descriptors: np.ndarray | None = None
        grid_coverage = 0.0

        if not is_severe_defect and getattr(self.config, "enable_geometric_verification", True):
            try:
                sift = cv2.SIFT_create(nfeatures=600)
                keypoints, descriptors = sift.detectAndCompute(gray, None)
            except Exception as exc:
                logger.debug("SIFT extraction fallback to ORB: %s", exc)
                orb = cv2.ORB_create(nfeatures=600)
                keypoints, descriptors = orb.detectAndCompute(gray, None)

            if keypoints:
                h, w = gray.shape[:2]
                cell_h, cell_w = max(1, h // 3), max(1, w // 3)
                occupied: set[tuple[int, int]] = set()
                for kp in keypoints:
                    r = min(2, int(kp.pt[1] // cell_h))
                    c = min(2, int(kp.pt[0] // cell_w))
                    occupied.add((r, c))
                grid_coverage = len(occupied) / 9.0

        kp_count = len(keypoints)
        if getattr(self.config, "enable_geometric_verification", True) and kp_count < 8:
            is_severe_defect = True

        if is_severe_defect:
            optical_score = 0.05
        else:
            norm_sharpness = min(1.0, sharpness / max(1.0, self.config.sharpness_threshold))
            norm_contrast = min(1.0, contrast / 50.0)
            norm_features = min(1.0, kp_count / 250.0) * max(0.2, grid_coverage)
            optical_score = 0.4 * norm_sharpness + 0.3 * norm_contrast + 0.3 * norm_features

        return FrameAnalysis(
            index=index,
            path=path,
            sharpness=round(sharpness, 2),
            brightness=round(brightness, 2),
            contrast=round(contrast, 2),
            texture_score=round(texture_score, 2),
            keypoint_count=kp_count,
            grid_coverage=round(grid_coverage, 2),
            optical_score=round(optical_score, 3),
            is_underexposed=is_underexposed,
            is_overexposed=is_overexposed,
            is_low_contrast=is_low_contrast,
            is_low_texture=is_low_texture,
            is_severe_defect=is_severe_defect,
            keypoints=keypoints,
            descriptors=descriptors,
            thumbnail=thumb,
        )

    def _verify_pair_geometry(
        self,
        frame_i: FrameAnalysis,
        frame_j: FrameAnalysis,
    ) -> MatchEdge:
        """Estimate Fundamental matrix and Homography to detect verified inliers and parallax."""
        if (
            frame_i.descriptors is None
            or frame_j.descriptors is None
            or len(frame_i.descriptors) < 8
            or len(frame_j.descriptors) < 8
        ):
            return MatchEdge(
                i=frame_i.index,
                j=frame_j.index,
                raw_matches=0,
                f_inliers=0,
                h_inliers=0,
                h_ratio=0.0,
                is_connected=False,
                is_parallax_bearing=False,
            )

        norm_type = cv2.NORM_HAMMING if frame_i.descriptors.dtype == np.uint8 else cv2.NORM_L2
        bf = cv2.BFMatcher(norm_type)
        try:
            raw_knn = bf.knnMatch(frame_i.descriptors, frame_j.descriptors, k=2)
            good_matches = [m for m, n in raw_knn if m.distance < 0.75 * n.distance]
        except Exception:
            good_matches = []

        raw_cnt = len(good_matches)
        min_inliers = getattr(self.config, "min_inlier_matches", 15)

        if raw_cnt < 8:
            return MatchEdge(
                i=frame_i.index,
                j=frame_j.index,
                raw_matches=raw_cnt,
                f_inliers=0,
                h_inliers=0,
                h_ratio=0.0,
                is_connected=False,
                is_parallax_bearing=False,
            )

        pts_i = np.float32([frame_i.keypoints[m.queryIdx].pt for m in good_matches])
        pts_j = np.float32([frame_j.keypoints[m.trainIdx].pt for m in good_matches])

        # Fundamental matrix estimation
        F, f_mask = cv2.findFundamentalMat(pts_i, pts_j, cv2.FM_RANSAC, 3.0)
        f_inliers = int(np.sum(f_mask > 0)) if (F is not None and f_mask is not None) else 0

        # Homography estimation (planar or pure rotation)
        H, h_mask = cv2.findHomography(pts_i, pts_j, cv2.RANSAC, 3.0)
        h_inliers = int(np.sum(h_mask > 0)) if (H is not None and h_mask is not None) else 0

        is_connected = max(f_inliers, h_inliers) >= min_inliers

        if f_inliers > 0:
            h_ratio = min(1.0, h_inliers / float(f_inliers))
        elif h_inliers >= min_inliers:
            h_ratio = 1.0
        else:
            h_ratio = 0.0

        max_h_ratio = getattr(self.config, "max_homography_inlier_ratio", 0.85)

        # Parallax check: true 3D baseline requires inliers not fully explained by homography alone
        is_parallax_bearing = is_connected and (f_inliers >= min_inliers) and (h_ratio < max_h_ratio)

        return MatchEdge(
            i=frame_i.index,
            j=frame_j.index,
            raw_matches=raw_cnt,
            f_inliers=f_inliers,
            h_inliers=h_inliers,
            h_ratio=round(h_ratio, 3),
            is_connected=is_connected,
            is_parallax_bearing=is_parallax_bearing,
        )

    def _select_keyframes(
        self,
        candidates: list[FrameAnalysis],
        edges: list[MatchEdge],
    ) -> tuple[list[int], dict[int, list[str]], dict[int, list[str]], dict[str, Any]]:
        """Perform stratified temporal selection with geometric connectivity and bridge preference."""
        n = len(candidates)
        if n == 0:
            return [], {}, {}, {"status": "unavailable", "limitation": "No candidate frames provided."}

        target_budget = getattr(self.config, "target_selected_frames", 30)
        target_budget = min(target_budget, n)

        has_geom = getattr(self.config, "enable_geometric_verification", True) and len(edges) > 0

        adj: dict[int, set[int]] = defaultdict(set)
        parallax_adj: dict[int, set[int]] = defaultdict(set)
        edge_map: dict[tuple[int, int], MatchEdge] = {}

        if has_geom:
            for e in edges:
                edge_map[(e.i, e.j)] = e
                edge_map[(e.j, e.i)] = e
                if e.is_connected:
                    adj[e.i].add(e.j)
                    adj[e.j].add(e.i)
                    if e.is_parallax_bearing:
                        parallax_adj[e.i].add(e.j)
                        parallax_adj[e.j].add(e.i)

        # Multi-factor utility score per candidate
        utility_scores: dict[int, float] = {}
        for c in candidates:
            if has_geom:
                p_deg = len(parallax_adj[c.index])
                t_deg = len(adj[c.index])
                u = c.optical_score + 0.3 * min(1.0, p_deg / 2.0) + 0.2 * min(1.0, t_deg / 3.0)
            else:
                u = c.optical_score
            utility_scores[c.index] = round(u, 3)

        # Step 1: Temporal Stratification into B buckets
        # When geometric verification is enabled, reserve budget slots for bridge frames and high-utility filling
        if has_geom and target_budget >= 3:
            num_buckets = max(2, int(target_budget * 0.75))
        else:
            num_buckets = min(target_budget, n)
        num_buckets = min(num_buckets, n)
        bucket_size = n / float(num_buckets)
        selected_set: set[int] = set()
        selection_reasons: dict[int, list[str]] = defaultdict(list)
        selected_thumbs: list[np.ndarray] = []

        def is_redundant(cand_idx: int) -> tuple[bool, int, float]:
            cand_thumb = candidates[cand_idx].thumbnail
            thresh = getattr(self.config, "redundancy_threshold", 0.98)
            for s_idx in selected_set:
                s_thumb = candidates[s_idx].thumbnail
                diff = float(np.mean(np.abs(cand_thumb.astype(float) - s_thumb.astype(float)))) / 255.0
                sim = 1.0 - diff
                if sim >= thresh:
                    return True, s_idx, sim
            return False, -1, 0.0

        for b in range(num_buckets):
            start_idx = int(b * bucket_size)
            end_idx = int((b + 1) * bucket_size) if b < num_buckets - 1 else n
            bucket_candidates = list(range(start_idx, end_idx))
            if not bucket_candidates:
                continue

            # Sort bucket candidates by utility descending
            bucket_candidates.sort(key=lambda idx: utility_scores[idx], reverse=True)

            picked = False
            for idx in bucket_candidates:
                cand = candidates[idx]
                if cand.is_severe_defect:
                    continue
                red, red_with, sim = is_redundant(idx)
                if not red:
                    selected_set.add(idx)
                    selection_reasons[idx].append(
                        f"Temporal anchor for sector {b+1}/{num_buckets} (utility: {utility_scores[idx]:.2f})"
                    )
                    picked = True
                    break

            if not picked and bucket_candidates:
                # If all were flagged redundant or non-ideal, pick top utility non-severe candidate
                for idx in bucket_candidates:
                    if not candidates[idx].is_severe_defect:
                        selected_set.add(idx)
                        selection_reasons[idx].append(
                            f"Fallback anchor for sector {b+1}/{num_buckets} (utility: {utility_scores[idx]:.2f})"
                        )
                        break

        # Step 2: Bridge Frame Selection (if graph is disconnected)
        if has_geom:
            def get_selected_components() -> list[set[int]]:
                sel_list = sorted(selected_set)
                visited_nodes: set[int] = set()
                comps: list[set[int]] = []
                for s_node in sel_list:
                    if s_node not in visited_nodes:
                        comp = set()
                        q = [s_node]
                        visited_nodes.add(s_node)
                        while q:
                            curr = q.pop(0)
                            comp.add(curr)
                            for nbr in adj[curr]:
                                if nbr in selected_set and nbr not in visited_nodes:
                                    visited_nodes.add(nbr)
                                    q.append(nbr)
                        comps.append(comp)
                return comps

            components = get_selected_components()

            if len(components) > 1:
                bridge_candidates = []
                for cand in candidates:
                    if cand.index in selected_set or cand.is_severe_defect:
                        continue
                    # Check how many distinct selected components this candidate connects to
                    connected_comps = set()
                    for c_idx, comp in enumerate(components):
                        if any(nbr in comp for nbr in adj[cand.index]):
                            connected_comps.add(c_idx)
                    if len(connected_comps) > 1:
                        bridge_candidates.append((cand.index, len(connected_comps), utility_scores[cand.index]))

                # Sort by number of connected components descending, then utility
                bridge_candidates.sort(key=lambda x: (x[1], x[2]), reverse=True)
                for b_idx, comp_count, u_score in bridge_candidates:
                    if len(selected_set) < target_budget:
                        selected_set.add(b_idx)
                        selection_reasons[b_idx].append(
                            f"Bridge frame linking {comp_count} disconnected subgraphs (utility: {u_score:.2f})"
                        )
                        components = get_selected_components()
                        if len(components) <= 1:
                            break
                    else:
                        replaced = False
                        for comp in sorted(components, key=len, reverse=True):
                            if len(comp) > 1:
                                sorted_nodes = sorted(comp, key=lambda idx: utility_scores[idx])
                                for rem_idx in sorted_nodes:
                                    if b_idx not in adj[rem_idx]:
                                        selected_set.remove(rem_idx)
                                        selected_set.add(b_idx)
                                        selection_reasons[b_idx].append(
                                            f"Bridge frame linking {comp_count} disconnected subgraphs (utility: {u_score:.2f})"
                                        )
                                        replaced = True
                                        break
                                if replaced:
                                    components = get_selected_components()
                                    break
                        if len(components) <= 1:
                            break

        # Step 3: Fill Budget with Remaining Non-Redundant High-Utility Frames
        if len(selected_set) < target_budget:
            unselected = [c.index for c in candidates if c.index not in selected_set and not c.is_severe_defect]
            unselected.sort(key=lambda idx: utility_scores[idx], reverse=True)

            for u_idx in unselected:
                if len(selected_set) >= target_budget:
                    break
                red, _, _ = is_redundant(u_idx)
                if not red:
                    selected_set.add(u_idx)
                    selection_reasons[u_idx].append(
                        f"High-utility supplemental keyframe (utility: {utility_scores[u_idx]:.2f})"
                    )

        selected_indices = sorted(selected_set)

        # Compute rejection reasons for unselected frames
        rejection_reasons: dict[int, list[str]] = defaultdict(list)
        for cand in candidates:
            idx = cand.index
            if idx in selected_set:
                continue

            if cand.is_severe_defect:
                if cand.brightness < 10.0:
                    rejection_reasons[idx].append(f"Severe underexposure (brightness {cand.brightness:.1f} < 10.0)")
                elif cand.brightness > 248.0:
                    rejection_reasons[idx].append(f"Severe overexposure (brightness {cand.brightness:.1f} > 248.0)")
                elif cand.contrast < 5.0:
                    rejection_reasons[idx].append(f"Near-zero contrast (std dev {cand.contrast:.1f} < 5.0)")
                elif cand.keypoint_count < 8:
                    rejection_reasons[idx].append(f"Insufficient visual features (keypoints {cand.keypoint_count} < 8)")
                else:
                    rejection_reasons[idx].append("Severe optical quality defect")
                continue

            red, red_with, sim = is_redundant(idx)
            if red:
                rejection_reasons[idx].append(
                    f"Visual redundancy with frame_{red_with:06d} (similarity {sim:.3f} >= threshold)"
                )
                continue

            if has_geom:
                t_deg = len(adj[idx])
                p_deg = len(parallax_adj[idx])
                if t_deg == 0:
                    rejection_reasons[idx].append("Graph isolation (0 geometrically verified inliers)")
                elif p_deg == 0:
                    rejection_reasons[idx].append("Homography-dominated motion without verified parallax")
                else:
                    rejection_reasons[idx].append(
                        f"Lower reconstruction utility ({utility_scores[idx]:.2f}) than selected anchors in sector"
                    )
            else:
                rejection_reasons[idx].append(
                    f"Lower optical quality score ({utility_scores[idx]:.2f}) than selected anchors in sector"
                )

        # Compute Match Graph Diagnostics
        if has_geom:
            cand_visited = set()
            cand_components = []
            for c in candidates:
                if c.index not in cand_visited and len(adj[c.index]) > 0:
                    comp = set()
                    q = [c.index]
                    cand_visited.add(c.index)
                    while q:
                        curr = q.pop(0)
                        comp.add(curr)
                        for nbr in adj[curr]:
                            if nbr not in cand_visited:
                                cand_visited.add(nbr)
                                q.append(nbr)
                    cand_components.append(comp)

            sel_visited = set()
            sel_components = []
            for s in selected_indices:
                if s not in sel_visited:
                    comp = set()
                    q = [s]
                    sel_visited.add(s)
                    while q:
                        curr = q.pop(0)
                        comp.add(curr)
                        for nbr in adj[curr]:
                            if nbr in selected_set and nbr not in sel_visited:
                                sel_visited.add(nbr)
                                q.append(nbr)
                    sel_components.append(comp)

            total_connected_pairs = sum(1 for e in edges if e.is_connected)
            parallax_pairs = sum(1 for e in edges if e.is_parallax_bearing)
            homography_pairs = sum(1 for e in edges if e.is_connected and not e.is_parallax_bearing)
            isolated_cands = sum(1 for c in candidates if len(adj[c.index]) == 0)

            # Temporal coverage metrics
            span = (selected_indices[-1] - selected_indices[0]) if len(selected_indices) > 1 else 0
            cov_ratio = round(span / max(1, n - 1), 3)
            gaps = [
                selected_indices[k] - selected_indices[k - 1]
                for k in range(1, len(selected_indices))
            ] if len(selected_indices) > 1 else [0]
            max_gap = max(gaps) if gaps else 0

            diagnostics = {
                "match_graph_status": "evaluated",
                "total_pairs_evaluated": len(edges),
                "connected_pairs_count": total_connected_pairs,
                "parallax_bearing_pairs_count": parallax_pairs,
                "homography_dominated_pairs_count": homography_pairs,
                "candidate_graph_components": len(cand_components),
                "selected_subgraph_components": len(sel_components),
                "isolated_candidate_frames": isolated_cands,
                "temporal_coverage_ratio": cov_ratio,
                "max_temporal_gap_frames": max_gap,
            }
        else:
            span = (selected_indices[-1] - selected_indices[0]) if len(selected_indices) > 1 else 0
            cov_ratio = round(span / max(1, n - 1), 3)
            diagnostics = {
                "match_graph_status": "unavailable",
                "limitation": (
                    "Geometric match-graph verification was disabled or unavailable; "
                    "frame selection fell back to temporal stratification and optical quality scoring."
                ),
                "temporal_coverage_ratio": cov_ratio,
            }

        return selected_indices, selection_reasons, rejection_reasons, diagnostics

    def assess_and_filter(
        self,
        frame_paths: Sequence[Path],
    ) -> tuple[Any, list[FrameQualityResult]]:
        """Execute reconstruction-aware evaluation and keyframe selection."""
        from loom.pipeline.artifacts import CaptureAnalysisArtifact

        if not frame_paths:
            artifact = CaptureAnalysisArtifact(
                stage_name="capture_quality",
                selected_frames=[],
                rejected_frames=[],
                average_sharpness=0.0,
                coverage_score=0.0,
                guidance_notes=["No frames provided for quality assessment."],
                metadata={"total_candidate_frames": 0, "selected_count": 0, "rejected_count": 0},
            )
            return artifact, []

        # 1. Optical and feature analysis
        candidates: list[FrameAnalysis] = []
        for idx, path in enumerate(frame_paths):
            cand = self._extract_frame_features(index=idx, path=path)
            candidates.append(cand)

        # 2. Geometric matching across bounded neighborhood
        edges: list[MatchEdge] = []
        has_geom = getattr(self.config, "enable_geometric_verification", True)
        window = getattr(self.config, "temporal_window_size", 3)
        n = len(candidates)

        if has_geom and n > 1:
            for i in range(n):
                for delta in range(1, window + 1):
                    j = i + delta
                    if j < n:
                        edge = self._verify_pair_geometry(candidates[i], candidates[j])
                        edges.append(edge)

        # 3. Stratified selection with graph connectivity
        selected_indices, sel_reasons, rej_reasons, diagnostics = self._select_keyframes(candidates, edges)
        selected_set = set(selected_indices)

        # 4. Construct FrameQualityResult contracts
        results: list[FrameQualityResult] = []
        selected_paths: list[Path] = []
        rejected_paths: list[Path] = []
        sharpness_values: list[float] = []

        blurry_count = 0
        exposure_count = 0
        redundant_count = 0
        low_texture_count = 0

        for cand in candidates:
            idx = cand.index
            is_acc = idx in selected_set
            sharpness_values.append(cand.sharpness)

            is_blurry = cand.sharpness < self.config.sharpness_threshold
            if is_blurry:
                blurry_count += 1
            if cand.is_underexposed or cand.is_overexposed or cand.is_low_contrast:
                exposure_count += 1
            if cand.is_low_texture:
                low_texture_count += 1

            reasons_tuple = tuple(rej_reasons.get(idx, ()))
            if any("redundancy" in r.lower() for r in reasons_tuple):
                redundant_count += 1

            res = FrameQualityResult(
                frame_path=cand.path,
                sharpness=cand.sharpness,
                brightness=cand.brightness,
                contrast=cand.contrast,
                texture_score=cand.texture_score,
                is_low_texture=cand.is_low_texture,
                is_blurry=is_blurry,
                is_underexposed=cand.is_underexposed,
                is_overexposed=cand.is_overexposed,
                is_low_contrast=cand.is_low_contrast,
                is_redundant=any("redundancy" in r.lower() for r in reasons_tuple),
                is_accepted=is_acc,
                rejection_reasons=reasons_tuple,
            )
            results.append(res)
            if is_acc:
                selected_paths.append(cand.path)
            else:
                rejected_paths.append(cand.path)

        avg_sharpness = float(np.mean(sharpness_values)) if sharpness_values else 0.0
        total_frames = max(1, len(frame_paths))
        blur_ratio = blurry_count / total_frames
        cov_score = diagnostics.get("temporal_coverage_ratio", round(len(selected_paths) / total_frames, 3))

        guidance_notes = CaptureGuidance.generate_recommendations(
            average_sharpness=avg_sharpness,
            blur_ratio=blur_ratio,
            coverage_score=cov_score,
            low_exposure_ratio=exposure_count / total_frames,
            redundancy_ratio=redundant_count / total_frames,
        )

        metadata = {
            "selection_mode": "reconstruction_aware",
            "total_candidate_frames": total_frames,
            "selected_count": len(selected_paths),
            "rejected_count": len(rejected_paths),
            "blurry_count": blurry_count,
            "exposure_defect_count": exposure_count,
            "redundant_count": redundant_count,
            "low_texture_count": low_texture_count,
            "temporal_coverage_score": cov_score,
            "graph_diagnostics": diagnostics,
            "selection_reasons": {
                candidates[idx].path.name: sel_reasons.get(idx, [])
                for idx in selected_indices
            },
            "thresholds": {
                "sharpness": self.config.sharpness_threshold,
                "selection_mode": "reconstruction_aware",
                "target_selected_frames": getattr(self.config, "target_selected_frames", 30),
                "min_inlier_matches": getattr(self.config, "min_inlier_matches", 15),
                "max_homography_inlier_ratio": getattr(self.config, "max_homography_inlier_ratio", 0.85),
                "temporal_window_size": getattr(self.config, "temporal_window_size", 3),
            },
        }

        artifact = CaptureAnalysisArtifact(
            stage_name="capture_quality",
            selected_frames=selected_paths,
            rejected_frames=rejected_paths,
            average_sharpness=round(avg_sharpness, 2),
            coverage_score=cov_score,
            guidance_notes=guidance_notes,
            metadata=metadata,
        )

        logger.info(
            "Reconstruction-aware selection completed: %d total, %d selected, %d rejected (coverage: %.2f)",
            total_frames,
            len(selected_paths),
            len(rejected_paths),
            cov_score,
        )

        return artifact, results
