import bpy
from bpy.types import AddonPreferences
from bpy.props import BoolProperty, EnumProperty

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


class STEPImporterPreferences(AddonPreferences):
    bl_idname = __package__

    import_materials: BoolProperty(
        name="Import Materials",
        description="Apply material colors from STEP file when available",
        default=True,
    )

    default_up_axis: EnumProperty(
        name="Source Up Axis",
        description="Which axis was 'up' in the application that exported the file (Y = glTF/FreeCAD/most CAD, Z = some CAD tools)",
        items=_AXIS_ITEMS,
        default="Y",
    )

    default_rotation: EnumProperty(
        name="Default Rotation",
        description="Default rotation around the vertical axis after up-axis correction",
        items=_ROTATION_ITEMS,
        default="0",
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
        layout.label(text="Default Transform (pre-fill for new imports)")
        layout.prop(self, "default_up_axis", text="Up in Source App")
        layout.prop(self, "default_rotation")


def register():
    bpy.utils.register_class(STEPImporterPreferences)


def unregister():
    bpy.utils.unregister_class(STEPImporterPreferences)
