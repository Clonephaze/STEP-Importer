"""Material handling for STEP imports.

cascadio.load(include_materials=True) embeds glTF PBR material data in the
GLB output. Blender's built-in glTF importer processes those automatically,
so standard base_color/metallic/roughness values come through without any
extra work here.

This module exists for cascadio-specific extras that the glTF importer
ignores — primarily PhysicalMaterial metadata (density, etc.) which cascadio
stores in GLB mesh extras. Those are surfaced here as Blender custom
properties so users can query them via Python or the Properties panel.
"""

import bpy


def apply_physical_properties(objects: list, glb_bytes: bytes) -> None:
    """Parse cascadio PhysicalMaterial metadata from GLB extras and store it
    as custom properties on the corresponding Blender objects.

    Not yet implemented — to be filled in once cascadio's material extras
    format is finalised upstream.
    """
    pass
