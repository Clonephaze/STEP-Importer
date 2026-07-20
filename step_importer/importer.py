import os
from math import pi, radians

import bpy
from mathutils import Vector

from .import_utils import _BLENDER_SUFFIX, _convert_to_glb, _import_glb
from .progress import ViewportProgressBar
from .utils import cleanup_topology, get_addon_preferences
from .materials import apply_material_settings


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

    kept = []
    for obj in new_objects:
        name = obj.name.lower()
        if any(name.startswith(prefix) for prefix in skip_prefixes):
            bpy.data.objects.remove(obj, do_unlink=True)
        else:
            kept.append(obj)
    return kept


def _tag_objects(objects: list, filepath: str, merged: bool) -> None:
    """Stamp CAD provenance metadata onto each imported mesh object.

    Stores the source file path and the GLB node name (with Blender's
    automatic numeric suffixes stripped) so the regenerate operator can
    match the object after a re-import regardless of name conflicts.
    Merged objects receive a sentinel path because they have no stable
    single-node identity.
    """
    for obj in objects:
        if obj.type != "MESH":
            continue
        obj["step_source_file"] = filepath
        obj["step_node_path"] = (
            "__merged__" if merged else _BLENDER_SUFFIX.sub("", obj.name)
        )


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


def _apply_correction(
    new_objects: list, up_axis: str, rotation_deg: float, scale: float = 1.0
) -> None:
    """Apply axis correction matrix to all imported objects.

    Args:
        new_objects: List of imported objects to correct.
        up_axis: Which axis of the source model is "up".
        rotation_deg: Additional rotation in degrees around Blender's +Z.
        scale: Uniform scale multiplier applied after orientation correction.
    """
    from mathutils import Matrix

    correction = _build_correction(up_axis, rotation_deg)
    if scale != 1.0:
        correction = Matrix.Scale(scale, 4) @ correction
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
    """Apply shading and topology cleanup to freshly imported objects.

    Only used by the initial import pipeline — the regenerate pipeline
    restores each object's own prior shading/cleanup state directly instead
    of applying these global preferences (see `_apply_shading_state`).

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


def _build_assembly_collections(new_objects: list, root_col) -> None:
    """Organise imported objects into nested Blender collections mirroring
    the CAD assembly hierarchy.

    The glTF importer parents child objects to Empty objects for non-mesh
    assembly nodes.  This function walks that hierarchy and creates a
    matching nested collection structure, then re-links each object into
    the appropriate collection.
    """
    new_set = set(new_objects)
    col_cache: dict = {}  # id(empty_obj) → bpy.types.Collection

    def _col_for_empty(empty):
        eid = id(empty)
        if eid in col_cache:
            return col_cache[eid]
        parent_col = _parent_col_of(empty)
        col = bpy.data.collections.new(empty.name)
        parent_col.children.link(col)
        col_cache[eid] = col
        _relink(empty, col)
        return col

    def _parent_col_of(obj):
        p = obj.parent
        if p is None or p not in new_set:
            return root_col
        if p.type == "EMPTY":
            return _col_for_empty(p)
        return _parent_col_of(p)

    def _relink(obj, target):
        for c in list(obj.users_collection):
            c.objects.unlink(obj)
        target.objects.link(obj)

    for obj in new_objects:
        if obj.type == "EMPTY":
            _col_for_empty(obj)
        else:
            target = _parent_col_of(obj)
            if target is not root_col:
                _relink(obj, target)


def import_step(
    filepath: str,
    up_axis: str = "Y",
    rotation_deg: float = 0.0,
    merge_objects: bool = False,
    skip_prefixes: frozenset = frozenset(),
    label: str | None = None,
    placement: str = "ORIGIN",
    use_assembly_collections: bool = False,
    scale: float = 1.0,
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
        label:        Override the progress bar title (used for multi-file batches).
        placement:    "ORIGIN" leaves objects at world origin; "CURSOR" offsets them
                      to the current 3D cursor position.
        use_assembly_collections: When True, imported objects are organised into
                      nested collections matching the STEP assembly hierarchy.
        scale:        Uniform scale multiplier applied to the imported geometry. 
                      Use 1000 if the model imports as millimetre-sized when it 
                      should be metres, or 0.001 for the reverse.
    """
    prefs = get_addon_preferences(bpy.context)
    filename = label if label is not None else os.path.basename(filepath)

    with ViewportProgressBar(bpy.context, filename) as bar:
        bar.update(0.05, "Reading file")
        glb_bytes = _convert_to_glb(filepath, prefs)

        post_import_value = 0.60 if prefs.cleanup_topology else 0.80
        bar.update(post_import_value, "Importing to scene")
        new_objects = _import_glb(glb_bytes, prefs)

        new_objects = _filter_objects(new_objects, skip_prefixes)
        apply_material_settings(new_objects, prefs.import_materials)
        _apply_correction(new_objects, up_axis, rotation_deg, scale)

        if placement == "CURSOR":
            from mathutils import Matrix

            cursor_loc = bpy.context.scene.cursor.location
            offset = Matrix.Translation(cursor_loc)
            for obj in new_objects:
                obj.matrix_world = offset @ obj.matrix_world

        if use_assembly_collections and not merge_objects and new_objects:
            root_col = bpy.context.view_layer.active_layer_collection.collection
            _build_assembly_collections(new_objects, root_col)

        if prefs.shade_smooth or prefs.cleanup_topology:
            bar.update(0.80, "Post-processing")
            _post_process(new_objects, prefs)

        if merge_objects:
            new_objects = _merge_objects(new_objects)

        _tag_objects(new_objects, filepath, merge_objects)
