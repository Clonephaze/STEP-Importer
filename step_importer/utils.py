import os

_STEP_EXTENSIONS = frozenset({".step", ".stp"})
_IGES_EXTENSIONS = frozenset({".iges", ".igs"})


def detect_file_type(filepath: str) -> str:
    """Return ``'step'`` or ``'iges'`` based on *filepath*'s extension."""
    ext = os.path.splitext(filepath)[1].lower()
    if ext in _STEP_EXTENSIONS:
        return "step"
    if ext in _IGES_EXTENSIONS:
        return "iges"
    raise ValueError(f"Unrecognised file extension: {ext!r}")


def cascadio_available() -> bool:
    """Return ``True`` if cascadio is importable (wheels are bundled)."""
    try:
        import cascadio  # noqa: F401

        return True
    except ImportError:
        return False


def cleanup_topology(
    objects, remove_doubles=True, doubles_dist=0.0001, dissolve=True, temp_sharp=True, dissolve_angle=0.5
):
    """
    Perform cleanup operations on the imported objects to fix common issues with STEP meshes.
    
    Args:
        objects: Iterable of Blender objects to clean up.
        remove_doubles: If True, remove duplicate vertices that are very close together.
        doubles_dist: Distance threshold for removing duplicate vertices.
        dissolve: If True, dissolve coplanar faces to simplify the mesh.
        temp_sharp: If True, temporarily marks sharp edges before dissolving coplanar faces, useful if geometry already has marked sharp edges.
        dissolve_angle: Angle threshold (in degrees) for dissolving coplanar faces.
    """
    import bmesh
    import math

    for obj in objects:
        if obj.type != "MESH":
            continue

        mesh = obj.data
        bm = bmesh.new()
        bm.from_mesh(mesh)

        try:
            if remove_doubles:
                bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=doubles_dist)

            if dissolve:
                if temp_sharp:
                    # Mark sharp edges by angle before dissolve needs them
                    for edge in bm.edges:
                        if len(edge.link_faces) == 2:
                            angle = edge.calc_face_angle(None)
                            if angle is not None and angle > math.radians(45):
                                edge.smooth = False
                        else:
                            edge.smooth = False

                bmesh.ops.dissolve_limit(
                    bm,
                    angle_limit=math.radians(dissolve_angle),
                    use_dissolve_boundaries=False,
                    delimit={"SHARP"},
                    verts=bm.verts,
                    edges=bm.edges,
                )
                if temp_sharp:
                    for edge in bm.edges:
                        edge.smooth = True
        finally:
            bm.to_mesh(mesh)
            bm.free()
            mesh.update()
