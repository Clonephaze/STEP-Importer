import bpy
import os

from math import radians

from .import_utils import _BLENDER_SUFFIX, _convert_to_glb, _find_layer_collection, _import_glb
from .progress import ViewportProgressBar
from .utils import get_addon_preferences
from .materials import apply_material_settings

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

            apply_material_settings(keep_materials, True)
            apply_material_settings(drop_materials, False)

            bar.update(0.90, "Post-processing")
            _apply_shading_state(smooth_objects, True)
            _apply_shading_state(flat_objects, False)
        finally:
            for leftover in list(scratch.objects):
                bpy.data.objects.remove(leftover, do_unlink=True)
            bpy.data.collections.remove(scratch)

    return len(swapped), errors


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

def _mesh_bbox_center(mesh):
    """Return the axis-aligned bounding box centre of *mesh* in local space."""
    from mathutils import Vector
    import numpy as np  # type: ignore

    if not mesh.vertices:
        return Vector((0.0, 0.0, 0.0))

    coords = np.empty(len(mesh.vertices) * 3, dtype=np.float64)
    mesh.vertices.foreach_get("co", coords)
    coords = coords.reshape(-1, 3)
    center = (coords.min(axis=0) + coords.max(axis=0)) * 0.5
    return Vector(center.tolist())