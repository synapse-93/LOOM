import trimesh

def apply_mesh_scale(mesh: trimesh.Trimesh, scale_factor: float) -> trimesh.Trimesh:
    """
    Multiplies all 3D mesh coordinate vertices by scale factor 's'.
    Returns a new scaled copy of the mesh.
    """
    scaled_mesh = mesh.copy()
    scaled_mesh.apply_scale(scale_factor)
    return scaled_mesh