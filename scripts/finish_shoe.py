import trimesh
import numpy as np
from pathlib import Path
from loom.printability.gate import PrintabilityGate

in_stl = Path("outputs/stl/shoe_production_master_280mm.stl")
out_dir = Path("outputs/stl")
out_stl = out_dir / "shoe_final_ready_to_print_280mm.stl"

print(f"1. Loading 891k-face mesh ({in_stl})...")
mesh = trimesh.load(in_stl)
print(f"   Vertices: {len(mesh.vertices):,}, Faces: {len(mesh.faces):,}")

# Z = 0 is the flat ankle cap
# Z = max is the jagged floor skirt
z_min, z_max = mesh.bounds[0][2], mesh.bounds[1][2]
total_h = z_max - z_min

# 2. Slice off the jagged floor skirt (top 11% of current inverted height)
# plane_normal=[0, 0, -1] keeps everything BELOW z_cut (the real shoe)
z_sole_cut = z_max - 0.11 * total_h
print(f"2. Slicing floor skirt at Z = {z_sole_cut:.2f} mm...")
clean_shoe = mesh.slice_plane(plane_origin=[0, 0, z_sole_cut], plane_normal=[0, 0, -1], cap=True)

# 3. Flip 180 degrees around X axis so sole is at bottom (Z=0) and laces face UP
print("3. Flipping model right-side up...")
R_flip = trimesh.transformations.rotation_matrix(np.pi, [1, 0, 0])
clean_shoe.apply_transform(R_flip)

# 4. Snap flat sole flush to Z = 0.0 and center on XY
clean_shoe.vertices[:, 2] -= clean_shoe.bounds[0][2]
clean_shoe.vertices[:, :2] -= clean_shoe.bounds.mean(axis=0)[:2]

# 5. Fix normal winding and scale uniformly to 280.0 mm
print("4. Scaling to 280.0 mm and checking normals...")
clean_shoe.fix_normals()
if clean_shoe.volume < 0:
    clean_shoe.invert()

scale = 280.0 / max(clean_shoe.extents)
clean_shoe.apply_scale(scale)
clean_shoe.vertices[:, 2] -= clean_shoe.bounds[0][2]

print(f"\nFinal Dimensions (mm): L={clean_shoe.extents[0]:.1f}, W={clean_shoe.extents[1]:.1f}, H={clean_shoe.extents[2]:.1f}")
print(f"Watertight: {clean_shoe.is_watertight}, Volume: {clean_shoe.volume / 1000:.1f} cm³")

# 6. Validate with Printability Gate
gate = PrintabilityGate()
res = gate.validate(clean_shoe)
passed = getattr(res, 'passed', getattr(res, 'is_valid', False))
print(f"Printability Gate: {'PASSED' if passed else 'FAILED'}")

clean_shoe.export(out_stl)
print(f"\nSUCCESS! Production-ready STL exported to: {out_stl}")
