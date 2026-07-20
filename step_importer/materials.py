import bpy

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


def apply_material_settings(objects: list, import_materials: bool) -> None:
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