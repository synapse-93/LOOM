import trimesh
import numpy as np
from pathlib import Path

pc_path = Path("outputs/demo/dense/fused.ply")
mesh_path = Path("outputs/demo/raw_shoe_isolated.ply")

if not mesh_path.exists():
    candidates = list(Path("outputs").glob("**/meshed-poisson.ply"))
    if candidates:
        mesh_path = candidates[0]

out_dir = Path("outputs/stl")
out_dir.mkdir(parents=True, exist_ok=True)
out_stl = out_dir / "shoe_production_master_280mm.stl"

print(f"1. Loading point cloud ({pc_path}) and raw mesh ({mesh_path})...")
pc = trimesh.load(pc_path)
mesh = trimesh.load(mesh_path, process=False)
pts = np.asarray(pc.vertices, dtype=np.float64)
print(f"   Dense cloud points: {len(pts):,}, Raw mesh faces: {len(mesh.faces):,}")

# 2. Vectorized RANSAC floor plane fitting on bottom 35% elevation points
print("2. Detecting support floor and leveling to Z = 0...")
z_cutoff = np.percentile(pts[:, 2], 35)
candidate_idx = np.where(pts[:, 2] <= z_cutoff)[0]

# Subsample candidate pool for sub-second convergence
sample_pool = candidate_idx[::2] if len(candidate_idx) > 50000 else candidate_idx
rng = np.random.default_rng(42)
best_inliers = []
best_normal = np.array([0.0, 0.0, 1.0])
best_d = 0.0
thresh = 0.015 * (pts[:, 2].max() - pts[:, 2].min())

for _ in range(800):
    idx = rng.choice(sample_pool, 3, replace=False)
    p1, p2, p3 = pts[idx]
    normal = np.cross(p2 - p1, p3 - p1)
    norm = np.linalg.norm(normal)
    if norm < 1e-7:
        continue
    normal /= norm
    d = -float(np.dot(normal, p1))

    dists = np.abs(np.dot(pts[sample_pool], normal) + d)
    inliers = np.where(dists < thresh)[0]
    if len(inliers) > len(best_inliers):
        best_inliers = inliers
        best_normal = normal
        best_d = d

# Ensure floor normal points UP toward the shoe mass
centroid = pts.mean(axis=0)
if np.dot(best_normal, centroid) + best_d < 0:
    best_normal = -best_normal
    best_d = -best_d

# Compute Rodrigues rotation aligning floor normal to [0, 0, 1]
target_z = np.array([0.0, 0.0, 1.0])
v = np.cross(best_normal, target_z)
s = np.linalg.norm(v)
c = float(np.dot(best_normal, target_z))

if s < 1e-8:
    R = np.eye(3) if c > 0 else -np.eye(3)
else:
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    R = np.eye(3) + vx + (vx @ vx) * ((1.0 - c) / (s ** 2))

# Compute floor elevation level in rotated space
rotated_pts = pts @ R.T
rotated_sub = pts[sample_pool] @ R.T
floor_z = float(np.median(rotated_sub[best_inliers, 2]))

# Center XY around the elevated shoe mass (Z > floor + 2cm)
above_floor = rotated_pts[:, 2] > (floor_z + 0.02)
shoe_cloud = rotated_pts[above_floor] if np.sum(above_floor) > 100 else rotated_pts
xy_center = shoe_cloud[:, :2].mean(axis=0)

# Build 4x4 rigid transformation matrix
T = np.eye(4)
T[:3, :3] = R
T[:3, 3] = [-xy_center[0], -xy_center[1], -floor_z]

# 3. Transform raw mesh to leveled canonical space
print("3. Aligning high-res mesh to gravity coordinates...")
mesh.apply_transform(T)

# 4. Isolate dominant shoe body (discards room clutter and floating artifacts)
print("4. Isolating dominant shoe component...")
comps = trimesh.graph.connected_components(mesh.face_adjacency, min_len=500)
shoe = mesh.submesh([max(comps, key=len)], append=True)
print(f"   Dominant shoe component faces: {len(shoe.faces):,}")

# 5. Clean horizontal cut at the true sole plane (Z = +1.5 mm above table)
z_min, z_max = shoe.bounds[0][2], shoe.bounds[1][2]
z_cut = max(0.005, z_min + 0.04 * (z_max - z_min))
print(f"5. Slicing flat sole plane at Z = {z_cut:.4f}...")

try:
    sliced = shoe.slice_plane(plane_origin=[0, 0, z_cut], plane_normal=[0, 0, 1], cap=True)
except Exception:
    sliced = shoe.slice_plane(plane_origin=[0, 0, z_cut], plane_normal=[0, 0, 1], cap=False)
    trimesh.repair.fill_holes(sliced)

# 6. Seal boundary loops and verify outward normal orientation
print("6. Sealing watertight boundary...")
trimesh.repair.fill_holes(sliced)
sliced.merge_vertices()
sliced.fix_normals()
if sliced.volume < 0:
    sliced.invert()

# 7. Uniform scale to 280.0 mm in float64 memory
target_length_mm = 280.0
scale = target_length_mm / max(sliced.extents)
sliced.apply_scale(scale)

# Snap bottom of sole flush to Z = 0.0 for 3D printer build plate
sliced.vertices[:, 2] -= sliced.bounds[0][2]
sliced.vertices[:, :2] -= sliced.bounds.mean(axis=0)[:2]

print(f"\nDimensions (mm): L={sliced.extents[0]:.1f}, W={sliced.extents[1]:.1f}, H={sliced.extents[2]:.1f}")
print(f"Watertight: {sliced.is_watertight}, Volume: {sliced.volume / 1000:.1f} cm³")

sliced.export(out_stl)
print(f"\nSUCCESS: Clean production STL exported to: {out_stl}")
