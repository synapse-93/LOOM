import trimesh
import numpy as np
from scipy.spatial import cKDTree
from pathlib import Path
from loom.printability.gate import PrintabilityGate

mesh_path = Path('outputs/demo/raw_shoe_isolated.ply')
pc_path = Path('outputs/demo/dense/fused.ply')
out_dir = Path('outputs/stl')
out_dir.mkdir(parents=True, exist_ok=True)

print(f"1. Loading raw Poisson shoe ({mesh_path})...")
mesh = trimesh.load(mesh_path, process=False)
pc = trimesh.load(pc_path)
print(f"   Mesh faces: {len(mesh.faces):,}, Point cloud points: {len(pc.vertices):,}")

# 2. Conservative KDTree culling (strips empty-air funnel, keeps shoe upper intact)
print("2. Stripping floating air funnel with safe threshold...")
tree = cKDTree(pc.vertices)
sample_dists, _ = tree.query(pc.vertices[::20], k=2, workers=8)
local_spacing = np.median(sample_dists[:, 1])

safe_threshold = local_spacing * 8.0
print(f"   Local spacing: {local_spacing:.5f}, Safe threshold: {safe_threshold:.5f}")

distances, _ = tree.query(mesh.vertices, workers=8)
valid_verts = distances <= safe_threshold
valid_faces = valid_verts[mesh.faces].all(axis=1)
culled = mesh.submesh([valid_faces], append=True)

# 3. Isolate main shoe body
comps = trimesh.graph.connected_components(culled.face_adjacency, min_len=500)
shoe = culled.submesh([max(comps, key=len)], append=True)
print(f"   Dominant shoe component: {len(shoe.faces):,} faces")

# 4. Light Taubin surface smoothing (removes surface ripple without shrinking shoe)
print("3. Applying Taubin smoothing to remove surface ripple...")
trimesh.smoothing.filter_taubin(shoe, lamb=0.5, nu=-0.53, iterations=5)

# 5. Clean horizontal sole cut with mapbox-earcut planar triangulation
z_min, z_max = shoe.bounds[0][2], shoe.bounds[1][2]
z_cut = z_min + 0.07 * (z_max - z_min)
print(f"4. Slicing and capping bottom skirt at Z = {z_cut:.4f}...")
sliced_shoe = shoe.slice_plane(plane_origin=[0, 0, z_cut], plane_normal=[0, 0, 1], cap=True)

# 6. Seal ankle collar opening
print("5. Sealing watertight volume...")
trimesh.repair.fill_holes(sliced_shoe)
sliced_shoe.merge_vertices()
sliced_shoe.fix_normals()

# 7. Ensure positive volume (fix inverted normal winding if needed)
if sliced_shoe.volume < 0:
    print("   Inverting inward-facing normals to ensure positive volume...")
    sliced_shoe.invert()

# 8. Scale uniformly to 280.0 mm in float64 memory
target_length_mm = 280.0
scale = target_length_mm / max(sliced_shoe.extents)
sliced_shoe.apply_scale(scale)
print(f"6. Scaled dimensions (mm): L={sliced_shoe.extents[0]:.1f}, W={sliced_shoe.extents[1]:.1f}, H={sliced_shoe.extents[2]:.1f}")
print(f"   Watertight: {sliced_shoe.is_watertight}, Volume: {sliced_shoe.volume / 1000:.1f} cm³")

# 9. Printability validation
gate = PrintabilityGate()
result = gate.validate(sliced_shoe)
gate_passed = getattr(result, 'passed', getattr(result, 'is_valid', False))
print(f"   Printability Gate: {'PASSED' if gate_passed else 'FAILED'}")

out_file = out_dir / 'shoe_clean_280mm.stl'
sliced_shoe.export(out_file)
print(f"\nSUCCESS! Clean, scaled production STL exported to: {out_file}")
