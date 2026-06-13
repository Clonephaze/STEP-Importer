import os
import tempfile
from math import pi, radians

import bpy

from .progress import ViewportProgressBar
from .utils import detect_file_type


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


def import_step(
    filepath: str,
    up_axis: str = "Y",
    rotation_deg: float = 0.0,
    merge_objects: bool = False,
    skip_prefixes: frozenset = frozenset(),
) -> None:
    """Convert a STEP/IGES file and import it into the current Blender scene.

    Pipeline:
        1. Read file bytes          (progress: 5%)
        2. cascadio: STEP → GLB    (progress: 70%)
        3. Write temp GLB file      (progress: 80%)
        4. bpy.ops.import_scene.gltf (progress: 100%)

    Args:
        filepath:     Absolute path to the STEP/IGES file.
        up_axis:      Which axis of the source model is "up" (mapped to Blender +Z).
                      ``Y`` matches cascadio's Y-up GLB output (default).
                      ``Z`` means no correction (use when the source is already Z-up).
        rotation_deg: Additional rotation in degrees around Blender's +Z axis after
                      the up-axis correction has been applied.
        merge_objects: When True, all imported bodies are joined into a
                       single mesh object after import.
    """
    import cascadio  # deferred: wheel installed by Blender extension system

    prefs = bpy.context.preferences.addons[__package__].preferences
    file_type = detect_file_type(filepath)
    filename = os.path.basename(filepath)

    with ViewportProgressBar(bpy.context, filename) as bar:
        bar.update(0.05, "Reading file")
        step_bytes = open(filepath, "rb").read()

        bar.update(0.10, "Converting STEP \u2192 GLB")
        glb_bytes = cascadio.load(
            step_bytes,
            file_type=file_type,
            include_materials=prefs.import_materials,
        )

        bar.update(0.80, "Importing to scene")
        with tempfile.NamedTemporaryFile(suffix=".glb", delete=False) as tmp:
            tmp.write(glb_bytes)
            tmp_path = tmp.name

        try:
            objects_before = set(bpy.context.scene.objects)
            bpy.ops.import_scene.gltf(filepath=tmp_path)
        finally:
            os.unlink(tmp_path)

        new_objects = [
            obj for obj in bpy.context.scene.objects if obj not in objects_before
        ]

        # Remove construction geometry by name prefix before doing anything else, to avoid accidentally merging it into the main meshes. This is a bit hacky but cascadio doesn't currently provide any other way to filter out construction geometry that I can find.
        if skip_prefixes:
            to_remove = [
                obj
                for obj in new_objects
                if any(obj.name.lower().startswith(p) for p in skip_prefixes)
            ]
            for obj in to_remove:
                new_objects.remove(obj)
                bpy.data.objects.remove(obj, do_unlink=True)

        correction = _build_correction(up_axis, rotation_deg)
        for obj in new_objects:
            obj.matrix_world = correction @ obj.matrix_world

        if merge_objects:
            mesh_objects = [obj for obj in new_objects if obj.type == "MESH"]
            if len(mesh_objects) > 1:
                bpy.ops.object.select_all(action="DESELECT")
                for obj in mesh_objects:
                    obj.select_set(True)
                bpy.context.view_layer.objects.active = mesh_objects[0]
                bpy.ops.object.join()
