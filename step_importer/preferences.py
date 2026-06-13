import bpy
from bpy.types import AddonPreferences
from bpy.props import BoolProperty, EnumProperty

_AXIS_ITEMS = [
    ("X",       "X",  ""),
    ("Y",       "Y",  ""),
    ("Z",       "Z",  ""),
    ("MINUS_X", "-X", ""),
    ("MINUS_Y", "-Y", ""),
    ("MINUS_Z", "-Z", ""),
]


class STEPImporterPreferences(AddonPreferences):
    bl_idname = __package__

    import_materials: BoolProperty(
        name="Import Materials",
        description="Apply material colors from STEP file when available",
        default=True,
    )

    default_forward_axis: EnumProperty(
        name="Default Forward",
        description="Default forward axis used for new imports",
        items=_AXIS_ITEMS,
        default="MINUS_Z",
    )

    default_up_axis: EnumProperty(
        name="Default Up",
        description="Default up axis used for new imports (Y = glTF standard, Z = FreeCAD/engineering default)",
        items=_AXIS_ITEMS,
        default="Y",
    )

    show_progress: BoolProperty(
        name="Show Import Progress",
        description="Display a GPU progress bar in the 3D viewport during import",
        default=True,
    )

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        layout.prop(self, "import_materials")
        layout.prop(self, "show_progress")

        layout.separator()
        layout.label(text="Default Axes (pre-fill for new imports)")
        layout.prop(self, "default_forward_axis")
        layout.prop(self, "default_up_axis")


def register():
    bpy.utils.register_class(STEPImporterPreferences)


def unregister():
    bpy.utils.unregister_class(STEPImporterPreferences)

