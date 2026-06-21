import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty
from bpy.types import Operator
from bpy_extras.io_utils import ImportHelper

from .importer import import_step
from .utils import cascadio_available

_AXIS_ITEMS = [
    ("X", "X", ""),
    ("Y", "Y", ""),
    ("Z", "Z", ""),
    ("MINUS_X", "-X", ""),
    ("MINUS_Y", "-Y", ""),
    ("MINUS_Z", "-Z", ""),
]

_ROTATION_ITEMS = [
    ("-90", "-90°", "Rotate 90° counter-clockwise"),
    ("0", "0°", "No rotation"),
    ("90", "90°", "Rotate 90° clockwise"),
    ("180", "180°", "Rotate 180°"),
]

# (prop_name, UI label, skip-by-default, name prefixes to match, tooltip)
_CONSTRUCTION_FILTERS = [
    (
        "skip_axes",
        "Axes",
        True,
        ("axes", "axis"),
        "Axis indicator objects (Axes, Axis001…)",
    ),
    (
        "skip_sketches",
        "Sketches",
        True,
        ("sketch",),
        "Sketch objects from parametric history",
    ),
    ("skip_lines", "Lines", True, ("line",), "Construction line objects"),
    (
        "skip_hatches",
        "Hatches",
        True,
        ("hatch",),
        "2D hatch/fill patterns used in architectural drawings",
    ),
    (
        "skip_wall_traces",
        "Wall Traces",
        False,
        ("walltrace", "wall_trace"),
        "Wall tracing/annotation objects",
    ),
    ("skip_wires", "Wires", False, ("wire",), "Wire/edge-only objects"),
    (
        "skip_rectangles",
        "Rectangles",
        False,
        ("rectangle",),
        "Rectangle sketch objects",
    ),
    (
        "skip_extrudes",
        "Extrude History",
        False,
        ("extrude",),
        "FreeCAD extrude-operation history objects",
    ),
    (
        "skip_cuts",
        "Cuts / Pockets",
        False,
        ("cut", "pocket", "chamfer"),
        "Cut, pocket, and chamfer operation objects",
    ),
    (
        "skip_terrain",
        "Terrain / Site",
        False,
        ("terrain", "topography", "site"),
        "Terrain, topography, and site objects",
    ),
]


