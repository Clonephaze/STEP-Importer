import os
import tempfile
from math import pi, radians

import bpy

from .progress import ViewportProgressBar
from .utils import detect_file_type, cleanup_topology


def _convert_to_glb(filepath: str, prefs) -> bytes:
    """Read a STEP/IGES file and convert it to GLB bytes via cascadio.

    Args:
        filepath: Absolute path to the STEP/IGES file.
        prefs: Add-on preferences containing tolerance and material settings.

    Returns:
        GLB file content as bytes.
    """
    import cascadio

    file_type = detect_file_type(filepath)
    step_bytes = open(filepath, "rb").read()

    return cascadio.load(
        step_bytes,
        file_type=file_type,
        include_materials=prefs.import_materials,
        tol_linear=prefs.tol_linear,
        tol_angular=prefs.tol_angular,
        tol_relative=prefs.tol_relative,
        node_name_format=cascadio.NodeNameFormat.PRODUCT_OR_INSTANCE,
    )


def _import_glb(glb_bytes: bytes, prefs) -> list:
    """Write GLB bytes to a temp file and import into Blender.

    Args:
        glb_bytes: GLB file content as bytes.
        prefs: Add-on preferences containing shading settings.

    Returns:
        List of all newly created Blender objects.
    """
    with tempfile.NamedTemporaryFile(suffix=".glb", delete=False) as tmp:
        tmp.write(glb_bytes)
        tmp_path = tmp.name

    try:
        objects_before = set(bpy.context.scene.objects)
        bpy.ops.import_scene.gltf(
            filepath=tmp_path,
            import_shading="SMOOTH" if prefs.shade_smooth else "FLAT",
            merge_vertices=True,
        )
    finally:
        os.unlink(tmp_path)

    return [obj for obj in bpy.context.scene.objects if obj not in objects_before]


def _filter_objects(new_objects: list, skip_prefixes: frozenset) -> list:
    """Remove construction geometry by name prefix.

    Args:
        new_objects: List of newly imported objects.
        skip_prefixes: Set of lowercase name prefixes to remove.

    Returns:
        Filtered list with construction geometry removed.
    """
    if not skip_prefixes:
        return new_objects

    to_remove = [
        obj
        for obj in new_objects
        if any(obj.name.lower().startswith(p) for p in skip_prefixes)
    ]
    for obj in to_remove:
        new_objects.remove(obj)
        bpy.data.objects.remove(obj, do_unlink=True)

    return new_objects


def _build_correction(up_axis: str, rotation_deg: float):
    """Return a 4x4 matrix that orients imported objects into Blender's Z-up space.

    up_axis      - which axis of the source model is "up" (should become Blender +Z).
    rotation_deg - additional spin (degrees) around Blender's +Z after up correction.
    """
    from mathutils import Matrix

    half = pi / 2
    up_corrections = {
        "Z": Matrix.Identity(4),
        "MINUS_Z": Matrix.Rotation(pi, 4, "X"),
        "Y": Matrix.Rotation(-half, 4, "X"),
        "MINUS_Y": Matrix.Rotation(half, 4, "X"),
        "X": Matrix.Rotation(half, 4, "Y"),
        "MINUS_X": Matrix.Rotation(-half, 4, "Y"),
    }
    up_mat = up_corrections.get(up_axis, Matrix.Identity(4))
    spin = Matrix.Rotation(radians(rotation_deg), 4, "Z")
    return spin @ up_mat


def _apply_correction(new_objects: list, up_axis: str, rotation_deg: float) -> None:
    """Apply axis correction matrix to all imported objects.

    Args:
        new_objects: List of imported objects to correct.
        up_axis: Which axis of the source model is "up".
        rotation_deg: Additional rotation in degrees around Blender's +Z.
    """
    correction = _build_correction(up_axis, rotation_deg)
    for obj in new_objects:
        obj.matrix_world = correction @ obj.matrix_world


def _merge_objects(new_objects: list) -> list:
    mesh_objects = [obj for obj in new_objects if obj.type == "MESH"]
    non_mesh_objects = [obj for obj in new_objects if obj.type != "MESH"]

    if len(mesh_objects) > 1:
        bpy.ops.object.select_all(action="DESELECT")
        for obj in mesh_objects:
            obj.select_set(True)
        bpy.context.view_layer.objects.active = mesh_objects[0]
        bpy.ops.object.join()
        bpy.context.view_layer.update()  # ensure join is fully resolved

        joined = bpy.context.view_layer.objects.active
        return non_mesh_objects + ([joined] if joined else [])

    return new_objects


def _post_process(new_objects: list, prefs) -> None:
    """Apply shading and topology cleanup to imported objects.

    Args:
        new_objects: List of imported objects to process.
        prefs: Add-on preferences containing shading and cleanup settings.
    """
    if prefs.shade_smooth:
        for obj in new_objects:
            if obj.type != "MESH":
                continue
            bpy.context.view_layer.objects.active = obj
            obj.select_set(True)
            bpy.ops.object.shade_smooth_by_angle(angle=radians(30))

    if prefs.cleanup_topology:
        should_mark_sharp = not prefs.shade_smooth
        cleanup_topology(
            new_objects,
            remove_doubles=prefs.ct_doubles,
            doubles_dist=prefs.ct_doubles_dist,
            dissolve=prefs.ct_dissolve,
            dissolve_angle=prefs.ct_dissolve_angle,
            temp_sharp=should_mark_sharp,
        )


def import_step(
    filepath: str,
    up_axis: str = "Y",
    rotation_deg: float = 0.0,
    merge_objects: bool = False,
    skip_prefixes: frozenset = frozenset(),
) -> None:
    """Convert a STEP/IGES file and import it into the current Blender scene.

    Pipeline:
        1. Read file bytes and convert to GLB
        2. Import GLB into Blender scene
        3. Filter construction geometry
        4. Apply axis correction
        5. Merge objects (optional)
        6. Post-process shading and cleanup
    Args:
        filepath:     Absolute path to the STEP/IGES file.
        up_axis:      Which axis of the source model is "up" (mapped to Blender +Z).
        rotation_deg: Additional rotation in degrees around Blender's +Z axis.
        merge_objects: When True, all imported bodies are joined into one mesh.
        skip_prefixes: Lowercase name prefixes of construction geometry to remove.
    """
    prefs = bpy.context.preferences.addons[__package__].preferences
    filename = os.path.basename(filepath)

    with ViewportProgressBar(bpy.context, filename) as bar:
        bar.update(0.05, "Reading file")
        glb_bytes = _convert_to_glb(filepath, prefs)

        post_import_value = 0.60 if prefs.cleanup_topology else 0.80
        bar.update(post_import_value, "Importing to scene")
        new_objects = _import_glb(glb_bytes, prefs)

        new_objects = _filter_objects(new_objects, skip_prefixes)
        _apply_correction(new_objects, up_axis, rotation_deg)

        if prefs.shade_smooth or prefs.cleanup_topology:
            bar.update(0.80, "Post-processing")
            _post_process(new_objects, prefs)

        if merge_objects:
            new_objects = _merge_objects(new_objects)
