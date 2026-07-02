import os
from typing import Literal

_STEP_EXTENSIONS = frozenset({".step", ".stp"})
_IGES_EXTENSIONS = frozenset({".iges", ".igs"})
_AXIS_ITEMS = [
    ("X", "X", ""),
    ("Y", "Y", ""),
    ("Z", "Z", ""),
    ("MINUS_X", "-X", ""),
    ("MINUS_Y", "-Y", ""),
    ("MINUS_Z", "-Z", ""),
]


_ROTATION_ITEMS = [
    ("-90", "-90°", "Rotate 90° counter-clockwise"),
    ("0", "0°", "No rotation"),
    ("90", "90°", "Rotate 90° clockwise"),
    ("180", "180°", "Rotate 180°"),
]


def detect_file_type(filepath: str) -> Literal["step", "iges"]:
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


def get_addon_preferences(context=None):
    """Return this add-on's preferences, raising a friendly error if unavailable.

    Args:
        context: A ``bpy.context``-like object exposing ``preferences.addons``.
            Defaults to ``bpy.context`` when not given.

    Raises:
        RuntimeError: If the add-on isn't registered/enabled, instead of a
            raw ``KeyError`` from indexing ``preferences.addons`` directly.
    """
    import bpy

    context = context or bpy.context
    entry = context.preferences.addons.get(__package__)
    if entry is None:
        raise RuntimeError(
            f"STEP Importer preferences not found (no '{__package__}' entry in "
            "bpy.context.preferences.addons)"
        )
    return entry.preferences


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
                bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=doubles_dist)

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
                    verts=list(bm.verts),
                    edges=list(bm.edges),
                )
                if temp_sharp:
                    for edge in bm.edges:
                        edge.smooth = True
        finally:
            bm.to_mesh(mesh)
            bm.free()
            mesh.update()
