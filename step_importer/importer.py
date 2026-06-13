import os
import tempfile

import bpy

from .progress import ViewportProgressBar
from .utils import detect_file_type


def import_step(
    filepath: str,
    forward_axis: str = "MINUS_Z",
    up_axis: str = "Y",
    merge_objects: bool = False,
) -> None:
    """Convert a STEP/IGES file and import it into the current Blender scene.

    Pipeline:
        1. Read file bytes          (progress: 5%)
        2. cascadio: STEP → GLB    (progress: 70%)
        3. Write temp GLB file      (progress: 80%)
        4. bpy.ops.import_scene.gltf (progress: 100%)

    Args:
        filepath:      Absolute path to the STEP/IGES file.
        forward_axis:  Forward axis passed to the glTF importer.
                       Defaults to ``MINUS_Z`` (glTF/Blender standard).
        up_axis:       Up axis passed to the glTF importer.
                       Defaults to ``Y`` (glTF standard — Y-up).
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
            bpy.ops.import_scene.gltf(
                filepath=tmp_path,
                forward_axis=forward_axis,
                up_axis=up_axis,
            )
        finally:
            os.unlink(tmp_path)

        if merge_objects:
            new_objects = [
                o for o in bpy.context.scene.objects
                if o not in objects_before and o.type == "MESH"
            ]
            if len(new_objects) > 1:
                bpy.ops.object.select_all(action="DESELECT")
                for obj in new_objects:
                    obj.select_set(True)
                bpy.context.view_layer.objects.active = new_objects[0]
                bpy.ops.object.join()

