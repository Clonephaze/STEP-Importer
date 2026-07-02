import bpy
from bpy.types import AddonPreferences
from bpy.props import BoolProperty, EnumProperty, FloatProperty
from .utils import _AXIS_ITEMS, _ROTATION_ITEMS

QUALITY_PRESET_ITEMS = [
    ("DRAFT",      "Draft",      "Fast tessellation with low triangle count, visible faceting on curves"),
    ("BALANCED",   "Balanced",   "Good quality with moderate triangle count"),
    ("FINE",       "Fine",       "High quality, slower but good for hero parts or close-ups"),
    ("ULTRA_FINE", "Ultra Fine", "Maximum quality, slowest but best for extreme close-ups"),
    ("CUSTOM",     "Custom",     "Manually set linear and angular tolerances"),
]

QUALITY_PRESETS = {
    "DRAFT":      (0.05, 0.6),
    "BALANCED":   (0.01, 0.25),
    "FINE":       (0.002, 0.1),
    "ULTRA_FINE": (0.0005, 0.05),
}


def _apply_preset(self, context):
    if self.tol_preset in QUALITY_PRESETS:
        linear, angular = QUALITY_PRESETS[self.tol_preset]
        self.tol_linear = linear
        self.tol_angular = angular


class STEPImporterPreferences(AddonPreferences):
    bl_idname = __package__

    import_materials: BoolProperty(
        name="Import Materials",
        description="Apply material colors from STEP file when available",
        default=True,
    )

    default_up_axis: EnumProperty(
        name="Source Up Axis",
        description="Which axis pointed up in the CAD application this model came from. Usually Y for most CAD software. Switch to Z if your model appears lying on it's side after import",
        items=_AXIS_ITEMS,
        default="Y",
    )

    default_rotation: EnumProperty(
        name="Default Rotation",
        description="Default rotation around the vertical axis after up-axis correction",
        items=_ROTATION_ITEMS,
        default="0",
    )

    tol_linear: bpy.props.FloatProperty(
        name="Linear Tolerance",
        description="Maximum distance between the mesh and the true CAD surface. In relative mode, expressed as a fraction of each edge's length. Lower values produce smoother geometry with more triangles.",
        default=0.01,
        min=0.001,
    )

    tol_angular: bpy.props.FloatProperty(
        name="Angular Tolerance",
        description="Maximum angle between adjacent triangles in radians. Controls curve smoothness independent of part size — lower values keep curves smooth on both large and small features.",
        default=0.5,
        min=0.001,
    )

    tol_relative: BoolProperty(
        name="Relative Tolerance",
        description="When True, scale linear tolerance to each feature's size rather than using a fixed world-space distance. Recommended for assemblies with mixed part sizes.",
        default=True,
    )

    tol_preset: EnumProperty(
        name="Quality Preset",
        description="Tessellation quality; higher quality produces smoother curves with more triangles",
        items=QUALITY_PRESET_ITEMS,
        default="BALANCED",
        update=_apply_preset,
    )

    shade_smooth: BoolProperty(
        name="Shade Smooth",
        description="Automatically shade smooth imported meshes.",
        default=True,
    )

    cleanup_topology: BoolProperty(
        name="Clean Up Topology",
        description="Cleanup of imported topology (remove doubles, merge nearby vertices, etc). May increase import time but can help with messy STEP files.",
        default=False,
    )

    ct_doubles: BoolProperty(
        name="Remove Doubles",
        description="Remove duplicate vertices that are very close together.",
        default=True,
    )

    ct_doubles_dist: bpy.props.FloatProperty(
        name="Doubles Distance",
        description="Distance threshold for removing duplicate vertices.",
        precision=5,
        default=0.0001,
        min=0.00001,
        max=1.0,
    )

    ct_dissolve: BoolProperty(
        name="Dissolve Faces",
        description="Dissolve coplanar faces to simplify the mesh.",
        default=True,
    )

    ct_dissolve_angle: bpy.props.FloatProperty(
        name="Dissolve Angle",
        description="Angle threshold (in degrees) for dissolving coplanar faces.",
        default=0.5,
        min=0.1,
        max=180.0,
    )

    show_progress: BoolProperty(
        name="Show Import Progress",
        description="Display a GPU progress bar in the 3D viewport during import",
        default=True,
    )

    default_placement: EnumProperty(
        name="Default Placement",
        description="Where to place imported objects in the scene",
        items=[
            ("ORIGIN", "World Origin", "Place at Blender world origin"),
            ("CURSOR", "3D Cursor", "Place at the current 3D cursor position"),
        ],
        default="ORIGIN",
    )

    default_scale: FloatProperty(
        name="Default Scale",
        description="Uniform scale multiplier applied to imported geometry. Use 1000 if a model that should be metres imports as millimetres, or 0.001 if a model that should be millimetres imports as metres.",
        default=1.0,
        min=0.0001,
        max=10000.0,
        soft_min=0.001,
        soft_max=1000.0,
    )

    use_assembly_collections: BoolProperty(
        name="Assembly Collections",
        description="Organise imported parts into nested Blender collections matching the STEP assembly hierarchy",
        default=False,
    )

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        # ── Default Transforms ────────────────────────────────────────────────
        layout.label(text="Default Transforms")
        layout.prop(self, "default_up_axis", text="Source Up Axis")
        layout.prop(self, "default_rotation")
        layout.prop(self, "default_placement")
        layout.prop(self, "default_scale")
        layout.separator()

        # ── Quality & Appearance ──────────────────────────────────────────────
        layout.label(text="Quality & Appearance")
        layout.prop(self, "tol_preset")
        if self.tol_preset == "CUSTOM":
            layout.prop(self, "tol_linear")
            layout.prop(self, "tol_angular")
        layout.prop(self, "tol_relative")
        layout.prop(self, "import_materials")
        layout.prop(self, "shade_smooth")
        layout.separator()

        # ── Structure ─────────────────────────────────────────────────────────
        layout.label(text="Structure")
        layout.prop(self, "use_assembly_collections")
        layout.prop(self, "show_progress")
        layout.separator()

        # ── Cleanup ───────────────────────────────────────────────────────────
        layout.label(text="Cleanup")
        layout.prop(self, "cleanup_topology")
        if self.cleanup_topology:
            box = layout.box()
            box.prop(self, "ct_doubles")
            if self.ct_doubles:
                box.prop(self, "ct_doubles_dist")
            box.prop(self, "ct_dissolve")
            if self.ct_dissolve:
                box.prop(self, "ct_dissolve_angle")


def register():
    bpy.utils.register_class(STEPImporterPreferences)


def unregister():
    bpy.utils.unregister_class(STEPImporterPreferences)
