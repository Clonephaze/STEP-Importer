import os
import re
import tempfile
from math import pi, radians

import bpy

from .progress import ViewportProgressBar
from .utils import detect_file_type, cleanup_topology, get_addon_preferences

# Matches Blender’s automatic “.001” / “.002” duplicate-name suffixes.
_BLENDER_SUFFIX = re.compile(r"\.\d{3,}$")


def _find_layer_collection(layer_col, name: str):
    """Recursively find a layer collection by its collection name."""
    if layer_col.name == name:
        return layer_col
    for child in layer_col.children:
        result = _find_layer_collection(child, name)
        if result:
            return result
    return None


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
    with open(filepath, "rb") as file:
        step_bytes = file.read()

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

    kept = []
    for obj in new_objects:
        name = obj.name.lower()
        if any(name.startswith(prefix) for prefix in skip_prefixes):
            bpy.data.objects.remove(obj, do_unlink=True)
        else:
            kept.append(obj)
    return kept


# cascadio/OCCT never writes an explicit metallicFactor/roughnessFactor for
# plain STEP colors, so glTF's un-set default of 1.0/1.0 (fully metallic,
# fully rough) applies on import. Materials still sitting at that default
# are corrected to Blender's Principled BSDF defaults instead.
_GLTF_DEFAULT_METALLIC = 1.0
_GLTF_DEFAULT_ROUGHNESS = 1.0
_BSDF_DEFAULT_METALLIC = 0.0
_BSDF_DEFAULT_ROUGHNESS = 0.5


