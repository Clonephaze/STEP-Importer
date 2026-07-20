"""
Utility functions shared by importer.py and regenerate.py
"""
import bpy
import re
import tempfile
import os

from .utils import detect_file_type

# Matches Blender's automatic ".001" / ".002" duplicate-name suffixes.
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