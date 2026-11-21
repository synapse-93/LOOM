import numpy as np
from pathlib import Path
import trimesh

from loom.geometry.alignment import CoordinateNormalizer

try:
    from sklearn.cluster import DBSCAN
except ImportError:
    from scipy.spatial import cKDTree

    class DBSCAN:
        """Lightweight KDTree-based DBSCAN fallback when scikit-learn is not installed."""

        def __init__(self, eps: float = 0.04, min_samples: int = 30):
            self.eps = eps
            self.min_samples = min_samples

        def fit(self, X: np.ndarray):
            tree = cKDTree(X)
            neighbors = tree.query_ball_point(X, r=self.eps)
            n = len(X)
            self.labels_ = np.full(n, -1, dtype=int)
            cluster_id = 0
            visited = np.zeros(n, dtype=bool)
            core_samples = np.array([len(neigh) >= self.min_samples for neigh in neighbors])

            for i in range(n):
                if visited[i] or not core_samples[i]:
                    continue
                self.labels_[i] = cluster_id
                visited[i] = True
                queue = [i]
                head = 0
                while head < len(queue):
                    curr = queue[head]
                    head += 1
                    for nxt in neighbors[curr]:
                        if not visited[nxt]:
                            visited[nxt] = True
                            if core_samples[nxt]:
                                queue.append(nxt)
                        if self.labels_[nxt] == -1:
                            self.labels_[nxt] = cluster_id
                cluster_id += 1
            return self


def main() -> None:
    pc_path = Path("outputs/demo/dense/fused.ply")
    out_dir = Path("outputs/demo")
    out_dir.mkdir(parents=True, exist_ok=True)

    print("1. Loading raw point cloud...")
    pc = trimesh.load(pc_path)
    pts = pc.vertices
    colors = pc.visual.vertex_colors if hasattr(pc.visual, "vertex_colors") else None
    print(f"   Total points: {len(pts):,}")

    # 2. Canonical Coordinate Normalization via CoordinateNormalizer
    print("2. Detecting floor plane and computing canonical alignment via CoordinateNormalizer...")
    normalizer = CoordinateNormalizer(distance_threshold=0.015, max_iterations=500)
    aligned_pc, align_res = normalizer.normalize(pc)
    rotated_pts = np.asarray(aligned_pc.vertices, dtype=np.float64)
    plane_n = align_res.support_plane.normal
    inlier_count = len(align_res.support_plane.inlier_indices)
    print(f"   Floor normal: [{plane_n[0]:.3f}, {plane_n[1]:.3f}, {plane_n[2]:.3f}] ({inlier_count:,} inliers)")

    # 3. Filter background chair points (keep foreground cluster above floor)
    print("3. Isolating shoe cluster from background chair...")
    # Floor points are Z ~ 0. Keep points where Z > -0.01
    above_floor_mask = rotated_pts[:, 2] > -0.01
    sub_pts = rotated_pts[above_floor_mask]
    sub_colors = colors[above_floor_mask] if colors is not None else None

    # DBSCAN on subsampled points to separate shoe from chair
    sample_idx = np.random.choice(len(sub_pts), min(50000, len(sub_pts)), replace=False)
    clustering = DBSCAN(eps=0.04, min_samples=30).fit(sub_pts[sample_idx])
    labels = clustering.labels_

    # Find largest cluster (the shoe)
    unique_labels, counts = np.unique(labels[labels >= 0], return_counts=True)
    shoe_cluster_id = unique_labels[np.argmax(counts)]

    # Compute bounding box of shoe cluster
    shoe_pts_sample = sub_pts[sample_idx][labels == shoe_cluster_id]
    shoe_min = shoe_pts_sample.min(axis=0) - 0.03
    shoe_max = shoe_pts_sample.max(axis=0) + 0.03

    # Crop full cloud to shoe bounding box
    shoe_mask = np.all((sub_pts >= shoe_min) & (sub_pts <= shoe_max), axis=1)
    final_shoe_pts = sub_pts[shoe_mask]
    final_colors = sub_colors[shoe_mask] if sub_colors is not None else None

    # Center shoe on XY origin
    xy_center = final_shoe_pts[:, :2].mean(axis=0)
    final_shoe_pts[:, :2] -= xy_center

    print(f"   Isolated shoe cloud: {len(final_shoe_pts):,} points")
    print(f"   Z range: {final_shoe_pts[:, 2].min():.4f} to {final_shoe_pts[:, 2].max():.4f}")

    # Save aligned, isolated point cloud
    clean_pc = trimesh.PointCloud(final_shoe_pts, colors=final_colors)
    out_pc = out_dir / "shoe_aligned_clean.ply"
    clean_pc.export(out_pc)
    print(f"   Saved clean point cloud to: {out_pc}")


if __name__ == "__main__":
    main()