def _fix_material_pbr_defaults(mat: "bpy.types.Material") -> None:
    """Correct a glTF-imported material left at spec-default Metallic/Roughness.

    Only materials still sitting at glTF's un-set default (1.0/1.0) are
    touched, so any legitimately authored metallic/rough material is left
    alone.
    """
    if not mat.use_nodes or mat.node_tree is None:
        return

    bsdf = next(
        (n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None
    )
    if bsdf is None:
        return

    metallic = bsdf.inputs.get("Metallic")
    roughness = bsdf.inputs.get("Roughness")
    if metallic is None or roughness is None:
        return

    if (
        metallic.default_value == _GLTF_DEFAULT_METALLIC
        and roughness.default_value == _GLTF_DEFAULT_ROUGHNESS
    ):
        metallic.default_value = _BSDF_DEFAULT_METALLIC
        roughness.default_value = _BSDF_DEFAULT_ROUGHNESS


def _strip_materials(objects: list) -> None:
    """Remove all material slots from imported mesh objects."""
    for obj in objects:
        if obj.type == "MESH":
            obj.data.materials.clear()


def _apply_material_settings(objects: list, import_materials: bool) -> None:
    """Apply the add-on's material import policy to freshly imported objects.

    cascadio/OCCT always bakes STEP colors into the GLB regardless of the
    ``import_materials`` setting, so when *import_materials* is False the
    only way to actually disable colored materials is to strip the slots
    here. When True, materials left at glTF's un-set Metallic/Roughness
    default are corrected instead of rendering as dark rough metal.
    """
    if not import_materials:
        _strip_materials(objects)
        return

    seen_materials = set()
    for obj in objects:
        if obj.type != "MESH":
            continue
        for mat in obj.data.materials:
            if mat is None or mat.name in seen_materials:
                continue
            seen_materials.add(mat.name)
            _fix_material_pbr_defaults(mat)


def _tag_objects(objects: list, filepath: str, merged: bool) -> None:
    """Stamp CAD provenance metadata onto each imported mesh object.

    Stores the source file path and the GLB node name (with Blender’s
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


def _apply_shading_state(objects: list, smooth: bool) -> None:
    """Set flat/smooth shading on *objects*, matching *smooth*.

    Used by the regenerate pipeline to restore each object's own prior
    shading state instead of applying the current global shade_smooth
    preference — shading is something the user can toggle per-object via
    the right-click menu, so regenerate should never override it.
    """
    for obj in objects:
        if obj.type != "MESH":
            continue
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        if smooth:
            bpy.ops.object.shade_smooth_by_angle(angle=radians(30))
        else:
            bpy.ops.object.shade_flat()


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
        _apply_material_settings(new_objects, prefs.import_materials)
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


def regenerate_parts(
    objects,
    tol_linear: float,
    tol_angular: float,
    tol_relative: bool,
    import_materials: bool,
) -> tuple:
    """Re-tessellate all eligible objects in *objects*, loading each source
    file only once regardless of how many parts share it.

    Returns ``(success_count: int, errors: list[str])``.
    """
    eligible = [
        obj
        for obj in objects
        if obj.type == "MESH"
        and "step_source_file" in obj
        and "step_node_path" in obj
        and obj["step_node_path"] != "__merged__"
    ]

    if not eligible:
        return 0, ["No eligible STEP objects in selection"]

    prefs = get_addon_preferences(bpy.context)

    original_active = bpy.context.view_layer.objects.active
    original_mode = original_active.mode if original_active else "OBJECT"
    if original_mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")

    try:
        return _regenerate_parts_impl(
            eligible, tol_linear, tol_angular, tol_relative, import_materials, prefs
        )
    finally:
        if (
            original_mode != "OBJECT"
            and original_active
            and original_active.name in bpy.data.objects
        ):
            bpy.context.view_layer.objects.active = original_active
            bpy.ops.object.mode_set(mode=original_mode)


def regenerate_part(
    obj: "bpy.types.Object",
    tol_linear: float,
    tol_angular: float,
    tol_relative: bool,
    import_materials: bool,
) -> tuple:
    """Re-tessellate a single object. Convenience wrapper around
    :func:`regenerate_parts`.

    Returns ``(success: bool, message: str)``.
    """
    count, errors = regenerate_parts(
        [obj], tol_linear, tol_angular, tol_relative, import_materials
    )
    if count == 1:
        return True, f"Regenerated '{obj.name}'"
    return False, errors[0] if errors else "Unknown error"


def _regenerate_parts_impl(
    eligible, tol_linear, tol_angular, tol_relative, import_materials, prefs
):
    from types import SimpleNamespace

    tol_ns = SimpleNamespace(
        import_materials=import_materials,
        tol_linear=tol_linear,
        tol_angular=tol_angular,
        tol_relative=tol_relative,
        shade_smooth=prefs.shade_smooth,
    )

    # Group by source file so each file is loaded only once.
    by_source = {}
    for obj in eligible:
        by_source.setdefault(obj["step_source_file"], []).append(obj)

    success_count = 0
    errors = []

    for source_file, file_objects in by_source.items():
        if not os.path.isfile(source_file):
            for obj in file_objects:
                errors.append(f"'{obj.name}': source file not found")
            continue

        file_count, file_errors = _regenerate_file_batch(
            source_file, file_objects, tol_ns, prefs
        )
        success_count += file_count
        errors.extend(file_errors)

    return success_count, errors


def _mesh_bbox_center(mesh):
    """Return the axis-aligned bounding box centre of *mesh* in local space."""
    from mathutils import Vector
    import numpy as np # type: ignore

    if not mesh.vertices:
        return Vector((0.0, 0.0, 0.0))

    coords = np.empty(len(mesh.vertices) * 3, dtype=np.float64)
    mesh.vertices.foreach_get("co", coords)
    coords = coords.reshape(-1, 3)
    center = (coords.min(axis=0) + coords.max(axis=0)) * 0.5
    return Vector(center.tolist())


def _regenerate_file_batch(source_file, objects, tol_ns, prefs):
    """Load *source_file* once and swap mesh data for every object in *objects*."""
    errors = []
    filename = os.path.basename(source_file)

    with ViewportProgressBar(bpy.context, filename) as bar:
        bar.update(0.05, "Reading file")
        glb_bytes = _convert_to_glb(source_file, tol_ns)

        scratch = bpy.data.collections.new("__step_regen_scratch__")
        bpy.context.scene.collection.children.link(scratch)
        scratch.hide_viewport = True

        try:
            layer_col = _find_layer_collection(
                bpy.context.view_layer.layer_collection, scratch.name
            )
            prev_active = bpy.context.view_layer.active_layer_collection
            bpy.context.view_layer.active_layer_collection = layer_col

            bar.update(0.60, "Importing to scene")
            try:
                new_objects = _import_glb(glb_bytes, tol_ns)
            finally:
                bpy.context.view_layer.active_layer_collection = prev_active

            # Build a node-name -> mesh-object lookup from the scratch import.
            scratch_by_node = {
                _BLENDER_SUFFIX.sub("", o.name): o
                for o in new_objects
                if o.type == "MESH"
            }

            bar.update(0.75, "Applying changes")

            swapped = []
            keep_materials = []
            drop_materials = []
            smooth_objects = []
            flat_objects = []
            for obj in objects:
                node_path = obj["step_node_path"]
                match = scratch_by_node.get(node_path)
                if match is None:
                    errors.append(
                        f"'{obj.name}': node '{node_path}' not found in re-import"
                    )
                    continue

                old_mesh = obj.data
                old_local_center = _mesh_bbox_center(old_mesh)
                # Preserve this object's own material and shading state rather
                # than the global import_materials/shade_smooth toggles — an
                # object regenerated materialless/flat (or given materials/
                # smoothed) should stay that way regardless of what settings
                # were last used to import.
                had_materials = any(old_mesh.materials)
                was_smooth = bool(old_mesh.polygons) and old_mesh.polygons[0].use_smooth

                obj.data = match.data
                obj.data.name = old_mesh.name
                if old_mesh.users == 0:
                    bpy.data.meshes.remove(old_mesh)

                # Compensate for any origin offset the user applied before regenerating.
                # Adjusting matrix_world by the delta keeps the geometry visually in place.
                new_local_center = _mesh_bbox_center(obj.data)
                delta = new_local_center - old_local_center
                if delta.length_squared > 1e-12:
                    from mathutils import Matrix

                    obj.matrix_world = obj.matrix_world @ Matrix.Translation(
                        (-delta).to_tuple()
                    )

                swapped.append(obj)
                (keep_materials if had_materials else drop_materials).append(obj)
                (smooth_objects if was_smooth else flat_objects).append(obj)

            _apply_material_settings(keep_materials, True)
            _apply_material_settings(drop_materials, False)

            bar.update(0.90, "Post-processing")
            _apply_shading_state(smooth_objects, True)
            _apply_shading_state(flat_objects, False)
        finally:
            for leftover in list(scratch.objects):
                bpy.data.objects.remove(leftover, do_unlink=True)
            bpy.data.collections.remove(scratch)

    return len(swapped), errors
