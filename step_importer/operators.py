import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty
from bpy.types import Operator
from bpy_extras.io_utils import ImportHelper

from .importer import import_step
from .utils import cascadio_available

# Axis enum items shared between the operator and preferences
_AXIS_ITEMS = [
    ("X",       "X",        ""),
    ("Y",       "Y",        ""),
    ("Z",       "Z",        ""),
    ("MINUS_X", "-X",       ""),
    ("MINUS_Y", "-Y",       ""),
    ("MINUS_Z", "-Z",       ""),
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

    # ── Per-import options (shown in the file browser sidebar) ────────────────

    forward_axis: EnumProperty(
        name="Forward",
        description="Forward axis of the imported model",
        items=_AXIS_ITEMS,
        default="MINUS_Z",
    )

    up_axis: EnumProperty(
        name="Up",
        description="Up axis of the imported model",
        items=_AXIS_ITEMS,
        default="Y",
    )

    merge_objects: BoolProperty(
        name="Merge Bodies",
        description="Join all imported bodies into a single mesh object",
        default=False,
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
        layout.prop(self, "forward_axis")
        layout.prop(self, "up_axis")

        layout.separator()
        layout.prop(self, "merge_objects")

    def invoke(self, context, event):
        # Pre-fill axis defaults from addon preferences
        prefs = context.preferences.addons.get(__package__)
        if prefs:
            self.forward_axis = prefs.preferences.default_forward_axis
            self.up_axis = prefs.preferences.default_up_axis
        return super().invoke(context, event)

    def execute(self, context):
        if not cascadio_available():
            self.report(
                {"ERROR"},
                "cascadio is not available. Check the extension is properly installed.",
            )
            return {"CANCELLED"}

        try:
            import_step(
                self.filepath,
                forward_axis=self.forward_axis,
                up_axis=self.up_axis,
                merge_objects=self.merge_objects,
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
    self.layout.operator(ImportSTEPOperator.bl_idname, text="STEP/IGES (.step/.stp/.igs)")


def register():
    bpy.utils.register_class(ImportSTEPOperator)
    bpy.utils.register_class(STEP_FH_import)
    bpy.types.TOPBAR_MT_file_import.append(_menu_func_import)


def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(_menu_func_import)
    bpy.utils.unregister_class(STEP_FH_import)
    bpy.utils.unregister_class(ImportSTEPOperator)