class ImportSTEPOperator(Operator, ImportHelper):
    """Import a STEP or IGES file into the current scene"""

    bl_idname = "import_scene.step"
    bl_label = "Import STEP/IGES"
    bl_options = {"REGISTER", "UNDO"}

    filename_ext = ".step"
    filter_glob: StringProperty(
        default="*.step;*.stp;*.iges;*.igs",
        options={"HIDDEN"},
    )

    up_axis: EnumProperty(
        name="Source Up Axis",
        description="Which axis was 'up' in the application that exported this file (will be rotated to Blender's +Z)",
        items=_AXIS_ITEMS,
        default="Y",
    )

    rotation_deg: EnumProperty(
        name="Rotation",
        description="Degrees to rotate around the vertical axis after up-axis correction",
        items=_ROTATION_ITEMS,
        default="0",
    )

    merge_objects: BoolProperty(
        name="Merge Bodies",
        description="Join all imported bodies into a single mesh object",
        default=False,
    )

    # ── Construction geometry filters ─────────────────────────────────────────
    skip_axes: BoolProperty(
        name="Axes", description=_CONSTRUCTION_FILTERS[0][4], default=True
    )
    skip_sketches: BoolProperty(
        name="Sketches", description=_CONSTRUCTION_FILTERS[1][4], default=True
    )
    skip_lines: BoolProperty(
        name="Lines", description=_CONSTRUCTION_FILTERS[2][4], default=True
    )
    skip_hatches: BoolProperty(
        name="Hatches", description=_CONSTRUCTION_FILTERS[3][4], default=True
    )
    skip_wall_traces: BoolProperty(
        name="Wall Traces", description=_CONSTRUCTION_FILTERS[4][4], default=False
    )
    skip_wires: BoolProperty(
        name="Wires", description=_CONSTRUCTION_FILTERS[5][4], default=False
    )
    skip_rectangles: BoolProperty(
        name="Rectangles", description=_CONSTRUCTION_FILTERS[6][4], default=False
    )
    skip_extrudes: BoolProperty(
        name="Extrude History", description=_CONSTRUCTION_FILTERS[7][4], default=False
    )
    skip_cuts: BoolProperty(
        name="Cuts / Pockets", description=_CONSTRUCTION_FILTERS[8][4], default=False
    )
    skip_terrain: BoolProperty(
        name="Terrain / Site", description=_CONSTRUCTION_FILTERS[9][4], default=False
    )

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        prefs = context.preferences.addons.get(__package__)
        if prefs:
            layout.prop(prefs.preferences, "import_materials")
            layout.separator()

        layout.label(text="Transform")
        layout.prop(self, "up_axis", text="Up in Source App")
        layout.prop(self, "rotation_deg")

        layout.separator()
        layout.label(text="Tolerances (for cascadio conversion)")
        if prefs:
            layout.prop(prefs.preferences, "tol_linear")
            layout.prop(prefs.preferences, "tol_angular")
            layout.prop(prefs.preferences, "tol_relative")
            layout.separator()
        layout.label(text="Post-Import Cleanup")
        if prefs:
            layout.prop(prefs.preferences, "shade_smooth")
            layout.prop(prefs.preferences, "cleanup_topology")
            if prefs.preferences.cleanup_topology:
                box = layout.box()
                box.label(text="Cleanup Options")
                box.prop(prefs.preferences, "ct_doubles")
                if prefs.preferences.ct_doubles:
                    box.prop(prefs.preferences, "ct_doubles_dist")
                box.prop(prefs.preferences, "ct_dissolve")
                if prefs.preferences.ct_dissolve:
                    box.prop(prefs.preferences, "ct_dissolve_angle")
        layout.prop(self, "merge_objects")

        layout.separator()
        header, panel = layout.panel("step_filters", default_closed=True)
        header.label(text="Skip Construction Geometry")
        if panel:
            col = panel.column(align=True)
            for prop_name, label, *_ in _CONSTRUCTION_FILTERS:
                col.prop(self, prop_name)

    def invoke(self, context, event):
        prefs = context.preferences.addons.get(__package__)
        if prefs:
            self.up_axis = prefs.preferences.default_up_axis
            self.rotation_deg = prefs.preferences.default_rotation

        if self.filepath:
            return context.window_manager.invoke_props_dialog(self)

        return super().invoke(context, event)

    def execute(self, context):
        if not cascadio_available():
            self.report(
                {"ERROR"},
                "cascadio is not available. Check the extension is properly installed.",
            )
            return {"CANCELLED"}

        try:
            skip_prefixes = frozenset(
                p
                for prop_name, _label, _default, prefixes, _tip in _CONSTRUCTION_FILTERS
                if getattr(self, prop_name)
                for p in prefixes
            )
            import_step(
                self.filepath,
                up_axis=self.up_axis,
                rotation_deg=float(self.rotation_deg),
                merge_objects=self.merge_objects,
                skip_prefixes=skip_prefixes,
            )
        except Exception as e:
            self.report({"ERROR"}, f"Import failed: {e}")
            return {"CANCELLED"}

        return {"FINISHED"}


class STEP_FH_import(bpy.types.FileHandler):
    """Drag-and-drop support for STEP/IGES files onto the 3D viewport."""

    bl_idname = "STEP_FH_import"
    bl_label = "STEP/IGES File Handler"
    bl_import_operator = "import_scene.step"
    bl_file_extensions = ".step;.stp;.iges;.igs"

    @classmethod
    def poll_drop(cls, context):
        return context.area and context.area.type == "VIEW_3D"


def _menu_func_import(self, context):
    self.layout.operator(
        ImportSTEPOperator.bl_idname, text="STEP/IGES (.step/.stp/.igs)"
    )


def register():
    bpy.utils.register_class(ImportSTEPOperator)
    bpy.utils.register_class(STEP_FH_import)
    bpy.types.TOPBAR_MT_file_import.append(_menu_func_import)


def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(_menu_func_import)
    bpy.utils.unregister_class(STEP_FH_import)
    bpy.utils.unregister_class(ImportSTEPOperator)
